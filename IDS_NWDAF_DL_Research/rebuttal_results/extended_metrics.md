# R3-9: Extended Evaluation Metrics

Derived from the canonical saved predictions (no retraining):
FedAvg = `result0307/FL` (reproduces paper Table FedAvg); FedDistill = `result0407/FD` (reproduces paper Table FedDistill, per-region mean).
All values in percent. `recall` is the attack detection rate (the security-critical metric for false negatives).

## TEST set

| Scheme | Arch | Acc | Prec (w) | Recall (w) | F1 (w) | Prec (macro) | Recall (macro) | F1 (macro) |
|---|---|---|---|---|---|---|---|---|
| FedAvg | MLP | 92.75 | 93.74 | 92.75 | 92.59 | 97.26 | 95.76 | 96.16 |
| FedAvg | CNN | 99.65 | 99.65 | 99.65 | 99.65 | 99.84 | 99.80 | 99.82 |
| FedAvg | RNN | 98.70 | 98.73 | 98.70 | 98.69 | 99.45 | 99.24 | 99.33 |
| FedAvg | GRU | 99.95 | 99.95 | 99.95 | 99.95 | 99.98 | 99.97 | 99.98 |
| FedAvg | LSTM | 99.97 | 99.97 | 99.97 | 99.97 | 99.99 | 99.98 | 99.98 |
| FedAvg | Transformer | 100.00 | 100.00 | 100.00 | 100.00 | 100.00 | 100.00 | 100.00 |
| FedDistill | MLP | 73.02 | 85.58 | 73.02 | 71.63 | 76.74 | 73.53 | 68.83 |
| FedDistill | CNN | 88.69 | 91.81 | 88.69 | 88.98 | 72.32 | 73.06 | 71.74 |
| FedDistill | RNN | 76.47 | 86.87 | 76.47 | 75.62 | 67.41 | 65.43 | 62.08 |
| FedDistill | GRU | 68.30 | 85.12 | 68.30 | 63.11 | 76.33 | 70.24 | 62.54 |
| FedDistill | LSTM | 69.89 | 86.47 | 69.89 | 66.12 | 67.06 | 61.80 | 56.72 |
| FedDistill | Transformer | 88.04 | 91.37 | 88.04 | 88.15 | 89.01 | 90.15 | 87.99 |

## EVAL set

| Scheme | Arch | Acc | Prec (w) | Recall (w) | F1 (w) | Prec (macro) | Recall (macro) | F1 (macro) |
|---|---|---|---|---|---|---|---|---|
| FedAvg | MLP | 79.45 | 86.28 | 79.45 | 78.07 | 85.13 | 70.89 | 71.43 |
| FedAvg | CNN | 80.21 | 85.77 | 80.21 | 75.68 | 94.68 | 72.87 | 74.33 |
| FedAvg | RNN | 91.38 | 92.68 | 91.38 | 90.68 | 93.01 | 86.82 | 87.91 |
| FedAvg | GRU | 87.04 | 89.83 | 87.04 | 86.34 | 90.89 | 84.36 | 85.20 |
| FedAvg | LSTM | 85.59 | 88.94 | 85.59 | 84.57 | 96.10 | 81.69 | 86.07 |
| FedAvg | Transformer | 98.21 | 98.27 | 98.21 | 98.17 | 99.37 | 97.57 | 98.39 |
| FedDistill | MLP | 65.73 | 59.77 | 65.73 | 56.09 | 60.89 | 48.75 | 47.88 |
| FedDistill | CNN | 72.02 | 70.43 | 72.02 | 64.93 | 75.25 | 57.81 | 58.93 |
| FedDistill | RNN | 67.99 | 65.55 | 67.99 | 58.73 | 72.67 | 51.19 | 51.83 |
| FedDistill | GRU | 62.70 | 69.07 | 62.70 | 52.31 | 75.75 | 43.26 | 43.42 |
| FedDistill | LSTM | 62.27 | 58.82 | 62.27 | 51.57 | 62.30 | 39.93 | 37.89 |
| FedDistill | Transformer | 84.52 | 85.22 | 84.52 | 81.35 | 91.32 | 80.93 | 82.60 |

## Per-class RECALL on EVAL set (detection rate per class, %)

| Scheme | Arch | normal | coapdos | mqttflood | pingflood | portscan | tcpsyn |
|---|---|---|---|---|---|---|---|
| FedAvg | MLP | 100.00 | 78.05 | 70.52 | 24.94 | 99.86 | 51.97 |
| FedAvg | CNN | 99.81 | 87.83 | 90.87 | 0.64 | 99.47 | 58.62 |
| FedAvg | RNN | 99.97 | 82.76 | 93.02 | 47.90 | 99.97 | 97.30 |
| FedAvg | GRU | 99.99 | 86.37 | 96.52 | 69.16 | 99.98 | 54.18 |
| FedAvg | LSTM | 99.98 | 85.76 | 98.12 | 46.19 | 99.96 | 60.15 |
| FedAvg | Transformer | 99.96 | 86.61 | 98.99 | 100.00 | 99.99 | 99.89 |
| FedDistill | MLP | 99.99 | 53.05 | 45.22 | 20.90 | 55.26 | 18.11 |
| FedDistill | CNN | 99.77 | 79.23 | 61.63 | 59.91 | 29.98 | 16.36 |
| FedDistill | RNN | 99.92 | 58.83 | 42.02 | 39.82 | 46.84 | 19.73 |
| FedDistill | GRU | 99.99 | 41.68 | 21.91 | 24.81 | 58.87 | 12.31 |
| FedDistill | LSTM | 99.99 | 45.14 | 26.07 | 25.23 | 23.37 | 19.76 |
| FedDistill | Transformer | 99.97 | 74.33 | 81.24 | 99.99 | 93.83 | 36.22 |
