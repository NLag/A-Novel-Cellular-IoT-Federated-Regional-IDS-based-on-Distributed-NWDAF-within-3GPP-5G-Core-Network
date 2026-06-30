# IoT Traffic Simulator

`IoT_Simulate` provides a library-backed traffic generator for PacketRusher UE pods and a host-side receiver for IDS/NWDAF experiments.

The first implementation is Go so the client can be built as a single Linux binary for PacketRusher pods. Protocol behavior uses real libraries:

- HTTP: Go `net/http`
- MQTT client: Eclipse Paho Go
- MQTT broker: Mochi MQTT embedded broker
- CoAP: plgd `go-coap`

Python 3 equivalents for future tooling are the standard HTTP libraries, Eclipse Paho Python, aMQTT, and aiocoap.

## Commands

Build both binaries:

```bash
cd IoT_Simulate
GOCACHE=/tmp/go-build-cache go build -o bin/iot-server ./cmd/iot-server
GOCACHE=/tmp/go-build-cache CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o bin/iot-client-linux-amd64 ./cmd/iot-client
```

Run the host-side receiver:

```bash
./bin/iot-server --bind 0.0.0.0 --out iot_server_events.jsonl
```

Run a local smoke test:

```bash
./bin/iot-client \
  --server 127.0.0.1 \
  --source-ip 127.0.0.1 \
  --min-devices 2 \
  --max-devices 2 \
  --message-count 3 \
  --out iot_client_events.jsonl
```

Run inside a PacketRusher pod after PDU sessions are up:

```bash
./iot-client-linux-amd64 \
  --server <host-reachable-ip> \
  --source-cidr 12.1.0.0/16 \
  --min-devices 10 \
  --max-devices 20 \
  --duration 3h \
  --out /tmp/iot_client_events.jsonl
```

The client discovers UE tunnel IPs from local interfaces inside `--source-cidr` and binds each simulated IoT device process to one of those source IPs. Use `--source-ip` or `--source-ip-file` to override discovery. By default, each simulated device waits its randomized startup delay, sends traffic for 3 hours, and then exits. Use `--message-count` for bounded smoke tests.

Run all regional PacketRusher pods from the workspace root:

```bash
oai-dev-env/minikube/scripts/run-iot-simulation-all-regions.sh
```

The all-region runner builds `iot-server` and the Linux `iot-client`, starts one host receiver, copies the client into every regional PacketRusher pod, and runs one client per region. By default each region spawns 10-20 simulated IoT device processes using HTTP, MQTT, and CoAP for 3 hours.

For a smaller all-region smoke test:

```bash
oai-dev-env/minikube/scripts/run-iot-simulation-all-regions.sh \
  --min-devices 2 \
  --max-devices 2 \
  --message-count 1
```

Logs are written under `IoT_Simulate/logs/<run-id>/`, including one host receiver JSONL file and one client JSONL file per region.

## Useful Flags

Server:

- `--bind`: bind address, default `0.0.0.0`
- `--http-port`: HTTP ingest port, default `8088`
- `--mqtt-port`: MQTT broker port, default `1883`
- `--coap-port`: CoAP UDP port, default `5683`
- `--out`: JSONL event output, default `iot_server_events.jsonl`; use `-` for stdout

Client:

- `--server`: server hostname or IP, default `host.minikube.internal`
- `--source-cidr`: UE tunnel IP discovery CIDR, default `12.1.0.0/16`
- `--source-ip`: explicit source IP; may be repeated or comma-separated
- `--source-ip-file`: file with one source IP per line
- `--protocols`: protocol list, default `http,mqtt,coap`
- `--min-devices` / `--max-devices`: simulated IoT device process range, default `10` to `20`
- `--duration`: traffic generation duration per simulated device after its startup delay, default `3h`; `0` disables the duration limit
- `--message-count`: messages per simulated device, default `0`; `0` means run until `--duration`
- `--payload-min-bytes` / `--payload-max-bytes`: generated payload size range
- `--wait-sources`: time to wait for auto-discovered UE source IPs, default `60s`

## Event Logs

Both commands write JSONL records. Server records include `timestamp`, `role`, `event`, `protocol`, `remote_addr`, `topic` or `path`, `payload_size`, and `status`. Client records include `device_id`, `device_type`, `source_ip`, protocol, payload size, and send status.

For IDS validation, start `iot-server` on the host, run `iot-client` inside a regional PacketRusher pod, then confirm:

- server JSONL receives HTTP, MQTT, and CoAP records
- remote/source addresses match UE tunnel IPs when routing permits source preservation
- SMF duplication and IDS packet counters increase for the selected region

## Tests

```bash
cd IoT_Simulate
GOCACHE=/tmp/go-build-cache go test ./...
```
