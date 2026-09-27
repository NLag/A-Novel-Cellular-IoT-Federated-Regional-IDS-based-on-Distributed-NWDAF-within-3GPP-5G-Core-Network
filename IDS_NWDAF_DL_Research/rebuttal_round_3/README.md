# Round 3 rebuttal workspace

This directory contains the code and generated evidence used to answer the
third-round reviewer comments. Canonical experiment archives remain in their
original project locations and are referenced rather than duplicated.

- `code/`: reproducible audit scripts.
- `data/`: notes identifying canonical source data and result archives.
- `results/`: machine-readable audit results.
- `output/`: regenerated figures and other reviewer-facing outputs.
- `logs/`: execution and validation logs.

The first audit, `code/validate_round3_evidence.py`, reconciles the evaluation
sample totals, independently recomputes the canonical Transformer FedAvg
metrics, validates every series in manuscript Figure 4, and regenerates Figure
4 with one-based completed-round numbering.
