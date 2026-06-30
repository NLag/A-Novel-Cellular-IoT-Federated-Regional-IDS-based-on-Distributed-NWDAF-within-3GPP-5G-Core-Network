#!/usr/bin/env python3
"""R3-9 rebuttal: extended evaluation metrics beyond accuracy + weighted-F1.

Reviewer 3 (comment R3-9) asked why only Accuracy and F1-score are reported.
This script derives the additional metrics they expect -- precision, recall
(the security-critical metric for false negatives) and macro-averaged F1 --
WITHOUT any retraining, by reusing the raw per-sample predictions/labels that
were already saved by the canonical experiment runs:

  * FedAvg  (global model)      : result0307/FL/{eval,test}_results_FL_<arch>.pkl
  * FedDist (per-region models) : result0407/FD/{evaluation,private_test}_results_FD_<arch>.pkl

Both runs were verified to reproduce the published paper tables exactly.
Output: extended_metrics.csv and extended_metrics.md in this directory.
"""
import os, pickle, csv
import numpy as np
from sklearn.metrics import (accuracy_score, precision_recall_fscore_support,
                             precision_score, recall_score, f1_score)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ARCHS = ["MLP", "CNN", "RNN", "GRU", "LSTM", "Transformer"]
CLASS_NAME = ['normal', 'coapdos', 'mqttflood', 'pingflood', 'portscan', 'tcpsyn']

FL_DIR = os.path.join(ROOT, "result0307", "FL")     # canonical FedAvg
FD_DIR = os.path.join(ROOT, "result0407", "FD")     # canonical FedDistill


def load(p):
    with open(p, "rb") as f:
        return pickle.load(f)


def metrics_from(labels, preds):
    """Overall metric bundle (percent) from per-sample labels/preds."""
    labels = np.asarray(labels); preds = np.asarray(preds)
    acc = accuracy_score(labels, preds) * 100
    out = {"accuracy": acc}
    for avg in ("weighted", "macro"):
        p, r, f, _ = precision_recall_fscore_support(
            labels, preds, average=avg, zero_division=0)
        out[f"precision_{avg}"] = p * 100
        out[f"recall_{avg}"] = r * 100
        out[f"f1_{avg}"] = f * 100
    # per-class recall = per-attack detection rate (what a security reviewer cares about)
    pc_recall = recall_score(labels, preds, average=None,
                             labels=list(range(len(CLASS_NAME))), zero_division=0) * 100
    pc_prec = precision_score(labels, preds, average=None,
                              labels=list(range(len(CLASS_NAME))), zero_division=0) * 100
    out["per_class_recall"] = dict(zip(CLASS_NAME, pc_recall))
    out["per_class_precision"] = dict(zip(CLASS_NAME, pc_prec))
    return out


def fl_metrics(arch, split):
    fname = ("eval_results" if split == "eval" else "test_results") + f"_FL_{arch}.pkl"
    o = load(os.path.join(FL_DIR, fname))
    e = o[0] if isinstance(o, dict) else o  # global model entry keyed by 0
    return metrics_from(e["labels"], e["predictions"])


def fd_metrics(arch, split):
    """FedDistill: average the per-region model metrics (matches paper summary)."""
    fname = ("evaluation_results" if split == "eval" else "private_test_results") + f"_FD_{arch}.pkl"
    regions = load(os.path.join(FD_DIR, fname))  # list of 5, each {0:{labels,preds}}
    per_region = [metrics_from(r[0]["labels"], r[0]["predictions"]) for r in regions]
    agg = {}
    for k in ("accuracy", "precision_weighted", "recall_weighted", "f1_weighted",
              "precision_macro", "recall_macro", "f1_macro"):
        agg[k] = float(np.mean([m[k] for m in per_region]))
    # per-class recall averaged across regions
    agg["per_class_recall"] = {c: float(np.mean([m["per_class_recall"][c] for m in per_region]))
                               for c in CLASS_NAME}
    agg["per_class_precision"] = {c: float(np.mean([m["per_class_precision"][c] for m in per_region]))
                                  for c in CLASS_NAME}
    agg["_per_region"] = per_region
    return agg


def main():
    rows = []
    for scheme, fn in (("FedAvg", fl_metrics), ("FedDistill", fd_metrics)):
        for split in ("test", "eval"):
            for arch in ARCHS:
                m = fn(arch, split)
                rows.append((scheme, split, arch, m))

    # CSV
    cols = ["scheme", "split", "arch", "accuracy",
            "precision_weighted", "recall_weighted", "f1_weighted",
            "precision_macro", "recall_macro", "f1_macro"]
    with open(os.path.join(HERE, "extended_metrics.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(cols)
        for scheme, split, arch, m in rows:
            w.writerow([scheme, split, arch] + [f"{m[c]:.2f}" for c in cols[3:]])

    # Markdown
    lines = ["# R3-9: Extended Evaluation Metrics", "",
             "Derived from the canonical saved predictions (no retraining):",
             "FedAvg = `result0307/FL` (reproduces paper Table FedAvg); "
             "FedDistill = `result0407/FD` (reproduces paper Table FedDistill, per-region mean).",
             "All values in percent. `recall` is the attack detection rate "
             "(the security-critical metric for false negatives).", ""]
    for split in ("test", "eval"):
        lines += [f"## {split.upper()} set", "",
                  "| Scheme | Arch | Acc | Prec (w) | Recall (w) | F1 (w) | Prec (macro) | Recall (macro) | F1 (macro) |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for scheme, sp, arch, m in rows:
            if sp != split:
                continue
            lines.append("| {} | {} | {:.2f} | {:.2f} | {:.2f} | {:.2f} | {:.2f} | {:.2f} | {:.2f} |".format(
                scheme, arch, m["accuracy"], m["precision_weighted"], m["recall_weighted"],
                m["f1_weighted"], m["precision_macro"], m["recall_macro"], m["f1_macro"]))
        lines.append("")
    # per-class recall on the eval set (variant attacks) -- the headline security view
    lines += ["## Per-class RECALL on EVAL set (detection rate per class, %)", "",
              "| Scheme | Arch | " + " | ".join(CLASS_NAME) + " |",
              "|---|---|" + "|".join(["---"] * len(CLASS_NAME)) + "|"]
    for scheme, sp, arch, m in rows:
        if sp != "eval":
            continue
        pc = m["per_class_recall"]
        lines.append("| {} | {} | ".format(scheme, arch) +
                     " | ".join(f"{pc[c]:.2f}" for c in CLASS_NAME) + " |")
    with open(os.path.join(HERE, "extended_metrics.md"), "w") as f:
        f.write("\n".join(lines) + "\n")

    # console summary
    print("Wrote extended_metrics.csv and extended_metrics.md")
    print("\nEVAL-set summary (Acc / Recall_w / F1_macro):")
    for scheme, sp, arch, m in rows:
        if sp == "eval":
            print(f"  {scheme:10s} {arch:12s} acc={m['accuracy']:6.2f}  "
                  f"recall_w={m['recall_weighted']:6.2f}  f1_macro={m['f1_macro']:6.2f}")


if __name__ == "__main__":
    main()
