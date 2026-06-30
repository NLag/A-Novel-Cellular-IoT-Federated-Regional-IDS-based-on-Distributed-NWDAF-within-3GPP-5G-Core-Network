#!/usr/bin/env python3
"""R4-8: FedAvg Transformer on the overlapping-skewed split (vs one-attack-per-region)."""
import os, sys, json, importlib.util
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import IDS_lib as lib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("abl", os.path.join(HERE, "seq_len_ablation.py"))
abl = importlib.util.module_from_spec(spec); spec.loader.exec_module(abl)

lib.SEQ_LEN = 256
TRAIN = os.path.join(ROOT, "datasets/overlapping_federated_datasets/train/")
EVAL = os.path.join(ROOT, "datasets/overlapping_federated_datasets/eval/")

print("Loading overlapping split ...", flush=True)
tr, va, te, ev = lib.load_private_region_datasets(TRAIN, EVAL, quiet=True)
model, rounds = abl.fedavg("Transformer", tr, va)
ev_m = abl.evaluate(model, ev)
import torch
tp, tl = [], []
model.eval()
with torch.no_grad():
    for i in range(len(te)):
        for inp, lab in te[i]:
            p = torch.argmax(model(inp).data, 2)
            tp.extend(p.view(-1).cpu().numpy()); tl.extend(lab.view(-1).cpu().numpy())
from sklearn.metrics import accuracy_score, f1_score
test_m = {"accuracy": accuracy_score(tl, tp) * 100,
          "f1_weighted": f1_score(tl, tp, average="weighted", zero_division=0) * 100}
out = {"scheme": "FedAvg", "split": "overlapping", "arch": "Transformer",
       "rounds": rounds, "test": test_m, "eval": ev_m}
json.dump(out, open(os.path.join(HERE, "r48_fedavg_overlap.json"), "w"), indent=2)
print(f"DONE FedAvg overlap: eval acc={ev_m['accuracy']:.2f} f1w={ev_m['f1_weighted']:.2f} "
      f"f1m={ev_m['f1_macro']:.2f} | test acc={test_m['accuracy']:.2f} | rounds={rounds}", flush=True)
