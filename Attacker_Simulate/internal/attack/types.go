package attack

import "time"

const (
	ScenarioMQTTPublishFlood        = "mqtt-publish-flood"
	ScenarioMQTTSlowITe             = "mqtt-slowite"
	ScenarioCoAPPutFlood            = "coap-put-flood"
	ScenarioICMPFlood               = "icmp-flood"
	ScenarioLANDPingFlood           = "land-ping-flood"
	ScenarioTCPSYNFlood             = "tcp-syn-flood"
	ScenarioRandomSourceTCPSYNFlood = "random-source-tcp-syn-flood"
	ScenarioPortScan                = "port-scan"
	ScenarioShortPortScan           = "short-port-scan"
	ScenarioSQLMapLike              = "sqlmap-like"
	LevelSmoke                      = "smoke"
	LevelTraining                   = "training"
	LevelEvaluation                 = "evaluation"
	ProtocolMQTT                    = "mqtt"
	ProtocolCoAP                    = "coap"
	ProtocolICMP                    = "icmp"
	ProtocolTCP                     = "tcp"
	ProtocolHTTP                    = "http"
	DefaultMaxDuration              = 60 * time.Second
	DefaultMaxRatePerSecond         = 500
	DefaultMaxSlowConnections       = 100
	DefaultMaxPortScanPorts         = 10000
)

type Event struct {
	Timestamp   time.Time      `json:"timestamp"`
	Role        string         `json:"role"`
	Event       string         `json:"event"`
	Scenario    string         `json:"scenario,omitempty"`
	Level       string         `json:"level,omitempty"`
	Protocol    string         `json:"protocol,omitempty"`
	SourceIP    string         `json:"source_ip,omitempty"`
	Target      string         `json:"target,omitempty"`
	TargetIP    string         `json:"target_ip,omitempty"`
	Port        int            `json:"port,omitempty"`
	PayloadSize int            `json:"payload_size,omitempty"`
	Count       int            `json:"count,omitempty"`
	Status      string         `json:"status,omitempty"`
	Error       string         `json:"error,omitempty"`
	Fields      map[string]any `json:"fields,omitempty"`
}

type Config struct {
	Scenario        string
	Level           string
	Target          string
	TargetIP        string
	SourceIPs       []string
	SourceCIDR      string
	Duration        time.Duration
	RatePerSecond   int
	MQTTPort        int
	CoAPPort        int
	HTTPPort        int
	TCPPort         int
	Ports           []int
	PayloadBytes    int
	SlowConnections int
	Out             string
}
