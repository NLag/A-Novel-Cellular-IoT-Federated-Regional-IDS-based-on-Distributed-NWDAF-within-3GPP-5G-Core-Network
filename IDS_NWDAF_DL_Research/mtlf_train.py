#!/usr/bin/env python3
"""Parametrized NWDAF MTLF training entrypoint.

Runs ONE training scenario for ONE architecture and writes a single servable
PyTorch state-dict (``model.pt``) plus a metrics/manifest sidecar into
``--output-dir``. This is the artifact contract the OAI MTLF expects: its
``_on_model_ready`` callback searches the output dir for ``model.pt`` / ``*.pth``,
computes a checksum, builds the ``Nnwdaf_MLModelProvision`` manifest, and
notifies subscribed IDS NFs.

The four 3GPP-relevant procedures are wired here:
    centralized            -> one global model on the combined dataset
    regional               -> independent model for one region
    federated-averaging    -> FedAvg global model (reuses tested driver)
    federated-distillation -> FedDistill regional model (reuses tested driver)

It is invoked by ``training_manager.py`` as::

    python -Bu mtlf_train.py --output-dir <dir> --epochs <n>

with NWDAF_MTLF_SCENARIO / NWDAF_MTLF_MODEL_ARCHITECTURE in the environment, and
can also be run by hand for offline (A40) training that feeds shared storage.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys

import torch
import torch.nn.functional as F
from sklearn.metrics import accuracy_score, f1_score

# IDS_lib lives next to this file in the research workspace.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from IDS_lib import (  # noqa: E402
    NUM_CLASS,
    NUM_REGION,
    PACKET_LEN,
    SEQ_LEN,
    CLASS_NAME,
    MLPClassifier,
    CNNClassifier,
    RNNClassifier,
    LSTMClassifier,
    GRUClassifier,
    TransformerClassifier,
    load_centralized_dataset,
    load_private_region_datasets,
    load_public_and_private_datasets,
    training_model,
)

# Canonical scenario keys (match nwdaf_mtlf_model_training/scenarios.py).
SCENARIO_ALIASES = {
    "centralized": "centralized",
    "regional": "regional",
    "federated-averaging": "fedavg",
    "fedavg": "fedavg",
    "federated-distillation": "feddistill",
    "feddistill": "feddistill",
}

DEFAULT_TRAIN_PATHS = {
    "centralized": "./datasets/federated_datasets_noslowite_nosqlmap/train/",
    "regional": "./datasets/federated_datasets_noslowite_nosqlmap/train/",
    "fedavg": "./datasets/federated_datasets_noslowite_nosqlmap/train/",
    "feddistill": "./datasets/federated_datasets_noslowite_nosqlmap/train/",
}
DEFAULT_EVAL_PATHS = {
    "centralized": "./datasets/federated_datasets_noslowite_nosqlmap/eval/",
    "regional": "./datasets/federated_datasets_noslowite_nosqlmap/eval/",
    "fedavg": "./datasets/federated_datasets_noslowite_nosqlmap/eval/",
    "feddistill": "./datasets/federated_datasets_noslowite_nosqlmap/eval/",
}


def build_model(arch: str, device: torch.device) -> torch.nn.Module:
    """Instantiate one architecture using the IDS_lib constructors."""
    arch = arch.strip()
    if arch == "MLP":
        model = MLPClassifier(input_features=PACKET_LEN, output_dim=NUM_CLASS)
    elif arch == "CNN":
        model = CNNClassifier(input_features=PACKET_LEN, output_dim=NUM_CLASS)
    elif arch == "RNN":
        model = RNNClassifier(input_features=PACKET_LEN, hidden_dim=256, output_dim=NUM_CLASS, num_layers=1)
    elif arch == "LSTM":
        model = LSTMClassifier(input_features=PACKET_LEN, hidden_dim=256, output_dim=NUM_CLASS, num_layers=1)
    elif arch == "GRU":
        model = GRUClassifier(input_features=PACKET_LEN, hidden_dim=256, output_dim=NUM_CLASS, num_layers=1)
    elif arch == "Transformer":
        model = TransformerClassifier(input_features=PACKET_LEN, hidden_dim=256, nhead=8, num_layers=2, output_dim=NUM_CLASS)
    else:
        raise ValueError(f"unknown architecture {arch!r}")
    return model.to(device)


def evaluate(model: torch.nn.Module, loaders, device: torch.device) -> dict:
    """Evaluate on one loader or a list of loaders; per-packet argmax (dim=2)."""
    if not isinstance(loaders, (list, tuple)):
        loaders = [loaders]
    model.eval()
    all_preds, all_labels = [], []
    with torch.no_grad():
        for loader in loaders:
            if loader is None:
                continue
            for inputs, labels in loader:
                inputs = inputs.to(device)
                outputs = model(inputs)
                predicted = torch.argmax(outputs.data, 2).cpu()
                all_preds.extend(predicted.view(-1).numpy())
                all_labels.extend(labels.cpu().view(-1).numpy())
    if not all_labels:
        return {}
    return {
        "accuracy": 100.0 * accuracy_score(all_labels, all_preds),
        "f1_weighted": 100.0 * f1_score(all_labels, all_preds, average="weighted"),
        "f1_macro": 100.0 * f1_score(all_labels, all_preds, average="macro"),
        "f1_per_class": [round(100.0 * v, 4) for v in f1_score(all_labels, all_preds, average=None)],
        "samples": len(all_labels),
    }


def run_centralized(arch, train_path, eval_path, epochs, device):
    train_loader, val_loader, test_loader, eval_loader = load_centralized_dataset(train_path, eval_path, quiet=True)
    model = build_model(arch, device)
    training_model(model, train_loader, val_loader, epochs=epochs, model_name=f"{arch}-centralized")
    return model, {"test": evaluate(model, test_loader, device), "eval": evaluate(model, eval_loader, device)}


def run_regional(arch, train_path, eval_path, epochs, region_idx, device):
    train_loaders, val_loaders, test_loaders, eval_loader = load_private_region_datasets(train_path, eval_path, quiet=True)
    k = region_idx
    model = build_model(arch, device)
    training_model(model, train_loaders[k], val_loaders[k], epochs=epochs, model_name=f"{arch}-region{k + 1}")
    return model, {"test": evaluate(model, test_loaders[k], device), "eval": evaluate(model, eval_loader, device)}


def run_fedavg(arch, train_path, eval_path, rounds, device):
    import DL_multiclass_federated as fa
    train_loaders, val_loaders, test_loaders, eval_loader = load_private_region_datasets(train_path, eval_path, quiet=True)
    models = [build_model(arch, device) for _ in range(NUM_REGION)]
    _metrics, averaged_model = fa.run_federated_learning(
        models, train_loaders, val_loaders, test_loaders, rounds=rounds, quiet=True, model_name=arch
    )
    averaged_model.to(device)
    return averaged_model, {
        "test": evaluate(averaged_model, test_loaders, device),
        "eval": evaluate(averaged_model, [eval_loader], device),
    }


def run_feddistill(arch, train_path, eval_path, rounds, region_idx, device):
    import DL_multiclass_Federated_Distillation as fd
    public_dataloaders, train_loaders, val_loaders, test_loaders, eval_loader = load_public_and_private_datasets(
        train_path, eval_path, quiet=True
    )
    # Reproduce the module-level public soft-label preparation (guarded under __main__ there).
    pub_train = public_dataloaders["train"]
    pub_val = public_dataloaders["validation"]
    public_soft = {"train": copy.deepcopy(pub_train), "validation": copy.deepcopy(pub_val)}
    public_true = {"train": pub_train, "validation": pub_val}
    public_true["train"].dataset.set_soft_labels(
        F.one_hot(public_true["train"].dataset.get_Y_tensor(), num_classes=NUM_CLASS).float()
    )
    public_true["validation"].dataset.set_soft_labels(
        F.one_hot(public_true["validation"].dataset.get_Y_tensor(), num_classes=NUM_CLASS).float()
    )
    # The driver reads `public_dataloaders_true_label` as a module global.
    fd.public_dataloaders_true_label = public_true

    models = [build_model(arch, device) for _ in range(NUM_REGION)]
    fd.run_federated_distillation(
        models, public_soft, train_loaders, val_loaders, test_loaders, rounds=rounds, quiet=True, model_name=arch
    )
    model = models[region_idx]  # the per-region model this MTLF instance serves
    return model, {
        "test": evaluate(model, test_loaders, device),
        "eval": evaluate(model, [eval_loader], device),
        "all_regions_eval": [evaluate(m, [eval_loader], device).get("accuracy") for m in models],
    }


def main(argv=None) -> int:
    env = os.environ
    p = argparse.ArgumentParser(description="NWDAF MTLF parametrized training entrypoint")
    p.add_argument("--scenario", default=env.get("NWDAF_MTLF_SCENARIO", "regional"))
    p.add_argument("--architecture", default=env.get("NWDAF_MTLF_MODEL_ARCHITECTURE") or "Transformer")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--epochs", type=int, default=50, help="local epochs (centralized/regional) ")
    p.add_argument("--rounds", type=int, default=None, help="federated rounds (default 50 fedavg / 100 feddistill)")
    p.add_argument("--region", type=int, default=int(env.get("NWDAF_MTLF_REGION", "1")), help="1-based region to export (regional/feddistill)")
    p.add_argument("--train-path", default=None)
    p.add_argument("--eval-path", default=None)
    p.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    p.add_argument("--quick", action="store_true", help="smoke mode: tiny epochs/rounds")
    args = p.parse_args(argv)

    scenario = SCENARIO_ALIASES.get(args.scenario)
    if scenario is None:
        p.error(f"unknown scenario {args.scenario!r}; valid: {sorted(set(SCENARIO_ALIASES))}")
    arch = args.architecture
    region_idx = max(0, min(NUM_REGION - 1, args.region - 1))

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)

    train_path = args.train_path or DEFAULT_TRAIN_PATHS[scenario]
    eval_path = args.eval_path or DEFAULT_EVAL_PATHS[scenario]
    epochs = 1 if args.quick else args.epochs
    if args.rounds is not None:
        rounds = args.rounds
    elif args.quick:
        rounds = 1
    else:
        rounds = 50 if scenario == "fedavg" else 100

    os.makedirs(args.output_dir, exist_ok=True)
    print(f"[mtlf_train] scenario={scenario} arch={arch} device={device} "
          f"epochs={epochs} rounds={rounds} region={region_idx + 1} out={args.output_dir}", flush=True)

    if scenario == "centralized":
        model, metrics = run_centralized(arch, train_path, eval_path, epochs, device)
    elif scenario == "regional":
        model, metrics = run_regional(arch, train_path, eval_path, epochs, region_idx, device)
    elif scenario == "fedavg":
        model, metrics = run_fedavg(arch, train_path, eval_path, rounds, device)
    else:  # feddistill
        model, metrics = run_feddistill(arch, train_path, eval_path, rounds, region_idx, device)

    # --- write the servable artifact (the MTLF serving contract) ---
    model_path = os.path.join(args.output_dir, "model.pt")
    torch.save(model.state_dict(), model_path)
    num_params = sum(p.numel() for p in model.parameters())

    manifest = {
        "architecture": arch,
        "artifactType": "pytorch-state-dict",
        "artifactFileName": "model.pt",
        "trainingScenario": args.scenario,
        "labelMap": {str(i): name for i, name in enumerate(CLASS_NAME)},
        "packetSize": PACKET_LEN,
        "sequenceSize": SEQ_LEN,
        "numClasses": NUM_CLASS,
        "numRegions": NUM_REGION,
        "region": region_idx + 1,
        "epochs": epochs,
        "rounds": rounds if scenario in ("fedavg", "feddistill") else None,
        "framework": "pytorch",
        "frameworkVersion": torch.__version__,
        "numParameters": num_params,
        "trainPath": train_path,
        "evalPath": eval_path,
        "metrics": metrics,
        "idsCompatible": True,
    }
    with open(os.path.join(args.output_dir, "metrics.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)

    test_acc = (metrics.get("test") or {}).get("accuracy")
    eval_acc = (metrics.get("eval") or {}).get("accuracy")
    print(f"[mtlf_train] DONE -> {model_path} ({num_params} params) "
          f"test_acc={test_acc} eval_acc={eval_acc}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
