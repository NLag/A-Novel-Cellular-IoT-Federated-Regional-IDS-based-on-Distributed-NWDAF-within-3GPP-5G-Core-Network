package sim

import "time"

const (
	ProtocolHTTP = "http"
	ProtocolMQTT = "mqtt"
	ProtocolCoAP = "coap"
)

type Event struct {
	Timestamp   time.Time      `json:"timestamp"`
	Role        string         `json:"role"`
	Event       string         `json:"event"`
	Protocol    string         `json:"protocol,omitempty"`
	DeviceID    string         `json:"device_id,omitempty"`
	DeviceType  string         `json:"device_type,omitempty"`
	SourceIP    string         `json:"source_ip,omitempty"`
	RemoteAddr  string         `json:"remote_addr,omitempty"`
	Topic       string         `json:"topic,omitempty"`
	Path        string         `json:"path,omitempty"`
	PayloadSize int            `json:"payload_size,omitempty"`
	Status      string         `json:"status,omitempty"`
	Error       string         `json:"error,omitempty"`
	Fields      map[string]any `json:"fields,omitempty"`
}

type DeviceProfile struct {
	ID              string `json:"id"`
	DeviceType      string `json:"device_type"`
	Protocol        string `json:"protocol"`
	SourceIP        string `json:"source_ip"`
	ServerHost      string `json:"server_host"`
	HTTPPort        int    `json:"http_port"`
	MQTTPort        int    `json:"mqtt_port"`
	CoAPPort        int    `json:"coap_port"`
	StartupDelayMS  int    `json:"startup_delay_ms"`
	IntervalMS      int    `json:"interval_ms"`
	JitterMS        int    `json:"jitter_ms"`
	PayloadMinBytes int    `json:"payload_min_bytes"`
	PayloadMaxBytes int    `json:"payload_max_bytes"`
	MessageCount    int    `json:"message_count"`
	DurationSeconds int    `json:"duration_seconds"`
	Topic           string `json:"topic"`
	Path            string `json:"path"`
	Seed            int64  `json:"seed"`
}

func (p DeviceProfile) StartupDelay() time.Duration {
	return time.Duration(p.StartupDelayMS) * time.Millisecond
}

func (p DeviceProfile) Interval() time.Duration {
	return time.Duration(p.IntervalMS) * time.Millisecond
}

func (p DeviceProfile) Jitter() time.Duration {
	return time.Duration(p.JitterMS) * time.Millisecond
}

func (p DeviceProfile) Duration() time.Duration {
	return time.Duration(p.DurationSeconds) * time.Second
}
