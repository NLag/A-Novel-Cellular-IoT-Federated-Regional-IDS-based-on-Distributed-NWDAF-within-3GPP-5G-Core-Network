package sim

import (
	"encoding/json"
	"net"
	"testing"
	"time"
)

func TestGenerateProfilesBounds(t *testing.T) {
	profiles, err := GenerateProfiles(ProfileOptions{
		ServerHost:      "127.0.0.1",
		HTTPPort:        8088,
		MQTTPort:        1883,
		CoAPPort:        5683,
		MinDevices:      10,
		MaxDevices:      20,
		MessageCount:    3,
		Duration:        3 * time.Hour,
		PayloadMinBytes: 80,
		PayloadMaxBytes: 120,
		Protocols:       []string{ProtocolHTTP, ProtocolMQTT, ProtocolCoAP},
		SourceIPs:       []string{"12.1.0.1", "12.1.0.2"},
	})
	if err != nil {
		t.Fatalf("GenerateProfiles returned error: %v", err)
	}
	if len(profiles) < 10 || len(profiles) > 20 {
		t.Fatalf("profile count = %d, want 10..20", len(profiles))
	}
	for _, profile := range profiles {
		if profile.ID == "" {
			t.Fatalf("profile ID is empty")
		}
		if net.ParseIP(profile.SourceIP) == nil {
			t.Fatalf("invalid source IP %q", profile.SourceIP)
		}
		if profile.MessageCount != 3 {
			t.Fatalf("message count = %d, want 3", profile.MessageCount)
		}
		if profile.DurationSeconds != 10800 {
			t.Fatalf("duration seconds = %d, want 10800", profile.DurationSeconds)
		}
		if profile.PayloadMinBytes != 80 || profile.PayloadMaxBytes != 120 {
			t.Fatalf("payload bounds = %d..%d, want 80..120", profile.PayloadMinBytes, profile.PayloadMaxBytes)
		}
	}
}

func TestGenerateProfilesAllowsDurationOnlyRun(t *testing.T) {
	profiles, err := GenerateProfiles(ProfileOptions{
		ServerHost:      "127.0.0.1",
		HTTPPort:        8088,
		MQTTPort:        1883,
		CoAPPort:        5683,
		MinDevices:      1,
		MaxDevices:      1,
		MessageCount:    0,
		Duration:        3 * time.Hour,
		PayloadMinBytes: 80,
		PayloadMaxBytes: 120,
		Protocols:       []string{ProtocolHTTP},
		SourceIPs:       []string{"12.1.0.1"},
	})
	if err != nil {
		t.Fatalf("GenerateProfiles returned error: %v", err)
	}
	if profiles[0].MessageCount != 0 {
		t.Fatalf("message count = %d, want 0", profiles[0].MessageCount)
	}
	if profiles[0].DurationSeconds != 10800 {
		t.Fatalf("duration seconds = %d, want 10800", profiles[0].DurationSeconds)
	}
}

func TestGeneratePayloadSize(t *testing.T) {
	profile := DeviceProfile{
		ID:              "device-1",
		DeviceType:      "temperature-sensor",
		Protocol:        ProtocolHTTP,
		SourceIP:        "12.1.0.1",
		PayloadMinBytes: 256,
		PayloadMaxBytes: 256,
		Seed:            42,
	}
	payload := GeneratePayload(profile, 1)
	if len(payload) != 256 {
		t.Fatalf("payload size = %d, want 256", len(payload))
	}
	var decoded map[string]any
	if err := json.Unmarshal(payload, &decoded); err != nil {
		t.Fatalf("payload is not valid JSON: %v: %s", err, payload)
	}
	if decoded["source_ip"] != profile.SourceIP {
		t.Fatalf("source_ip = %v, want %s", decoded["source_ip"], profile.SourceIP)
	}
}

func TestGeneratePayloadKeepsMetadataWhenRequestedSizeIsSmall(t *testing.T) {
	profile := DeviceProfile{
		ID:              "device-1",
		DeviceType:      "temperature-sensor",
		Protocol:        ProtocolMQTT,
		SourceIP:        "12.1.0.1",
		PayloadMinBytes: 16,
		PayloadMaxBytes: 16,
		Seed:            42,
	}
	payload := GeneratePayload(profile, 1)
	var decoded map[string]any
	if err := json.Unmarshal(payload, &decoded); err != nil {
		t.Fatalf("payload is not valid JSON: %v: %s", err, payload)
	}
	if decoded["device_id"] != profile.ID {
		t.Fatalf("device_id = %v, want %s", decoded["device_id"], profile.ID)
	}
	if decoded["source_ip"] != profile.SourceIP {
		t.Fatalf("source_ip = %v, want %s", decoded["source_ip"], profile.SourceIP)
	}
}

func TestNormalizeProtocols(t *testing.T) {
	got := normalizeProtocols([]string{"HTTP", "mqtt", "unknown", "coap", "http"})
	want := []string{ProtocolHTTP, ProtocolMQTT, ProtocolCoAP}
	if len(got) != len(want) {
		t.Fatalf("protocol count = %d, want %d: %#v", len(got), len(want), got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("protocol[%d] = %q, want %q", i, got[i], want[i])
		}
	}
}
