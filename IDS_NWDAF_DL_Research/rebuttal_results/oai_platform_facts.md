# OAI 5G platform — re-implementation facts (for R4-1/R4-2/R1-8)

Captured live from the running minikube lab (`oai-dev`, namespace `oai-5g-core`, pods up 14 days).

## Cross-platform reproduction (headline)
The IDS architecture of the paper (originally evaluated on the commercial Amarisoft testbed)
has been **re-implemented on a fully open-source stack**: OAI 5G Core + a custom OAI **NWDAF**,
**PacketRusher** UE/gNB simulator, on **Kubernetes/minikube**, across **5 Tracking Areas**
(paris/lyon/marseille/toulouse/nice; TAC 000001–000005; 100 UEs each). This is a second,
independent platform with the same regional/federated scenario — directly addressing
reproducibility (R1-8) and the commercial-testbed dependency.

## NWDAF is realized as actual NFs (not "conceptually approximated") — R4-1
Per region (×5), the following NWDAF services are **deployed, running, and NRF-registered**:
- **MTLF** (`:8082`) — exposes `Nnwdaf_MLModelProvision` (`/nnwdaf-mlmodelprovision/v1/ml-models/{id}/file` and `/manifest`); `nrfRegistered: true`; serving area region+TAC; `trainingScenario` selectable (centralized/regional/federated-averaging/federated-distillation).
- **DCCF** (`:8081`) — data-management / IDS-report storage; `nrfRegistered: true`; MongoDB-backed.
- **NBI-analytics, NBI-events, NBI-ML, SBI, engine, MongoDB** — all per region.
- **NBI gateway** (Kong) — `:80/:443/:8001`.

The **IDS NF** (×5, `:8080` HTTP control + `:2152` UDP GTP-U) registers with NRF (as `AF` for OAI enum compatibility), activates traffic-influence via PCF (`trafficInfluenceStatus: accepted`), **subscribes to MTLF model updates over SBI** (`nwdafModelSubscriptionStatus: accepted`, receives `Nnwdaf_MLModelProvision` notifications), and processes **real duplicated GTP-U** (paris IDS: `packetCount=11129`, `decodeErrors=0`, last UE `12.1.0.144`).

### Honest scoping (R4-1/R4-2)
- **Standards-aligned and exercised:** NF registration/discovery (NRF), the SBI model-provision service (MTLF `Nnwdaf_MLModelProvision`), DCCF data-management, PCF traffic-influence → SMF → UPF GTP-U duplication, AMF/SMF event subscriptions.
- **Custom (not 3GPP-specified):** the ML *training algorithm* inside MTLF (3GPP does not specify the algorithm), and the IDS registers as `AF` because OAI's NRF rejects a custom `IDS` NF type.
- **Still placeholder / pending Track B:** the IDS detector currently runs a deterministic placeholder (`region-paris-placeholder-v1`) and MTLF serves a stub model; reproducing the *real* federated detection accuracy on OAI is the remaining Track B work.

## What Track B must still produce (to claim "similar results")
1. Run the 4 training procedures in MTLF on OAI-captured traffic → export real models.
2. Have the IDS load the real model (hot-swap) and reproduce detection accuracy → show it is **similar** to the Amarisoft results.
3. Measure live: CP signaling overhead per TA (R4-3), end-to-end detection latency (R4-4), FL aggregation/round latency (R2-5), and IDS+NWDAF-training resource impact on the core.
