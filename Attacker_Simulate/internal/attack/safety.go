package attack

import (
	"fmt"
	"net"
	"sort"
	"strconv"
	"strings"
	"time"
)

func ResolveLabTarget(target string) (string, error) {
	if target == "" {
		return "", fmt.Errorf("target is required")
	}
	ips, err := net.LookupIP(target)
	if err != nil {
		return "", fmt.Errorf("resolve target %q: %w", target, err)
	}
	for _, ip := range ips {
		if ip4 := ip.To4(); ip4 != nil && IsLabIP(ip4) {
			return ip4.String(), nil
		}
	}
	return "", fmt.Errorf("target %q resolved to no lab/private IPv4 address: %v", target, ips)
}

func IsLabIP(ip net.IP) bool {
	ip = ip.To4()
	if ip == nil {
		return false
	}
	privateBlocks := []string{
		"10.0.0.0/8",
		"12.1.0.0/16",
		"127.0.0.0/8",
		"169.254.0.0/16",
		"172.16.0.0/12",
		"192.168.0.0/16",
	}
	for _, block := range privateBlocks {
		_, network, _ := net.ParseCIDR(block)
		if network.Contains(ip) {
			return true
		}
	}
	return false
}

func ValidateScenario(scenario string) error {
	switch scenario {
	case ScenarioMQTTPublishFlood, ScenarioMQTTSlowITe, ScenarioCoAPPutFlood,
		ScenarioICMPFlood, ScenarioLANDPingFlood, ScenarioTCPSYNFlood,
		ScenarioRandomSourceTCPSYNFlood, ScenarioPortScan, ScenarioShortPortScan,
		ScenarioSQLMapLike:
		return nil
	default:
		return fmt.Errorf("unsupported attack scenario %q", scenario)
	}
}

func NormalizeLevel(level string) (string, error) {
	switch strings.ToLower(strings.TrimSpace(level)) {
	case "", LevelSmoke:
		return LevelSmoke, nil
	case LevelTraining:
		return LevelTraining, nil
	case LevelEvaluation:
		return LevelEvaluation, nil
	default:
		return "", fmt.Errorf("unsupported level %q", level)
	}
}

func ApplyLevelDefaults(level string, duration time.Duration, rate int, connections int) (time.Duration, int, int) {
	if duration <= 0 {
		switch level {
		case LevelTraining:
			duration = 60 * time.Second
		case LevelEvaluation:
			duration = 30 * time.Second
		default:
			duration = 5 * time.Second
		}
	}
	if rate <= 0 {
		switch level {
		case LevelTraining:
			rate = 200
		case LevelEvaluation:
			rate = 100
		default:
			rate = 20
		}
	}
	if connections <= 0 {
		switch level {
		case LevelTraining:
			connections = 40
		case LevelEvaluation:
			connections = 25
		default:
			connections = 5
		}
	}
	return duration, rate, connections
}

func EnforceSafety(duration time.Duration, rate int, connections int) (time.Duration, int, int) {
	if duration > DefaultMaxDuration {
		duration = DefaultMaxDuration
	}
	if rate > DefaultMaxRatePerSecond {
		rate = DefaultMaxRatePerSecond
	}
	if connections > DefaultMaxSlowConnections {
		connections = DefaultMaxSlowConnections
	}
	if rate < 1 {
		rate = 1
	}
	if connections < 1 {
		connections = 1
	}
	return duration, rate, connections
}

func ParsePorts(spec string, fallback []int) ([]int, error) {
	spec = strings.TrimSpace(spec)
	if spec == "" {
		return fallback, nil
	}
	seen := map[int]bool{}
	var ports []int
	for _, part := range strings.Split(spec, ",") {
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		if strings.Contains(part, "-") {
			bounds := strings.SplitN(part, "-", 2)
			if len(bounds) != 2 {
				return nil, fmt.Errorf("invalid port range %q", part)
			}
			start, err := parsePort(bounds[0])
			if err != nil {
				return nil, err
			}
			end, err := parsePort(bounds[1])
			if err != nil {
				return nil, err
			}
			if end < start {
				return nil, fmt.Errorf("invalid descending port range %q", part)
			}
			for port := start; port <= end; port++ {
				if !seen[port] {
					ports = append(ports, port)
					seen[port] = true
				}
				if len(ports) > DefaultMaxPortScanPorts {
					return nil, fmt.Errorf("port list exceeds safety cap %d", DefaultMaxPortScanPorts)
				}
			}
			continue
		}
		port, err := parsePort(part)
		if err != nil {
			return nil, err
		}
		if !seen[port] {
			ports = append(ports, port)
			seen[port] = true
		}
	}
	sort.Ints(ports)
	if len(ports) == 0 {
		return nil, fmt.Errorf("empty port list")
	}
	return ports, nil
}

func parsePort(value string) (int, error) {
	port, err := strconv.Atoi(strings.TrimSpace(value))
	if err != nil || port < 1 || port > 65535 {
		return 0, fmt.Errorf("invalid port %q", value)
	}
	return port, nil
}

func CommonShortPorts() []int {
	return []int{22, 53, 80, 123, 443, 1883, 5683, 8080, 8088, 8443}
}
