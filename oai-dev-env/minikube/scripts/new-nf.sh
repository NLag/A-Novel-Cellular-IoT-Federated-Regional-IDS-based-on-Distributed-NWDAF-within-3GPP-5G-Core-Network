#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

usage() {
  cat <<'EOF'
Usage: new-nf.sh <nf-name>

Example:
  new-nf.sh oai-my-nf
EOF
}

main() {
  local nf_name="${1:-}"
  local destination file values_destination metadata_destination release_name

  [[ -n "$nf_name" ]] || {
    usage
    exit 1
  }

  [[ "$nf_name" =~ ^[a-z0-9-]+$ ]] || die "NF name must use lowercase letters, numbers, and hyphens only"

  destination="$CHARTS_ROOT/$nf_name"
  release_name="${nf_name#oai-}"
  values_destination="$VALUES_ROOT/${release_name}-dev.yaml"
  metadata_destination="$CUSTOM_NF_ROOT/${nf_name}.env"
  [[ ! -e "$destination" ]] || die "Destination already exists: $destination"
  [[ ! -e "$values_destination" ]] || die "Values file already exists: $values_destination"
  [[ ! -e "$metadata_destination" ]] || die "Metadata file already exists: $metadata_destination"

  cp -R "$CHART_NF_TEMPLATE" "$destination"
  mkdir -p "$CUSTOM_NF_ROOT"

  while IFS= read -r -d '' file; do
    sed -i "s/template-nf/${nf_name}/g" "$file"
  done < <(find "$destination" -type f -print0)

  cp "$destination/values.yaml" "$values_destination"
  cat >"$metadata_destination" <<EOF
# shellcheck shell=bash
NF_NAME=${nf_name}
NF_RELEASE=${release_name}
NF_CHART=${destination}
NF_VALUES=${values_destination}
NF_IMAGE_REPOSITORY=local/${nf_name}
NF_IMAGE_TAG=dev
NF_IMAGE_PULL_POLICY=Never
NF_DEPLOYMENT_NAME=${nf_name}
NF_BUILD_CONTEXT=
NF_BUILD_DOCKERFILE=
NF_BUILD_TARGET=${release_name}
EOF

  log "Scaffolded standalone NF chart at $destination"
  log "Created values file at $values_destination"
  log "Created metadata stub at $metadata_destination"
  log "Next steps:"
  log "  1. Point NF_BUILD_* in $metadata_destination to your source tree and Dockerfile"
  log "  2. Edit $values_destination for ports, env, and waitForNrf"
  log "  3. Build with: $ENV_ROOT/scripts/build-nf-image.sh ${release_name}"
  log "  4. Deploy with: $ENV_ROOT/scripts/redeploy-stack.sh ${release_name}"
}

main "$@"
