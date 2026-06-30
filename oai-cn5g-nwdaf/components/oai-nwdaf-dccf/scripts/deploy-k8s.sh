#!/bin/bash
set -e

NAMESPACE="oai-tutorial"
MINIKUBE_PROFILE="newS"

echo "=========================================="
echo "Deploying NWDAF-DCCF to Kubernetes"
echo "Profile: ${MINIKUBE_PROFILE}"
echo "Namespace: ${NAMESPACE}"
echo "=========================================="
echo ""

# Check if images exist
echo "Checking for required images in minikube..."
minikube -p ${MINIKUBE_PROFILE} ssh "docker images | grep -E '(oai-nwdaf-dccf|casmella)'" || {
    echo ""
    echo "ERROR: Images not found in minikube!"
    echo "Please run: ./scripts/build-local.sh"
    exit 1
}

echo ""
echo "✓ Images found"
echo ""

# Apply CRDs
echo "1/8 Creating Custom Resource Definitions..."
kubectl apply -f ../kubernetes/02-crds.yaml

# Apply RBAC
echo "2/8 Creating RBAC resources..."
kubectl apply -f ../kubernetes/03-rbac.yaml

# Apply ConfigMaps
echo "3/9 Creating ConfigMaps..."
kubectl apply -f ../kubernetes/04-configmaps.yaml

# Apply Storage
echo "4/9 Creating PersistentVolumeClaim..."
kubectl apply -f ../kubernetes/04a-storage.yaml

# Apply Controller
echo "5/9 Deploying Casmella Controller..."
kubectl apply -f ../kubernetes/05-controller-deployment.yaml

# Wait for controller
echo "   Waiting for controller to be ready..."
kubectl rollout status deployment/casmella-controller -n ${NAMESPACE} --timeout=120s || true

# Apply Agent DaemonSet
echo "6/9 Deploying DCCF Agent DaemonSet..."
kubectl apply -f ../kubernetes/08-dccf-agent-daemonset.yaml

# Apply Services
echo "7/9 Creating Services..."
kubectl apply -f ../kubernetes/09-dccf-service.yaml

# Apply DCCF Service Deployment
echo "8/9 Deploying DCCF Service..."
kubectl apply -f ../kubernetes/12-dccf-service-deployment.yaml

# Apply PodMonitors
echo "9/9 Creating PodMonitors..."
kubectl apply -f ../kubernetes/11-podmonitors.yaml

# Wait for deployments
echo "Waiting for DCCF agent to be ready..."
kubectl rollout status daemonset/oai-nwdaf-dccf-agent -n ${NAMESPACE} --timeout=300s || {
    echo ""
    echo "WARNING: Timeout waiting for DaemonSet. Checking status..."
    kubectl get pods -n ${NAMESPACE} -l app=oai-nwdaf-dccf
}

echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Quick Status Check:"
kubectl get pods -n ${NAMESPACE} -l app=oai-nwdaf-dccf -o wide
echo ""
kubectl get svc -n ${NAMESPACE} -l app=oai-nwdaf-dccf
echo ""

echo "Useful Commands:"
echo "  # View logs"
echo "  kubectl logs -n ${NAMESPACE} -l app=oai-nwdaf-dccf -f"
echo ""
echo "  # Check pod details"
echo "  kubectl describe pod -n ${NAMESPACE} -l app=oai-nwdaf-dccf"
echo ""
echo "  # Port forward to access NADRF"
echo "  kubectl port-forward -n ${NAMESPACE} svc/oai-nwdaf-dccf 8081:8081"
echo ""
echo "  # Test health endpoint"
echo "  curl http://localhost:8081/health"
echo ""
echo "  # View metrics in Prometheus"
echo "  kubectl port-forward -n prometheus svc/prom-kube-prometheus-stack-prometheus 9090:9090"
echo "  # Then open: http://localhost:9090"
echo ""
echo "  # View in Grafana"
echo "  # Access: http://$(minikube -p ${MINIKUBE_PROFILE} ip):30080"
echo ""