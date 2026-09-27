# Round 2 Experimental Progress

Last updated: 27 August 2026

## R2-4 independent regional baseline

- Reused `../DL_multiclass_regional_models.py` and added `r2_4_regional_baseline.py` as a result-persisting harness.
- Corrected the harness paths after it was moved into `rebuttal_round_2/`.
- Used the original `federated_datasets_noslowite_nosqlmap` training and independent evaluation data.
- Loaded each region's private data together with the shared public data, with no cross-region parameter, logit, or knowledge exchange.
- Used the implemented two-stage 80:20 and 80:20 splits, which yield an effective 64/16/20 train/validation/test allocation.
- Trained five Transformer models on an NVIDIA A40 with Adam at `1e-4`, a 50-epoch maximum, and validation-loss stopping (`min_delta=0.001`, patience 5). Random seeds were not fixed, consistently with the original runs.
- Archived model states, configuration, metrics, confusion matrices, labels, hard predictions, and continuous six-class probabilities.

## Validated result

On the independent evaluation set, the unweighted mean and population standard deviation across the five regional models are:

| Metric | Mean ± SD (%) |
|---|---:|
| Accuracy | 91.19 ± 6.28 |
| Weighted F1 | 89.92 ± 8.18 |
| Macro F1 | 91.13 ± 6.82 |

Per-region external-evaluation accuracy is 80.73%, 95.90%, 96.25%, 95.99%, and 87.06% for Regions 1--5. Relative to this regional-only mean, the paper's FedAvg Transformer gains 7.02 accuracy points and 8.25 weighted-F1 points; FedDistill is lower by 6.67 and 8.57 points.

## Artifacts and checks

- Report: `../../OAI_5G_STORAGE/IDS_RELATED_STORAGE/REPORT/r2-4-regional-baseline-20260827/`
- Models: `../../OAI_5G_STORAGE/IDS_RELATED_STORAGE/MODEL/r2-4-regional-transformer-20260827/`
- `summary.json` SHA-256: `7c65dc4021243ba1b817be0b39fdddf7d78ee9b7f43ac09995e3f5c4da139a02`
- Each external-evaluation archive contains 296,192 labels, predictions, and six-class probability vectors.
- Accuracy, weighted F1, and macro F1 were recomputed from each NPZ archive and exactly match the saved JSON metrics.
- Probability arrays are finite and every probability row sums to one within numerical tolerance.

