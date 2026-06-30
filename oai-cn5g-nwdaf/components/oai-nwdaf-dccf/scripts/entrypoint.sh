#!/bin/bash
# Entrypoint script to set up environment and start DCCF

# Detect kernel version and set BCC_KERNEL_SOURCE
KERNEL_VERSION=$(uname -r)
export BCC_KERNEL_SOURCE=/lib/modules/${KERNEL_VERSION}/build

echo "Detected kernel version: ${KERNEL_VERSION}"
echo "Setting BCC_KERNEL_SOURCE to: ${BCC_KERNEL_SOURCE}"

# Check if kernel headers are available
if [ ! -d "${BCC_KERNEL_SOURCE}" ]; then
    echo "WARNING: Kernel headers not found at ${BCC_KERNEL_SOURCE}"
    echo "eBPF compilation may fail. Please install kernel headers on the host:"
    echo "  sudo apt-get install linux-headers-${KERNEL_VERSION}"
fi

# Set Python path to include Casmella modules
export PYTHONPATH=/casmella:$PYTHONPATH

# Start the Casmella eBPF agent
exec python3 /casmella/casmella/main.py --config /config/agent-config.yaml