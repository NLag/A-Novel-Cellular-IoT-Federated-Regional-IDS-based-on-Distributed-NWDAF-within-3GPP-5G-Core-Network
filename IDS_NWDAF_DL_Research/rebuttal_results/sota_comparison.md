# R2-2: Comparison against external state-of-the-art (reported-metric comparison)

Per the agreed approach, we do **not** re-implement the baselines in our emulator;
we compare against each work's **own reported headline metrics** and argue scenario
similarity (federated learning + IoT/5G intrusion detection). All four reviewer-relevant
papers have now been read in full and the numbers below are verified from their tables.
The comparison is explicitly a *positioning* comparison: datasets and splits differ, so
it is not a controlled head-to-head.

## Our result (for reference)
- **Transformer + FedAvg**: test **99.99%** acc / 99.99% wF1; **independent-eval 98.21%** acc / 98.17% wF1 — obtained on an *independently generated* dataset with attack **variants** and a **one-attack-per-region** (maximal non-IID) split.
- Differentiators: raw-packet input, 6-class, mapped onto a **3GPP NWDAF NF on a real 5G core**, evaluated cross-environment.

## Comparison table (verified reported numbers)

| Work | Scheme | Input / Dataset | Classes | Non-IID? | Eval distribution | Reported headline |
|---|---|---|---|---|---|---|
| **FIDS** (Mirzaee 2021) | FedAvg (FDNN), 16 clients, 5G smart-metering | feature-based / **NSL-KDD** (40→60 feat, one-hot+RFE) | 5 (DoS/U2R/R2L/Probe+normal) | random split (≈IID) | same-dataset | **99.55% acc, 99.5% P/R/F1, AUC 99.56**; rare U2R only P0.75/R0.50/F0.60 |
| **FedGen+** (Li 2025) | Generative FedDistill, 20 clients | raw-packet→784B image / **USTC-TFC2016, CTU-13** (+Edge-IIoTset…) | multi | Dirichlet α (0.05–10) | same-dataset, varied heterogeneity | USTC: **97.57% acc/97.58 F1** (α=1) → **88.36/88.04** (α=0.05); CTU-13 92.15/92.13 (α=1); Edge-IIoTset 99.17. Plain **FedDistill drops to 62.4%** at α=0.05 |
| **FLEKD** (Shen 2024) | Ensemble-KD FL, 9 clients, MLP | feature-based / **CICIDS2019** | 7 (DDoS variants) | Dirichlet α (0.5–10) | same-dataset | per-class F1 ≈ **99.8%**; rare/unknown class (UDPLag) **96.6–98.3%**, drop-label unknown 80.9% |
| **FedNIDS** (Nguyen 2024) | FedAvg+FedProx pretrain + novel-attack fine-tune, 4 silos | raw-packet (1525B) / **CIC-IDS2017/2018** | binary (attack/benign) | hash-shard, some silos see unseen attacks | cross-silo + held-out novel | **avg F1 0.97**; attack F1 0.99/0.99/0.96/0.94 per silo; novel botnet only after **fine-tuning** (4 rounds); adversarial F1 0.17→0.92 after fine-tune |

## Argument for the rebuttal
1. **Comparable or better headline performance under a stricter protocol.** Our Transformer-FedAvg reaches 98.21% on an *independently generated* eval set with attack variants — between FedGen+ (97.57% near-IID, same-dataset) and FLEKD/FIDS (~99.5–99.8% same-dataset) and above FedNIDS (binary, avg F1 0.97). Crucially, the SOTA numbers are same-distribution test splits, whereas ours is measured cross-environment, which normally *depresses* metrics.
2. **The closest analogues validate our setup, not contradict it.** FedNIDS uses exactly our hardest setting (cross-silo non-IID where "some silos experience attacks no other silo encounters") yet is only binary and needs an explicit *fine-tuning stage* to handle novel attacks; our 6-class Transformer generalises to attack variants **without** a per-attack fine-tuning step.
3. **Independent corroboration of our FedDistill finding (supports R2-4).** FedGen+ reports that plain FedDistill collapses to **62.4%** under high heterogeneity (α=0.05), and FLEKD argues simple logit/weight averaging "loses a lot of useful information … classification boundaries become fuzzy." This independently confirms our observation that vanilla FedDistill transfers knowledge poorly under non-IID — exactly why only the Transformer survives it in our results.
4. **Unique deployment realism.** None of the four maps the detector onto a 3GPP-compliant 5G core (NWDAF/SBI) with raw packets: FIDS is 5G-themed but feature-based on NSL-KDD; FLEKD is feature-based CICIDS2019; FedGen+/FedNIDS are raw-packet but not 5G-core NFs. Our work is the only raw-packet detector instantiated as a 5G-core NF.
5. **Honest limitation.** Datasets/splits differ; this is positioning evidence, not a controlled benchmark. A controlled re-implementation is noted as future work.

## One-line citations (already in references.bib)
- FIDS — Mirzaee et al., *FIDS: A Federated Intrusion Detection System for 5G Smart Metering Network*, MSN 2021. (`Parya_Haji_Mirzaee_2021`)
- FedGen+ — Li et al., *Flow-Based IoT Intrusion Detection via Improved Generative Federated Distillation Learning*, IEEE IoT J. 2025. (`Zeyu_Li_2025`)
- FLEKD — Shen et al., *Effective Intrusion Detection in Heterogeneous IoT Networks via Ensemble Knowledge Distillation-based Federated Learning*, arXiv 2024. (`Jiyuan_Shen_2024`)
- FedNIDS — Nguyen et al., *FedNIDS: A Federated Learning Framework for Packet-Based NIDS*, Digit. Threats 2025. (`Quoc_H_Nguyen_2024`)
