# Custom OAI NWDAF for IDS Development

This repository is a custom NWDAF workspace used by the IDS project in this checkout. It started from the OpenAirInterface `oai-cn5g-nwdaf` codebase, but the current local purpose is narrower and more practical: provide the NWDAF, DCCF, and MTLF pieces needed for an IDS-as-5GC-NF architecture.

The IDS roadmap is tracked in [`../IDS/PLAN_IDS.md`](../IDS/PLAN_IDS.md). NWDAF-specific completed work is tracked in [`PROGRESS_NWDAF.md`](./PROGRESS_NWDAF.md), and remaining NWDAF work is tracked in [`PLAN_NWDAF.md`](./PLAN_NWDAF.md).

## Current Role

The NWDAF in this tree supports the IDS Phase 2 direction:

- collect AMF/SMF events and protocol data through the NWDAF SBI/DCCF path
- expose NWDAF NBI analytics, events, and ML model provision services
- provide an MTLF model-provision service for IDS model-update subscriptions
- eventually train, store, publish, and serve IDS model artifacts produced from the research code in [`../IDS_NWDAF_DL_Research`](../IDS_NWDAF_DL_Research)
- run as the `nwdaf` Helm release in the local minikube OAI lab under [`../oai-dev-env/minikube`](../oai-dev-env/minikube)

The IDS runtime currently consumes only the first narrow integration point: MTLF-style model-ready notifications containing `mLModelInfo[].mLFileAddr.mlModelUrl`. Fetching and loading the advertised IDS model is still future work.

## Component Layout

Core components:

- [`components/oai-nwdaf-engine`](./components/oai-nwdaf-engine): analytics engine used by NBI analytics.
- [`components/oai-nwdaf-nbi-analytics`](./components/oai-nwdaf-nbi-analytics): generated Go `Nnwdaf_AnalyticsInfo` service with custom engine calls for network performance, UE communication, and UE mobility.
- [`components/oai-nwdaf-nbi-events`](./components/oai-nwdaf-nbi-events): generated Go `Nnwdaf_EventsSubscription` service.
- [`components/oai-nwdaf-nbi-ml`](./components/oai-nwdaf-nbi-ml): generated Go `Nnwdaf_MLModelProvision` service. The generated handlers are still mostly stubs and are not the current IDS model-provision target.
- [`components/oai-nwdaf-sbi`](./components/oai-nwdaf-sbi): southbound service that subscribes to AMF/SMF events, stores notifications in MongoDB, and has a DCCF client boundary.
- [`components/oai-nwdaf-dccf`](./components/oai-nwdaf-dccf): custom Python DCCF service with NRF registration, AMF/SMF notification ingestion, data/analytics endpoints, subscription management, and MongoDB-backed IDS report intake/listing with SQLite and memory fallbacks.
- [`components/oai-nwdaf-mtlf`](./components/oai-nwdaf-mtlf): custom Python MTLF service implementing the practical IDS-facing `Nnwdaf_MLModelProvision` subscription/notification/model-metadata/model-file path, boot-time IDS training scenario selection, and MongoDB metadata indexing for shared-storage files.

Deployment-related files:

- [`deployment`](./deployment): original Kubernetes manifests.
- [`docker-compose`](./docker-compose): original compose deployment material.
- [`../oai-dev-env/minikube/charts/oai-nwdaf-dev`](../oai-dev-env/minikube/charts/oai-nwdaf-dev): active Helm chart used by this IDS dev lab.

## IDS Integration Baseline

The active minikube deployment contains:

- MongoDB database
- Kong NBI gateway
- NWDAF engine
- NBI analytics
- NBI events
- NBI ML
- SBI
- MTLF
- DCCF

The gateway routes are:

- `/nnwdaf-analyticsinfo/v1/analytics`
- `/nnwdaf-eventssubscription/v1`
- `/nnwdaf-mlmodelprovision/v1` routed to the generated Go `oai-nwdaf-nbi-ml` service

The IDS-facing model-provision path is currently implemented by `components/oai-nwdaf-mtlf` and is reached in-cluster through `oai-nwdaf-mtlf-service:8082`, not through the Kong NBI gateway:

- `POST /nnwdaf-mlmodelprovision/v1/subscriptions`
- `DELETE /nnwdaf-mlmodelprovision/v1/subscriptions/{subscriptionId}`
- `GET /nnwdaf-mlmodelprovision/v1/ml-models`
- `GET /nnwdaf-mlmodelprovision/v1/ml-models/{modelId}`
- `GET /nnwdaf-mlmodelprovision/v1/ml-models/{modelId}/manifest`
- `GET /nnwdaf-mlmodelprovision/v1/ml-models/{modelId}/file`
- `POST /proprietary/v1/training-jobs`

The proprietary training-job API is operational scaffolding, not a 3GPP-standard external interface.

For the development lab, MTLF can seed a `stub-latest` model containing random bytes and immediately notify a new IDS subscription about the newest model. This is only for Workstream 2.3 interaction testing before the real IDS model export from `../IDS_NWDAF_DL_Research` is available.

MTLF training jobs are scenario-bound at boot through Helm values. The supported IDS research scenario keys match the normalized workspace in `../IDS_NWDAF_DL_Research/nwdaf_mtlf_model_training`:

- `centralized`
- `regional`
- `federated-averaging`
- `federated-distillation`

The current chart defaults to `regional` for the Option A regional NWDAF deployment. The legacy flat scripts are still executed as subprocess targets; they should be replaced by import-safe `nwdaf_mtlf_model_training` package entry points as that package is completed.

The IDS report path is currently implemented by `components/oai-nwdaf-dccf` and is reached in-cluster through `oai-nwdaf-dccf:8081`:

- `POST /ndccf-datamanagement/v1/ids-reports`
- `GET /ndccf-datamanagement/v1/ids-reports`

This report path is a lab compatibility endpoint backed primarily by the NWDAF MongoDB. DCCF falls back to SQLite, then memory, if MongoDB is unavailable. A separate ADRF-like storage service is still not implemented.

`OAI_5G_STORAGE` is the shared artifact space for this lab. The Helm chart mounts it into MTLF, DCCF, and IDS at `/oai-5g-storage`. MTLF records metadata for files under that root in the regional NWDAF MongoDB `storage_metadata` collection.

## Dev Lab Commands

Build NWDAF images into minikube:

```bash
oai-dev-env/minikube/scripts/build-nf-image.sh all-nwdaf
```

Redeploy NWDAF:

```bash
oai-dev-env/minikube/scripts/redeploy-stack.sh nwdaf
```

Fast loop for one NWDAF component:

```bash
oai-dev-env/minikube/scripts/build-nf-image.sh mtlf
oai-dev-env/minikube/scripts/redeploy-nf.sh mtlf
```

Check the release:

```bash
helm -n oai-5g-core status nwdaf
kubectl -n oai-5g-core get pods -l app.kubernetes.io/instance=nwdaf
kubectl -n oai-5g-core logs deploy/oai-nwdaf-mtlf
kubectl -n oai-5g-core logs deploy/oai-nwdaf-dccf
```

Host-side NBI gateway smoke check:

```bash
curl -H 'Host: oai-nwdaf-nbi-gateway' \
  "http://$(minikube -p oai-dev ip):30080/nnwdaf-analyticsinfo/v1/analytics"
```

## Current Caveats

- This is not a clean upstream OAI NWDAF checkout anymore; it is an IDS-oriented local fork/workspace.
- The Go `oai-nwdaf-nbi-ml` service is generated and still mostly returns `501 Not Implemented` for subscription handlers.
- The Python MTLF is the current practical model-provision service for IDS integration.
- MTLF training is scoped to IDS packet-classification scenarios from `../IDS_NWDAF_DL_Research`; the current implementation still uses legacy scripts as subprocess targets until normalized package entry points are available.
- DCCF and MTLF register as NWDAF-type functions for compatibility with the local lab.
- ADRF behavior is not implemented as a separate NF yet; storage is currently MongoDB/DCCF/MTLF-local depending on the path.
- IDS metadata fetching and report forwarding are implemented as disabled-by-default Phase 2 integration switches. Model-byte download, checksum validation, PyTorch artifact loading, and runtime hot-swap are still planned Phase 2 work.

## Provenance And License

The base project is OpenAirInterface CN5G NWDAF and remains under the OAI Public License V1.1. See [`LICENSE`](./LICENSE). Local changes should keep the OAI license headers intact where present and clearly document IDS-specific deviations.
