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

docker network prune -f

echo ""
echo "==================================="
echo "All components stopped. Waiting 5 seconds..."
echo "==================================="
sleep 5

echo ""
echo "==================================="
echo "Starting All Components"
echo "==================================="
# Start 5G Core Network
echo "Starting 5G Core Network..."
cd ~/oai/oai-cn5g-fed/docker-compose
python3 ./core-network.py --type start-basic-vpp --scenario 1
# docker-compose -f docker-compose-basic-vpp-pcf-redirection.yaml up -d


echo ""
echo "Waiting 30 seconds for 5G Core to stabilize..."
sleep 30

# Start NWDAF
echo "Starting NWDAF..."
cd ~/oai/oai-cn5g-nwdaf
docker-compose -f docker-compose/docker-compose-nwdaf-cn-http2.yaml up -d --force-recreate

echo ""
echo "Waiting 15 seconds for NWDAF to subscribe to AMF/SMF..."
sleep 15

# Start gnbsim
echo "Starting gnbsim..."
cd ~/oai/oai-cn5g-fed
docker-compose -f docker-compose/docker-compose-gnbsim-vpp.yaml up -d --force-recreate

echo ""
echo "Waiting 10 seconds for UE to attach..."
sleep 10

echo ""
echo "==================================="
echo "All Components Started!"
echo "==================================="

# Check status
echo ""
echo "Checking component status..."
echo ""
echo "5G Core Network:"
cd ~/oai/oai-cn5g-fed/docker-compose
#docker-compose -f docker-compose-basic-vpp-pcf-redirection.yaml ps
docker-compose -f docker-compose-basic-vpp-nrf.yaml ps -a

echo ""
echo "NWDAF Components:"
cd ~/oai/oai-cn5g-nwdaf
docker-compose -f docker-compose/docker-compose-nwdaf-cn-http2.yaml ps  

echo ""
echo "gnbsim:"
cd ~/oai/oai-cn5g-fed
docker ps | grep gnbsim

echo ""
echo "==================================="
echo "Setup Complete!"
echo "==================================="
echo ""
echo "Verification Commands:"
echo " # Check if NWDAF received notifications:"
echo " docker logs oai-nwdaf-sbi | grep -E 'Storing|Inserted|Matched'"
echo ""
echo " # Check database:"
echo " docker exec -it oai-nwdaf-database mongosh --eval 'use testing; db.amf.countDocuments({})'"
echo ""
echo " # Test analytics:"
echo " cd ~/oai/oai-cn5g-nwdaf/cli"
echo " source env/bin/activate"
echo " python nwdaf.py analytics examples/analytics/numUe.json"


## PCF
# curl -X POST http://localhost:6062/test/pcf -H "Content-Type: application/json" -d '{"notifId":"pcf-test-1","eventNotifs":[{"event":{},"supi":"imsi-208950000000031","timeStamp":"2025-10-29T10:00:00Z","accType":"3GPP_ACCESS","pduSessionInfo":{"snssai":{"sst":222,"sd":"00007b"},"dnn":"default","ueMac":"00:11:22:33:44:55"}}]}'
# docker logs oai-nwdaf-sbi --tail 20 | grep -A 5 "PCF\|pcf\|test/pcf"
# docker exec -it oai-nwdaf-database mongosh testing --quiet --eval 'db.getCollectionNames()'
# docker exec -it oai-nwdaf-database mongosh testing --quiet --eval 'db.pcf.find().pretty()'

