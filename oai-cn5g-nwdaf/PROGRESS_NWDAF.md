# NWDAF Development Progress

Last checked: 2026-06-30 after wiring the four training procedures into the MTLF via a single parameterised entry point (Track B).

This file tracks completed custom NWDAF work needed by the IDS project. Remaining NWDAF work is tracked in [`PLAN_NWDAF.md`](./PLAN_NWDAF.md). Dev-lab deployment checkpoints live in [`../oai-dev-env/PROGRESS_DEV_ENV.md`](../oai-dev-env/PROGRESS_DEV_ENV.md), and IDS-side work lives in [`../IDS/PROGRESS_IDS.md`](../IDS/PROGRESS_IDS.md).

## Current Snapshot

This repository is a custom IDS-oriented NWDAF workspace derived from OpenAirInterface `oai-cn5g-nwdaf`.

The active local deployment target is the minikube lab in [`../oai-dev-env/minikube`](../oai-dev-env/minikube). The legacy singleton NWDAF release `nwdaf` still exists, but the active Phase 2 regional baseline uses two additional NWDAF Helm releases:

- `nwdaf-paris`: region `region-paris`, TAC `000001`
- `nwdaf-lyon`: region `region-lyon`, TAC `000002`

Each regional release currently includes:

- MongoDB database.
- Kong NBI gateway.
- NWDAF engine.
- NBI analytics.
- NBI events.
- NBI ML.
- SBI.
- MTLF.
- DCCF.

The IDS-side Phase 2 integration now has a two-region NWDAF baseline. Paris IDS subscribes to Paris MTLF and forwards reports to Paris DCCF; Lyon IDS subscribes to Lyon MTLF and forwards reports to Lyon DCCF. DCCF uses each regional NWDAF MongoDB as the primary IDS report store, with SQLite and memory fallback paths for lab resilience. MTLF now has boot-time IDS training-scenario configuration and MongoDB metadata records for shared-storage files. Real normalized IDS model training/export and IDS runtime model fetch/hot-swap are still future work.

## Current Component Roles

- `components/oai-nwdaf-engine`: existing analytics engine used by NBI analytics for network performance, UE communication, and UE mobility calculations.
- `components/oai-nwdaf-nbi-analytics`: generated Go `Nnwdaf_AnalyticsInfo` service with custom engine calls.
- `components/oai-nwdaf-nbi-events`: generated Go `Nnwdaf_EventsSubscription` service.
- `components/oai-nwdaf-nbi-ml`: generated Go `Nnwdaf_MLModelProvision` service. Its subscription handlers are still mostly generated stubs. The Kong `/nnwdaf-mlmodelprovision/v1` route currently points here.
- `components/oai-nwdaf-sbi`: Go southbound service for AMF/SMF/PCF notification intake and MongoDB storage; it also contains a DCCF client boundary.
- `components/oai-nwdaf-dccf`: custom Python DCCF service with NRF registration, AMF/SMF event subscriptions, notification ingestion, data/analytics endpoints, subscription management, and MongoDB-backed IDS report storage.
- `components/oai-nwdaf-mtlf`: custom Python MTLF service implementing the practical IDS-facing `Nnwdaf_MLModelProvision` subscription, model registry, model-file serving, scenario-bound proprietary training-job trigger, shared-storage metadata indexing, DCCF callback, NRF registration, and health/readiness endpoints. IDS reaches it directly through the in-cluster MTLF service.

## Done

- [x] Added NWDAF to the local minikube dev lab.
  - Helm chart exists at [`../oai-dev-env/minikube/charts/oai-nwdaf-dev`](../oai-dev-env/minikube/charts/oai-nwdaf-dev).
  - Lab values exist under the minikube values tree.
  - Images are source-built with `pullPolicy: Never` for OAI-owned NWDAF components.
  - MongoDB and Kong remain upstream third-party images.
- [x] Deployed and validated the NWDAF release in namespace `oai-5g-core`.
  - `core`, `nwdaf`, and `packetrusher` releases have been deployed in the lab.
  - NWDAF pods were observed `1/1 Running` during the dev-lab validation.
  - The host-side Kong gateway on NodePort `30080` reached the NBI analytics route and returned application-level `400 Bad Request` for a missing event ID, proving route reachability.
- [x] Wired NWDAF to the local OAI core.
  - NRF URI: `http://oai-nrf:80`.
  - AMF URI: `http://oai-amf`.
  - SMF URI: `http://oai-smf`.
  - Event notify URI: `http://oai-nwdaf-sbi:8080`.
  - AMF and SMF HTTP versions are set to HTTP/2 in the lab values.
- [x] Verified baseline AMF/SMF event subscriptions.
  - SBI logs showed AMF subscription response `HTTP/2.0 201 Created`.
  - SBI logs showed SMF subscription response from `CreateIndividualSubcription`.
  - SBI stored AMF and SMF notifications in MongoDB.
  - DCCF logs showed successful AMF/SMF event subscriptions over HTTP/2 and received AMF/SMF notifications.
- [x] Added custom DCCF functionality.
  - DCCF can register with NRF.
  - DCCF can subscribe to AMF/SMF event exposure.
  - DCCF exposes `Ndccf_DataManagement`-style endpoints:
    - `/ndccf-datamanagement/v1/analytics`
    - `/ndccf-datamanagement/v1/data`
    - `/ndccf-datamanagement/v1/nf-events`
    - `/ndccf-datamanagement/v1/stats`
    - `/ndccf-datamanagement/v1/subscriptions`
  - DCCF normalizes timestamp differences between AMF Unix timestamps and SMF NTP timestamps.
- [x] Added custom MTLF functionality.
  - MTLF is exposed as an in-cluster service, separate from the Kong route to generated `oai-nwdaf-nbi-ml`.
  - MTLF can register with NRF.
  - MTLF can subscribe to DCCF for training data pushes.
  - MTLF exposes the IDS-relevant model-provision path:
    - `POST /nnwdaf-mlmodelprovision/v1/subscriptions`
    - `DELETE /nnwdaf-mlmodelprovision/v1/subscriptions/{subscriptionId}`
  - `GET /nnwdaf-mlmodelprovision/v1/ml-models`
  - `GET /nnwdaf-mlmodelprovision/v1/ml-models/{modelId}`
  - `GET /nnwdaf-mlmodelprovision/v1/ml-models/{modelId}/manifest`
  - `GET /nnwdaf-mlmodelprovision/v1/ml-models/{modelId}/file`
  - MTLF sends `NnwdafMLModelProvisionNotif` callbacks with `notifCorreId`, `mLModelInfo[].mLFileAddr.mlModelUrl`, and an IDS-local `idsModelManifestUrl` extension.
  - MTLF can seed a dev-only `stub-latest` model with random bytes so IDS/NWDAF subscription, notification, manifest fetch, and file-serving paths can be smoke-tested before real model export exists.
  - MTLF can notify a new subscription about the newest existing model when the dev/test setting is enabled.
  - MTLF has a proprietary training-job API under `/proprietary/v1/training-jobs`.
  - MTLF health/readiness and NRF status endpoints exist.
- [x] Started IDS Workstream 2.3 from the IDS side.
  - IDS now has disabled-by-default `nwdafIntegration` config.
  - IDS can subscribe to MTLF model-ready notifications.
  - IDS exposes `/nids-model-management/v1/model-notifications`.
  - IDS records the latest MTLF model notification and optional metadata fetch status in `/stats`.
  - IDS can optionally forward detection reports to DCCF.
- [x] Added the first NWDAF-side IDS report fallback.
  - DCCF accepts IDS report records at `POST /ndccf-datamanagement/v1/ids-reports`.
  - DCCF lists recent IDS reports with optional region and predicted-class filters at `GET /ndccf-datamanagement/v1/ids-reports`.
  - DCCF `/ndccf-datamanagement/v1/stats` includes the IDS report count.
- [x] Promoted DCCF IDS reports to MongoDB primary storage.
  - Added a DCCF MongoDB report store backed by the regional NWDAF MongoDB.
  - Added unique `reportId`, `region`, and `predictedClass` indexes for IDS report queries.
  - DCCF now stores and lists IDS reports from MongoDB first.
  - SQLite remains the fallback when MongoDB is unavailable, and in-memory storage remains the last lab fallback.
  - Added lazy MongoDB reconnect so DCCF can start before the regional MongoDB pod is immediately selectable and reconnect on the first report/query.
  - DCCF IDS-report list and stats responses expose the active storage backend as `storage`.
- [x] Smoke-tested the IDS/NWDAF bidirectional lab path.
  - Rebuilt and redeployed `ids`, `mtlf`, and `dccf`.
  - MTLF seeded `stub-latest` and exposed it through the model registry API.
  - MTLF notified IDS about `stub-latest` after a steady-state subscription.
  - IDS fetched the stub model manifest.
  - IDS forwarded one detection report to DCCF.
  - DCCF stored and listed the forwarded report.
- [x] Added Option A regional NWDAF support for the Phase 2 IDS architecture.
  - The dev chart supports suffix-aware names, selectors, ConfigMaps, service URLs, and labels.
  - Added regional dev values for:
    - `nwdaf-paris`
    - `nwdaf-lyon`
  - MTLF config now carries `serving_area.region` and `serving_area.tac`.
  - DCCF config now carries `serving_area.region` and `serving_area.tac`.
  - MTLF manifests and `/health` output include serving-area metadata.
  - DCCF `/health`, IDS report intake, and IDS report listing include serving-area metadata.
  - MTLF model-ready notifications retry delivery so transient IDS service readiness during redeploy does not lose the bootstrap notification.
  - Fixed regional MTLF NRF registration by using h2c HTTP/2 prior-knowledge NRF requests and UUID NF instance IDs.
  - Paris MTLF now registers as `22222222-2222-4222-8222-222222222201`.
  - Lyon MTLF now registers as `22222222-2222-4222-8222-222222222202`.
  - Validated Paris IDS subscription to `oai-nwdaf-mtlf-region-paris`, notification for `region-paris-stub-latest`, and manifest fetch with serving area `region-paris` / TAC `000001`.
  - Validated Lyon IDS subscription to `oai-nwdaf-mtlf-region-lyon`, notification for `region-lyon-stub-latest`, and manifest fetch with serving area `region-lyon` / TAC `000002`.
  - Validated Paris IDS report forwarding to `oai-nwdaf-dccf-region-paris`.
  - Validated Lyon IDS report forwarding to `oai-nwdaf-dccf-region-lyon`.
  - Revalidated regional DCCF report persistence after the MongoDB storage change:
    - rebuilt `local/oai-nwdaf-dccf:dev` with image ID prefix `c9f473441ed8`.
    - redeployed `nwdaf-paris` and `nwdaf-lyon` to release revision `8`.
    - Paris DCCF stored and listed `synthetic-mongo-test-v2` with `storage: mongodb`.
    - Lyon DCCF stored and listed `synthetic-mongo-test-v2` with `storage: mongodb`.
  - Option B, a single-release chart with regional MTLF/DCCF subfunctions, is kept as future work only.
- [x] Documented this repository as a custom IDS-oriented NWDAF fork.
  - [`README.md`](./README.md) now identifies this workspace as a custom OAI NWDAF variant for the IDS project.
  - The README separates generated OAI NBI services from the custom Python MTLF and DCCF services.
  - The README documents that the MTLF training-job API is proprietary operational scaffolding, not a 3GPP external interface.
  - The README documents the DCCF IDS-report path as a MongoDB-backed lab compatibility endpoint while a separate ADRF NF remains unimplemented.
- [x] Added the initial IDS model artifact manifest boundary in MTLF.
  - MTLF exposes `GET /nnwdaf-mlmodelprovision/v1/ml-models/{modelId}/manifest`.
  - MTLF exposes `GET /nnwdaf-mlmodelprovision/v1/ml-models/{modelId}/file`.
  - The IDS-facing manifest includes the core runtime fields used by the IDS model artifact contract:
    - `modelVersion`
    - `architecture`
    - `artifactType`
    - `labelMap`
    - `packetSize`
    - `sequenceSize`
    - `checksum`
    - `sourceNf`
    - `sourceNfInstanceId`
    - `sourceUri`
  - The dev-only `stub-latest` model path generates `sha256:` checksum metadata for the random stub model bytes.
  - Real IDS packet-classification exports from `../IDS_NWDAF_DL_Research` are still future work and are now tracked in [`PLAN_NWDAF.md`](./PLAN_NWDAF.md).
- [x] Started IDS research-scenario execution from MTLF.
  - Added Helm-configured MTLF training scenarios:
    - `centralized`
    - `regional`
    - `federated-averaging`
    - `federated-distillation`
  - Set the default regional NWDAF scenario to `regional`.
  - Removed the old GNN forecasting training/inference path from MTLF.
  - Added Helm-selected IDS model architecture config with options:
    - `MLP`
    - `CNN`
    - `RNN`
    - `GRU`
    - `LSTM`
    - `Transformer`
  - MTLF training jobs now reject a request for a scenario different from the one selected when the stack booted.
  - Kept legacy scripts as subprocess targets while the normalized `nwdaf_mtlf_model_training` package is still metadata-only for training.
  - Added `GET /proprietary/v1/training-scenario` for scenario smoke checks.
  - Adapted the NWDAF codebase to the current research workspace name `IDS_NWDAF_DL_Research` and normalized package name `nwdaf_mtlf_model_training`.
  - Vendored `nwdaf_mtlf_model_training` into the MTLF source tree and image.
  - MTLF now loads the normalized scenario registry at boot and exposes the resolved script path, research workspace, and package name from `GET /proprietary/v1/training-scenario`.
- [x] Added shared `OAI_5G_STORAGE` metadata support.
  - Added shared storage chart values and mounts for MTLF, DCCF, and IDS at `/oai-5g-storage`.
  - Added MTLF MongoDB metadata records for files under the shared storage root.
  - Metadata records are stored in the regional NWDAF MongoDB `storage_metadata` collection.
  - Added `GET /proprietary/v1/storage/files` to list shared-storage metadata from MTLF.
  - Stub model files and training output files can be indexed with category, producer NF, region, TAC, training scenario, job ID, model ID, size, and SHA-256.
  - Seeded the shared PVC with lightweight IDS training-code files under `/oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research`.
  - Rebuilt `local/oai-nwdaf-mtlf:dev` successfully with image ID prefix `7439bfab30d9`.
  - Rebuilt `local/oai-nwdaf-mtlf:dev` successfully after the normalized-package integration with image ID prefix `afbb74bb736e`.
- [x] Moved remaining NWDAF tasks out of this progress file.
  - Forward-looking NWDAF workstreams now live in [`PLAN_NWDAF.md`](./PLAN_NWDAF.md).

## Current Caveats

- This repo is now a local IDS-oriented custom NWDAF workspace, not a clean upstream checkout.
- `components/oai-nwdaf-nbi-ml` is generated Go code and still mostly unimplemented for ML model subscriptions.
- `components/oai-nwdaf-mtlf` is the current practical model-provision target for IDS.
- MTLF can select IDS research scenarios by Helm config, but the current scenario targets still call legacy scripts as subprocesses. The normalized `nwdaf_mtlf_model_training` package does not yet contain import-safe training implementations.
- DCCF stores IDS reports in the regional NWDAF MongoDB first, with SQLite and memory fallback. A separate ADRF NF is not implemented.
- IDS can receive MTLF model-ready notifications and fetch manifests, but model-byte fetching, checksum validation, PyTorch artifact loading, and hot-swap remain future work.
- NWDAF SBI has logged attempted PCF subscription timeouts in the dev lab; PCF event exposure is not part of the current IDS/NWDAF baseline.
- Large IDS datasets and result artifacts should stay in `../IDS_NWDAF_DL_Research`, not inside this NWDAF runtime tree.

## Verification History

- NWDAF Helm release `nwdaf` deployed successfully in the local lab during dev-environment validation.
- AMF/SMF subscriptions and notifications were verified from NWDAF SBI and DCCF logs.
- Kong NBI gateway NodePort `30080` reached NBI analytics application logic.
- IDS-side Workstream 2.3 unit tests passed after adding MTLF notification parsing:
  - `python3 -m unittest discover -s IDS/components/oai-ids/tests`: 24 tests passed.
- IDS Helm chart rendered with `nwdafIntegration` disabled by default.

## Useful Commands

Build all NWDAF images:

```bash
oai-dev-env/minikube/scripts/build-nf-image.sh all-nwdaf
```

Redeploy NWDAF:

```bash
oai-dev-env/minikube/scripts/redeploy-stack.sh nwdaf
```

Fast loop for MTLF:

```bash
oai-dev-env/minikube/scripts/build-nf-image.sh mtlf
oai-dev-env/minikube/scripts/redeploy-nf.sh mtlf
kubectl -n oai-5g-core logs deploy/oai-nwdaf-mtlf
```

Fast loop for DCCF:

```bash
oai-dev-env/minikube/scripts/build-nf-image.sh dccf
oai-dev-env/minikube/scripts/redeploy-nf.sh dccf
kubectl -n oai-5g-core logs deploy/oai-nwdaf-dccf
```

## Track B: Parameterised MTLF Training Entry Point (2026-06-30)

The four training procedures are now wired into the MTLF behind a single parameterised entry point, so the MTLF serves real models instead of a stub (reviewer R4-1/R4-2).

- `IDS_NWDAF_DL_Research/mtlf_train.py` runs ONE scenario (`centralized` / `regional` / `federated-averaging` / `federated-distillation`) for ONE architecture and writes a servable `model.pt` (state-dict) + `metrics.json` into `--output-dir`, matching the MTLF `_on_model_ready` contract (it searches `model.pt` / `*.pth`, builds the `Nnwdaf_MLModelProvision` manifest, and notifies subscribed IDS NFs).
- The legacy research scripts `DL_multiclass_federated.py` and `DL_multiclass_Federated_Distillation.py` were made import-safe (module-level dataset loads guarded under `if __name__ == "__main__"`), so their FedAvg/FedDistill drivers can be imported and reused without side effects; direct execution is unchanged.
- `config/mtlf-config.yaml`: `training.script_path` and all four `training_scenario.scripts.*` now point at `mtlf_train.py`, and `pass_output_dir_args` is `true` so the training manager passes `--output-dir` / `--epochs` (scenario + architecture come from `NWDAF_MTLF_SCENARIO` / `NWDAF_MTLF_MODEL_ARCHITECTURE`).
- The MTLF pod has python3 + CPU torch 2.2.2 and sees `mtlf_train.py` + the `MODEL` dir over shared storage; because the pod is CPU-only, the accurate model is trained offline on the A40 and dropped into `/oai-5g-storage/IDS_RELATED_STORAGE/MODEL/...` for the MTLF to serve.

Verification:
- All four procedures produce a valid `model.pt` + `metrics.json` end-to-end (smoke-tested at `--quick`).
- FedAvg-Transformer trained on the OAI-captured dataset: test 96.18% / eval 100% (`../IDS_NWDAF_DL_Research/rebuttal_results/track_b_oai_results.md`).
- Per-round FL latency measured on OAI: ≈5 s/round FedAvg, ≈30 s/round FedDistill.
