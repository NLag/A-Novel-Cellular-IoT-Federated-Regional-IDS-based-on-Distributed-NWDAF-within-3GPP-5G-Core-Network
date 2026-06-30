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
 * Description: DCCF client for fetching analytics data via Ndccf_DataManagement (3GPP TS 29.552)
 */

package sbi

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"net/url"
	"time"
)

// NFLoadAnalytics represents NF Load analytics data from DCCF
type NFLoadAnalytics struct {
	AnalyticsType string `json:"analyticsType"`
	TimeWindow    struct {
		StartTime string `json:"startTime"`
		EndTime   string `json:"endTime"`
	} `json:"timeWindow"`
	NFLoadData []struct {
		NFInstanceID      string   `json:"nfInstanceId"`
		EventCount        int      `json:"eventCount"`
		AvgResponseTimeMs *float64 `json:"avgResponseTimeMs"`
	} `json:"nfLoadData"`
}

// UEMobilityAnalytics represents UE Mobility analytics data from DCCF
type UEMobilityAnalytics struct {
	AnalyticsType string `json:"analyticsType"`
	TimeWindow    struct {
		StartTime string `json:"startTime"`
		EndTime   string `json:"endTime"`
	} `json:"timeWindow"`
	MobilityEvents []struct {
		EventType string `json:"eventType"`
		Count     int    `json:"count"`
	} `json:"mobilityEvents"`
}

// QoSSustainabilityAnalytics represents QoS Sustainability analytics from DCCF
type QoSSustainabilityAnalytics struct {
	AnalyticsType string `json:"analyticsType"`
	TimeWindow    struct {
		StartTime string `json:"startTime"`
		EndTime   string `json:"endTime"`
	} `json:"timeWindow"`
	QoSEvents []struct {
		Protocol  string `json:"protocol"`
		EventType string `json:"eventType"`
		Count     int    `json:"count"`
	} `json:"qosEvents"`
}

// AllAnalytics contains all analytics types
type AllAnalytics struct {
	NFLoad            NFLoadAnalytics            `json:"nfLoad"`
	UEMobility        UEMobilityAnalytics        `json:"ueMobility"`
	QoSSustainability QoSSustainabilityAnalytics `json:"qosSustainability"`
}

// ProtocolEvent represents a single protocol event from DCCF
type ProtocolEvent struct {
	ID          int    `json:"id"`
	Timestamp   string `json:"timestamp"`
	Protocol    string `json:"protocol"`
	EventType   string `json:"event_type"`
	SrcIP       string `json:"src_ip"`
	DstIP       string `json:"dst_ip"`
	SrcPort     int    `json:"src_port"`
	DstPort     int    `json:"dst_port"`
	SrcPodName  string `json:"src_pod_name"`
	DstPodName  string `json:"dst_pod_name"`
	Metadata    string `json:"metadata"`
}

// EventsResponse represents the response from DCCF data endpoint
type EventsResponse struct {
	Events    []ProtocolEvent `json:"events"`
	Count     int             `json:"count"`
	Timestamp string          `json:"timestamp"`
}

// StatsResponse represents the response from DCCF stats endpoint
type StatsResponse struct {
	TotalEvents      int            `json:"totalEvents"`
	EventsByProtocol map[string]int `json:"eventsByProtocol"`
	Timestamp        string         `json:"timestamp"`
}

// DCCFClient handles communication with DCCF service
type DCCFClient struct {
	endpoint string
	client   *http.Client
}

// NewDCCFClient creates a new DCCF client
func NewDCCFClient(endpoint string) *DCCFClient {
	return &DCCFClient{
		endpoint: endpoint,
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

// GetAnalytics fetches analytics data from DCCF
// analyticsType can be: "NF_LOAD", "UE_MOBILITY", "QOS_SUSTAINABILITY", or empty for all
func (c *DCCFClient) GetAnalytics(analyticsType string, timeWindowMinutes int) (*AllAnalytics, error) {
	if c.endpoint == "" {
		return nil, fmt.Errorf("DCCF endpoint not configured")
	}

	// Build URL with query parameters
	u, err := url.Parse(fmt.Sprintf("%s/ndccf-datamanagement/v1/analytics", c.endpoint))
	if err != nil {
		return nil, fmt.Errorf("failed to parse URL: %v", err)
	}

	q := u.Query()
	if analyticsType != "" {
		q.Set("analytics_type", analyticsType)
	}
	if timeWindowMinutes > 0 {
		q.Set("time_window", fmt.Sprintf("%d", timeWindowMinutes))
	}
	u.RawQuery = q.Encode()

	log.Printf("Fetching analytics from DCCF: %s", u.String())

	resp, err := c.client.Get(u.String())
	if err != nil {
		return nil, fmt.Errorf("failed to fetch analytics from DCCF: %v", err)
	}
	defer resp.Body.Close()

	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %v", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("DCCF returned status %d: %s", resp.StatusCode, string(body))
	}

	var analytics AllAnalytics
	if err := json.Unmarshal(body, &analytics); err != nil {
		return nil, fmt.Errorf("failed to unmarshal analytics: %v", err)
	}

	return &analytics, nil
}

// GetNFLoadAnalytics fetches NF Load analytics specifically
func (c *DCCFClient) GetNFLoadAnalytics(timeWindowMinutes int) (*NFLoadAnalytics, error) {
	if c.endpoint == "" {
		return nil, fmt.Errorf("DCCF endpoint not configured")
	}

	u, err := url.Parse(fmt.Sprintf("%s/ndccf-datamanagement/v1/analytics", c.endpoint))
	if err != nil {
		return nil, fmt.Errorf("failed to parse URL: %v", err)
	}

	q := u.Query()
	q.Set("analytics_type", "NF_LOAD")
	if timeWindowMinutes > 0 {
		q.Set("time_window", fmt.Sprintf("%d", timeWindowMinutes))
	}
	u.RawQuery = q.Encode()

	resp, err := c.client.Get(u.String())
	if err != nil {
		return nil, fmt.Errorf("failed to fetch NF Load analytics: %v", err)
	}
	defer resp.Body.Close()

	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %v", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("DCCF returned status %d: %s", resp.StatusCode, string(body))
	}

	var analytics NFLoadAnalytics
	if err := json.Unmarshal(body, &analytics); err != nil {
		return nil, fmt.Errorf("failed to unmarshal NF Load analytics: %v", err)
	}

	return &analytics, nil
}

// GetUEMobilityAnalytics fetches UE Mobility analytics specifically
func (c *DCCFClient) GetUEMobilityAnalytics(timeWindowMinutes int) (*UEMobilityAnalytics, error) {
	if c.endpoint == "" {
		return nil, fmt.Errorf("DCCF endpoint not configured")
	}

	u, err := url.Parse(fmt.Sprintf("%s/ndccf-datamanagement/v1/analytics", c.endpoint))
	if err != nil {
		return nil, fmt.Errorf("failed to parse URL: %v", err)
	}

	q := u.Query()
	q.Set("analytics_type", "UE_MOBILITY")
	if timeWindowMinutes > 0 {
		q.Set("time_window", fmt.Sprintf("%d", timeWindowMinutes))
	}
	u.RawQuery = q.Encode()

	resp, err := c.client.Get(u.String())
	if err != nil {
		return nil, fmt.Errorf("failed to fetch UE Mobility analytics: %v", err)
	}
	defer resp.Body.Close()

	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %v", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("DCCF returned status %d: %s", resp.StatusCode, string(body))
	}

	var analytics UEMobilityAnalytics
	if err := json.Unmarshal(body, &analytics); err != nil {
		return nil, fmt.Errorf("failed to unmarshal UE Mobility analytics: %v", err)
	}

	return &analytics, nil
}

// GetProtocolEvents fetches raw protocol events from DCCF
func (c *DCCFClient) GetProtocolEvents(protocol string, eventType string, limit int) (*EventsResponse, error) {
	if c.endpoint == "" {
		return nil, fmt.Errorf("DCCF endpoint not configured")
	}

	u, err := url.Parse(fmt.Sprintf("%s/ndccf-datamanagement/v1/data", c.endpoint))
	if err != nil {
		return nil, fmt.Errorf("failed to parse URL: %v", err)
	}

	q := u.Query()
	if protocol != "" {
		q.Set("protocol", protocol)
	}
	if eventType != "" {
		q.Set("event_type", eventType)
	}
	if limit > 0 {
		q.Set("limit", fmt.Sprintf("%d", limit))
	}
	u.RawQuery = q.Encode()

	log.Printf("Fetching protocol events from DCCF: %s", u.String())

	resp, err := c.client.Get(u.String())
	if err != nil {
		return nil, fmt.Errorf("failed to fetch events from DCCF: %v", err)
	}
	defer resp.Body.Close()

	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %v", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("DCCF returned status %d: %s", resp.StatusCode, string(body))
	}

	var events EventsResponse
	if err := json.Unmarshal(body, &events); err != nil {
		return nil, fmt.Errorf("failed to unmarshal events: %v", err)
	}

	return &events, nil
}

// GetStats fetches database statistics from DCCF
func (c *DCCFClient) GetStats() (*StatsResponse, error) {
	if c.endpoint == "" {
		return nil, fmt.Errorf("DCCF endpoint not configured")
	}

	u := fmt.Sprintf("%s/ndccf-datamanagement/v1/stats", c.endpoint)

	log.Printf("Fetching stats from DCCF: %s", u)

	resp, err := c.client.Get(u)
	if err != nil {
		return nil, fmt.Errorf("failed to fetch stats from DCCF: %v", err)
	}
	defer resp.Body.Close()

	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %v", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("DCCF returned status %d: %s", resp.StatusCode, string(body))
	}

	var stats StatsResponse
	if err := json.Unmarshal(body, &stats); err != nil {
		return nil, fmt.Errorf("failed to unmarshal stats: %v", err)
	}

	return &stats, nil
}

// HealthCheck checks if DCCF service is healthy
func (c *DCCFClient) HealthCheck() error {
	if c.endpoint == "" {
		return fmt.Errorf("DCCF endpoint not configured")
	}

	u := fmt.Sprintf("%s/health", c.endpoint)

	resp, err := c.client.Get(u)
	if err != nil {
		return fmt.Errorf("DCCF health check failed: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("DCCF health check returned status %d", resp.StatusCode)
	}

	return nil
}

// Global DCCF client instance
var dccfClient *DCCFClient

// InitDCCFClient initializes the DCCF client
// It first tries to discover DCCF via NRF, then falls back to static configuration
func InitDCCFClient() {
	var endpoint string

	// Try NRF discovery first
	nrfEndpoint := GetNRFEndpoint()
	ownInstanceID := GetOwnInstanceID()

	if nrfEndpoint != "" {
		log.Println("Attempting to discover DCCF via NRF...")
		discoveredEndpoint, err := DiscoverDCCF(nrfEndpoint, ownInstanceID)
		if err != nil {
			log.Printf("NRF discovery failed: %v", err)
		} else {
			endpoint = discoveredEndpoint
			log.Printf("DCCF discovered via NRF: %s", endpoint)
		}
	}

	// Fall back to static configuration if discovery failed
	if endpoint == "" && config.Dccf.Endpoint != "" {
		endpoint = config.Dccf.Endpoint
		log.Printf("Using static DCCF endpoint: %s", endpoint)
	}

	// If still no endpoint, skip initialization
	if endpoint == "" {
		log.Println("DCCF endpoint not available (neither via NRF discovery nor static config), skipping DCCF client initialization")
		return
	}

	dccfClient = NewDCCFClient(endpoint)
	log.Printf("DCCF client initialized with endpoint: %s", endpoint)

	// Perform initial health check
	if err := dccfClient.HealthCheck(); err != nil {
		log.Printf("Warning: DCCF health check failed: %v", err)
	} else {
		log.Println("DCCF service is healthy")
	}
}

// RefreshDCCFEndpoint re-discovers DCCF endpoint via NRF
// Call this if the current endpoint becomes unavailable
func RefreshDCCFEndpoint() error {
	nrfEndpoint := GetNRFEndpoint()
	ownInstanceID := GetOwnInstanceID()

	if nrfEndpoint == "" {
		return fmt.Errorf("NRF endpoint not configured")
	}

	endpoint, err := DiscoverDCCF(nrfEndpoint, ownInstanceID)
	if err != nil {
		return err
	}

	dccfClient = NewDCCFClient(endpoint)
	log.Printf("DCCF client refreshed with new endpoint: %s", endpoint)

	return nil
}

// GetDCCFClient returns the global DCCF client instance
func GetDCCFClient() *DCCFClient {
	return dccfClient
}
