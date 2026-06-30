#!/usr/bin/env python3
"""R4-5 rebuttal: sequence-length ablation for the FedAvg detector.

Reviewer 4 (R4-5) notes the 256-packet sequence length is motivated only by
latency and asks for an ablation of detection performance vs. sequence length.

This runner retrains the FedAvg global model at SEQ_LEN in {64,128,256,512}
using EXACTLY the canonical methodology of DL_multiclass_federated.py
(same loaders, same training_model early-stopping, same equal-weight averaging,
same round-level convergence rule), and additionally measures per-sequence GPU
inference latency at each length -- closing the loop on the latency rationale.

It is self-contained: it reuses the building blocks of IDS_lib but does not
import the experiment script (avoiding its import-time data load), and it sets
IDS_lib.SEQ_LEN programmatically before building each dataset.

Usage:
  python3 rebuttal_results/seq_len_ablation.py                 # Transformer, all 4 lengths
  python3 rebuttal_results/seq_len_ablation.py --archs Transformer CNN LSTM
  python3 rebuttal_results/seq_len_ablation.py --seq-lens 64 128 256 512
"""
import os, sys, json, time, argparse, copy
import numpy as np
import torch
from sklearn.metrics import accuracy_score, f1_score

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import IDS_lib as lib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
TRAIN = os.path.join(ROOT, "datasets/federated_datasets_noslowite_nosqlmap/train/")
EVAL = os.path.join(ROOT, "datasets/federated_datasets_noslowite_nosqlmap/eval/")

# Canonical FedAvg convergence constants (mirror DL_multiclass_federated.py)
ROUNDS = 50
FL_DELTA_ACC = 0.01
FL_DELTA_WEIGHT = 0.0001
FL_PATIENCE = 5


def build(arch):
    P, C = lib.PACKET_LEN, lib.NUM_CLASS
    if arch == "MLP":         return lib.MLPClassifier(input_features=P, output_dim=C)
    if arch == "CNN":         return lib.CNNClassifier(input_features=P, output_dim=C)
    if arch == "RNN":         return lib.RNNClassifier(input_features=P, hidden_dim=256, output_dim=C)
    if arch == "LSTM":        return lib.LSTMClassifier(input_features=P, hidden_dim=256, output_dim=C)
    if arch == "GRU":         return lib.GRUClassifier(input_features=P, hidden_dim=256, output_dim=C)
    if arch == "Transformer": return lib.TransformerClassifier(input_features=P)
    raise ValueError(arch)


def evaluate(model, loader):
    model.eval(); preds = []; labels = []
    with torch.no_grad():
        for inputs, lab in loader:
            out = model(inputs)
            p = torch.argmax(out.data, 2)
            preds.extend(p.view(-1).cpu().numpy())
            labels.extend(lab.view(-1).cpu().numpy())
    acc = accuracy_score(labels, preds) * 100
    return {
        "accuracy": acc,
        "f1_weighted": f1_score(labels, preds, average="weighted", zero_division=0) * 100,
        "f1_macro": f1_score(labels, preds, average="macro", zero_division=0) * 100,
    }


def fedavg(arch, train_loaders, val_loaders):
    """Faithful replica of run_federated_learning (global averaged model)."""
    model_list = [build(a).to(DEVICE) for a in [arch] * lib.NUM_REGION]
    averaged = build(arch).to(DEVICE)
    prev_state, patience, last_acc = None, 0, None
    for rnd in range(ROUNDS):
        for i in range(len(model_list)):
            lib.training_model(model_list[i], train_loaders[i], val_loaders[i],
                               patience=5, quiet=True, model_name=f"{arch}_{i}")
        avg_state = lib.average_model_weights(model_list)
        wchange = lib.calculate_weight_change(prev_state, avg_state) if prev_state else float("inf")
        prev_state = avg_state
        averaged.load_state_dict(avg_state)
        # global validation accuracy across all regions
        yp, yl = [], []
        averaged.eval()
        with torch.no_grad():
            for i in range(len(val_loaders)):
                for inputs, lab in val_loaders[i]:
                    p = torch.argmax(averaged(inputs).data, 2)
                    yp.extend(p.view(-1).cpu().numpy()); yl.extend(lab.view(-1).cpu().numpy())
        gacc = 100 * accuracy_score(yl, yp)
        for m in model_list:
            m.load_state_dict(avg_state)
        improve = (gacc - last_acc) if last_acc is not None else float("inf")
        print(f"    [{arch}] round {rnd+1}: global_val_acc={gacc:.2f} dW={wchange:.6f}", flush=True)
        if last_acc is not None and improve < FL_DELTA_ACC and wchange < FL_DELTA_WEIGHT:
            patience += 1
            if patience >= FL_PATIENCE:
                print(f"    [{arch}] converged after {rnd+1} rounds", flush=True)
                break
        else:
            patience = 0
        last_acc = gacc
    return averaged, rnd + 1


def measure_latency(model, eval_loader):
    """Per-batch / per-sequence GPU inference latency (ms)."""
    model.eval()
    batch = next(iter(eval_loader))[0].to(DEVICE)
    bsz = batch.size(0)
    with torch.no_grad():
        for _ in range(5):  # warmup
            model(batch)
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        for _ in range(50):
            model(batch)
        torch.cuda.synchronize()
        dt = (time.perf_counter() - t0) / 50
    return {"batch_size": bsz, "ms_per_batch": dt * 1000, "ms_per_sequence": dt * 1000 / bsz}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archs", nargs="+", default=["Transformer"])
    ap.add_argument("--seq-lens", nargs="+", type=int, default=[64, 128, 256, 512])
    args = ap.parse_args()

    out_json = os.path.join(HERE, "seq_len_ablation_results.json")
    results = json.load(open(out_json)) if os.path.exists(out_json) else []
    print(f"Device {DEVICE}; archs={args.archs}; seq_lens={args.seq_lens}", flush=True)

    for L in args.seq_lens:
        lib.SEQ_LEN = L
        print(f"\n=== SEQ_LEN={L}: loading data ===", flush=True)
        train_loaders, val_loaders, test_loaders, eval_loader = \
            lib.load_private_region_datasets(TRAIN, EVAL, quiet=True)
        for arch in args.archs:
            if any(r["arch"] == arch and r["seq_len"] == L for r in results):
                print(f"  skip {arch} L={L} (done)", flush=True); continue
            print(f"--- train {arch} @ SEQ_LEN={L} ---", flush=True)
            t0 = time.time()
            model, rounds_run = fedavg(arch, train_loaders, val_loaders)
            ev = evaluate(model, eval_loader)
            # test = combine per-region test predictions
            tp, tl = [], []
            model.eval()
            with torch.no_grad():
                for i in range(len(test_loaders)):
                    for inputs, lab in test_loaders[i]:
                        p = torch.argmax(model(inputs).data, 2)
                        tp.extend(p.view(-1).cpu().numpy()); tl.extend(lab.view(-1).cpu().numpy())
            test_m = {"accuracy": accuracy_score(tl, tp) * 100,
                      "f1_weighted": f1_score(tl, tp, average="weighted", zero_division=0) * 100,
                      "f1_macro": f1_score(tl, tp, average="macro", zero_division=0) * 100}
            lat = measure_latency(model, eval_loader)
            nparams = sum(p.numel() for p in model.parameters())
            rec = {"arch": arch, "seq_len": L, "rounds_run": rounds_run,
                   "params": nparams, "train_seconds": round(time.time() - t0, 1),
                   "test": test_m, "eval": ev, "latency": lat}
            results.append(rec)
            json.dump(results, open(out_json, "w"), indent=2)
            print(f"  DONE {arch} L={L}: eval_acc={ev['accuracy']:.2f} "
                  f"eval_f1w={ev['f1_weighted']:.2f} eval_f1m={ev['f1_macro']:.2f} "
                  f"lat={lat['ms_per_sequence']:.3f}ms/seq rounds={rounds_run}", flush=True)

    # markdown
    lines = ["# R4-5: Sequence-length ablation (FedAvg global model)", "",
             "Same methodology as the canonical FedAvg run; eval = independent dataset. "
             "Latency measured on the A40 for a batch of 16 sequences.", "",
             "| Arch | SeqLen | Test Acc | Test F1(w) | Eval Acc | Eval F1(w) | Eval F1(macro) | Rounds | ms/seq |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(results, key=lambda x: (x["arch"], x["seq_len"])):
        lines.append("| {} | {} | {:.2f} | {:.2f} | {:.2f} | {:.2f} | {:.2f} | {} | {:.3f} |".format(
            r["arch"], r["seq_len"], r["test"]["accuracy"], r["test"]["f1_weighted"],
            r["eval"]["accuracy"], r["eval"]["f1_weighted"], r["eval"]["f1_macro"],
            r["rounds_run"], r["latency"]["ms_per_sequence"]))
    open(os.path.join(HERE, "seq_len_ablation.md"), "w").write("\n".join(lines) + "\n")
    print("\nWrote seq_len_ablation_results.json and seq_len_ablation.md", flush=True)


if __name__ == "__main__":
    main()
