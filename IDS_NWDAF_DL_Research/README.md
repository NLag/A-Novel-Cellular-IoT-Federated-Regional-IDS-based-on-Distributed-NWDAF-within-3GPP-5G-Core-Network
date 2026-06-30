# IDS NWDAF Federated Learning Workspace

This folder contains the research Python code and experiment artifacts for the AI/deep-learning part of the IDS/NWDAF work. It is separate from the current `IDS/components/oai-ids` network-function prototype: this code focuses on model training, federated learning, federated distillation, dataset preparation, and result analysis.

The tree also contains many large datasets and generated results. Treat this directory as a research workspace, not as a clean runtime package yet.

## What Is Here

Core code:

- `nwdaf_mtlf_model_training/`: normalization package for Phase 2 work. It currently provides side-effect-free constants, a workspace manifest, and package boundaries for future refactors.
- `IDS_lib.py`: shared library for dataset preprocessing, PyTorch datasets/loaders, training loops, distillation training, model averaging, and model definitions.
- `DL_multiclass_centralize.py`: centralized multi-class training/evaluation for several model architectures.
- `DL_multiclass_federated.py`: federated learning workflow using regional private datasets and model-weight averaging.
- `DL_multiclass_Federated_Distillation.py`: federated distillation workflow using public/shared data plus regional private data.
- `DL_multiclass_regional_models.py`: trains separate regional models, currently against the simple federated dataset split.
- `train_test_data_federated_simple.ipynb`, `train_test_data_federated_realistic.ipynb`, and notebooks under `datasets/`: dataset preparation notebooks.
- `requirements.txt`: dependency list inferred from the current scripts.

Large data/artifact areas:

- `datasets/`: raw and prepared NAS traffic datasets.


## Dataset Warning

Many files in this directory are large CSV, PKL, ZIP, PNG, or PTH artifacts. Do not recursively read dataset or result files when documenting or analyzing the code. Use directory names, file names, sizes, and at most the first safe line of a CSV when needed.

Current size snapshot from inspection:

- `datasets/`: about 1.2 GB.

Active training scripts currently point to:

```text
./datasets/federated_datasets/train/
./datasets/federated_datasets/eval/
```

That prepared split contains:

- `train/public/public_shared_dataset.csv`
- `train/private/private_region_dataset_1.csv` through `private_region_dataset_5.csv`
- `eval/Combined_eval_dataset.csv`


Raw or scenario-specific dataset folders include:

- `normal`
- `coap_dos`
- `mqttPUBflood`
- `pingflood`
- `port_scan`
- `tcpflood`

CSV rows appear to follow the feature order listed in `datasets/Feature_name.dat`, starting with:

```text
idx
level
timestamp
direction
ue_id
```

The code expects a packet hex column named `packet_hex` and a numeric `label` column after preprocessing.

## Model and Data Assumptions

The shared constants in `IDS_lib.py` define the current experiment shape:

```text
NUM_CLASS = 6
CLASS_NAME = ['normal', 'coapdos', 'mqttflood', 'pingflood', 'portscan', 'tcpsyn']
NUM_REGION = 5
BATCH_SIZE = 16
SEQ_LEN = 256
PACKET_LEN = 1500
EPOCHS = 50
DISTILLATION_EPOCHS = 25
LEARNING_RATE = 0.0001
```

The dataset loader converts packet hex strings into byte tensors, pads each packet to `PACKET_LEN`, groups packets into sequences of `SEQ_LEN`, and trains sequence classifiers that predict one label per packet in the sequence.

Implemented model classes:

- `MLPClassifier`
- `CNNClassifier`
- `RNNClassifier`
- `LSTMClassifier`
- `GRUClassifier`
- `TransformerClassifier`
- `TwoLevelTransformer`

## Normalized Package Boundary

Workstream 2.1 starts the transition from flat research scripts to explicit packages. The package is intentionally light at first so existing experiments keep working.

Current normalized modules:

- `nwdaf_mtlf_model_training/constants.py`: side-effect-free experiment defaults mirroring `IDS_lib.py`.
- `nwdaf_mtlf_model_training/manifest.py`: workspace manifest for legacy scripts, dataset splits, notebooks, and artifact directories.
- `nwdaf_mtlf_model_training/scenarios.py`: registry for the four main training scenarios and their legacy scripts.
- `nwdaf_mtlf_model_training/cli.py`: safe command-line inspection helper that does not execute training.
- `nwdaf_mtlf_model_training/data/`: target package for dataset handling and preprocessing.
- `nwdaf_mtlf_model_training/models/`: target package for PyTorch model definitions.
- `nwdaf_mtlf_model_training/training/`: target package for local training and distillation training loops.
- `nwdaf_mtlf_model_training/federated/`: target package for federated averaging, federated distillation orchestration, and communication-cost metrics.
- `nwdaf_mtlf_model_training/evaluation/`: target package for metrics, confusion matrices, plots, and result persistence.

The normalized package should stay separate from the runtime IDS NF. The runtime IDS should consume exported model artifacts through a stable contract, not import training scripts directly.

For the NWDAF MTLF integration, `nwdaf_mtlf_model_training` is the preferred long-term API boundary. The current MTLF can select one of the four scenario keys at Helm boot time, but it still executes the flat legacy scripts as subprocesses because the package does not yet contain import-safe training entry points.

Inspect the normalized scenario registry with:

```bash
python3 -m nwdaf_mtlf_model_training list-scenarios
python3 -m nwdaf_mtlf_model_training show-scenario federated-distillation
python3 -m nwdaf_mtlf_model_training legacy-command centralized
```

These commands only print metadata or legacy commands. They do not execute training or load datasets.

## Main Workflows

Run commands from this directory because the scripts use relative dataset paths.

```bash
cd IDS_NWDAF_DL_Research
```

The four normalized scenario keys are:

| Scenario key | Legacy script | Purpose |
| --- | --- | --- |
| `centralized` | `DL_multiclass_centralize.py` | Train global models on combined data. |
| `federated-averaging` | `DL_multiclass_federated.py` | Train regional models and average weights each round. |
| `federated-distillation` | `DL_multiclass_Federated_Distillation.py` | Train regional models using public-data soft-label exchange plus private data. |
| `regional` | `DL_multiclass_regional_models.py` | Train independent regional models with no global aggregation. |

Centralized training:

```bash
python DL_multiclass_centralize.py
```

This loads all public/private training data into one centralized train/validation/test split, trains multiple architectures, evaluates them, and writes model/checkpoint and confusion-matrix files into the current working directory.

Federated learning:

```bash
python DL_multiclass_federated.py
```

This loads regional private datasets, trains one model per region, averages model weights each round, evaluates the averaged model, and writes round metrics, test/evaluation results, and plots.

Federated distillation:

```bash
python DL_multiclass_Federated_Distillation.py
```

This loads public/shared and regional private datasets, performs public-data distillation with soft labels, then trains on private regional data. It writes per-model checkpoints, pickled metrics/results, and plots.

Regional-only training:

```bash
python DL_multiclass_regional_models.py
```

This trains separate regional models and evaluates each model independently.

Important: the training scripts perform dataset loading at module import/top level, before the `if __name__ == "__main__"` block. Importing these scripts from another module can therefore load large datasets immediately.

## Expected Dependencies

`requirements.txt` records the inferred dependency set:

```text
torch
pandas
numpy
scikit-learn
matplotlib
tqdm
jupyter
```

A likely local setup is:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install torch pandas numpy scikit-learn matplotlib tqdm jupyter
```

Choose the PyTorch install command that matches the target machine's CPU/GPU/CUDA environment.

Run the lightweight normalization tests with:

```bash
cd IDS_NWDAF_DL_Research
python3 -m unittest discover -s tests
```

## Result Artifacts

Generated result folders are date-like experiment snapshots. Common files include:

- `model_*.pth` and `sample_*_classifier.pth`: PyTorch model state files.
- `round_metrics_*.pkl`: per-round training metrics.
- `evaluation_results_*.pkl`, `eval_results_*.pkl`, `test_results_*.pkl`, `private_test_results_*.pkl`: saved evaluation outputs.
- `confusion_matrix_*.png`: confusion matrix plots.
- `convergence_plots_*.png`, `f1_score_over_rounds*.png`, `validation_accuracy_over_rounds*.png`: convergence and metric plots.
- `output.txt`: captured console output from runs.

The canonical/latest result folder is not obvious from filenames alone. Verify with experiment notes before using a result snapshot as a reference.

## Current Gaps

- Paths and hyperparameters are hard-coded in scripts.
- Dataset loading happens at import time in training scripts.
- Results are written into the working directory or result folders without a single run configuration file.
- Most functional code still lives in `IDS_lib.py`; future work should migrate it into the new package slices without breaking existing experiment scripts.

## Relationship To The IDS Runtime

This folder should become the source for the Phase 2 AI/model work in the IDS roadmap:

- define model artifact metadata and label maps
- train/federate models using the research workflows here
- export selected model artifacts for the runtime IDS NF
- later connect model updates to NWDAF/DCCF/ADRF/MTLF-style flows

## Track B — OAI integration and cross-platform reproduction (2026-06-30)

The ML/DL integration is now connected to the live OAI NWDAF/IDS, and the deployed `oai-ids` NF runs the **real** trained model (no longer a placeholder):

- `mtlf_train.py` — parameterised NWDAF MTLF training entry point. Runs one scenario (`centralized` / `regional` / `federated-averaging` / `federated-distillation`) for one architecture and writes a servable `model.pt` (state-dict) + `metrics.json`, matching the MTLF `Nnwdaf_MLModelProvision` contract. Wired into `oai-cn5g-nwdaf` MTLF config.
- `DL_multiclass_federated.py` and `DL_multiclass_Federated_Distillation.py` were made **import-safe** (module-level dataset loads guarded under `if __name__ == "__main__"`) so `mtlf_train.py` can reuse their drivers; direct execution is unchanged.
- `build_oai_dataset.py` — consolidates the live OAI captures (`OAI_5G_STORAGE/IDS_RELATED_STORAGE/DATASETS/...`) into the federated training layout `datasets/oai_federated_20260630/` (public + 5 private + eval), one attack per region.
- `rebuttal_results/track_b_oai_results.md` — full Track B results: FedAvg-Transformer trained on OAI-captured traffic reaches **test 96.18% / eval 100%** (similar to the Amarisoft thesis); end-to-end detection latency ≈ a few ms; per-round FL latency ≈5 s (FedAvg) / ≈30 s (FedDistill); CP overhead gated to one notification per attack episode.
- The runtime IDS NF loads the exported state-dict via `IDS/components/oai-ids/app/torch_detector.py` (see `IDS/PROGRESS_IDS.md`).

The earlier note below is superseded by the above:

> For now, the deployed `oai-ids` NF uses a deterministic placeholder detector. The real ML/DL integration should happen only after the model artifact boundary and NWDAF integration contract are defined.
