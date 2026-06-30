# Dev Environment Future Work

This file is the forward-looking plan only. Current lab behavior and operating commands live in [`minikube/README.md`](./minikube/README.md). Completed checkpoints and runtime observations live in [`PROGRESS_DEV_ENV.md`](./PROGRESS_DEV_ENV.md).

## Objective

Enable PacketRusher data-plane testing in `oai-dev` without the current one-gNB-per-UE resource cost, then extend the lab into the Phase 2 regional IDS/NWDAF architecture.

Target shape:

- one PacketRusher pod per region
- one simulated gNB per region
- one shared gNB N3 tunnel per region
- many UEs in that region using the shared tunnel for user-plane traffic
- no `--dedicatedGnb` requirement for the standard tunnel data-plane profile
- one TAC per region
- one IDS instance per region/TAC
- one NWDAF Helm release per region/TAC for the current Option A deployment shape
- one shared `OAI_5G_STORAGE` mount available to IDS, MTLF, and DCCF for model, dataset, report, and federated exchange files
- clear labels, service names, NF instance IDs, and config values that map each PacketRusher region to the matching IDS/NWDAF region

The initial shared-tunnel runtime scenario is complete. The checked-in PacketRusher lab values currently run the shared non-VRF tunnel profile with `tunnel.enabled=true`, so the minikube node must have the `gtp5g` module loaded for PacketRusher data-plane traffic. The remaining work is hardening, scaling, and making the validation path repeatable.

The next architecture milestone is **regional IDS and regional NWDAF support before federated learning**. The two-region / two-TAC core and PacketRusher baseline is complete; federated algorithms should not be implemented until the lab can run distinct regional IDS/NWDAF instances and prove that region/TAC routing, model metadata, and detection reports remain separated.

## Workstream 1: Repeatable Shared-Tunnel Smoke Test

- Add a repeatable command set or script for the default tunnel profile:
  - `tunnel.enabled=true`
  - `tunnel.vrf=false`
  - five UEs per region
- Add explicit checks for:
  - `gtp5g` module presence on the minikube node
  - one `gtp5g` interface per region/gNB
  - all region UE /32 addresses on the same region tunnel device
  - UE-sourced ICMP to `oai-traffic-server`
  - UE-sourced ICMP to one external endpoint
- Keep the README command for temporarily disabling tunnels when a control-plane-only run is needed.

## Workstream 2: Scale Shared-Tunnel Profile

- Scale the shared-tunnel profile beyond the current five UEs per region.
- Extend MySQL seed data before increasing UE counts beyond the existing subscriber range.
- Capture resource usage for shared-gNB tunnel mode versus the old one-gNB-per-UE tunnel mode.
- Verify that per-UE source policy routing and PacketRusher cleanup remain stable at the selected scale.

## Workstream 3: Tunnel Mode Follow-Ups

- Revisit `--tunnel-vrf=true` after the non-VRF shared tunnel design is working.
- Keep handover and explicit multi-gNB tests as separate scenario profiles because they may still need `--dedicatedGnb`.

## Workstream 4: Regional IDS Instances

Purpose: harden the completed region-aware IDS traffic delivery path.

- Completed baseline:
  - The IDS Helm chart supports `regions[]` and deploys one ConfigMap, Deployment, and Service per region/TAC.
  - SMF can select a regional IDS duplication host by configured SUPI range.
  - Paris UE traffic is duplicated to `oai-ids-region-paris`.
  - Lyon UE traffic is duplicated to `oai-ids-region-lyon`.
  - Both IDS regions forward reports to DCCF with their own region/TAC metadata.
- Remaining follow-ups:
  - Decide whether the `oai-ids` compatibility service should be removed or kept as an explicitly documented fallback.
  - Add an automated smoke command/script that checks both IDS packet counters after Paris and Lyon UE-source traffic.

## Workstream 5: Regional NWDAF Instances

Purpose: prepare NWDAF/MTLF/DCCF behavior for region-specific model ownership before federated learning.

- Completed baseline:
  - Option A is the active deployment shape: one NWDAF Helm release per region/TAC.
  - `nwdaf-paris` deploys a full NWDAF stack for `region-paris`, TAC `000001`.
  - `nwdaf-lyon` deploys a full NWDAF stack for `region-lyon`, TAC `000002`.
  - The NWDAF dev chart supports suffix-aware names, selectors, ConfigMaps, service URLs, and labels through `global.nameSuffix`, `global.region`, and `global.tac`.
  - Regional values define distinct database names, MTLF services, DCCF services, MTLF NF instance IDs, DCCF NF instance IDs, seeded stub model IDs, and callback/base URIs.
  - IDS regional values point Paris to `oai-nwdaf-mtlf-region-paris` and `oai-nwdaf-dccf-region-paris`, and Lyon to `oai-nwdaf-mtlf-region-lyon` and `oai-nwdaf-dccf-region-lyon`.
  - MTLF manifests and health output carry `servingArea.region` and `servingArea.tac`.
  - DCCF health, IDS report intake, and IDS report listing carry region/TAC metadata.
  - DCCF IDS report storage uses the regional NWDAF MongoDB first, with SQLite and memory fallback.
  - MTLF training scenario is selected by Helm at boot; the active default is `regional`.
  - MTLF model architecture is selected by Helm at boot; supported values are `MLP`, `CNN`, `RNN`, `GRU`, `LSTM`, and `Transformer`.
  - MTLF can record shared-storage file metadata in the regional NWDAF MongoDB.
  - Regional MTLF instances register with NRF using UUID NF instance IDs and h2c HTTP/2 prior-knowledge requests.
  - MTLF model notifications retry callback delivery so transient IDS service readiness during redeploy does not drop the bootstrap model notification.
  - IDS deployments use `Recreate` strategy in this one-replica dev lab to avoid model notifications being delivered to a terminating old pod during redeploy.
- Validated:
  - Paris IDS subscribed to Paris MTLF and fetched the Paris stub-model manifest.
  - Lyon IDS subscribed to Lyon MTLF and fetched the Lyon stub-model manifest.
  - Paris IDS forwarded a synthetic detection report to Paris DCCF.
  - Lyon IDS forwarded a synthetic detection report to Lyon DCCF.
  - DCCF report queries filtered by region returned only the matching regional report from MongoDB.
- Remaining follow-ups:
  - Keep Option B as future work only: a single NWDAF release with `regions[]` for selected regional subfunctions may be useful later if full per-region stacks are too heavy.
  - Add a repeatable smoke script for regional MTLF subscription, manifest fetch, IDS report forwarding, and DCCF report filtering.
  - Add MongoDB PVC/retention/export handling if regional DCCF report records need to survive database pod replacement.
  - Add a shared-storage bootstrap flow for `OAI_5G_STORAGE`, including either PVC provisioning or a documented minikube host mount.
  - Decide when to retire or disable the legacy singleton `nwdaf` release in favor of the two regional releases.

## Workstream 6: End-to-End Multi-Region Smoke Test

Purpose: prove that the lab topology matches the Phase 2 target architecture before federated algorithms are added.

- Redeploy in this order:
  - core config with both TACs
  - regional NWDAF instances or regional MTLF/DCCF services
  - regional IDS instances
  - PacketRusher two-region profile
- Smoke checks:
  - `kubectl get pods` shows both PacketRusher regions, both IDS regions, and both NWDAF regions.
  - AMF logs show accepted NG setup for TAC 1 and TAC 2.
  - PacketRusher logs show UE registration and PDU sessions in both regions.
  - IDS Paris `/stats` reports `region-paris`, TAC `000001`.
  - IDS Lyon `/stats` reports `region-lyon`, TAC `000002`.
  - MTLF Paris exposes a Paris model/stub.
  - MTLF Lyon exposes a Lyon model/stub.
  - MTLF Paris `/proprietary/v1/training-scenario` reports `regional`.
  - MTLF Lyon `/proprietary/v1/training-scenario` reports `regional`.
  - IDS, MTLF, and DCCF pods mount `/oai-5g-storage`.
  - DCCF Paris stores only Paris IDS reports in the Paris NWDAF MongoDB.
  - DCCF Lyon stores only Lyon IDS reports in the Lyon NWDAF MongoDB.
- Document any remaining singletons explicitly:
  - NRF
  - UDR/UDM/AUSF
  - SMF/UPF/DNN
  - traffic server
