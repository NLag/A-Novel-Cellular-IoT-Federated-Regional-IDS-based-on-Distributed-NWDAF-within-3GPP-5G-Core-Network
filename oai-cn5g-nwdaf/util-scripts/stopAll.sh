#!/bin/bash
echo "==================================="
echo "Stopping All Components"
echo "==================================="
# Stop gnbsim
echo "Stopping gnbsim..."
cd ~/oai/oai-cn5g-fed
docker-compose -f docker-compose/docker-compose-gnbsim-vpp.yaml down

# Stop NWDAF
echo "Stopping NWDAF..."
cd ~/oai/oai-cn5g-nwdaf
docker-compose -f docker-compose/docker-compose-nwdaf-cn-http2.yaml down 

# Stop 5G Core Network
echo "Stopping 5G Core Network..."
cd ~/oai/oai-cn5g-fed/docker-compose
python3 ./core-network.py --type stop-basic-vpp --scenario 1
#docker-compose -f docker-compose-basic-vpp-pcf-redirection.yaml down

# Stop DCCF
echo "Stopping DCCF..."
cd ~/oai/oai-cn5g-nwdaf/components/oai-nwdaf-dccf/docker-compose
docker-compose -f docker-compose-dccf.yaml down


docker network prune -f

echo ""
echo "==================================="
echo "All components stopped. Waiting 5 seconds..."
echo "==================================="
sleep 5
