# R4-7: Effect of Extreme Class Imbalance (FedAvg, eval set)

Binary attack-vs-normal view. Detection rate (recall) and normal false-positive rate (FPR) are prevalence-invariant; accuracy, precision and F1 are projected exactly to each attack prevalence.
Natural eval prevalence = 52.49% attack. All values in percent.

## MLP  (recall=76.18%, FPR=0.00% -- both constant)

| Attack prevalence | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|
| 52.49% | 87.50 | 100.00 | 76.18 | 86.48 |
| 10.00% | 97.62 | 99.97 | 76.18 | 86.47 |
| 1.00% | 99.76 | 99.72 | 76.18 | 86.38 |
| 0.50% | 99.88 | 99.45 | 76.18 | 86.27 |
| 0.10% | 99.97 | 97.28 | 76.18 | 85.45 |

## CNN  (recall=62.49%, FPR=0.19% -- both constant)

| Attack prevalence | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|
| 52.49% | 80.22 | 99.72 | 62.49 | 76.83 |
| 10.00% | 96.07 | 97.29 | 62.49 | 76.10 |
| 1.00% | 99.43 | 76.56 | 62.49 | 68.81 |
| 0.50% | 99.62 | 61.90 | 62.49 | 62.19 |
| 0.10% | 99.77 | 24.45 | 62.49 | 35.15 |

## RNN  (recall=87.75%, FPR=0.03% -- both constant)

| Attack prevalence | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|
| 52.49% | 93.55 | 99.97 | 87.75 | 93.46 |
| 10.00% | 98.74 | 99.66 | 87.75 | 93.32 |
| 1.00% | 99.84 | 96.37 | 87.75 | 91.86 |
| 0.50% | 99.91 | 92.96 | 87.75 | 90.28 |
| 0.10% | 99.95 | 72.45 | 87.75 | 79.37 |

## GRU  (recall=81.35%, FPR=0.01% -- both constant)

| Attack prevalence | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|
| 52.49% | 90.21 | 99.98 | 81.35 | 89.71 |
| 10.00% | 98.12 | 99.84 | 81.35 | 89.65 |
| 1.00% | 99.80 | 98.30 | 81.35 | 89.03 |
| 0.50% | 99.89 | 96.64 | 81.35 | 88.34 |
| 0.10% | 99.97 | 85.14 | 81.35 | 83.20 |

## LSTM  (recall=72.57%, FPR=0.02% -- both constant)

| Attack prevalence | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|
| 52.49% | 85.59 | 99.97 | 72.57 | 84.09 |
| 10.00% | 97.24 | 99.71 | 72.57 | 84.00 |
| 1.00% | 99.70 | 96.90 | 72.57 | 82.99 |
| 0.50% | 99.84 | 93.96 | 72.57 | 81.89 |
| 0.10% | 99.95 | 75.60 | 72.57 | 74.05 |

## Transformer  (recall=96.62%, FPR=0.04% -- both constant)

| Attack prevalence | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|
| 52.49% | 98.21 | 99.97 | 96.62 | 98.27 |
| 10.00% | 99.63 | 99.66 | 96.62 | 98.12 |
| 1.00% | 99.93 | 96.42 | 96.62 | 96.52 |
| 0.50% | 99.95 | 93.05 | 96.62 | 94.81 |
| 0.10% | 99.96 | 72.74 | 96.62 | 83.00 |

