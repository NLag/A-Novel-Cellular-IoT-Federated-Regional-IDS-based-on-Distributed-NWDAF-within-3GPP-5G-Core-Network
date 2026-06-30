#!/usr/bin/env python3
"""R4-8: build an OVERLAPPING-but-SKEWED non-IID regional split.

Reviewer 4 (R4-8) notes the one-attack-per-region split is an artificially clean
non-IID partition and asks how the model behaves when regions observe
*overlapping but skewed* attack distributions.

Construction (no duplication, identical total attack volume as the baseline):
each attack class a is redistributed 70/30 -- its dominant region a keeps 70% of
class a's samples, and the remaining 30% is split evenly across the other four
regions. Every region therefore sees ALL attack classes (overlap) but is dominated
by its own (skew). Normal traffic stays partitioned exactly as in the baseline,
and the public/eval sets are copied unchanged so the comparison is controlled.

Output: datasets/overlapping_federated_datasets/{train/{public,private},eval}
"""
import os, shutil
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "datasets/federated_datasets_noslowite_nosqlmap")
OUT = os.path.join(ROOT, "datasets/overlapping_federated_datasets")
SEED = 42
DOMINANT_FRAC = 0.70
REGIONS = [1, 2, 3, 4, 5]


def main():
    rng = np.random.RandomState(SEED)
    os.makedirs(os.path.join(OUT, "train", "private"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "train", "public"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "eval"), exist_ok=True)

    priv = {k: pd.read_csv(os.path.join(BASE, "train", "private",
                                        f"private_region_dataset_{k}.csv")) for k in REGIONS}
    # normal rows stay with their region; attack-a pool is region a's own attack rows
    normals = {k: priv[k][priv[k]["label"] == 0] for k in REGIONS}
    attack_pool = {a: priv[a][priv[a]["label"] == a] for a in REGIONS}

    region_parts = {k: [normals[k]] for k in REGIONS}
    for a in REGIONS:
        pool = attack_pool[a].sample(frac=1.0, random_state=SEED).reset_index(drop=True)
        n = len(pool)
        n_dom = int(DOMINANT_FRAC * n)
        region_parts[a].append(pool.iloc[:n_dom])           # 70% to dominant region a
        rest = pool.iloc[n_dom:]
        others = [k for k in REGIONS if k != a]
        for o, chunk in zip(others, np.array_split(rest, len(others))):
            region_parts[o].append(chunk)                   # 30% spread to the rest

    print("New region label distributions (overlapping-skewed):")
    for k in REGIONS:
        df = pd.concat(region_parts[k], ignore_index=True)
        df = df.sort_values("timestamp").reset_index(drop=True)  # interleave classes in time
        df.to_csv(os.path.join(OUT, "train", "private",
                               f"private_region_dataset_{k}.csv"), index=False)
        dist = df["label"].value_counts().sort_index().to_dict()
        print(f"  region {k}: rows={len(df)} labels={dist}")

    # public + eval copied unchanged (controlled comparison)
    shutil.copy(os.path.join(BASE, "train", "public", "public_shared_dataset.csv"),
                os.path.join(OUT, "train", "public", "public_shared_dataset.csv"))
    shutil.copy(os.path.join(BASE, "eval", "Combined_eval_dataset.csv"),
                os.path.join(OUT, "eval", "Combined_eval_dataset.csv"))
    print(f"\nWrote overlapping split to {OUT}")


if __name__ == "__main__":
    main()
