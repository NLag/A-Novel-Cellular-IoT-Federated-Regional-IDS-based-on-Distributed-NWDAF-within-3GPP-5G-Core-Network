package attack

import (
	"net"
	"testing"
	"time"
)

func TestIsLabIP(t *testing.T) {
	tests := []struct {
		ip   string
		want bool
	}{
		{"10.244.2.10", true},
		{"12.1.4.10", true},
		{"192.168.49.1", true},
		{"172.20.0.1", true},
		{"127.0.0.1", true},
		{"8.8.8.8", false},
	}
	for _, tt := range tests {
		if got := IsLabIP(net.ParseIP(tt.ip)); got != tt.want {
			t.Fatalf("IsLabIP(%s) = %v, want %v", tt.ip, got, tt.want)
		}
	}
}

func TestParsePorts(t *testing.T) {
	ports, err := ParsePorts("22,80,100-102,80", nil)
	if err != nil {
		t.Fatalf("ParsePorts returned error: %v", err)
	}
	want := []int{22, 80, 100, 101, 102}
	if len(ports) != len(want) {
		t.Fatalf("ports = %#v, want %#v", ports, want)
	}
	for i := range want {
		if ports[i] != want[i] {
			t.Fatalf("ports[%d] = %d, want %d", i, ports[i], want[i])
		}
	}
}

func TestSafetyCaps(t *testing.T) {
	duration, rate, connections := EnforceSafety(10*time.Minute, 10_000, 500)
	if duration != DefaultMaxDuration {
		t.Fatalf("duration = %s, want %s", duration, DefaultMaxDuration)
	}
	if rate != DefaultMaxRatePerSecond {
		t.Fatalf("rate = %d, want %d", rate, DefaultMaxRatePerSecond)
	}
	if connections != DefaultMaxSlowConnections {
		t.Fatalf("connections = %d, want %d", connections, DefaultMaxSlowConnections)
	}
}
