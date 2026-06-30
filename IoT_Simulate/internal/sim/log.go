package sim

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"sync"
	"time"
)

type EventLogger struct {
	mu sync.Mutex
	w  io.WriteCloser
}

func NewEventLogger(path string) (*EventLogger, error) {
	if path == "" || path == "-" {
		return &EventLogger{w: nopWriteCloser{Writer: os.Stdout}}, nil
	}

	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return nil, fmt.Errorf("open event log: %w", err)
	}
	return &EventLogger{w: f}, nil
}

func (l *EventLogger) Close() error {
	if l == nil || l.w == nil {
		return nil
	}
	return l.w.Close()
}

func (l *EventLogger) Write(event Event) error {
	if event.Timestamp.IsZero() {
		event.Timestamp = time.Now().UTC()
	}

	b, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("marshal event: %w", err)
	}
	b = append(b, '\n')

	l.mu.Lock()
	defer l.mu.Unlock()
	_, err = l.w.Write(b)
	return err
}

type nopWriteCloser struct {
	io.Writer
}

func (n nopWriteCloser) Close() error {
	return nil
}
