from __future__ import annotations

from dataclasses import dataclass, field
import csv
import hashlib
import json
from pathlib import Path
import threading
import time
from typing import Any


CAPTURE_LEVEL_REPORT_ONLY = "report-only"
CAPTURE_LEVEL_PACKET_CAPTURE = "packet-capture"
CAPTURE_LEVEL_MODEL_READY = "model-ready"

MODEL_READY_FIELDNAMES = [
    "scenario_id",
    "region",
    "tac",
    "ids_instance_id",
    "timestamp",
    "sequence_id",
    "sequence_index",
    "packet_index",
    "ue_ip",
    "teid",
    "traffic_class",
    "attack_label",
    "attack_variant",
    "label",
    "numeric_label",
    "predicted_class",
    "predicted_label",
    "predicted_score",
    "detector_name",
    "detector_reason",
    "split",
    "packet_hex",
]


@dataclass
class DatasetCaptureConfig:
    enabled: bool = False
    level: str = CAPTURE_LEVEL_REPORT_ONLY
    storage_root: str = "/oai-5g-storage"
    relative_path: str = "IDS_RELATED_STORAGE/DATASETS"
    scenario_id: str = "manual"
    traffic_class: str = "unknown"
    attack_label: str = "unknown"
    attack_variant: str = ""
    generator: str = ""
    generator_metadata: dict[str, Any] = field(default_factory=dict)
    include_raw_gtpu: bool = False
    include_inner_packet: bool = False
    sequence_size: int = 200
    split: str = "unspecified"
    numeric_label: int = -1
    flush_every: int = 1


@dataclass(frozen=True)
class CapturePaths:
    dataset_dir: Path
    events_path: Path
    model_ready_path: Path | None
    manifest_path: Path


class DatasetCaptureWriter:
    def __init__(
        self,
        config: DatasetCaptureConfig,
        ids_instance_id: str,
        region: str,
        tac: str,
        model_version: str,
    ) -> None:
        self.config = normalize_capture_config(config)
        self.ids_instance_id = ids_instance_id
        self.region = region
        self.tac = tac
        self.model_version = model_version
        self._lock = threading.Lock()
        self._packet_index = 0
        self._events_stream = None
        self._csv_stream = None
        self._csv_writer = None
        self.paths: CapturePaths | None = None

        if self.config.enabled:
            self.paths = build_capture_paths(
                self.config,
                ids_instance_id=ids_instance_id,
                region=region,
            )
            self.paths.dataset_dir.mkdir(parents=True, exist_ok=True)
            self._events_stream = self.paths.events_path.open("a", encoding="utf-8")
            if self.config.level == CAPTURE_LEVEL_MODEL_READY and self.paths.model_ready_path:
                csv_exists = ensure_model_ready_csv_schema(
                    self.paths.model_ready_path, MODEL_READY_FIELDNAMES
                )
                self._csv_stream = self.paths.model_ready_path.open(
                    "a", encoding="utf-8", newline=""
                )
                self._csv_writer = csv.DictWriter(
                    self._csv_stream,
                    fieldnames=MODEL_READY_FIELDNAMES,
                )
                if not csv_exists:
                    self._csv_writer.writeheader()
            self.write_manifest()

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def close(self) -> None:
        with self._lock:
            if self._events_stream:
                self._events_stream.flush()
                self._events_stream.close()
                self._events_stream = None
            if self._csv_stream:
                self._csv_stream.flush()
                self._csv_stream.close()
                self._csv_stream = None

    def write_manifest(self) -> None:
        if not self.enabled or not self.paths:
            return
        manifest = {
            "schemaVersion": "ids-dataset-capture-v1",
            "createdAt": time.time(),
            "idsInstanceId": self.ids_instance_id,
            "region": self.region,
            "tac": self.tac,
            "modelVersion": self.model_version,
            "scenarioId": self.config.scenario_id,
            "level": self.config.level,
            "trafficClass": self.config.traffic_class,
            "attackLabel": self.config.attack_label,
            "attackVariant": self.config.attack_variant,
            "generator": self.config.generator,
            "generatorMetadata": self.config.generator_metadata,
            "sequenceSize": self.config.sequence_size,
            "split": self.config.split,
            "numericLabel": self.config.numeric_label,
            "files": {
                "events": str(self.paths.events_path),
                "modelReady": str(self.paths.model_ready_path)
                if self.paths.model_ready_path
                else "",
            },
        }
        self.paths.manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def capture_packet(
        self,
        *,
        timestamp: float,
        peer: str,
        teid: int,
        raw_gtpu_packet: bytes,
        inner_packet: bytes,
        ue_ip: str | None,
        ipv4_metadata: dict[str, Any] | None,
        report: dict[str, Any],
        detector_features: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not self.enabled or not self._events_stream:
            return None
        with self._lock:
            packet_index = self._packet_index
            self._packet_index += 1
            sequence_size = max(1, self.config.sequence_size)
            sequence_id = packet_index // sequence_size
            sequence_index = packet_index % sequence_size
            predicted_class = str(report.get("predictedClass") or "")
            predicted_score = report.get("score")
            detector = report.get("detector", {}) or {}
            record = {
                "schemaVersion": "ids-dataset-capture-v1",
                "timestamp": timestamp,
                "captureTime": time.time(),
                "scenarioId": self.config.scenario_id,
                "idsInstanceId": self.ids_instance_id,
                "region": self.region,
                "tac": self.tac,
                "modelVersion": self.model_version,
                "packetIndex": packet_index,
                "sequenceId": sequence_id,
                "sequenceIndex": sequence_index,
                "sequenceSize": sequence_size,
                "split": self.config.split,
                "trafficClass": self.config.traffic_class,
                "attackLabel": self.config.attack_label,
                "attackVariant": self.config.attack_variant,
                "numericLabel": self.config.numeric_label,
                "generator": self.config.generator,
                "generatorMetadata": self.config.generator_metadata,
                "peer": peer,
                "teid": teid,
                "ueIp": ue_ip,
                "packetSize": len(inner_packet),
                "rawGtpuSize": len(raw_gtpu_packet),
                "rawGtpuSha256": hashlib.sha256(raw_gtpu_packet).hexdigest(),
                "innerPacketSha256": hashlib.sha256(inner_packet).hexdigest(),
                "ipv4": ipv4_metadata or {},
                "reportId": report.get("reportId"),
                "predictedClass": predicted_class,
                "predictedLabel": predicted_label(predicted_class),
                "score": predicted_score,
                "detector": detector,
                "features": detector_features,
            }
            if should_include_raw_gtpu(self.config):
                record["rawGtpuHex"] = raw_gtpu_packet.hex()
            if should_include_inner_packet(self.config):
                record["packetHex"] = inner_packet.hex()

            self._events_stream.write(json.dumps(record, sort_keys=True) + "\n")
            if self.config.flush_every <= 1 or packet_index % self.config.flush_every == 0:
                self._events_stream.flush()

            if self._csv_writer:
                self._csv_writer.writerow(
                    {
                        "scenario_id": self.config.scenario_id,
                        "region": self.region,
                        "tac": self.tac,
                        "ids_instance_id": self.ids_instance_id,
                        "timestamp": timestamp,
                        "sequence_id": sequence_id,
                        "sequence_index": sequence_index,
                        "packet_index": packet_index,
                        "ue_ip": ue_ip or "",
                        "teid": teid,
                        "traffic_class": self.config.traffic_class,
                        "attack_label": self.config.attack_label,
                        "attack_variant": self.config.attack_variant,
                        "label": self.config.numeric_label,
                        "numeric_label": self.config.numeric_label,
                        "predicted_class": predicted_class,
                        "predicted_label": predicted_label(predicted_class),
                        "predicted_score": predicted_score if predicted_score is not None else "",
                        "detector_name": detector.get("name", ""),
                        "detector_reason": detector.get("reason", ""),
                        "split": self.config.split,
                        "packet_hex": inner_packet.hex(),
                    }
                )
                if self.config.flush_every <= 1 or packet_index % self.config.flush_every == 0:
                    self._csv_stream.flush()
            return {
                "packetIndex": packet_index,
                "sequenceId": sequence_id,
                "sequenceIndex": sequence_index,
                "eventsPath": str(self.paths.events_path) if self.paths else "",
            }


def normalize_capture_config(config: DatasetCaptureConfig) -> DatasetCaptureConfig:
    level = (config.level or CAPTURE_LEVEL_REPORT_ONLY).strip().lower()
    if level not in {
        CAPTURE_LEVEL_REPORT_ONLY,
        CAPTURE_LEVEL_PACKET_CAPTURE,
        CAPTURE_LEVEL_MODEL_READY,
    }:
        raise ValueError(f"unsupported dataset capture level: {config.level}")
    config.level = level
    if config.sequence_size <= 0:
        config.sequence_size = 1
    if config.flush_every <= 0:
        config.flush_every = 1
    return config


def build_capture_paths(
    config: DatasetCaptureConfig,
    *,
    ids_instance_id: str,
    region: str,
) -> CapturePaths:
    safe_scenario = safe_path_part(config.scenario_id)
    safe_region = safe_path_part(region)
    safe_instance = safe_path_part(ids_instance_id)
    dataset_dir = (
        Path(config.storage_root)
        / config.relative_path
        / safe_scenario
        / safe_region
        / safe_instance
    )
    events_path = dataset_dir / "packets.jsonl"
    model_ready_path = (
        dataset_dir / "model_ready.csv"
        if config.level == CAPTURE_LEVEL_MODEL_READY
        else None
    )
    return CapturePaths(
        dataset_dir=dataset_dir,
        events_path=events_path,
        model_ready_path=model_ready_path,
        manifest_path=dataset_dir / "manifest.json",
    )


def ensure_model_ready_csv_schema(path: Path, fieldnames: list[str]) -> bool:
    if not path.exists():
        return False
    with path.open("r", encoding="utf-8", newline="") as stream:
        first_line = stream.readline()
        if not first_line:
            return False
        existing_fieldnames = next(csv.reader([first_line]))
        if existing_fieldnames == fieldnames:
            return True
        stream.seek(0)
        rows = list(csv.DictReader(stream))

    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    tmp_path.replace(path)
    return True


def safe_path_part(value: str) -> str:
    value = value or "unknown"
    return "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in value)


def should_include_raw_gtpu(config: DatasetCaptureConfig) -> bool:
    return config.include_raw_gtpu or config.level in {
        CAPTURE_LEVEL_PACKET_CAPTURE,
    }


def should_include_inner_packet(config: DatasetCaptureConfig) -> bool:
    return config.include_inner_packet or config.level in {
        CAPTURE_LEVEL_PACKET_CAPTURE,
        CAPTURE_LEVEL_MODEL_READY,
    }


def predicted_label(predicted_class: str) -> int:
    normalized = (predicted_class or "").strip().lower()
    if normalized == "benign":
        return 0
    if normalized in {"malicious", "attack", "anomalous"}:
        return 1
    return -1
