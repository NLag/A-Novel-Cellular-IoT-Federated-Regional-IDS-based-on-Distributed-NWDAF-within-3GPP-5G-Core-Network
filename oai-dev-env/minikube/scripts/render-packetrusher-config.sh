#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

usage() {
  cat <<'EOF'
Usage: render-packetrusher-config.sh --bind-ip <ip> [--amf-ip <ip>] [--amf-port <port>] [--output <path>]

Examples:
  render-packetrusher-config.sh --bind-ip 192.168.49.2
  render-packetrusher-config.sh --bind-ip 192.168.49.10 --amf-ip 192.168.49.2 --output /tmp/packetrusher.yml
EOF
}

main() {
  local bind_ip=""
  local amf_ip=""
  local amf_port="$PACKETRUSHER_AMF_NGAP_NODEPORT"
  local output_path="$PACKETRUSHER_CONFIG_DEFAULT"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --bind-ip)
        bind_ip="${2:-}"
        shift 2
        ;;
      --amf-ip)
        amf_ip="${2:-}"
        shift 2
        ;;
      --amf-port)
        amf_port="${2:-}"
        shift 2
        ;;
      --output)
        output_path="${2:-}"
        shift 2
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        usage
        exit 1
        ;;
    esac
  done

  [[ -n "$bind_ip" ]] || die "--bind-ip is required"
  [[ -f "$PACKETRUSHER_CONFIG_TEMPLATE" ]] || die "Missing PacketRusher template: $PACKETRUSHER_CONFIG_TEMPLATE"

  if [[ -z "$amf_ip" ]]; then
    ensure_tools minikube
    ensure_minikube
    amf_ip="$(minikube_ip)"
  fi

  mkdir -p "$(dirname "$output_path")"
  sed \
    -e "s/__PACKETRUSHER_BIND_IP__/${bind_ip}/g" \
    -e "s/__AMF_NODE_IP__/${amf_ip}/g" \
    -e "s/__AMF_NODE_PORT__/${amf_port}/g" \
    "$PACKETRUSHER_CONFIG_TEMPLATE" > "$output_path"

  log "Wrote PacketRusher config to $output_path"
  log "AMF NGAP endpoint: ${amf_ip}:${amf_port}"
  log "For --dedicatedGnb, reserve sequential N2/N3 IPs starting at ${bind_ip}"
}

main "$@"
