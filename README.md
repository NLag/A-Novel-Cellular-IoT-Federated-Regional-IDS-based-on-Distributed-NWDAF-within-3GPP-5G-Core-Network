# A Novel Cellular IoT Federated Regional IDS based on Distributed NWDAF within the 3GPP 5G Core Network

Supporting code, deployment lab, datasets, and manuscript for a **federated, region-distributed Intrusion Detection System (IDS)** that is integrated into the 3GPP 5G Core as a control-plane Network Function (NF) and coordinated by the **Network Data Analytics Function (NWDAF)** across multiple Tracking Areas.

## Scope

The IDS inspects raw 5G user-plane packets (duplicated as GTP-U from the UPF) with deep-learning sequence models, and is trained **federatively** across regions so that each Tracking Area improves detection without sharing raw user data. Two federation schemes are studied — **Federated Averaging (FedAvg)** and **Federated Distillation (FedDistill)** — over a deliberately non-IID, one-attack-per-region split. NWDAF acts as the federated coordinator (model training/serving via `Nnwdaf_MLModelProvision`), and the IDS registers and interoperates over the 3GPP Service-Based Interface (NRF, PCF/SMF/UPF, AMF, DCCF).

The work spans two complementary tracks:

1. **Offline deep-learning research** — model training, federated learning/distillation, dataset preparation, and result analysis on captured raw-packet datasets (originally over a commercial Amarisoft 5G testbed).
2. **Live open-source emulation** — a full **OpenAirInterface (OAI) 5G Core + custom NWDAF** lab on Kubernetes/minikube, with simulated UEs (PacketRusher), IoT/attacker traffic generators, live GTP-U capture, in-NF PyTorch inference, and end-to-end overhead/latency measurement. This is the independent, reproducible platform that cross-validates the research results.

## Repository structure

| Path | Role |
|------|------|
| [`IDS_NWDAF_DL_Research/`](IDS_NWDAF_DL_Research/) | Research Python workspace: model architectures + training (`IDS_lib.py`), the four training procedures (`DL_multiclass_*.py`), the parameterised MTLF entry point (`mtlf_train.py`), dataset builders, datasets, and reviewer-rebuttal experiments (`rebuttal_results/`). |
| [`IDS/`](IDS/) | The IDS network-function prototype (`components/oai-ids`): NRF registration, GTP-U capture, PyTorch detector + sliding-window alert gate, dataset capture, and observe-only countermeasures. See [`IDS/PLAN_IDS.md`](IDS/PLAN_IDS.md) / [`IDS/PROGRESS_IDS.md`](IDS/PROGRESS_IDS.md). |
| [`oai-cn5g-nwdaf/`](oai-cn5g-nwdaf/) | Custom IDS-oriented NWDAF (MTLF / DCCF / NBI / engine), derived from OAI. See [`oai-cn5g-nwdaf/PROGRESS_NWDAF.md`](oai-cn5g-nwdaf/PROGRESS_NWDAF.md). |
| [`oai-cn5g-fed/`](oai-cn5g-fed/) | OpenAirInterface 5G Core (federated deployment) used as the base 5G core. |
| [`oai-dev-env/`](oai-dev-env/) | The minikube development lab: Helm charts, region values, and build/redeploy/run scripts that bring up the 5-region core + NWDAF + IDS + PacketRusher. See [`oai-dev-env/PROGRESS_DEV_ENV.md`](oai-dev-env/PROGRESS_DEV_ENV.md). |
| [`PacketRusher/`](PacketRusher/) | UE/gNB simulator (one pod per region, 100 UEs each) generating the PDU sessions over which traffic is sent. |
| [`IoT_Simulate/`](IoT_Simulate/) | Go IoT traffic generator (HTTP/MQTT/CoAP) — benign/normal traffic. |
| [`Attacker_Simulate/`](Attacker_Simulate/) | Go attack traffic generator (CoAP/MQTT floods, port scan, TCP-SYN/ICMP floods, etc.). |
| [`OAI_5G_STORAGE/`](OAI_5G_STORAGE/) | Shared storage mounted into the lab pods: captured `DATASETS/`, served `MODEL/`, `TRAINING_CODE/`, and reports. |
| [`charts/`](charts/) | Supporting Helm charts. |

## Regional / federated setup

The lab runs **five Tracking Areas** — `paris`, `lyon`, `marseille`, `toulouse`, `nice` (TAC `000001`–`000005`) — each with its own IDS NF, regional NWDAF (MTLF/DCCF), and PacketRusher UE pod. For the non-IID study each region observes a single dominant attack class: `paris→coapdos`, `lyon→mqttflood`, `marseille→pingflood`, `toulouse→portscan`, `nice→tcpsyn` (label 0 = normal).

## Where to start

- **Run the lab:** `oai-dev-env/minikube/` (build with `scripts/build-nf-image.sh`, deploy with `scripts/redeploy-stack.sh` / `redeploy-nf.sh`); read [`oai-dev-env/PROGRESS_DEV_ENV.md`](oai-dev-env/PROGRESS_DEV_ENV.md) for the runbook and current state.
- **Train / reproduce models:** [`IDS_NWDAF_DL_Research/README.md`](IDS_NWDAF_DL_Research/README.md); the parameterised entry point is `mtlf_train.py`, datasets are built with `build_oai_dataset.py`.
- **Cross-platform reproduction results:** [`IDS_NWDAF_DL_Research/rebuttal_results/track_b_oai_results.md`](IDS_NWDAF_DL_Research/rebuttal_results/track_b_oai_results.md).
- **The paper & reviewer responses:** [`Third-Contribution/`](Third-Contribution/).

Each major subsystem keeps its own `PLAN_*.md` (forward plan) and `PROGRESS_*.md` (dated checkpoint log) for detailed status.
