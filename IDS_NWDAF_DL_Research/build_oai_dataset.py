#!/usr/bin/env python3
"""Consolidate live OAI captures into a federated training dataset.

Reads the IDS dataset-capture ``model_ready.csv`` files written during the
emulation and emits the public/private/eval CSV layout expected by the training
loaders (columns: timestamp, packet_hex, label).

One-attack-per-region (mirrors the thesis non-IID split):
    region 1 (paris)     -> coapdos   (label 1)
    region 2 (lyon)      -> mqttflood (label 2)
    region 3 (marseille) -> pingflood (label 3)
    region 4 (toulouse)  -> portscan  (label 4)
    region 5 (nice)      -> tcpsyn    (label 5)
Normal IoT traffic is label 0. The capture wrote a placeholder numeric_label,
so the label is (re)assigned here from the region->attack mapping we controlled.
"""

from __future__ import annotations

import csv
import glob
import os

STORAGE = "./OAI_5G_STORAGE/IDS_RELATED_STORAGE/DATASETS"
NORMAL_SCENARIO = "normal-iot-20260615"
ATTACK_SCENARIO = "oai-attack-20260630"
OUT = "./IDS_NWDAF_DL_Research/datasets/oai_federated_20260630"

SEQ = 256          # block size = one model sequence
EVAL_FRAC = 0.2    # held-out fraction per class for the eval set
PUBLIC_FRAC = 0.15 # fraction of each class's train portion donated to the public set
NORMAL_CAP_MULT = 2  # cap normal packets per region to this x the region's attack count

# region index (1-based) -> (region name, attack numeric label)
REGIONS = [
    (1, "paris", 1),
    (2, "lyon", 2),
    (3, "marseille", 3),
    (4, "toulouse", 4),
    (5, "nice", 5),
]


def read_hex(scenario: str, region: str) -> list[str]:
    pattern = os.path.join(STORAGE, scenario, f"region-{region}", "*", "model_ready.csv")
    files = glob.glob(pattern)
    rows: list[str] = []
    for f in files:
        with open(f, newline="") as fh:
            for row in csv.DictReader(fh):
                h = (row.get("packet_hex") or "").strip()
                if h:
                    rows.append(h)
    return rows


def interleave_blocks(streams: list[tuple[list[str], int]]) -> list[tuple[str, int]]:
    """Round-robin SEQ-sized blocks from each (hexlist, label) stream."""
    out: list[tuple[str, int]] = []
    idx = [0] * len(streams)
    active = True
    while active:
        active = False
        for s, (hexes, label) in enumerate(streams):
            start = idx[s]
            if start >= len(hexes):
                continue
            block = hexes[start:start + SEQ]
            idx[s] = start + SEQ
            out.extend((h, label) for h in block)
            if idx[s] < len(hexes):
                active = True
    return out


def write_csv(path: str, rows: list[tuple[str, int]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp", "packet_hex", "label"])
        for i, (hexstr, label) in enumerate(rows):
            w.writerow([i, hexstr, label])


def split_for_eval(items: list[str]) -> tuple[list[str], list[str]]:
    """Hold out the last EVAL_FRAC (whole SEQ blocks) for eval."""
    n_eval = int(len(items) * EVAL_FRAC)
    n_eval -= n_eval % SEQ  # keep whole sequences
    if n_eval == 0 and len(items) >= 2 * SEQ:
        n_eval = SEQ
    return items[: len(items) - n_eval], items[len(items) - n_eval:]


def main() -> None:
    public_streams: list[tuple[list[str], int]] = []
    eval_streams: list[tuple[list[str], int]] = []

    # Normal traffic, pooled across regions for the public/eval split.
    normal_all: list[str] = []
    for _, region, _ in REGIONS:
        normal_all.extend(read_hex(NORMAL_SCENARIO, region))
    print(f"normal pooled packets: {len(normal_all)}")

    summary = []
    for ridx, region, label in REGIONS:
        attack = read_hex(ATTACK_SCENARIO, region)
        normal = read_hex(NORMAL_SCENARIO, region)
        # cap normal to keep the attack class well represented per region
        cap = min(len(normal), NORMAL_CAP_MULT * len(attack)) if attack else len(normal)
        normal = normal[:cap]

        a_train, a_eval = split_for_eval(attack)
        n_train, n_eval = split_for_eval(normal)

        # private region file: interleave normal(0) + this attack(label)
        rows = interleave_blocks([(n_train, 0), (a_train, label)])
        write_csv(os.path.join(OUT, "train", "private", f"private_region_dataset_{ridx}.csv"), rows)

        # donate a slice to the public set (covers all classes once assembled)
        pub_a = a_train[: max(SEQ, int(len(a_train) * PUBLIC_FRAC))]
        public_streams.append((pub_a, label))
        eval_streams.append((a_eval, label))

        summary.append((region, label, len(attack), len(a_train), len(a_eval), len(n_train)))
        print(f"region {ridx} {region}: attack={len(attack)} (train {len(a_train)}/eval {len(a_eval)}), "
              f"normal_train={len(n_train)} -> private rows={len(rows)}")

    # public set: normal sample + each attack sample
    n_pub = normal_all[: PUBLIC_FRAC and int(len(normal_all) * 0.05) or SEQ]
    public_streams.insert(0, (n_pub, 0))
    public_rows = interleave_blocks(public_streams)
    write_csv(os.path.join(OUT, "train", "public", "public_shared_dataset.csv"), public_rows)
    print(f"public rows: {len(public_rows)}")

    # eval set: held-out normal + held-out of each attack
    _, normal_eval = split_for_eval(normal_all)
    eval_streams.insert(0, (normal_eval, 0))
    eval_rows = interleave_blocks(eval_streams)
    write_csv(os.path.join(OUT, "eval", "Combined_eval_dataset.csv"), eval_rows)
    print(f"eval rows: {len(eval_rows)}")

    print("\n=== summary (region, label, attack_total, a_train, a_eval, n_train) ===")
    for s in summary:
        print(" ", s)
    print(f"\nDataset written to {OUT}")


if __name__ == "__main__":
    main()
