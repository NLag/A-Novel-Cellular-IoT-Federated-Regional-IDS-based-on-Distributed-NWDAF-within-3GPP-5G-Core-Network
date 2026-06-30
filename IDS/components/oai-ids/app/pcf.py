from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import subprocess
import time
from typing import Any

from .config import IdsConfig


LOGGER = logging.getLogger("oai.ids.pcf")


@dataclass
class PcfTrafficInfluenceResult:
    status: str
    body: str = ""
    error: str = ""
    attempts: int = 0


def sm_policy_uri(base_uri: str) -> str:
    base = base_uri.rstrip("/")
    if base.endswith("/sm-policies"):
        return base
    return f"{base}/sm-policies"


def ids_traffic_influence_uri(base_uri: str) -> str:
    base = base_uri.rstrip("/")
    if base.endswith("/sm-policies"):
        base = base[: -len("/sm-policies")]
    if base.endswith("/ids-traffic-influence"):
        return base
    return f"{base}/ids-traffic-influence"


def build_sm_policy_context(config: IdsConfig) -> dict[str, Any]:
    traffic = config.traffic_influence
    slice_info: dict[str, Any] = {"sst": traffic.snssai_sst}
    if traffic.snssai_sd:
        slice_info["sd"] = traffic.snssai_sd

    return {
        "supi": traffic.supi,
        "pduSessionId": traffic.pdu_session_id,
        "pduSessionType": traffic.pdu_session_type,
        "dnn": traffic.dnn,
        "notificationUri": traffic.notification_uri,
        "sliceInfo": slice_info,
        "servingNetwork": {
            "mcc": config.serving_area.mcc,
            "mnc": config.serving_area.mnc,
        },
        "accessType": "3GPP_ACCESS",
        "ratType": "NR",
    }


class PcfTrafficInfluenceClient:
    def __init__(self, config: IdsConfig):
        self.config = config

    def request_policy(self) -> PcfTrafficInfluenceResult:
        traffic = self.config.traffic_influence
        payload = build_sm_policy_context(self.config)

        if not traffic.enabled or traffic.mode == "disabled":
            return PcfTrafficInfluenceResult(status="disabled")

        if traffic.mode == "observe-only":
            LOGGER.info(
                "traffic influence observe-only request: %s",
                json.dumps(payload, sort_keys=True),
            )
            return PcfTrafficInfluenceResult(
                status="observe-only",
                body=json.dumps(payload, sort_keys=True),
                attempts=0,
            )

        if traffic.mode not in {"sm-policy-probe", "preconfigured-rule"}:
            return PcfTrafficInfluenceResult(
                status="unsupported",
                error=f"unsupported traffic influence mode: {traffic.mode}",
            )

        uri = sm_policy_uri(traffic.pcf_base_uri)
        last_error = ""
        for attempt in range(1, traffic.max_attempts + 1):
            try:
                self._activate_once()
                body = self._post_json(uri, payload, traffic.request_timeout_seconds)
                return PcfTrafficInfluenceResult(
                    status="accepted",
                    body=body,
                    attempts=attempt,
                )
            except Exception as exc:
                last_error = str(exc)
                LOGGER.warning(
                    "PCF traffic influence request failed on attempt %d/%d: %s",
                    attempt,
                    traffic.max_attempts,
                    last_error,
                )
                if attempt < traffic.max_attempts:
                    time.sleep(traffic.retry_interval_seconds)

        return PcfTrafficInfluenceResult(
            status="failed",
            error=last_error,
            attempts=traffic.max_attempts,
        )

    def refresh_policy(self) -> PcfTrafficInfluenceResult:
        traffic = self.config.traffic_influence
        if not traffic.enabled or traffic.mode in {"disabled", "observe-only"}:
            return PcfTrafficInfluenceResult(status="disabled")

        last_error = ""
        for attempt in range(1, traffic.max_attempts + 1):
            try:
                body = self._activate_once()
                return PcfTrafficInfluenceResult(
                    status="accepted",
                    body=body,
                    attempts=attempt,
                )
            except Exception as exc:
                last_error = str(exc)
                LOGGER.warning(
                    "PCF traffic influence refresh failed on attempt %d/%d: %s",
                    attempt,
                    traffic.max_attempts,
                    last_error,
                )
                if attempt < traffic.max_attempts:
                    time.sleep(traffic.retry_interval_seconds)

        return PcfTrafficInfluenceResult(
            status="failed",
            error=last_error,
            attempts=traffic.max_attempts,
        )

    def release_policy(self) -> PcfTrafficInfluenceResult:
        traffic = self.config.traffic_influence
        if not traffic.enabled or traffic.mode in {"disabled", "observe-only"}:
            return PcfTrafficInfluenceResult(status="disabled")

        uri = ids_traffic_influence_uri(traffic.pcf_base_uri)
        try:
            body = self._post_json(
                uri,
                {
                    "active": False,
                    "pccRuleId": traffic.duplication_policy_id,
                    "source": self.config.instance_id,
                },
                traffic.request_timeout_seconds,
            )
            return PcfTrafficInfluenceResult(status="released", body=body, attempts=1)
        except Exception as exc:
            return PcfTrafficInfluenceResult(status="release-failed", error=str(exc), attempts=1)

    def _activate_once(self) -> str:
        traffic = self.config.traffic_influence
        uri = ids_traffic_influence_uri(traffic.pcf_base_uri)
        return self._post_json(
            uri,
            {
                "active": True,
                "pccRuleId": traffic.duplication_policy_id,
                "source": self.config.instance_id,
            },
            traffic.request_timeout_seconds,
        )

    @staticmethod
    def _post_json(uri: str, payload: dict[str, Any], timeout_seconds: int) -> str:
        command = [
            "curl",
            "--silent",
            "--show-error",
            "--fail-with-body",
            "--http2-prior-knowledge",
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
            raise RuntimeError(details or "unknown PCF request error")
        return result.stdout.strip()
