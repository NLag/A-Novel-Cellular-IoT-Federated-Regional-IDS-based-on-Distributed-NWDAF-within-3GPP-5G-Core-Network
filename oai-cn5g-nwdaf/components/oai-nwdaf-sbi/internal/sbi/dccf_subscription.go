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
 * Description: DCCF subscription client and notification handler for OAI NWDAF
 * Implements 3GPP TS 29.552 Ndccf_DataManagement subscription/notification
 */

package sbi

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"sync"
	"time"
)

// SubscriptionRequest represents a request to subscribe to DCCF
type SubscriptionRequest struct {
	NotificationURI      string   `json:"notificationUri"`
	NFID                 string   `json:"nfId"`
	EventTypes           []string `json:"eventTypes"`
	Protocols            []string `json:"protocols"`
	ExpiryTime           string   `json:"expiryTime,omitempty"`
	NotificationInterval int      `json:"notificationInterval"`
}

// SubscriptionResponse represents the response from DCCF subscription
type SubscriptionResponse struct {
	SubscriptionID       string   `json:"subscriptionId"`
	NotificationURI      string   `json:"notificationUri"`
	NFID                 string   `json:"nfId"`
	EventTypes           []string `json:"eventTypes"`
	Protocols            []string `json:"protocols"`
	NotificationInterval int      `json:"notificationInterval"`
	CreatedAt            string   `json:"createdAt"`
}

// DCCFNotification represents a notification from DCCF
type DCCFNotification struct {
	SubscriptionID   string                 `json:"subscriptionId"`
	NotificationType string                 `json:"notificationType"`
	Timestamp        string                 `json:"timestamp"`
	AnalyticsData    map[string]interface{} `json:"analyticsData"`
}

// NotificationHandler is called when a notification is received
type NotificationHandler func(notification *DCCFNotification)

// DCCFSubscriptionClient handles subscriptions to DCCF
type DCCFSubscriptionClient struct {
	dccfEndpoint      string
	notificationURI   string
	nfInstanceID      string
	subscriptionID    string
	client            *http.Client
	handler           NotificationHandler
	mutex             sync.RWMutex
	latestData        map[string]interface{}
}

// NewDCCFSubscriptionClient creates a new subscription client
func NewDCCFSubscriptionClient(dccfEndpoint, notificationURI, nfInstanceID string) *DCCFSubscriptionClient {
	return &DCCFSubscriptionClient{
		dccfEndpoint:    dccfEndpoint,
		notificationURI: notificationURI,
		nfInstanceID:    nfInstanceID,
		client:          &http.Client{Timeout: 30 * time.Second},
		latestData:      make(map[string]interface{}),
	}
}

// SetNotificationHandler sets the handler for incoming notifications
func (c *DCCFSubscriptionClient) SetNotificationHandler(handler NotificationHandler) {
	c.handler = handler
}

// Subscribe creates a subscription to DCCF
func (c *DCCFSubscriptionClient) Subscribe(eventTypes []string, protocols []string, intervalSeconds int) error {
	if c.dccfEndpoint == "" {
		return fmt.Errorf("DCCF endpoint not configured")
	}

	request := SubscriptionRequest{
		NotificationURI:      c.notificationURI,
		NFID:                 c.nfInstanceID,
		EventTypes:           eventTypes,
		Protocols:            protocols,
		NotificationInterval: intervalSeconds,
	}

	requestJSON, err := json.Marshal(request)
	if err != nil {
		return fmt.Errorf("failed to marshal subscription request: %v", err)
	}

	url := fmt.Sprintf("%s/ndccf-datamanagement/v1/subscriptions", c.dccfEndpoint)
	log.Printf("Subscribing to DCCF at %s", url)

	resp, err := c.client.Post(url, "application/json", bytes.NewBuffer(requestJSON))
	if err != nil {
		return fmt.Errorf("failed to subscribe to DCCF: %v", err)
	}
	defer resp.Body.Close()

	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("failed to read response body: %v", err)
	}

	if resp.StatusCode != http.StatusCreated && resp.StatusCode != http.StatusOK {
		return fmt.Errorf("DCCF subscription failed with status %d: %s", resp.StatusCode, string(body))
	}

	var response SubscriptionResponse
	if err := json.Unmarshal(body, &response); err != nil {
		return fmt.Errorf("failed to unmarshal subscription response: %v", err)
	}

	c.subscriptionID = response.SubscriptionID
	log.Printf("Successfully subscribed to DCCF with subscription ID: %s", c.subscriptionID)

	return nil
}

// Unsubscribe removes the subscription from DCCF
func (c *DCCFSubscriptionClient) Unsubscribe() error {
	if c.subscriptionID == "" {
		return nil
	}

	url := fmt.Sprintf("%s/ndccf-datamanagement/v1/subscriptions/%s", c.dccfEndpoint, c.subscriptionID)

	req, err := http.NewRequest(http.MethodDelete, url, nil)
	if err != nil {
		return fmt.Errorf("failed to create unsubscribe request: %v", err)
	}

	resp, err := c.client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to unsubscribe from DCCF: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNoContent || resp.StatusCode == http.StatusOK {
		log.Printf("Successfully unsubscribed from DCCF (subscription: %s)", c.subscriptionID)
		c.subscriptionID = ""
		return nil
	}

	return fmt.Errorf("DCCF unsubscribe failed with status %d", resp.StatusCode)
}

// HandleNotification processes an incoming notification from DCCF
func (c *DCCFSubscriptionClient) HandleNotification(notification *DCCFNotification) {
	c.mutex.Lock()
	defer c.mutex.Unlock()

	// Store the latest data
	for key, value := range notification.AnalyticsData {
		c.latestData[key] = value
	}

	log.Printf("Received DCCF notification (subscription: %s, type: %s)",
		notification.SubscriptionID, notification.NotificationType)

	// Call the custom handler if set
	if c.handler != nil {
		c.handler(notification)
	}
}

// GetLatestData returns the latest analytics data received from notifications
func (c *DCCFSubscriptionClient) GetLatestData() map[string]interface{} {
	c.mutex.RLock()
	defer c.mutex.RUnlock()

	// Return a copy
	data := make(map[string]interface{})
	for k, v := range c.latestData {
		data[k] = v
	}
	return data
}

// GetSubscriptionID returns the current subscription ID
func (c *DCCFSubscriptionClient) GetSubscriptionID() string {
	return c.subscriptionID
}

// IsSubscribed returns whether there is an active subscription
func (c *DCCFSubscriptionClient) IsSubscribed() bool {
	return c.subscriptionID != ""
}

// Global subscription client instance
var dccfSubscriptionClient *DCCFSubscriptionClient

// InitDCCFSubscription initializes and creates a subscription to DCCF
func InitDCCFSubscription() {
	client := GetDCCFClient()
	if client == nil || client.endpoint == "" {
		log.Println("DCCF client not available, skipping subscription initialization")
		return
	}

	// Build notification URI from server config
	notificationURI := fmt.Sprintf("%s/dccf/notifications", config.Server.NotifUri)

	dccfSubscriptionClient = NewDCCFSubscriptionClient(
		client.endpoint,
		notificationURI,
		config.Nrf.NFInstanceID,
	)

	// Set default notification handler
	dccfSubscriptionClient.SetNotificationHandler(func(notification *DCCFNotification) {
		log.Printf("Processing DCCF notification: %v", notification.AnalyticsData)
		// TODO: Process analytics data and update internal state
	})

	// Subscribe to all event types
	err := dccfSubscriptionClient.Subscribe(
		[]string{"NF_LOAD", "UE_MOBILITY", "QOS_SUSTAINABILITY"},
		[]string{"http2", "ngap", "pfcp", "gtpu", "nas"},
		60, // 60 second notification interval
	)

	if err != nil {
		log.Printf("Failed to subscribe to DCCF: %v", err)
	}
}

// GetDCCFSubscriptionClient returns the global subscription client
func GetDCCFSubscriptionClient() *DCCFSubscriptionClient {
	return dccfSubscriptionClient
}

// DCCFNotificationHandler is the HTTP handler for DCCF notifications
func DCCFNotificationHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
		return
	}

	body, err := ioutil.ReadAll(r.Body)
	if err != nil {
		log.Printf("Failed to read notification body: %v", err)
		http.Error(w, "Failed to read body", http.StatusBadRequest)
		return
	}
	defer r.Body.Close()

	var notification DCCFNotification
	if err := json.Unmarshal(body, &notification); err != nil {
		log.Printf("Failed to unmarshal notification: %v", err)
		http.Error(w, "Invalid notification format", http.StatusBadRequest)
		return
	}

	// Process the notification
	if dccfSubscriptionClient != nil {
		dccfSubscriptionClient.HandleNotification(&notification)
	}

	w.WriteHeader(http.StatusOK)
}
