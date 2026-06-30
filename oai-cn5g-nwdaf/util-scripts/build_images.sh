#!/bin/bash

# Script to build all NWDAF Docker images
# Make sure you're in the oai-cn5g-nwdaf directory before running

set -e  # Exit on error

# Delete existing NWDAF images
echo ""
echo "======================================"
echo "Removing existing NWDAF images..."
echo "======================================"
docker rmi -f oai-nwdaf-nbi-analytics:latest 2>/dev/null || true
docker rmi -f oai-nwdaf-nbi-events:latest 2>/dev/null || true
docker rmi -f oai-nwdaf-nbi-ml:latest 2>/dev/null || true
docker rmi -f oai-nwdaf-engine:latest 2>/dev/null || true
docker rmi -f oai-nwdaf-sbi:latest 2>/dev/null || true


echo "======================================"
echo "Building OAI NWDAF Docker Images"
echo "======================================"

# Check if we're in the correct directory
if [ ! -d "components" ]; then
    echo "Error: components directory not found!"
    echo "Please run this script from the oai-cn5g-nwdaf root directory"
    exit 1
fi

# 1. Build oai-nwdaf-nbi-analytics
echo ""
echo "[1/5] Building oai-nwdaf-nbi-analytics..."
docker build --network=host --no-cache \
            --target oai-nwdaf-nbi-analytics --tag oai-nwdaf-nbi-analytics:latest \
            --file components/oai-nwdaf-nbi-analytics/docker/Dockerfile.nbi-analytics \
            components/oai-nwdaf-nbi-analytics

# 2. Build oai-nwdaf-nbi-events
echo ""
echo "[2/5] Building oai-nwdaf-nbi-events..."
docker build --network=host --no-cache \
            --target oai-nwdaf-nbi-events --tag oai-nwdaf-nbi-events:latest \
            --file components/oai-nwdaf-nbi-events/docker/Dockerfile.nbi-events \
            components/oai-nwdaf-nbi-events

# 3. Build oai-nwdaf-nbi-ml
echo ""
echo "[3/5] Building oai-nwdaf-nbi-ml..."
docker build --network=host --no-cache \
            --target oai-nwdaf-nbi-ml --tag oai-nwdaf-nbi-ml:latest \
            --file components/oai-nwdaf-nbi-ml/docker/Dockerfile.nbi-ml \
            components/oai-nwdaf-nbi-ml

# 4. Build oai-nwdaf-engine
echo ""
echo "[4/5] Building oai-nwdaf-engine..."
docker build --network=host --no-cache \
            --target oai-nwdaf-engine --tag oai-nwdaf-engine:latest \
            --file components/oai-nwdaf-engine/docker/Dockerfile.engine \
            components/oai-nwdaf-engine

# 5. Build oai-nwdaf-sbi
echo ""
echo "[5/5] Building oai-nwdaf-sbi..."
docker build --network=host --no-cache \
            --target oai-nwdaf-sbi --tag oai-nwdaf-sbi:latest \
            --file components/oai-nwdaf-sbi/docker/Dockerfile.sbi \
            components/oai-nwdaf-sbi

# Pull required images
echo ""
echo "======================================"
echo "Pulling required external images..."
echo "======================================"
docker pull mongo
docker pull kong
docker pull rohankharade/gnbsim
docker image tag rohankharade/gnbsim:latest gnbsim:latest

# Clean up dangling images
echo ""
echo "======================================"
echo "Cleaning up dangling images..."
echo "======================================"
docker image prune --force

# Try buildx prune if available
if docker buildx version &> /dev/null; then
    docker buildx prune -f
fi

echo ""
echo "======================================"
echo "Build Complete!"
echo "======================================"
echo ""
echo "Built images:"
docker images | grep -E "oai-nwdaf|mongo|kong"

echo ""
echo "You can now proceed with network configuration and deployment."
