#!/bin/bash

echo "==================================="
echo "Complete Cleanup - Removing Everything"
echo "==================================="

# Stop gnbsim
echo "Stopping gnbsim..."
cd ~/oai/oai-cn5g-fed
docker-compose -f docker-compose/docker-compose-gnbsim-vpp.yaml down 2>/dev/null || true

# Stop manually started NWDAF SBI
echo "Stopping manually started NWDAF SBI..."
docker stop oai-nwdaf-sbi 2>/dev/null || true
docker rm oai-nwdaf-sbi 2>/dev/null || true

# Stop NWDAF components
echo "Stopping NWDAF components..."
cd ~/oai/oai-cn5g-nwdaf
docker-compose -f docker-compose/docker-compose-nwdaf-cn-http2.yaml down 2>/dev/null || true
docker-compose -f docker-compose/docker-compose-nwdaf-cn-http1.yaml down 2>/dev/null || true

# Stop 5G Core
echo "Stopping 5G Core Network..."
cd ~/oai/oai-cn5g-fed/docker-compose
python3 ./core-network.py --type stop-basic-vpp --scenario 1 2>/dev/null || true

sleep 5

# Remove all NWDAF and OAI containers
echo "Removing all containers..."
docker ps -a | grep -E "oai-|nwdaf|gnbsim|vpp-upf" | awk '{print $1}' | xargs -r docker rm -f

# Remove NWDAF images
echo "Removing NWDAF images..."
docker images | grep nwdaf | awk '{print $3}' | xargs -r docker rmi -f

# Remove networks
echo "Removing Docker networks..."
docker network rm demo-oai-public-net 2>/dev/null || true
docker network rm oai-public-access 2>/dev/null || true
docker network rm oai-public-core 2>/dev/null || true

# Remove volumes
echo "Removing Docker volumes..."
docker volume ls | grep -E "oai|nwdaf" | awk '{print $2}' | xargs -r docker volume rm

# Clean up dangling images and build cache
echo "Cleaning up Docker system..."
docker system prune -f
