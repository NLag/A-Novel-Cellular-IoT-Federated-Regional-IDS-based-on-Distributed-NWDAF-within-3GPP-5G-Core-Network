package service

import (
	"net/netip"
	"testing"
)

func TestSharedTunnelNameIsStableAndFitsLinuxIFNAMSIZ(t *testing.T) {
	gnbIP := netip.MustParseAddr("10.244.0.183")

	first := sharedTunnelName(gnbIP)
	second := sharedTunnelName(gnbIP)

	if first != second {
		t.Fatalf("sharedTunnelName should be stable, got %q then %q", first, second)
	}
	if len(first) > 15 {
		t.Fatalf("sharedTunnelName must fit Linux IFNAMSIZ, got %q with length %d", first, len(first))
	}
}

func TestAllocateGtpRuleIDsAreUnique(t *testing.T) {
	gtpRuleIDGenerator.Store(0)

	first := allocateGtpRuleIDs()
	second := allocateGtpRuleIDs()

	seen := map[uint32]bool{}
	for _, id := range []uint32{
		first.farUplink,
		first.farDownlink,
		first.pdrDownlink,
		first.pdrUplink,
		first.qer,
		second.farUplink,
		second.farDownlink,
		second.pdrDownlink,
		second.pdrUplink,
		second.qer,
	} {
		if id == 0 {
			t.Fatal("allocated GTP rule IDs must not be zero")
		}
		if seen[id] {
			t.Fatalf("allocated duplicate GTP rule ID %d", id)
		}
		seen[id] = true
	}
}
