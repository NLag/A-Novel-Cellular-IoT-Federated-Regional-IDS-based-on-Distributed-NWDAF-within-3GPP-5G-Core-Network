# NWDAF MTLF For IDS Model Provision

This component is the custom Model Training Logical Function used by the IDS project. It exposes the practical IDS-facing subset of `Nnwdaf_MLModelProvision`, manages IDS packet-classification training jobs, publishes model metadata/manifests/files, and notifies subscribed IDS instances when a model artifact is ready.

The old GNN forecasting workflow has been removed from this MTLF. Training is now scoped to the IDS research model families from `IDS_NWDAF_DL_Research`.

## Role

- Register with NRF as an NWDAF-compatible function exposing `nnwdaf-mlmodelprovision`.
- Accept IDS model-update subscriptions.
- Run one Helm-selected training scenario.
- Publish trained IDS artifacts through model metadata, manifest, and file endpoints.
- Record files written under `OAI_5G_STORAGE` in the regional NWDAF MongoDB `storage_metadata` collection.
- Notify IDS subscribers after a model is registered.

The proprietary training-job API is operational scaffolding. It is not a 3GPP external SBI.

## Training Scenarios

The scenario is fixed when the Helm release boots. A training request for a different scenario is rejected.

Supported scenario keys:

- `centralized`: one MTLF trains a global model from combined data.
- `regional`: each regional MTLF trains its own regional model.
- `federated-averaging`: regional MTLFs exchange model weights for FedAvg.
- `federated-distillation`: regional MTLFs exchange public-dataset logits.

The normalized `nwdaf_mtlf_model_training` package is vendored into this MTLF source tree and copied into the MTLF image. MTLF uses it as the safe scenario metadata boundary so scenario keys and legacy script paths can be resolved without importing dataset-loading training scripts.

The current implementation still executes the legacy research scripts as subprocesses. The long-term target is to replace those subprocess targets with import-safe training entry points inside `nwdaf_mtlf_model_training`.

## Model Architectures

The active architecture is selected through Helm at boot. Supported options mirror `IDS_NWDAF_DL_Research/IDS_lib.py`:

| Architecture | Main parameters |
| --- | --- |
| `MLP` | `hidden_dim: 256` |
| `CNN` | Conv1d stack: 1500 -> 512 -> 256 -> 128, FC 128 -> 32 -> classes |
| `RNN` | `hidden_dim: 256`, `num_layers: 1` |
| `GRU` | `hidden_dim: 256`, `num_layers: 1` |
| `LSTM` | `hidden_dim: 256`, `num_layers: 1` |
| `Transformer` | `hidden_dim: 256`, `nhead: 8`, `num_layers: 2` |

Common IDS defaults:

- classes: `normal`, `coapdos`, `mqttflood`, `pingflood`, `portscan`, `tcpsyn`
- packet length: `1500`
- sequence length: `256`
- batch size: `16`
- learning rate: `0.0001`
- epochs: `50` in the research defaults, chart-configurable for MTLF jobs

## Shared Storage

The dev chart mounts `OAI_5G_STORAGE` at `/oai-5g-storage` in MTLF, DCCF, and IDS pods.

Expected paths:

- `/oai-5g-storage/IDS_RELATED_STORAGE/DATASET`
- `/oai-5g-storage/IDS_RELATED_STORAGE/MODEL`
- `/oai-5g-storage/IDS_RELATED_STORAGE/REPORT`
- `/oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE`
- `/oai-5g-storage/IDS_RELATED_STORAGE/EXCHANGE`

Files created under this root should have a MongoDB metadata record. MTLF writes metadata for model artifacts and training outputs with category, producer NF, region, TAC, training scenario, job ID, model ID, file size, and SHA-256.

## Configuration

The Helm chart renders `mtlf-config.yaml`.

Key values:

```yaml
mtlf:
  training:
    scriptPath: /oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research/DL_multiclass_regional_models.py
    modelsDir: /oai-5g-storage/IDS_RELATED_STORAGE/MODEL
    defaultEpochs: 100
    pythonBin: python3
    passOutputDirArgs: false
    workingDir: /oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research
    researchWorkspace: /oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research
    normalizedPackage: nwdaf_mtlf_model_training
  trainingScenario:
    scenario: regional
    modelArchitecture: Transformer
    researchWorkspace: /oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research
    normalizedPackage: nwdaf_mtlf_model_training
    modelArchitectures:
      MLP:
        hidden_dim: 256
      CNN: {}
      RNN:
        hidden_dim: 256
        num_layers: 1
      GRU:
        hidden_dim: 256
        num_layers: 1
      LSTM:
        hidden_dim: 256
        num_layers: 1
      Transformer:
        hidden_dim: 256
        nhead: 8
        num_layers: 2
```

The chart also configures:

- `shared_storage.root`
- regional MongoDB URI/database
- `storage_metadata` collection
- serving area metadata
- callback URI used in model notifications

## API

Standard model-provision endpoints:

- `POST /nnwdaf-mlmodelprovision/v1/subscriptions`
- `DELETE /nnwdaf-mlmodelprovision/v1/subscriptions/{subscriptionId}`
- `GET /nnwdaf-mlmodelprovision/v1/ml-models`
- `GET /nnwdaf-mlmodelprovision/v1/ml-models/{modelId}`
- `GET /nnwdaf-mlmodelprovision/v1/ml-models/{modelId}/manifest`
- `GET /nnwdaf-mlmodelprovision/v1/ml-models/{modelId}/file`

Proprietary operational endpoints:

- `POST /proprietary/v1/training-jobs`
- `GET /proprietary/v1/training-jobs`
- `GET /proprietary/v1/training-jobs/{jobId}`
- `DELETE /proprietary/v1/training-jobs/{jobId}`
- `GET /proprietary/v1/training-scenario`
- `GET /proprietary/v1/storage/files`

Health:

- `GET /health`
- `GET /ready`
- `GET /nrf/status`
- `POST /nrf/register`

## Current Limitations

- `nwdaf_mtlf_model_training` currently provides import-safe constants, manifests, and scenario metadata. It does not yet contain full training entry points, so MTLF still uses legacy scripts as subprocesses.
- Legacy scripts write artifacts relative to their working directory; the configured working directory should therefore live under `OAI_5G_STORAGE`.
- IDS runtime model-byte loading and hot-swap are tracked separately in IDS Workstream 2.3.
- FedAvg and FedDistill network coordination still need explicit MTLF-to-MTLF exchange logic.
