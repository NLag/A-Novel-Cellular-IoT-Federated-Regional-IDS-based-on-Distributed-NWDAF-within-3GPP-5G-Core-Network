from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CLASS_LABELS = ("benign", "malicious")


@dataclass(frozen=True)
class PacketFeatures:
    values: tuple[float, ...]
    original_size: int
    clipped_size: int
    high_byte_ratio: float
    zero_byte_ratio: float


@dataclass(frozen=True)
class ClassificationResult:
    predicted_class: str
    predicted_index: int
    score: float
    reason: str
    features: dict[str, Any]


@dataclass(frozen=True)
class PlaceholderDetector:
    packet_mtu: int
    mode: str
    seed: int
    malicious_packet_size_threshold: int
    high_byte_ratio_threshold: float


def torch_available() -> bool:
    """Compatibility shim for older tests; the Phase 1 detector is pure Python."""

    return False


def build_model(
    packet_mtu: int,
    seed: int,
    hidden_layers: list[int] | None = None,
    mode: str = "heuristic",
    malicious_packet_size_threshold: int = 512,
    high_byte_ratio_threshold: float = 0.60,
) -> PlaceholderDetector:
    del hidden_layers
    if packet_mtu <= 0:
        raise ValueError("packet_mtu must be positive")
    if malicious_packet_size_threshold <= 0:
        raise ValueError("malicious_packet_size_threshold must be positive")
    if high_byte_ratio_threshold <= 0 or high_byte_ratio_threshold > 1:
        raise ValueError("high_byte_ratio_threshold must be in range (0, 1]")

    return PlaceholderDetector(
        packet_mtu=packet_mtu,
        mode=mode,
        seed=seed,
        malicious_packet_size_threshold=malicious_packet_size_threshold,
        high_byte_ratio_threshold=high_byte_ratio_threshold,
    )


def vectorize_packet(packet: bytes, packet_mtu: int) -> PacketFeatures:
    if packet_mtu <= 0:
        raise ValueError("packet_mtu must be positive")

    clipped = packet[:packet_mtu]
    padding = packet_mtu - len(clipped)
    values = tuple(byte / 255.0 for byte in clipped) + tuple(0.0 for _ in range(padding))
    high_byte_count = sum(1 for byte in clipped if byte >= 0xC0)
    zero_byte_count = sum(1 for byte in clipped if byte == 0)
    clipped_size = len(clipped)
    return PacketFeatures(
        values=values,
        original_size=len(packet),
        clipped_size=clipped_size,
        high_byte_ratio=(high_byte_count / clipped_size) if clipped_size else 0.0,
        zero_byte_ratio=(zero_byte_count / clipped_size) if clipped_size else 0.0,
    )


def _bounded_score(value: float) -> float:
    return max(0.5, min(0.99, value))


def classify_packet(
    model: PlaceholderDetector,
    packet_vector: PacketFeatures,
) -> ClassificationResult:
    # PyTorch / sequence detectors are duck-typed and self-classify.
    if getattr(model, "is_torch", False):
        return model.classify(packet_vector)
    if model.mode == "force-benign":
        return ClassificationResult(
            predicted_class="benign",
            predicted_index=0,
            score=0.99,
            reason="forced-benign",
            features=_feature_report(packet_vector),
        )
    if model.mode == "force-malicious":
        return ClassificationResult(
            predicted_class="malicious",
            predicted_index=1,
            score=0.99,
            reason="forced-malicious",
            features=_feature_report(packet_vector),
        )

    size_ratio = packet_vector.original_size / model.malicious_packet_size_threshold
    byte_ratio = packet_vector.high_byte_ratio / model.high_byte_ratio_threshold
    max_ratio = max(size_ratio, byte_ratio)

    if packet_vector.original_size >= model.malicious_packet_size_threshold:
        return ClassificationResult(
            predicted_class="malicious",
            predicted_index=1,
            score=_bounded_score(0.5 + min(size_ratio, 1.0) * 0.49),
            reason="packet-size-threshold",
            features=_feature_report(packet_vector),
        )
    if packet_vector.high_byte_ratio >= model.high_byte_ratio_threshold:
        return ClassificationResult(
            predicted_class="malicious",
            predicted_index=1,
            score=_bounded_score(0.5 + min(byte_ratio, 1.0) * 0.49),
            reason="high-byte-ratio-threshold",
            features=_feature_report(packet_vector),
        )

    return ClassificationResult(
        predicted_class="benign",
        predicted_index=0,
        score=_bounded_score(0.99 - min(max_ratio, 1.0) * 0.49),
        reason="below-placeholder-thresholds",
        features=_feature_report(packet_vector),
    )


def _feature_report(packet_vector: PacketFeatures) -> dict[str, Any]:
    return {
        "packetSize": packet_vector.original_size,
        "clippedSize": packet_vector.clipped_size,
        "highByteRatio": round(packet_vector.high_byte_ratio, 6),
        "zeroByteRatio": round(packet_vector.zero_byte_ratio, 6),
    }
