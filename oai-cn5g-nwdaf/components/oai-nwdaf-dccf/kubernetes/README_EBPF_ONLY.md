# eBPF-Only Monitoring for OAI 5G Core

Quick setup guide for deploying eBPF monitoring to your minikube cluster with Prometheus metrics export.

## 📋 What You Get

- ✅ **eBPF-based protocol monitoring** (HTTP/2, NGAP, PFCP)
- ✅ **Prometheus metrics** exposed on port 9950
- ✅ **Zero-touch discovery** of OAI network functions
- ✅ **Minimal overhead** - just the agent, no controller or database
- ✅ **Real-time visibility** into 5G core network operations

## 🚀 Quick Start (3 steps)

### 1. Build the Image

```bash
cd /home/dave/oai/newsetup/oai-cn5g-nwdaf/components/oai-nwdaf-dccf/kubernetes
chmod +x build-ebpf-image.sh
./build-ebpf-image.sh
```

### 2. Deploy to Kubernetes

```bash
chmod +x deploy-ebpf-only.sh
./deploy-ebpf-only.sh
```

### 3. Verify It's Working

```bash
# Check pods
kubectl get pods -n oai-tutorial -l app=ebpf-agent

# View metrics
kubectl port-forward -n oai-tutorial daemonset/ebpf-agent 9950:9950
curl http://localhost:9950/metrics
```

## 📊 Example Prometheus Queries

```promql
# Total request rate across all NFs
sum(rate(casmella_requests_total[5m]))

# Request latency (p95) by NF type
histogram_quantile(0.95, 
  sum by (nf_type, le) (rate(casmella_request_duration_seconds_bucket[5m]))
)

# HTTP/2 requests by operation
sum by (operation) (rate(casmella_http2_requests_total[5m]))

# NGAP message rate (gNB ↔ AMF)
rate(casmella_ngap_messages_total[5m])

# PFCP message rate (SMF ↔ UPF)
rate(casmella_pfcp_messages_total[5m])
```

## 📁 Files in This Directory

| File | Description |
|------|-------------|
| `minimal-ebpf-deployment.yaml` | Complete K8s manifest (namespace, RBAC, DaemonSet, Service, PodMonitor) |
| `build-ebpf-image.sh` | Builds the Docker image in minikube |
| `deploy-ebpf-only.sh` | Automated deployment script |
| `prometheus-scrape-config.yaml` | Alternative Prometheus scrape config (if not using Operator) |
| `EBPF_ONLY_DEPLOYMENT.md` | Detailed documentation |
| `README.md` | This file |

## 🔧 Configuration

### Adjust Network Interfaces

Edit the ConfigMap in `minimal-ebpf-deployment.yaml`:

```yaml
excluded_interfaces:
  - "lo"
  - "docker0"
  - "cni0"
  - "flannel.1"  # Add your CNI interface
```

### Enable/Disable Protocols

```yaml
ignore_sent_requests_and_received_responses:
  http2: true   # Only monitor received requests
  ngap: false   # Monitor all NGAP messages
  pfcp: true    # Only monitor received requests
```

### Resource Limits

```yaml
resources:
  requests:
    memory: "512Mi"
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "2000m"
```

## 🔍 Troubleshooting

### Agent not starting?

```bash
# Check logs
kubectl logs -n oai-tutorial -l app=ebpf-agent --tail=100

# Common issues:
# - Kernel too old (need 5.8+)
# - Missing kernel headers
# - BPF filesystem not mounted
```

### No metrics appearing?

```bash
# Verify agent is capturing traffic
kubectl exec -n oai-tutorial -l app=ebpf-agent -- curl localhost:9950/metrics

# Check if OAI pods are running
kubectl get pods -n oai-tutorial

# Verify network interface configuration
kubectl logs -n oai-tutorial -l app=ebpf-agent | grep interface
```

### Prometheus not scraping?

```bash
# Check PodMonitor exists
kubectl get podmonitor -n oai-tutorial

# Check Prometheus targets
kubectl port-forward -n <prometheus-ns> svc/prometheus 9090:9090
# Visit http://localhost:9090/targets
```

## 📖 Full Documentation

For detailed information, see [EBPF_ONLY_DEPLOYMENT.md](./EBPF_ONLY_DEPLOYMENT.md)

## 🆘 Need Help?

1. **Check logs**: `kubectl logs -n oai-tutorial -l app=ebpf-agent -f`
2. **Verify kernel**: `minikube ssh -- uname -r` (should be 5.8+)
3. **Test metrics**: `kubectl port-forward -n oai-tutorial daemonset/ebpf-agent 9950:9950`
4. **View config**: `kubectl get cm ebpf-agent-config -n oai-tutorial -o yaml`

## 🗑️ Uninstall

```bash
kubectl delete -f minimal-ebpf-deployment.yaml
```

## ⚡ What's Next?

- **Grafana**: Import dashboards to visualize metrics
- **Alerting**: Set up Prometheus alerts for anomaly detection
- **Full DCCF**: Deploy complete DCCF stack with event correlation and NRF integration

---

**Note**: This setup includes only the eBPF monitoring component. It does not include:
- DCCF controller
- NRF registration
- Centralized event database
- DCCF service with Nadrf API

For the full DCCF stack, use the standard deployment manifests in the parent directory.
