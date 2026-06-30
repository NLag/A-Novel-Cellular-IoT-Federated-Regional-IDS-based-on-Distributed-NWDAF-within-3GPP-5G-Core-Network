# csv-replay

## Build

```bash
cd /home/dave/oai/newsetup/simulation/PacketRusher
/usr/local/go/bin/go build -o csv-replay ./cmd/csv-replay
```

## Refresh AMF IP (run if AMF pod restarted)

```bash
AMF_IP=$(kubectl get pod -n oai-tutorial -l app.kubernetes.io/name=oai-amf -o jsonpath='{.items[0].status.podIP}')
sed -i "s/^  - ip: \".*\"$/  - ip: \"$AMF_IP\"/" /home/dave/oai/newsetup/simulation/PacketRusher/config/config.yml
```

## Clean stale processes

```bash
sudo pkill -9 packetrusher 2>/dev/null
sudo pkill -9 csv-replay 2>/dev/null
sudo pkill -9 nr-gnb 2>/dev/null
```

## Run (first 10 UEs)

```bash
cd /home/dave/oai/newsetup/simulation/PacketRusher
sudo ./csv-replay -n 100 \
  --csv /home/dave/oai/newsetup/simulation/runner/extracted/dataset/1jour/extracted_data.csv
```

## Run with custom flags

```bash
cd /home/dave/oai/newsetup/simulation/PacketRusher
sudo ./csv-replay -n 100 \
  --csv /home/dave/oai/newsetup/simulation/runner/extracted/dataset/1jour/extracted_data.csv \
  --loglevel info
```

## Tail logs to file

```bash
cd /home/dave/oai/newsetup/simulation/PacketRusher
sudo ./csv-replay -n 100 \
  --csv /home/dave/oai/newsetup/simulation/runner/extracted/dataset/1jour/extracted_data.csv \
  2>&1 | tee /tmp/csv-replay.log
```

## Filter CSV scheduler events only

```bash
grep "\[CSV\]" /tmp/csv-replay.log
```

## Verify in AMF

```bash
kubectl logs -n oai-tutorial deployment/oai-amf -f | grep -E "00101000000000[0-9]"
```

## Verify in SMF

```bash
kubectl logs -n oai-tutorial deployment/oai-smf -f | grep -iE "pdu session"
```
