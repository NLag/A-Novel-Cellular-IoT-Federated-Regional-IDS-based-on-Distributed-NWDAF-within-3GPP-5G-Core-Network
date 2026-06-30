/*
 * Licensed to the OpenAirInterface (OAI) Software Alliance under one or more
 * contributor license agreements.  See the NOTICE file distributed with
 * this work for additional information regarding copyright ownership.
 * The OpenAirInterface Software Alliance licenses this file to You under
 * the OAI Public License, Version 1.1  (the "License"); you may not use this
 * file except in compliance with the License. You may obtain a copy of the
 * License at
 *
 *      http://www.openairinterface.org/?page_id=698
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *-------------------------------------------------------------------------------
 * For more information about the OpenAirInterface (OAI) Software Alliance:
 *      contact@openairinterface.org
 */

/*
 * Author: Abdelkader Mekrache <mekrache@eurecom.fr>
 * Author: Karim Boutiba 	   <boutiba@eurecom.fr>
 * Author: Arina Prostakova    <prostako@eurecom.fr>
 * Description: This file contains functions related pcf post notifications.
 */

package sbi

import (
	"context"
	"encoding/json"
	"io/ioutil"
	"log"
	"net/http"
	"time"

	pcf_client "gitlab.eurecom.fr/oai/cn5g/oai-cn5g-nwdaf/components/oai-nwdaf-sbi/internal/pcfclient"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo/options"
)

// ------------------------------------------------------------------------------
func storePcfNotificationOnDB(w http.ResponseWriter, r *http.Request) {
	switch r.Method {

	case "POST":
		log.Printf("Storing PCF notification in Database")
		body, err := ioutil.ReadAll(r.Body)
		if err != nil {
			http.Error(w, "Error reading request body", http.StatusInternalServerError)
			return
		}
		var pcfNotification pcf_client.PcEventExposureNotif
		err = json.Unmarshal(body, &pcfNotification)
		if err != nil {
			http.Error(w, "Error unmarshaling JSON", http.StatusBadRequest)
			return
		}
		eventNotifs := pcfNotification.EventNotifs
		if len(eventNotifs) == 0 {
			http.Error(w, "Error: no EventNotifs in PCF notification", http.StatusBadRequest)
			return
		}
		databaseName := config.Database.DbName
		collectionName := config.Database.CollectionPcfName
		pcfCollection := mongoClient.Database(databaseName).Collection(collectionName)
		opts := options.Update().SetUpsert(true)
		// store notifications one by one
		for _, notif := range eventNotifs {
			// Get UE identifier from PDU session information or SUPI/GPSI
			oid := notif.Supi
			if oid == "" {
				oid = notif.Gpsi
				if oid == "" {
					// Try to get from PDU session info
					if notif.PduSessionInfo.UeMac != "" {
						oid = notif.PduSessionInfo.UeMac
					} else {
						http.Error(w, "ue identifier (supi, gpsi, or ueMac) not found in notification", http.StatusBadRequest)
						return
					}
				}
			}
			update, err := getUpdateByPcfNotif(notif)
			if err != nil {
				log.Printf("error in getUpdateByPcfNotif: %v", err)
				continue
			}
			// Update/Insert the PCF notification
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer cancel()
			res, err := pcfCollection.UpdateByID(ctx, oid, update, opts)
			if err != nil {
				log.Printf("error in updating the PCF collection: %v", err)
				continue
			}
			if res.MatchedCount != 0 {
				log.Printf("matched and updated an existing notification from PCF")
			}
			if res.UpsertedCount != 0 {
				log.Printf("inserted a new notification from PCF with ID %v\n",
					res.UpsertedID)
			}
		}
		w.WriteHeader(http.StatusOK)

	default:
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
	}
}

// ------------------------------------------------------------------------------
// getUpdateByPcfNotif - Return update bson.D by PCF notification
func getUpdateByPcfNotif(notif pcf_client.PcEventNotification) (bson.D, error) {
	var update bson.D
	var err error
	
	// Note: PcEvent in the generated code is an empty struct, but EventNotifs contain event type info
	// We need to check the fields present in the notification to determine the event type
	
	// Check if it's an Access Type Change event (has AccType)
	if notif.AccType != "" {
		update, err = getUpdateAccessTypeChange(notif)
		if err == nil {
			return update, nil
		}
	}
	
	// Check if it's a PLMN Change event
	if notif.PlmnId.Mcc != "" {
		update, err = getUpdatePlmnChange(notif)
		if err == nil {
			return update, nil
		}
	}
	
	// Default: store the complete notification
	log.Printf("PCF event type not specifically handled, storing complete notification")
	return getUpdateGenericPcfEvent(notif)
}

// ------------------------------------------------------------------------------
// getUpdateAccessTypeChange - Create update bson.D in case of Access Type Change
func getUpdateAccessTypeChange(notif pcf_client.PcEventNotification) (bson.D, error) {
	timeStamp := time.Now().Unix()
	push := accessTypeChange{
		AccType:      notif.AccType,
		RatType:      notif.RatType,
		Snssai:       &notif.PduSessionInfo.Snssai,
		Dnn:          &notif.PduSessionInfo.Dnn,
		PduSessInfo:  &notif.PduSessionInfo,
		TimeStamp:    timeStamp,
	}
	update := bson.D{
		{"$set", bson.D{
			{"lastmodified", timeStamp},
		}},
		{"$push", bson.M{
			"accesstypechangelist": &push,
		}},
	}
	return update, nil
}

// ------------------------------------------------------------------------------
// getUpdatePlmnChange - Create update bson.D in case of PLMN Change
func getUpdatePlmnChange(notif pcf_client.PcEventNotification) (bson.D, error) {
	timeStamp := time.Now().Unix()
	push := plmnChange{
		PlmnId:      &notif.PlmnId,
		Snssai:      &notif.PduSessionInfo.Snssai,
		Dnn:         &notif.PduSessionInfo.Dnn,
		PduSessInfo: &notif.PduSessionInfo,
		TimeStamp:   timeStamp,
	}
	update := bson.D{
		{"$set", bson.D{
			{"lastmodified", timeStamp},
		}},
		{"$push", bson.M{
			"plmnchangelist": &push,
		}},
	}
	return update, nil
}

// ------------------------------------------------------------------------------
// getUpdateGenericPcfEvent - Create update bson.D for generic PCF events
func getUpdateGenericPcfEvent(notif pcf_client.PcEventNotification) (bson.D, error) {
	timeStamp := time.Now().Unix()
	push := genericPcfEvent{
		Notification: notif,
		TimeStamp:    timeStamp,
	}
	update := bson.D{
		{"$set", bson.D{
			{"lastmodified", timeStamp},
		}},
		{"$push", bson.M{
			"pcfeventlist": &push,
		}},
	}
	return update, nil
}
