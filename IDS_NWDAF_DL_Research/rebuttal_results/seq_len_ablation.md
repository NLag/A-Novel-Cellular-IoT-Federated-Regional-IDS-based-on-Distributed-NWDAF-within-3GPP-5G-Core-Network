# R4-5: Sequence-length ablation (FedAvg global model)

Same methodology as the canonical FedAvg run; eval = independent dataset. Latency measured on the A40 for a batch of 16 sequences.

| Arch | SeqLen | Test Acc | Test F1(w) | Eval Acc | Eval F1(w) | Eval F1(macro) | Rounds | ms/seq |
|---|---|---|---|---|---|---|---|---|
| Transformer | 64 | 99.97 | 99.97 | 98.41 | 98.39 | 98.61 | 50 | 0.042 |
| Transformer | 128 | 100.00 | 100.00 | 98.44 | 98.41 | 98.58 | 50 | 0.075 |
| Transformer | 256 | 99.98 | 99.98 | 98.93 | 98.91 | 99.02 | 50 | 0.158 |
| Transformer | 512 | 99.98 | 99.98 | 96.82 | 96.78 | 97.46 | 48 | 0.386 |

## Interpretation (for R4-5 response)
- **Detection vs length:** accuracy on the independent eval set is robust for 64–256 packets (98.4–98.9%) and **peaks at 256** (98.93%). It then **drops at 512** (96.82%), i.e. an over-long window dilutes the attack signal and is harder to optimise with the same budget. So 256 is near-optimal in detection, not merely a latency pick.
- **Latency vs length:** per-sequence GPU inference scales **super-linearly** (0.042 → 0.075 → 0.158 → 0.386 ms), consistent with the Transformer's O(T^2) self-attention (Section complexity). Doubling 256→512 costs ~2.4x latency *and* loses accuracy — a strictly worse operating point.
- **Conclusion:** 256 packets is the sweet spot (best eval accuracy, latency still well under the per-batch budget). Shorter windows (64/128) trade ~0.5% accuracy for lower latency and could be chosen at higher line rates, matching the bandwidth-driven argument in the paper. (Ablation uses a fresh retrain, so absolute eval numbers differ marginally from the canonical Table; the trend is the result.)
