package attack

import (
	"encoding/json"
	"net"
	"testing"
)

func TestGeneratePayloadIsValidJSONWithMetadata(t *testing.T) {
	cfg := Config{
		Scenario:     ScenarioMQTTPublishFlood,
		Level:        LevelSmoke,
		Target:       "127.0.0.1",
		PayloadBytes: 256,
	}
	payload := GeneratePayload(cfg, "12.1.0.10", 7)
	if len(payload) != 256 {
		t.Fatalf("payload size = %d, want 256", len(payload))
	}
	var decoded map[string]any
	if err := json.Unmarshal(payload, &decoded); err != nil {
		t.Fatalf("payload is not valid JSON: %v", err)
	}
	if decoded["source_ip"] != "12.1.0.10" {
		t.Fatalf("source_ip = %v", decoded["source_ip"])
	}
}

func TestRawPacketBuilders(t *testing.T) {
	src := net.ParseIP("12.1.0.10")
	dst := net.ParseIP("192.168.49.1")
	syn := BuildIPv4TCPSYN(src, dst, 12345, 80, 99)
	if len(syn) != 40 {
		t.Fatalf("tcp syn length = %d, want 40", len(syn))
	}
	if syn[9] != 6 || syn[33] != 0x02 {
		t.Fatalf("unexpected TCP SYN packet fields")
	}
	icmp := BuildIPv4ICMPEcho(src, dst, 1, 2, []byte("abc"))
	if len(icmp) != 31 {
		t.Fatalf("icmp length = %d, want 31", len(icmp))
	}
	if icmp[9] != 1 || icmp[20] != 8 {
		t.Fatalf("unexpected ICMP packet fields")
	}
}

func TestRandomIPInCIDR(t *testing.T) {
	_, network, _ := net.ParseCIDR("12.1.0.0/16")
	for range 20 {
		ip := RandomIPInCIDR("12.1.0.0/16")
		if !network.Contains(ip) {
			t.Fatalf("random IP %s is outside CIDR", ip)
		}
	}
}
