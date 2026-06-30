#!/bin/bash
# Build eBPF agent image for minikube

set -e

echo "=========================================="
echo "Building eBPF Agent Image for Minikube"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "${SCRIPT_DIR}/.."

# Check if minikube is running
if ! minikube status &>/dev/null; then
    echo -e "${YELLOW}Warning: Minikube doesn't appear to be running${NC}"
    echo "Start it with: minikube start"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Switch to minikube Docker environment
echo "Switching to minikube Docker environment..."
eval $(minikube docker-env)

# Build BCC base image
echo ""
echo "Step 1/2: Building BCC base image..."
if docker images | grep -q "casmella-bcc-python.*local"; then
    echo -e "${GREEN}✓ BCC base image already exists${NC}"
    read -p "Rebuild it? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker build -t casmella-bcc-python:local -f docker/dockerBCC/Dockerfile .
    fi
else
    docker build -t casmella-bcc-python:local -f docker/dockerBCC/Dockerfile .
fi

# Build main DCCF image
echo ""
echo "Step 2/2: Building DCCF/eBPF agent image..."
docker build -t oai-nwdaf-dccf:latest -f docker/Dockerfile .

echo ""
echo -e "${GREEN}=========================================="
echo "Build Complete!"
echo "==========================================${NC}"
echo ""
echo "Image built: oai-nwdaf-dccf:latest"
echo ""
echo "Next steps:"
echo "  1. Deploy to minikube:"
echo "     cd ${SCRIPT_DIR}"
echo "     ./deploy-ebpf-only.sh"
echo ""
echo "  2. Or manually apply:"
echo "     kubectl apply -f ${SCRIPT_DIR}/minimal-ebpf-deployment.yaml"
echo ""
