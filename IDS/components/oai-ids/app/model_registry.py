from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from .config import IdsConfig
from .model import PlaceholderDetector, build_model


class ModelArtifactError(RuntimeError):
    """Raised when a model artifact cannot be used by the current IDS runtime."""


@dataclass(frozen=True)
class ModelArtifactMetadata:
    model_version: str
    architecture: str
    artifact_type: str
    label_map: dict[int, str]
    packet_size: int
    sequence_size: int
    checksum: str
    source_nf: str
    source_nf_instance_id: str
    source_uri: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "modelVersion": self.model_version,
            "architecture": self.architecture,
            "artifactType": self.artifact_type,
            "labelMap": {str(key): value for key, value in self.label_map.items()},
            "packetSize": self.packet_size,
            "sequenceSize": self.sequence_size,
            "checksum": self.checksum,
            "sourceNf": self.source_nf,
            "sourceNfInstanceId": self.source_nf_instance_id,
            "sourceUri": self.source_uri,
        }


@dataclass(frozen=True)
class ModelRuntime:
    detector: PlaceholderDetector
    metadata: ModelArtifactMetadata
    registry_status: str


class ModelRegistryClient:
    """Local placeholder registry client.

    This is the first stable boundary for Workstream 2.2. It supports local
    placeholder manifests now. NWDAF/DCCF/ADRF fetching and PyTorch model loading
    should be added behind this interface later.
    """

    def __init__(self, config: IdsConfig):
        self.config = config

    def load(self) -> ModelRuntime:
        metadata, artifact_payload, status = self._load_metadata()
        if metadata.artifact_type in ("pytorch-state-dict", "pytorch"):
            return self._load_torch(metadata, artifact_payload, status)
        if metadata.artifact_type != "placeholder":
            raise ModelArtifactError(
                f"artifact type {metadata.artifact_type!r} is not supported yet"
            )

        runtime = artifact_payload.get("runtime", {})
        detector = build_model(
            packet_mtu=metadata.packet_size,
            seed=int(runtime.get("seed", self.config.classifier.seed)),
            hidden_layers=self.config.classifier.hidden_layers,
            mode=str(runtime.get("mode", self.config.classifier.mode)),
            malicious_packet_size_threshold=int(
                runtime.get(
                    "maliciousPacketSizeThreshold",
                    self.config.classifier.malicious_packet_size_threshold,
                )
            ),
            high_byte_ratio_threshold=float(
                runtime.get(
                    "highByteRatioThreshold",
                    self.config.classifier.high_byte_ratio_threshold,
                )
            ),
        )
        return ModelRuntime(
            detector=detector,
            metadata=metadata,
            registry_status=status,
        )

    def _load_torch(self, metadata, artifact_payload, status) -> ModelRuntime:
        from .torch_detector import build_torch_detector

        registry = self.config.model_registry
        artifact_path = Path(registry.artifact_path)
        model_file = (
            artifact_payload.get("modelFile")
            or artifact_payload.get("artifactFileName")
            or "model.pt"
        )
        model_path = artifact_path.parent / model_file
        if not model_path.exists():
            raise ModelArtifactError(f"torch model file not found: {model_path}")

        expected = artifact_payload.get("modelChecksum") or registry.checksum
        if expected:
            actual = _sha256_file(model_path)
            if expected not in (actual, actual.split(":")[-1]):
                raise ModelArtifactError(
                    f"torch model checksum mismatch: expected {expected}, got {actual}"
                )

        runtime = artifact_payload.get("runtime", {})
        detector = build_torch_detector(
            state_dict_path=str(model_path),
            packet_mtu=metadata.packet_size,
            architecture=metadata.architecture,
            seq_len=metadata.sequence_size,
            label_map=metadata.label_map,
            device=str(runtime.get("device", "cpu")),
            mode=str(runtime.get("mode", "pytorch")),
            num_classes=max(len(metadata.label_map), 2),
        )
        return ModelRuntime(
            detector=detector,
            metadata=metadata,
            registry_status=f"{status}-torch",
        )

    def _load_metadata(self) -> tuple[ModelArtifactMetadata, dict[str, Any], str]:
        registry = self.config.model_registry
        if registry.artifact_path:
            artifact_path = Path(registry.artifact_path)
            payload = _read_json_artifact(artifact_path)
            checksum = _sha256_file(artifact_path)
            expected_checksum = registry.checksum or payload.get("expectedChecksum", "")
            if expected_checksum and expected_checksum != checksum:
                raise ModelArtifactError(
                    f"model artifact checksum mismatch: expected {expected_checksum}, got {checksum}"
                )
            return (
                _metadata_from_payload(
                    payload=payload,
                    config=self.config,
                    checksum=payload.get("checksum") or checksum,
                ),
                payload,
                "loaded-local-artifact",
            )

        payload = _default_placeholder_payload(self.config)
        return (
            _metadata_from_payload(
                payload=payload,
                config=self.config,
                checksum=self.config.model_registry.checksum,
            ),
            payload,
            "loaded-default-placeholder",
        )


def load_model_runtime(config: IdsConfig) -> ModelRuntime:
    return ModelRegistryClient(config).load()


def _default_placeholder_payload(config: IdsConfig) -> dict[str, Any]:
    registry = config.model_registry
    return {
        "modelVersion": registry.model_version,
        "architecture": registry.architecture,
        "artifactType": registry.artifact_type,
        "labelMap": registry.label_map,
        "packetSize": config.classifier.packet_mtu,
        "sequenceSize": registry.sequence_size,
        "checksum": registry.checksum,
        "source": {
            "nf": registry.source_nf,
            "nfInstanceId": registry.source_nf_instance_id,
            "uri": registry.source_uri,
        },
        "runtime": {
            "mode": config.classifier.mode,
            "seed": config.classifier.seed,
            "maliciousPacketSizeThreshold": config.classifier.malicious_packet_size_threshold,
            "highByteRatioThreshold": config.classifier.high_byte_ratio_threshold,
        },
    }


def _metadata_from_payload(
    payload: dict[str, Any],
    config: IdsConfig,
    checksum: str,
) -> ModelArtifactMetadata:
    registry = config.model_registry
    source = payload.get("source") or {}
    return ModelArtifactMetadata(
        model_version=str(payload.get("modelVersion", registry.model_version)),
        architecture=str(payload.get("architecture", registry.architecture)),
        artifact_type=str(payload.get("artifactType", registry.artifact_type)),
        label_map=_normalize_label_map(payload.get("labelMap", registry.label_map)),
        packet_size=int(payload.get("packetSize", config.classifier.packet_mtu)),
        sequence_size=int(payload.get("sequenceSize", registry.sequence_size)),
        checksum=checksum,
        source_nf=str(source.get("nf", registry.source_nf)),
        source_nf_instance_id=str(
            source.get("nfInstanceId", registry.source_nf_instance_id)
        ),
        source_uri=str(source.get("uri", registry.source_uri)),
    )


def _normalize_label_map(raw_label_map: dict[Any, Any]) -> dict[int, str]:
    return {int(key): str(value) for key, value in raw_label_map.items()}


def _read_json_artifact(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ModelArtifactError(f"model artifact not found: {path}")
    with path.open("r", encoding="utf-8") as stream:
        payload = json.load(stream)
    if not isinstance(payload, dict):
        raise ModelArtifactError("model artifact must be a JSON object")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"
