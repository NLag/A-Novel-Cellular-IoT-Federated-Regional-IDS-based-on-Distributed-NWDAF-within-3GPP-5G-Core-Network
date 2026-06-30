# Track B — OAI 5G cross-platform reproduction (B1–B4 results)

Live OAI 5G Core + custom NWDAF on minikube (`oai-dev`, ns `oai-5g-core`), 5 Tracking
Areas (paris/lyon/marseille/toulouse/nice, TAC 000001–000005), PacketRusher UEs, IDS NFs
duplicating GTP-U. All numbers measured on this second, independent platform (the thesis
used a commercial Amarisoft testbed).

## B1 — Four training procedures wired into the NWDAF MTLF
- Unified parametrized entrypoint `mtlf_train.py` (scenario × architecture → `model.pt`
  state-dict + `metrics.json`), matching the MTLF `Nnwdaf_MLModelProvision` serving contract.
- All 4 procedures verified end-to-end (centralized / regional / federated-averaging /
  federated-distillation), 6 architectures. MTLF config (`mtlf-config.yaml`) dispatches all
  scenarios through the entrypoint; `pass_output_dir_args: true`.

## B2 — Live capture → federated dataset
- IDS dataset-capture writes `model_ready.csv` (`packet_hex` + label) per region.
- **Key finding (tunnel routing):** UE-source traffic routes through the GTP tunnel via
  `ip rule from <UE_IP> lookup <gnb_table>`. Raw-socket attacks (tcp-syn, icmp) needed either
  a UE source (icmp-flood, not land-ping) or a destination policy rule
  (`ip rule to <target> lookup <gnb_table>`) to traverse the UPF and be captured.
- Captured one-attack-per-region (mirrors thesis non-IID), label i per region:
  paris=coapdos(1), lyon=mqttflood(2), marseille=pingflood(3), toulouse=portscan(4), nice=tcpsyn(5).
  Attack packets/region: 3645 / 3423 / 4060 / 4821 / 3542; normal ~7k–17k/region.
- Consolidated to `datasets/oai_federated_20260630/` (public + 5 private + eval, all 6 classes).

## B3 — Train on OAI data + live in-IDS inference (similar results)
- **FedAvg-Transformer trained on OAI-captured data: TEST 96.18% (F1w 96.00, F1m 95.68),
  EVAL 100% (per-class F1 all ~100).** Thesis (Amarisoft): test ~99.99% / eval 98.21%.
  → cross-platform reproduction with comparable accuracy.
- Implemented full PyTorch loading + per-packet sequence inference in the IDS NF
  (`app/torch_detector.py`, `model_registry.py` `pytorch-state-dict` path); rebuilt IDS image
  with CPU torch.
- Live: IDS loads `loaded-local-artifact-torch` (Transformer, seq 256) and classifies live
  GTP-U — TCP-SYN attack in region-nice detected as **`torch:tcpsyn`** (label 5), score 0.9999,
  predicted_class malicious for all packets.

## B4 — Overhead / latency / resource (measured on OAI, per agreed methodology)

**(R2-5) Per-round FL latency — time for one training round:**
- FedAvg-Transformer ~**5.08 s/round** (16 rounds → ~81 s to early-stop) on A40.
- Thesis-scale FedDistill ~**29.76 s/round**.

**(R4-4) End-to-end detection latency — attack-start → detected:**
- Method: clean benign baseline (fresh IDS, `lastPredictedClass=None`), then launch the
  attack and measure wall-clock from the first attack packet to the first detection.
- Result: first TCP-SYN packet sent `11:55:18.604`, IDS flips to `malicious` `…518.610`
  → **≈5.7 ms** from first attack packet to detection. The per-packet sequence model flags
  the first malicious packet, so there is no buffer-fill delay. Pure inference is ~16 ms per
  256-packet sequence / ~1.1 ms for a single packet on the IDS CPU. (The attacker's ~4 s
  UE-source discovery is a tool artifact, not IDS latency.)

**(R4-3) CP signaling overhead — messages generated, training vs inference:**
- *Inference (un-gated baseline):* the IDS classifies every duplicated packet, so without
  gating it would forward ~1 DCCF report per inspected packet: **~15 reports/s under normal**
  vs **~27 reports/s under attack** (per TA; attack rate is throttled by tunnel/UPF duplication
  + IDS processing, not the offered 300 pps).
- *Inference (with sliding-window alert gate — added):* a notification (NWDAF report +
  countermeasure) is raised only after **≥10 malicious in the last 50 inspected packets**, and
  re-armed after the count falls to ≤3. Measured: a 15 s sustained attack of **3546 packets
  produced exactly 1 NWDAF notification** (`alertsRaised=1`, `nwdafReportsForwarded=1`) instead
  of 3546 — and isolated normal-traffic false positives never reach the threshold, so they raise
  no notification. CP signaling is thus **one event per sustained-attack episode**, not
  per-packet, while per-packet classification/capture continue for the dataset.
- *Training:* CP is **event-driven, not traffic-proportional** — 1 one-time MTLF model
  subscription per IDS + a model-provision notification per published model (2 observed over the
  deployment), plus periodic NRF heartbeats. Training adds essentially no per-packet CP load.

**Resource impact:** IDS pod RSS with torch ≈ **138 MB** (image 954 MB incl. CPU torch);
MTLF pod RSS ≈ **299 MB**; model 9.47 MB / 2.48 M params. MTLF training is CPU-only in-pod
(offline A40 training used for the accurate model; in-cluster path validated functionally).

**False positives + mitigation:** on freshly generated normal IoT traffic the live model
mislabels some normal packets as `portscan` (short normal TCP connects resemble scans), a
consequence of the small live-capture training set. This is expected per-packet noise; the
sliding-window alert gate above is the mitigation — isolated false positives stay below the
10-in-50 threshold and never raise a notification, so operational alerting is robust even though
per-packet predictions are noisy.

## Honest scoping
- OAI EVAL = same-platform held-out (synthetic attacks are cleanly separable → 100%); the
  thesis EVAL was a harder cross-environment test. The OAI result demonstrates feasibility +
  reproduction, not a stricter generalisation benchmark.
- Attack volumes are modest (~3.5–4.9k packets/class) due to short live captures.
