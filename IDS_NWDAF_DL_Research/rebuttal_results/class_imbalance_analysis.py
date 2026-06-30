#!/usr/bin/env python3
"""R4-7 rebuttal: effect of extreme class imbalance (down to <1% attack).

Reviewer 4 (R4-7) asks how an extreme attack-to-normal ratio (e.g. <1% attack)
would affect results, given our balanced "attack-window" evaluation set
(naturally ~52% attack).

Key statistical fact we exploit: in the binary attack-vs-normal view, the
detection rate (recall = P(flag | attack)) and the normal false-positive rate
(FPR = P(flag | normal)) are properties of the model and are INVARIANT to the
class prevalence. Only prevalence-weighted quantities (accuracy, precision, F1)
change as attacks become rarer. We can therefore project every metric to any
prevalence p EXACTLY from the saved per-sample predictions -- no resampling,
no retraining:

    accuracy(p)  = p*recall + (1-p)*(1-FPR)
    precision(p) = p*recall / ( p*recall + (1-p)*FPR )
    F1(p)        = 2*precision*recall / (precision + recall)

This demonstrates the intended argument: recall (catching attacks) is unchanged
under extreme imbalance, accuracy becomes misleading (inflated by the normal
class), and precision -- i.e. the false-alarm burden -- becomes the binding
metric. Source predictions: canonical FedAvg run result0307/FL.
"""
import os, pickle, csv
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FL_DIR = os.path.join(ROOT, "result0307", "FL")
ARCHS = ["MLP", "CNN", "RNN", "GRU", "LSTM", "Transformer"]
PREVALENCES = [0.5249, 0.10, 0.01, 0.005, 0.001]  # 0.5249 = natural eval prevalence


def binary_rates(arch):
    o = pickle.load(open(os.path.join(FL_DIR, f"eval_results_FL_{arch}.pkl"), "rb"))
    e = o[0]
    y = np.asarray(e["labels"]) != 0       # true attack
    p = np.asarray(e["predictions"]) != 0  # flagged as attack
    recall = p[y].mean()                   # P(flag | attack)
    fpr = p[~y].mean()                     # P(flag | normal)
    return recall, fpr


def project(recall, fpr, prev):
    acc = prev * recall + (1 - prev) * (1 - fpr)
    denom = prev * recall + (1 - prev) * fpr
    prec = (prev * recall / denom) if denom > 0 else 0.0
    f1 = (2 * prec * recall / (prec + recall)) if (prec + recall) > 0 else 0.0
    return acc * 100, prec * 100, recall * 100, f1 * 100


def main():
    rows = []
    for arch in ARCHS:
        recall, fpr = binary_rates(arch)
        for prev in PREVALENCES:
            acc, prec, rec, f1 = project(recall, fpr, prev)
            rows.append((arch, prev, recall * 100, fpr * 100, acc, prec, rec, f1))

    with open(os.path.join(HERE, "class_imbalance.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["arch", "attack_prevalence", "recall(const)", "fpr(const)",
                    "accuracy", "precision", "recall", "f1"])
        for r in rows:
            w.writerow([r[0], f"{r[1]:.4f}"] + [f"{x:.2f}" for x in r[2:]])

    lines = ["# R4-7: Effect of Extreme Class Imbalance (FedAvg, eval set)", "",
             "Binary attack-vs-normal view. Detection rate (recall) and normal "
             "false-positive rate (FPR) are prevalence-invariant; accuracy, "
             "precision and F1 are projected exactly to each attack prevalence.",
             "Natural eval prevalence = 52.49% attack. All values in percent.", ""]
    for arch in ARCHS:
        recall, fpr = binary_rates(arch)
        lines += [f"## {arch}  (recall={recall*100:.2f}%, FPR={fpr*100:.2f}% -- both constant)", "",
                  "| Attack prevalence | Accuracy | Precision | Recall | F1 |",
                  "|---|---|---|---|---|"]
        for prev in PREVALENCES:
            acc, prec, rec, f1 = project(recall, fpr, prev)
            lines.append(f"| {prev*100:.2f}% | {acc:.2f} | {prec:.2f} | {rec:.2f} | {f1:.2f} |")
        lines.append("")
    with open(os.path.join(HERE, "class_imbalance.md"), "w") as f:
        f.write("\n".join(lines) + "\n")

    print("Wrote class_imbalance.csv and class_imbalance.md\n")
    print("Headline (Transformer vs MLP): recall constant, accuracy inflates, precision collapses")
    for arch in ("Transformer", "MLP"):
        recall, fpr = binary_rates(arch)
        print(f"\n{arch}: recall={recall*100:.2f}%  FPR={fpr*100:.2f}%")
        for prev in (0.5249, 0.01, 0.001):
            acc, prec, rec, f1 = project(recall, fpr, prev)
            print(f"   prev={prev*100:6.2f}%  acc={acc:6.2f}  prec={prec:6.2f}  rec={rec:6.2f}  f1={f1:6.2f}")


if __name__ == "__main__":
    main()
