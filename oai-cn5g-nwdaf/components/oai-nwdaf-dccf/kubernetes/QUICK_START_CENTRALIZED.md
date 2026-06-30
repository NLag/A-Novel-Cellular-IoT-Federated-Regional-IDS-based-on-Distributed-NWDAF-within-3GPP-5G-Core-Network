# Quick Start: Centralized Data Collection in DCCF

This guide shows you how to quickly enable centralized data collection in DCCF for your OAI 5G deployment.

## Overview

**Goal**: Configure DCCF to receive and store ALL network data in one place:
- ✅ Protocol events (HTTP/2, PFCP, NGAP, NAS, GTP) via eBPF
- ✅ NF events (AMF/SMF notifications) via 3GPP APIs

## Prerequisites

- Kubernetes cluster with OAI 5G core deployed
- `kubectl` access to the cluster
- DCCF already deployed and capturing protocol events

## Step 1: Update DCCF Configuration

Apply the new DCCF configuration with NF subscriptions enabled:

```bash
kubectl apply -f deployment/centralized-collection-config.yaml
```

Or manually edit the existing ConfigMap:

```bash
kubectl edit configmap dccf-config -n oai-tutorial
```

Add this section:

```yaml
nf_subscriptions:
  enabled: true
  amf:
    endpoint: "http://oai-amf-service.oai-tutorial.svc.cluster.local:80"
    events:
      - "REGISTRATION_STATE_REPORT"
      - "LOCATION_REPORT"
      - "CONNECTIVITY_STATE_REPORT"
  smf:
    endpoint: "http://oai-smf-service.oai-tutorial.svc.cluster.local:80"
    events:
      - "PDU_SES_EST"
      - "PDU_SES_REL"
      - "QOS_MON"
```

## Step 2: Restart DCCF

Restart DCCF to pick up the new configuration:

```bash
kubectl rollout restart deployment/oai-nwdaf-dccf -n oai-tutorial
```

Wait for DCCF to be ready:

```bash
kubectl rollout status deployment/oai-nwdaf-dccf -n oai-tutorial
```

## Step 3: Verify Subscriptions Created

Check DCCF logs to confirm it subscribed to AMF and SMF:

```bash
kubectl logs -n oai-tutorial deployment/oai-nwdaf-dccf --tail=50 | grep -i "subscribed"
```

Expected output:
```
INFO: Subscribing to NF events (AMF, SMF)...
INFO: Subscribed to AMF events: sub-amf-001
INFO: Subscribed to SMF events: sub-smf-001
```

## Step 4: Verify NF Events Being Received

Check that DCCF is receiving notifications:

```bash
# Watch for incoming notifications
kubectl logs -n oai-tutorial deployment/oai-nwdaf-dccf -f | grep -i "notification"
```

Expected output:
```
INFO: Received AMF notification: amf-notify-001
INFO: Stored AMF event: REGISTRATION_STATE_REPORT
INFO: Received SMF notification: smf-notify-002
INFO: Stored SMF event: PDU_SES_EST
```

## Step 5: Check Database

Verify events are being stored in the database:

```bash
# Connect to DCCF pod
kubectl exec -it -n oai-tutorial deployment/oai-nwdaf-dccf -- sh

# Check if nf_events table exists
sqlite3 /data/casmella.db "SELECT name FROM sqlite_master WHERE type='table';"

# Expected output should include:
# protocol_events
# nf_events

# Count NF events
sqlite3 /data/casmella.db "SELECT COUNT(*) FROM nf_events;"

# Show event breakdown by source
sqlite3 /data/casmella.db "SELECT source, event_type, COUNT(*) FROM nf_events GROUP BY source, event_type;"

# Show recent events
sqlite3 /data/casmella.db "SELECT * FROM nf_events ORDER BY created_at DESC LIMIT 5;"
```

## Step 6: Test API Endpoints

Test the new NF events endpoint:

```bash
# Get DCCF service URL
DCCF_URL="http://oai-nwdaf-dccf.oai-tutorial.svc.cluster.local:8081"

# From within cluster (exec into any pod)
kubectl exec -it deployment/oai-nwdaf-dccf -- sh

# Get statistics (includes both protocol and NF events)
curl "$DCCF_URL/ndccf-datamanagement/v1/stats"

# Get AMF events
curl "$DCCF_URL/ndccf-datamanagement/v1/nf-events?source=AMF&limit=10"

# Get SMF events
curl "$DCCF_URL/ndccf-datamanagement/v1/nf-events?source=SMF&limit=10"

# Get all NF events
curl "$DCCF_URL/ndccf-datamanagement/v1/nf-events?limit=20"
```

## Step 7: Update NWDAF (Optional)

If you have NWDAF SBI component, update it to fetch from DCCF:

```bash
kubectl edit configmap nwdaf-sbi-config -n oai-tutorial
```

Add/update:

```yaml
dccf:
  endpoint: "http://oai-nwdaf-dccf.oai-tutorial.svc.cluster.local:8081"
  nf_events_api: "/ndccf-datamanagement/v1/nf-events"
  protocol_events_api: "/ndccf-datamanagement/v1/data"

mongodb:
  enabled: false  # No longer needed
```

Restart NWDAF SBI:

```bash
kubectl rollout restart deployment/oai-nwdaf-sbi -n oai-tutorial
```

## Verification Checklist

- [ ] DCCF configuration updated with `nf_subscriptions.enabled: true`
- [ ] DCCF restarted and running
- [ ] Subscription logs show successful AMF subscription
- [ ] Subscription logs show successful SMF subscription
- [ ] DCCF logs show incoming AMF notifications
- [ ] DCCF logs show incoming SMF notifications
- [ ] Database has `nf_events` table
- [ ] Database contains NF events (count > 0)
- [ ] API endpoint `/nf-events?source=AMF` returns data
- [ ] API endpoint `/nf-events?source=SMF` returns data
- [ ] Statistics endpoint shows `nfEvents` section

## Troubleshooting

### No subscriptions created

**Symptoms**: Logs don't show "Subscribed to AMF/SMF events"

**Solutions**:
1. Check AMF/SMF endpoints are correct in config
2. Verify network connectivity:
   ```bash
   kubectl exec -it deployment/oai-nwdaf-dccf -- curl http://oai-amf-service:80/health
   kubectl exec -it deployment/oai-nwdaf-dccf -- curl http://oai-smf-service:80/health
   ```
3. Check if AMF/SMF support event subscriptions (3GPP TS 29.518, 29.508)

### No notifications received

**Symptoms**: Subscriptions created but no "Received AMF/SMF notification" logs

**Solutions**:
1. Verify callback URI is reachable from AMF/SMF:
   ```bash
   # From AMF pod
   curl http://oai-nwdaf-dccf:8081/health
   ```
2. Check if events are actually occurring (UE registration, PDU sessions)
3. Verify subscription hasn't expired (check validity_time)

### Database errors

**Symptoms**: "Error storing NF event" in logs

**Solutions**:
1. Check database file permissions:
   ```bash
   kubectl exec -it deployment/oai-nwdaf-dccf -- ls -la /data/casmella.db
   ```
2. Check disk space:
   ```bash
   kubectl exec -it deployment/oai-nwdaf-dccf -- df -h /data
   ```
3. Manually create table if needed (see main documentation)

### API returns empty results

**Symptoms**: `curl` returns `{"events": [], "count": 0}`

**Solutions**:
1. Verify events are in database:
   ```bash
   sqlite3 /data/casmella.db "SELECT COUNT(*) FROM nf_events;"
   ```
2. Check query parameters (source, event_type)
3. Verify data is recent (not older than retention period)

## Performance Tuning

For high-volume deployments (thousands of UEs):

```yaml
# In dccf-config.yaml
performance:
  worker_threads: 8          # Increase for more concurrent requests
  max_connections: 200       # Increase connection pool
  request_timeout: 60        # Increase for slow networks

database:
  protocol_events:
    batch_size: 500          # Larger batches for high volume
    batch_timeout: 2.0       # Longer batching window
  nf_events:
    batch_size: 100          # NF events are typically lower volume
    batch_timeout: 1.0
```

## Next Steps

1. **Set up monitoring**: Add Prometheus metrics for NF event collection
2. **Configure retention**: Adjust `retention_hours` based on storage capacity
3. **Enable analytics**: Use NWDAF to analyze both protocol and NF events
4. **Implement alerting**: Alert on missing subscriptions or failed notifications
5. **Scale if needed**: Add replicas for DCCF if handling very high load

## Additional Resources

- **Full Documentation**: See `CENTRALIZED_DATA_COLLECTION.md`
- **API Reference**: See `API_REFERENCE.md` for all endpoints
- **Configuration Examples**: See `deployment/centralized-collection-config.yaml`
- **3GPP Specs**:
  - TS 29.552 (Ndccf_DataManagement)
  - TS 29.518 (Namf_EventExposure)
  - TS 29.508 (Nsmf_EventExposure)
