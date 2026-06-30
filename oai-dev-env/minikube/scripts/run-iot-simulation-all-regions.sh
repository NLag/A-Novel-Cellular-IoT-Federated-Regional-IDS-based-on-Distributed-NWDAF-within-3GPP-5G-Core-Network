#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

IOT_ROOT="$WORKSPACE_ROOT/IoT_Simulate"
IOT_BIN_DIR="$IOT_ROOT/bin"
IOT_SERVER_BIN="$IOT_BIN_DIR/iot-server"
IOT_CLIENT_BIN="$IOT_BIN_DIR/iot-client-linux-amd64"

RUN_ID="${RUN_ID:-$(date -u +%Y%m%d%H%M%S)}"
LOG_DIR="${LOG_DIR:-$IOT_ROOT/logs/$RUN_ID}"
GOCACHE_DIR="${GOCACHE:-/tmp/go-build-cache}"

REGIONS_CSV="${REGIONS:-region-paris,region-lyon,region-marseille,region-toulouse,region-nice}"
SERVER_HOST="${IOT_SERVER_HOST:-host.minikube.internal}"
SOURCE_CIDR="${IOT_SOURCE_CIDR:-12.1.0.0/16}"
PROTOCOLS="${IOT_PROTOCOLS:-http,mqtt,coap}"
MIN_DEVICES="${IOT_MIN_DEVICES:-10}"
MAX_DEVICES="${IOT_MAX_DEVICES:-20}"
MESSAGE_COUNT="${IOT_MESSAGE_COUNT:-0}"
DURATION="${IOT_DURATION:-3h}"
PAYLOAD_MIN_BYTES="${IOT_PAYLOAD_MIN_BYTES:-64}"
PAYLOAD_MAX_BYTES="${IOT_PAYLOAD_MAX_BYTES:-512}"
HTTP_PORT="${IOT_HTTP_PORT:-18092}"
MQTT_PORT="${IOT_MQTT_PORT:-11886}"
COAP_PORT="${IOT_COAP_PORT:-15686}"
WAIT_SOURCES="${IOT_WAIT_SOURCES:-60s}"
START_SERVER=true
BUILD_BINARIES=true

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Run the IoT simulator client in every regional PacketRusher pod.

Options:
  --regions <csv>              Regions to run, default: $REGIONS_CSV
  --server-host <host>         IoT receiver host from pod, default: $SERVER_HOST
  --source-cidr <cidr>         UE tunnel source CIDR, default: $SOURCE_CIDR
  --protocols <csv>            Protocols for clients, default: $PROTOCOLS
  --min-devices <n>            Minimum devices per region, default: $MIN_DEVICES
  --max-devices <n>            Maximum devices per region, default: $MAX_DEVICES
  --message-count <n>          Messages per simulated device; 0 means run until duration, default: $MESSAGE_COUNT
  --duration <duration>        Traffic generation duration per simulated device, default: $DURATION
  --payload-min-bytes <n>      Minimum payload bytes, default: $PAYLOAD_MIN_BYTES
  --payload-max-bytes <n>      Maximum payload bytes, default: $PAYLOAD_MAX_BYTES
  --http-port <n>              Host HTTP port, default: $HTTP_PORT
  --mqtt-port <n>              Host MQTT port, default: $MQTT_PORT
  --coap-port <n>              Host CoAP port, default: $COAP_PORT
  --wait-sources <duration>    Wait for UE source IP discovery, default: $WAIT_SOURCES
  --log-dir <path>             Local log directory, default: $LOG_DIR
  --no-server                  Do not start a local iot-server
  --skip-build                 Reuse existing IoT_Simulate/bin binaries
  -h, --help                   Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --regions) REGIONS_CSV="$2"; shift 2 ;;
    --server-host) SERVER_HOST="$2"; shift 2 ;;
    --source-cidr) SOURCE_CIDR="$2"; shift 2 ;;
    --protocols) PROTOCOLS="$2"; shift 2 ;;
    --min-devices) MIN_DEVICES="$2"; shift 2 ;;
    --max-devices) MAX_DEVICES="$2"; shift 2 ;;
    --message-count) MESSAGE_COUNT="$2"; shift 2 ;;
    --duration) DURATION="$2"; shift 2 ;;
    --payload-min-bytes) PAYLOAD_MIN_BYTES="$2"; shift 2 ;;
    --payload-max-bytes) PAYLOAD_MAX_BYTES="$2"; shift 2 ;;
    --http-port) HTTP_PORT="$2"; shift 2 ;;
    --mqtt-port) MQTT_PORT="$2"; shift 2 ;;
    --coap-port) COAP_PORT="$2"; shift 2 ;;
    --wait-sources) WAIT_SOURCES="$2"; shift 2 ;;
    --log-dir) LOG_DIR="$2"; shift 2 ;;
    --no-server) START_SERVER=false; shift ;;
    --skip-build) BUILD_BINARIES=false; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done

ensure_tools kubectl go
mkdir -p "$IOT_BIN_DIR" "$LOG_DIR"

if [[ "$BUILD_BINARIES" == "true" ]]; then
  log "Building IoT simulator binaries"
  (
    cd "$IOT_ROOT"
    GOCACHE="$GOCACHE_DIR" go build -o "$IOT_SERVER_BIN" ./cmd/iot-server
    GOCACHE="$GOCACHE_DIR" CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o "$IOT_CLIENT_BIN" ./cmd/iot-client
  )
fi

[[ -x "$IOT_CLIENT_BIN" ]] || die "Missing executable client binary: $IOT_CLIENT_BIN"
if [[ "$START_SERVER" == "true" ]]; then
  [[ -x "$IOT_SERVER_BIN" ]] || die "Missing executable server binary: $IOT_SERVER_BIN"
fi

SERVER_LOG="$LOG_DIR/iot_server_events.jsonl"
SERVER_STDOUT="$LOG_DIR/iot_server_stdout.log"
server_pid=""

cleanup() {
  if [[ -n "$server_pid" ]] && kill -0 "$server_pid" >/dev/null 2>&1; then
    log "Stopping iot-server pid=$server_pid"
    kill "$server_pid" >/dev/null 2>&1 || true
    wait "$server_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

if [[ "$START_SERVER" == "true" ]]; then
  log "Starting host iot-server on HTTP=$HTTP_PORT MQTT=$MQTT_PORT CoAP=$COAP_PORT"
  "$IOT_SERVER_BIN" \
    --bind 0.0.0.0 \
    --http-port "$HTTP_PORT" \
    --mqtt-port "$MQTT_PORT" \
    --coap-port "$COAP_PORT" \
    --out "$SERVER_LOG" >"$SERVER_STDOUT" 2>&1 &
  server_pid="$!"
  sleep 2
  if ! kill -0 "$server_pid" >/dev/null 2>&1; then
    sed -n '1,120p' "$SERVER_STDOUT" >&2
    die "iot-server failed to start"
  fi
fi

IFS=',' read -r -a regions <<<"$REGIONS_CSV"
declare -A pod_by_region
declare -A pid_by_region
declare -A remote_log_by_region

for region in "${regions[@]}"; do
  region="$(printf '%s' "$region" | xargs)"
  [[ -n "$region" ]] || continue

  selector="app.kubernetes.io/name=oai-packetrusher-dev,app.kubernetes.io/instance=${PACKETRUSHER_RELEASE},app.kubernetes.io/component=packetrusher-region,app.kubernetes.io/region=${region}"
  pod="$(kubectl -n "$NAMESPACE" get pod -l "$selector" -o jsonpath='{.items[0].metadata.name}')"
  [[ -n "$pod" ]] || die "No PacketRusher pod found for region $region"

  pod_by_region["$region"]="$pod"
  remote_client="/tmp/iot-client"
  remote_log="/tmp/iot_client_events_${region}_${RUN_ID}.jsonl"
  remote_log_by_region["$region"]="$remote_log"

  log "Copying iot-client to $region pod=$pod"
  kubectl -n "$NAMESPACE" cp "$IOT_CLIENT_BIN" "$pod:$remote_client" >/dev/null
  kubectl -n "$NAMESPACE" exec "$pod" -- chmod +x "$remote_client" >/dev/null

  log "Starting IoT client region=$region pod=$pod"
  (
    kubectl -n "$NAMESPACE" exec "$pod" -- "$remote_client" \
      --server "$SERVER_HOST" \
      --source-cidr "$SOURCE_CIDR" \
      --protocols "$PROTOCOLS" \
      --min-devices "$MIN_DEVICES" \
      --max-devices "$MAX_DEVICES" \
      --message-count "$MESSAGE_COUNT" \
      --duration "$DURATION" \
      --payload-min-bytes "$PAYLOAD_MIN_BYTES" \
      --payload-max-bytes "$PAYLOAD_MAX_BYTES" \
      --wait-sources "$WAIT_SOURCES" \
      --http-port "$HTTP_PORT" \
      --mqtt-port "$MQTT_PORT" \
      --coap-port "$COAP_PORT" \
      --out "$remote_log"
  ) >"$LOG_DIR/${region}_kubectl_exec.log" 2>&1 &
  pid_by_region["$region"]="$!"
done

failed=0
for region in "${!pid_by_region[@]}"; do
  pid="${pid_by_region[$region]}"
  if wait "$pid"; then
    log "IoT client completed region=$region"
  else
    log "IoT client failed region=$region; see $LOG_DIR/${region}_kubectl_exec.log"
    failed=1
  fi
done

for region in "${regions[@]}"; do
  region="$(printf '%s' "$region" | xargs)"
  [[ -n "$region" ]] || continue
  pod="${pod_by_region[$region]}"
  remote_log="${remote_log_by_region[$region]}"
  local_log="$LOG_DIR/${region}_client_events.jsonl"
  log "Collecting client log region=$region"
  kubectl -n "$NAMESPACE" cp "$pod:$remote_log" "$local_log" >/dev/null || true
done

log "All-region IoT simulation logs: $LOG_DIR"
if [[ -f "$SERVER_LOG" ]]; then
  log "Server event count by protocol:"
  for protocol in http mqtt coap; do
    count="$(rg -c "\"protocol\":\"${protocol}\"" "$SERVER_LOG" 2>/dev/null || true)"
    printf '  %s: %s\n' "$protocol" "${count:-0}"
  done
fi

exit "$failed"
