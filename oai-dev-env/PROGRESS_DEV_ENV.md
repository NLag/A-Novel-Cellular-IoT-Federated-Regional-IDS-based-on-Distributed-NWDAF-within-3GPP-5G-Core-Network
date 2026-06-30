# Development Environment Progress

Last checked: 2026-06-30 after running the live attack-capture campaign and end-to-end measurements (Track B)

## Current Snapshot

The `oai-dev-env` folder now contains a Helm-managed minikube development lab for:

- OAI 5G Core release `core`
- legacy singleton OAI NWDAF release `nwdaf`
- regional OAI NWDAF releases `nwdaf-paris`, `nwdaf-lyon`, `nwdaf-marseille`, `nwdaf-toulouse`, and `nwdaf-nice`
- PacketRusher release `packetrusher`
- optional custom NFs through the standalone chart template path

The checked-in configuration is ahead of the remembered "one PacketRusher UE" state. The default PacketRusher values now define five tunnel-enabled region pods with 100 UEs each:

  - `region-paris`: TAC `000001`, gNB ID `000008`, MSIN start `0000000100`, UE count `100`
  - `region-lyon`: TAC `000002`, gNB ID `000009`, MSIN start `0000000200`, UE count `100`
  - `region-marseille`: TAC `000003`, gNB ID `000010`, MSIN start `0000000300`, UE count `100`
  - `region-toulouse`: TAC `000004`, gNB ID `000011`, MSIN start `0000000400`, UE count `100`
  - `region-nice`: TAC `000005`, gNB ID `000012`, MSIN start `0000000500`, UE count `100`
  - registration pacing: `timeBetweenRegistrationMs=2000`

The minikube profile `oai-dev` is running. The `core`, `nwdaf`, and `packetrusher` Helm releases are deployed, and all pods reported `1/1 Running` after the restart.

Documentation roles are now split as:

- `oai-dev-env/minikube/README.md`: current lab layout and operating commands
- `oai-dev-env/PLAN_Dev_ENV.md`: future work only
- `oai-dev-env/PROGRESS_DEV_ENV.md`: checkpoint log and runtime observations

The PacketRusher build loop now points at the repo-root `PacketRusher` source tree. A local rebuild produced `local/oai-5g-packetrusher:dev`, and `redeploy-nf.sh packetrusher` upgraded only the `packetrusher` Helm release to revision `3`.

PacketRusher now has the code path needed for shared non-VRF gNB tunnels, and the checked-in dev values run that profile with `tunnel.enabled=true`. The minikube node must have the `gtp5g` module loaded before PacketRusher is deployed. The chart renders `--tunnel --tunnel-vrf=false` without `--dedicatedGnb` and grants the PacketRusher container the configured netlink/GTP capabilities.

The IDS release now runs in regional mode from `values/ids-dev.yaml`:

- `oai-ids-region-paris`: region `region-paris`, TAC `000001`, NF instance `11111111-1111-4111-8111-111111111101`
- `oai-ids-region-lyon`: region `region-lyon`, TAC `000002`, NF instance `11111111-1111-4111-8111-111111111102`
- `oai-ids-region-marseille`: region `region-marseille`, TAC `000003`, NF instance `11111111-1111-4111-8111-111111111103`
- `oai-ids-region-toulouse`: region `region-toulouse`, TAC `000004`, NF instance `11111111-1111-4111-8111-111111111104`
- `oai-ids-region-nice`: region `region-nice`, TAC `000005`, NF instance `11111111-1111-4111-8111-111111111105`
- compatibility service `oai-ids` currently selects the Paris IDS as a fallback

The active Phase 2 NWDAF regional baseline uses Option A: one full NWDAF Helm release per region/TAC.

- `nwdaf-paris`: region `region-paris`, TAC `000001`, with services such as `oai-nwdaf-mtlf-region-paris` and `oai-nwdaf-dccf-region-paris`
- `nwdaf-lyon`: region `region-lyon`, TAC `000002`, with services such as `oai-nwdaf-mtlf-region-lyon` and `oai-nwdaf-dccf-region-lyon`
- `nwdaf-marseille`: region `region-marseille`, TAC `000003`, with services such as `oai-nwdaf-mtlf-region-marseille` and `oai-nwdaf-dccf-region-marseille`
- `nwdaf-toulouse`: region `region-toulouse`, TAC `000004`, with services such as `oai-nwdaf-mtlf-region-toulouse` and `oai-nwdaf-dccf-region-toulouse`
- `nwdaf-nice`: region `region-nice`, TAC `000005`, with services such as `oai-nwdaf-mtlf-region-nice` and `oai-nwdaf-dccf-region-nice`
- MTLF stub model IDs are region-specific:
  - Paris: `region-paris-stub-latest`
  - Lyon: `region-lyon-stub-latest`
  - Marseille: `region-marseille-stub-latest`
  - Toulouse: `region-toulouse-stub-latest`
  - Nice: `region-nice-stub-latest`
- IDS regional NWDAF integration points now target the matching regional MTLF and DCCF services.
- Regional DCCF IDS reports are stored in the matching regional NWDAF MongoDB first. SQLite remains a fallback if MongoDB is unavailable, and memory remains the last lab fallback.
- `OAI_5G_STORAGE` is chart-wired as a shared mount at `/oai-5g-storage` for MTLF, DCCF, and IDS. MTLF records metadata for files under that root in the regional NWDAF MongoDB.

SMF now maps the PacketRusher regional SUPI ranges to the matching IDS services:

- Paris SUPIs `001010000000100` through `001010000000199` duplicate to `oai-ids-region-paris`
- Lyon SUPIs `001010000000200` through `001010000000299` duplicate to `oai-ids-region-lyon`
- Marseille SUPIs `001010000000300` through `001010000000399` duplicate to `oai-ids-region-marseille`
- Toulouse SUPIs `001010000000400` through `001010000000499` duplicate to `oai-ids-region-toulouse`
- Nice SUPIs `001010000000500` through `001010000000599` duplicate to `oai-ids-region-nice`

SMF now also prefers UE-location TAC over the dev-only SUPI fallback when selecting a regional IDS duplication service:

- TAC `000001` duplicates to `oai-ids-region-paris`
- TAC `000002` duplicates to `oai-ids-region-lyon`
- TAC `000003` duplicates to `oai-ids-region-marseille`
- TAC `000004` duplicates to `oai-ids-region-toulouse`
- TAC `000005` duplicates to `oai-ids-region-nice`
- the SUPI range mapping remains configured as a fallback while the TAC path is hardened

Prior tunnel-enabled validation reached release `packetrusher` revision `8`:

- `region-paris`: one gNB tunnel device `gnbd21c5fd0` for UE IPs `12.1.1.100` through `12.1.1.104`
- `region-lyon`: one gNB tunnel device `gnbd31c6163` for UE IPs `12.1.0.34` through `12.1.0.38`
- both region pods are `1/1 Running`
- a UE-sourced internet ICMP check from Paris UE `12.1.1.100` to `1.1.1.1` passed with `3/3` replies

Historical validation note: the small shared-tunnel validation profile passed, then PacketRusher was restored to the then-default non-tunnel profile:

- temporary tunnel release: `packetrusher` revision `6`
- restored default release: `packetrusher` revision `7`
- `region-paris`: one gNB tunnel device `gnbe11eb604` for UE IPs `12.1.1.100` and `12.1.1.101`
- `region-lyon`: one gNB tunnel device `gnbe21eb797` for UE IPs `12.1.0.27` and `12.1.0.28`
- UE-sourced traffic to `oai-traffic-server` pod IP `10.244.0.128` passed from all four tested UE IPs
- UE-sourced internet ICMP to `1.1.1.1` passed from Paris UE `12.1.1.100` and Lyon UE `12.1.0.28`
- after restoring the then-default profile, the new PacketRusher pods ran without `gtp5g` links and logs showed `Tunnel has been disabled`

## Done

- [x] Expanded Workstream 2.5/5 runtime to five regions with 100 PacketRusher UEs per region.
  - Added regional NWDAF values and releases:
    - `nwdaf-marseille`
    - `nwdaf-toulouse`
    - `nwdaf-nice`
  - Expanded PacketRusher regions to:
    - `region-paris`: MSIN `0000000100`, TAC `000001`, `ueCount=100`
    - `region-lyon`: MSIN `0000000200`, TAC `000002`, `ueCount=100`
    - `region-marseille`: MSIN `0000000300`, TAC `000003`, `ueCount=100`
    - `region-toulouse`: MSIN `0000000400`, TAC `000004`, `ueCount=100`
    - `region-nice`: MSIN `0000000500`, TAC `000005`, `ueCount=100`
  - Expanded IDS regional values to deploy one IDS per TAC.
  - Expanded AMF `plmn_support_list` and NSSF slice availability to TACs `1` through `5`.
  - Expanded SMF IDS duplication maps by TAC and by SUPI fallback range.
  - Added and ran `scripts/seed-500-ue-subscribers.sql`; the running MySQL database now has 500 auth rows and 500 session rows for SUPIs `001010000000100` through `001010000000599`.
  - Redeployed:
    - `core` revision `17`
    - `ids` revision `23`
    - `packetrusher` revision `17`
    - `nwdaf-paris` revision `10`
    - `nwdaf-lyon` revision `10`
    - `nwdaf-marseille` revision `1`
    - `nwdaf-toulouse` revision `1`
    - `nwdaf-nice` revision `1`
  - All five IDS, MTLF, DCCF, and PacketRusher regional pods reported `1/1 Running`.
  - PacketRusher pods had two early restarts during the rollout, then stayed running while UE registration/PDU session setup continued.
  - The initial `timeBetweenRegistrationMs=500` profile was too aggressive for five parallel 100-UE regions and PacketRusher pods logged `Unable to create FAR: bad file descriptor`.
  - Slowed PacketRusher registration pacing to `timeBetweenRegistrationMs=2000` and redeployed `packetrusher` revision `18`; the new pods started with restart count `0` and were progressing through UE setup.

- [x] Workstream 5, regional NWDAF Option A baseline:
  - Made the NWDAF dev chart suffix-aware so multiple releases can coexist in namespace `oai-5g-core`.
  - Added regional Helm values:
    - `values/nwdaf-paris-dev.yaml`
    - `values/nwdaf-lyon-dev.yaml`
  - Added `global.nameSuffix`, `global.region`, and `global.tac` support to the NWDAF chart.
  - Added regional labels to NWDAF resources:
    - `nwdaf.oai/region`
    - `nwdaf.oai/tac`
  - Added `serving_area` to generated MTLF and DCCF config.
  - Updated MTLF manifests and `/health` output to include serving-area metadata.
  - Updated DCCF `/health`, IDS report intake, and IDS report listing to include serving-area metadata.
  - Added DCCF MongoDB-backed IDS report storage:
    - regional DCCF config points to each regional MongoDB service and database.
    - IDS report list and stats endpoints expose the active report storage backend.
    - DCCF lazily reconnects to MongoDB if it starts before MongoDB is selectable.
    - SQLite remains the fallback report store.
  - Added MTLF training scenario config for the IDS research workflows:
    - `centralized`
    - `regional`
    - `federated-averaging`
    - `federated-distillation`
  - Set the default regional NWDAF MTLF scenario to `regional`.
  - Removed the old GNN-oriented MTLF training/inference path.
  - Added Helm-selected IDS model architecture options: `MLP`, `CNN`, `RNN`, `GRU`, `LSTM`, and `Transformer`.
  - Added shared `OAI_5G_STORAGE` chart wiring:
    - MTLF mounts it at `/oai-5g-storage`.
    - DCCF mounts it at `/oai-5g-storage`.
    - IDS mounts it at `/oai-5g-storage`.
  - Switched the checked-in shared storage values from direct `hostPath` to the shared PVC `oai-5g-storage`.
  - Created the `oai-5g-storage` PVC in namespace `oai-5g-core`; it bound successfully with `50Gi`, `ReadWriteOnce`, storage class `standard`.
  - Later switched the checked-in shared storage values from the PVC to a host-backed Minikube mount:
    - host folder: `OAI_5G_STORAGE`
    - Minikube node path: `/oai-5g-host-storage`
    - pod mount path: `/oai-5g-storage`
  - Started the Minikube mount and validated pod-to-host write-through with `.mtlf-paris-hostpath-test`.
  - Seeded the PVC with the normalized research package and lightweight legacy training targets:
    - `/oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research/nwdaf_mtlf_model_training`
    - `/oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research/DL_multiclass_centralize.py`
    - `/oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research/DL_multiclass_regional_models.py`
    - `/oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research/DL_multiclass_federated.py`
    - `/oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research/DL_multiclass_Federated_Distillation.py`
    - `/oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research/IDS_lib.py`
    - `/oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research/README.md`
    - `/oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research/requirements.txt`
  - Added MTLF MongoDB metadata indexing for files under `/oai-5g-storage`, using the regional NWDAF `storage_metadata` collection.
  - Rebuilt `local/oai-nwdaf-mtlf:dev` successfully with image ID prefix `7439bfab30d9`.
  - Rebuilt `local/oai-nwdaf-mtlf:dev` after the `nwdaf_mtlf_model_training` image integration with image ID prefix `afbb74bb736e`.
  - Updated IDS regional values so:
    - Paris subscribes to `http://oai-nwdaf-mtlf-region-paris:8082/nnwdaf-mlmodelprovision/v1`.
    - Paris forwards reports to `http://oai-nwdaf-dccf-region-paris:8081/ndccf-datamanagement/v1/ids-reports`.
    - Lyon subscribes to `http://oai-nwdaf-mtlf-region-lyon:8082/nnwdaf-mlmodelprovision/v1`.
    - Lyon forwards reports to `http://oai-nwdaf-dccf-region-lyon:8081/ndccf-datamanagement/v1/ids-reports`.
  - Updated dev scripts with regional NWDAF release targets:
    - `redeploy-stack.sh nwdaf-regional`
    - `redeploy-stack.sh nwdaf-paris`
    - `redeploy-stack.sh nwdaf-lyon`
  - Added retry/backoff to MTLF model-ready notification delivery so regional IDS redeploy timing does not drop bootstrap model notifications.
  - Fixed MTLF NRF registration:
    - Replaced MTLF's plain HTTP/1.1 `httpx` NRF calls with `curl --http2-prior-knowledge`, matching the OAI NRF h2c endpoint behavior.
    - Changed Paris MTLF NF instance ID to `22222222-2222-4222-8222-222222222201`.
    - Changed Lyon MTLF NF instance ID to `22222222-2222-4222-8222-222222222202`.
    - Updated IDS placeholder model metadata to reference the regional MTLF UUIDs.
  - Set the IDS chart deployment strategy to `Recreate` for the one-replica regional dev lab, avoiding callback delivery to terminating old IDS pods during redeploy.
  - Rebuilt `local/oai-nwdaf-mtlf:dev` successfully with image ID prefix `3d7cb08d6618` after the NRF registration fix.
  - Rebuilt `local/oai-nwdaf-dccf:dev` successfully with image ID prefix `4cc508a31419`.
  - Deployed `nwdaf-paris`; release revision `4` was running after the NRF fix redeploy.
  - Deployed `nwdaf-lyon`; release revision `4` was running after the NRF fix redeploy.
  - Redeployed IDS; release revision `21` was running after the NRF fix redeploy.
  - Validated MTLF NRF registration:
    - Paris MTLF `/health` reported `nrfRegistered: true`.
    - Lyon MTLF `/health` reported `nrfRegistered: true`.
    - NRF returned registered profiles for both regional MTLF UUIDs.
  - Validated Paris IDS model flow:
    - IDS subscription status `accepted`.
    - MTLF notified IDS about `region-paris-stub-latest`.
    - IDS fetched the manifest from `oai-nwdaf-mtlf-region-paris`.
    - Manifest serving area was `region-paris`, TAC `000001`.
  - Validated Lyon IDS model flow:
    - IDS subscription status `accepted`.
    - MTLF notified IDS about `region-lyon-stub-latest`.
    - IDS fetched the manifest from `oai-nwdaf-mtlf-region-lyon`.
    - Manifest serving area was `region-lyon`, TAC `000002`.
  - Validated Paris IDS-to-DCCF report flow with a synthetic report:
    - IDS `/stats` showed `nwdafReportForwardStatus: accepted`.
    - Paris DCCF listed one `region-paris`, TAC `000001` report.
  - Validated Lyon IDS-to-DCCF report flow with a synthetic report:
    - IDS `/stats` showed `nwdafReportForwardStatus: accepted`.
    - Lyon DCCF listed one `region-lyon`, TAC `000002` report.
  - Rebuilt `local/oai-nwdaf-dccf:dev` with MongoDB report-store support and image ID prefix `c9f473441ed8`.
  - Redeployed `nwdaf-paris` and `nwdaf-lyon`; both regional releases reached revision `8`.
  - Revalidated the regional IDS-to-DCCF report path after the MongoDB storage change:
    - Paris IDS posted `synthetic-mongo-test-v2`; Paris DCCF listed one matching report with `storage: mongodb`.
    - Lyon IDS posted `synthetic-mongo-test-v2`; Lyon DCCF listed one matching report with `storage: mongodb`.
    - Both DCCF `/stats` responses reported `idsReports.storage=mongodb` and `idsReports.total=1`.
  - Kept Option B as future work only: a lighter single-release regional-subfunction chart can be revisited if full per-region NWDAF stacks are too heavy.
- [x] Phase 2 TAC/TAI-based regional IDS selection:
  - Added AMF `ueLocation.nrLocation.tai` generation for SMF PDU-session create and update requests using the UE context populated from NGAP/NAS registration state.
  - Added SMF OpenAPI conversion for `ueLocation` and `addUeLocation`, extracting NR/E-UTRA TAI TAC into the internal create/update SM context request.
  - Stored the serving TAC on the SMF PDU-session context.
  - Added `OAI_SMF_IDS_DUPLICATION_HOST_BY_TAC`, using comma- or semicolon-separated rules in the form `<tac>=<ids-service>`.
  - Updated IDS duplication target selection to prefer the TAC map and fall back to `OAI_SMF_IDS_DUPLICATION_HOST_BY_SUPI` when TAC is missing or unmapped.
  - Updated `values/core-dev.yaml` with the current TAC mapping:
    - TAC `000001=oai-ids-region-paris`
    - TAC `000002=oai-ids-region-lyon`
  - Rebuilt `local/oai-smf:dev` successfully with image ID prefix `831c24126e8e`.
  - Rebuilt `local/oai-amf:dev` successfully with image ID prefix `8f5cee21b6a1`.
  - Redeployed AMF; `core` upgraded to revision `15`, and `oai-amf` rolled out successfully.
  - Redeployed SMF; `core` upgraded to revision `16`, and `oai-smf` rolled out successfully.
  - Redeployed NWDAF so AMF/SMF subscriptions were recreated; `nwdaf` upgraded to revision `18`.
  - Redeployed PacketRusher; `packetrusher` upgraded to revision `16`, and both regional deployments rolled out successfully.
  - All pods in `oai-5g-core` reported `1/1 Running` after the restart.
  - PacketRusher logs showed PDU-session establishment and GTP tunnel interface configuration for both regions.
  - AMF logs showed location reports with TAC `2` for Lyon cell `0x090000` and TAC `1` for Paris cell `0x080000`.
  - SMF logs confirmed TAC-selected IDS duplication targets:
    - `oai-ids-region-lyon` using UE location TAC `000002`
    - `oai-ids-region-paris` using UE location TAC `000001`
  - SMF logs confirmed FAR duplication parameters were added for both selected regional IDS services.
  - UE-source ICMP to `oai-traffic-server` pod IP `10.244.1.89` passed with `3/3` replies from:
    - Paris UE `12.1.1.100`
    - Lyon UE `12.1.0.2`
  - IDS counters confirmed TAC-selected regional separation after the pings:
    - Paris IDS advanced from `packetCount: 9` to `packetCount: 12`, last UE IP `12.1.1.100`, reports forwarded `12`.
    - Lyon IDS advanced from `packetCount: 3` to `packetCount: 6`, last UE IP `12.1.0.2`, reports forwarded `6`.
- [x] Phase 2 regional IDS traffic delivery:
  - Added SMF support for `OAI_SMF_IDS_DUPLICATION_HOST_BY_SUPI`, using comma- or semicolon-separated rules in the form `<supi-start>-<supi-end>=<ids-service>`.
  - Applied the regional host selector when IDS duplication is enabled during PDU-session creation.
  - Applied the same selector when the PCF/SMF IDS traffic-influence notification path updates existing PDU sessions.
  - Updated `values/core-dev.yaml` with the current dev-region mapping:
    - Paris `001010000000100-001010000000104=oai-ids-region-paris`
    - Lyon `001010000000109-001010000000113=oai-ids-region-lyon`
  - Rebuilt `local/oai-smf:dev` successfully with image ID prefix `12ae8e68f1fa`.
  - Redeployed SMF through the `core` release; `core` upgraded to revision `14`, and `oai-smf` rolled out successfully.
  - Verified the running SMF has `OAI_SMF_IDS_DUPLICATION_HOST_BY_SUPI` and can resolve both regional IDS services.
  - Verified `gtp5g`, `sctp`, and `udp_tunnel` were loaded in the minikube node.
  - Switched checked-in PacketRusher dev values to `tunnel.enabled=true` for regional IDS data-plane validation.
  - Redeployed PacketRusher; release `packetrusher` upgraded to revision `15`.
  - PacketRusher created PDU sessions for both regional UE sets:
    - Paris UE tunnel IPs `12.1.1.100` through `12.1.1.104`.
    - Lyon UE tunnel IPs `12.1.0.2` through `12.1.0.6`.
  - SMF logs confirmed FAR duplication targets:
    - Paris sessions: `target=oai-ids-region-paris:2152`.
    - Lyon sessions: `target=oai-ids-region-lyon:2152`.
  - UE-source ICMP to `oai-traffic-server` pod IP `10.244.1.89` passed with `3/3` replies from:
    - Paris UE `12.1.1.100`.
    - Lyon UE `12.1.0.2`.
  - IDS counters confirmed regional separation after the pings:
    - Paris IDS advanced from `packetCount: 6` to `packetCount: 9`, last UE IP `12.1.1.100`, reports forwarded `9`.
    - Lyon IDS advanced from `packetCount: 0` to `packetCount: 3`, last UE IP `12.1.0.2`, reports forwarded `3`.
- [x] Phase 2 regional IDS deployment baseline:
  - Extended the IDS Helm chart with `regions[]` support.
  - Regional mode renders one ConfigMap, Deployment, and Service per region.
  - Regional resources carry stable labels:
    - `app.kubernetes.io/region`
    - `ids.oai/tac`
  - Kept a compatibility service named `oai-ids`, currently selecting `region-paris`, so existing SMF duplication config still has a valid service target.
  - Updated `values/ids-dev.yaml` with Paris and Lyon IDS region entries, distinct instance IDs, distinct NRF instance IDs, region-specific placeholder model versions, and region-specific NWDAF callback URIs.
  - Updated IDS `/stats` to include `idsInstanceId`, `host`, `region`, `mcc`, `mnc`, and `tac`.
  - Updated the custom NF redeploy scripts so `redeploy-stack.sh ids` and `redeploy-nf.sh ids` wait on all regional IDS deployments by selector.
  - Rebuilt `local/oai-ids:dev` with image ID prefix `6355e8de6749`.
  - Redeployed IDS; release `ids` upgraded to revision `14`.
  - Both regional IDS pods rolled out as `1/1 Running` with zero restarts.
  - `/stats` confirmed:
    - Paris: `oai-ids-region-paris`, region `region-paris`, TAC `000001`, model `region-paris-placeholder-v1`.
    - Lyon: `oai-ids-region-lyon`, region `region-lyon`, TAC `000002`, model `region-lyon-placeholder-v1`.
  - NRF contains both IDS NF records with the expected `customInfo.idsServingRegion` and `customInfo.idsServingTac` values.
  - Both regional IDS instances completed NWDAF model subscriptions.
  - At this checkpoint, the single SMF duplication host still sent duplicated GTP-U to the compatibility service and therefore Paris IDS only:
    - Paris IDS received six packets from the two UE ping tests and forwarded six reports to DCCF.
    - Lyon IDS remained at `packetCount: 0`.
  - Follow-up completed in the regional IDS traffic delivery checkpoint above.
- [x] Phase 2 multi-region / multi-TAC core baseline:
  - Updated the dev-env plan with the regional IDS/NWDAF target architecture and follow-on workstreams for regional IDS, regional NWDAF, and end-to-end multi-region smoke tests.
  - Added AMF support for both dev tracking areas in `oai-dev-env/minikube/charts/oai-5g-core-dev/config.yaml`:
    - Paris TAC `0x0001`.
    - Lyon TAC `0x0002`.
  - Added NSSF slice availability for TAC `"1"` and TAC `"2"` in `oai-dev-env/minikube/charts/oai-5g-core-dev/nssf_slice_config.yaml`.
  - Updated PacketRusher dev values so Paris uses TAC `000001` and Lyon uses TAC `000002`.
  - Switched the checked-in PacketRusher dev values to `tunnel.enabled=false` for a stable control-plane-only smoke profile when `gtp5g` is not loaded. This was later changed back to `tunnel.enabled=true` after regional IDS data-plane validation became the default.
  - Updated `oai-dev-env/minikube/README.md` with the two default TACs and the control-plane versus shared-tunnel profile behavior.
  - `helm lint` passed for the core chart and PacketRusher chart.
  - `helm template` confirmed AMF/NSSF and PacketRusher render both regional TACs.
  - Redeployed `core`; release `core` upgraded to revision `13`.
  - Redeployed `nwdaf` after the core change; release `nwdaf` upgraded to revision `17`.
  - Redeployed `packetrusher`; release `packetrusher` upgraded to revision `13`.
  - PacketRusher region pods stayed `1/1 Running` with zero restarts after the control-plane-only redeploy.
  - AMF accepted both regional gNBs:
    - Paris gNB cell `0x080000`, TAC `1`.
    - Lyon gNB cell `0x090000`, TAC `2`.
  - All ten default UEs registered and established PDU sessions:
    - Paris IMSIs `001010000000100` through `001010000000104`.
    - Lyon IMSIs `001010000000109` through `001010000000113`.
  - AMF sent location reports to NWDAF SBI and DCCF with TAC `1` for Paris and TAC `2` for Lyon.
- [x] PacketRusher shared tunnel profile validation:
  - Set `tunnel.enabled: true` in the PacketRusher chart defaults and dev values file.
  - Kept `tunnel.vrf: false`, so the enabled tunnel profile remains the shared non-VRF gNB tunnel profile.
  - Updated the README to describe `gtp5g` as a PacketRusher tunnel prerequisite and to document how to disable tunnel mode.
  - `helm lint oai-dev-env/minikube/charts/oai-packetrusher-dev -f oai-dev-env/minikube/values/packetrusher-dev.yaml` passed.
  - `helm template` now renders `--tunnel --tunnel-vrf=false`, privileged mode, `NET_ADMIN`, and `NET_RAW` by default.
  - `helm template --set tunnel.enabled=false` still renders the control-plane-only PacketRusher command without tunnel flags or elevated tunnel security settings.
  - `helm template --set tunnel.vrf=true` still fails intentionally because shared VRF tunnel mode is unsupported.
  - Verified `gtp5g`, `sctp`, and `udp_tunnel` were loaded in the minikube node before redeploying.
  - Redeployed PacketRusher with the new default profile; release `packetrusher` upgraded to revision `8`.
  - The tunnel-enabled five-UE-per-region deployment had one `gtp5g` link per region:
    - Paris `gnbd21c5fd0` with `12.1.1.100/32` through `12.1.1.104/32`
    - Lyon `gnbd31c6163` with `12.1.0.34/32` through `12.1.0.38/32`
  - UE-sourced ICMP from `12.1.1.100` to `1.1.1.1` passed with `3/3` replies.
- [x] Workstream 4, shared tunnel runtime validation:
  - Built the bundled PacketRusher `gtp5g` kernel module after `gcc-12` was installed.
  - Verified `gtp5g`, `sctp`, and `udp_tunnel` were loaded in the minikube node.
  - Deployed a temporary shared-tunnel profile with two regions and two UEs per region:
    - `tunnel.enabled=true`
    - `tunnel.vrf=false`
    - `region-paris` `ueCount=2`
    - `region-lyon` `ueCount=2`
  - Both regions completed NG setup, UE registration, and PDU-session establishment.
  - PacketRusher created one shared `gtp5g` interface per region/gNB:
    - Paris pod `10.244.0.189`: `gnbe11eb604`
    - Lyon pod `10.244.0.188`: `gnbe21eb797`
  - Paris placed both UE /32 addresses on the same tunnel interface:
    - `12.1.1.100/32`
    - `12.1.1.101/32`
  - Lyon placed both UE /32 addresses on the same tunnel interface:
    - `12.1.0.27/32`
    - `12.1.0.28/32`
  - Source policy routing was present per UE while pointing at the shared tunnel device.
  - UE-sourced ICMP to `oai-traffic-server` pod IP `10.244.0.128` passed with `3/3` replies from:
    - `12.1.1.100`
    - `12.1.1.101`
    - `12.1.0.27`
    - `12.1.0.28`
  - UE-sourced ICMP internet egress to `1.1.1.1` passed with `3/3` replies from:
    - `12.1.1.100`
    - `12.1.0.28`
  - UPF logs showed N4 session establishment/modification for the four new sessions and `pfcp_switch` upstream activity for the UE traffic.
  - Restored PacketRusher to the then-default non-tunnel profile with `redeploy-nf.sh packetrusher`; release `packetrusher` upgraded to revision `7`.
  - The restored then-default PacketRusher pods rolled out as `1/1 Running`, logs showed `Tunnel has been disabled`, and `ip -d link show type gtp5g` was empty in the new pods.
- [x] Workstream 3, PacketRusher Helm tunnel profile:
  - Added `tunnel.enabled` and `tunnel.vrf` values to the PacketRusher chart and dev values file.
  - Added default tunnel security settings for the enabled profile: privileged mode plus `NET_ADMIN` and `NET_RAW`.
  - At that point, the default profile still rendered no `--tunnel` flags and no elevated container security settings.
  - The enabled profile renders `--tunnel --tunnel-vrf=false` for each region and does not render `--dedicatedGnb`.
  - `tunnel.enabled=true,tunnel.vrf=true` now fails at Helm template time because shared VRF tunnel mode is intentionally unsupported.
  - Documented that Helm can grant pod privileges but does not install or load the host/minikube-node `gtp5g` kernel module.
  - `helm lint oai-dev-env/minikube/charts/oai-packetrusher-dev -f oai-dev-env/minikube/values/packetrusher-dev.yaml` passed.
  - `helm template` was checked for default, enabled, and invalid VRF modes.
  - Redeployed the then-default non-tunnel PacketRusher profile; release `packetrusher` upgraded to revision `5`, both region pods rolled out as `1/1 Running`, and logs showed `Tunnel has been disabled`.
- [x] Workstream 2, shared-gNB tunnel code:
  - Documented the current PacketRusher tunnel mechanism before code changes.
  - `multi-ue --tunnel --tunnel-vrf=false` no longer requires `--dedicatedGnb`.
  - `multi-ue --tunnel` without `--tunnel-vrf=false` still rejects shared mode because the CLI default is VRF tunnel mode.
  - Non-VRF tunnel mode now uses one shared `gtp5g` netdev/socket per gNB N3 address.
  - Per-UE/PDU-session PDR, FAR, and QER IDs are allocated uniquely so multiple UEs can share one gNB tunnel device.
  - Per-UE source routing state remains separate while routes point to the shared gNB tunnel device.
  - UE PDU sessions now carry a cleanup callback so shared tunnel references, per-UE rules, addresses, routes, rules, and VRFs are released in order.
  - VRF tunnel mode remains on the old per-UE tunnel path and is still not supported for shared-gNB tunnel mode.
  - Added focused tests for shared tunnel interface naming, GTP rule ID allocation, and one-shot tunnel cleanup.
  - Rebuilt `local/oai-5g-packetrusher:dev` successfully with image ID prefix `48530145fb60`.
  - Redeployed PacketRusher on the then-default non-tunnel profile; release `packetrusher` upgraded to revision `4`, and both region pods rolled out as `1/1 Running`.
- [x] Workstream 1, PacketRusher build loop:
  - `build-nf-image.sh packetrusher` now builds from `/home/linhngn/newsetup/PacketRusher`.
  - `bash -n oai-dev-env/minikube/scripts/build-nf-image.sh` passes.
  - `oai-dev-env/minikube/scripts/build-nf-image.sh packetrusher` completed successfully.
  - The minikube Docker daemon contains `local/oai-5g-packetrusher:dev` with image ID prefix `183bd7da9a13`.
  - `oai-dev-env/minikube/scripts/redeploy-nf.sh packetrusher` upgraded release `packetrusher` to revision `3`.
  - PacketRusher deployments `packetrusher-region-paris` and `packetrusher-region-lyon` rolled out successfully and their new pods reported `1/1 Running`.
- [x] Documentation roles cleaned up so completed architecture and operating details live in `minikube/README.md`, while `PLAN_Dev_ENV.md` tracks only future work.
- [x] Dev environment root normalized to `oai-dev-env/minikube`.
- [x] `README.md` documents the bootstrap, build, deploy, PacketRusher, and inner-loop flows.
- [x] Shared helper scripts exist:
  - `scripts/common.sh`
  - `scripts/reset-runtime.sh`
  - `scripts/build-nf-image.sh`
  - `scripts/redeploy-stack.sh`
  - `scripts/redeploy-nf.sh`
  - `scripts/new-nf.sh`
  - `scripts/render-packetrusher-config.sh`
- [x] Source trees used by the dev environment are present:
  - `oai-cn5g-fed`
  - `oai-cn5g-nwdaf`
  - `PacketRusher`
- [x] Core umbrella chart exists at `minikube/charts/oai-5g-core-dev`.
- [x] Core chart dependencies are vendored in `minikube/charts/oai-5g-core-dev/charts`.
- [x] Core chart enables the planned core components:
  - MySQL
  - NRF
  - NSSF
  - LMF
  - UDR
  - UDM
  - AUSF
  - AMF
  - SMF
  - UPF
  - traffic server
- [x] IMS is disabled in the core values.
- [x] Core OAI images are configured as local dev images with `pullPolicy: Never`.
- [x] AMF, SMF, UPF, and traffic-server multus are disabled in the dev values.
- [x] Core config keeps the planned baseline:
  - `http_version: 2`
  - PLMN `001/01`
  - TAC `1` / `000001` for `region-paris`
  - TAC `2` / `000002` for `region-lyon`
  - DNN `oai`
  - S-NSSAI `sst: 1`, `sd: FFFFFF`
  - AMF value `8000`
- [x] Stable AMF NGAP service exists in the core chart:
  - service name `oai-amf-ngap`
  - SCTP port `38412`
  - NodePort `31412`
- [x] MySQL seed data includes PacketRusher subscriber range `001010000000100` through at least `001010000000120`, covering the current default regions.
- [x] NWDAF chart exists at `minikube/charts/oai-nwdaf-dev`.
- [x] NWDAF chart includes the planned services and deployments:
  - MongoDB database
  - Kong NBI gateway
  - engine
  - NBI analytics
  - NBI events
  - NBI ML
  - SBI
  - MTLF
  - DCCF
- [x] NWDAF OAI images are configured as local dev images with `pullPolicy: Never`; MongoDB and Kong remain upstream third-party images.
- [x] NWDAF is wired to in-cluster service names:
  - `http://oai-nrf:80`
  - `http://oai-amf`
  - `http://oai-smf`
  - `EVENT_NOTIFY_URI=http://oai-nwdaf-sbi:8080`
- [x] NWDAF AMF and SMF HTTP versions are set to `2`.
- [x] NWDAF NBI gateway is exposed as NodePort:
  - HTTP `30080`
  - HTTPS `30443`
  - admin `32001`
- [x] PacketRusher chart exists at `minikube/charts/oai-packetrusher-dev`.
- [x] PacketRusher lab values exist at `minikube/values/packetrusher-dev.yaml`.
- [x] PacketRusher chart renders one ConfigMap and one Deployment per `regions[]` item.
- [x] Each PacketRusher region pod injects its own pod IP into `gnodeb.controlif.ip` and `gnodeb.dataif.ip` with the Kubernetes downward API.
- [x] PacketRusher runs `packetrusher multi-ue -n <ueCount>` and does not use `--dedicatedGnb` in the default chart path.
- [x] PacketRusher targets `oai-amf-ngap.oai-5g-core.svc.cluster.local:38412`.
- [x] `helm template` succeeds for the `core`, `nwdaf`, and `packetrusher` charts with the current dev values.
- [x] Optional custom NF scaffolding exists, with an `ids` custom NF metadata stub.
- [x] `oai-dev-env/minikube/scripts/redeploy-stack.sh all` restarted minikube and redeployed `core` and `nwdaf`.
- [x] `oai-dev-env/minikube/scripts/redeploy-stack.sh packetrusher` redeployed PacketRusher.
- [x] Helm reports `core`, `nwdaf`, and `packetrusher` as `deployed`.
- [x] All checked pods in namespace `oai-5g-core` reported `1/1 Running` after restart.
- [x] Services are present, including `oai-amf-ngap` NodePort `31412/SCTP` and `oai-nwdaf-nbi-gateway` NodePort `30080/TCP`.
- [x] PFCP/N4 path verified from SMF and UPF logs:
  - SMF logs show repeated `PFCP HEARTBEAT PROCEDURE`.
  - UPF logs show repeated `Received SX HEARTBEAT REQUEST`.
  - UPF logs show `Received N4_SESSION_ESTABLISHMENT_REQUEST` and `Received N4_SESSION_MODIFICATION_REQUEST`.
  - SMF logs show `Set PDU Session Status to PDU_SESSION_ACTIVE`.
- [x] PacketRusher attach/PDU-session path verified for the configured default regions:
  - `region-paris` registered IMSIs `001010000000100` through `001010000000104`.
  - `region-lyon` registered IMSIs `001010000000109` through `001010000000113`.
  - Both region logs show `Receive Registration Accept`, `PDU Session was created with successful`, and `PDU address received`.
  - Historical note: at that time tunnel creation was disabled for the default non-tunnel PacketRusher profile. The shared tunnel profile was later validated, and the current checked-in dev values are tunnel-enabled for regional IDS data-plane smoke testing.
- [x] NWDAF AMF/SMF subscriptions and notifications verified from logs:
  - SBI log shows AMF subscription response `HTTP/2.0 201 Created`.
  - SBI log shows SMF subscription response from `CreateIndividualSubcription`.
  - SBI stores AMF and SMF notifications in MongoDB.
  - DCCF log shows successful AMF and SMF event subscriptions over HTTP/2 and received AMF/SMF notifications.
- [x] Host-side NWDAF gateway reachability verified through NodePort `30080`:
  - `curl -H 'Host: oai-nwdaf-nbi-gateway' http://192.168.49.2:30080/nnwdaf-analyticsinfo/v1/analytics` reached Kong and the upstream NBI service.
  - Response was `400 Bad Request` with body `"missing Event Id param"`, which confirms the route is reachable and the request reached application logic.

## Not Verified In This Check

- [ ] No remaining items from the current runtime checklist.

Reason: pod readiness, PFCP/N4, NWDAF subscriptions/notifications, PacketRusher registration/PDU sessions, host-side NWDAF gateway reachability, and the small shared-gNB tunnel traffic path were verified.

## Current Caveats

- NWDAF SBI logs an attempted PCF subscription timeout to `http://192.168.70.139:8080/npcf-eventexposure/v1/subscriptions`; PCF is currently out of scope for this dev lab.
- PacketRusher shared-tunnel mode requires the host/minikube-node `gtp5g` module to be built and loaded. The checked-in dev values currently keep tunnels enabled so the regional IDS data-plane smoke test exercises UE traffic by default.
- `oai-traffic-server` logs `Error: Nexthop has invalid gateway.`, but the iperf3 listeners remain up and UE-sourced ICMP to the traffic-server pod IP succeeded through the UPF path.

## Supporting Commands / Scripts

1. Start or reset the runtime:

   ```bash
   oai-dev-env/minikube/scripts/reset-runtime.sh
   ```

   or, if preserving runtime state:

   ```bash
   minikube start -p oai-dev
   ```

2. Check whether local images exist in the minikube Docker daemon:

   ```bash
   eval "$(minikube -p oai-dev docker-env --shell bash)"
   docker images --format '{{.Repository}}:{{.Tag}}' | sort
   ```

3. Build any missing images:

   ```bash
   oai-dev-env/minikube/scripts/build-nf-image.sh all-core
   oai-dev-env/minikube/scripts/build-nf-image.sh all-nwdaf
   oai-dev-env/minikube/scripts/build-nf-image.sh packetrusher
   ```

4. Deploy the base lab:

   ```bash
   oai-dev-env/minikube/scripts/redeploy-stack.sh all
   ```

5. Deploy PacketRusher when UE simulation is needed:

   ```bash
   oai-dev-env/minikube/scripts/redeploy-stack.sh packetrusher
   ```

6. Verify runtime state:

   ```bash
   kubectl -n oai-5g-core get pods,svc,deploy
   helm -n oai-5g-core status core
   helm -n oai-5g-core status nwdaf
   helm -n oai-5g-core status packetrusher
   ```

7. Check the important logs:

   ```bash
   kubectl -n oai-5g-core logs deploy/oai-smf
   kubectl -n oai-5g-core logs deploy/oai-upf
   kubectl -n oai-5g-core logs deploy/oai-nwdaf-sbi
   kubectl -n oai-5g-core logs -l app.kubernetes.io/name=oai-packetrusher-dev
   ```

8. Temporarily disable PacketRusher tunnels if a control-plane-only run is needed:

   ```bash
   helm upgrade --install packetrusher oai-dev-env/minikube/charts/oai-packetrusher-dev \
     -n oai-5g-core \
     -f oai-dev-env/minikube/values/packetrusher-dev.yaml \
     --set tunnel.enabled=false
   ```

## Open Items

- Scale the shared-gNB tunnel profile beyond the current five-UE-per-region profile.
- Add repeatable shared-tunnel smoke-test commands or a script for the tunnel-enabled profile.
- Add a repeatable PacketRusher/NWDAF smoke-test command set once the live cluster is confirmed healthy.
- Extend MySQL seed data before increasing PacketRusher UE counts beyond the seeded IMSI range.

## Workstream 2 Notes: PacketRusher Tunnel Mechanism

Current PacketRusher tunnel behavior before code changes:

- `packetrusher multi-ue --tunnel` is rejected unless `--dedicatedGnb` is also set in `internal/templates/test-multi-ues-in-queue.go`.
- With `--dedicatedGnb`, PacketRusher creates one simulated gNB per UE. Each UE therefore has its own gNB N3 address.
- After PDU-session setup, `internal/control_test_engine/ue/gtp/service/SetupGtpInterface` creates one Linux `gtp5g` netdev per UE using `gtpLink.CmdAddWithStopCh`.
- The netdev name is `val<msin>`, for example `val0000000100`.
- PacketRusher installs fixed rule IDs on that per-UE netdev:
  - FAR `1` for uplink forwarding
  - FAR `2` for downlink forwarding with outer-header creation toward the UPF
  - PDR `1` for downlink traffic from core to UE, matched by UE IP and downlink TEID
  - PDR `2` for uplink traffic from access to core, matched by UE IP and gNB GTP-U source IP
  - QER `1` when QFI is present
- PacketRusher adds the UE /32 IP address to the UE-specific netdev.
- In non-VRF tunnel mode, it adds a source-based routing rule from the UE /32 to a routing table based on the uplink TEID, then adds a default route in that table through the UE-specific netdev.
- In VRF tunnel mode, it creates a UE-specific VRF named `vrf<msin>`, enslaves the UE-specific netdev to it, and uses the same TEID-based routing table.
- Cleanup is currently UE-owned: UE termination deletes the stored netdev, route, rule, and VRF, and PDU-session deletion signals the per-UE GTP socket stop channel.

Planned shared-gNB mechanism:

- Allow `multi-ue --tunnel --tunnel-vrf=false` without `--dedicatedGnb`.
- Keep one simulated gNB per region/pod, so all UEs in that region share the same gNB N3 address.
- Create one `gtp5g` netdev/socket per gNB N3 address instead of one per UE.
- Install unique PDR/FAR/QER IDs per UE/PDU session on the shared gNB netdev because fixed IDs `1` and `2` would collide.
- Keep UE-specific source routing: each UE IP still gets its own source rule and TEID-based routing table, but all routes point to the shared gNB netdev.
- Track shared tunnel ownership with a reference count keyed by gNB N3 address, and delete the shared netdev only after the last attached UE/PDU session releases it.
- Leave shared VRF mode for later because one shared netdev cannot be cleanly enslaved to multiple per-UE VRFs at the same time.

Implemented shared-gNB mechanism:

- `SetupGtpInterface` uses a shared tunnel registry for `config.TunnelTun`.
- Shared tunnel registry keys are the gNB N3 IP address values received from the gNB context.
- Shared tunnel device names are stable FNV-derived names like `gnb<hash>` and are kept under Linux interface-name length limits.
- The shared tunnel registry reference-counts each gNB tunnel and removes the shared `gtp5g` netdev only when the final UE/PDU-session releases it.
- Dedicated per-UE tunnel setup remains in place for `config.TunnelVrf`.
- PDR/FAR/QER IDs are process-unique allocations, avoiding the old fixed `1` and `2` IDs that only worked on one netdev per UE.

Verification for this code workstream:

- Passed:

  ```bash
  GOCACHE=/tmp/packetrusher-gocache go test ./internal/control_test_engine/ue/gtp/service ./internal/control_test_engine/ue/context ./internal/templates
  GOCACHE=/tmp/packetrusher-gocache go build ./cmd/packetrusher.go
  oai-dev-env/minikube/scripts/build-nf-image.sh packetrusher
  oai-dev-env/minikube/scripts/redeploy-nf.sh packetrusher
  ```

- `go test ./...` was also attempted with a writable cache. It still fails on pre-existing unrelated repository issues:
  - `internal/work_load_model` requires missing host GSL headers.
  - `scenarios/sample` contains WASM import stubs that do not compile as a normal Go package.
  - `test` attempts a privileged listener and fails with `operation not permitted`.
  - The edited packages passed before those unrelated failures.

## Track B: Live Attack Capture, Dataset, and Measurements (2026-06-30)

Drove the lab end-to-end to capture a labeled multi-class dataset and measure live costs (reviewer R4-3/R4-4/R2-5/R1-8).

GTP-tunnel routing (key finding):

- UE-source traffic routes through the GTP tunnel via `ip rule from <UE_IP> lookup <gnb_table>` (each such table has `default dev gnb...`). OS-stack/connection-oriented attacks (mqtt/coap floods, port-scan) traverse the UPF and are captured.
- Raw-socket attacks (tcp-syn, icmp) bypass the tunnel by default. Fixes: use a UE source (`icmp-flood`, not `land-ping-flood`, which spoofs src=dst), and add a destination policy rule `ip rule add to <target> lookup <gnb_table>` so raw packets egress `gnb`. With this, tcp-syn capture went from 0 to ~600 packets / 15 s.

Capture campaign (one-attack-per-region, mirrors the thesis non-IID split):

- `values/ids-dev.yaml` `datasetCapture` set to scenario `oai-attack-20260630`, `traffic_class: attack`; the IoT server (`IoT_Simulate/bin/iot-server`) run on the host for the mqtt/coap floods.
- Attacker (`Attacker_Simulate/bin/attacker-client-linux-amd64`) run from each PacketRusher pod: paris=coapdos, lyon=mqttflood, marseille=pingflood (icmp), toulouse=portscan, nice=tcpsyn. Captured ~3.4k–4.9k attack packets/region; normal traffic was already captured under scenario `normal-iot-20260615`.
- Consolidated with `IDS_NWDAF_DL_Research/build_oai_dataset.py` into `datasets/oai_federated_20260630/` (public + 5 private + eval; region i → label i, labels assigned per region at consolidation).

Measurements (per agreed methodology):

- End-to-end detection latency: ≈ a few ms (first attack packet → detection against a clean benign baseline); ≈16 ms per 256-packet sequence on the CPU-only IDS NF.
- CP signaling: un-gated, one DCCF report per inspected packet (~15/s normal, ~27/s attack); with the IDS sliding-window alert gate a 3546-packet attack produced 1 NWDAF notification. Training CP is event-driven (one model-provision notification per published model). Set-up cost per TA: 1 NRF registration + 1 PCF traffic-influence + 1 MTLF subscription.
- Resource: IDS pod RSS ≈138 MB (image 954 MB with CPU torch), MTLF pod RSS ≈299 MB.

Full results: `../IDS_NWDAF_DL_Research/rebuttal_results/track_b_oai_results.md`. A backup of the pre-Track-B `values/ids-dev.yaml` is at `/tmp/ids-dev.yaml.bak`.
