# Attacker Traffic Simulator

`Attacker_Simulate` provides controlled UE-side attack traffic generation for IDS workstream 3.2. It is intended only for the local minikube/OAI lab and refuses targets that do not resolve to lab/private IPv4 ranges.

The first implementation is Go so the attacker client can be built as a single Linux binary and copied into PacketRusher pods.

## Supported Scenarios

- `mqtt-publish-flood`: rate-limited MQTT publish flood using Eclipse Paho.
- `mqtt-slowite`: SlowITe-like MQTT behavior using many long-lived low-throughput clients.
- `coap-put-flood`: rate-limited CoAP PUT flood using `go-coap`.
- `icmp-flood`: raw ICMP echo flood.
- `land-ping-flood`: raw ICMP echo with source and destination set to the target IP.
- `tcp-syn-flood`: raw TCP SYN packets.
- `random-source-tcp-syn-flood`: raw TCP SYN packets with randomized lab CIDR source IPs.
- `port-scan`: bounded TCP connect scan.
- `short-port-scan`: short scan of common lab ports.
- `sqlmap-like`: HTTP requests with SQLmap-like payloads.

Raw ICMP/TCP scenarios require a privileged pod or `CAP_NET_RAW`. The current PacketRusher chart runs privileged for GTP tunnel support, so these modes are expected to work inside PacketRusher pods.

## Safety Controls

- Target must resolve to a lab/private IPv4 range: `10.0.0.0/8`, `12.1.0.0/16`, `127.0.0.0/8`, `169.254.0.0/16`, `172.16.0.0/12`, or `192.168.0.0/16`.
- Duration is capped at `60s`.
- Rate is capped at `500` packets/messages/attempts per second.
- Slow MQTT connection count is capped at `100`.
- Port scans are capped at `10000` ports.
- Defaults are conservative: `--level smoke` runs short, low-rate attacks.

## Build

```bash
cd Attacker_Simulate
GOCACHE=/tmp/go-build-cache go build -o bin/attacker-client ./cmd/attacker-client
GOCACHE=/tmp/go-build-cache CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o bin/attacker-client-linux-amd64 ./cmd/attacker-client
```

## Local Smoke

Start the IoT receiver from the workspace root:

```bash
cd IoT_Simulate
GOCACHE=/tmp/go-build-cache go run ./cmd/iot-server \
  --bind 127.0.0.1 \
  --http-port 18093 \
  --mqtt-port 11887 \
  --coap-port 15687 \
  --out /tmp/attacker_local_server.jsonl
```

Run a controlled MQTT attack:

```bash
cd Attacker_Simulate
GOCACHE=/tmp/go-build-cache go run ./cmd/attacker-client \
  --attack mqtt-publish-flood \
  --target 127.0.0.1 \
  --source-ip 127.0.0.1 \
  --mqtt-port 11887 \
  --duration 2s \
  --rate 5 \
  --out /tmp/attacker_mqtt.jsonl
```

## PacketRusher UE Usage

Copy the Linux binary into a regional PacketRusher pod after PDU sessions are up:

```bash
kubectl -n oai-5g-core cp \
  Attacker_Simulate/bin/attacker-client-linux-amd64 \
  packetrusher-region-paris-<pod-suffix>:/tmp/attacker-client

kubectl -n oai-5g-core exec packetrusher-region-paris-<pod-suffix> -- chmod +x /tmp/attacker-client
```

Run a smoke attack through discovered UE tunnel IPs:

```bash
kubectl -n oai-5g-core exec packetrusher-region-paris-<pod-suffix> -- \
  /tmp/attacker-client \
    --attack mqtt-publish-flood \
    --level smoke \
    --target host.minikube.internal \
    --source-cidr 12.1.0.0/16 \
    --mqtt-port 11886 \
    --duration 5s \
    --rate 20 \
    --out /tmp/attacker_events_mqtt.jsonl
```

Examples:

```bash
# CoAP PUT flood
/tmp/attacker-client --attack coap-put-flood --target host.minikube.internal --source-cidr 12.1.0.0/16 --coap-port 15686

# Short port scan against common lab service ports
/tmp/attacker-client --attack short-port-scan --target host.minikube.internal --source-cidr 12.1.0.0/16

# Raw TCP SYN flood, requires CAP_NET_RAW
/tmp/attacker-client --attack tcp-syn-flood --target host.minikube.internal --source-cidr 12.1.0.0/16 --tcp-port 8088 --duration 5s --rate 20

# Random-source SYN variant, restricted to --source-cidr
/tmp/attacker-client --attack random-source-tcp-syn-flood --target host.minikube.internal --source-cidr 12.1.0.0/16 --tcp-port 8088 --duration 5s --rate 20
```

## Tests

```bash
cd Attacker_Simulate
GOCACHE=/tmp/go-build-cache go test ./...
```
