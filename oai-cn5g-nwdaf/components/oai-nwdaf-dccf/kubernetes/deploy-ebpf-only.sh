#!/bin/bash
# Quick deployment script for eBPF-only monitoring

set -e

echo "======================================"
echo "eBPF Agent Deployment Script"
echo "======================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check if running in minikube context
CURRENT_CONTEXT=$(kubectl config current-context)
echo -e "${YELLOW}Current kubectl context: ${CURRENT_CONTEXT}${NC}"
read -p "Continue with this context? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# Step 1: Build Docker image
echo ""
echo "===================================="
echo "Step 1: Building Docker Image"
echo "===================================="
read -p "Do you want to build the eBPF agent image? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Switching to minikube docker-env..."
    eval $(minikube docker-env)
    
    cd "${SCRIPT_DIR}/.."
    
    # First check if BCC base image exists
    if ! docker images | grep -q "casmella-bcc-python.*local"; then
        echo "Building BCC base image..."
        docker build -t casmella-bcc-python:local -f docker/dockerBCC/Dockerfile .
    else
        echo "BCC base image already exists"
    fi
    
    echo "Building image: oai-nwdaf-dccf:latest"
    docker build -t oai-nwdaf-dccf:latest -f docker/Dockerfile .
    
    echo -e "${GREEN}✓ Image built successfully${NC}"
else
    echo "Skipping image build. Make sure the image 'oai-nwdaf-dccf:latest' exists."
fi

# Step 2: Check kernel requirements
echo ""
echo "===================================="
echo "Step 2: Checking Kernel Requirements"
echo "===================================="
echo "Checking kernel version in minikube..."
KERNEL_VERSION=$(minikube ssh -- uname -r)
echo "Kernel version: ${KERNEL_VERSION}"

# Check BPF filesystem
if minikube ssh -- "mount | grep -q bpf"; then
    echo -e "${GREEN}✓ BPF filesystem is mounted${NC}"
else
    echo -e "${RED}✗ BPF filesystem not found${NC}"
    echo "Attempting to mount..."
    minikube ssh -- "sudo mkdir -p /sys/fs/bpf && sudo mount -t bpf none /sys/fs/bpf" || true
fi

# Check debugfs
if minikube ssh -- "test -d /sys/kernel/debug"; then
    echo -e "${GREEN}✓ debugfs is available${NC}"
else
    echo -e "${YELLOW}⚠ debugfs not found (may cause issues)${NC}"
fi

# Step 3: Deploy eBPF agent
echo ""
echo "===================================="
echo "Step 3: Deploying eBPF Agent"
echo "===================================="
kubectl apply -f "${SCRIPT_DIR}/minimal-ebpf-deployment.yaml"

echo ""
echo "Waiting for DaemonSet to be ready..."
kubectl rollout status daemonset/ebpf-agent -n oai-tutorial --timeout=120s

# Step 4: Verify deployment
echo ""
echo "===================================="
echo "Step 4: Verifying Deployment"
echo "===================================="

# Check pods
echo ""
echo "DaemonSet status:"
kubectl get daemonset ebpf-agent -n oai-tutorial

echo ""
echo "Pod status:"
kubectl get pods -n oai-tutorial -l app=ebpf-agent

# Check logs
echo ""
echo "Recent logs (last 20 lines):"
kubectl logs -n oai-tutorial -l app=ebpf-agent --tail=20 || echo "Could not fetch logs yet"

# Try to curl metrics
echo ""
echo "Testing metrics endpoint..."
POD_NAME=$(kubectl get pod -n oai-tutorial -l app=ebpf-agent -o jsonpath='{.items[0].metadata.name}')
if [ -n "$POD_NAME" ]; then
    echo "Fetching metrics from pod: ${POD_NAME}"
    kubectl exec -n oai-tutorial "$POD_NAME" -- curl -s localhost:9950/metrics | head -30 || echo "Could not fetch metrics"
else
    echo -e "${YELLOW}⚠ No pods found yet${NC}"
fi

# Step 5: Prometheus setup info
echo ""
echo "===================================="
echo "Step 5: Prometheus Configuration"
echo "===================================="
echo ""
echo "The PodMonitor has been created. Check if Prometheus is scraping:"
echo ""
echo "  kubectl get podmonitor ebpf-agent-monitor -n oai-tutorial"
echo ""
echo "If using standalone Prometheus (not Operator), apply the scrape config:"
echo ""
echo "  ${SCRIPT_DIR}/prometheus-scrape-config.yaml"
echo ""

# Summary
echo ""
echo "======================================"
echo "${GREEN}Deployment Complete!${NC}"
echo "======================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Check agent logs:"
echo "   kubectl logs -n oai-tutorial -l app=ebpf-agent -f"
echo ""
echo "2. Port-forward to access metrics locally:"
echo "   kubectl port-forward -n oai-tutorial daemonset/ebpf-agent 9950:9950"
echo "   curl http://localhost:9950/metrics"
echo ""
echo "3. Verify Prometheus is scraping:"
echo "   - Check Prometheus targets page"
echo "   - Query: casmella_requests_total"
echo ""
echo "4. View full documentation:"
echo "   ${SCRIPT_DIR}/EBPF_ONLY_DEPLOYMENT.md"
echo ""

# Offer to show logs
echo ""
read -p "Do you want to follow the agent logs now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    kubectl logs -n oai-tutorial -l app=ebpf-agent -f
fi
