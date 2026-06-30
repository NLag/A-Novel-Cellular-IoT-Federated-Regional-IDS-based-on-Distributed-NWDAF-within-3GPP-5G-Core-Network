from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import subprocess
import time
from typing import Any
from urllib.parse import urlparse

from .config import IdsConfig


LOGGER = logging.getLogger("oai.ids.nwdaf")


@dataclass(frozen=True)
class NwdafIntegrationResult:
    status: str
    body: str = ""
    error: str = ""
    attempts: int = 0
    subscription_id: str = ""


@dataclass(frozen=True)
class NwdafModelUpdate:
    correlation_id: str
    event: str
    model_url: str
    manifest_url: str
    model_id: str
    accuracy: str
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "correlationId": self.correlation_id,
            "event": self.event,
            "modelUrl": self.model_url,
            "manifestUrl": self.manifest_url,
            "modelId": self.model_id,
            "accuracy": self.accuracy,
            "raw": self.raw,
        }


def ml_model_subscriptions_uri(base_uri: str) -> str:
    base = base_uri.rstrip("/")
    if base.endswith("/subscriptions"):
        return base
    return f"{base}/subscriptions"


def ml_model_subscription_uri(base_uri: str, subscription_id: str) -> str:
    return f"{ml_model_subscriptions_uri(base_uri)}/{subscription_id}"


def ml_model_info_uri_from_file_url(model_url: str) -> str:
    model_url = model_url.rstrip("/")
    if model_url.endswith("/file"):
        return model_url[: -len("/file")]
    return model_url


def build_ml_model_subscription(config: IdsConfig) -> dict[str, Any]:
    nwdaf = config.nwdaf_integration
    payload: dict[str, Any] = {
        "notifUri": nwdaf.notification_uri,
        "notifCorreId": nwdaf.notif_correlation_id,
        "mLModels": [
            {
                "mLEvent": nwdaf.ml_event,
            }
        ],
    }
    if nwdaf.supported_features:
        payload["suppFeat"] = nwdaf.supported_features
    if nwdaf.expiry:
        payload["expiry"] = nwdaf.expiry
    return payload


def build_ids_report_record(config: IdsConfig, report: dict[str, Any]) -> dict[str, Any]:
    return {
        "sourceNf": "IDS",
        "idsInstanceId": config.instance_id,
        "region": config.serving_area.region,
        "mcc": config.serving_area.mcc,
        "mnc": config.serving_area.mnc,
        "tac": config.serving_area.tac,
        "reportId": report.get("reportId", ""),
        "timestamp": report.get("timestamp"),
        "predictedClass": report.get("predictedClass", ""),
        "score": report.get("score"),
        "ueIp": report.get("ueIp"),
        "teid": report.get("teid"),
        "packetSize": report.get("packetSize"),
        "action": report.get("action"),
        "report": report,
    }


def parse_model_update_notification(payload: dict[str, Any]) -> NwdafModelUpdate:
    model_infos = payload.get("mLModelInfo") or payload.get("mlModelInfo") or []
    if not isinstance(model_infos, list) or not model_infos:
        raise ValueError("NWDAF model notification does not include mLModelInfo")

    model_info = model_infos[0] or {}
    file_addr = model_info.get("mLFileAddr") or model_info.get("mlFileAddr") or {}
    model_url = file_addr.get("mlModelUrl") or file_addr.get("mLModelUrl") or ""
    manifest_url = model_info.get("idsModelManifestUrl") or ""
    if not model_url:
        raise ValueError("NWDAF model notification does not include mlModelUrl")

    return NwdafModelUpdate(
        correlation_id=str(
            payload.get("notifCorreId") or payload.get("notifCorrelationId") or ""
        ),
        event=str(model_info.get("mLEvent") or model_info.get("mlEvent") or ""),
        model_url=str(model_url),
        manifest_url=str(manifest_url),
        model_id=_model_id_from_url(str(model_url)),
        accuracy=str(model_info.get("accuracy") or ""),
        raw=payload,
    )


class NwdafMlModelClient:
    def __init__(self, config: IdsConfig):
        self.config = config

    def subscribe_model_updates(self) -> NwdafIntegrationResult:
        nwdaf = self.config.nwdaf_integration
        payload = build_ml_model_subscription(self.config)

        if not nwdaf.enabled or nwdaf.mode == "disabled":
            return NwdafIntegrationResult(status="disabled")

        if nwdaf.mode == "observe-only":
            LOGGER.info(
                "NWDAF model subscription observe-only request: %s",
                json.dumps(payload, sort_keys=True),
            )
            return NwdafIntegrationResult(
                status="observe-only",
                body=json.dumps(payload, sort_keys=True),
                attempts=0,
            )

        if nwdaf.mode != "subscribe":
            return NwdafIntegrationResult(
                status="unsupported",
                error=f"unsupported NWDAF integration mode: {nwdaf.mode}",
            )

        uri = ml_model_subscriptions_uri(nwdaf.base_uri)
        last_error = ""
        for attempt in range(1, nwdaf.max_attempts + 1):
            try:
                body = self._post_json(uri, payload, nwdaf.request_timeout_seconds)
                return NwdafIntegrationResult(
                    status="accepted",
                    body=body,
                    attempts=attempt,
                    subscription_id=_subscription_id_from_body(body),
                )
            except Exception as exc:
                last_error = str(exc)
                LOGGER.warning(
                    "NWDAF model subscription failed on attempt %d/%d: %s",
                    attempt,
                    nwdaf.max_attempts,
                    last_error,
                )
                if attempt < nwdaf.max_attempts:
                    time.sleep(nwdaf.retry_interval_seconds)

        return NwdafIntegrationResult(
            status="failed",
            error=last_error,
            attempts=nwdaf.max_attempts,
        )

    def unsubscribe_model_updates(self, subscription_id: str) -> NwdafIntegrationResult:
        nwdaf = self.config.nwdaf_integration
        if not subscription_id:
            return NwdafIntegrationResult(status="skipped", error="missing subscription ID")
        if not nwdaf.enabled or nwdaf.mode in {"disabled", "observe-only"}:
            return NwdafIntegrationResult(status="disabled")

        uri = ml_model_subscription_uri(nwdaf.base_uri, subscription_id)
        try:
            body = self._delete(uri, nwdaf.request_timeout_seconds)
            return NwdafIntegrationResult(
                status="released",
                body=body,
                attempts=1,
                subscription_id=subscription_id,
            )
        except Exception as exc:
            return NwdafIntegrationResult(
                status="release-failed",
                error=str(exc),
                attempts=1,
                subscription_id=subscription_id,
            )

    def fetch_model_metadata(self, model_url: str) -> NwdafIntegrationResult:
        nwdaf = self.config.nwdaf_integration
        if not nwdaf.enabled or not nwdaf.fetch_model_metadata:
            return NwdafIntegrationResult(status="disabled")
        if nwdaf.mode == "observe-only":
            uri = ml_model_info_uri_from_file_url(model_url)
            LOGGER.info("NWDAF model metadata fetch observe-only request: %s", uri)
            return NwdafIntegrationResult(status="observe-only", body=uri)
        if nwdaf.mode == "disabled":
            return NwdafIntegrationResult(status="disabled")

        uri = ml_model_info_uri_from_file_url(model_url)
        try:
            body = self._get(uri, nwdaf.request_timeout_seconds)
            return NwdafIntegrationResult(status="fetched", body=body, attempts=1)
        except Exception as exc:
            return NwdafIntegrationResult(
                status="failed",
                error=str(exc),
                attempts=1,
            )

    def forward_detection_report(
        self,
        report: dict[str, Any],
    ) -> NwdafIntegrationResult:
        nwdaf = self.config.nwdaf_integration
        if (
            not nwdaf.enabled
            or nwdaf.mode == "disabled"
            or not nwdaf.report_forwarding_enabled
        ):
            return NwdafIntegrationResult(status="disabled")

        payload = build_ids_report_record(self.config, report)
        if nwdaf.mode == "observe-only":
            LOGGER.info(
                "NWDAF IDS report forwarding observe-only request: %s",
                json.dumps(payload, sort_keys=True),
            )
            return NwdafIntegrationResult(
                status="observe-only",
                body=json.dumps(payload, sort_keys=True),
            )

        try:
            body = self._post_json(
                nwdaf.report_forwarding_uri,
                payload,
                nwdaf.request_timeout_seconds,
            )
            return NwdafIntegrationResult(status="accepted", body=body, attempts=1)
        except Exception as exc:
            return NwdafIntegrationResult(
                status="failed",
                error=str(exc),
                attempts=1,
            )

    @staticmethod
    def _post_json(uri: str, payload: dict[str, Any], timeout_seconds: int) -> str:
        command = [
            "curl",
            "--silent",
            "--show-error",
            "--fail-with-body",
            "--max-time",
            str(timeout_seconds),
            "-X",
            "POST",
            uri,
            "-H",
            "Content-Type: application/json",
            "--data-binary",
            json.dumps(payload),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            details = " ".join(
                item
                for item in (result.stderr.strip(), result.stdout.strip())
                if item
            )
            raise RuntimeError(details or "unknown NWDAF request error")
        return result.stdout.strip()

    @staticmethod
    def _get(uri: str, timeout_seconds: int) -> str:
        command = [
            "curl",
            "--silent",
            "--show-error",
            "--fail-with-body",
            "--max-time",
            str(timeout_seconds),
            uri,
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            details = " ".join(
                item
                for item in (result.stderr.strip(), result.stdout.strip())
                if item
            )
            raise RuntimeError(details or "unknown NWDAF request error")
        return result.stdout.strip()

    @staticmethod
    def _delete(uri: str, timeout_seconds: int) -> str:
        command = [
            "curl",
            "--silent",
            "--show-error",
            "--fail-with-body",
            "--max-time",
            str(timeout_seconds),
            "-X",
            "DELETE",
            uri,
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            details = " ".join(
                item
                for item in (result.stderr.strip(), result.stdout.strip())
                if item
            )
            raise RuntimeError(details or "unknown NWDAF request error")
        return result.stdout.strip()


def _subscription_id_from_body(body: str) -> str:
    if not body:
        return ""
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("subscriptionId") or payload.get("subId") or "")


def _model_id_from_url(model_url: str) -> str:
    parsed = urlparse(model_url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[-1] == "file":
        return parts[-2]
    if parts:
        return parts[-1]
    return model_url
