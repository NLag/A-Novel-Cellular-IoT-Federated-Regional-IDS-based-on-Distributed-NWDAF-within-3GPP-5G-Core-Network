# Minikube Dev Lab

This environment turns the repo into a developer-first OAI lab built around:

- `core` from [`oai-dev-env/minikube/charts/oai-5g-core-dev`](./charts/oai-5g-core-dev)
- `nwdaf` from [`oai-dev-env/minikube/charts/oai-nwdaf-dev`](./charts/oai-nwdaf-dev)
- PacketRusher from [`PacketRusher`](../../PacketRusher), packaged as `local/oai-5g-packetrusher` and deployed as the optional in-cluster UE/gNB simulator
- optional custom NFs such as `ids` and `pcf`, deployed explicitly when needed

The default path is source-built OAI images loaded into minikube and Helm for every in-cluster component. PacketRusher is deployed as a separate Helm release when UE simulation is needed.

Use the docs this way:

- [`README.md`](./README.md): current lab layout and operating commands
- [`../PLAN_Dev_ENV.md`](../PLAN_Dev_ENV.md): future work only
- [`../PROGRESS_DEV_ENV.md`](../PROGRESS_DEV_ENV.md): checkpoint log while work is in progress

## Current Lab Shape

The lab uses one namespace, `oai-5g-core`, and these Helm releases:

- `core`
- `nwdaf`
- `packetrusher`
- optional custom releases such as `ids` and `pcf`

The core release includes MySQL, NRF, NSSF, LMF, UDR, UDM, AUSF, AMF, SMF, UPF, and the traffic server. IMS is disabled. PCF is currently a custom NF release from [`charts/oai-pcf`](./charts/oai-pcf), not from the top-level [`../../charts`](../../charts) templates. NEF remains out of scope unless the chart set is expanded later.

The NWDAF release includes MongoDB, Kong NBI gateway, engine, NBI analytics, NBI events, NBI ML, SBI, MTLF, and DCCF. NWDAF uses in-cluster service names for NRF, AMF, and SMF, with HTTP/2 enabled for AMF/SMF subscriptions. The regional DCCF report path stores IDS reports in the matching regional MongoDB first, with SQLite and memory fallbacks for lab resilience. MTLF is boot-configured for one IDS research training scenario and records shared artifact metadata in MongoDB.

The IDS release is regional when deployed from [`values/ids-dev.yaml`](./values/ids-dev.yaml):

- `oai-ids-region-paris` serves `region-paris`, TAC `000001`
- `oai-ids-region-lyon` serves `region-lyon`, TAC `000002`
- `oai-ids-region-marseille` serves `region-marseille`, TAC `000003`
- `oai-ids-region-toulouse` serves `region-toulouse`, TAC `000004`
- `oai-ids-region-nice` serves `region-nice`, TAC `000005`
- `oai-ids` remains as a compatibility service and currently selects the Paris IDS

`OAI_5G_STORAGE` is chart-wired as the shared artifact path and is mounted at `/oai-5g-storage` in IDS, MTLF, and DCCF pods. The checked-in dev values use a Minikube host mount: the host folder `OAI_5G_STORAGE` is mounted into the Minikube node at `/oai-5g-host-storage`, and the charts mount that node path into pods.

The dev scripts start a new `oai-dev` profile with this mount automatically through `--mount --mount-string`, so the Docker-driver node container is created with a native bind mount. The relevant defaults are in [`scripts/common.sh`](./scripts/common.sh):

- `MINIKUBE_MEMORY=65536`
- `MINIKUBE_SHARED_STORAGE_MOUNT=true`
- `MINIKUBE_SHARED_STORAGE_HOST_PATH=$WORKSPACE_ROOT/OAI_5G_STORAGE`
- `MINIKUBE_SHARED_STORAGE_NODE_PATH=/oai-5g-host-storage`

With the Docker driver, Minikube cannot add this mount to an already-created node container. If the mount is absent, the dev scripts fail instead of starting a separate `minikube mount` process. Recreate the `oai-dev` profile through the dev scripts so Minikube creates the node with the mount from the start.

This host-backed storage is intended for normalized research-package code, model artifacts, training outputs, report exports, and federated exchange files.

To recreate the Docker-driver profile with the start-time mount, first preserve anything needed from in-cluster PVCs, then run:

```bash
minikube delete -p oai-dev
oai-dev-env/minikube/scripts/build-nf-image.sh all-core
oai-dev-env/minikube/scripts/build-nf-image.sh all-nwdaf
oai-dev-env/minikube/scripts/build-nf-image.sh ids
oai-dev-env/minikube/scripts/build-nf-image.sh packetrusher
oai-dev-env/minikube/scripts/redeploy-stack.sh all
```

The host folder `OAI_5G_STORAGE` is not deleted by `minikube delete`, but the Minikube cluster, in-node Docker images, Kubernetes resources, and non-host-backed PVC contents are removed.

SMF traffic duplication is region-aware in the dev profile through `OAI_SMF_IDS_DUPLICATION_HOST_BY_TAC`. TACs `000001` through `000005` map to `oai-ids-region-paris`, `oai-ids-region-lyon`, `oai-ids-region-marseille`, `oai-ids-region-toulouse`, and `oai-ids-region-nice`. The SUPI range selector remains configured as a fallback while the TAC path is hardened. The legacy `oai-ids` service remains as a Paris fallback.

The PacketRusher release is region-oriented:

- one `regions[]` item renders one ConfigMap and one Deployment
- one Deployment runs one PacketRusher pod
- one PacketRusher pod represents one region and one simulated gNB
- the pod runs `packetrusher multi-ue -n <ueCount>` without `--dedicatedGnb`
- the pod binds N2 and N3 to its own pod IP through the Kubernetes downward API

The baseline access profile is:

- PLMN `001/01`
- TACs:
  - `region-paris`: `000001`
  - `region-lyon`: `000002`
- DNN `oai`
- S-NSSAI `sst: 1`, `sd: FFFFFF`
- AMF field `8000`

The checked-in PacketRusher lab values currently use the shared-gNB tunnel profile so multi-region/TAC smoke tests exercise user-plane traffic. The minikube node must have the `gtp5g` kernel module loaded before PacketRusher is redeployed.

## Source-Built Images

OAI-owned components are built locally into the minikube Docker daemon and consumed with `pullPolicy: Never`.

Core image targets:

- `oai-amf`
- `oai-ausf`
- `oai-lmf`
- `oai-nrf`
- `oai-nssf`
- `oai-smf`
- `oai-traffic-server`
- `oai-udm`
- `oai-udr`
- `oai-upf`

NWDAF image targets:

- `engine`
- `nbi-analytics`
- `nbi-events`
- `nbi-ml`
- `sbi`
- `mtlf`
- `dccf`

PacketRusher is built as `local/oai-5g-packetrusher:dev` from [`../../PacketRusher`](../../PacketRusher). Third-party images such as MySQL, MongoDB, and Kong remain upstream images.

## Prerequisites

- `docker`
- `kubectl`
- `helm`
- `minikube`

Align the host with the OAI docs before bringing the lab up:

```bash
sudo modprobe sctp
echo "sctp" | sudo tee /etc/modules-load.d/sctp.conf
sudo sysctl net.ipv4.conf.all.forwarding=1
sudo iptables -P FORWARD ACCEPT
```

PacketRusher can use user-plane tunnels when `tunnel.enabled=true`, but that profile requires PacketRusher's `gtp5g` kernel prerequisite from its upstream README. The chart grants the PacketRusher pod `NET_ADMIN`, `NET_RAW`, and privileged mode, but it does not install or load the host/minikube-node kernel module.

## First Bootstrap

Reset the existing runtime if you want a clean start:

```bash
oai-dev-env/minikube/scripts/reset-runtime.sh
```

Build the full source-built OAI image set into minikube's Docker daemon:

```bash
oai-dev-env/minikube/scripts/build-nf-image.sh all-core
oai-dev-env/minikube/scripts/build-nf-image.sh all-nwdaf
oai-dev-env/minikube/scripts/build-nf-image.sh packetrusher
```

Bring the default lab up:

```bash
oai-dev-env/minikube/scripts/redeploy-stack.sh all
```

Expose the NWDAF gateway hostname from the host:

```bash
echo "$(minikube -p oai-dev ip) oai-nwdaf-nbi-gateway" | sudo tee -a /etc/hosts
```

After deployment, the key host-side endpoints are:

- PacketRusher NGAP to AMF from inside the cluster: `oai-amf-ngap.oai-5g-core.svc.cluster.local:38412` over SCTP
- PacketRusher NGAP to AMF from the host: `$(minikube -p oai-dev ip):31412` over SCTP
- NWDAF gateway: `http://$(minikube -p oai-dev ip):30080`

## PacketRusher Flow

The regional PacketRusher chart is in [`charts/oai-packetrusher-dev`](./charts/oai-packetrusher-dev), with the lab values in [`values/packetrusher-dev.yaml`](./values/packetrusher-dev.yaml). The default values create five PacketRusher pods:

- `region-paris`: one gNB, 100 UEs, MSIN range `0000000100` through `0000000199`, gNB ID `000008`
- `region-lyon`: one gNB, 100 UEs, MSIN range `0000000200` through `0000000299`, gNB ID `000009`
- `region-marseille`: one gNB, 100 UEs, MSIN range `0000000300` through `0000000399`, gNB ID `000010`
- `region-toulouse`: one gNB, 100 UEs, MSIN range `0000000400` through `0000000499`, gNB ID `000011`
- `region-nice`: one gNB, 100 UEs, MSIN range `0000000500` through `0000000599`, gNB ID `000012`

The current five-region profile uses `timeBetweenRegistrationMs: 2000`. A faster `500 ms` registration cadence caused PacketRusher restarts during parallel 100-UE region startup in the lab.

The default regions use different tracking areas:

- `region-paris`: TAC `000001`
- `region-lyon`: TAC `000002`
- `region-marseille`: TAC `000003`
- `region-toulouse`: TAC `000004`
- `region-nice`: TAC `000005`

Build the local wrapper image and deploy the PacketRusher release:

```bash
oai-dev-env/minikube/scripts/build-nf-image.sh packetrusher
oai-dev-env/minikube/scripts/redeploy-stack.sh packetrusher
kubectl -n oai-5g-core get pods -l app.kubernetes.io/name=oai-packetrusher-dev
```

Each `regions[]` item renders one ConfigMap and one Deployment. The pod injects its own pod IP into `gnodeb.controlif.ip` and `gnodeb.dataif.ip`, then runs `packetrusher multi-ue -n <ueCount>` without `--dedicatedGnb`. When `tunnel.enabled=true`, the chart appends `--tunnel --tunnel-vrf=false`.

The current seeded MySQL data covers the IMSI range used by these five regions. For an already-running lab database, run [`scripts/seed-500-ue-subscribers.sql`](./scripts/seed-500-ue-subscribers.sql) against `oai_db`; fresh database initialization also includes the same SUPI range in the chart SQL seed.

### PacketRusher Value Sources

The region names, UE counts, MSIN starts, and gNB IDs are Helm values in [`values/packetrusher-dev.yaml`](./values/packetrusher-dev.yaml). These values decide which IMSIs PacketRusher presents to the core:

- Paris uses `msinStart: 100`, so its first two IMSIs are `001010000000100` and `001010000000101`.
- Lyon uses `msinStart: 109`, so its first two IMSIs are `001010000000109` and `001010000000110`.

The PacketRusher ConfigMap template in [`charts/oai-packetrusher-dev/templates/configmaps.yaml`](./charts/oai-packetrusher-dev/templates/configmaps.yaml) writes `__POD_IP__` into both `gnodeb.controlif.ip` and `gnodeb.dataif.ip`. The Deployment template in [`charts/oai-packetrusher-dev/templates/deployments.yaml`](./charts/oai-packetrusher-dev/templates/deployments.yaml) replaces that placeholder at container startup using the Kubernetes downward API. This means the gNB N3 IP is the PacketRusher pod IP, not a committed static address.

Shared GTP interface names such as `gnbe11eb604` or `gnbe21eb797` are runtime-generated by PacketRusher code, not defined in Helm. The shared tunnel code hashes the gNB N3 IP with FNV32a and formats the Linux interface name as `gnb%08x`. Because the input is the pod IP, the interface name can change after a pod restart.

UE IP addresses come from subscriber data or SMF dynamic allocation:

- Paris UEs `001010000000100` and `001010000000101` have static IPs `12.1.1.100` and `12.1.1.101` in [`charts/mysql/initialization/oai_db-basic.sql`](./charts/mysql/initialization/oai_db-basic.sql).
- Lyon UEs `001010000000109` and `001010000000110` do not have static `staticIpAddress` entries, so their observed `12.1.0.27` and `12.1.0.28` addresses came from the SMF dynamic pool.
- The lab DNN `oai` dynamic UE pool is configured in [`charts/oai-5g-core-dev/config.yaml`](./charts/oai-5g-core-dev/config.yaml) as `12.1.0.0/16`.

Example from the small shared-tunnel validation run:

- Paris created one shared `gtp5g` tunnel `gnbe11eb604` for UE IPs `12.1.1.100` and `12.1.1.101`.
- Lyon created one shared `gtp5g` tunnel `gnbe21eb797` for UE IPs `12.1.0.27` and `12.1.0.28`.

The checked-in lab values run the shared-gNB data-plane profile by default. `tunnel.enabled=true` renders `--tunnel --tunnel-vrf=false` without `--dedicatedGnb`:

```bash
helm upgrade --install packetrusher ./oai-dev-env/minikube/charts/oai-packetrusher-dev \
  -n oai-5g-core \
  -f oai-dev-env/minikube/values/packetrusher-dev.yaml \
  --set tunnel.enabled=true
```

This profile still uses one PacketRusher pod and one gNB per region. VRF tunnel mode is intentionally not part of the shared-gNB profile yet because PacketRusher's current VRF design expects one GTP interface per UE.

To return to a control-plane-only profile, disable the tunnel values:

```bash
helm upgrade --install packetrusher ./oai-dev-env/minikube/charts/oai-packetrusher-dev \
  -n oai-5g-core \
  -f oai-dev-env/minikube/values/packetrusher-dev.yaml \
  --set tunnel.enabled=false
```

The old host-side PacketRusher config renderer remains available for debugging against the AMF `NodePort`:

```bash
oai-dev-env/minikube/scripts/render-packetrusher-config.sh --bind-ip <packet_rusher_ip>
```

For multi-gNB and handover tests, use a separate scenario profile because `--dedicatedGnb` changes the default regional model:

```bash
sudo ./packetrusher --config ../../oai-dev-env/minikube/packetrusher/config.yml multi-ue -n 4 --dedicatedGnb --ngh 5000
```

## Fast Inner Loop

For an edited core NF:

```bash
oai-dev-env/minikube/scripts/build-nf-image.sh amf
oai-dev-env/minikube/scripts/redeploy-nf.sh amf
```

For the traffic server:

```bash
oai-dev-env/minikube/scripts/build-nf-image.sh traffic-server
oai-dev-env/minikube/scripts/redeploy-nf.sh traffic-server
```

For a debug binary of a core NF:

```bash
oai-dev-env/minikube/scripts/build-nf-image.sh --debug smf
oai-dev-env/minikube/scripts/redeploy-nf.sh --debug smf
```

If AMF or SMF was restarted, redeploy NWDAF so subscriptions are recreated:

```bash
oai-dev-env/minikube/scripts/redeploy-stack.sh nwdaf
```

For an edited NWDAF component:

```bash
oai-dev-env/minikube/scripts/build-nf-image.sh sbi
oai-dev-env/minikube/scripts/redeploy-nf.sh sbi
```

For shared core config changes in [`oai-dev-env/minikube/charts/oai-5g-core-dev/config.yaml`](./charts/oai-5g-core-dev/config.yaml):

```bash
oai-dev-env/minikube/scripts/redeploy-stack.sh core
```

For PacketRusher-only changes:

```bash
oai-dev-env/minikube/scripts/build-nf-image.sh packetrusher
oai-dev-env/minikube/scripts/redeploy-nf.sh packetrusher
```

## Optional Custom NFs

Scaffold a new standalone NF chart:

```bash
oai-dev-env/minikube/scripts/new-nf.sh oai-my-nf
```

That creates:

- a chart under `oai-dev-env/minikube/charts/`
- a values file under `oai-dev-env/minikube/values/`
- a metadata stub under `oai-dev-env/minikube/custom-nfs/`

Typical flow:

```bash
oai-dev-env/minikube/scripts/build-nf-image.sh my-nf
oai-dev-env/minikube/scripts/redeploy-stack.sh my-nf
```

`ids` stays available through this custom-NF path, but it is no longer part of the default `all` deployment.
