# MTLF Pod Data Commands

## 1. Create directories in the pod

```bash
kubectl exec -n oai-tutorial deploy/oai-nwdaf-nbi-ml -- mkdir -p /workspace/raw
```

## 2. Copy data files into the pod

```bash
POD=$(kubectl get pod -n oai-tutorial -l app=oai-nwdaf-nbi-ml -o jsonpath='{.items[0].metadata.name}')

kubectl cp /home/dave/oai/contrib1/data/100ue1202/output/merged_datasets/protocol_events.csv \
  oai-tutorial/${POD}:/workspace/raw/protocol_events.csv

kubectl cp /home/dave/oai/contrib1/data/100ue1202/output/merged_datasets/nf_events.csv \
  oai-tutorial/${POD}:/workspace/raw/nf_events.csv

kubectl cp /home/dave/oai/contrib1/data/100ue1202/output/merged_datasets/query_result_1m_99.csv \
  oai-tutorial/${POD}:/workspace/raw/query_result_1m_99.csv
```

## 3. Copy the processing script into the pod

```bash
kubectl cp /home/dave/oai/contrib1/training/process_data_serial_chain.py \
  oai-tutorial/${POD}:/app/process_data_serial_chain.py
```

## 4. Run the processing script

```bash
kubectl exec -it -n oai-tutorial deploy/oai-nwdaf-nbi-ml -- \
  env PROTOCOL_EVENTS_FILE=/workspace/raw/protocol_events.csv \
      NF_EVENTS_FILE=/workspace/raw/nf_events.csv \
      PROMETHEUS_FILE=/workspace/raw/query_result_1m_99.csv \
      OUTPUT_FILE=/workspace/dataset_serial_chain.pt \
  python3 /app/process_data_serial_chain.py
```

## 5. Copy the output dataset back to the host

```bash
kubectl cp oai-tutorial/${POD}:/workspace/dataset_serial_chain.pt \
  /home/dave/oai/contrib1/data/100ue1202/output/merged_datasets/dataset_serial_chain.pt
```

## Troubleshooting

### Fix NumPy version conflict (segfault / ABI mismatch)
```bash
kubectl exec -n oai-tutorial deploy/oai-nwdaf-nbi-ml -- \
  pip install --no-cache-dir "numpy>=1.24.0,<2.0.0"
```

### Fix torch_sparse segfault
```bash
kubectl exec -n oai-tutorial deploy/oai-nwdaf-nbi-ml -- \
  pip uninstall -y torch_sparse torch_scatter torch_cluster
```

### Rebuild & redeploy (Dockerfile updated)
The `Dockerfile.mtlf` now pins `numpy<2.0.0` and no longer installs prebuilt `torch_sparse/torch_scatter/torch_cluster` wheels to avoid ABI/segfault issues. Rebuild the image into the Minikube daemon and redeploy:

```bash
cd /home/dave/oai/contrib1/training
eval $(minikube docker-env)
docker build -f Dockerfile.mtlf -t oai-nwdaf-nbi-ml:latest .
kubectl apply -f /home/dave/oai/contrib1/oai-cn5g-nwdaf/manifests/manifests-labeled/nwdaf-nbi-ml.yaml
kubectl rollout restart deployment/oai-nwdaf-nbi-ml -n oai-tutorial
```

If you still need the additional PyG compiled extensions later, rebuild them inside the image ensuring versions match PyTorch and NumPy, or install via compatible wheels built for your PyTorch/CUDA combination.

### (Optional) Reinstall PyG in a live pod
If you prefer to patch the running pod (temporary), uninstall the problematic extensions and (re)install `torch_geometric` only:

```bash
kubectl exec -n oai-tutorial deploy/oai-nwdaf-nbi-ml -- \
  pip uninstall -y torch_sparse torch_scatter torch_cluster || true
kubectl exec -n oai-tutorial deploy/oai-nwdaf-nbi-ml -- \
  pip install --no-cache-dir torch_geometric==2.5.3
```

### Verify GPU is available
```bash
kubectl exec -n oai-tutorial deploy/oai-nwdaf-nbi-ml -- \
  python3 -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

### Verify package versions
```bash
kubectl exec -n oai-tutorial deploy/oai-nwdaf-nbi-ml -- \
  python3 -c "import numpy, torch; print('numpy:', numpy.__version__, 'torch:', torch.__version__)"
```
