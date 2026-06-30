#!/bin/bash
# Patches Casmella to work with Docker instead of Kubernetes

set -e

CASMELLA_DIR="/casmella/casmella"

echo "Adapting Casmella for Docker mode..."

# Create Kubernetes stub module
cat > ${CASMELLA_DIR}/core/k8s.py << 'EOF'
"""
Stub for K8s functions when running in Docker mode
"""
import json
import logging

logger = logging.getLogger(__name__)

def load_incluster_config():
    """Stub - no-op for Docker mode"""
    pass

def get_topology_resource(name):
    """Return empty topology"""
    return {}, {}

def get_hooklist_resource(name):
    """Return topology from Docker discovery"""
    try:
        with open('/tmp/topology.json', 'r') as f:
            topology = json.load(f)
        return topology.get('podInterfaces', {}), {}
    except Exception as e:
        logger.warning(f"Failed to load topology: {e}")
        return {}, {}

def get_fiveqiinfo_resource(name):
    """Return empty 5QI info"""
    return {}

def patch_custom_resource(singular, plural, spec):
    """No-op in Docker mode"""
    logger.debug(f"Skipping K8s patch in Docker mode: {singular}/{plural}")
    pass

def get_custom_resource(singular, plural, name):
    """Return empty resource"""
    return {}

def create_custom_resource(singular, plural, spec):
    """No-op in Docker mode"""
    pass

def delete_custom_resource(singular, plural, name):
    """No-op in Docker mode"""
    pass

# For compatibility with Casmella's imports
class V1Pod:
    pass

class CoreV1Api:
    def list_pod_for_all_namespaces(self, *args, **kwargs):
        return type('obj', (object,), {'items': []})()
EOF

# Verify the stub was created
if [ -f "${CASMELLA_DIR}/core/k8s.py" ]; then
    echo "✓ Kubernetes stub created successfully"
    echo "✓ File size: $(wc -l < ${CASMELLA_DIR}/core/k8s.py) lines"
else
    echo "✗ Failed to create Kubernetes stub"
    exit 1
fi

echo "Casmella adapted for Docker mode"