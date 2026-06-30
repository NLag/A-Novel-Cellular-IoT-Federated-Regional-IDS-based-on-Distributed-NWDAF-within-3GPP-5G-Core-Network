#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

usage() {
  cat <<'EOF'
Usage: redeploy-nf.sh [--debug] <nf>

Examples:
  redeploy-nf.sh amf
  redeploy-nf.sh --debug smf
  redeploy-nf.sh ids
  redeploy-nf.sh sbi
  redeploy-nf.sh packetrusher
EOF
}

main() {
  local debug_build="false"
  local target=""
  local nonce tag nf image_repo component value_key deployment_name

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --debug)
        debug_build="true"
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        target="$1"
        shift
        ;;
    esac
  done

  [[ -n "$target" ]] || {
    usage
    exit 1
  }

  ensure_minikube
  ensure_namespace
  nonce="$(timestamp_nonce)"

  if nf="$(canonical_core_nf "$target" 2>/dev/null)"; then
    if [[ "$debug_build" == "true" && "$nf" == "oai-traffic-server" ]]; then
      die "--debug is not supported for $nf"
    fi
    tag="dev"
    [[ "$debug_build" == "true" ]] && tag="debug-dev"
    image_repo="$(core_nf_image_repo "$nf")"
    log "Redeploying $nf with ${image_repo}:${tag}"
    helm_upgrade_core \
      --set-string "${nf}.nfimage.repository=${image_repo}" \
      --set-string "${nf}.nfimage.version=${tag}" \
      --set-string "${nf}.nfimage.pullPolicy=Never" \
      --set-string "${nf}.dev.rolloutNonce=${nonce}"
    rollout_status "$nf"

    if [[ "$nf" == "oai-amf" || "$nf" == "oai-smf" ]]; then
      log "AMF/SMF restarted; redeploy regional NWDAF next to recreate subscriptions: $ENV_ROOT/scripts/redeploy-stack.sh nwdaf-regional"
    fi
    exit 0
  fi

  [[ "$debug_build" == "false" ]] || die "--debug is only supported for core NFs"

  if component="$(canonical_nwdaf_component "$target" 2>/dev/null)"; then
    value_key="$(nwdaf_component_values_key "$component")"
    deployment_name="$(nwdaf_component_name "$component")"
    log "Redeploying $deployment_name"

    case "$component" in
      database|gateway)
        helm_upgrade_nwdaf --set-string "${value_key}.rolloutNonce=${nonce}"
        ;;
      *)
        image_repo="$(nwdaf_image_repo "$component")"
        helm_upgrade_nwdaf \
          --set-string "${value_key}.image.repository=${image_repo}" \
          --set-string "${value_key}.image.tag=dev" \
          --set-string "${value_key}.image.pullPolicy=Never" \
          --set-string "${value_key}.rolloutNonce=${nonce}"
        ;;
    esac

    rollout_status "$deployment_name"
    exit 0
  fi

  if canonical_packetrusher "$target" >/dev/null 2>&1; then
    log "Redeploying PacketRusher with ${PACKETRUSHER_IMAGE_REPOSITORY}:${PACKETRUSHER_IMAGE_TAG}"
    helm_upgrade_packetrusher \
      --set-string "image.repository=${PACKETRUSHER_IMAGE_REPOSITORY}" \
      --set-string "image.tag=${PACKETRUSHER_IMAGE_TAG}" \
      --set-string "image.pullPolicy=${PACKETRUSHER_IMAGE_PULL_POLICY}" \
      --set-string "dev.rolloutNonce=${nonce}"
    rollout_status_selector "app.kubernetes.io/name=oai-packetrusher-dev,app.kubernetes.io/instance=${PACKETRUSHER_RELEASE}"
    exit 0
  fi

  if load_custom_nf_metadata "$target" 2>/dev/null; then
    log "Redeploying $NF_NAME with ${NF_IMAGE_REPOSITORY}:${NF_IMAGE_TAG}"
    helm_upgrade_custom_nf "$NF_RELEASE" "$NF_CHART" "$NF_VALUES" \
      --set-string "image.repository=${NF_IMAGE_REPOSITORY}" \
      --set-string "image.tag=${NF_IMAGE_TAG}" \
      --set-string "image.pullPolicy=${NF_IMAGE_PULL_POLICY}" \
      --set-string "dev.rolloutNonce=${nonce}"
    if [[ -n "${NF_DEPLOYMENT_SELECTOR:-}" ]]; then
      rollout_status_selector "$NF_DEPLOYMENT_SELECTOR"
    else
      rollout_status "$NF_DEPLOYMENT_NAME"
    fi
    exit 0
  fi

  die "Unknown NF or component: $target"
}

main "$@"
