#!/usr/bin/env python3
"""Validate Round 3 sample totals, canonical metrics, and Figure 4 traces."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import pickle
from collections import Counter
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/round3-matplotlib")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, recall_score


RESEARCH = Path(__file__).resolve().parents[2]
WORKSPACE = RESEARCH.parent
ROUND3 = RESEARCH / "rebuttal_round_3"
CSV_PATH = (
    RESEARCH
    / "datasets/federated_datasets_noslowite_nosqlmap/eval/Combined_eval_dataset.csv"
)
EVAL_RESULT = RESEARCH / "result0307/FL/eval_results_FL_Transformer.pkl"
FL_RESULT_DIR = RESEARCH / "result0307/FL"
RESULT_PATH = ROUND3 / "results/round3_evidence_audit.json"
FIGURE_PATH = ROUND3 / "output/FL_f1_score_over_completed_rounds.png"
LOG_PATH = ROUND3 / "logs/round3_evidence_audit.log"

ARCHITECTURES = ["Transformer", "LSTM", "GRU", "MLP", "CNN", "RNN"]
SEQUENCE_LENGTH = 256


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv_counts() -> tuple[int, Counter[int]]:
    counts: Counter[int] = Counter()
    rows = 0
    with CSV_PATH.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            rows += 1
            counts[int(row["label"])] += 1
    return rows, counts


def load_pickle(path: Path):
    with path.open("rb") as stream:
        return pickle.load(stream)


def as_float_list(values) -> list[float]:
    return [float(value) for value in values]


def main() -> int:
    raw_rows, raw_class_counts = read_csv_counts()
    complete_sequences, remainder = divmod(raw_rows, SEQUENCE_LENGTH)
    evaluated_packets = complete_sequences * SEQUENCE_LENGTH

    stored = load_pickle(EVAL_RESULT)[0]
    labels = [int(value) for value in stored["labels"]]
    predictions = [int(value) for value in stored["predictions"]]
    if len(labels) != len(predictions):
        raise RuntimeError("Canonical label and prediction lengths differ")
    if len(labels) != evaluated_packets:
        raise RuntimeError("Canonical result length does not match complete sequences")

    six_class_cm = confusion_matrix(labels, predictions, labels=list(range(6)))
    binary_labels = [0 if value == 0 else 1 for value in labels]
    binary_predictions = [0 if value == 0 else 1 for value in predictions]
    tn, fp, fn, tp = confusion_matrix(
        binary_labels, binary_predictions, labels=[0, 1]
    ).ravel()

    traces = {}
    for architecture in ARCHITECTURES:
        path = FL_RESULT_DIR / f"round_metrics_FL_{architecture}.pkl"
        metrics = load_pickle(path)
        f1_values = as_float_list(metrics["global_f1_weighted"])
        accuracy_values = as_float_list(metrics["global_accuracy"])
        macro_f1_values = as_float_list(metrics["global_f1_macro"])
        traces[architecture] = {
            "source": str(path.relative_to(WORKSPACE)),
            "sha256": sha256(path),
            "completed_rounds": len(f1_values),
            "weighted_f1_first_five": f1_values[:5],
            "weighted_f1_final": f1_values[-1],
            "accuracy_first_five_percent": accuracy_values[:5],
            "accuracy_final_percent": accuracy_values[-1],
            "macro_f1_first_five": macro_f1_values[:5],
            "macro_f1_final": macro_f1_values[-1],
        }

    report = {
        "inputs": {
            "evaluation_csv": {
                "path": str(CSV_PATH.relative_to(WORKSPACE)),
                "sha256": sha256(CSV_PATH),
            },
            "transformer_fedavg_evaluation_result": {
                "path": str(EVAL_RESULT.relative_to(WORKSPACE)),
                "sha256": sha256(EVAL_RESULT),
            },
        },
        "sample_reconciliation": {
            "raw_csv_packet_rows": raw_rows,
            "raw_csv_class_counts": dict(sorted(raw_class_counts.items())),
            "sequence_length_packets": SEQUENCE_LENGTH,
            "complete_sequences": complete_sequences,
            "evaluated_packets": evaluated_packets,
            "trailing_packets_excluded": remainder,
            "evaluated_class_counts": dict(sorted(Counter(labels).items())),
        },
        "recomputed_transformer_fedavg_metrics": {
            "labels": len(labels),
            "predictions": len(predictions),
            "correct": sum(a == b for a, b in zip(labels, predictions)),
            "errors": sum(a != b for a, b in zip(labels, predictions)),
            "accuracy_percent": 100.0 * accuracy_score(labels, predictions),
            "weighted_f1_percent": 100.0
            * f1_score(labels, predictions, average="weighted", zero_division=0),
            "macro_f1_percent": 100.0
            * f1_score(labels, predictions, average="macro", zero_division=0),
            "per_class_recall_percent": [
                100.0 * value
                for value in recall_score(
                    labels, predictions, average=None, labels=list(range(6)), zero_division=0
                )
            ],
            "six_class_confusion_matrix": six_class_cm.tolist(),
            "binary_attack_vs_normal": {
                "tp": int(tp),
                "fn": int(fn),
                "fp": int(fp),
                "tn": int(tn),
                "attack_recall_percent": 100.0 * tp / (tp + fn),
                "false_positive_rate_percent": 100.0 * fp / (fp + tn),
            },
            "stored_accuracy_percent": float(stored["accuracy"]),
            "stored_weighted_f1_percent": 100.0
            * float(stored["f1_score"]["weighted"]),
        },
        "figure4": {
            "interpretation": (
                "Each stored point is measured after local client training (up to 50 "
                "epochs with early stopping), aggregation, and global validation. The "
                "canonical archive contains no untrained round-0 point."
            ),
            "traces": traces,
        },
    }

    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    plt.figure(figsize=(10, 6))
    for architecture in ARCHITECTURES:
        trace = load_pickle(
            FL_RESULT_DIR / f"round_metrics_FL_{architecture}.pkl"
        )["global_f1_weighted"]
        rounds = range(1, len(trace) + 1)
        plt.plot(rounds, trace, label=architecture, marker="o", markersize=4)
    plt.xlabel("Completed federated round")
    plt.ylabel("Validation weighted F1-score")
    plt.xlim(left=0.5)
    plt.ylim(bottom=0.0, top=1.05)
    plt.xticks([1, 2, 5, 10, 20, 30, 40, 50])
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    FIGURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(FIGURE_PATH, dpi=160)
    plt.close()

    log_lines = [
        "Round 3 evidence audit: PASS",
        f"Raw CSV rows: {raw_rows}",
        f"Complete sequences: {complete_sequences} x {SEQUENCE_LENGTH}",
        f"Evaluated packets: {evaluated_packets}",
        f"Trailing packets excluded: {remainder}",
        f"Canonical correct/errors: {report['recomputed_transformer_fedavg_metrics']['correct']}/"
        f"{report['recomputed_transformer_fedavg_metrics']['errors']}",
        f"Recomputed accuracy: {report['recomputed_transformer_fedavg_metrics']['accuracy_percent']:.12f}%",
        f"Recomputed weighted F1: {report['recomputed_transformer_fedavg_metrics']['weighted_f1_percent']:.12f}%",
        f"Figure written: {FIGURE_PATH.relative_to(WORKSPACE)}",
        f"Report written: {RESULT_PATH.relative_to(WORKSPACE)}",
    ]
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    print("\n".join(log_lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
