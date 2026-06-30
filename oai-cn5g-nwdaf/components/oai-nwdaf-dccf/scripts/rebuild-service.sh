#!/bin/bash
set -e

MINIKUBE_PROFILE="newS"
IMAGE_TAG="latest"

echo "=========================================="
echo "Rebuilding DCCF Service Image"
echo "=========================================="
echo ""

# Check if minikube profile exists
if ! minikube profile list | grep -q "${MINIKUBE_PROFILE}"; then
    echo "Error: Minikube profile '${MINIKUBE_PROFILE}' not found"
    exit 1
fi

# Set Docker environment to use minikube's Docker daemon
echo "Setting Docker environment to minikube '${MINIKUBE_PROFILE}'..."
eval $(minikube -p ${MINIKUBE_PROFILE} docker-env)

# Build the service image
echo ""
echo "Building DCCF Service image (oai-nwdaf-dccf:${IMAGE_TAG})..."
cd /home/dave/oai/newsetup/oai-cn5g-nwdaf/components/oai-nwdaf-dccf
docker build -t oai-nwdaf-dccf:${IMAGE_TAG} \
    -f docker/Dockerfile.service \
    --progress=plain \
    .

echo ""
echo "✓ Service image built successfully"
#minikube image load -p ${MINIKUBE_PROFILE} oai-nwdaf-dccf:${IMAGE_TAG}
# Restart the service pod to pick up the new image
echo ""
echo "Restarting DCCF service pod..."
kubectl delete pod -n oai-tutorial -l app=oai-nwdaf-dccf,component=dccf

echo ""
echo "Waiting for new pod to start..."
sleep 5
kubectl wait --for=condition=ready pod -n oai-tutorial -l app=oai-nwdaf-dccf,component=dccf --timeout=120s

echo ""
echo "=========================================="
echo "DCCF Service rebuilt and restarted!"
echo "=========================================="
echo ""
echo "Check logs:"
echo "kubectl logs -n oai-tutorial \$(kubectl get pod -n oai-tutorial -l app=oai-nwdaf-dccf,component=dccf -o jsonpath='{.items[0].metadata.name}') -f"
