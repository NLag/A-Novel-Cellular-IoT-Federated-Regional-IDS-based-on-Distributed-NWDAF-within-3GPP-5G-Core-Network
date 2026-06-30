# NWDAF Development Plan

This file tracks future NWDAF work for the IDS project. Completed checkpoints and runtime observations live in [`PROGRESS_NWDAF.md`](./PROGRESS_NWDAF.md). Current repository usage and component roles live in [`README.md`](./README.md).

## Objective

Evolve this custom OAI NWDAF workspace from the current IDS/NWDAF interaction baseline into a regional model-provision and report-storage layer for the IDS Phase 2 architecture.

The current baseline already has:

- a Helm-managed NWDAF release in the local minikube lab
- custom Python MTLF service for IDS-facing model subscriptions, model metadata, manifests, and file serving
- custom Python DCCF service for AMF/SMF event subscriptions and MongoDB-backed IDS report intake/listing, with SQLite/memory fallback for lab resilience
- IDS subscription and report-forwarding smoke tests using a seeded `stub-latest` model

The remaining work should focus on model artifact correctness, real IDS research-model export, report-storage hardening/export, regional NWDAF behavior, and federated metadata. Federated algorithms should wait until regional IDS/NWDAF separation is validated end to end.

## Workstream NWDAF-1: Documentation And Compatibility Matrix

Purpose: keep the custom fork understandable as it diverges from upstream OAI NWDAF.

- Add a compact compatibility matrix covering:
  - generated Go NBI ML service
  - custom Python MTLF service
  - custom Python DCCF data-management service
  - IDS runtime model client
- For each exposed endpoint, classify it as:
  - 3GPP-aligned interface
  - local lab shim
  - proprietary operational API
  - generated upstream stub
- Document which service IDS should call for each current flow:
  - model subscription
  - model metadata fetch
  - model file fetch
  - IDS report forwarding
  - report retrieval/export
- Keep `README.md` focused on current usage and keep this plan limited to future work.

## Workstream NWDAF-2: Complete IDS Model Artifact Contract

Purpose: make MTLF-published artifacts loadable and verifiable by the IDS runtime.

- Extend MTLF model metadata with the remaining IDS artifact fields:
  - `createdAt`
  - `trainingScenario`
  - `framework`
  - `frameworkVersion`
  - training dataset manifest reference
  - evaluation metric summary
- Ensure real model exports populate all required fields, not only the dev-only `stub-latest` path.
- Keep checksum generation in MTLF and validate that model file bytes match the manifest checksum.
- Keep MTLF metadata scoped to IDS packet-classification artifacts; the old GNN forecasting workflow is no longer part of this component.
- Define supported artifact types explicitly:
  - placeholder/stub artifacts for smoke tests
  - PyTorch state dict
  - TorchScript or another runtime-loadable package if selected later

## Workstream NWDAF-3: Connect MTLF To IDS Research Models

Purpose: publish actual IDS packet-classification models from [`../IDS_NWDAF_DL_Research`](../IDS_NWDAF_DL_Research) through the MTLF registry.

- Current baseline:
  - MTLF can be booted with one IDS research scenario selected by Helm.
  - Scenario keys match the normalized research workspace:
    - `centralized`
    - `regional`
    - `federated-averaging`
    - `federated-distillation`
  - Legacy scripts remain subprocess targets until the normalized package has side-effect-free training entry points.
  - Shared storage is mounted at `/oai-5g-storage`, and files under that root can be indexed in MongoDB.
- Add an export path from `../IDS_NWDAF_DL_Research/nwdaf_mtlf_model_training` into MTLF-managed model storage.
- Start with one IDS packet-classification architecture before exposing the full model matrix.
- Preserve the Contribution 3 defaults unless intentionally changed:
  - packet length `1500`
  - sequence length `256`
  - six-class federated label map
- Keep Contribution 2's eight-class label map separate until the control-plane/IP/non-IP IDS runtime path exists.
- Avoid importing legacy training scripts directly from MTLF if they still load large datasets at module import time.
- Produce a manifest and model file that can be consumed through:
  - `GET /nnwdaf-mlmodelprovision/v1/ml-models/{modelId}/manifest`
  - `GET /nnwdaf-mlmodelprovision/v1/ml-models/{modelId}/file`
- Replace the legacy script subprocess targets with normalized package commands when `nwdaf_mtlf_model_training` contains import-safe training modules.

## Workstream NWDAF-4: Full Model Provision Flow To IDS

Purpose: validate the model-update loop beyond the current stub manifest fetch.

- Validate the full model-update loop:
  - IDS subscribes to MTLF.
  - MTLF accepts the subscription and returns `subscriptionId`.
  - MTLF publishes a model-ready notification to IDS.
  - IDS fetches model metadata from the advertised URL.
  - IDS fetches model bytes from the advertised URL.
  - IDS validates checksum and compatibility.
  - IDS hot-swaps the active runtime model or keeps the previous model on failure.
- Add in-cluster smoke commands for IDS-to-MTLF subscription and model fetch.
- Add failure-mode tests:
  - missing model URL
  - invalid checksum
  - unsupported artifact type
  - model fetch timeout
  - IDS callback unreachable
  - manifest/model mismatch

## Workstream NWDAF-5: Report Storage Hardening And ADRF/DCCF Role

Purpose: harden the current DCCF MongoDB-backed IDS report store and keep the ADRF role explicit.

- Current storage baseline:
  - DCCF uses the regional NWDAF MongoDB as the primary IDS report store.
  - DCCF creates indexes for report ID, region, and predicted class.
  - DCCF falls back to SQLite when MongoDB is unavailable.
  - DCCF keeps an in-memory cache only as the last lab fallback.
- Add persistence hardening for the MongoDB pods if reports must survive Helm redeploys or pod replacement:
  - PVC-backed MongoDB storage
  - backup/export command for regional report collections
  - retention controls for synthetic smoke-test reports
- Define IDS report payload scope:
  - report metadata only by default
  - no raw packet bytes unless a dataset-capture scenario explicitly enables it
- Add report retrieval/export flow for later dataset generation.
- Document ADRF gaps explicitly if a separate ADRF NF is not implemented.

## Workstream NWDAF-6: Regional NWDAF Hardening

Purpose: prepare MTLF/DCCF behavior for one IDS/NWDAF loop per region/TAC before federated learning.

- Completed baseline now lives in the dev environment as Option A:
  - one full NWDAF Helm release per region/TAC
  - `nwdaf-paris` for `region-paris`, TAC `000001`
  - `nwdaf-lyon` for `region-lyon`, TAC `000002`
  - regional MTLF and DCCF services for each IDS region
  - region/TAC metadata in MTLF manifests and DCCF IDS reports
  - regional MTLF NRF registration with UUID NF instance IDs
- Remaining hardening:
  - Add a durable subscription store if MTLF pod restarts should preserve subscriptions.
  - Add MongoDB PVCs if DCCF report records must survive database pod replacement.
  - Add automated regional smoke tests for model notification, manifest fetch, IDS report forwarding, and report filtering.
  - Revisit Option B only if full per-region NWDAF stacks are too heavy for later federated experiments.

## Workstream NWDAF-7: Federated Regional IDS Metadata

Purpose: add federation tracking after regional NWDAF behavior is stable.

- Add regional model metadata for IDS instances:
  - region
  - TAC
  - source NWDAF/MTLF instance
  - training dataset manifest
- Support multiple regional model artifacts in MTLF.
- Add a federated round metadata model:
  - FedAvg weights exchange
  - FedDistill public-dataset logits exchange
  - communication size metrics
  - per-region evaluation metrics
- Prepare for multiple IDS instances consuming different regional models.

## Workstream NWDAF-8: Shared OAI_5G_STORAGE Metadata

Purpose: make model, dataset, report, and federated exchange files discoverable across IDS/NWDAF components.

- Current baseline:
  - MTLF, DCCF, and IDS can mount `OAI_5G_STORAGE` at `/oai-5g-storage` in the dev chart.
  - MTLF can record metadata for files under the shared root into the regional NWDAF MongoDB.
  - Metadata records include storage path, category, producer NF, region, TAC, training scenario, job ID, model ID, file size, and SHA-256.
- Remaining work:
  - Decide whether the dev lab should use a hostPath, PVC, or explicit minikube mount for `OAI_5G_STORAGE`.
  - Add a repeatable bootstrap command to populate `IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research` from the research workspace.
  - Add dataset manifest records for the active dataset split before training starts.
  - Add retention/export policy for generated model and report artifacts.
  - Add a consumer-side IDS model loader that can resolve model artifacts from either MTLF HTTP URLs or the shared storage metadata.

## Near-Term Order

1. Finish the compatibility matrix and endpoint classification.
2. Complete the real IDS model artifact manifest contract.
3. Export one IDS research model from `../IDS_NWDAF_DL_Research` into MTLF storage.
4. Validate IDS model byte fetch, checksum validation, and runtime hot-swap.
5. Harden the completed Option A regional NWDAF deployment and add automated regional smoke tests.
6. Harden MongoDB-backed IDS report storage and export.
7. Add shared-storage bootstrap and metadata validation.
8. Add federated metadata and algorithm-specific exchange tracking.
