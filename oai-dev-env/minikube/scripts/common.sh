#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_ROOT="$WORKSPACE_ROOT/oai-dev-env/minikube"
CHARTS_ROOT="$ENV_ROOT/charts"
VALUES_ROOT="$ENV_ROOT/values"
CUSTOM_NF_ROOT="$ENV_ROOT/custom-nfs"

MINIKUBE_PROFILE="${MINIKUBE_PROFILE:-oai-dev}"
MINIKUBE_DRIVER="${MINIKUBE_DRIVER:-docker}"
MINIKUBE_CPUS="${MINIKUBE_CPUS:-8}"
MINIKUBE_MEMORY="${MINIKUBE_MEMORY:-65536}"
MINIKUBE_DISK_SIZE="${MINIKUBE_DISK_SIZE:-60g}"
MINIKUBE_SHARED_STORAGE_MOUNT="${MINIKUBE_SHARED_STORAGE_MOUNT:-true}"
MINIKUBE_SHARED_STORAGE_HOST_PATH="${MINIKUBE_SHARED_STORAGE_HOST_PATH:-$WORKSPACE_ROOT/OAI_5G_STORAGE}"
MINIKUBE_SHARED_STORAGE_NODE_PATH="${MINIKUBE_SHARED_STORAGE_NODE_PATH:-/oai-5g-host-storage}"

NAMESPACE="${OAI_NAMESPACE:-oai-5g-core}"
HELM_TIMEOUT="${HELM_TIMEOUT:-20m}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-15m}"

CORE_RELEASE="${CORE_RELEASE:-core}"
NWDAF_RELEASE="${NWDAF_RELEASE:-nwdaf}"
NWDAF_PARIS_RELEASE="${NWDAF_PARIS_RELEASE:-nwdaf-paris}"
NWDAF_LYON_RELEASE="${NWDAF_LYON_RELEASE:-nwdaf-lyon}"
NWDAF_MARSEILLE_RELEASE="${NWDAF_MARSEILLE_RELEASE:-nwdaf-marseille}"
NWDAF_TOULOUSE_RELEASE="${NWDAF_TOULOUSE_RELEASE:-nwdaf-toulouse}"
NWDAF_NICE_RELEASE="${NWDAF_NICE_RELEASE:-nwdaf-nice}"
PACKETRUSHER_RELEASE="${PACKETRUSHER_RELEASE:-packetrusher}"
PACKETRUSHER_AMF_NGAP_NODEPORT="${PACKETRUSHER_AMF_NGAP_NODEPORT:-31412}"
NWDAF_GATEWAY_HTTP_NODEPORT="${NWDAF_GATEWAY_HTTP_NODEPORT:-30080}"

CHART_CORE="$CHARTS_ROOT/oai-5g-core-dev"
CHART_NWDAF="$CHARTS_ROOT/oai-nwdaf-dev"
CHART_PACKETRUSHER="$CHARTS_ROOT/oai-packetrusher-dev"
CHART_NF_TEMPLATE="$CHARTS_ROOT/nf-template"

VALUES_CORE="$VALUES_ROOT/core-dev.yaml"
VALUES_NWDAF="$VALUES_ROOT/nwdaf-dev.yaml"
VALUES_NWDAF_PARIS="$VALUES_ROOT/nwdaf-paris-dev.yaml"
VALUES_NWDAF_LYON="$VALUES_ROOT/nwdaf-lyon-dev.yaml"
VALUES_NWDAF_MARSEILLE="$VALUES_ROOT/nwdaf-marseille-dev.yaml"
VALUES_NWDAF_TOULOUSE="$VALUES_ROOT/nwdaf-toulouse-dev.yaml"
VALUES_NWDAF_NICE="$VALUES_ROOT/nwdaf-nice-dev.yaml"
VALUES_PACKETRUSHER="$VALUES_ROOT/packetrusher-dev.yaml"
PACKETRUSHER_CONFIG_TEMPLATE="$ENV_ROOT/packetrusher/config.template.yml"
PACKETRUSHER_CONFIG_DEFAULT="$ENV_ROOT/packetrusher/config.yml"
PACKETRUSHER_IMAGE_REPOSITORY="${PACKETRUSHER_IMAGE_REPOSITORY:-local/oai-5g-packetrusher}"
PACKETRUSHER_IMAGE_TAG="${PACKETRUSHER_IMAGE_TAG:-dev}"
PACKETRUSHER_IMAGE_PULL_POLICY="${PACKETRUSHER_IMAGE_PULL_POLICY:-Never}"

timestamp_nonce() {
  date -u +%Y%m%d%H%M%S
}

log() {
  printf '[oai-dev] %s\n' "$*"
}

die() {
  printf 'Error: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

ensure_tools() {
  local tool
  for tool in "$@"; do
    require_cmd "$tool"
  done
}

ensure_shared_storage_mount() {
  [[ "$MINIKUBE_SHARED_STORAGE_MOUNT" == "true" ]] || return 0

  if minikube -p "$MINIKUBE_PROFILE" ssh -- "mountpoint -q '$MINIKUBE_SHARED_STORAGE_NODE_PATH'" >/dev/null 2>&1; then
    return 0
  fi

  die "Shared storage mount is not active at $MINIKUBE_SHARED_STORAGE_NODE_PATH. With the Docker driver this must be set when the node container is created; recreate the profile through the dev scripts so minikube starts with --mount --mount-string=${MINIKUBE_SHARED_STORAGE_HOST_PATH}:${MINIKUBE_SHARED_STORAGE_NODE_PATH}."
}

ensure_minikube() {
  ensure_tools minikube kubectl helm
  if ! minikube -p "$MINIKUBE_PROFILE" status >/dev/null 2>&1; then
    log "Starting minikube profile $MINIKUBE_PROFILE"
    local start_args=(
      -p "$MINIKUBE_PROFILE" \
      --driver="$MINIKUBE_DRIVER" \
      --cpus="$MINIKUBE_CPUS" \
      --memory="$MINIKUBE_MEMORY" \
      --disk-size="$MINIKUBE_DISK_SIZE"
    )
    if [[ "$MINIKUBE_SHARED_STORAGE_MOUNT" == "true" ]]; then
      mkdir -p "$MINIKUBE_SHARED_STORAGE_HOST_PATH"
      start_args+=(
        --mount
        --mount-string="${MINIKUBE_SHARED_STORAGE_HOST_PATH}:${MINIKUBE_SHARED_STORAGE_NODE_PATH}"
      )
    fi
    minikube start "${start_args[@]}"
    ensure_shared_storage_mount
  elif [[ "$MINIKUBE_SHARED_STORAGE_MOUNT" == "true" ]]; then
    ensure_shared_storage_mount
  fi
}

ensure_namespace() {
  kubectl get namespace "$NAMESPACE" >/dev/null 2>&1 || kubectl create namespace "$NAMESPACE" >/dev/null
  kubectl label namespace "$NAMESPACE" \
    pod-security.kubernetes.io/enforce=privileged \
    pod-security.kubernetes.io/audit=privileged \
    pod-security.kubernetes.io/warn=privileged \
    --overwrite >/dev/null
}

use_minikube_docker_env() {
  ensure_tools minikube
  eval "$(minikube -p "$MINIKUBE_PROFILE" docker-env --shell bash)"
}

minikube_ip() {
  minikube -p "$MINIKUBE_PROFILE" ip
}

log_dev_endpoints() {
  local ip

  ip="$(minikube_ip)"
  log "Current minikube IP: $ip"
  log "PacketRusher AMF NGAP endpoint: ${ip}:${PACKETRUSHER_AMF_NGAP_NODEPORT} (SCTP)"
  log "In-cluster PacketRusher AMF NGAP service: oai-amf-ngap.${NAMESPACE}.svc.cluster.local:38412"
  log "NWDAF NBI gateway: http://${ip}:${NWDAF_GATEWAY_HTTP_NODEPORT}"
}

helm_upgrade_core() {
  helm dependency update "$CHART_CORE" >/dev/null
  helm upgrade --install "$CORE_RELEASE" "$CHART_CORE" \
    -n "$NAMESPACE" \
    --create-namespace \
    -f "$VALUES_CORE" \
    --wait \
    --timeout "$HELM_TIMEOUT" \
    "$@"
}

helm_upgrade_nwdaf() {
  helm upgrade --install "$NWDAF_RELEASE" "$CHART_NWDAF" \
    -n "$NAMESPACE" \
    --create-namespace \
    -f "$VALUES_NWDAF" \
    --wait \
    --timeout "$HELM_TIMEOUT" \
    "$@"
}

helm_upgrade_nwdaf_release() {
  local release_name="$1"
  local values_path="$2"

  shift 2

  helm upgrade --install "$release_name" "$CHART_NWDAF" \
    -n "$NAMESPACE" \
    --create-namespace \
    -f "$values_path" \
    --wait \
    --timeout "$HELM_TIMEOUT" \
    "$@"
}

helm_upgrade_packetrusher() {
  helm upgrade --install "$PACKETRUSHER_RELEASE" "$CHART_PACKETRUSHER" \
    -n "$NAMESPACE" \
    --create-namespace \
    -f "$VALUES_PACKETRUSHER" \
    --wait \
    --timeout "$HELM_TIMEOUT" \
    "$@"
}

helm_upgrade_custom_nf() {
  local release_name="$1"
  local chart_path="$2"
  local values_path="$3"

  shift 3

  helm upgrade --install "$release_name" "$chart_path" \
    -n "$NAMESPACE" \
    --create-namespace \
    -f "$values_path" \
    --wait \
    --timeout "$HELM_TIMEOUT" \
    "$@"
}

rollout_status() {
  local deployment_name="$1"
  kubectl -n "$NAMESPACE" rollout status "deployment/${deployment_name}" --timeout="$ROLLOUT_TIMEOUT"
}

rollout_status_selector() {
  local selector="$1"
  kubectl -n "$NAMESPACE" rollout status deployment -l "$selector" --timeout="$ROLLOUT_TIMEOUT"
}

canonical_core_nf() {
  case "$1" in
    amf|oai-amf) echo "oai-amf" ;;
    ausf|oai-ausf) echo "oai-ausf" ;;
    lmf|oai-lmf) echo "oai-lmf" ;;
    nrf|oai-nrf) echo "oai-nrf" ;;
    nssf|oai-nssf) echo "oai-nssf" ;;
    smf|oai-smf) echo "oai-smf" ;;
    traffic-server|trf-gen-cn5g|oai-traffic-server) echo "oai-traffic-server" ;;
    udm|oai-udm) echo "oai-udm" ;;
    udr|oai-udr) echo "oai-udr" ;;
    upf|oai-upf) echo "oai-upf" ;;
    *) return 1 ;;
  esac
}

canonical_nwdaf_component() {
  case "$1" in
    database|oai-nwdaf-database) echo "database" ;;
    gateway|nbi-gateway|oai-nwdaf-nbi-gateway) echo "gateway" ;;
    engine|oai-nwdaf-engine) echo "engine" ;;
    nbi-analytics|oai-nwdaf-nbi-analytics) echo "nbi-analytics" ;;
    nbi-events|oai-nwdaf-nbi-events) echo "nbi-events" ;;
    nbi-ml|oai-nwdaf-nbi-ml) echo "nbi-ml" ;;
    sbi|oai-nwdaf-sbi) echo "sbi" ;;
    mtlf|oai-nwdaf-mtlf|oai-nwdaf-mtlf-service) echo "mtlf" ;;
    dccf|oai-nwdaf-dccf) echo "dccf" ;;
    *) return 1 ;;
  esac
}

canonical_packetrusher() {
  case "$1" in
    packetrusher|oai-packetrusher|oai-5g-packetrusher) echo "oai-5g-packetrusher" ;;
    *) return 1 ;;
  esac
}

custom_nf_metadata_path() {
  local target="$1"
  local candidate

  if [[ -f "$CUSTOM_NF_ROOT/${target}.env" ]]; then
    echo "$CUSTOM_NF_ROOT/${target}.env"
    return 0
  fi

  if [[ "$target" != oai-* ]] && [[ -f "$CUSTOM_NF_ROOT/oai-${target}.env" ]]; then
    echo "$CUSTOM_NF_ROOT/oai-${target}.env"
    return 0
  fi

  return 1
}

clear_custom_nf_metadata() {
  unset CUSTOM_NF_METADATA_PATH
  unset NF_NAME NF_RELEASE NF_CHART NF_VALUES NF_IMAGE_REPOSITORY
  unset NF_IMAGE_TAG NF_IMAGE_PULL_POLICY NF_DEPLOYMENT_NAME NF_DEPLOYMENT_SELECTOR
  unset NF_BUILD_CONTEXT NF_BUILD_DOCKERFILE NF_BUILD_TARGET
}

load_custom_nf_metadata() {
  local metadata_path="$1"

  clear_custom_nf_metadata
  CUSTOM_NF_METADATA_PATH="$(custom_nf_metadata_path "$metadata_path")" || return 1
  # shellcheck disable=SC1090
  source "$CUSTOM_NF_METADATA_PATH"

  : "${NF_NAME:?Missing NF_NAME in $CUSTOM_NF_METADATA_PATH}"
  : "${NF_RELEASE:=${NF_NAME#oai-}}"
  : "${NF_CHART:=$CHARTS_ROOT/$NF_NAME}"
  : "${NF_VALUES:=$VALUES_ROOT/${NF_RELEASE}-dev.yaml}"
  : "${NF_IMAGE_REPOSITORY:=local/${NF_NAME}}"
  : "${NF_IMAGE_TAG:=dev}"
  : "${NF_IMAGE_PULL_POLICY:=Never}"
  : "${NF_DEPLOYMENT_NAME:=$NF_NAME}"
  : "${NF_DEPLOYMENT_SELECTOR:=}"
  : "${NF_BUILD_CONTEXT:=}"
  : "${NF_BUILD_DOCKERFILE:=}"
  : "${NF_BUILD_TARGET:=${NF_NAME#oai-}}"
}

canonical_custom_nf() {
  load_custom_nf_metadata "$1" || return 1
  echo "$NF_NAME"
}

list_custom_nf_names() {
  [[ -d "$CUSTOM_NF_ROOT" ]] || return 0
  find "$CUSTOM_NF_ROOT" -maxdepth 1 -type f -name '*.env' -printf '%f\n' | \
    sed 's/\.env$//' | sort
}

core_nf_image_repo() {
  local nf="$1"
  case "$nf" in
    oai-traffic-server) echo "local/oai-traffic-server" ;;
    *) echo "local/${nf}" ;;
  esac
}

nwdaf_component_name() {
  case "$1" in
    database) echo "oai-nwdaf-database" ;;
    gateway) echo "oai-nwdaf-nbi-gateway" ;;
    engine) echo "oai-nwdaf-engine" ;;
    nbi-analytics) echo "oai-nwdaf-nbi-analytics" ;;
    nbi-events) echo "oai-nwdaf-nbi-events" ;;
    nbi-ml) echo "oai-nwdaf-nbi-ml" ;;
    sbi) echo "oai-nwdaf-sbi" ;;
    mtlf) echo "oai-nwdaf-mtlf" ;;
    dccf) echo "oai-nwdaf-dccf" ;;
    *) return 1 ;;
  esac
}

nwdaf_component_values_key() {
  case "$1" in
    database) echo "database" ;;
    gateway) echo "gateway" ;;
    engine) echo "engine" ;;
    nbi-analytics) echo "nbiAnalytics" ;;
    nbi-events) echo "nbiEvents" ;;
    nbi-ml) echo "nbiMl" ;;
    sbi) echo "sbi" ;;
    mtlf) echo "mtlf" ;;
    dccf) echo "dccf" ;;
    *) return 1 ;;
  esac
}

nwdaf_image_repo() {
  local component="$1"
  case "$component" in
    dccf) echo "local/oai-nwdaf-dccf" ;;
    *) echo "local/$(nwdaf_component_name "$component")" ;;
  esac
}
