#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

usage() {
  cat <<'EOF'
Usage: redeploy-stack.sh [all|core|nwdaf|nwdaf-regional|nwdaf-paris|nwdaf-lyon|nwdaf-marseille|nwdaf-toulouse|nwdaf-nice|pcf|ids|packetrusher|<custom-nf>]
EOF
}

nwdaf_rollout_args() {
  local nonce="$1"
  printf '%s\n' \
    "--set-string" "database.rolloutNonce=${nonce}" \
    "--set-string" "gateway.rolloutNonce=${nonce}" \
    "--set-string" "engine.rolloutNonce=${nonce}" \
    "--set-string" "nbiAnalytics.rolloutNonce=${nonce}" \
    "--set-string" "nbiEvents.rolloutNonce=${nonce}" \
    "--set-string" "nbiMl.rolloutNonce=${nonce}" \
    "--set-string" "sbi.rolloutNonce=${nonce}" \
    "--set-string" "mtlf.rolloutNonce=${nonce}" \
    "--set-string" "dccf.rolloutNonce=${nonce}"
}

redeploy_core() {
  local nonce="$1"
  local -a extra_args=(--set-string "global.dev.rolloutNonce=${nonce}")

  log "Deploying core release $CORE_RELEASE"
  helm_upgrade_core "${extra_args[@]}"
}

redeploy_nwdaf() {
  local nonce="$1"
  local -a extra_args

  mapfile -t extra_args < <(nwdaf_rollout_args "$nonce")
  log "Deploying NWDAF release $NWDAF_RELEASE"
  helm_upgrade_nwdaf "${extra_args[@]}"
}

redeploy_nwdaf_release() {
  local release="$1"
  local values_path="$2"
  local nonce="$3"
  local -a extra_args

  mapfile -t extra_args < <(nwdaf_rollout_args "$nonce")
  log "Deploying regional NWDAF release $release"
  helm_upgrade_nwdaf_release "$release" "$values_path" "${extra_args[@]}"
}

redeploy_nwdaf_regional() {
  redeploy_nwdaf_release "$NWDAF_PARIS_RELEASE" "$VALUES_NWDAF_PARIS" "$(timestamp_nonce)"
  redeploy_nwdaf_release "$NWDAF_LYON_RELEASE" "$VALUES_NWDAF_LYON" "$(timestamp_nonce)"
  redeploy_nwdaf_release "$NWDAF_MARSEILLE_RELEASE" "$VALUES_NWDAF_MARSEILLE" "$(timestamp_nonce)"
  redeploy_nwdaf_release "$NWDAF_TOULOUSE_RELEASE" "$VALUES_NWDAF_TOULOUSE" "$(timestamp_nonce)"
  redeploy_nwdaf_release "$NWDAF_NICE_RELEASE" "$VALUES_NWDAF_NICE" "$(timestamp_nonce)"
}

redeploy_packetrusher() {
  local nonce="$1"

  log "Deploying PacketRusher release $PACKETRUSHER_RELEASE"
  helm_upgrade_packetrusher \
    --set-string "image.repository=${PACKETRUSHER_IMAGE_REPOSITORY}" \
    --set-string "image.tag=${PACKETRUSHER_IMAGE_TAG}" \
    --set-string "image.pullPolicy=${PACKETRUSHER_IMAGE_PULL_POLICY}" \
    --set-string "dev.rolloutNonce=${nonce}"
}

redeploy_custom_nf() {
  local target="$1"
  local nonce="$2"

  load_custom_nf_metadata "$target" || die "Unknown custom NF: $target"
  log "Deploying custom NF release $NF_RELEASE"
  helm_upgrade_custom_nf "$NF_RELEASE" "$NF_CHART" "$NF_VALUES" \
    --set-string "image.repository=${NF_IMAGE_REPOSITORY}" \
    --set-string "image.tag=${NF_IMAGE_TAG}" \
    --set-string "image.pullPolicy=${NF_IMAGE_PULL_POLICY}" \
    --set-string "dev.rolloutNonce=${nonce}"
}

main() {
  local target="${1:-all}"

  case "$target" in
    -h|--help)
      usage
      exit 0
      ;;
    all|core|nwdaf|nwdaf-regional|nwdaf-paris|nwdaf-lyon|nwdaf-marseille|nwdaf-toulouse|nwdaf-nice|packetrusher)
      ;;
    *)
      if ! load_custom_nf_metadata "$target" >/dev/null 2>&1; then
        usage
        exit 1
      fi
      ;;
  esac

  ensure_minikube
  ensure_namespace

  case "$target" in
    all)
      redeploy_core "$(timestamp_nonce)"
      redeploy_nwdaf_regional
      redeploy_custom_nf pcf "$(timestamp_nonce)"
      rollout_status "$NF_DEPLOYMENT_NAME"
      redeploy_custom_nf ids "$(timestamp_nonce)"
      rollout_status_selector "$NF_DEPLOYMENT_SELECTOR"
      redeploy_packetrusher "$(timestamp_nonce)"
      rollout_status_selector "app.kubernetes.io/name=oai-packetrusher-dev,app.kubernetes.io/instance=${PACKETRUSHER_RELEASE}"
      ;;
    core)
      redeploy_core "$(timestamp_nonce)"
      if helm -n "$NAMESPACE" status "$NWDAF_PARIS_RELEASE" >/dev/null 2>&1 || \
         helm -n "$NAMESPACE" status "$NWDAF_LYON_RELEASE" >/dev/null 2>&1 || \
         helm -n "$NAMESPACE" status "$NWDAF_MARSEILLE_RELEASE" >/dev/null 2>&1 || \
         helm -n "$NAMESPACE" status "$NWDAF_TOULOUSE_RELEASE" >/dev/null 2>&1 || \
         helm -n "$NAMESPACE" status "$NWDAF_NICE_RELEASE" >/dev/null 2>&1; then
        log "Core changed; redeploying regional NWDAF so SBI subscriptions are recreated"
        redeploy_nwdaf_regional
      elif helm -n "$NAMESPACE" status "$NWDAF_RELEASE" >/dev/null 2>&1; then
        log "Core changed; redeploying compatibility NWDAF so SBI subscriptions are recreated"
        redeploy_nwdaf "$(timestamp_nonce)"
      fi
      ;;
    nwdaf)
      redeploy_nwdaf "$(timestamp_nonce)"
      ;;
    nwdaf-regional)
      redeploy_nwdaf_regional
      ;;
    nwdaf-paris)
      redeploy_nwdaf_release "$NWDAF_PARIS_RELEASE" "$VALUES_NWDAF_PARIS" "$(timestamp_nonce)"
      ;;
    nwdaf-lyon)
      redeploy_nwdaf_release "$NWDAF_LYON_RELEASE" "$VALUES_NWDAF_LYON" "$(timestamp_nonce)"
      ;;
    nwdaf-marseille)
      redeploy_nwdaf_release "$NWDAF_MARSEILLE_RELEASE" "$VALUES_NWDAF_MARSEILLE" "$(timestamp_nonce)"
      ;;
    nwdaf-toulouse)
      redeploy_nwdaf_release "$NWDAF_TOULOUSE_RELEASE" "$VALUES_NWDAF_TOULOUSE" "$(timestamp_nonce)"
      ;;
    nwdaf-nice)
      redeploy_nwdaf_release "$NWDAF_NICE_RELEASE" "$VALUES_NWDAF_NICE" "$(timestamp_nonce)"
      ;;
    packetrusher)
      redeploy_packetrusher "$(timestamp_nonce)"
      rollout_status_selector "app.kubernetes.io/name=oai-packetrusher-dev,app.kubernetes.io/instance=${PACKETRUSHER_RELEASE}"
      ;;
    *)
      redeploy_custom_nf "$target" "$(timestamp_nonce)"
      if [[ -n "${NF_DEPLOYMENT_SELECTOR:-}" ]]; then
        rollout_status_selector "$NF_DEPLOYMENT_SELECTOR"
      else
        rollout_status "$NF_DEPLOYMENT_NAME"
      fi
      ;;
  esac

  log_dev_endpoints
}

main "$@"
