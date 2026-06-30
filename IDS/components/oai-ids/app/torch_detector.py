"""PyTorch detector for the IDS NF.

Loads a state-dict produced by the NWDAF MTLF training entrypoint
(``mtlf_train.py``) and classifies live GTP-U packets with the same raw-packet
sequence model used in the research/thesis pipeline. The model architecture is
copied verbatim from ``IDS_lib.TransformerClassifier`` so the saved state-dict
keys match exactly.

The research model is a per-packet sequence classifier ([B, T, 1500] -> [B, T, C]).
The IDS sees one packet at a time, so we keep a rolling buffer of the last T
packet vectors and emit the prediction for the most recent packet.
"""

from __future__ import annotations

import collections

import torch
import torch.nn as nn

from .model import ClassificationResult, PacketFeatures, _feature_report


class TransformerClassifier(nn.Module):
    """Verbatim copy of IDS_lib.TransformerClassifier (state-dict compatible)."""

    def __init__(self, input_features, hidden_dim=256, nhead=8, num_layers=2, output_dim=6):
        super().__init__()
        self.input_embedding = nn.Sequential(
            nn.Linear(input_features, 512),
            nn.ReLU(),
            nn.Linear(512, hidden_dim),
            nn.ReLU(),
        )
        encoder_layers = nn.TransformerEncoderLayer(
            d_model=hidden_dim, nhead=nhead, dim_feedforward=hidden_dim * 4, batch_first=True
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layers, num_layers=num_layers)
        self.output_layer = nn.Linear(hidden_dim, output_dim)

    def forward(self, x):
        if len(x.shape) == 2:
            x = x.unsqueeze(0)
        x = self.input_embedding(x)
        x = self.transformer_encoder(x)
        return self.output_layer(x)


ARCHITECTURES = {"Transformer": TransformerClassifier}


class TorchDetector:
    """Runtime detector wrapping a loaded torch sequence model.

    Duck-typed with the placeholder detector: exposes ``.mode`` and a
    ``.classify(packet_vector)`` method that ``model.classify_packet`` dispatches to.
    """

    is_torch = True

    def __init__(self, model, packet_mtu, seq_len, class_names, device, mode="pytorch"):
        self.model = model
        self.packet_mtu = packet_mtu
        self.seq_len = max(1, int(seq_len))
        self.class_names = class_names
        self.device = device
        self.mode = mode
        self._buffer: collections.deque = collections.deque(maxlen=self.seq_len)

    @torch.no_grad()
    def classify(self, packet_vector: PacketFeatures) -> ClassificationResult:
        vec = torch.tensor(packet_vector.values, dtype=torch.float32, device=self.device)
        self._buffer.append(vec)
        seq = torch.stack(list(self._buffer)).unsqueeze(0)  # [1, L, packet_mtu]
        logits = self.model(seq)  # [1, L, C]
        probs = torch.softmax(logits[0, -1], dim=-1)  # latest packet
        idx = int(torch.argmax(probs).item())
        score = float(probs[idx].item())
        class_name = self.class_names[idx] if idx < len(self.class_names) else str(idx)
        features = _feature_report(packet_vector)
        features["modelClassIndex"] = idx
        features["modelClassName"] = class_name
        return ClassificationResult(
            predicted_class="benign" if idx == 0 else "malicious",
            predicted_index=idx,
            score=round(score, 6),
            reason=f"torch:{class_name}",
            features=features,
        )


def build_torch_detector(
    state_dict_path: str,
    packet_mtu: int,
    architecture: str,
    seq_len: int,
    label_map: dict[int, str],
    device: str = "cpu",
    mode: str = "pytorch",
    num_classes: int = 6,
) -> TorchDetector:
    cls = ARCHITECTURES.get(architecture)
    if cls is None:
        raise ValueError(f"unsupported torch architecture {architecture!r}; have {sorted(ARCHITECTURES)}")
    dev = torch.device(device)
    model = cls(input_features=packet_mtu, output_dim=num_classes)
    try:
        state = torch.load(state_dict_path, map_location=dev, weights_only=True)
    except TypeError:  # older torch without weights_only
        state = torch.load(state_dict_path, map_location=dev)
    model.load_state_dict(state)
    model.to(dev).eval()
    class_names = [label_map.get(i, str(i)) for i in range(num_classes)]
    return TorchDetector(model, packet_mtu, seq_len, class_names, dev, mode)
