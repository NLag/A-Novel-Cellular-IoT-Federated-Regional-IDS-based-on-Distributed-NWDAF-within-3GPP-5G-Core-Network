#!/bin/bash
set -e

NAMESPACE="oai-tutorial"
MANIFESTS_DIR="${MANIFESTS_DIR:-./manifests-labeled}"

echo "========================================"
echo "  Deploying NWDAF with Project Labels"
echo "========================================"
echo ""

# 1. MongoDB with Labels
cat > "${MANIFESTS_DIR}/nwdaf-mongodb.yaml" << 'MONGODB'
apiVersion: v1
kind: Service
metadata:
  name: oai-nwdaf-database
  namespace: oai-tutorial
  labels:
    project: oai-tutorial
    component: nwdaf-database
spec:
  ports:
  - port: 27017
    targetPort: 27017
    protocol: TCP
  selector:
    app: oai-nwdaf-database
    project: oai-tutorial
    component: nwdaf-database
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: oai-nwdaf-database
  namespace: oai-tutorial
  labels:
    project: oai-tutorial
    component: nwdaf-database
spec:
  replicas: 1
  selector:
    matchLabels:
      app: oai-nwdaf-database
      project: oai-tutorial
      component: nwdaf-database
  template:
    metadata:
      labels:
        app: oai-nwdaf-database
        project: oai-tutorial
        component: nwdaf-database
    spec:
      containers:
      - name: mongodb
        image: mongo:latest
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 27017
        env:
        - name: MONGO_INITDB_DATABASE
          value: "testing"
MONGODB

# 2. Kong Gateway with Labels
cat > "${MANIFESTS_DIR}/nwdaf-kong.yaml" << 'KONG'
apiVersion: v1
kind: Service
metadata:
  name: oai-nwdaf-nbi-gateway
  namespace: oai-tutorial
  labels:
    project: oai-tutorial
    component: nwdaf-nbi-gateway
spec:
  type: NodePort
  ports:
  - name: http
    port: 8000
    targetPort: 8000
    protocol: TCP
  - name: admin
    port: 8001
    targetPort: 8001
    protocol: TCP
  selector:
    app: oai-nwdaf-nbi-gateway
    project: oai-tutorial
    component: nwdaf-nbi-gateway
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: oai-nwdaf-nbi-gateway
  namespace: oai-tutorial
  labels:
    project: oai-tutorial
    component: nwdaf-nbi-gateway
spec:
  replicas: 1
  selector:
    matchLabels:
      app: oai-nwdaf-nbi-gateway
      project: oai-tutorial
      component: nwdaf-nbi-gateway
  template:
    metadata:
      labels:
        app: oai-nwdaf-nbi-gateway
        project: oai-tutorial
        component: nwdaf-nbi-gateway
    spec:
      containers:
      - name: kong
        image: kong:latest
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 8000
        - containerPort: 8001
        env:
        - name: KONG_DATABASE
          value: "off"
        - name: KONG_DECLARATIVE_CONFIG
          value: "/opt/kong/kong.yaml"
        - name: KONG_PROXY_ACCESS_LOG
          value: "/dev/stdout"
        - name: KONG_ADMIN_ACCESS_LOG
          value: "/dev/stdout"
        - name: KONG_PROXY_ERROR_LOG
          value: "/dev/stderr"
        - name: KONG_ADMIN_ERROR_LOG
          value: "/dev/stderr"
        - name: KONG_ADMIN_LISTEN
          value: "0.0.0.0:8001"
        volumeMounts:
        - name: kong-config
          mountPath: /opt/kong
      volumes:
      - name: kong-config
        configMap:
          name: kong-config
KONG

# Copy kong-config.yaml as-is (ConfigMaps don't need pod labels)
cp ~/oai/nwdaf-k8s/manifests/nwdaf-kong-config.yaml "${MANIFESTS_DIR}/"

# 3. NBI Analytics with Labels
cat > "${MANIFESTS_DIR}/nwdaf-nbi-analytics.yaml" << 'ANALYTICS'
apiVersion: v1
kind: Service
metadata:
  name: oai-nwdaf-nbi-analytics
  namespace: oai-tutorial
  labels:
    project: oai-tutorial
    component: nwdaf-nbi-analytics
spec:
  ports:
  - port: 80
    targetPort: 8881
    protocol: TCP
  selector:
    app: oai-nwdaf-nbi-analytics
    project: oai-tutorial
    component: nwdaf-nbi-analytics
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: oai-nwdaf-nbi-analytics
  namespace: oai-tutorial
  labels:
    project: oai-tutorial
    component: nwdaf-nbi-analytics
spec:
  replicas: 1
  selector:
    matchLabels:
      app: oai-nwdaf-nbi-analytics
      project: oai-tutorial
      component: nwdaf-nbi-analytics
  template:
    metadata:
      labels:
        app: oai-nwdaf-nbi-analytics
        project: oai-tutorial
        component: nwdaf-nbi-analytics
    spec:
      containers:
      - name: nbi-analytics
        image: oai-nwdaf-nbi-analytics:latest
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 8881
        env:
        - name: ENGINE_URI
          value: "http://oai-nwdaf-engine:80"
        - name: ENGINE_NUM_OF_UE_ROUTE
          value: "/network_performance/num_of_ue"
        - name: ENGINE_SESS_SUCC_RATIO_ROUTE
          value: "/network_performance/sess_succ_ratio"
        - name: ENGINE_UE_COMMUNICATION_ROUTE
          value: "/ue_communication"
        - name: ENGINE_UE_MOBILITY_ROUTE
          value: "/ue_mobility"
        - name: SERVER_ADDR
          value: "0.0.0.0:8881"
ANALYTICS

# 4. NBI Events with Labels
cat > "${MANIFESTS_DIR}/nwdaf-nbi-events.yaml" << 'EVENTS'
apiVersion: v1
kind: Service
metadata:
  name: oai-nwdaf-nbi-events
  namespace: oai-tutorial
  labels:
    project: oai-tutorial
    component: nwdaf-nbi-events
spec:
  ports:
  - port: 80
    targetPort: 8882
    protocol: TCP
  selector:
    app: oai-nwdaf-nbi-events
    project: oai-tutorial
    component: nwdaf-nbi-events
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: oai-nwdaf-nbi-events
  namespace: oai-tutorial
  labels:
    project: oai-tutorial
    component: nwdaf-nbi-events
spec:
  replicas: 1
  selector:
    matchLabels:
      app: oai-nwdaf-nbi-events
      project: oai-tutorial
      component: nwdaf-nbi-events
  template:
    metadata:
      labels:
        app: oai-nwdaf-nbi-events
        project: oai-tutorial
        component: nwdaf-nbi-events
    spec:
      containers:
      - name: nbi-events
        image: oai-nwdaf-nbi-events:latest
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 8882
        env:
        - name: ENGINE_URI
          value: "http://oai-nwdaf-engine:80"
        - name: ENGINE_NUM_OF_UE_ROUTE
          value: "/network_performance/num_of_ue"
        - name: ENGINE_SESS_SUCC_RATIO_ROUTE
          value: "/network_performance/sess_succ_ratio"
        - name: ENGINE_UE_COMMUNICATION_ROUTE
          value: "/ue_communication"
        - name: ENGINE_UE_MOBILITY_ROUTE
          value: "/ue_mobility"
        - name: SERVER_ADDR
          value: "0.0.0.0:8882"
EVENTS

# 5. NBI ML with Labels
cat > "${MANIFESTS_DIR}/nwdaf-nbi-ml.yaml" << 'ML'
apiVersion: v1
kind: Service
metadata:
  name: oai-nwdaf-nbi-ml
  namespace: oai-tutorial
  labels:
    project: oai-tutorial
    component: nwdaf-nbi-ml
spec:
  ports:
  - port: 80
    targetPort: 8883
    protocol: TCP
  selector:
    app: oai-nwdaf-nbi-ml
    project: oai-tutorial
    component: nwdaf-nbi-ml
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: oai-nwdaf-nbi-ml
  namespace: oai-tutorial
  labels:
    project: oai-tutorial
    component: nwdaf-nbi-ml
spec:
  replicas: 1
  selector:
    matchLabels:
      app: oai-nwdaf-nbi-ml
      project: oai-tutorial
      component: nwdaf-nbi-ml
  template:
    metadata:
      labels:
        app: oai-nwdaf-nbi-ml
        project: oai-tutorial
        component: nwdaf-nbi-ml
    spec:
      containers:
      - name: nbi-ml
        image: oai-nwdaf-nbi-ml:latest
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 8883
        env:
        - name: SERVER_ADDR
          value: "0.0.0.0:8883"
ML

# 6. Engine with Labels
cat > "${MANIFESTS_DIR}/nwdaf-engine.yaml" << 'ENGINE'
apiVersion: v1
kind: Service
metadata:
  name: oai-nwdaf-engine
  namespace: oai-tutorial
  labels:
    project: oai-tutorial
    component: nwdaf-engine
spec:
  ports:
  - port: 80
    targetPort: 8888
    protocol: TCP
  selector:
    app: oai-nwdaf-engine
    project: oai-tutorial
    component: nwdaf-engine
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: oai-nwdaf-engine
  namespace: oai-tutorial
  labels:
    project: oai-tutorial
    component: nwdaf-engine
spec:
  replicas: 1
  selector:
    matchLabels:
      app: oai-nwdaf-engine
      project: oai-tutorial
      component: nwdaf-engine
  template:
    metadata:
      labels:
        app: oai-nwdaf-engine
        project: oai-tutorial
        component: nwdaf-engine
    spec:
      containers:
      - name: engine
        image: oai-nwdaf-engine:latest
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 8888
        env:
        - name: MONGODB_URI
          value: "mongodb://oai-nwdaf-database:27017"
        - name: MONGODB_DATABASE_NAME
          value: "testing"
        - name: MONGODB_COLLECTION_NAME_AMF
          value: "amf"
        - name: MONGODB_COLLECTION_NAME_SMF
          value: "smf"
        - name: ENGINE_NUM_OF_UE_ROUTE
          value: "/network_performance/num_of_ue"
        - name: ENGINE_SESS_SUCC_RATIO_ROUTE
          value: "/network_performance/sess_succ_ratio"
        - name: ENGINE_UE_COMMUNICATION_ROUTE
          value: "/ue_communication"
        - name: ENGINE_UE_MOBILITY_ROUTE
          value: "/ue_mobility"
        - name: SERVER_ADDR
          value: "0.0.0.0:8888"
ENGINE

# 7. SBI with Labels
cat > "${MANIFESTS_DIR}/nwdaf-sbi.yaml" << 'SBI'
apiVersion: v1
kind: Service
metadata:
  name: oai-nwdaf-sbi
  namespace: oai-tutorial
  labels:
    project: oai-tutorial
    component: nwdaf-sbi
spec:
  ports:
  - port: 80
    targetPort: 8885
    protocol: TCP
  selector:
    app: oai-nwdaf-sbi
    project: oai-tutorial
    component: nwdaf-sbi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: oai-nwdaf-sbi
  namespace: oai-tutorial
  labels:
    project: oai-tutorial
    component: nwdaf-sbi
spec:
  replicas: 1
  selector:
    matchLabels:
      app: oai-nwdaf-sbi
      project: oai-tutorial
      component: nwdaf-sbi
  template:
    metadata:
      labels:
        app: oai-nwdaf-sbi
        project: oai-tutorial
        component: nwdaf-sbi
    spec:
      containers:
      - name: sbi
        image: oai-nwdaf-sbi:latest
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 8885
        env:
        - name: AMF_IP_ADDR
          value: "http://oai-amf:80"
        - name: AMF_HTTP_VERSION
          value: "2"
        - name: AMF_SUBSCR_ROUTE
          value: "/namf-evts/v1"
        - name: AMF_API_ROUTE
          value: "/test/amf"
        - name: AMF_NOTIFY_CORRELATION_ID
          value: "string"
        - name: AMF_NOTIFICATION_ID
          value: "1"
        - name: AMF_NOTIFICATION_FORWARD_ROUTE
          value: "/sbi/notification/amf"
        - name: SMF_IP_ADDR
          value: "http://oai-smf:80"
        - name: SMF_HTTP_VERSION
          value: "2"
        - name: SMF_SUBSCR_ROUTE
          value: "/nsmf_event-exposure/v1"
        - name: SMF_API_ROUTE
          value: "/test/smf"
        - name: SMF_NOTIFY_CORRELATION_ID
          value: "string"
        - name: SMF_NOTIFICATION_ID
          value: "2"
        - name: SMF_NOTIFICATION_FORWARD_ROUTE
          value: "/sbi/notification/smf"
        - name: MONGODB_URI
          value: "mongodb://oai-nwdaf-database:27017"
        - name: MONGODB_DATABASE_NAME
          value: "testing"
        - name: MONGODB_COLLECTION_NAME_AMF
          value: "amf"
        - name: MONGODB_COLLECTION_NAME_SMF
          value: "smf"
        - name: EVENT_NOTIFY_URI
          value: "http://oai-nwdaf-sbi:80"
        - name: SERVER_ADDR
          value: "0.0.0.0:8885"
SBI

echo "=== Manifests with labels created in ${MANIFESTS_DIR} ==="
echo ""

# Now deploy in correct order
echo "=== Deploying MongoDB ==="
kubectl apply -f "${MANIFESTS_DIR}/nwdaf-mongodb.yaml"
kubectl wait --for=condition=ready pod -l component=nwdaf-database -n ${NAMESPACE} --timeout=120s

echo "=== Deploying Kong Gateway ==="
kubectl apply -f "${MANIFESTS_DIR}/nwdaf-kong-config.yaml"
kubectl apply -f "${MANIFESTS_DIR}/nwdaf-kong.yaml"
kubectl wait --for=condition=available deployment -l component=nwdaf-nbi-gateway -n ${NAMESPACE} --timeout=120s

echo "=== Deploying NWDAF Components ==="
kubectl apply -f "${MANIFESTS_DIR}/nwdaf-sbi.yaml"
kubectl apply -f "${MANIFESTS_DIR}/nwdaf-engine.yaml"
kubectl apply -f "${MANIFESTS_DIR}/nwdaf-nbi-analytics.yaml"
kubectl apply -f "${MANIFESTS_DIR}/nwdaf-nbi-events.yaml"
kubectl apply -f "${MANIFESTS_DIR}/nwdaf-nbi-ml.yaml"

echo "=== Waiting for all deployments ==="
kubectl wait --for=condition=available --timeout=120s deployment -n ${NAMESPACE} \
  -l project=oai-tutorial,component=nwdaf-sbi
kubectl wait --for=condition=available --timeout=120s deployment -n ${NAMESPACE} \
  -l project=oai-tutorial,component=nwdaf-engine
kubectl wait --for=condition=available --timeout=120s deployment -n ${NAMESPACE} \
  -l project=oai-tutorial,component=nwdaf-nbi-analytics
kubectl wait --for=condition=available --timeout=120s deployment -n ${NAMESPACE} \
  -l project=oai-tutorial,component=nwdaf-nbi-events
kubectl wait --for=condition=available --timeout=120s deployment -n ${NAMESPACE} \
  -l project=oai-tutorial,component=nwdaf-nbi-ml

echo ""
echo "=== All pods with labels ==="
kubectl get pods -n ${NAMESPACE} -l project=oai-tutorial --show-labels

echo ""
echo "=== NWDAF pods only ==="
kubectl get pods -n ${NAMESPACE} -l project=oai-tutorial -l component | grep nwdaf

echo ""
echo "=== Gateway Info ==="
MINIKUBE_IP=$(minikube ip)
NODEPORT=$(kubectl get svc oai-nwdaf-nbi-gateway -n ${NAMESPACE} -o jsonpath='{.spec.ports[0].nodePort}')
echo "NWDAF Gateway URL: http://${MINIKUBE_IP}:${NODEPORT}"

echo ""
echo "========================================"
echo "  NWDAF Deployment with Labels Complete!"
echo "========================================"

