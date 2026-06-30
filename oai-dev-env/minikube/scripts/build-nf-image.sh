#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

usage() {
  cat <<'EOF'
Usage: build-nf-image.sh [--clean] [--debug] <nf|packetrusher|all-core|all-nwdaf|all-custom|all>

Examples:
  build-nf-image.sh amf
  build-nf-image.sh traffic-server
  build-nf-image.sh --debug smf
  build-nf-image.sh ids
  build-nf-image.sh packetrusher
  build-nf-image.sh all-nwdaf
EOF
}

resolve_core_build() {
  local nf="$1"
  local short_name="${nf#oai-}"

  if [[ "$nf" == "oai-traffic-server" ]]; then
    BUILD_CONTEXT="$WORKSPACE_ROOT/oai-cn5g-fed"
    BUILD_DOCKERFILE="$BUILD_CONTEXT/ci-scripts/Dockerfile.traffic.generator.ubuntu"
    BUILD_TARGET="trf-gen-cn5g"
    BUILD_IMAGE="$(core_nf_image_repo "$nf")"
    return
  fi

  BUILD_CONTEXT="$WORKSPACE_ROOT/oai-cn5g-fed/component/${nf}"
  BUILD_DOCKERFILE="$BUILD_CONTEXT/docker/Dockerfile.${short_name}.ubuntu"
  BUILD_TARGET="$nf"
  BUILD_IMAGE="$(core_nf_image_repo "$nf")"
}

resolve_nwdaf_build() {
  local component="$1"

  case "$component" in
    engine)
      BUILD_CONTEXT="$WORKSPACE_ROOT/oai-cn5g-nwdaf/components/oai-nwdaf-engine"
      BUILD_DOCKERFILE="$BUILD_CONTEXT/docker/Dockerfile.engine"
      BUILD_TARGET="oai-nwdaf-engine"
      ;;
    nbi-analytics)
      BUILD_CONTEXT="$WORKSPACE_ROOT/oai-cn5g-nwdaf/components/oai-nwdaf-nbi-analytics"
      BUILD_DOCKERFILE="$BUILD_CONTEXT/docker/Dockerfile.nbi-analytics"
      BUILD_TARGET="oai-nwdaf-nbi-analytics"
      ;;
    nbi-events)
      BUILD_CONTEXT="$WORKSPACE_ROOT/oai-cn5g-nwdaf/components/oai-nwdaf-nbi-events"
      BUILD_DOCKERFILE="$BUILD_CONTEXT/docker/Dockerfile.nbi-events"
      BUILD_TARGET="oai-nwdaf-nbi-events"
      ;;
    nbi-ml)
      BUILD_CONTEXT="$WORKSPACE_ROOT/oai-cn5g-nwdaf/components/oai-nwdaf-nbi-ml"
      BUILD_DOCKERFILE="$BUILD_CONTEXT/docker/Dockerfile.nbi-ml"
      BUILD_TARGET="oai-nwdaf-nbi-ml"
      ;;
    sbi)
      BUILD_CONTEXT="$WORKSPACE_ROOT/oai-cn5g-nwdaf/components/oai-nwdaf-sbi"
      BUILD_DOCKERFILE="$BUILD_CONTEXT/docker/Dockerfile.sbi"
      BUILD_TARGET="oai-nwdaf-sbi"
      ;;
    mtlf)
      BUILD_CONTEXT="$WORKSPACE_ROOT/oai-cn5g-nwdaf/components/oai-nwdaf-mtlf"
      BUILD_DOCKERFILE="$BUILD_CONTEXT/docker/Dockerfile.mtlf"
      BUILD_TARGET="oai-nwdaf-mtlf"
      ;;
    dccf)
      BUILD_CONTEXT="$WORKSPACE_ROOT/oai-cn5g-nwdaf/components/oai-nwdaf-dccf"
      BUILD_DOCKERFILE="$BUILD_CONTEXT/docker/Dockerfile.service"
      BUILD_TARGET="oai-nwdaf-dccf"
      ;;
    *)
      die "Unsupported NWDAF component: $component"
      ;;
  esac

  BUILD_IMAGE="$(nwdaf_image_repo "$component")"
}

resolve_custom_nf_build() {
  load_custom_nf_metadata "$1" || die "Unsupported custom NF: $1"

  [[ -n "$NF_BUILD_CONTEXT" ]] || die "Missing NF_BUILD_CONTEXT in $CUSTOM_NF_METADATA_PATH"
  [[ -n "$NF_BUILD_DOCKERFILE" ]] || die "Missing NF_BUILD_DOCKERFILE in $CUSTOM_NF_METADATA_PATH"

  BUILD_CONTEXT="$NF_BUILD_CONTEXT"
  BUILD_DOCKERFILE="$NF_BUILD_DOCKERFILE"
  BUILD_TARGET="$NF_BUILD_TARGET"
  BUILD_IMAGE="$NF_IMAGE_REPOSITORY"
}

resolve_packetrusher_build() {
  BUILD_CONTEXT="$WORKSPACE_ROOT/PacketRusher"
  BUILD_DOCKERFILE="$BUILD_CONTEXT/docker/Dockerfile"
  BUILD_TARGET="packetrusher"
  BUILD_IMAGE="$PACKETRUSHER_IMAGE_REPOSITORY"
}

docker_build_nf() {
  local image_repo="$1"
  local tag="$2"
  local dockerfile_path="$3"
  local target_name="$4"
  local context_dir="$5"
  local clean_build="$6"

  local -a docker_args=(
    build
    --network=host
    --file "$dockerfile_path"
    --target "$target_name"
    --tag "${image_repo}:${tag}"
  )

  if [[ "$clean_build" == "true" ]]; then
    docker_args+=(--no-cache)
  fi

  docker_args+=("$context_dir")
  docker "${docker_args[@]}"
}

build_core_nf() {
  local nf="$1"
  local clean_build="$2"
  local debug_build="$3"
  local dockerfile_path tag temp_dockerfile

  resolve_core_build "$nf"
  tag="dev"
  dockerfile_path="$BUILD_DOCKERFILE"
  temp_dockerfile=""

  [[ -d "$BUILD_CONTEXT" ]] || die "Missing source tree: $BUILD_CONTEXT"
  [[ -f "$BUILD_DOCKERFILE" ]] || die "Missing Dockerfile: $BUILD_DOCKERFILE"

  if [[ "$debug_build" == "true" ]]; then
    [[ "$nf" != "oai-traffic-server" ]] || die "--debug is not supported for $nf"
    tag="debug-dev"
    temp_dockerfile="$(mktemp "/tmp/${nf#oai-}.XXXXXX.Dockerfile")"
    sed 's/--build-type Release/--build-type Debug/g' "$BUILD_DOCKERFILE" > "$temp_dockerfile"
    dockerfile_path="$temp_dockerfile"
  fi

  log "Building ${BUILD_IMAGE}:${tag} from $BUILD_CONTEXT"
  docker_build_nf "$BUILD_IMAGE" "$tag" "$dockerfile_path" "$BUILD_TARGET" "$BUILD_CONTEXT" "$clean_build"

  if [[ -n "$temp_dockerfile" ]]; then
    rm -f "$temp_dockerfile"
  fi
}

build_nwdaf_component() {
  local component="$1"
  local clean_build="$2"

  resolve_nwdaf_build "$component"

  [[ -d "$BUILD_CONTEXT" ]] || die "Missing source tree: $BUILD_CONTEXT"
  [[ -f "$BUILD_DOCKERFILE" ]] || die "Missing Dockerfile: $BUILD_DOCKERFILE"

  log "Building ${BUILD_IMAGE}:dev from $BUILD_CONTEXT"
  docker_build_nf "$BUILD_IMAGE" "dev" "$BUILD_DOCKERFILE" "$BUILD_TARGET" "$BUILD_CONTEXT" "$clean_build"
}

build_custom_nf() {
  local nf="$1"
  local clean_build="$2"

  resolve_custom_nf_build "$nf"

  [[ -d "$BUILD_CONTEXT" ]] || die "Missing source tree: $BUILD_CONTEXT"
  [[ -f "$BUILD_DOCKERFILE" ]] || die "Missing Dockerfile: $BUILD_DOCKERFILE"

  log "Building ${BUILD_IMAGE}:${NF_IMAGE_TAG} from $BUILD_CONTEXT"
  docker_build_nf "$BUILD_IMAGE" "$NF_IMAGE_TAG" "$BUILD_DOCKERFILE" "$BUILD_TARGET" "$BUILD_CONTEXT" "$clean_build"
}

build_packetrusher() {
  local clean_build="$1"

  resolve_packetrusher_build

  [[ -d "$BUILD_CONTEXT" ]] || die "Missing source tree: $BUILD_CONTEXT"
  [[ -f "$BUILD_DOCKERFILE" ]] || die "Missing Dockerfile: $BUILD_DOCKERFILE"

  log "Building ${BUILD_IMAGE}:${PACKETRUSHER_IMAGE_TAG} from $BUILD_CONTEXT"
  docker_build_nf "$BUILD_IMAGE" "$PACKETRUSHER_IMAGE_TAG" "$BUILD_DOCKERFILE" "$BUILD_TARGET" "$BUILD_CONTEXT" "$clean_build"
}

main() {
  local clean_build="false"
  local debug_build="false"
  local target="${1:-}"
  local item
  local -a core_targets=(
    oai-amf
    oai-ausf
    oai-lmf
    oai-nrf
    oai-nssf
    oai-smf
    oai-traffic-server
    oai-udm
    oai-udr
    oai-upf
  )
  local -a nwdaf_targets=(
    engine
    nbi-analytics
    nbi-events
    nbi-ml
    sbi
    mtlf
    dccf
  )
  local -a custom_targets=()

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --clean)
        clean_build="true"
        shift
        ;;
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

  ensure_tools docker minikube
  ensure_minikube
  use_minikube_docker_env
  mapfile -t custom_targets < <(list_custom_nf_names)

  case "$target" in
    all-core)
      for item in "${core_targets[@]}"; do
        build_core_nf "$item" "$clean_build" "$debug_build"
      done
      ;;
    all-nwdaf)
      [[ "$debug_build" == "false" ]] || die "--debug is only supported for core NFs"
      for item in "${nwdaf_targets[@]}"; do
        build_nwdaf_component "$item" "$clean_build"
      done
      ;;
    all)
      [[ "$debug_build" == "false" ]] || die "--debug cannot be combined with all because NWDAF images do not have debug variants"
      for item in "${core_targets[@]}"; do
        build_core_nf "$item" "$clean_build" "$debug_build"
      done
      for item in "${nwdaf_targets[@]}"; do
        build_nwdaf_component "$item" "$clean_build"
      done
      build_packetrusher "$clean_build"
      for item in "${custom_targets[@]}"; do
        build_custom_nf "$item" "$clean_build"
      done
      ;;
    all-custom)
      [[ "$debug_build" == "false" ]] || die "--debug is only supported for core NFs"
      for item in "${custom_targets[@]}"; do
        build_custom_nf "$item" "$clean_build"
      done
      ;;
    *)
      if item="$(canonical_core_nf "$target" 2>/dev/null)"; then
        build_core_nf "$item" "$clean_build" "$debug_build"
      elif item="$(canonical_nwdaf_component "$target" 2>/dev/null)"; then
        [[ "$debug_build" == "false" ]] || die "--debug is only supported for core NFs"
        build_nwdaf_component "$item" "$clean_build"
      elif item="$(canonical_packetrusher "$target" 2>/dev/null)"; then
        [[ "$debug_build" == "false" ]] || die "--debug is only supported for core NFs"
        build_packetrusher "$clean_build"
      elif item="$(canonical_custom_nf "$target" 2>/dev/null)"; then
        [[ "$debug_build" == "false" ]] || die "--debug is only supported for core NFs"
        build_custom_nf "$item" "$clean_build"
      else
        die "Unknown NF or component: $target"
      fi
      ;;
  esac
}

main "$@"
