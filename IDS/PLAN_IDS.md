# IDS Development Plan

This plan tracks future IDS work. Completed checkpoints and runtime observations live in [`PROGRESS_IDS.md`](./PROGRESS_IDS.md). Current usage notes live in [`README.md`](./README.md).

## Current Direction

Develop the IDS as a 5G Core Network Function first, with practical 5G integration taking priority over the final AI implementation. Machine-learning and deep-learning behavior should stay as a simple placeholder until the 5G NF interfaces, deployment model, traffic ingestion path, and operational loop are stable.

After the standalone IDS NF is working, extend it into the federated IDS-enabled 5G architecture described in Contribution 3, using NWDAF/DCCF/ADRF/MTLF concepts and the imported research workspace in [`../IDS_NWDAF_DL_Research`](../IDS_NWDAF_DL_Research). Finally, use the OAI quick-deploy environment to generate larger-scale IoT traffic over UEs and produce reproducible datasets.

## Completed Foundation

- The OAI minikube developer environment is now in place under [`../oai-dev-env/minikube`](../oai-dev-env/minikube).
- OAI 5G Core and NWDAF are Helm-managed in namespace `oai-5g-core`.
- The build/redeploy loop exists for source-built NFs through:
  - `build-nf-image.sh`
  - `redeploy-nf.sh`
  - `redeploy-stack.sh`
  - `new-nf.sh`
- NWDAF has been deployed and verified with AMF/SMF subscriptions, notifications, and host-side NBI gateway reachability.
- PacketRusher is built from the local source tree and deployed as a Helm release.
- PacketRusher now defaults to the shared non-VRF tunnel profile:
  - one PacketRusher pod per region
  - one simulated gNB per region
  - one shared `gtp5g` tunnel per region
  - multiple UE /32 addresses assigned to the same region tunnel device
- UE-sourced traffic over PacketRusher GTP links has been verified to the lab traffic server and external ICMP endpoints.
- The initial IDS component skeleton exists in [`components/oai-ids`](./components/oai-ids):
  - HTTP health/readiness/stats endpoints
  - NRF registration and deregistration client
  - GTP-U UDP listener and decapsulation
  - packet vectorization
  - deterministic placeholder detector
  - basic unit tests for GTP-U parsing and model behavior
- Phase 1 workstreams 1.1 through 1.3 are complete:
  - runtime configuration contract
  - structured IDS event logs
  - report/subscription HTTP APIs
  - `oai-ids` Helm chart and `ids-dev.yaml` values
  - local image build through `build-nf-image.sh ids`
  - targeted redeploy through `redeploy-nf.sh ids`
  - NRF registration in the OAI lab using a valid v4 NF instance UUID and an OAI-supported `AF` NF type
- Phase 1 workstream 1.4 has a validated policy-driven duplication baseline:
  - PCF deploys as a custom minikube NF from [`../oai-dev-env/minikube/charts/oai-pcf`](../oai-dev-env/minikube/charts/oai-pcf).
  - IDS sends explicit traffic influence activation/deactivation notifications to PCF and can still run an SMPolicy probe for compatibility checks.
  - PCF exposes the current IDS traffic influence state and can return the lab `ids-duplication` PCC rule.
  - PCF keeps the IDS duplication rule inactive by default and activates/deactivates it only through the IDS lifecycle notification endpoint.
  - SMF keeps local PCC/default forwarding active, probes PCF once at startup to register its callback, and then passively waits for PCF notifications.
  - SMF can add PFCP FAR duplication parameters for the IDS GTP-U endpoint during PDU session establishment.
  - UPF simpleswitch can enforce FAR `DUPL` by emitting a duplicated GTP-U packet to IDS while retaining normal forwarding.
  - PacketRusher UE traffic has been validated to continue normally while UPF duplicates uplink traffic to IDS.
  - Live existing-session PFCP modification/removal remains future hardening.
- Phase 1 workstream 1.5 is complete for the current placeholder baseline:
  - real ML assumptions were removed from the runtime detector path
  - deterministic heuristic, forced-benign, and forced-malicious modes are available for tests and smoke runs
  - reports include IDS instance, timestamp, region, MCC/MNC/TAC, UE IP when parsed from inner IPv4, TEID, predicted class, score, action, detector reason, and packet metadata
  - local in-memory/file report storage remains the active storage path
- Phase 1 workstream 1.6 is complete for observe-only countermeasure stubs:
  - malicious reports produce planned SMF, AMF, UDM, and PCF/SMF countermeasure actions
  - observe-only mode logs intended NF actions without calling target NFs
  - active mode has both global and per-action config gates, but live NF calls remain disabled/stubbed
- Phase 2 workstream 2.1 has an initial research-code normalization baseline:
  - external Contribution 3 Python code is present in [`../IDS_NWDAF_DL_Research`](../IDS_NWDAF_DL_Research)
  - [`../IDS_NWDAF_DL_Research/README.md`](../IDS_NWDAF_DL_Research/README.md) documents scripts, datasets, result artifacts, dependencies, and warnings for large files
  - `requirements.txt` records the inferred Python dependencies
  - `nwdaf_mtlf_model_training/` defines side-effect-free constants, a workspace manifest, and package boundaries for data, models, training, federated logic, and evaluation
  - the four current research scenarios are registered as `centralized`, `federated-averaging`, `federated-distillation`, and `regional`
  - legacy training scripts remain runnable while later refactors move code into the normalized package
- Phase 2 workstream 2.2 has an initial IDS model-artifact contract baseline:
  - IDS has a model registry client boundary for local placeholder artifacts
  - model artifact metadata includes version, architecture, artifact type, label map, packet size, sequence size, checksum, source NF, source NF instance ID, and source URI
  - IDS `/stats`, detection reports, and packet-classification logs include model artifact identity
  - placeholder artifacts can be loaded from config defaults or a local JSON manifest
  - real PyTorch artifact loading and remote NWDAF/DCCF/ADRF fetching remain future work
- Phase 2 workstream 2.3 has an initial NWDAF integration boundary:
  - the local OAI NWDAF chart exposes NBI analytics, NBI events, NBI ML model provision, SBI, MTLF, and DCCF services
  - IDS has disabled-by-default `nwdafIntegration` config
  - IDS can build an MTLF `Nnwdaf_MLModelProvision` subscription request for model-ready notifications
  - IDS exposes `/nids-model-management/v1/model-notifications` for MTLF model-ready callbacks
  - IDS `/stats` records model subscription state and the latest received NWDAF model update
  - IDS can forward regional detection reports to the matching DCCF, and DCCF now stores those reports in regional NWDAF MongoDB first with SQLite/memory fallback
  - model fetch, checksum validation, PyTorch loading, and hot-swap remain future work

## Documentation Inputs

The active research documentation for implementation planning is:

- [`docs/06-contribution-1-5g-iot-ids-for-ciot-as-nf-in-5gc.md`](./docs/06-contribution-1-5g-iot-ids-for-ciot-as-nf-in-5gc.md)
- [`docs/07-contribution-2-ai-ml-based-ids-as-5gc-nf-in-the-control-plane-for-ip-non-ip-ciot-traffic.md`](./docs/07-contribution-2-ai-ml-based-ids-as-5gc-nf-in-the-control-plane-for-ip-non-ip-ciot-traffic.md)
- [`docs/08-contribution-3-a-novel-ciot-federated-regional-ids-based-on-distributed-nwdaf-within-5gc.md`](./docs/08-contribution-3-a-novel-ciot-federated-regional-ids-based-on-distributed-nwdaf-within-5gc.md)

The older French summary and related-work sections are intentionally out of scope for current development.

## Implementation Scope and Traceability

The implementation plan should stay traceable to the three active research contributions while reflecting the current OAI lab constraints:

- Contribution 1 maps to the current user-plane path: IDS as a 5GC NF, NRF registration, PCF/SMF/UPF traffic-duplication control, GTP-U ingestion, local detection, event/report APIs, and planned SMF/AMF/UDM/PCF countermeasures.
- Contribution 2 maps to future control-plane coverage: AMF N1/N2 message duplication for decrypted CIoT user data, raw-packet binary inference, sequence-aware model support, and IP/non-IP traffic labels. This is not implemented yet in the OAI lab and should remain explicit future work until the AMF/NWDAF data source is available or stubbed.
- Contribution 3 maps to Phase 2 and Phase 3: regional IDS instances keyed by serving area/TAC, NWDAF/DCCF/ADRF/MTLF model/report flows, federated training, and larger reproducible IoT datasets.
- The OAI lab registers IDS with NRF as `AF` for compatibility. The project identity remains `oai-ids`, `Nids-*` in the internal API naming, Helm release/service names, report fields, and documentation.
- Any 3GPP service not present in the current OAI codebase should be represented by a narrow compatibility shim or clearly documented stub before adding broader abstractions.
- The runtime IDS NF must not import the research training scripts directly. The only allowed boundary from research code to runtime is an exported model artifact plus metadata.

## Phase 1: IDS NF With 5G Network Functionality

Goal: make `oai-ids` a deployable, observable, 5G-aware NF in the OAI dev lab. The classifier remains intentionally simple.

Workstreams 1.1 through 1.6 are complete for the validated baseline and documented in [`PROGRESS_IDS.md`](./PROGRESS_IDS.md) and [`README.md`](./README.md). Remaining hardening is tracked below instead of keeping the completed workstream detail in this future plan.

### Phase 1 Runtime Contract

The stable Phase 1 runtime shape is:

- Process shape:
  - one Python `oai-ids` process per pod
  - HTTP SBI-like control surface on port `8080`
  - UDP GTP-U listener on port `2152`
  - local configuration loaded from the Helm-rendered IDS YAML
- 5G identity:
  - NRF registration/deregistration through OAI NRF using `nfType: AF`
  - serving-area metadata in runtime config: `region`, `mcc`, `mnc`, `tac`
  - model/report metadata tied to `idsInstanceId`
- Data path:
  - IDS activates the PCF IDS traffic influence gate on startup
  - PCF notifies SMF when the gate changes
  - SMF installs IDS duplication parameters for new PDU sessions when the gate is active
  - UPF simpleswitch duplicates uplink GTP-U packets to the IDS endpoint while preserving normal forwarding
  - IDS decapsulates GTP-U, extracts inner IPv4 metadata when present, vectorizes payload bytes, runs deterministic detection, and writes a report
- API surface:
  - `/healthz`, `/readyz`, `/stats`
  - `/nids-security/v1/reports`
  - `/nids-event-exposure/v1/subscriptions`
- Safety posture:
  - detection remains deterministic placeholder logic
  - countermeasures remain observe-only by default
  - active countermeasure modes are gated and still stubbed

### Phase 1 Hardening: Existing-Session PFCP Updates

- Add the PDU session modification path for sessions that already exist when IDS is activated.
- Translate IDS deactivation notifications into PFCP N4 session modifications that remove the duplication action without disrupting normal forwarding.
- Define the exact session-state owner for existing-session changes:
  - PCF owns the IDS traffic-influence gate
  - SMF owns per-PDU-session duplication state
  - UPF owns FAR enforcement and duplicate emission counters
- Add an SMF reconciliation path after restart:
  - probe PCF for current IDS gate state
  - mark existing local sessions as needing duplication add/remove reconciliation
  - avoid modifying normal PCC/default forwarding when the IDS gate is inactive
- Add a deactivation sequence test:
  - IDS sends inactive lifecycle notification
  - PCF stores inactive state and notifies SMF callbacks
  - SMF sends PFCP modification removing only IDS duplication parameters
  - UPF stops duplicate emission while UE traffic continues normally
- Add focused regression tests for:
  - PCF IDS lifecycle state reads and refreshes
  - SMF IDS gate restoration from PCF startup probe
  - PFCP `Duplicating Parameters` encoding
  - local PCC fallback when IDS influence is inactive
- Add integration smoke commands for:
  - one active PDU session before IDS activation
  - one new PDU session after IDS activation
  - IDS deactivation while both sessions continue forwarding
- Decide whether the eBPF/XDP/TC datapath also needs duplication support or whether the lab standardizes on the simpleswitch path for IDS development.
- Add UPF counters or log lines precise enough to prove duplicate emission without relying only on IDS packet reception.

### Phase 1 Hardening: Operational Readiness

- Add structured startup summaries that include:
  - IDS instance ID and NRF NF instance ID
  - serving area
  - GTP-U listen address
  - traffic influence mode and target PCF URI
  - active model artifact metadata
- Add report retention controls for the file-backed report store:
  - maximum file size or max records
  - startup behavior when the file already exists
  - documented path for exporting reports from the pod
- Add a small synthetic GTP-U sender or test fixture that can run inside the cluster and send one known inner IPv4 packet to IDS.
- Add log correlation fields across IDS, PCF, SMF, and UPF:
  - IDS `reportId`
  - UE IP
  - TEID
  - SUPI/PDU session ID when available
  - duplication policy ID
- Keep the `force-benign` and `force-malicious` modes as deployment smoke tools.

### Phase 1 Validation

- Unit tests pass for config loading, GTP-U parsing, placeholder classification, report generation, and NRF payload construction.
- IDS image builds locally and deploys to minikube.
- IDS registers with NRF and becomes ready.
- IDS can request or activate traffic influence through PCF.
- PCF can expose an IDS duplication PCC rule to SMF.
- SMF keeps local PCC/default behavior for normal traffic and selects the IDS local duplication rule only after the PCF/N7 trigger.
- SMF can translate the gated IDS duplication policy into N4/PFCP PDR/FAR state.
- UPF can enforce FAR duplication and send duplicated GTP-U traffic to IDS without breaking normal UE forwarding.
- `/stats` changes after duplicated packet ingestion.
- IDS can receive at least one duplicated GTP-U packet from the UPF and produce a detection report.
- IDS can run beside the default PacketRusher tunnel profile without destabilizing AMF/SMF/UPF/NWDAF.

## Phase 2: Federated IDS Architecture With NWDAF

Goal: implement the federated IDS-enabled 5G architecture from Contribution 3 after the standalone NF path is stable. This phase is where AI/deep-learning code becomes first-class.

### Phase 2 Target Architecture

The target Phase 2 shape is a regional IDS/NWDAF loop:

- Each IDS instance represents one serving area or TAC group and includes its region/TAC in NRF registration metadata, reports, logs, and model metadata.
- NWDAF/MTLF owns model training and model publication. IDS consumes model metadata and artifacts.
- DCCF/ADRF are treated as coordination and storage points for model artifacts, training outputs, and IDS reports. The current DCCF report path stores IDS reports in regional NWDAF MongoDB; a separate ADRF NF remains future work.
- IDS can keep detecting with the previous active model if model fetch, checksum validation, or load fails.
- Regional model differences are expected and should be visible in `/stats`, reports, and smoke-test output.
- The first real model path should support one architecture and one label map end to end before the full model matrix is exposed.

### Phase 2 Hardening: Finish Research-Code Normalization

- Migrate functional code out of the legacy flat scripts into `../IDS_NWDAF_DL_Research/nwdaf_mtlf_model_training`:
  - dataset handling
  - model definitions
  - training loops
  - federated averaging
  - federated distillation
  - evaluation and reporting
- Preserve the current training scripts as compatibility entry points while converting them to import the package.
- Keep the four scenario entry points explicit:
  - centralized model training
  - averaging federated learning
  - federated distillation
  - separate regional model training
- Remove top-level dataset loading side effects from importable modules.
- Add a run configuration layer for dataset paths, hyperparameters, output directories, and model selection.
- Add typed experiment outputs that can be consumed by artifact export:
  - trained model path
  - model architecture
  - label map
  - packet length
  - sequence length
  - training dataset manifest
  - evaluation metrics
  - checksum
- Add lightweight unit tests that validate package imports do not load datasets or start training.
- Keep runtime IDS code separate from training/research code, with a stable model artifact boundary.

### Phase 2 Hardening: Model Artifact Fetching and Hot Swap

- Add remote fetch clients behind the model registry abstraction:
  - NWDAF model info/fetch
  - DCCF data management fetch
  - ADRF retrieval fallback
- Add real PyTorch artifact loading after the artifact metadata contract is stable.
- Add a model hot-swap path that can replace the active runtime model without restarting IDS.
- Add sequence-buffered inference for models that require packet sequences larger than one packet.
- Preserve placeholder artifacts as a smoke-test and rollback path.

The artifact contract should be expanded from the current placeholder metadata into a runtime-loadable manifest:

- Required artifact fields:
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
  - `createdAt`
  - `trainingScenario`
  - `framework`
  - `frameworkVersion`
- Runtime compatibility checks:
  - artifact type is supported by the IDS runtime
  - packet size matches the vectorizer
  - sequence size is available in the IDS sequence buffer
  - label map can be mapped to report `predictedClass`
  - checksum matches the fetched bytes
- Hot-swap safety:
  - load and validate a candidate model off the packet-processing path
  - atomically replace the active runtime only after validation
  - keep previous model metadata and rollback reason in logs
  - expose active and last-failed model metadata through `/stats`

### Phase 2 Hardening: Sequence Inference

- Add a sequence buffer before real DL inference:
  - configurable keying strategy: global stream, per-region, per-UE IP, per-TEID, or per-direction where available
  - configurable sequence length, initially matching the research default `256`
  - padding/warm-up behavior for new streams
  - maximum buffer count and eviction policy to avoid unbounded memory growth
- Decide how to preserve the research assumption that the model sees a mixed packet stream while still supporting per-UE countermeasures.
- Add report fields for sequence inference:
  - sequence key
  - sequence index or window timestamp
  - model input packet count
  - per-packet classification position
  - warm-up versus full-window inference
- Keep per-packet placeholder inference available for smoke tests and for rollback.

### Workstream 2.3: NWDAF Integration

Current focus: turn the validated metadata/report prototype into a model-byte exchange and validation path.

- Add IDS model-byte fetch from the MTLF `mLFileAddr.mlModelUrl`.
- Add checksum validation for downloaded model bytes.
- Add artifact compatibility checks before accepting an NWDAF-advertised model:
  - `artifactType`
  - `architecture`
  - `packetSize`
  - `sequenceSize`
  - `labelMap`
  - `idsCompatible`
- Keep the current detector unchanged when any model fetch or validation step fails.
- Add `/stats` fields for model-byte fetch, checksum validation, and active/ rejected NWDAF model state.
- Harden IDS report forwarding on the current DCCF MongoDB-backed path:
  - keep SQLite and memory fallback behavior explicit
  - add report export commands for dataset-generation scenarios
  - add PVC/retention policy if reports must survive MongoDB pod replacement
  - revisit a separate ADRF NF after the MongoDB-backed DCCF path is stable
- Keep raw packet bytes out of forwarded reports unless an explicit dataset-capture scenario enables them.

### Workstream 2.4: Federated Training Prototype

- Current baseline:
  - MTLF training jobs are scenario-bound at boot through Helm values.
  - Supported scenario keys match the normalized research workspace:
    - `centralized`
    - `regional`
    - `federated-averaging`
    - `federated-distillation`
  - The active regional NWDAF deployment defaults to `regional`.
  - The model architecture is selected by Helm at boot.
  - Supported architecture keys are:
    - `MLP`
    - `CNN`
    - `RNN`
    - `GRU`
    - `LSTM`
    - `Transformer`
  - MTLF can launch the selected scenario as an isolated subprocess and reject a request for a different scenario.
  - `OAI_5G_STORAGE` is exposed in-cluster at `/oai-5g-storage` for MTLF, DCCF, and IDS pods.
  - Files written under the shared storage root can be recorded in the regional NWDAF MongoDB `storage_metadata` collection.
- Continue moving the implementation out of legacy scripts and into `../IDS_NWDAF_DL_Research/nwdaf_mtlf_model_training`:
  - add side-effect-free dataset loaders
  - add model definitions
  - add local training loops
  - add federated averaging orchestration
  - add federated distillation orchestration
  - add model export utilities
- Implement a local federated training harness matching Contribution 3:
  - multiple regional datasets
  - one public dataset
  - FedAvg
  - FedDistill
  - model evaluation per region
- Start with one small architecture before adding the full model matrix.
- Record communication payload sizes and model accuracy metrics.
- Use the current research defaults as the first target unless deliberately changed:
  - `PACKET_LEN = 1500`
  - `SEQ_LEN = 256`
  - `NUM_REGION = 5`
  - six-class federated label map: normal, CoAP PUT flood, MQTT publish flood, ping flood, port scan, TCP SYN flood
- Keep the Contribution 2 eight-class label map separate until the CP/IP/non-IP runtime path is implemented.
- Add a model export command that writes:
  - model file
  - manifest JSON
  - checksum file
  - evaluation summary
  - optional public-dataset logits for FedDistill
- Store every exported artifact under `OAI_5G_STORAGE/IDS_RELATED_STORAGE` and ensure each file has a MongoDB metadata record:
  - model artifacts under `MODEL`
  - dataset manifests under `DATASET`
  - training reports and evaluation summaries under `REPORT`
  - federated weight/logit exchange files under a dedicated exchange subdirectory
- Track FedAvg and FedDistill separately:
  - FedAvg requires identical architecture across regions and exchanges weights
  - FedDistill can support heterogeneous models and exchanges public-dataset logits
  - communication-size metrics must be reported for both

### Workstream 2.5: Multi-Region Runtime

- Baseline now deployed in the Minikube lab:
  - `region-paris`: TAC `000001`, `oai-ids-region-paris`, `nwdaf-paris`, 100 PacketRusher UEs from MSIN `0000000100`
  - `region-lyon`: TAC `000002`, `oai-ids-region-lyon`, `nwdaf-lyon`, 100 PacketRusher UEs from MSIN `0000000200`
  - `region-marseille`: TAC `000003`, `oai-ids-region-marseille`, `nwdaf-marseille`, 100 PacketRusher UEs from MSIN `0000000300`
  - `region-toulouse`: TAC `000004`, `oai-ids-region-toulouse`, `nwdaf-toulouse`, 100 PacketRusher UEs from MSIN `0000000400`
  - `region-nice`: TAC `000005`, `oai-ids-region-nice`, `nwdaf-nice`, 100 PacketRusher UEs from MSIN `0000000500`
- Keep maintaining multiple IDS instances with region/TAC metadata.
- Keep each IDS connected to the corresponding PacketRusher region traffic path through SMF TAC-based duplication.
- Add model version and region to detection logs.
- Verify each region can load a different model artifact.
- Verify NWDAF can coordinate model update events across IDS instances.
- Extend Helm values to support explicit IDS region profiles:
  - release/name suffix
  - service name
  - serving region
  - TAC
  - GTP-U listen service
  - model artifact URI or region model selector
- Map PacketRusher regions to IDS regions:
  - `region-paris`
  - `region-lyon`
  - `region-marseille`
  - `region-toulouse`
  - `region-nice`
  - one shared PacketRusher gNB tunnel per region remains the default source of UE traffic
- Decide whether traffic duplication routes by:
  - one IDS endpoint per SMF/UPF rule selected from region metadata
  - one IDS endpoint per UPF instance
  - one shared IDS endpoint with report-level region tagging
- Add a multi-region smoke test that proves each IDS receives traffic from its intended UE range and no region silently monopolizes all duplicated traffic.

### Phase 2 Validation

- One IDS instance can fetch or receive a model update from the NWDAF-side prototype.
- Multiple regional IDS instances can run with distinct model metadata.
- Federated training can produce an artifact that the IDS runtime can load.
- Detection reports include model version and region.
- Missing NWDAF APIs are explicitly documented with temporary stubs.

## Phase 3: Large-Scale IoT Traffic and Dataset Generation

Goal: reproduce the IDS documentation scenarios at larger scale in the OAI quick-deploy environment.

### Phase 3 Lab Baseline

The dataset-generation work should start from the current OAI minikube lab rather than the older Open5GS/UERANSIM or Amarisoft assumptions:

- PacketRusher is the UE/gNB simulator.
- The default PacketRusher deployment has two region pods, one gNB per region, and five UEs per region.
- Shared non-VRF `gtp5g` tunnels are the default user-plane path.
- The DNN is `oai`, PLMN is `001/01`, TAC is `000001`, and UE IPs come from static MySQL entries or the SMF dynamic pool.
- PacketRusher tunnel mode requires the minikube node to have `gtp5g`, `sctp`, and related kernel support loaded.
- Large scenarios must be opt-in and must not become the default inner-loop test.

### Workstream 3.1: UE Traffic Generation

- Use PacketRusher shared gNB tunnels as the default UE data path.
- Bind traffic generators to UE source IPs where possible.
- Implement or integrate generators for:
  - MQTT publishers
  - MQTT subscribers
  - CoAP POST clients
  - CoAP GET clients
  - benign periodic IoT profiles
  - attack profiles
- Start with a small deterministic scenario, then scale UE count and client count.
- Add generator placement options:
  - inside PacketRusher pods using UE source addresses when practical
  - separate traffic-generator pods with policy routing through UE tunnel interfaces if needed
  - host-side generator only for debugging, not for canonical dataset generation
- Add service targets in the lab:
  - MQTT broker
  - CoAP server
  - HTTP target for SQLmap-like traffic
  - ICMP/TCP target using `oai-traffic-server` where possible
- Record generator metadata for every scenario:
  - region
  - UE IMSI or source IP
  - protocol
  - profile parameters
  - attack tool and command
  - start/stop timestamps

### Workstream 3.2: Attack Scenarios

- Reproduce the documentation attack classes in stages:
  - MQTT publish flood
  - MQTT SlowITe-like behavior
  - CoAP PUT flood
  - ICMP flood
  - TCP SYN flood
  - random-source TCP SYN flood
  - port scan
  - SQLmap-like traffic if an HTTP target is available
- Keep attack generation controlled and isolated to the minikube lab network.
- Split attack support into three levels:
  - smoke: one benign flow and one short attack flow
  - training: enough samples for model training/export
  - evaluation: independently generated profiles and attack variants
- Add variant attacks for generalization testing:
  - LAND-style ping flood where supported
  - short port scan instead of full port scan
  - spoofed/random-source TCP SYN flood where the lab network permits it
- Add safety controls:
  - hard duration limits
  - packet-rate limits
  - namespace-only targets
  - clear teardown commands

### Workstream 3.3: Dataset Capture and Labeling

Completed baseline is tracked in [`PROGRESS_IDS.md`](./PROGRESS_IDS.md): IDS now has Helm-configured dataset capture that writes `manifest.json`, `packets.jsonl`, and optional `model_ready.csv` under `/oai-5g-storage/IDS_RELATED_STORAGE/DATASETS`.

Remaining work:

- Add scenario-runner control so benign and attack windows set `scenario_id`, `traffic_class`, `attack_label`, `attack_variant`, `split`, and `numeric_label` automatically at capture boundaries.
- Preserve PacketRusher UE identifiers and traffic-generator process/profile IDs in capture records instead of only the generator-level metadata.
- Add capture-window start/end timestamps to the manifest and define deterministic labeling rules for mixed benign/attack boundary windows.
- Add optional parquet export after the first CSV ingestion path is validated with `../IDS_NWDAF_DL_Research`.
- Add NWDAF MongoDB metadata records for IDS dataset files written under `OAI_5G_STORAGE` so DCCF/MTLF can discover datasets without scanning the filesystem.
- Add end-to-end validation that:
  - enables `datasetCapture.level=model-ready`
  - runs IoT and attacker generators
  - confirms IDS writes shared-storage files
  - confirms generated CSV can be loaded by the normalized training package

### Workstream 3.4: CI/CD Scenario Runner

- Add a quick-deploy scenario runner that can:
  - reset or reuse minikube
  - deploy core/NWDAF/PacketRusher/IDS
  - start traffic generators
  - start attack generators
  - collect IDS reports and packet captures
  - export dataset artifacts
- Keep small smoke scenarios fast enough for regular development.
- Keep large dataset scenarios explicit and opt-in.
- Provide at least three scenario presets:
  - `smoke`: one region, one UE, one benign flow, one short attack
  - `regional-smoke`: Paris and Lyon, distinct benign profiles, IDS reports from both regions
  - `dataset-small`: controlled benign and attack windows with exported model-ready data
- Add preflight checks:
  - minikube profile running
  - required local images present
  - Helm releases healthy
  - PacketRusher shared tunnels present
  - IDS ready and NRF-registered
  - PCF/SMF/UPF duplication chain active
- Add artifact collection:
  - IDS reports
  - IDS/PCF/SMF/UPF/PacketRusher logs
  - packet captures
  - scenario manifest
  - generated dataset files

### Phase 3 Validation

- Small scenario generates labeled benign and attack traffic through UE tunnel IPs.
- IDS receives traffic and emits reports during the scenario.
- Dataset export includes raw bytes, labels, UE metadata, and scenario metadata.
- Large scenario can be started from a documented command without manual chart edits.

## Cross-Cutting Requirements

- Keep 5G integration and AI training loosely coupled.
- Prefer explicit placeholder behavior over partially hidden ML behavior during Phase 1.
- Preserve the current OAI dev lab as the integration target.
- Track every completed checkpoint in [`PROGRESS_IDS.md`](./PROGRESS_IDS.md).
- Keep all large datasets and generated results out of the runtime IDS tree.
- Avoid recursive scans over `../IDS_NWDAF_DL_Research/datasets`, `result*`, `TA_df`, and `TA_eval_df` during normal development.
- Every new runtime interface needs:
  - config fields
  - unit tests
  - startup log fields
  - README smoke commands
  - progress-log checkpoint once validated
- Every new lab integration needs:
  - Helm values
  - a render/lint check
  - a minikube smoke test
  - rollback notes if it changes PCF/SMF/UPF behavior
- Countermeasure work must remain observe-only until the exact target NF request bodies, authorization assumptions, and failure modes are documented.
- Keep operational instructions in [`README.md`](./README.md).
- Do not re-add removed documentation sections unless explicitly requested.

## Immediate Next Steps

1. Add the existing-session N7-to-N4 modification/removal path so PCF deactivation clears IDS duplication from already-established PFCP sessions.
2. Add focused regression tests for PFCP `Duplicating Parameters` encoding, PCF IDS lifecycle state, and SMF IDS gate selection.
3. Continue Phase 2 by exporting one real research model artifact, loading it behind the IDS model-registry boundary, and documenting the first NWDAF-side model-update stub.
