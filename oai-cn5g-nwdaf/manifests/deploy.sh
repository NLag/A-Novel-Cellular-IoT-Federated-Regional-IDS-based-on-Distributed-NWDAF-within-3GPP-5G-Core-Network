# Redeploy in correct order
echo "=== Deploying MongoDB ==="
kubectl apply -f /home/dave/oai/newsetup/oai-cn5g-nwdaf/manifests/manifests-labeled/nwdaf-mongodb.yaml
kubectl wait --for=condition=ready pod -l app=oai-nwdaf-database -n oai-tutorial --timeout=120s

echo "=== Deploying Kong Gateway ==="
kubectl apply -f /home/dave/oai/newsetup/oai-cn5g-nwdaf/manifests/manifests-labeled/nwdaf-kong-config.yaml
kubectl apply -f /home/dave/oai/newsetup/oai-cn5g-nwdaf/manifests/manifests-labeled/nwdaf-kong.yaml
kubectl wait --for=condition=available deployment oai-nwdaf-nbi-gateway -n oai-tutorial --timeout=120s

echo "=== Deploying NWDAF Components ==="
kubectl apply -f /home/dave/oai/newsetup/oai-cn5g-nwdaf/manifests/manifests-labeled/nwdaf-sbi.yaml
kubectl apply -f /home/dave/oai/newsetup/oai-cn5g-nwdaf/manifests/manifests-labeled/nwdaf-engine.yaml
kubectl apply -f /home/dave/oai/newsetup/oai-cn5g-nwdaf/manifests/manifests-labeled/nwdaf-nbi-analytics.yaml
kubectl apply -f /home/dave/oai/newsetup/oai-cn5g-nwdaf/manifests/manifests-labeled/nwdaf-nbi-events.yaml
kubectl apply -f /home/dave/oai/newsetup/oai-cn5g-nwdaf/manifests/manifests-labeled/nwdaf-nbi-ml.yaml

echo "=== Waiting for all deployments ==="
kubectl wait --for=condition=available --timeout=120s deployment -n oai-tutorial \
  oai-nwdaf-sbi \
  oai-nwdaf-engine \
  oai-nwdaf-nbi-analytics \
  oai-nwdaf-nbi-events \
  oai-nwdaf-nbi-ml

echo "=== All pods ==="
kubectl get pods -n oai-tutorial | grep nwdaf

echo "=== Gateway Info ==="
MINIKUBE_IP=$(minikube ip)
NODEPORT=$(kubectl get svc oai-nwdaf-nbi-gateway -n oai-tutorial -o jsonpath='{.spec.ports[0].nodePort}')
echo "NWDAF Gateway URL: http://${MINIKUBE_IP}:${NODEPORT}"
