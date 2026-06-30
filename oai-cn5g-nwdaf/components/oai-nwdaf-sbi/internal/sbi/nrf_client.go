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
 * Description: NRF client for NWDAF registration (3GPP TS 29.510)
 */

package sbi

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"time"
)

// NFProfile represents the NF Profile for NRF registration
type NFProfile struct {
	NFInstanceID    string       `json:"nfInstanceId"`
	NFType          string       `json:"nfType"`
	NFStatus        string       `json:"nfStatus"`
	HeartBeatTimer  int          `json:"heartBeatTimer"`
	IPv4Addresses   []string     `json:"ipv4Addresses,omitempty"`
	NFServices      []NFService  `json:"nfServices,omitempty"`
	NWDAFInfo       *NWDAFInfo   `json:"nwdafInfo,omitempty"`
}

// NFService represents an NF service
type NFService struct {
	ServiceInstanceID string       `json:"serviceInstanceId"`
	ServiceName       string       `json:"serviceName"`
	Versions          []NFVersion  `json:"versions"`
	Scheme            string       `json:"scheme"`
	NFServiceStatus   string       `json:"nfServiceStatus"`
	IPEndPoints       []IPEndPoint `json:"ipEndPoints,omitempty"`
}

// NFVersion represents service version
type NFVersion struct {
	APIVersionInURI string `json:"apiVersionInUri"`
	APIFullVersion  string `json:"apiFullVersion"`
}

// IPEndPoint represents IP endpoint
type IPEndPoint struct {
	IPv4Address string `json:"ipv4Address,omitempty"`
	Port        int    `json:"port,omitempty"`
}

// NWDAFInfo contains NWDAF-specific information
type NWDAFInfo struct {
	EventIDs    []string `json:"eventIds,omitempty"`
	NWDAFEvents []string `json:"nwdafEvents,omitempty"`
}

// NRFClient handles NRF registration
type NRFClient struct {
	nrfEndpoint      string
	nfInstanceID     string
	ipv4Address      string
	sbiPort          int
	heartbeatTimer   int
	autoRegister     bool
	registered       bool
	stopHeartbeat    chan struct{}
}

// NewNRFClient creates a new NRF client
func NewNRFClient(nrfEndpoint, nfInstanceID, ipv4Address string, sbiPort, heartbeatTimer int, autoRegister bool) *NRFClient {
	return &NRFClient{
		nrfEndpoint:    nrfEndpoint,
		nfInstanceID:   nfInstanceID,
		ipv4Address:    ipv4Address,
		sbiPort:        sbiPort,
		heartbeatTimer: heartbeatTimer,
		autoRegister:   autoRegister,
		stopHeartbeat:  make(chan struct{}),
	}
}

// buildNFProfile creates the NF Profile for registration
func (c *NRFClient) buildNFProfile() NFProfile {
	return NFProfile{
		NFInstanceID:   c.nfInstanceID,
		NFType:         "NWDAF",
		NFStatus:       "REGISTERED",
		HeartBeatTimer: c.heartbeatTimer,
		IPv4Addresses:  []string{c.ipv4Address},
		NFServices: []NFService{
			{
				ServiceInstanceID: fmt.Sprintf("%s-nnwdaf-eventssubscription", c.nfInstanceID),
				ServiceName:       "nnwdaf-eventssubscription",
				Versions: []NFVersion{
					{
						APIVersionInURI: "v1",
						APIFullVersion:  "1.0.0",
					},
				},
				Scheme:          "http",
				NFServiceStatus: "REGISTERED",
				IPEndPoints: []IPEndPoint{
					{
						IPv4Address: c.ipv4Address,
						Port:        c.sbiPort,
					},
				},
			},
			{
				ServiceInstanceID: fmt.Sprintf("%s-nnwdaf-analyticsinfo", c.nfInstanceID),
				ServiceName:       "nnwdaf-analyticsinfo",
				Versions: []NFVersion{
					{
						APIVersionInURI: "v1",
						APIFullVersion:  "1.0.0",
					},
				},
				Scheme:          "http",
				NFServiceStatus: "REGISTERED",
				IPEndPoints: []IPEndPoint{
					{
						IPv4Address: c.ipv4Address,
						Port:        c.sbiPort,
					},
				},
			},
		},
		NWDAFInfo: &NWDAFInfo{
			EventIDs: []string{
				"NF_LOAD",
				"UE_MOBILITY",
				"UE_COMM",
				"QOS_SUSTAINABILITY",
				"ABNORMAL_BEHAVIOUR",
			},
			NWDAFEvents: []string{
				"NF_LOAD",
				"UE_MOBILITY",
			},
		},
	}
}

// Register registers the NWDAF with NRF
func (c *NRFClient) Register() error {
	if !c.autoRegister {
		log.Println("NRF auto-registration disabled")
		return nil
	}

	if c.nrfEndpoint == "" {
		log.Println("NRF endpoint not configured, skipping registration")
		return nil
	}

	nfProfile := c.buildNFProfile()
	profileJSON, err := json.Marshal(nfProfile)
	if err != nil {
		return fmt.Errorf("failed to marshal NF profile: %v", err)
	}

	url := fmt.Sprintf("%s/nnrf-nfm/v1/nf-instances/%s", c.nrfEndpoint, c.nfInstanceID)
	log.Printf("Registering NWDAF with NRF at %s", url)

	client := &http.Client{Timeout: 10 * time.Second}
	req, err := http.NewRequest(http.MethodPut, url, bytes.NewBuffer(profileJSON))
	if err != nil {
		return fmt.Errorf("failed to create request: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to register with NRF: %v", err)
	}
	defer resp.Body.Close()

	body, _ := ioutil.ReadAll(resp.Body)

	if resp.StatusCode == http.StatusOK || resp.StatusCode == http.StatusCreated {
		c.registered = true
		log.Printf("Successfully registered with NRF (status: %d)", resp.StatusCode)

		// Start heartbeat
		go c.heartbeatLoop()
		return nil
	}

	return fmt.Errorf("NRF registration failed with status %d: %s", resp.StatusCode, string(body))
}

// Deregister removes the NWDAF from NRF
func (c *NRFClient) Deregister() error {
	if !c.registered {
		return nil
	}

	// Stop heartbeat
	close(c.stopHeartbeat)

	url := fmt.Sprintf("%s/nnrf-nfm/v1/nf-instances/%s", c.nrfEndpoint, c.nfInstanceID)

	client := &http.Client{Timeout: 10 * time.Second}
	req, err := http.NewRequest(http.MethodDelete, url, nil)
	if err != nil {
		return fmt.Errorf("failed to create deregister request: %v", err)
	}

	resp, err := client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to deregister from NRF: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusOK || resp.StatusCode == http.StatusNoContent {
		c.registered = false
		log.Println("Successfully deregistered from NRF")
		return nil
	}

	return fmt.Errorf("NRF deregistration failed with status %d", resp.StatusCode)
}

// heartbeatLoop sends periodic heartbeats to NRF
func (c *NRFClient) heartbeatLoop() {
	ticker := time.NewTicker(time.Duration(c.heartbeatTimer) * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-c.stopHeartbeat:
			return
		case <-ticker.C:
			c.sendHeartbeat()
		}
	}
}

// sendHeartbeat sends a heartbeat to NRF
func (c *NRFClient) sendHeartbeat() {
	url := fmt.Sprintf("%s/nnrf-nfm/v1/nf-instances/%s", c.nrfEndpoint, c.nfInstanceID)

	// PATCH with heartbeat update
	patchData := []map[string]interface{}{
		{
			"op":    "replace",
			"path":  "/nfStatus",
			"value": "REGISTERED",
		},
	}

	patchJSON, err := json.Marshal(patchData)
	if err != nil {
		log.Printf("Failed to marshal heartbeat patch: %v", err)
		return
	}

	client := &http.Client{Timeout: 10 * time.Second}
	req, err := http.NewRequest(http.MethodPatch, url, bytes.NewBuffer(patchJSON))
	if err != nil {
		log.Printf("Failed to create heartbeat request: %v", err)
		return
	}
	req.Header.Set("Content-Type", "application/json-patch+json")

	resp, err := client.Do(req)
	if err != nil {
		log.Printf("NRF heartbeat failed: %v", err)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusOK {
		log.Println("NRF heartbeat successful")
	} else if resp.StatusCode == http.StatusNotFound {
		log.Println("NF not found in NRF, re-registering...")
		c.registered = false
		c.Register()
	} else {
		log.Printf("NRF heartbeat failed with status %d", resp.StatusCode)
	}
}

// IsRegistered returns the registration status
func (c *NRFClient) IsRegistered() bool {
	return c.registered
}

// Global NRF client instance
var nrfClient *NRFClient

// InitNRFRegistration initializes and performs NRF registration
func InitNRFRegistration() {
	if config.Nrf.Endpoint == "" {
		log.Println("NRF endpoint not configured, skipping NRF registration")
		return
	}

	nrfClient = NewNRFClient(
		config.Nrf.Endpoint,
		config.Nrf.NFInstanceID,
		config.Nrf.IPv4Address,
		config.Nrf.SBIPort,
		config.Nrf.HeartbeatTimer,
		config.Nrf.AutoRegister,
	)

	if err := nrfClient.Register(); err != nil {
		log.Printf("Failed to register with NRF: %v", err)
	}
}

// NFInstancesResponse represents the response from NRF discovery
type NFInstancesResponse struct {
	NFInstances []NFProfile `json:"nfInstances"`
}

// DiscoverNFInstances queries NRF to discover NF instances of a given type
func DiscoverNFInstances(nrfEndpoint string, nfType string, serviceName string) ([]NFProfile, error) {
	if nrfEndpoint == "" {
		return nil, fmt.Errorf("NRF endpoint not configured")
	}

	// Build discovery URL with query parameters
	// GET /nnrf-disc/v1/nf-instances?target-nf-type=NWDAF&service-names=ndccf-datamanagement
	url := fmt.Sprintf("%s/nnrf-disc/v1/nf-instances?target-nf-type=%s", nrfEndpoint, nfType)
	if serviceName != "" {
		url = fmt.Sprintf("%s&service-names=%s", url, serviceName)
	}

	log.Printf("Discovering NF instances from NRF: %s", url)

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		return nil, fmt.Errorf("failed to query NRF: %v", err)
	}
	defer resp.Body.Close()

	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %v", err)
	}

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("NRF discovery failed with status %d: %s", resp.StatusCode, string(body))
	}

	var response NFInstancesResponse
	if err := json.Unmarshal(body, &response); err != nil {
		return nil, fmt.Errorf("failed to unmarshal NRF response: %v", err)
	}

	log.Printf("Discovered %d NF instances", len(response.NFInstances))
	return response.NFInstances, nil
}

// DiscoverDCCF discovers DCCF service endpoint via NRF
// It looks for NWDAF instances that provide ndccf-datamanagement service
func DiscoverDCCF(nrfEndpoint string, ownInstanceID string) (string, error) {
	if nrfEndpoint == "" {
		return "", fmt.Errorf("NRF endpoint not configured")
	}

	// Discover NWDAF instances with ndccf-datamanagement service
	instances, err := DiscoverNFInstances(nrfEndpoint, "NWDAF", "ndccf-datamanagement")
	if err != nil {
		return "", fmt.Errorf("failed to discover DCCF: %v", err)
	}

	// Find a DCCF instance (not ourselves)
	for _, instance := range instances {
		// Skip our own instance
		if instance.NFInstanceID == ownInstanceID {
			continue
		}

		// Look for ndccf-datamanagement service
		for _, service := range instance.NFServices {
			if service.ServiceName == "ndccf-datamanagement" && service.NFServiceStatus == "REGISTERED" {
				// Build endpoint URL from service info
				if len(service.IPEndPoints) > 0 {
					ep := service.IPEndPoints[0]
					endpoint := fmt.Sprintf("%s://%s:%d", service.Scheme, ep.IPv4Address, ep.Port)
					log.Printf("Discovered DCCF at %s (instance: %s)", endpoint, instance.NFInstanceID)
					return endpoint, nil
				}
				// Fallback to NFProfile IPv4 addresses
				if len(instance.IPv4Addresses) > 0 {
					endpoint := fmt.Sprintf("http://%s:8081", instance.IPv4Addresses[0])
					log.Printf("Discovered DCCF at %s (instance: %s)", endpoint, instance.NFInstanceID)
					return endpoint, nil
				}
			}
		}
	}

	return "", fmt.Errorf("no DCCF instance found in NRF")
}

// GetNRFEndpoint returns the configured NRF endpoint
func GetNRFEndpoint() string {
	return config.Nrf.Endpoint
}

// GetOwnInstanceID returns the own NF instance ID
func GetOwnInstanceID() string {
	return config.Nrf.NFInstanceID
}
