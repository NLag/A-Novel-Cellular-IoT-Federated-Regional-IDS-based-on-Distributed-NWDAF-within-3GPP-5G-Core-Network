from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import signal
import socket
import threading
import time
from typing import Any
import uuid

from .config import IdsConfig, load_config
from .countermeasures import build_countermeasure_plan, summarize_report_action
from .dataset_capture import DatasetCaptureWriter
from .gtpu import GtpuDecapsulationError, decapsulate_gtpu, extract_ipv4_metadata
from .model import classify_packet, vectorize_packet
from .model_registry import ModelRuntime, load_model_runtime
from .nwdaf import NwdafMlModelClient, parse_model_update_notification
from .nrf import NrfClient, NrfRegistration, discover_pod_ip
from .pcf import PcfTrafficInfluenceClient


LOGGER = logging.getLogger("oai.ids")


def log_event(event: str, **fields: Any) -> None:
    LOGGER.info(json.dumps({"event": event, **fields}, sort_keys=True))


class RuntimeState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._packet_count = 0
        self._decode_errors = 0
        self._alert_window = None
        self._alert_active = False
        self._alerts_raised = 0
        self._last_teid = None
        self._last_packet_size = None
        self._last_score = None
        self._last_predicted_class = None
        self._last_report_id = None
        self._last_ue_ip = None
        self._model_artifact = None
        self._traffic_influence_status = "not-started"
        self._traffic_influence_error = None
        self._nwdaf_model_subscription_status = "not-started"
        self._nwdaf_model_subscription_error = None
        self._nwdaf_model_subscription_id = None
        self._last_nwdaf_model_update = None
        self._last_nwdaf_model_metadata_fetch = None
        self._nwdaf_report_forward_status = "not-started"
        self._nwdaf_report_forward_error = None
        self._nwdaf_reports_forwarded = 0
        self._dataset_capture_status = "disabled"
        self._dataset_capture_path = None
        self._dataset_capture_packet_count = 0
        self._last_dataset_capture_record = None

    def record_packet(
        self,
        teid: int,
        packet_size: int,
        score: float,
        predicted_class: str,
        report_id: str,
        ue_ip: str | None,
    ) -> None:
        with self._lock:
            self._packet_count += 1
            self._last_teid = teid
            self._last_packet_size = packet_size
            self._last_score = score
            self._last_predicted_class = predicted_class
            self._last_report_id = report_id
            self._last_ue_ip = ue_ip

    def record_decode_error(self) -> None:
        with self._lock:
            self._decode_errors += 1

    def record_traffic_influence(self, status: str, error: str | None = None) -> None:
        with self._lock:
            self._traffic_influence_status = status
            self._traffic_influence_error = error

    def record_model_artifact(self, model_artifact: dict[str, Any]) -> None:
        with self._lock:
            self._model_artifact = model_artifact

    def record_nwdaf_model_subscription(
        self,
        status: str,
        error: str | None = None,
        subscription_id: str | None = None,
    ) -> None:
        with self._lock:
            self._nwdaf_model_subscription_status = status
            self._nwdaf_model_subscription_error = error
            if subscription_id:
                self._nwdaf_model_subscription_id = subscription_id

    def record_nwdaf_model_update(self, model_update: dict[str, Any]) -> None:
        with self._lock:
            self._last_nwdaf_model_update = model_update

    def record_nwdaf_model_metadata_fetch(
        self,
        status: str,
        error: str | None = None,
        body: str = "",
    ) -> None:
        metadata: Any = body
        if body:
            try:
                metadata = json.loads(body)
            except json.JSONDecodeError:
                metadata = body
        with self._lock:
            self._last_nwdaf_model_metadata_fetch = {
                "status": status,
                "error": error,
                "metadata": metadata,
            }

    def record_nwdaf_report_forward(self, status: str, error: str | None = None) -> None:
        with self._lock:
            self._nwdaf_report_forward_status = status
            self._nwdaf_report_forward_error = error
            if status == "accepted":
                self._nwdaf_reports_forwarded += 1

    def record_dataset_capture_started(self, status: str, path: str | None = None) -> None:
        with self._lock:
            self._dataset_capture_status = status
            self._dataset_capture_path = path

    def record_dataset_capture_packet(self, record: dict[str, Any] | None) -> None:
        if not record:
            return
        with self._lock:
            self._dataset_capture_packet_count += 1
            self._last_dataset_capture_record = record

    def record_dataset_capture_error(self, error: str) -> None:
        with self._lock:
            self._dataset_capture_status = "error"
            self._last_dataset_capture_record = {"error": error}

    def evaluate_alert(
        self, is_malicious: bool, window: int, threshold: int, clear_below: int
    ) -> tuple[bool, bool, int]:
        """Sliding-window alert latch.

        Returns (notify, active, malicious_count). ``notify`` is True only on the
        rising edge into an alert (>= threshold malicious within the last ``window``
        inspected packets); the latch clears once the count falls to ``clear_below``.
        """
        with self._lock:
            if self._alert_window is None:
                self._alert_window = []
            self._alert_window.append(1 if is_malicious else 0)
            if len(self._alert_window) > window:
                del self._alert_window[: len(self._alert_window) - window]
            count = sum(self._alert_window)
            notify = False
            if not self._alert_active:
                if count >= threshold:
                    self._alert_active = True
                    self._alerts_raised += 1
                    notify = True
            elif count <= clear_below:
                self._alert_active = False
            return notify, self._alert_active, count

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "packetCount": self._packet_count,
                "decodeErrors": self._decode_errors,
                "alertsRaised": self._alerts_raised,
                "alertActive": self._alert_active,
                "lastTeid": self._last_teid,
                "lastPacketSize": self._last_packet_size,
                "lastScore": self._last_score,
                "lastPredictedClass": self._last_predicted_class,
                "lastReportId": self._last_report_id,
                "lastUeIp": self._last_ue_ip,
                "modelArtifact": self._model_artifact,
                "trafficInfluenceStatus": self._traffic_influence_status,
                "trafficInfluenceError": self._traffic_influence_error,
                "nwdafModelSubscriptionStatus": self._nwdaf_model_subscription_status,
                "nwdafModelSubscriptionError": self._nwdaf_model_subscription_error,
                "nwdafModelSubscriptionId": self._nwdaf_model_subscription_id,
                "lastNwdafModelUpdate": self._last_nwdaf_model_update,
                "lastNwdafModelMetadataFetch": self._last_nwdaf_model_metadata_fetch,
                "nwdafReportForwardStatus": self._nwdaf_report_forward_status,
                "nwdafReportForwardError": self._nwdaf_report_forward_error,
                "nwdafReportsForwarded": self._nwdaf_reports_forwarded,
                "datasetCaptureStatus": self._dataset_capture_status,
                "datasetCapturePath": self._dataset_capture_path,
                "datasetCapturePacketCount": self._dataset_capture_packet_count,
                "lastDatasetCaptureRecord": self._last_dataset_capture_record,
            }


class ReportStore:
    def __init__(self, storage: str, file_path: str) -> None:
        self.storage = storage
        self.file_path = Path(file_path)
        self._lock = threading.Lock()
        self._reports: list[dict[str, Any]] = []

    def add(self, report: dict[str, Any]) -> None:
        with self._lock:
            self._reports.append(report)
            if self.storage == "file":
                self.file_path.parent.mkdir(parents=True, exist_ok=True)
                with self.file_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(report, sort_keys=True) + "\n")

    def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._reports[-limit:])


class SubscriptionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscriptions: dict[str, dict[str, Any]] = {}

    def add(self, payload: dict[str, Any]) -> dict[str, Any]:
        subscription_id = str(uuid.uuid4())
        subscription = {
            "subscriptionId": subscription_id,
            "createdAt": time.time(),
            "payload": payload,
        }
        with self._lock:
            self._subscriptions[subscription_id] = subscription
        return subscription

    def delete(self, subscription_id: str) -> bool:
        with self._lock:
            return self._subscriptions.pop(subscription_id, None) is not None

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._subscriptions.values())


def build_detection_report(
    config: IdsConfig,
    teid: int | None,
    packet_size: int | None,
    predicted_class: str,
    score: float,
    source: str,
    ue_ip: str | None = None,
    detector: dict[str, Any] | None = None,
    model_artifact: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = {
        "reportId": str(uuid.uuid4()),
        "idsInstanceId": config.instance_id,
        "timestamp": time.time(),
        "region": config.serving_area.region,
        "mcc": config.serving_area.mcc,
        "mnc": config.serving_area.mnc,
        "tac": config.serving_area.tac,
        "teid": teid,
        "ueIp": ue_ip,
        "packetSize": packet_size,
        "predictedClass": predicted_class,
        "score": score,
        "source": source,
        "detector": detector or {},
        "modelArtifact": model_artifact or {},
        "metadata": metadata or {},
    }
    planned_countermeasures = build_countermeasure_plan(
        config=config.countermeasures,
        predicted_class=predicted_class,
        report_context=report,
    )
    report["action"] = summarize_report_action(
        predicted_class=predicted_class,
        config=config.countermeasures,
        planned_countermeasures=planned_countermeasures,
    )
    report["countermeasures"] = planned_countermeasures
    return report


def log_countermeasure_plan(report: dict[str, Any]) -> None:
    for countermeasure in report.get("countermeasures", []):
        log_event(
            "ids-countermeasure-planned",
            report_id=report["reportId"],
            countermeasure=countermeasure["name"],
            target_nf=countermeasure["targetNf"],
            service=countermeasure["service"],
            mode=countermeasure["mode"],
            status=countermeasure["status"],
            called=countermeasure["called"],
            ue_ip=countermeasure["context"].get("ueIp"),
            teid=countermeasure["context"].get("teid"),
        )


def forward_report_to_nwdaf(
    config: IdsConfig,
    state: RuntimeState,
    report: dict[str, Any],
) -> None:
    nwdaf = config.nwdaf_integration
    if (
        not nwdaf.enabled
        or nwdaf.mode == "disabled"
        or not nwdaf.report_forwarding_enabled
    ):
        return

    result = NwdafMlModelClient(config).forward_detection_report(report)
    state.record_nwdaf_report_forward(result.status, result.error or None)
    log_event(
        "ids-nwdaf-report-forward-completed",
        report_id=report.get("reportId"),
        status=result.status,
        attempts=result.attempts,
        error=result.error,
    )


def build_http_handler(
    config: IdsConfig,
    state: RuntimeState,
    ready_event: threading.Event,
    reports: ReportStore,
    subscriptions: SubscriptionStore,
):
    class IdsHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/healthz":
                self._write_json(HTTPStatus.OK, {"status": "ok"})
                return
            if self.path == "/readyz":
                status = HTTPStatus.OK if ready_event.is_set() else HTTPStatus.SERVICE_UNAVAILABLE
                self._write_json(status, {"ready": ready_event.is_set()})
                return
            if self.path == "/stats":
                payload = {
                    "idsInstanceId": config.instance_id,
                    "host": config.host,
                    "region": config.serving_area.region,
                    "mcc": config.serving_area.mcc,
                    "mnc": config.serving_area.mnc,
                    "tac": config.serving_area.tac,
                    **state.snapshot(),
                }
                self._write_json(HTTPStatus.OK, payload)
                return
            if self.path == "/nids-security/v1/reports":
                self._write_json(HTTPStatus.OK, {"reports": reports.list_recent()})
                return
            if self.path == "/nids-event-exposure/v1/subscriptions":
                self._write_json(HTTPStatus.OK, {"subscriptions": subscriptions.list()})
                return
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path == "/nids-event-exposure/v1/subscriptions":
                payload = self._read_json()
                subscription = subscriptions.add(payload)
                log_event(
                    "ids-event-subscription-created",
                    subscription_id=subscription["subscriptionId"],
                )
                self._write_json(HTTPStatus.CREATED, subscription)
                return
            if self.path == "/nids-security/v1/reports":
                payload = self._read_json()
                report = build_detection_report(
                    config=config,
                    teid=payload.get("teid"),
                    packet_size=payload.get("packetSize"),
                    predicted_class=payload.get("predictedClass", "unknown"),
                    score=float(payload.get("score", 0.0)),
                    source="api",
                    ue_ip=payload.get("ueIp"),
                    detector=payload.get("detector"),
                    model_artifact=payload.get("modelArtifact"),
                    metadata=payload.get("metadata"),
                )
                stored_report = {**report, "payload": payload}
                reports.add(stored_report)
                log_countermeasure_plan(report)
                forward_report_to_nwdaf(config, state, stored_report)
                log_event(
                    "ids-report-created",
                    report_id=report["reportId"],
                    source="api",
                    predicted_class=report["predictedClass"],
                    action=report["action"],
                )
                self._write_json(HTTPStatus.CREATED, report)
                return
            if self.path == "/nids-model-management/v1/model-notifications":
                payload = self._read_json()
                try:
                    model_update = parse_model_update_notification(payload)
                except ValueError as exc:
                    self._write_json(
                        HTTPStatus.BAD_REQUEST,
                        {"error": "invalid NWDAF model notification", "detail": str(exc)},
                    )
                    return
                state.record_nwdaf_model_update(model_update.to_dict())
                log_event(
                    "ids-nwdaf-model-notification-received",
                    correlation_id=model_update.correlation_id,
                    ml_event=model_update.event,
                    model_id=model_update.model_id,
                    model_url=model_update.model_url,
                    manifest_url=model_update.manifest_url,
                    accuracy=model_update.accuracy,
                )
                fetch_result = NwdafMlModelClient(config).fetch_model_metadata(
                    model_update.manifest_url or model_update.model_url
                )
                if fetch_result.status != "disabled":
                    state.record_nwdaf_model_metadata_fetch(
                        fetch_result.status,
                        fetch_result.error or None,
                        fetch_result.body,
                    )
                    log_event(
                        "ids-nwdaf-model-metadata-fetch-completed",
                        model_id=model_update.model_id,
                        status=fetch_result.status,
                        attempts=fetch_result.attempts,
                        error=fetch_result.error,
                    )
                self._write_json(
                    HTTPStatus.ACCEPTED,
                    {
                        "status": "accepted",
                        "modelUpdate": model_update.to_dict(),
                        "metadataFetchStatus": fetch_result.status,
                        "note": "model validation and hot-swap are tracked as Phase 2 follow-up work",
                    },
                )
                return
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_DELETE(self) -> None:  # noqa: N802
            prefix = "/nids-event-exposure/v1/subscriptions/"
            if self.path.startswith(prefix):
                subscription_id = self.path[len(prefix) :]
                if subscriptions.delete(subscription_id):
                    log_event(
                        "ids-event-subscription-deleted",
                        subscription_id=subscription_id,
                    )
                    self._write_json(HTTPStatus.OK, {"deleted": subscription_id})
                    return
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "subscription not found"})
                return
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            body = self.rfile.read(length)
            if not body:
                return {}
            return json.loads(body.decode("utf-8"))

        def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return IdsHandler


def process_duplicated_packets(
    config: IdsConfig,
    state: RuntimeState,
    stop_event: threading.Event,
    model_runtime: ModelRuntime,
    reports: ReportStore,
    dataset_capture: DatasetCaptureWriter,
) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((config.gtpu.host, config.gtpu.port))
    sock.settimeout(1.0)
    log_event(
        "ids-gtpu-listener-started",
        host=config.gtpu.host,
        port=config.gtpu.port,
        region=config.serving_area.region,
    )

    try:
        while not stop_event.is_set():
            try:
                packet, peer = sock.recvfrom(65535)
            except socket.timeout:
                continue

            try:
                log_event("ids-packet-received", peer=f"{peer[0]}:{peer[1]}", size=len(packet))
                gtpu_packet = decapsulate_gtpu(packet)
                packet_vector = vectorize_packet(
                    gtpu_packet.payload, model_runtime.metadata.packet_size
                )
                result = classify_packet(model_runtime.detector, packet_vector)
                ipv4_metadata = extract_ipv4_metadata(gtpu_packet.payload)
                ue_ip = ipv4_metadata.source_ip if ipv4_metadata else None
                metadata: dict[str, Any] = {
                    "gtpu": {
                        "peer": f"{peer[0]}:{peer[1]}",
                        "hasExtensionHeaders": gtpu_packet.has_extension_headers,
                        "messageLength": gtpu_packet.message_length,
                    },
                    "features": result.features,
                }
                if ipv4_metadata:
                    metadata["ipv4"] = {
                        "sourceIp": ipv4_metadata.source_ip,
                        "destinationIp": ipv4_metadata.destination_ip,
                        "protocol": ipv4_metadata.protocol,
                        "totalLength": ipv4_metadata.total_length,
                    }
                packet_timestamp = time.time()
                report = build_detection_report(
                    config=config,
                    teid=gtpu_packet.teid,
                    packet_size=len(gtpu_packet.payload),
                    predicted_class=result.predicted_class,
                    score=result.score,
                    source="gtpu",
                    ue_ip=ue_ip,
                    detector={
                        "name": "deterministic-placeholder",
                        "mode": model_runtime.detector.mode,
                        "reason": result.reason,
                        "modelVersion": model_runtime.metadata.model_version,
                        "architecture": model_runtime.metadata.architecture,
                    },
                    model_artifact=model_runtime.metadata.to_dict(),
                    metadata=metadata,
                )
                reports.add(report)
                # Sliding-window alert gate: suppress isolated false positives and
                # cut CP signaling by only notifying on sustained malicious activity.
                is_malicious = result.predicted_index != 0
                if config.alerting.enabled:
                    notify, alert_active, malicious_in_window = state.evaluate_alert(
                        is_malicious,
                        config.alerting.window,
                        config.alerting.threshold,
                        config.alerting.clear_below,
                    )
                else:
                    notify, alert_active, malicious_in_window = is_malicious, is_malicious, 0
                if notify:
                    log_event(
                        "ids-alert-raised",
                        predicted_class=result.predicted_class,
                        reason=result.reason,
                        maliciousInWindow=malicious_in_window,
                        window=config.alerting.window,
                        threshold=config.alerting.threshold,
                    )
                    log_countermeasure_plan(report)
                    forward_report_to_nwdaf(config, state, report)
                try:
                    capture_record = dataset_capture.capture_packet(
                        timestamp=packet_timestamp,
                        peer=f"{peer[0]}:{peer[1]}",
                        teid=gtpu_packet.teid,
                        raw_gtpu_packet=packet,
                        inner_packet=gtpu_packet.payload,
                        ue_ip=ue_ip,
                        ipv4_metadata=metadata.get("ipv4"),
                        report=report,
                        detector_features=result.features,
                    )
                    state.record_dataset_capture_packet(capture_record)
                except Exception as exc:  # pragma: no cover - defensive runtime logging
                    state.record_dataset_capture_error(str(exc))
                    LOGGER.exception("IDS dataset capture failed")
                state.record_packet(
                    teid=gtpu_packet.teid,
                    packet_size=len(gtpu_packet.payload),
                    score=result.score,
                    predicted_class=result.predicted_class,
                    report_id=report["reportId"],
                    ue_ip=ue_ip,
                )
                log_event(
                    "ids-packet-classified",
                    peer=f"{peer[0]}:{peer[1]}",
                    teid=gtpu_packet.teid,
                    ue_ip=ue_ip,
                    packet_size=len(gtpu_packet.payload),
                    score=round(result.score, 6),
                    predicted_class=result.predicted_class,
                    reason=result.reason,
                    report_id=report["reportId"],
                    action=report["action"],
                )
            except GtpuDecapsulationError as exc:
                state.record_decode_error()
                log_event("ids-packet-decode-error", error=str(exc))
            except Exception:  # pragma: no cover - defensive runtime logging
                state.record_decode_error()
                LOGGER.exception("unexpected IDS packet-processing failure")
    finally:
        sock.close()


def install_signal_handlers(stop_event: threading.Event) -> None:
    def _handle_signal(signum, _frame):
        LOGGER.info("received signal %s, shutting down IDS", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)


def run_traffic_influence_workflow(
    config: IdsConfig,
    state: RuntimeState,
    ready_event: threading.Event,
    stop_event: threading.Event,
) -> None:
    traffic = config.traffic_influence
    if not traffic.enabled or traffic.mode == "disabled":
        state.record_traffic_influence("disabled")
        log_event("ids-traffic-influence-disabled", mode=traffic.mode)
        return

    while not stop_event.is_set() and not ready_event.wait(1.0):
        pass
    if stop_event.is_set():
        return

    log_event(
        "ids-traffic-influence-request-started",
        mode=traffic.mode,
        pcf_base_uri=traffic.pcf_base_uri,
        dnn=traffic.dnn,
        supi=traffic.supi,
        duplication_policy_id=traffic.duplication_policy_id,
    )
    client = PcfTrafficInfluenceClient(config)
    refresh_interval_seconds = max(traffic.retry_interval_seconds, 30.0)
    registered = False
    while not stop_event.is_set():
        result = client.refresh_policy() if registered else client.request_policy()
        state.record_traffic_influence(
            status=result.status,
            error=result.error or None,
        )
        log_event(
            "ids-traffic-influence-request-completed",
            status=result.status,
            attempts=result.attempts,
            error=result.error,
        )
        if result.status == "accepted":
            registered = True
            stop_event.wait(refresh_interval_seconds)
            continue
        if result.status != "failed":
            return
        stop_event.wait(traffic.retry_interval_seconds)


def run_nwdaf_model_subscription_workflow(
    config: IdsConfig,
    state: RuntimeState,
    ready_event: threading.Event,
    stop_event: threading.Event,
) -> None:
    nwdaf = config.nwdaf_integration
    if not nwdaf.enabled or nwdaf.mode == "disabled":
        state.record_nwdaf_model_subscription("disabled")
        log_event("ids-nwdaf-model-subscription-disabled", mode=nwdaf.mode)
        return

    while not stop_event.is_set() and not ready_event.wait(1.0):
        pass
    if stop_event.is_set():
        return

    log_event(
        "ids-nwdaf-model-subscription-started",
        mode=nwdaf.mode,
        base_uri=nwdaf.base_uri,
        notification_uri=nwdaf.notification_uri,
        ml_event=nwdaf.ml_event,
        correlation_id=nwdaf.notif_correlation_id,
    )
    client = NwdafMlModelClient(config)
    result = client.subscribe_model_updates()
    state.record_nwdaf_model_subscription(
        status=result.status,
        error=result.error or None,
        subscription_id=result.subscription_id or None,
    )
    log_event(
        "ids-nwdaf-model-subscription-completed",
        status=result.status,
        attempts=result.attempts,
        subscription_id=result.subscription_id,
        error=result.error,
    )
    if result.status == "accepted":
        stop_event.wait()
        release_result = client.unsubscribe_model_updates(result.subscription_id)
        log_event(
            "ids-nwdaf-model-subscription-release-completed",
            status=release_result.status,
            attempts=release_result.attempts,
            subscription_id=release_result.subscription_id,
            error=release_result.error,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OAI IDS NF placeholder runtime")
    parser.add_argument(
        "--config",
        default=os.getenv("IDS_CONFIG_PATH", "/app/config/ids.yaml"),
        help="Path to the IDS YAML configuration file",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=os.getenv("IDS_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = parse_args()
    config = load_config(args.config)
    stop_event = threading.Event()
    ready_event = threading.Event()
    state = RuntimeState()
    reports = ReportStore(config.reports.storage, config.reports.file_path)
    subscriptions = SubscriptionStore()

    install_signal_handlers(stop_event)

    model_runtime = load_model_runtime(config)
    state.record_model_artifact(model_runtime.metadata.to_dict())
    dataset_capture = DatasetCaptureWriter(
        config.dataset_capture,
        ids_instance_id=config.instance_id,
        region=config.serving_area.region,
        tac=config.serving_area.tac,
        model_version=model_runtime.metadata.model_version,
    )
    if dataset_capture.enabled and dataset_capture.paths:
        state.record_dataset_capture_started(
            "enabled",
            str(dataset_capture.paths.dataset_dir),
        )
        log_event(
            "ids-dataset-capture-enabled",
            level=dataset_capture.config.level,
            scenario_id=dataset_capture.config.scenario_id,
            path=str(dataset_capture.paths.dataset_dir),
            region=config.serving_area.region,
        )
    else:
        state.record_dataset_capture_started("disabled")
        log_event("ids-dataset-capture-disabled")
    log_event(
        "ids-model-artifact-loaded",
        model_version=model_runtime.metadata.model_version,
        architecture=model_runtime.metadata.architecture,
        artifact_type=model_runtime.metadata.artifact_type,
        packet_size=model_runtime.metadata.packet_size,
        sequence_size=model_runtime.metadata.sequence_size,
        checksum=model_runtime.metadata.checksum,
        source_nf=model_runtime.metadata.source_nf,
        source_nf_instance_id=model_runtime.metadata.source_nf_instance_id,
        registry_status=model_runtime.registry_status,
    )

    handler = build_http_handler(config, state, ready_event, reports, subscriptions)
    http_server = ThreadingHTTPServer((config.http.host, config.http.port), handler)
    http_thread = threading.Thread(
        target=http_server.serve_forever,
        kwargs={"poll_interval": 0.5},
        name="ids-http",
        daemon=True,
    )
    http_thread.start()
    LOGGER.info("serving IDS HTTP endpoints on %s:%d", config.http.host, config.http.port)

    pod_ip = os.getenv("POD_IP") or discover_pod_ip(config.host)
    registration = NrfRegistration(
        base_uri=config.nrf.base_uri,
        nf_instance_id=config.nrf.nf_instance_id,
        nf_type=config.nrf.nf_type,
        nf_status=config.nrf.nf_status,
        service_name=config.nrf.service_name,
        service_version=config.nrf.service_version,
        heart_beat_timer=config.nrf.heart_beat_timer,
        host=config.host,
        pod_ip=pod_ip,
        http_port=config.http.port,
        serving_region=config.serving_area.region,
        serving_tac=config.serving_area.tac,
    )
    nrf_client = NrfClient(registration)

    packet_thread = threading.Thread(
        target=process_duplicated_packets,
        args=(config, state, stop_event, model_runtime, reports, dataset_capture),
        name="ids-gtpu",
        daemon=True,
    )
    packet_thread.start()

    registration_thread = threading.Thread(
        target=nrf_client.wait_until_registered,
        args=(ready_event, stop_event),
        name="ids-nrf",
        daemon=True,
    )
    registration_thread.start()

    traffic_influence_thread = threading.Thread(
        target=run_traffic_influence_workflow,
        args=(config, state, ready_event, stop_event),
        name="ids-traffic-influence",
        daemon=True,
    )
    traffic_influence_thread.start()

    nwdaf_model_thread = threading.Thread(
        target=run_nwdaf_model_subscription_workflow,
        args=(config, state, ready_event, stop_event),
        name="ids-nwdaf-model-subscription",
        daemon=True,
    )
    nwdaf_model_thread.start()

    try:
        while not stop_event.wait(1.0):
            pass
    finally:
        ready_event.clear()
        stop_event.set()
        http_server.shutdown()
        http_server.server_close()
        registration_thread.join(timeout=5.0)
        traffic_influence_thread.join(timeout=5.0)
        nwdaf_model_thread.join(timeout=5.0)
        packet_thread.join(timeout=5.0)
        dataset_capture.close()
        release_result = PcfTrafficInfluenceClient(config).release_policy()
        log_event(
            "ids-traffic-influence-release-completed",
            status=release_result.status,
            attempts=release_result.attempts,
            error=release_result.error,
        )
        nrf_client.deregister()
        http_thread.join(timeout=5.0)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
