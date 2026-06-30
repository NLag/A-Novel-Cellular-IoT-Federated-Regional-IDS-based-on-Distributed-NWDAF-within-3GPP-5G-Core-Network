# IDS Development Progress

Last checked: 2026-06-30 after enabling real PyTorch model loading, live in-NF inference, and a sliding-window alert gate (Track B)

## Current Snapshot

The IDS workspace now has a forward-looking development plan in [`PLAN_IDS.md`](./PLAN_IDS.md), a top-level operating overview in [`README.md`](./README.md), and this checkpoint log.

The active implementation seed is [`components/oai-ids`](./components/oai-ids). It is currently a Python IDS NF prototype focused on 5G integration mechanics:

- HTTP health/readiness/stats endpoints.
- NRF registration and deregistration client.
- UDP listener for duplicated GTP-U traffic.
- GTP-U decapsulation.
- Packet vectorization to fixed-size pure-Python features.
- Deterministic placeholder detector.
- Placeholder model artifact contract and local model registry client.
- Inner IPv4 metadata extraction from duplicated GTP-U payloads.
- Local detection reports with 5G, detector, and packet metadata.
- Observe-only countermeasure stubs for SMF, AMF, UDM, and PCF/SMF policy actions.
- Basic unit tests for GTP-U parsing, placeholder model behavior, and report generation.
- IDS-side NWDAF/MTLF model-update subscription and notification parsing boundary, disabled by default.

The imported AI/deep-learning research workspace is [`../IDS_NWDAF_DL_Research`](../IDS_NWDAF_DL_Research). It contains the Contribution 3 training code, prepared datasets, generated result artifacts, and an initial normalized Python package boundary in `nwdaf_mtlf_model_training/`.

The OAI development environment needed for IDS integration is mostly complete under [`../oai-dev-env/minikube`](../oai-dev-env/minikube):

- OAI Core is Helm-managed.
- NWDAF is Helm-managed and has been runtime-verified.
- PacketRusher is Helm-managed.
- PacketRusher uses shared non-VRF GTP tunnels by default, enabling UE-sourced user-plane traffic for IDS development.
- Helper scripts exist for local image build and targeted NF redeploy.
- `oai-ids` now builds from source as `local/oai-ids:dev` and deploys as Helm release `ids`.
- The deployed IDS pod registers with NRF and reaches `Ready`.
- PCF now builds from source as `local/oai-pcf:dev` and deploys as Helm release `pcf`.
- The dev PCF chart now lives in `../oai-dev-env/minikube/charts/oai-pcf`; the top-level `charts` tree is only reference material for this lab.
- The deployed PCF pod registers with NRF and loads the lab IDS PCC rule.
- PCF keeps `ids-duplication` inactive by default and changes state only through the IDS lifecycle notification endpoint.
- IDS sends an activation notification to PCF during startup and sends a deactivation notification during shutdown before NRF deregistration.
- SMF keeps local PCC/default rules active, probes PCF once at startup to register its IDS callback, and then passively waits for PCF notifications.
- UPF simpleswitch now has an initial PFCP FAR `DUPL` enforcement path that sends a duplicated GTP-U packet to IDS while preserving normal forwarding.

## Done

- [x] Replaced the old IDS plan, which described the generic OAI minikube lab, with an IDS-specific implementation plan.
- [x] Summarized completed OAI dev-lab work relevant to IDS:
  - Helm-managed OAI Core.
  - Helm-managed NWDAF.
  - verified NWDAF subscriptions and notifications.
  - PacketRusher local source build loop.
  - PacketRusher shared gNB tunnel profile.
  - UE-sourced tunnel traffic validation.
- [x] Captured the current IDS component baseline.
- [x] Derived the future IDS roadmap from active docs:
  - Contribution 1: IDS as 5GC NF for user-plane IoT traffic.
  - Contribution 2: CP-aware IDS for IP and non-IP CIoT traffic, with ML/DL deferred during Phase 1.
  - Contribution 3: federated regional IDS coordinated through NWDAF.
- [x] Created a new IDS README.
- [x] Created this progress log.
- [x] Completed Phase 1 workstream 1.1, IDS runtime contract:
  - Added config fields for IDS instance ID, serving area, report storage, countermeasure mode, GTP-U, HTTP, classifier, and NRF.
  - Added structured JSON logs for GTP-U listener start, packet receive/classification, decode errors, report creation, and event subscription creation.
  - Exposed report IDs and latest classification fields through `/stats`.
- [x] Completed Phase 1 workstream 1.2, Helm chart and dev deployment:
  - Added the `oai-ids` Helm chart under `../oai-dev-env/minikube/charts/oai-ids`.
  - Added lab override values in `../oai-dev-env/minikube/values/ids-dev.yaml`.
  - Used the existing custom NF hook `../oai-dev-env/minikube/custom-nfs/oai-ids.env` for build/redeploy integration.
  - Verified `build-nf-image.sh ids` builds `local/oai-ids:dev`.
  - Verified `redeploy-nf.sh ids` installs release `ids` in namespace `oai-5g-core`.
- [x] Completed Phase 1 workstream 1.3, NRF and SBI baseline:
  - Aligned NRF registration with OAI NRF validation by using `nfType: AF` and a stable v4 UUID NF instance ID.
  - Kept IDS identity in the Helm release, service name, runtime `instanceId`, and IDS-specific APIs.
  - Added `/nids-security/v1/reports` and `/nids-event-exposure/v1/subscriptions`.
  - Verified report creation and subscription creation through in-pod curl smoke tests.
  - Improved NRF client error reporting so future curl failures include both stderr and response body.
- [x] Refined Phase 1 workstream 1.4 scope:
  - Replaced the temporary "UPF-side observation or duplication path" framing with the full policy-driven chain from IDS to PCF, PCF to SMF over N7, SMF to UPF over N4/PFCP, and UPF packet duplication to IDS.
  - Split workstream 1.4 into standards/OAI gap audit, IDS traffic influence client, PCF PCC duplication rule support, SMF N7-to-N4 translation, UPF PFCP duplication enforcement, and end-to-end validation.
  - Captured the target behavior from Contribution 1: IDS requests traffic influence, PCF activates or creates a PCC rule, SMF translates it to PDR/FAR state, and UPF duplicates matching traffic using FAR duplicating parameters.
- [x] Started workstreams 1.4.1 through 1.4.3 for IDS-PCF interaction:
  - Audited the running lab and confirmed there is no deployed PCF pod or Helm release yet.
  - Confirmed the current SMF config uses `use_local_pcc_rules: yes`, so it is not consuming PCF PCC decisions in this lab state.
  - Confirmed OAI PCF source implements `Npcf_SMPolicyControl` create/get/update/delete handlers and file-provisioned policy decisions under `/npcf-smpolicycontrol/v1/sm-policies`.
  - Confirmed OAI PCF feature documentation marks N7 as supported but N5/AF input and UpdateNotify as unsupported.
  - Added IDS `trafficInfluence` runtime config and a PCF client in `components/oai-ids/app/pcf.py`.
  - Added IDS support for `disabled`, `observe-only`, `sm-policy-probe`, and `preconfigured-rule` traffic influence modes.
  - Added unit tests for config loading and OAI-compatible SMPolicy context payload construction.
- [x] Added PCF to the minikube lab for workstreams 1.4.1 through 1.4.3:
  - Created the dev PCF chart in `../oai-dev-env/minikube/charts/oai-pcf` from the reference chart.
  - Added minikube custom-NF metadata in `../oai-dev-env/minikube/custom-nfs/oai-pcf.env`.
  - Added lab values in `../oai-dev-env/minikube/values/pcf-dev.yaml`.
  - Patched the PCF chart for standalone rendering, minikube image overrides, rollout nonce annotations, config override support, and mounted local policy files.
  - Added a lab `ids-duplication` PCC rule selected for DNN `oai`.
  - Built `local/oai-pcf:dev` from `../oai-cn5g-fed/component/oai-pcf`.
  - Deployed Helm release `pcf` in namespace `oai-5g-core`.
  - Verified PCF loaded local policy files and registered with NRF.
  - Verified `Npcf_SMPolicyControl` accepts an IDS-originated SM policy probe and returns the `ids-duplication` PCC rule.
  - Enabled IDS `trafficInfluence` in lab values with `mode: sm-policy-probe`.
  - Redeployed IDS and verified startup traffic influence status `accepted`.
- [x] Implemented the first pass of workstreams 1.4.4 through 1.4.6:
  - Added a PCF-side in-memory gate for the `ids-duplication` PCC rule so normal SMPolicy requests do not receive the IDS duplication rule until an IDS-originated probe activates it.
  - Added an SMF opt-in probe gate with `OAI_SMF_IDS_PCF_PROBE_ENABLED`, allowing SMF to contact PCF for the IDS trigger while `use_local_pcc_rules: yes` remains active.
  - Added SMF session fields and environment-driven IDS duplication target settings:
    - `OAI_SMF_IDS_DUPLICATION_HOST`
    - `OAI_SMF_IDS_DUPLICATION_PORT`
    - `OAI_SMF_IDS_DUPLICATION_TEID`
  - Added SMF logic that enables IDS duplication only when the PCF decision contains PCC rule `ids-duplication` and traffic-control data with `traffCorreInd: true`.
  - Kept the normal local PCC/default UPF selection path when the IDS trigger is absent.
  - Added PFCP FAR duplicating parameters during PDU session establishment when the IDS trigger is present.
  - Added UPF simpleswitch support for FAR apply-action `DUPL`, sending the copied packet to the configured IDS GTP-U endpoint while continuing the normal `FORW` path.
  - Added SMF Helm `extraEnv` support and wired the IDS duplication env vars in `oai-dev-env/minikube/values/core-dev.yaml`.
  - Added PCF service discovery config to the OAI core dev chart so SMF can resolve `oai-pcf`.
- [x] Refined the PCF/SMF lifecycle behavior requested after the first duplication-chain build:
  - Changed PCF so `ids-duplication` is inactive by default and is not activated by a plain SMPolicy probe.
  - Added PCF `POST /npcf-smpolicycontrol/v1/ids-traffic-influence` for explicit IDS activate/deactivate notifications.
  - Added PCF notification fan-out to SMF callback associations when IDS traffic influence changes.
  - Changed IDS startup to activate the PCF IDS traffic influence gate before its compatibility SMPolicy probe.
  - Changed IDS shutdown to send an inactive notification to PCF before NRF deregistration.
  - Added SMF startup probing to create the PCF association once, then passively wait at `/npcf-smpolicycontrol/v1/ids-notify`.
  - Added SMF handling for both activation and deactivation notifications, updating IDS duplication state for local PCC handling.
- [x] Completed Phase 1 workstream 1.5, placeholder detection and reporting:
  - Replaced the PyTorch MLP placeholder with a deterministic pure-Python detector.
  - Added `heuristic`, `force-benign`, and `force-malicious` modes for predictable smoke tests.
  - Added configurable packet-size and high-byte-ratio thresholds.
  - Added inner IPv4 source/destination/protocol extraction from duplicated GTP-U payloads.
  - Added UE IP, MCC/MNC, detector reason, feature metadata, and GTP-U peer metadata to detection reports.
  - Kept reports local through the existing in-memory/file-backed report store.
- [x] Completed Phase 1 workstream 1.6, observe-only countermeasure stubs:
  - Added planned countermeasure actions for:
    - SMF PDU session release through `Nids-Nsmf`.
    - AMF UE context release through `Nids-Namf`.
    - UDM deregistration/service restriction through `Nids-Nudm`.
    - PCF/SMF policy update through `Nids-Npcf`/N7/N4.
  - Added explicit config gates for active countermeasures:
    - global `active_enabled`
    - per-action gates for SMF, AMF, UDM, and PCF/SMF actions
  - Kept default behavior as `observe-only`, where malicious reports record/log intended NF actions and never call the target NF.
  - Added report fields for planned countermeasures, status, target NF, interface, service, base URI, gate state, and relevant UE/TEID context.
- [x] Started Phase 2 workstream 2.1, import and normalize research code:
  - Documented the imported research workspace in `../IDS_NWDAF_DL_Research/README.md`.
  - Identified the active research scripts:
    - `IDS_lib.py`
    - `DL_multiclass_centralize.py`
    - `DL_multiclass_federated.py`
    - `DL_multiclass_Federated_Distillation.py`
    - `DL_multiclass_regional_models.py`
  - Captured the large dataset and result-artifact areas that future agents should not deep-scan.
  - Added `../IDS_NWDAF_DL_Research/requirements.txt` with the inferred Python dependencies.
  - Added `../IDS_NWDAF_DL_Research/nwdaf_mtlf_model_training/` as the normalized package boundary.
  - Added side-effect-free experiment constants and a workspace manifest so Phase 2 code can discover legacy scripts and dataset splits without importing `IDS_lib.py` or loading data.
  - Added placeholder package slices for dataset handling, model definitions, training loops, federated logic, and evaluation/reporting.
  - Added a scenario registry and safe CLI for the four main research workflows:
    - centralized model training
    - averaging federated learning
    - federated distillation
    - separate regional model training
- [x] Started Phase 2 workstream 2.2, regional IDS model contract:
  - Added IDS model registry config under `modelRegistry`.
  - Added a model registry client abstraction in `components/oai-ids/app/model_registry.py`.
  - Added model artifact metadata fields for:
    - model version
    - architecture
    - artifact type
    - label map
    - packet size
    - sequence size
    - checksum
    - source NF
    - source NF instance ID
    - source URI
  - Added placeholder artifact loading from config defaults or a local JSON manifest.
  - Added checksum validation for local artifact manifests when an expected checksum is configured.
  - Kept non-placeholder artifact types rejected for now so real PyTorch loading is explicit future work.
  - Added the active model artifact to `/stats` and detection reports.
  - Added startup logging for `ids-model-artifact-loaded`.
- [x] Started Phase 2 workstream 2.3, NWDAF integration:
  - Audited the local OAI NWDAF chart and confirmed the lab exposes NBI analytics, NBI events, NBI ML model provision, SBI, MTLF, and DCCF services.
  - Mapped Contribution 3 roles onto the local OAI NWDAF deployment:
    - NWDAF/MTLF as analytics and model provider.
    - DCCF as the first data coordination and IDS-report fallback surface.
    - ADRF as a planned durable storage role that is not implemented as a separate NF yet.
  - Used the MTLF `Nnwdaf_MLModelProvision` subscription/notification path as the first IDS integration target.
  - Added IDS `nwdafIntegration` runtime config with disabled, observe-only, subscribe, metadata-fetch, and report-forwarding controls.
  - Added an IDS NWDAF model-provision client boundary in `components/oai-ids/app/nwdaf.py`.
  - Added support for building model-update subscription payloads with `notifUri`, `notifCorreId`, `mLModels`, `suppFeat`, and optional expiry.
  - Added `/nids-model-management/v1/model-notifications` so IDS can receive MTLF model-ready notifications.
  - Added optional model metadata fetch from the MTLF model info/manifest URL after notification receipt.
  - Added optional IDS report forwarding to the NWDAF-side DCCF compatibility endpoint.
  - Added `/stats` fields for NWDAF model subscription status, subscription ID, errors, latest received model update, latest metadata fetch, report forwarding status, and forwarded report count.
  - Added MTLF model metadata/manifest support for IDS-facing model discovery.
  - Added a DCCF IDS report endpoint for lab validation while a separate ADRF NF is pending.
  - Promoted DCCF IDS report storage to regional NWDAF MongoDB primary storage, with SQLite and memory fallbacks.
  - Added a dev-only MTLF stub model seed so IDS/NWDAF interaction can be tested before real research model export exists.
  - Enabled IDS `nwdafIntegration` and MTLF stub model seeding in the minikube dev override values for the Workstream 2.3 smoke test.
  - Rebuilt and redeployed `ids`, `mtlf`, and `dccf` in the minikube dev lab.
  - Validated the current bidirectional IDS/NWDAF smoke path:
    - MTLF seeded `stub-latest` at `/models/stub-latest/model.pt`.
    - MTLF exposed `stub-latest` from `GET /nnwdaf-mlmodelprovision/v1/ml-models`.
    - MTLF sent a model-ready notification to IDS after a steady-state subscription.
    - IDS recorded the notification in `/stats` with `modelId=stub-latest`.
    - IDS fetched the `stub-latest` manifest and recorded `lastNwdafModelMetadataFetch.status=fetched`.
    - IDS forwarded one smoke-test detection report to DCCF.
    - DCCF listed the forwarded report and reported `idsReports.total=1`.
  - Revalidated the regional IDS-to-DCCF path after MongoDB became the primary DCCF report store:
    - Paris IDS forwarded report `55173e85-b1bf-4f62-b839-0905cc140b3e` to Paris DCCF.
    - Lyon IDS forwarded report `14b66113-7e93-44c8-823f-37da79a49049` to Lyon DCCF.
    - Both DCCF regional report queries returned `storage: mongodb` and one matching `synthetic-mongo-test-v2` report.
    - Both DCCF `/stats` responses reported `idsReports.storage=mongodb`.
  - Kept model-byte download, checksum validation, PyTorch loading, and active model hot-swap as explicit follow-up work.
  - Added unit tests for NWDAF config loading, subscription URI construction, subscription payload construction, model-ready notification parsing, model metadata URL derivation, and DCCF report payload construction.
- [x] Started Phase 2 workstream 2.4, federated training prototype:
  - Added MTLF boot-time training scenario config with the four normalized research scenario keys:
    - `centralized`
    - `regional`
    - `federated-averaging`
    - `federated-distillation`
  - Set the active regional NWDAF baseline to `regional` by default.
  - Removed the old GNN-oriented MTLF training/inference path.
  - Added Helm-selected IDS model architecture options:
    - `MLP`
    - `CNN`
    - `RNN`
    - `GRU`
    - `LSTM`
    - `Transformer`
  - Kept the legacy research scripts as subprocess targets instead of importing them into MTLF, because the current flat scripts load datasets at module import time.
  - Added `/proprietary/v1/training-scenario` so smoke tests can verify the active MTLF scenario without launching a long training run.
  - Added shared `OAI_5G_STORAGE` mount wiring for MTLF, DCCF, and IDS pods at `/oai-5g-storage`.
  - Added MongoDB-backed shared-storage metadata records for files written under `OAI_5G_STORAGE`.
  - Added `/proprietary/v1/storage/files` on MTLF to list metadata records for shared files in the regional NWDAF MongoDB.

## Planned Phases

1. **IDS NF with 5G network functionality**
   - Deployable `oai-ids` NF.
   - NRF registration.
   - GTP-U traffic ingestion.
   - report/event APIs.
   - placeholder detection.
   - observe-only countermeasure stubs.

2. **Federated IDS architecture with NWDAF**
   - Import research AI/federated-learning code.
   - Define model artifact contract.
   - Integrate model updates and report storage with NWDAF/DCCF/ADRF/MTLF concepts.
   - Support regional IDS instances.

3. **Large-scale IoT traffic and dataset generation**
   - Generate MQTT and CoAP traffic over UE tunnel IPs.
   - Add controlled attack scenarios.
   - Capture and label packets.
   - Export datasets for reproducing the documented experiments at larger scale.

## Current Caveats

- OAI NRF does not accept a custom `IDS` NF type, so the current baseline registers as `AF`.
- PCF is now deployed as a custom minikube NF from `../oai-dev-env/minikube/charts/oai-pcf`, not as part of the base OAI core release.
- SMF still uses local PCC/default forwarding for normal traffic by design; PCF is used only as the IDS duplication trigger.
- OAI PCF currently has N7 SMPolicyControl support, but not upstream N5/AF traffic influence input or standard policy update notification support. The current lab uses a narrow IDS-specific endpoint and notification shim.
- The classifier in `components/oai-ids` is deterministic placeholder logic, not the final AI/ML detector.
- UPF duplication into IDS is implemented only in the simpleswitch/lab path so far; the eBPF/XDP/TC datapath has not been extended.
- The SMF duplication path currently targets PDU session establishment. SMF accepts deactivation notifications, but existing-session N7-to-N4 PFCP modification/removal still needs implementation.
- The PCF IDS activation gate is in memory and resets on PCF restart; a running IDS now periodically refreshes the active lifecycle state so PCF restart is repaired after the refresh interval.
- Runtime PacketRusher-to-UPF-to-IDS duplication validation has passed for session-establishment duplication; existing-session removal is still pending.
- Active countermeasure NF calls are intentionally not implemented yet; current active mode only marks gated actions as `stub-active-not-called`.
- `../IDS_NWDAF_DL_Research` still contains large local datasets and result snapshots. The normalized package must avoid recursive scans and must not import legacy scripts casually because current training scripts load datasets at module import time.
- IDS model registry currently supports local placeholder artifacts only. Remote model-byte download, PyTorch artifact loading, and live hot-swap are future hardening items.
- IDS NWDAF integration can optionally fetch metadata/manifest information after model-ready notifications, but it does not yet validate the artifact checksum or hot-swap the active detector.
- Existing docs sections 03 and 05 were removed from the active documentation flow and were not restored.

## Immediate Next Checkpoints

- Add existing-session N7-to-N4 PFCP modification/removal when PCF deactivates IDS influence.
- Add regression tests for PCF IDS lifecycle state, SMF gate restoration, and PFCP duplicating-parameters encoding.
- Keep existing-session N7-to-N4 PFCP modification/removal as a hardening follow-up.
- Continue Phase 2 by adding remote model fetch/hot-swap support and migrating `IDS_lib.py` functions into the `nwdaf_mtlf_model_training` package.
- Enable an explicit MTLF subscription smoke test once the local NWDAF model-provision service is ready for IDS callbacks.

## Checkpoint: SMF Local PCC Safety Decision

- We will not switch SMF globally from local PCC/default behavior to PCF-driven PCC mode at this stage.
- Reason: the current PacketRusher UE traffic path is working, and flipping SMF policy source could destabilize normal PDU session establishment.
- Target approach:
  - keep `use_local_pcc_rules: yes`
  - add an IDS traffic influence PCC rule to SMF local handling
  - activate the IDS rule only after a specific PCF/N7 IDS trigger is observed
  - continue default rules when the trigger is absent
- Code audit note:
  - `smf_n7::select_pcf()` currently returns no PCF storage when `use_local_pcc_rules` is true.
  - `smf_context.cpp` continues with default rules when SM policy association creation is not successful.
  - This matches the desired safe baseline, but we need to add the gated IDS rule path explicitly.

## Verification: Workstreams 1.1-1.3

- `python3 -m unittest discover -s IDS/components/oai-ids/tests`: passed, 7 tests.
- `python3 -m compileall IDS/components/oai-ids/app`: passed.
- `helm lint oai-dev-env/minikube/charts/oai-ids -f oai-dev-env/minikube/values/ids-dev.yaml`: passed.
- `helm template ids oai-dev-env/minikube/charts/oai-ids -n oai-5g-core -f oai-dev-env/minikube/values/ids-dev.yaml`: rendered successfully.
- `oai-dev-env/minikube/scripts/build-nf-image.sh ids`: built `local/oai-ids:dev`.
- `oai-dev-env/minikube/scripts/redeploy-nf.sh ids`: deployed release `ids`.
- `helm -n oai-5g-core status ids`: `STATUS: deployed`.
- `kubectl -n oai-5g-core get pods -l app.kubernetes.io/name=oai-ids -o wide`: pod `1/1 Running`.
- `kubectl -n oai-5g-core exec deploy/oai-ids -- curl -s http://127.0.0.1:8080/readyz`: `{"ready": true}`.
- `kubectl -n oai-5g-core exec deploy/oai-ids -- curl -s http://127.0.0.1:8080/stats`: returned live counters.
- `kubectl -n oai-5g-core exec deploy/oai-ids -- curl -s http://127.0.0.1:8080/nids-security/v1/reports`: returned stored reports.
- `kubectl -n oai-5g-core exec deploy/oai-ids -- curl -s http://127.0.0.1:8080/nids-event-exposure/v1/subscriptions`: returned stored subscriptions.

## Verification: IDS-PCF Workstream Start

- `python3 -m unittest discover -s IDS/components/oai-ids/tests`: passed, 9 tests.
- `python3 -m compileall IDS/components/oai-ids/app`: passed.
- `helm lint oai-dev-env/minikube/charts/oai-ids -f oai-dev-env/minikube/values/ids-dev.yaml`: passed.
- `helm template ids oai-dev-env/minikube/charts/oai-ids -n oai-5g-core -f oai-dev-env/minikube/values/ids-dev.yaml`: rendered successfully with `trafficInfluence.enabled: false`.
- `oai-dev-env/minikube/scripts/build-nf-image.sh ids`: rebuilt `local/oai-ids:dev`.
- `oai-dev-env/minikube/scripts/redeploy-nf.sh ids`: upgraded release `ids` to revision 2.
- `kubectl -n oai-5g-core get pods -l app.kubernetes.io/name=oai-ids -o wide`: pod `1/1 Running`.
- `kubectl -n oai-5g-core logs deploy/oai-ids --tail=80`: showed `ids-traffic-influence-disabled` and successful NRF registration.
- `kubectl -n oai-5g-core exec deploy/oai-ids -- curl -s http://127.0.0.1:8080/readyz`: `{"ready": true}`.
- `kubectl -n oai-5g-core exec deploy/oai-ids -- curl -s http://127.0.0.1:8080/stats`: returned `trafficInfluenceStatus: disabled`.

## Verification: PCF Lab Deployment and IDS-PCF Interaction

- `helm lint oai-dev-env/minikube/charts/oai-pcf -f oai-dev-env/minikube/values/pcf-dev.yaml`: passed with only the existing non-SemVer chart version warning.
- `helm template pcf oai-dev-env/minikube/charts/oai-pcf -n oai-5g-core -f oai-dev-env/minikube/values/pcf-dev.yaml`: rendered successfully.
- `oai-dev-env/minikube/scripts/build-nf-image.sh pcf`: built `local/oai-pcf:dev`.
- `oai-dev-env/minikube/scripts/redeploy-nf.sh pcf`: installed release `pcf`.
- `kubectl -n oai-5g-core get pods,svc -l app.kubernetes.io/name=oai-pcf -o wide`: PCF pod `1/1 Running`, service `oai-pcf:80`.
- `kubectl -n oai-5g-core logs deploy/oai-pcf --tail=120`: showed policy files loaded, `ids-duplication` parsed, DNN decision for `oai`, and NRF registration successful.
- `kubectl -n oai-5g-core exec deploy/oai-ids -- curl -sS --http2-prior-knowledge -i -X POST http://oai-pcf/npcf-smpolicycontrol/v1/sm-policies ...`: returned `HTTP/2 201` with PCC rule `ids-duplication` and traffic-control decision `ids-traffic-control`.
- `oai-dev-env/minikube/scripts/redeploy-nf.sh ids`: upgraded IDS to revision 3 with traffic influence enabled.
- `kubectl -n oai-5g-core logs deploy/oai-ids --tail=160`: showed `ids-traffic-influence-request-started` and `ids-traffic-influence-request-completed` with status `accepted`.

## Verification: Initial SMF/UPF Duplication Chain Build

- `git diff --check -- <touched PCF/SMF/UPF/chart files>`: passed.
- `helm template core oai-dev-env/minikube/charts/oai-5g-core-dev -n oai-5g-core -f oai-dev-env/minikube/values/core-dev.yaml`: rendered successfully.
- Rendered core chart still has `use_local_pcc_rules: yes`.
- Rendered core chart includes PCF service config for `oai-pcf`.
- Rendered SMF deployment includes:
  - `OAI_SMF_IDS_PCF_PROBE_ENABLED=true`
  - `OAI_SMF_IDS_DUPLICATION_HOST=oai-ids`
  - `OAI_SMF_IDS_DUPLICATION_PORT=2152`
  - `OAI_SMF_IDS_DUPLICATION_TEID=0x1D5`
- `oai-dev-env/minikube/scripts/build-nf-image.sh pcf`: built `local/oai-pcf:dev`.
- `oai-dev-env/minikube/scripts/build-nf-image.sh smf`: built `local/oai-smf:dev`.
- `oai-dev-env/minikube/scripts/build-nf-image.sh upf`: built `local/oai-upf:dev`.

## Verification: Explicit IDS Lifecycle and Passive SMF Callback Build

- `git diff --check -- <touched IDS/PCF/SMF/chart files>`: passed.
- `python3 -m unittest discover -s IDS/components/oai-ids/tests`: passed, 10 tests.
- `helm lint oai-dev-env/minikube/charts/oai-pcf -f oai-dev-env/minikube/values/pcf-dev.yaml`: passed with only the existing non-SemVer chart version warning.
- `helm template pcf oai-dev-env/minikube/charts/oai-pcf -n oai-5g-core -f oai-dev-env/minikube/values/pcf-dev.yaml`: rendered successfully.
- `helm template core oai-dev-env/minikube/charts/oai-5g-core-dev -n oai-5g-core -f oai-dev-env/minikube/values/core-dev.yaml`: rendered successfully.
- `oai-dev-env/minikube/scripts/build-nf-image.sh pcf`: built `local/oai-pcf:dev`.
- `oai-dev-env/minikube/scripts/build-nf-image.sh smf`: built `local/oai-smf:dev`.

## Verification: Workstream 1.4.7 End-to-End Duplication Datapath

- Redeployed PCF, SMF, UPF, IDS, AMF, PacketRusher, and finally NWDAF during the validation sequence.
- Rebuilt IDS after finding the running `local/oai-ids:dev` image was stale; IDS then activated PCF traffic influence successfully.
- Verified PCF notification path:
  - PCF logged IDS traffic influence activation/deactivation from the IDS lifecycle endpoint.
  - PCF sent IDS traffic influence notifications to SMF callback `/npcf-smpolicycontrol/v1/ids-notify`.
  - SMF logged `IDS traffic influence state set to active`.
- Verified SMF policy behavior:
  - SMF kept `use_local_pcc_rules: yes`.
  - Normal UPF selection remained unchanged.
  - SMF added IDS duplication parameters only after the PCF active notification.
- Found and fixed PFCP encoding issue:
  - Initial UPF rejection was `PFCP IE type 5 length 0` on session establishment.
  - Root cause was an empty `Duplicating Parameters` grouped IE encoder.
  - Added destination interface, outer header creation, transport-level marking, and forwarding policy child IEs to the PFCP duplicating-parameters encoder.
  - Rebuilt `local/oai-smf:dev` and redeployed SMF.
- Verified N4 after the fix:
  - UPF accepted `N4_SESSION_ESTABLISHMENT_REQUEST` payloads with duplication enabled.
  - UPF accepted follow-up `N4_SESSION_MODIFICATION_REQUEST`.
  - No repeat of the `PFCP IE type 5 length 0` error after the SMF rebuild.
- Verified PacketRusher UE sessions:
  - Paris shared GTP interface: `gnb41845029`.
  - Lyon shared GTP interface: `gnb3e844b70`.
  - PacketRusher received PDU session accepts and UE IPs, including Paris `12.1.1.100-12.1.1.104` and Lyon `12.1.0.2-12.1.0.6`.
  - PacketRusher used current UPF address `10.244.0.236:2152`.
- Verified UE data transfer and duplication:
  - `kubectl -n oai-5g-core exec deploy/packetrusher-region-paris -- ping -c 2 -I 12.1.1.100 8.8.8.8`: passed, 2 transmitted / 2 received.
  - IDS `/stats` after the ping showed `packetCount: 2`, `decodeErrors: 0`, `lastTeid: 469`, `lastPacketSize: 88`.
  - IDS logs showed two duplicated packets from UPF peer `10.244.0.236:2152` and classification reports in observe-only mode.
- Caveats and follow-ups:
  - Existing-session PFCP removal on IDS deactivation remains future work; new sessions after deactivation follow the inactive gate.
  - NWDAF was redeployed after AMF/SMF restarts to recreate event subscriptions.

## Verification: IDS Lifecycle State Query and Startup Retry Fix

- Fixed PCF IDS lifecycle semantics:
  - PCF still starts with `ids-duplication` inactive because it cannot know whether IDS is already running.
  - `GET /npcf-smpolicycontrol/v1/ids-traffic-influence` now returns the current in-memory IDS traffic influence state without changing it.
  - `POST /npcf-smpolicycontrol/v1/ids-traffic-influence` without an `active` field now also returns the current state instead of silently defaulting to inactive.
- Fixed IDS startup behavior:
  - IDS still waits for NRF registration first.
  - After NRF registration, IDS now keeps retrying PCF traffic influence activation until PCF is online or IDS is stopped.
  - After a successful activation, IDS periodically refreshes the active registration while running so a rolling-update shutdown from an older IDS pod cannot leave PCF inactive permanently.
  - Refresh uses the lightweight IDS lifecycle endpoint only; it does not create a new SMPolicy association on every refresh.
- Fixed SMF startup restoration:
  - SMF startup probing now initializes its local IDS gate from the PCC decision returned by PCF instead of hard-setting the local gate to inactive.
  - If PCF is already active when SMF restarts, the returned `ids-duplication` PCC rule restores the SMF active gate without a manual deactivate/activate cycle.
- Validation:
  - `git diff --check -- <touched PCF/SMF/IDS files>`: passed.
  - `python3 -m unittest discover -s IDS/components/oai-ids/tests`: passed, 10 tests.
  - `oai-dev-env/minikube/scripts/build-nf-image.sh pcf`: built `local/oai-pcf:dev`.
  - `oai-dev-env/minikube/scripts/build-nf-image.sh smf`: built `local/oai-smf:dev`.
  - `oai-dev-env/minikube/scripts/build-nf-image.sh ids`: built `local/oai-ids:dev`.
  - Redeployed PCF, SMF, IDS, and NWDAF in the minikube lab after rebuilds.
  - Verified `GET /npcf-smpolicycontrol/v1/ids-traffic-influence` returns the live PCF state; after IDS refresh it returned `idsTrafficInfluenceActive: true`.
  - Verified PCF restart resets state inactive and the running IDS refresh reactivates it after the refresh interval.
  - Verified PCF refresh logs no longer imply a new activation when the active state is unchanged.

## Verification: Workstream 1.5 Placeholder Detection and Reporting

- Replaced the IDS placeholder detector with deterministic pure-Python logic so Phase 1 does not depend on PyTorch or hidden random model weights.
- Added report metadata for region, MCC/MNC/TAC, TEID, parsed UE IPv4 source, detector reason, GTP-U peer, and placeholder feature values.
- Removed the PyTorch CPU wheel requirement from the IDS component runtime dependencies.
- Validation:
  - `python3 -m unittest discover -s IDS/components/oai-ids/tests`: passed, 14 tests.
  - `python3 -m compileall IDS/components/oai-ids/app`: passed.
  - `git diff --check -- IDS/PLAN_IDS.md IDS/README.md IDS/PROGRESS_IDS.md IDS/components/oai-ids oai-dev-env/minikube/charts/oai-ids/values.yaml oai-dev-env/minikube/values/ids-dev.yaml`: passed.
  - `helm lint oai-dev-env/minikube/charts/oai-ids -f oai-dev-env/minikube/values/ids-dev.yaml`: passed.
  - `helm template ids oai-dev-env/minikube/charts/oai-ids -n oai-5g-core -f oai-dev-env/minikube/values/ids-dev.yaml`: rendered successfully with the deterministic classifier settings.
  - `oai-dev-env/minikube/scripts/build-nf-image.sh ids`: built `local/oai-ids:dev`.
  - `oai-dev-env/minikube/scripts/redeploy-nf.sh ids`: upgraded IDS to revision 9.
  - `kubectl -n oai-5g-core get pods -l app.kubernetes.io/name=oai-ids -o wide`: pod `1/1 Running`.
  - `kubectl -n oai-5g-core logs deploy/oai-ids --tail=80`: showed NRF registration and accepted PCF traffic influence activation.
  - `kubectl -n oai-5g-core exec deploy/oai-ids -- curl -s http://127.0.0.1:8080/readyz`: `{"ready": true}`.
  - `kubectl -n oai-5g-core exec deploy/oai-ids -- curl -s http://127.0.0.1:8080/stats`: returned zero packet counters after redeploy and `trafficInfluenceStatus: accepted`.

## Verification: Workstream 1.6 Observe-Only Countermeasure Stubs

- Added deterministic countermeasure planning for malicious reports.
- Added observe-only log events named `ids-countermeasure-planned`.
- Added active-mode gates without enabling live NF calls.
- Validation:
  - `python3 -m unittest discover -s IDS/components/oai-ids/tests`: passed, 16 tests.
  - `python3 -m compileall IDS/components/oai-ids/app`: passed.
  - `git diff --check -- IDS/components/oai-ids oai-dev-env/minikube/charts/oai-ids/values.yaml oai-dev-env/minikube/values/ids-dev.yaml`: passed.
  - `helm lint oai-dev-env/minikube/charts/oai-ids -f oai-dev-env/minikube/values/ids-dev.yaml`: passed.
  - `helm template ids oai-dev-env/minikube/charts/oai-ids -n oai-5g-core -f oai-dev-env/minikube/values/ids-dev.yaml`: rendered successfully with observe-only countermeasure config.
  - `oai-dev-env/minikube/scripts/build-nf-image.sh ids`: built `local/oai-ids:dev`.
  - `oai-dev-env/minikube/scripts/redeploy-nf.sh ids`: upgraded IDS to revision 10.
  - `kubectl -n oai-5g-core get pods -l app.kubernetes.io/name=oai-ids -o wide`: pod `1/1 Running`.
  - `kubectl -n oai-5g-core exec deploy/oai-ids -- curl -s http://127.0.0.1:8080/readyz`: `{"ready": true}`.
  - `kubectl -n oai-5g-core exec deploy/oai-ids -- curl -s http://127.0.0.1:8080/stats`: returned zero packet counters after redeploy and `trafficInfluenceStatus: accepted`.
  - Posted a malicious smoke report to `/nids-security/v1/reports`; the response included four observe-only planned countermeasures with `called: false`.
  - `kubectl -n oai-5g-core logs deploy/oai-ids --tail=80`: showed four `ids-countermeasure-planned` log events for SMF, AMF, UDM, and PCF/SMF actions.

## Verification: Workstream 2.1 Research-Code Normalization Baseline

- Added the first non-invasive package boundary for the imported Contribution 3 code.
- Kept legacy research scripts in place so existing training commands continue to work.
- Added stable scenario keys for `centralized`, `federated-averaging`, `federated-distillation`, and `regional`.
- Avoided importing `IDS_lib.py` during tests because it imports PyTorch and prints device state at module import time.
- Validation:
  - `python3 -m nwdaf_mtlf_model_training list-scenarios` from `../IDS_NWDAF_DL_Research`: listed the four supported workflows without loading datasets.
  - `python3 -m unittest discover -s tests` from `../IDS_NWDAF_DL_Research`: passed, 5 tests.
  - `python3 -m compileall nwdaf_mtlf_model_training` from `../IDS_NWDAF_DL_Research`: passed.
  - `git diff --check -- IDS/PLAN_IDS.md IDS/PROGRESS_IDS.md IDS/README.md IDS_NWDAF_DL_Research`: passed.

## Verification: Workstream 2.2 Model Artifact Contract Baseline

- Added the IDS-side model artifact metadata and registry client boundary.
- Wired placeholder artifact metadata into runtime stats and detection reports.
- Rendered the IDS Helm values with the `modelRegistry` block.
- Validation:
  - `python3 -m unittest discover -s IDS/components/oai-ids/tests`: passed, 20 tests.
  - `python3 -m compileall IDS/components/oai-ids/app`: passed.
  - `python3 -m unittest discover -s tests` from `../IDS_NWDAF_DL_Research`: passed, 5 tests.
  - `git diff --check -- IDS/components/oai-ids oai-dev-env/minikube/charts/oai-ids/values.yaml oai-dev-env/minikube/values/ids-dev.yaml`: passed.
  - `helm lint oai-dev-env/minikube/charts/oai-ids -f oai-dev-env/minikube/values/ids-dev.yaml`: passed.
  - `helm template ids oai-dev-env/minikube/charts/oai-ids -n oai-5g-core -f oai-dev-env/minikube/values/ids-dev.yaml`: rendered successfully with `modelRegistry.model_version: lab-placeholder-v1`.
  - `oai-dev-env/minikube/scripts/build-nf-image.sh ids`: rebuilt `local/oai-ids:dev`.
  - `oai-dev-env/minikube/scripts/redeploy-nf.sh ids`: upgraded Helm release `ids` and rolled out deployment `oai-ids`.
  - `kubectl -n oai-5g-core get pods -l app.kubernetes.io/name=oai-ids -o wide`: pod `1/1 Running`.
  - `kubectl -n oai-5g-core logs deploy/oai-ids --tail=120`: showed `ids-model-artifact-loaded` for `lab-placeholder-v1` and PCF traffic influence status `accepted`.
  - `kubectl -n oai-5g-core exec deploy/oai-ids -- curl -s http://127.0.0.1:8080/stats`: returned the active `modelArtifact` metadata with `modelVersion: lab-placeholder-v1` and `trafficInfluenceStatus: accepted`.

## Verification: Workstream 3.3 Dataset Capture Baseline

- Added IDS-side dataset capture for duplicated GTP-U packets.
- Added Helm-configured `ids.datasetCapture` values with capture disabled by default.
- Added capture levels:
  - `report-only`: IDS report and packet metadata with packet hashes, no packet hex.
  - `packet-capture`: raw duplicated GTP-U hex and decapsulated inner packet hex in JSONL.
  - `model-ready`: JSONL plus `model_ready.csv` rows for training ingestion, including the `packet_hex` and numeric `label` columns expected by `../IDS_NWDAF_DL_Research`.
- Added shared-storage output path:
  - `/oai-5g-storage/IDS_RELATED_STORAGE/DATASETS/<scenario_id>/<region>/<ids_instance_id>/manifest.json`
  - `/oai-5g-storage/IDS_RELATED_STORAGE/DATASETS/<scenario_id>/<region>/<ids_instance_id>/packets.jsonl`
  - `/oai-5g-storage/IDS_RELATED_STORAGE/DATASETS/<scenario_id>/<region>/<ids_instance_id>/model_ready.csv` when `level: model-ready`
- Added runtime `/stats` fields for capture status, capture path, packet count, and latest captured packet index.
- Preserved dataset metadata in every JSONL record:
  - IDS instance, region, TAC, model version, scenario ID, traffic class, attack label, attack variant, generator metadata, split, numeric label, UE IP, TEID, peer, packet sizes, hashes, IPv4 metadata, detector fields, and report ID.
- Refined model-ready dataset labeling so capture keeps all successfully decapsulated duplicated packets regardless of IDS prediction:
  - `traffic_class`, `attack_label`, and `numeric_label` remain scenario/ground-truth labels.
  - `predicted_class`, `predicted_label`, `predicted_score`, `detector_name`, and `detector_reason` are now written to `model_ready.csv`.
  - Existing legacy `model_ready.csv` files are upgraded to the new header before appending new rows, preserving old rows with blank prediction fields.
- Updated [`README.md`](./README.md) with capture-level behavior and a Helm values example.
- Validation:
  - `python3 -m unittest discover -s tests` from `IDS/components/oai-ids`: passed, 29 tests.
  - `python3 -m compileall app` from `IDS/components/oai-ids`: passed.
  - `helm lint oai-dev-env/minikube/charts/oai-ids -f oai-dev-env/minikube/values/ids-dev.yaml`: passed.
  - `helm template ids oai-dev-env/minikube/charts/oai-ids -n oai-5g-core -f oai-dev-env/minikube/values/ids-dev.yaml`: rendered regional IDS ConfigMaps with `datasetCapture` and the `/oai-5g-storage` shared mount.
  - `git diff --check -- IDS/components/oai-ids oai-dev-env/minikube/charts/oai-ids/values.yaml oai-dev-env/minikube/values/ids-dev.yaml`: passed.
- Not yet deployed in minikube during this checkpoint; deployment should follow the next bounded dataset-capture scenario.

## Verification: Real PyTorch Model Loading, Live Inference, and Alert Gate (Track B, 2026-06-30)

Goal: replace the deterministic placeholder with the real federated model trained on the OAI platform and run it live in the IDS NF (reviewer comments R4-1/R4-2/R4-4/R1-8).

- Added `app/torch_detector.py`: a `TransformerClassifier` copied verbatim from `IDS_lib` (state-dict-compatible) plus a `TorchDetector` that keeps a rolling 256-packet buffer and classifies the latest packet (`build_torch_detector`, `classify`).
- Extended `app/model_registry.py` to support `artifactType: pytorch-state-dict` / `pytorch`: it resolves the model file from the JSON manifest, optionally verifies the model-file checksum, builds the torch detector, and returns it as the `ModelRuntime.detector` (`registry_status: loaded-local-artifact-torch`).
- `app/model.py` `classify_packet` now dispatches to torch detectors (duck-typed via `is_torch`); the placeholder path is unchanged.
- Added a **sliding-window alert gate** (`AlertingConfig` in `app/config.py`; `RuntimeState.evaluate_alert` in `app/main.py`): a notification (NWDAF report + countermeasure) is raised only after `threshold` malicious packets within the last `window` inspected packets, re-armed at `clear_below`. Per-packet classification and dataset capture still run; only the notification is gated. New `/stats` fields `alertsRaised` / `alertActive`. Defaults `window=50, threshold=10, clear_below=3` (Helm `ids.alerting`).
- `docker/Dockerfile.ids`: added CPU-only PyTorch (`torch==2.2.2` from the cpu index) so inference runs in-NF without CUDA.
- `oai-dev-env/minikube/values/ids-dev.yaml`: global `modelRegistry` now points at the served manifest `/oai-5g-storage/IDS_RELATED_STORAGE/MODEL/oai-fedavg-transformer-20260630/ids_model.json` with `artifact_type: pytorch-state-dict`, `architecture: Transformer`, `sequence_size: 256`, and the 6-class `label_map`; an `alerting` block was added.

Validation (live minikube, all five regional IDS):
- Startup logs `ids-model-artifact-loaded` with `architecture=Transformer`, `artifact_type=pytorch-state-dict`, `registry_status=loaded-local-artifact-torch`, `sequence_size=256`.
- A region-nice TCP-SYN attack is classified `torch:tcpsyn` (label 5), score ~0.9999, `predicted_class=malicious`.
- Alert gate: a 15 s / 3546-packet attack produced `alertsRaised=1`, `nwdafReportsForwarded=1` (one notification, not per-packet).
- End-to-end detection latency ≈ a few ms from the first attack packet; single-sequence CPU inference ≈16 ms / 256-packet window; IDS pod RSS ≈138 MB.
- Known limitation: on freshly generated normal traffic some packets are mislabeled (e.g. portscan) due to the small live-capture training set; the alert gate suppresses these isolated per-packet false positives.
- Image rebuilt (`build-nf-image.sh ids`) and redeployed (`redeploy-nf.sh ids`); all five regional deployments rolled out successfully.
