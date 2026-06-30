#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

main() {
  local release custom_nf
  local -a releases=("$CORE_RELEASE" "$NWDAF_RELEASE" "gnb" "nrue")
  local -a custom_nfs=()
  local -a containers=()
  local -a image_ids=()

  ensure_tools docker minikube helm kubectl
  mapfile -t custom_nfs < <(list_custom_nf_names)

  for custom_nf in "${custom_nfs[@]}"; do
    if load_custom_nf_metadata "$custom_nf" >/dev/null 2>&1; then
      releases+=("$NF_RELEASE")
    fi
  done

  if minikube -p "$MINIKUBE_PROFILE" status >/dev/null 2>&1; then
    for release in "${releases[@]}"; do
      helm -n "$NAMESPACE" uninstall "$release" >/dev/null 2>&1 || true
    done
    kubectl delete namespace "$NAMESPACE" --ignore-not-found=true >/dev/null 2>&1 || true
  fi

  minikube delete -p "$MINIKUBE_PROFILE" >/dev/null 2>&1 || true

  mapfile -t containers < <(docker ps -aq --filter name=oai-)
  if ((${#containers[@]})); then
    docker rm -f "${containers[@]}" >/dev/null
  fi

  mapfile -t image_ids < <(
    docker image ls --format '{{.Repository}} {{.ID}}' | awk '
      $1 ~ /^(local\/oai-|local\/oai-nwdaf-|oaisoftwarealliance\/oai-|docker.io\/oaisoftwarealliance\/oai-|oaisoftwarealliance\/trf-gen-cn5g|docker.io\/oaisoftwarealliance\/trf-gen-cn5g|production.imagehub\/oai-nwdaf-|oai-nwdaf-)/ {
        print $2
      }
    ' | sort -u
  )
  if ((${#image_ids[@]})); then
    docker image rm -f "${image_ids[@]}" >/dev/null
  fi

  log "Runtime reset complete for minikube profile $MINIKUBE_PROFILE"
}

main "$@"
