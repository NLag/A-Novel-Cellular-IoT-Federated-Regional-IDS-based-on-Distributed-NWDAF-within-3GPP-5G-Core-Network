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
 * Description: This file contains utils functions.
 */

package sbi

import (
	"bytes"
	"context"
	"encoding/json"
	"io/ioutil"
	"log"
	"net/http"
	"time"

	"github.com/kelseyhightower/envconfig"
	amf_client "gitlab.eurecom.fr/oai/cn5g/oai-cn5g-nwdaf/components/oai-nwdaf-sbi/internal/amfclient"
	pcf_client "gitlab.eurecom.fr/oai/cn5g/oai-cn5g-nwdaf/components/oai-nwdaf-sbi/internal/pcfclient"
	smf_client "gitlab.eurecom.fr/oai/cn5g/oai-cn5g-nwdaf/components/oai-nwdaf-sbi/internal/smfclient"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

// ------------------------------------------------------------------------------
// InitConfig - Initialize global variables (cfg and mongoClient) and subscribe to AMF and SMF
func InitConfig() {
	err := envconfig.Process("", &config)
	if err != nil {
		log.Fatal(err.Error())
	}
	clientOptions := options.Client().ApplyURI(config.Database.Uri)
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	client, err := mongo.Connect(ctx, clientOptions)
	if err != nil {
		log.Fatal(err)
	}
	log.Printf("Connected to MongoDB.")
	mongoClient = client

	// Check if we should use DCCF for all data collection
	dccfOnlyMode := config.DataCollectionMode == "DCCF_ONLY"
	if dccfOnlyMode {
		log.Printf("Data collection mode: DCCF_ONLY - skipping direct NF subscriptions")
	}

	// Subscribe to AMF events only if not in DCCF-only mode and AMF is configured
	if !dccfOnlyMode && config.Amf.IpAddr != "" {
		amfEventSubscription(
			config.Server.NotifUri+config.Amf.ApiRoute,
			config.Amf.NotifCorrId,
			config.Amf.NotifId,
		)
	} else if config.Amf.IpAddr == "" {
		log.Printf("AMF IP address not configured - skipping AMF subscription")
	}

	// Subscribe to SMF events only if not in DCCF-only mode and SMF is configured
	if !dccfOnlyMode && config.Smf.IpAddr != "" {
		smfEventSubscription(
			config.Server.NotifUri+config.Smf.ApiRoute,
			config.Smf.NotifId,
		)
	} else if config.Smf.IpAddr == "" {
		log.Printf("SMF IP address not configured - skipping SMF subscription")
	}

	// Subscribe to PCF events only if not in DCCF-only mode and PCF is configured
	if !dccfOnlyMode && config.Pcf.IpAddr != "" {
		pcfEventSubscription(
			config.Server.NotifUri+config.Pcf.ApiRoute,
			config.Pcf.NotifId,
		)
	} else if config.Pcf.IpAddr == "" {
		log.Printf("PCF IP address not configured - skipping PCF subscription")
	}

	// Register with NRF as NWDAF
	InitNRFRegistration()
	// Initialize DCCF client for fetching analytics data
	InitDCCFClient()
	// Subscribe to DCCF for push notifications
	InitDCCFSubscription()
}

// ------------------------------------------------------------------------------
func amfEventSubscription(
	amfEventNotifyUri string,
	amfNotifyCorrelationId string,
	amfNfId string,
) {
	// Store all AMF event types
	var amfEvents []amf_client.AmfEvent
	for _, amfEventTypeAnyOf := range amf_client.AllowedAmfEventTypeAnyOfEnumValues {
		amfEvents = append(amfEvents, *amf_client.NewAmfEvent(amfEventTypeAnyOf))
	}
	// Subscribe to all AMF event types
	amfCreateEventSubscription := *amf_client.NewAmfCreateEventSubscription(
		*amf_client.NewAmfEventSubscription(
			amfEvents,
			amfEventNotifyUri,
			amfNotifyCorrelationId,
			amfNfId,
		),
	)
	configuration := amf_client.NewConfiguration()
	amfApiClient := amf_client.NewAPIClient(configuration)
	resp, r, err := amfApiClient.SubscriptionsCollectionCollectionApi.CreateSubscription(
		context.Background()).AmfCreateEventSubscription(amfCreateEventSubscription).Execute()
	if err != nil {
		log.Printf(
			"Error when calling `SubscriptionsCollectionCollectionApi.CreateSubscription``: %v\n",
			err,
		)
		log.Printf("Full HTTP response: %v\n", r)
	}
	// response from `CreateSubscription`: AmfCreatedEventSubscription
	log.Printf(
		"Response from `SubscriptionsCollectionCollectionApi.CreateSubscription`: %v\n",
		resp,
	)
}

// ------------------------------------------------------------------------------
func smfEventSubscription(smfEventNotifyUri string, smfNfId string) {

	// Store all SMF event types
	var smfEventSubs []smf_client.EventSubscription
	smfEventSubs = append(smfEventSubs,
		*smf_client.NewEventSubscription(smf_client.SMFEVENTANYOF_PDU_SES_EST),
	)
	smfEventSubs = append(smfEventSubs,
		*smf_client.NewEventSubscription(smf_client.SMFEVENTANYOF_UE_IP_CH),
	)
	smfEventSubs = append(smfEventSubs,
		*smf_client.NewEventSubscription(smf_client.SMFEVENTANYOF_PLMN_CH),
	)
	smfEventSubs = append(smfEventSubs,
		*smf_client.NewEventSubscription(smf_client.SMFEVENTANYOF_DDDS),
	)
	smfEventSubs = append(smfEventSubs,
		*smf_client.NewEventSubscription(smf_client.SMFEVENTANYOF_PDU_SES_REL),
	)
	smfEventSubs = append(smfEventSubs,
		*smf_client.NewEventSubscription(smf_client.SMFEVENTANYOF_QOS_MON),
	)
	// Subscribe to all SMF event types
	nsmfEventExposure := *smf_client.NewNsmfEventExposure(
		smfNfId,
		smfEventNotifyUri,
		smfEventSubs,
	)
	configuration := smf_client.NewConfiguration()
	smfApiClient := smf_client.NewAPIClient(configuration)
	resp, r, err := smfApiClient.SubscriptionsCollectionApi.CreateIndividualSubcription(
		context.Background()).NsmfEventExposure(nsmfEventExposure).Execute()
	if err != nil {
		log.Printf(
			"Error when calling `SubscriptionsCollectionApi.CreateIndividualSubcription``: %v\n",
			err,
		)
		log.Printf("Full HTTP response: %v\n", r)
	}
	// response from `CreateIndividualSubcription`: NsmfEventExposure
	log.Printf(
		"Response from `SubscriptionsCollectionApi.CreateIndividualSubcription`: %v\n",
		resp,
	)
}

// ------------------------------------------------------------------------------
func pcfEventSubscription(pcfEventNotifyUri string, pcfNfId string) {
	// Store all PCF event types
	var pcfEvents []pcf_client.PcEvent
	// Note: PcEvent in the generated client is an empty struct
	// The actual event types are defined as PcEventAnyOf constants
	// For now, we create empty PcEvent structs - the actual event filtering
	// happens based on notification content
	pcfEvents = append(pcfEvents, pcf_client.PcEvent{})

	// Subscribe to PCF event types
	pcfEventExposureSubsc := pcf_client.PcEventExposureSubsc{
		NotifUri:  pcfEventNotifyUri,
		NotifId:   pcfNfId,
		EventSubs: pcfEvents,
	}

	// Make HTTP request to PCF subscription endpoint
	subscriptionData, err := json.Marshal(pcfEventExposureSubsc)
	if err != nil {
		log.Printf("Error marshaling PCF subscription data: %v\n", err)
		return
	}

	pcfSubscriptionUrl := config.Pcf.IpAddr + config.Pcf.SubRoute + "/subscriptions"
	log.Printf("Subscribing to PCF events at: %s\n", pcfSubscriptionUrl)

	resp, err := http.Post(pcfSubscriptionUrl, "application/json", bytes.NewBuffer(subscriptionData))
	if err != nil {
		log.Printf("Error when calling PCF subscription API: %v\n", err)
		return
	}
	defer resp.Body.Close()

	body, _ := ioutil.ReadAll(resp.Body)
	log.Printf("Response from PCF subscription (status %d): %s\n", resp.StatusCode, string(body))
}
