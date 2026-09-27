#!/bin/bash

# ssh Core5G 'screen -S extractingNAS -X stuff "echo testing remote command^M"'

for i in {1..5}; do
    for j in {1..5}; do

        echo "Clean screen sessions..."
        if ssh Core5G 'screen -list' | grep -q "extractingNAS.*(Detached)"; then
            ssh Core5G 'screen -S extractingNAS -X stuff "^C"'
            ssh Core5G 'screen -S extractingNAS -X quit'
        elif ssh Core5G 'screen -list' | grep -q "extractingNAS.*(Dead)"; then
            ssh Core5G 'screen -wipe'
        else
            echo "no extractingNAS screen session found"
        fi
        ssh Core5G 'screen -dmS extractingNAS'

        if ssh UESimbox 'screen -list' | grep -q "emulateIoT.*(Detached)"; then
            ssh UESimbox 'screen -S emulateIoT -X stuff "^C"'
            ssh UESimbox 'screen -S emulateIoT -X quit'
        elif ssh UESimbox 'screen -list' | grep -q "emulateIoT.*(Dead)"; then
            ssh UESimbox 'screen -wipe'
        else
            echo "no emulateIoT screen session found"
        fi
        ssh UESimbox 'screen -dmS emulateIoT'

        echo "Restarting lte services"

        ssh Core5G 'screen -S extractingNAS -X stuff "service lte restart^M"'
        ssh UESimbox 'screen -S emulateIoT -X stuff "service lte restart^M"'
        cat mqtt_reset_num | ssh MqttServer "sudo -p '' -S systemctl restart mosquitto.service"
        cat mqtt_reset_num | ssh MqttServer "sudo -p '' -S systemctl restart aiocoapServer.service"

        echo "Waiting for services to restart..."
        sleep 120
        
        echo "Starting packet capturing..."
        ssh Core5G 'screen -S extractingNAS -X stuff "/root/IDS_DL/regional_NAS_dataset/extract_NAS.py &>> /root/IDS_DL/regional_NAS_dataset/logs/extract_NAS_\$(date +%Y%m%d_%H%M%S).log^M"'
        sleep 10

        echo "Emulating IoT with $i MQTT + $j COAP..."
        ssh UESimbox "screen -S emulateIoT -X stuff \"/root/IoTClient/executeIoT.sh $i $j &>> /root/IoTClient/logs/executeIoT_\$(date +%Y%m%d_%H%M%S).log^M\""
        sleep 10

        sleep 4200
    done
done