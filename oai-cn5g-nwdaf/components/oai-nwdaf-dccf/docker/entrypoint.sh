#!/bin/bash
# MTLF Entrypoint Script
# Keeps the pod running so users can exec in to run training commands.
# Also sets up the mtlf CLI alias.

set -e

echo "=============================================="
echo "  NWDAF MTLF (Model Training Logical Function)"
echo "=============================================="
echo ""
echo "Available commands:"
echo "  mtlf status    - Show available data and models"
echo "  mtlf extract   - Extract data from DCCF database"
echo "  mtlf process   - Convert CSVs to graph dataset"
echo "  mtlf train     - Train GNN autoencoder"
echo "  mtlf test      - Evaluate model / detect anomalies"
echo "  mtlf pipeline  - Full end-to-end pipeline"
echo ""
echo "Run 'mtlf --help' for detailed usage."
echo ""

# Create workspace directories
mkdir -p /workspace/raw /models

# Use non-interactive matplotlib backend
export MPLBACKEND=Agg

# Print status on startup
python /app/mtlf_cli.py status 2>/dev/null || echo "(status check skipped - database may not be mounted yet)"

echo ""
echo "Pod is ready. Use 'kubectl exec' to run training commands."
echo "Waiting..."

# Keep the container alive
exec sleep infinity
