#!/bin/bash
set -e

MINIKUBE_PROFILE="newS"

echo "=========================================="
echo "NWDAF-DCCF: Build and Deploy"
echo "=========================================="
echo ""

# Step 1: Build images
echo "STEP 1: Building Docker images..."
./scripts/build-local.sh

echo ""
echo "=========================================="
echo ""

# Step 2: Deploy to Kubernetes
echo "STEP 2: Deploying to Kubernetes..."
./scripts/deploy-k8s.sh

echo ""
echo "=========================================="
echo "Build and Deploy Complete!"
echo "=========================================="