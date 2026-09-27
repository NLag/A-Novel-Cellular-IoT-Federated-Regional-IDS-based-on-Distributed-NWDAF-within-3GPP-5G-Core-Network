#!/usr/bin/env python3
"""Run the R2-4 independent-regional Transformer baseline.

This experiment uses the same prepared dataset as the reported centralized,
FedAvg, and FedDistill runs.  Each regional model can access its own private
dataset plus the shared public dataset through ``load_private_region_datasets``
but receives no parameters, logits, or other knowledge from another region.

The script deliberately does not set random seeds, matching the randomness
status already disclosed for the original runs.  It persists configuration,
per-region metrics, predictions, continuous probabilities, and model states so
the new baseline remains auditable without altering the historical scripts.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)

RESEARCH_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = RESEARCH_ROOT.parent
sys.path.insert(0, str(RESEARCH_ROOT))

from IDS_lib import (  # noqa: E402
    BATCH_SIZE,
    CLASS_NAME,
    DELTA_LOSS,
    LEARNING_RATE,
    NUM_CLASS,
    NUM_REGION,
    PACKET_LEN,
    SEQ_LEN,
    TransformerClassifier,
    load_private_region_datasets,
)
from DL_multiclass_regional_models import train_regional_models  # noqa: E402


DEFAULT_TRAIN_PATH = RESEARCH_ROOT / "datasets/federated_datasets_noslowite_nosqlmap/train"
DEFAULT_EVAL_PATH = RESEARCH_ROOT / "datasets/federated_datasets_noslowite_nosqlmap/eval"
DEFAULT_REPORT_DIR = (
    WORKSPACE_ROOT
    / "OAI_5G_STORAGE/IDS_RELATED_STORAGE/REPORT/r2-4-regional-baseline-20260827"
)
DEFAULT_MODEL_DIR = (
    WORKSPACE_ROOT
    / "OAI_5G_STORAGE/IDS_RELATED_STORAGE/MODEL/r2-4-regional-transformer-20260827"
)


def evaluate(model: torch.nn.Module, loaders, device: torch.device) -> tuple[dict, dict]:
    """Evaluate a model and return serializable metrics plus raw score arrays."""
    if not isinstance(loaders, (list, tuple)):
        loaders = [loaders]

    model.eval()
    labels_parts: list[np.ndarray] = []
    prediction_parts: list[np.ndarray] = []
    probability_parts: list[np.ndarray] = []

    with torch.no_grad():
        for loader in loaders:
            for inputs, labels in loader:
                inputs = inputs.to(device)
                outputs = model(inputs)
                probabilities = torch.softmax(outputs, dim=2)
                predictions = torch.argmax(probabilities, dim=2)
                labels_parts.append(labels.detach().cpu().reshape(-1).numpy())
                prediction_parts.append(predictions.detach().cpu().reshape(-1).numpy())
                probability_parts.append(
                    probabilities.detach().cpu().reshape(-1, NUM_CLASS).numpy().astype(np.float32)
                )

    labels = np.concatenate(labels_parts)
    predictions = np.concatenate(prediction_parts)
    probabilities = np.concatenate(probability_parts)

    precision, recall, f1, support = precision_recall_fscore_support(
        labels,
        predictions,
        labels=np.arange(NUM_CLASS),
        zero_division=0,
    )
    weighted = precision_recall_fscore_support(
        labels, predictions, average="weighted", zero_division=0
    )
    macro = precision_recall_fscore_support(
        labels, predictions, average="macro", zero_division=0
    )

    metrics = {
        "samples": int(labels.size),
        "accuracy_percent": float(100.0 * accuracy_score(labels, predictions)),
        "precision_weighted_percent": float(100.0 * weighted[0]),
        "recall_weighted_percent": float(100.0 * weighted[1]),
        "f1_weighted_percent": float(100.0 * weighted[2]),
        "precision_macro_percent": float(100.0 * macro[0]),
        "recall_macro_percent": float(100.0 * macro[1]),
        "f1_macro_percent": float(100.0 * macro[2]),
        "per_class": {
            CLASS_NAME[i]: {
                "precision_percent": float(100.0 * precision[i]),
                "recall_percent": float(100.0 * recall[i]),
                "f1_percent": float(100.0 * f1[i]),
                "support": int(support[i]),
            }
            for i in range(NUM_CLASS)
        },
        "confusion_matrix": confusion_matrix(
            labels, predictions, labels=np.arange(NUM_CLASS)
        ).tolist(),
    }
    arrays = {
        "labels": labels.astype(np.int16),
        "predictions": predictions.astype(np.int16),
        "probabilities": probabilities,
    }
    return metrics, arrays


def summarize(per_region: list[dict], evaluation_name: str) -> dict:
    keys = [
        "accuracy_percent",
        "precision_weighted_percent",
        "recall_weighted_percent",
        "f1_weighted_percent",
        "precision_macro_percent",
        "recall_macro_percent",
        "f1_macro_percent",
    ]
    summary: dict[str, object] = {
        "aggregation": "unweighted mean and population standard deviation across five regional models",
        "evaluation": evaluation_name,
        "regions": len(per_region),
    }
    for key in keys:
        values = np.asarray([entry[evaluation_name][key] for entry in per_region], dtype=float)
        summary[key] = {
            "mean": float(values.mean()),
            "std_across_regions": float(values.std(ddof=0)),
            "min": float(values.min()),
            "max": float(values.max()),
        }

    summary["per_class_f1_percent"] = {}
    summary["per_class_recall_percent"] = {}
    for class_name in CLASS_NAME:
        f1_values = np.asarray(
            [entry[evaluation_name]["per_class"][class_name]["f1_percent"] for entry in per_region]
        )
        recall_values = np.asarray(
            [entry[evaluation_name]["per_class"][class_name]["recall_percent"] for entry in per_region]
        )
        summary["per_class_f1_percent"][class_name] = {
            "mean": float(f1_values.mean()),
            "std_across_regions": float(f1_values.std(ddof=0)),
        }
        summary["per_class_recall_percent"][class_name] = {
            "mean": float(recall_values.mean()),
            "std_across_regions": float(recall_values.std(ddof=0)),
        }
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-path", type=Path, default=DEFAULT_TRAIN_PATH)
    parser.add_argument("--eval-path", type=Path, default=DEFAULT_EVAL_PATH)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--min-delta", type=float, default=DELTA_LOSS)
    parser.add_argument(
        "--regions",
        type=int,
        default=NUM_REGION,
        help="Number of regions to run; use 1 only for a smoke/timing check.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.report_dir.mkdir(parents=True, exist_ok=True)
    args.model_dir.mkdir(parents=True, exist_ok=True)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    config = {
        "purpose": "R2-4 independent regional baseline without aggregation",
        "architecture": "Transformer",
        "device": str(device),
        "train_path": str(args.train_path.resolve()),
        "eval_path": str(args.eval_path.resolve()),
        "regions_requested": args.regions,
        "public_data_access": "shared public dataset merged with each regional private dataset",
        "cross_region_exchange": "none",
        "split_procedure": "80:20 development:test, then 80:20 train:validation within development",
        "effective_split_percent": {"train": 64, "validation": 16, "test": 20},
        "random_seeds_fixed": False,
        "batch_size": BATCH_SIZE,
        "sequence_packets": SEQ_LEN,
        "packet_bytes": PACKET_LEN,
        "learning_rate": LEARNING_RATE,
        "max_epochs": args.epochs,
        "local_early_stopping": {"validation_loss_min_delta": args.min_delta, "patience": args.patience},
    }
    with (args.report_dir / "run_config.json").open("w") as handle:
        json.dump(config, handle, indent=2)

    print(f"[r2-4] device={device}")
    print(f"[r2-4] train={args.train_path}")
    print(f"[r2-4] eval={args.eval_path}")
    print(f"[r2-4] report={args.report_dir}")

    load_started = time.perf_counter()
    train_loaders, validation_loaders, test_loaders, eval_loader = load_private_region_datasets(
        str(args.train_path), str(args.eval_path), quiet=True
    )
    load_seconds = time.perf_counter() - load_started
    print(f"[r2-4] datasets loaded in {load_seconds:.2f}s")

    region_count = min(args.regions, len(train_loaders))
    per_region: list[dict] = []
    experiment_started = time.perf_counter()

    for region_index in range(region_count):
        region_number = region_index + 1
        print(f"[r2-4] training region {region_number}/{region_count}", flush=True)
        model = TransformerClassifier(input_features=PACKET_LEN).to(device)
        train_started = time.perf_counter()
        best_validation_loss = train_regional_models(
            [model],
            [train_loaders[region_index]],
            [validation_loaders[region_index]],
            [test_loaders[region_index]],
            epochs=args.epochs,
            patience=args.patience,
            min_delta=args.min_delta,
            quiet=False,
            debug=False,
        )[0]
        train_seconds = time.perf_counter() - train_started

        own_test, own_test_arrays = evaluate(model, test_loaders[region_index], device)
        combined_test, combined_test_arrays = evaluate(model, test_loaders, device)
        external_eval, external_eval_arrays = evaluate(model, eval_loader, device)

        region_metrics = {
            "region": region_number,
            "best_validation_loss": float(best_validation_loss),
            "training_seconds": float(train_seconds),
            "own_region_test": own_test,
            "combined_regional_test": combined_test,
            "external_evaluation": external_eval,
        }
        per_region.append(region_metrics)

        torch.save(model.state_dict(), args.model_dir / f"region-{region_number}-transformer.pt")
        with (args.report_dir / f"region-{region_number}-metrics.json").open("w") as handle:
            json.dump(region_metrics, handle, indent=2)
        for evaluation_name, arrays in (
            ("own-region-test", own_test_arrays),
            ("combined-regional-test", combined_test_arrays),
            ("external-evaluation", external_eval_arrays),
        ):
            np.savez_compressed(
                args.report_dir / f"region-{region_number}-{evaluation_name}.npz", **arrays
            )

        print(
            f"[r2-4] region={region_number} train={train_seconds:.2f}s "
            f"own_test_acc={own_test['accuracy_percent']:.4f}% "
            f"combined_test_acc={combined_test['accuracy_percent']:.4f}% "
            f"eval_acc={external_eval['accuracy_percent']:.4f}% "
            f"eval_macro_f1={external_eval['f1_macro_percent']:.4f}%",
            flush=True,
        )

    result = {
        "config": config,
        "dataset_load_seconds": float(load_seconds),
        "experiment_seconds": float(time.perf_counter() - experiment_started),
        "per_region": per_region,
        "summaries": {
            "own_region_test": summarize(per_region, "own_region_test"),
            "combined_regional_test": summarize(per_region, "combined_regional_test"),
            "external_evaluation": summarize(per_region, "external_evaluation"),
        },
    }
    with (args.report_dir / "summary.json").open("w") as handle:
        json.dump(result, handle, indent=2)
    with (args.report_dir / "summary.pkl").open("wb") as handle:
        pickle.dump(result, handle)

    eval_summary = result["summaries"]["external_evaluation"]
    print(
        "[r2-4] DONE external evaluation mean: "
        f"accuracy={eval_summary['accuracy_percent']['mean']:.4f}% "
        f"weighted_f1={eval_summary['f1_weighted_percent']['mean']:.4f}% "
        f"macro_f1={eval_summary['f1_macro_percent']['mean']:.4f}%",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
