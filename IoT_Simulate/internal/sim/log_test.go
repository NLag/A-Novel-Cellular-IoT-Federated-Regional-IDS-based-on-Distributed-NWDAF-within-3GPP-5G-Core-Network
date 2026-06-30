package sim

import (
	"bufio"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestEventLoggerWritesJSONL(t *testing.T) {
	path := filepath.Join(t.TempDir(), "events.jsonl")
	logger, err := NewEventLogger(path)
	if err != nil {
		t.Fatalf("NewEventLogger returned error: %v", err)
	}
	if err := logger.Write(Event{
		Role:        "client",
		Event:       "message_sent",
		Protocol:    ProtocolHTTP,
		DeviceID:    "device-1",
		SourceIP:    "127.0.0.1",
		PayloadSize: 42,
		Status:      "ok",
	}); err != nil {
		t.Fatalf("Write returned error: %v", err)
	}
	if err := logger.Close(); err != nil {
		t.Fatalf("Close returned error: %v", err)
	}

	f, err := os.Open(path)
	if err != nil {
		t.Fatalf("open log: %v", err)
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	if !scanner.Scan() {
		t.Fatalf("expected one JSONL line")
	}
	var event Event
	if err := json.Unmarshal(scanner.Bytes(), &event); err != nil {
		t.Fatalf("unmarshal event: %v", err)
	}
	if event.Timestamp.IsZero() {
		t.Fatalf("timestamp was not set")
	}
	if event.DeviceID != "device-1" || event.PayloadSize != 42 || event.Status != "ok" {
		t.Fatalf("unexpected event: %#v", event)
	}
	if scanner.Scan() {
		t.Fatalf("expected one line only")
	}
}
