#!/bin/bash
set -e

MINIKUBE_PROFILE="newS"
IMAGE_TAG="latest"

echo "=========================================="
echo "Building NWDAF-DCCF Images Locally"
echo "=========================================="
echo ""

# Check if minikube profile exists
if ! minikube profile list | grep -q ${MINIKUBE_PROFILE}; then
    echo "Error: Minikube profile '${MINIKUBE_PROFILE}' not found"
    exit 1
fi

# Check if BCC base image exists in host Docker
if ! docker images | grep -q "casmella-bcc-python.*local"; then
    echo "Error: casmella-bcc-python:local not found in host Docker"
    echo "Please build it first using: docker build -t casmella-bcc-python:local -f docker/dockerBCC/Dockerfile ."
    exit 1
fi

echo "Step 1: Loading BCC base image into minikube..."
# Check if image already exists in minikube
if minikube -p ${MINIKUBE_PROFILE} ssh "docker images | grep -q 'casmella-bcc-python.*local'"; then
    echo "  ✓ BCC image already exists in minikube"
else
    echo "  Loading casmella-bcc-python:local into minikube..."
    minikube -p ${MINIKUBE_PROFILE} image load casmella-bcc-python:local
    echo "  ✓ BCC image loaded"
fi

# Set Docker environment to use minikube's Docker daemon
echo ""
echo "Step 2: Setting Docker environment to minikube..."
eval $(minikube -p ${MINIKUBE_PROFILE} docker-env)

echo ""
echo "Step 3: Building DCCF Agent image..."
docker build -t oai-nwdaf-dccf:${IMAGE_TAG} \
    -f docker/Dockerfile \
    --progress=plain \
    .

echo ""
echo "Step 4: Building Casmella Controller image..."
docker build -t casmella-controller:${IMAGE_TAG} \
    -f docker/Dockerfile.controller \
    --progress=plain \
    .

echo ""
echo "Step 5: Building Casmella SDG image..."
docker build -t casmella-sdg:${IMAGE_TAG} \
    -f docker/Dockerfile.sdg \
    --progress=plain \
    .

echo ""
echo "Step 6: Building DCCF Service image..."
docker build -t oai-nwdaf-dccf:${IMAGE_TAG} \
    -f docker/Dockerfile.service \
    --progress=plain \
    .

# Reset Docker environment
eval $(minikube -p ${MINIKUBE_PROFILE} docker-env -u)

echo ""
echo "=========================================="
echo "Images built successfully!"
echo "=========================================="
echo ""
echo "Available images in minikube:"
minikube -p ${MINIKUBE_PROFILE} ssh "docker images | grep -E '(oai-nwdaf-dccf|casmella)'"

echo ""
echo "To verify images:"
echo "  minikube -p ${MINIKUBE_PROFILE} ssh"
echo "  docker images | grep -E '(oai-nwdaf-dccf|casmella)'"