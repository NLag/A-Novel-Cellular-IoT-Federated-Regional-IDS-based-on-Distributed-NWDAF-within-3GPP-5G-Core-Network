# eBPF-Only Deployment Guide for OAI 5G Core

This guide explains how to deploy **only the eBPF monitoring component** from DCCF to your minikube cluster with Prometheus metrics export.

## What's Included

- ✅ eBPF agent for protocol monitoring (HTTP/2, gNB-AMF, NGAP, PFCP)
- ✅ Prometheus metrics export on port 9950
- ✅ Automatic discovery of 5G NF pods
- ❌ No DCCF controller
- ❌ No NRF registration
- ❌ No centralized event database

## Prerequisites

1. **Minikube cluster with OAI 5G Core installed**
2. **Docker image built** - The eBPF agent image needs to be available
3. **Kernel requirements** - Your kernel must support eBPF (kernel 5.8+)
4. **Prometheus** - Either Prometheus Operator or standalone Prometheus

## Step 1: Build the eBPF Agent Image

The agent is part of the main DCCF image. Build it in your minikube environment:

```bash
# Use minikube's Docker daemon
eval $(minikube docker-env)

# Navigate to dccf directory
cd /home/dave/oai/newsetup/oai-cn5g-nwdaf/components/oai-nwdaf-dccf

# Build BCC base image first (if not already built)
docker build -t casmella-bcc-python:local -f docker/dockerBCC/Dockerfile .

# Build the agent image
docker build -t oai-nwdaf-dccf:latest -f docker/Dockerfile .
```

## Step 2: Verify Kernel Support

Check if your minikube node supports eBPF:

```bash
# SSH into minikube
minikube ssh

# Check kernel version (should be 5.8+)
uname -r

# Check if BPF filesystem is mounted
mount | grep bpf

# Check debugfs
ls /sys/kernel/debug

exit
```

## Step 3: Deploy the eBPF Agent

Deploy the minimal eBPF monitoring setup:

```bash
# Apply the complete deployment
kubectl apply -f /home/dave/oai/newsetup/oai-cn5g-nwdaf/components/oai-nwdaf-dccf/kubernetes/minimal-ebpf-deployment.yaml
```

This will create:
- Namespace: `oai-tutorial` (if not exists)
- ServiceAccount + RBAC
- ConfigMaps (agent-config, openapi-operations)
- DaemonSet (one agent per node)
- Service for metrics
- PodMonitor for Prometheus scraping

## Step 4: Verify Deployment

Check the agent is running:

```bash
# Check DaemonSet status
kubectl get daemonset ebpf-agent -n oai-tutorial

# Check pod status
kubectl get pods -n oai-tutorial -l app=ebpf-agent

# Check agent logs
kubectl logs -n oai-tutorial -l app=ebpf-agent --tail=50

# Verify metrics endpoint
kubectl exec -n oai-tutorial -l app=ebpf-agent -- curl -s localhost:9950/metrics | head -20
```

## Step 5: Configure Prometheus

### Option A: Using Prometheus Operator (Recommended)

The deployment includes a PodMonitor resource. Just verify it's created:

```bash
# Check PodMonitor
kubectl get podmonitor ebpf-agent-monitor -n oai-tutorial

# If your Prometheus uses a different release label, edit the PodMonitor:
kubectl edit podmonitor ebpf-agent-monitor -n oai-tutorial
# Change the "release" label to match your Prometheus
```

### Option B: Using Standalone Prometheus

Add this scrape config to your Prometheus configuration:

```yaml
scrape_configs:
  - job_name: 'ebpf-agent'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - oai-tutorial
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app]
        action: keep
        regex: ebpf-agent
      - source_labels: [__meta_kubernetes_pod_ip]
        action: replace
        target_label: __address__
        replacement: ${1}:9950
      - source_labels: [__meta_kubernetes_pod_name]
        action: replace
        target_label: pod
      - source_labels: [__meta_kubernetes_namespace]
        action: replace
        target_label: namespace
    scrape_interval: 15s
    metrics_path: /metrics
```

Then reload Prometheus:

```bash
# If Prometheus is in the monitoring namespace
kubectl rollout restart deployment prometheus-server -n monitoring
```

## Step 6: Access Metrics in Prometheus

Once Prometheus is scraping, you can query metrics:

```promql
# Request rate per NF service
rate(casmella_requests_total[5m])

# Request latency (p95)
histogram_quantile(0.95, rate(casmella_request_duration_seconds_bucket[5m]))

# Active connections
casmella_active_connections

# Protocol-specific metrics
rate(casmella_http2_requests_total[5m])
rate(casmella_ngap_messages_total[5m])
rate(casmella_pfcp_messages_total[5m])
```

## Customization

### Adjust Resource Limits

Edit the DaemonSet in `minimal-ebpf-deployment.yaml`:

```yaml
resources:
  requests:
    memory: "512Mi"    # Increase if needed
    cpu: "500m"
  limits:
    memory: "2Gi"
    cpu: "2000m"
```

### Enable Database (Optional)

If you want local event storage on each node:

```yaml
# In ebpf-agent-config ConfigMap
database:
  enabled: true
  path: /data/casmella.db
  retention_hours: 24
```

Then add a volume mount:

```yaml
# In DaemonSet volumes
- name: database-storage
  hostPath:
    path: /var/lib/ebpf-agent
    type: DirectoryOrCreate

# In volumeMounts
- name: database-storage
  mountPath: /data
```

### Monitor HTTPS Traffic

Enable HTTPS monitoring (requires SSL library hooks):

```yaml
# In agent-config.yaml
monitor_https: true
```

### Adjust Network Interfaces

Configure which interfaces to monitor:

```yaml
# In agent-config.yaml
excluded_interfaces:
  - "lo"
  - "docker0"
  - "cni0"
  - "flannel.1"  # Add your CNI interfaces

# For N6 interface monitoring (UPF data plane)
n6_interface_names:
  - "eth1"  # Your N6 interface
```

## Troubleshooting

### Agent Not Starting

Check logs for errors:

```bash
kubectl logs -n oai-tutorial -l app=ebpf-agent --tail=100
```

Common issues:
- **Permission denied**: Ensure privileged mode and capabilities are set
- **BPF not supported**: Kernel too old or BPF not enabled
- **Missing debugfs**: Mount debugfs with `mount -t debugfs none /sys/kernel/debug`

### No Metrics Available

```bash
# Check if metrics endpoint responds
kubectl port-forward -n oai-tutorial daemonset/ebpf-agent 9950:9950

# In another terminal
curl http://localhost:9950/metrics
```

If empty, the agent may not be capturing traffic. Check:
- Network interfaces configuration
- OAI pods are running in the same namespace
- Traffic is actually flowing through the monitored interfaces

### High Resource Usage

eBPF monitoring can be resource-intensive. Reduce load:

```yaml
# In agent-config.yaml
use_xdp: false  # Use TC hooks instead (less aggressive)

# Filter protocols
ignore_sent_requests_and_received_responses:
  http2: true
  ngap: true
  pfcp: true
```

### Prometheus Not Scraping

Check service discovery:

```bash
# Port forward to Prometheus
kubectl port-forward -n <prometheus-namespace> svc/prometheus 9090:9090

# Check targets at http://localhost:9090/targets
# Look for ebpf-agent targets
```

If using PodMonitor, verify:
```bash
# Check if Prometheus Operator is watching oai-tutorial namespace
kubectl get prometheus -A -o yaml | grep -A 5 podMonitorNamespaceSelector
```

## Metrics Reference

### Core Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `casmella_requests_total` | Counter | Total requests by NF, service, operation |
| `casmella_request_duration_seconds` | Histogram | Request latency distribution |
| `casmella_active_connections` | Gauge | Current active connections |
| `casmella_errors_total` | Counter | Failed requests/responses |

### Protocol-Specific Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `casmella_http2_requests_total` | Counter | HTTP/2 requests (SBI) |
| `casmella_http2_response_status_total` | Counter | HTTP responses by status code |
| `casmella_ngap_messages_total` | Counter | NGAP messages (gNB↔AMF) |
| `casmella_pfcp_messages_total` | Counter | PFCP messages (SMF↔UPF) |

### Labels

All metrics include:
- `nf_name`: Network Function name (pod name)
- `nf_type`: NF type (AMF, SMF, UPF, etc.)
- `service`: Service name from OpenAPI
- `operation`: Operation name (e.g., N1N2MessageTransfer)
- `method`: HTTP method or protocol message type
- `node`: Kubernetes node name

## Uninstall

To remove the eBPF monitoring:

```bash
kubectl delete -f /home/dave/oai/newsetup/oai-cn5g-nwdaf/components/oai-nwdaf-dccf/kubernetes/minimal-ebpf-deployment.yaml
```

## Next Steps

- **Grafana Dashboards**: Import dashboards to visualize metrics
- **Alerting**: Set up Prometheus alerts for anomaly detection
- **Full DCCF**: Deploy the complete DCCF stack with event correlation

## Support

For issues or questions:
- Check logs: `kubectl logs -n oai-tutorial -l app=ebpf-agent`
- Review configuration: `kubectl get cm -n oai-tutorial ebpf-agent-config -o yaml`
- Verify eBPF programs: `minikube ssh -- sudo bpftool prog list`
