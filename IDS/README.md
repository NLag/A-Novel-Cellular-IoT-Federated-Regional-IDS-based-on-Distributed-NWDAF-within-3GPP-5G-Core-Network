# IDS Development Workspace

This directory contains the IDS research documentation and the first implementation seed for an OAI-compatible IDS Network Function.

## Layout

- [`docs`](./docs): simplified Markdown export of the IDS thesis/research documentation.
- [`components/oai-ids`](./components/oai-ids): current IDS NF prototype.
- [`../IDS_NWDAF_DL_Research`](../IDS_NWDAF_DL_Research): imported AI/deep-learning and federated-learning research workspace for Phase 2.
- [`PLAN_IDS.md`](./PLAN_IDS.md): forward-looking implementation plan.
- [`PROGRESS_IDS.md`](./PROGRESS_IDS.md): checkpoint log and runtime observations.

## Current Implementation Baseline

The current `oai-ids` component is a Python NF prototype. It is intentionally focused on 5G integration mechanics first, not final IDS intelligence.

Implemented seed behavior:

- HTTP endpoints:
  - `/healthz`
  - `/readyz`
  - `/stats`
  - `/nids-security/v1/reports`
  - `/nids-event-exposure/v1/subscriptions`
  - `/nids-model-management/v1/model-notifications`
- NRF registration and deregistration client.
- UDP listener for duplicated GTP-U traffic.
- GTP-U decapsulation.
- Packet vectorization to fixed-size pure-Python features.
- Deterministic placeholder detector with heuristic, forced-benign, and forced-malicious modes.
- Placeholder model artifact contract and local model registry client.
- IDS-side NWDAF/MTLF model-update subscription boundary, disabled by default.
- Inner IPv4 metadata extraction from duplicated GTP-U payloads.
- Observe-only countermeasure stubs for SMF, AMF, UDM, and PCF/SMF policy actions.
- Local report store and simple event subscription store.
- Unit tests for config loading, NRF payload construction, GTP-U decoding, and model behavior.

The placeholder detector is not the final IDS model. It exists so the 5G runtime path can be developed and tested before adding the full machine-learning and federated-learning stack.

Current detection reports include the report ID, IDS instance ID, timestamp, region, MCC/MNC/TAC, TEID, UE IP when parsed from the inner IPv4 packet, predicted class, score, action, detector reason, model artifact metadata, GTP-U/feature metadata, and any planned countermeasure actions.

The model artifact contract currently supports placeholder artifacts from config defaults or a local JSON manifest. Each artifact records model version, architecture, artifact type, label map, packet size, sequence size, checksum, source NF, source NF instance ID, and source URI. Real PyTorch loading and runtime hot-swap are planned Phase 2 follow-ups.

The NWDAF integration boundary now covers both directions for the first Workstream 2.3 prototype. IDS can build a TS 29.520-style `Nnwdaf_MLModelProvision` subscription request, receive MTLF notifications containing `mLModelInfo[].mLFileAddr.mlModelUrl`, optionally fetch the advertised metadata/manifest, and optionally forward detection reports to the NWDAF-side DCCF compatibility endpoint. These paths are disabled by default in Helm values. Model-byte download, checksum validation, artifact compatibility enforcement, PyTorch loading, and active detector hot-swap remain planned Phase 2 hardening.

The minikube dev override enables this integration for smoke testing and pairs it with an MTLF `stub-latest` random-byte model when no real research model has been exported yet.

## Dataset Capture

IDS can optionally persist duplicated GTP-U traffic into the shared storage mount at `/oai-5g-storage`. In the minikube lab this maps back to [`../OAI_5G_STORAGE`](../OAI_5G_STORAGE) when the minikube mount is running.

Captured files are written under:

```text
/oai-5g-storage/IDS_RELATED_STORAGE/DATASETS/<scenario_id>/<region>/<ids_instance_id>/
```

Each capture directory contains `manifest.json` and `packets.jsonl`. When `level: model-ready` is selected, IDS also writes `model_ready.csv` with `packet_hex`, numeric ground-truth `label`/`numeric_label`, IDS `predicted_class`/`predicted_label`, predicted score, detector reason, split, sequence, UE IP, TEID, region, TAC, and scenario metadata.

The Helm value block is `ids.datasetCapture`:

```yaml
ids:
  datasetCapture:
    enabled: true
    level: model-ready
    scenario_id: smoke-benign-paris-001
    traffic_class: normal
    attack_label: benign
    attack_variant: ""
    generator: IoT_Simulate
    generator_metadata:
      min_devices: 2
      max_devices: 2
      message_count: 3
    sequence_size: 200
    split: train
    numeric_label: 0
```

Supported levels:

- `report-only`: writes IDS report and packet metadata plus packet hashes, without packet hex.
- `packet-capture`: writes raw duplicated GTP-U hex and decapsulated inner packet hex in `packets.jsonl`.
- `model-ready`: writes `packets.jsonl` plus `model_ready.csv` for `../IDS_NWDAF_DL_Research` ingestion.

Capture does not filter out packets by IDS prediction. The scenario fields (`traffic_class`, `attack_label`, and `numeric_label`) describe the capture window's ground-truth label, while `predicted_class`, `predicted_label`, and `predicted_score` preserve how the active IDS model classified each packet. This keeps normal/benign traffic and packets predicted as malicious in the same bounded capture when the duplicated traffic contains both.

Keep capture disabled for normal long-running lab use unless a bounded dataset scenario is running.

## Development Direction

The work is split into three phases:

1. Build the IDS as a deployable 5G Core NF with practical 5G network behavior:
   - Helm deployment
   - NRF registration
   - GTP-U packet ingestion
   - event/report APIs
   - placeholder detection
   - observe-only countermeasure stubs
2. Extend the architecture with NWDAF-supported federated IDS behavior:
   - imported research workspace in `../IDS_NWDAF_DL_Research`
   - normalized package boundary for training code
   - model update flow
   - NWDAF/DCCF/ADRF/MTLF integration points
   - regional IDS instances
   - real AI/deep-learning code from the research implementation
3. Generate larger-scale IoT traffic over UE tunnels in the OAI dev lab:
   - MQTT and CoAP traffic generators
   - attack generators
   - packet capture and labeling
   - reproducible dataset export
   - CI/CD-friendly scenario runner

See [`PLAN_IDS.md`](./PLAN_IDS.md) for the detailed workstreams.

## Documentation Inputs

The active docs for implementation planning are:

- [`docs/06-contribution-1-5g-iot-ids-for-ciot-as-nf-in-5gc.md`](./docs/06-contribution-1-5g-iot-ids-for-ciot-as-nf-in-5gc.md)
- [`docs/07-contribution-2-ai-ml-based-ids-as-5gc-nf-in-the-control-plane-for-ip-non-ip-ciot-traffic.md`](./docs/07-contribution-2-ai-ml-based-ids-as-5gc-nf-in-the-control-plane-for-ip-non-ip-ciot-traffic.md)
- [`docs/08-contribution-3-a-novel-ciot-federated-regional-ids-based-on-distributed-nwdaf-within-5gc.md`](./docs/08-contribution-3-a-novel-ciot-federated-regional-ids-based-on-distributed-nwdaf-within-5gc.md)

The older French summary and related-work sections were removed from the active documentation index and are not part of the current implementation plan.

## OAI Dev Lab Dependency

IDS development targets the existing minikube lab under [`../oai-dev-env/minikube`](../oai-dev-env/minikube).

Relevant completed lab capabilities:

- OAI 5G Core and NWDAF are deployed by Helm in namespace `oai-5g-core`.
- NWDAF AMF/SMF subscriptions and notifications have been verified.
- The OAI NWDAF chart exposes NBI analytics, NBI events, NBI ML model provision, SBI, MTLF, and DCCF services. The first IDS integration target is the MTLF `Nnwdaf_MLModelProvision` subscription/notification path.
- PCF is deployed as a custom minikube NF from [`../oai-dev-env/minikube/charts/oai-pcf`](../oai-dev-env/minikube/charts/oai-pcf). The top-level `charts` copy is reference material only for this lab.
- PCF loads a lab `ids-duplication` PCC rule and returns it from `Npcf_SMPolicyControl`.
- PCF gates the `ids-duplication` rule as inactive by default. IDS activates it through `POST /npcf-smpolicycontrol/v1/ids-traffic-influence` on startup, periodically refreshes that active registration while running, and deactivates it through the same endpoint on shutdown. `GET /npcf-smpolicycontrol/v1/ids-traffic-influence` returns the current gate state without changing it.
- The policy-driven duplication chain has been validated for new PDU sessions: IDS activates PCF, PCF notifies SMF, SMF installs PFCP duplication parameters, UPF duplicates uplink GTP-U to IDS, and normal UE traffic continues.
- PacketRusher is built from local source and deployed by Helm.
- PacketRusher now defaults to shared non-VRF GTP tunnels, so UE-sourced data traffic is available for IDS testing.
- Build/redeploy helper scripts already support the local dev loop for OAI NFs.

SMF policy safety note: the lab keeps SMF on local PCC/default behavior. SMF probes PCF once at startup to register its IDS notification callback and initializes its IDS gate from the PCF decision, then passively waits for PCF notifications at `/npcf-smpolicycontrol/v1/ids-notify`. PCF is used only as the IDS duplication trigger, so normal PacketRusher UE traffic remains on the current path. When the trigger is active for a new PDU session, SMF adds PFCP FAR duplication parameters toward the IDS endpoint while retaining normal forwarding.

Current IDS duplication lab defaults are set in [`../oai-dev-env/minikube/values/core-dev.yaml`](../oai-dev-env/minikube/values/core-dev.yaml):

- `OAI_SMF_IDS_PCF_PROBE_ENABLED=true`
- `OAI_SMF_IDS_DUPLICATION_HOST=oai-ids`
- `OAI_SMF_IDS_DUPLICATION_PORT=2152`
- `OAI_SMF_IDS_DUPLICATION_TEID=0x1D5`

The UPF duplication enforcement currently exists in the simpleswitch/lab path. SMF can accept activation and deactivation notifications from PCF. Deactivation clears the IDS traffic influence state for future PDU sessions, which is the expected behavior for the current implementation. Live PFCP session modification to add or remove duplication from already-established sessions remains planned future work.

## Near-Term Commands

Local component testing uses `unittest`:

```bash
python3 -m unittest discover -s IDS/components/oai-ids/tests
```

The current minikube dev workflow is:

```bash
oai-dev-env/minikube/scripts/build-nf-image.sh pcf
oai-dev-env/minikube/scripts/redeploy-nf.sh pcf
oai-dev-env/minikube/scripts/build-nf-image.sh smf
oai-dev-env/minikube/scripts/build-nf-image.sh upf
oai-dev-env/minikube/scripts/build-nf-image.sh ids
oai-dev-env/minikube/scripts/redeploy-nf.sh ids
helm -n oai-5g-core status pcf
helm -n oai-5g-core status ids
kubectl -n oai-5g-core logs deploy/oai-ids
```

Useful smoke checks:

```bash
kubectl -n oai-5g-core exec deploy/oai-ids -- curl -s http://127.0.0.1:8080/readyz
kubectl -n oai-5g-core exec deploy/oai-ids -- curl -s http://127.0.0.1:8080/stats
kubectl -n oai-5g-core exec deploy/oai-ids -- curl -s http://127.0.0.1:8080/nids-security/v1/reports
kubectl -n oai-5g-core exec deploy/oai-ids -- curl -s http://127.0.0.1:8080/nids-event-exposure/v1/subscriptions
kubectl -n oai-5g-core exec deploy/oai-ids -- curl -s -X POST http://127.0.0.1:8080/nids-model-management/v1/model-notifications -H 'Content-Type: application/json' --data-binary '{"notifCorreId":"oai-ids-model-updates","mLModelInfo":[{"mLEvent":"ABNORMAL_BEHAVIOUR","mLFileAddr":{"mlModelUrl":"http://oai-nwdaf-mtlf-service:8082/nnwdaf-mlmodelprovision/v1/ml-models/model-job-smoke/file"},"accuracy":"HIGH"}]}'
kubectl -n oai-5g-core exec deploy/oai-ids -- curl -sS --http2-prior-knowledge -i -X POST http://oai-pcf/npcf-smpolicycontrol/v1/sm-policies -H 'Content-Type: application/json' --data-binary '{"supi":"imsi-001010000000001","pduSessionId":1,"pduSessionType":"IPV4","dnn":"oai","notificationUri":"http://oai-ids:8080/nids-event-exposure/v1/notifications","sliceInfo":{"sst":1},"servingNetwork":{"mcc":"001","mnc":"01"},"accessType":"3GPP_ACCESS","ratType":"NR"}'
```

The IDS chart is [`../oai-dev-env/minikube/charts/oai-ids`](../oai-dev-env/minikube/charts/oai-ids), with lab values in [`../oai-dev-env/minikube/values/ids-dev.yaml`](../oai-dev-env/minikube/values/ids-dev.yaml).

The PCF chart is [`../oai-dev-env/minikube/charts/oai-pcf`](../oai-dev-env/minikube/charts/oai-pcf). The lab values are in [`../oai-dev-env/minikube/values/pcf-dev.yaml`](../oai-dev-env/minikube/values/pcf-dev.yaml), with custom-NF metadata in [`../oai-dev-env/minikube/custom-nfs/oai-pcf.env`](../oai-dev-env/minikube/custom-nfs/oai-pcf.env).

NRF compatibility note: the IDS registers with OAI NRF as `nfType: AF` because OAI validates NF types against the generated 3GPP enum and does not accept a custom `IDS` type. The readable IDS identity remains in the Helm release, service name, runtime `instanceId`, and custom IDS API surface.

## Notes

- Phase 1 should keep detection simple and deterministic.
- Active countermeasure NF calls are still disabled; current behavior records and logs planned actions.
- Real ML/DL work begins in Phase 2 after the NF integration path is solid.
- `nwdafIntegration` is disabled in the lab values until the MTLF model-provision service is ready for IDS subscription tests.
