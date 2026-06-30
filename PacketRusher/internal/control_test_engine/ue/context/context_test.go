package context

import "testing"

func TestPduSessionTunnelCleanupRunsOnce(t *testing.T) {
	pduSession := &UEPDUSession{}
	calls := 0

	pduSession.SetTunnelCleanup(func() {
		calls++
	})

	if !pduSession.CleanupTunnel() {
		t.Fatal("CleanupTunnel should report true when a cleanup function is registered")
	}
	if pduSession.CleanupTunnel() {
		t.Fatal("CleanupTunnel should report false after cleanup already ran")
	}
	if calls != 1 {
		t.Fatalf("cleanup should run once, ran %d times", calls)
	}
}
