package sim

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	mrand "math/rand"
	"net"
	"slices"
	"strings"
	"time"
)

type ProfileOptions struct {
	ServerHost      string
	HTTPPort        int
	MQTTPort        int
	CoAPPort        int
	MinDevices      int
	MaxDevices      int
	MessageCount    int
	Duration        time.Duration
	PayloadMinBytes int
	PayloadMaxBytes int
	Protocols       []string
	SourceIPs       []string
}

var deviceTypes = []string{
	"temperature-sensor",
	"humidity-sensor",
	"smart-meter",
	"vibration-sensor",
	"air-quality-sensor",
	"asset-tracker",
	"pressure-sensor",
	"camera-metadata-node",
}

func GenerateProfiles(opts ProfileOptions) ([]DeviceProfile, error) {
	if opts.MinDevices <= 0 || opts.MaxDevices < opts.MinDevices {
		return nil, fmt.Errorf("invalid device range %d-%d", opts.MinDevices, opts.MaxDevices)
	}
	if len(opts.SourceIPs) == 0 {
		return nil, fmt.Errorf("no source IPs available")
	}
	protocols := normalizeProtocols(opts.Protocols)
	if len(protocols) == 0 {
		return nil, fmt.Errorf("no supported protocols requested")
	}
	if opts.PayloadMinBytes <= 0 {
		opts.PayloadMinBytes = 64
	}
	if opts.PayloadMaxBytes < opts.PayloadMinBytes {
		opts.PayloadMaxBytes = opts.PayloadMinBytes
	}
	if opts.MessageCount < 0 {
		opts.MessageCount = 0
	}
	durationSeconds := int(opts.Duration.Seconds())
	if durationSeconds < 0 {
		durationSeconds = 0
	}

	r := mrand.New(mrand.NewSource(time.Now().UnixNano()))
	count := opts.MinDevices
	if opts.MaxDevices > opts.MinDevices {
		count += r.Intn(opts.MaxDevices - opts.MinDevices + 1)
	}

	profiles := make([]DeviceProfile, 0, count)
	for i := range count {
		protocol := protocols[r.Intn(len(protocols))]
		deviceType := deviceTypes[r.Intn(len(deviceTypes))]
		sourceIP := opts.SourceIPs[i%len(opts.SourceIPs)]
		id := fmt.Sprintf("%s-%s-%02d", strings.ReplaceAll(deviceType, "-", ""), randomSuffix(4), i)
		topic := fmt.Sprintf("iot/%s/%s", deviceType, id)
		path := fmt.Sprintf("/ingest/%s/%s", deviceType, id)

		profiles = append(profiles, DeviceProfile{
			ID:              id,
			DeviceType:      deviceType,
			Protocol:        protocol,
			SourceIP:        sourceIP,
			ServerHost:      opts.ServerHost,
			HTTPPort:        opts.HTTPPort,
			MQTTPort:        opts.MQTTPort,
			CoAPPort:        opts.CoAPPort,
			StartupDelayMS:  r.Intn(10_000),
			IntervalMS:      500 + r.Intn(4_500),
			JitterMS:        r.Intn(750),
			PayloadMinBytes: opts.PayloadMinBytes,
			PayloadMaxBytes: opts.PayloadMaxBytes,
			MessageCount:    opts.MessageCount,
			DurationSeconds: durationSeconds,
			Topic:           topic,
			Path:            path,
			Seed:            r.Int63(),
		})
	}

	return profiles, nil
}

func normalizeProtocols(protocols []string) []string {
	if len(protocols) == 0 {
		return []string{ProtocolHTTP, ProtocolMQTT, ProtocolCoAP}
	}

	seen := map[string]bool{}
	var out []string
	for _, protocol := range protocols {
		switch strings.ToLower(strings.TrimSpace(protocol)) {
		case ProtocolHTTP:
			if !seen[ProtocolHTTP] {
				out = append(out, ProtocolHTTP)
				seen[ProtocolHTTP] = true
			}
		case ProtocolMQTT:
			if !seen[ProtocolMQTT] {
				out = append(out, ProtocolMQTT)
				seen[ProtocolMQTT] = true
			}
		case ProtocolCoAP:
			if !seen[ProtocolCoAP] {
				out = append(out, ProtocolCoAP)
				seen[ProtocolCoAP] = true
			}
		}
	}
	return out
}

func GeneratePayload(profile DeviceProfile, seq int) []byte {
	r := mrand.New(mrand.NewSource(profile.Seed + int64(seq)))
	size := profile.PayloadMinBytes
	if profile.PayloadMaxBytes > profile.PayloadMinBytes {
		size += r.Intn(profile.PayloadMaxBytes - profile.PayloadMinBytes + 1)
	}

	metric := 10 + r.Float64()*90
	payload := generatedPayload{
		DeviceID:   profile.ID,
		DeviceType: profile.DeviceType,
		Protocol:   profile.Protocol,
		Sequence:   seq,
		Metric:     metric,
		SourceIP:   profile.SourceIP,
	}
	body := marshalPayload(payload)
	if len(body) >= size {
		return body
	}

	paddingLen := size - len(body)
	for range 4 {
		payload.Padding = strings.Repeat("x", paddingLen)
		body = marshalPayload(payload)
		if len(body) == size {
			return body
		}
		if len(body) > size {
			paddingLen -= len(body) - size
		} else {
			paddingLen += size - len(body)
		}
		if paddingLen < 0 {
			paddingLen = 0
		}
	}
	return body
}

type generatedPayload struct {
	DeviceID   string  `json:"device_id"`
	DeviceType string  `json:"device_type"`
	Protocol   string  `json:"protocol"`
	Sequence   int     `json:"sequence"`
	Metric     float64 `json:"metric"`
	SourceIP   string  `json:"source_ip"`
	Padding    string  `json:"padding,omitempty"`
}

func marshalPayload(payload generatedPayload) []byte {
	body, err := json.Marshal(payload)
	if err != nil {
		return []byte("{}")
	}
	return body
}

func SleepWithJitter(base, jitter time.Duration, seq int, seed int64) {
	time.Sleep(JitterDelay(base, jitter, seq, seed))
}

func JitterDelay(base, jitter time.Duration, seq int, seed int64) time.Duration {
	if base <= 0 && jitter <= 0 {
		return 0
	}
	delay := base
	if jitter > 0 {
		r := mrand.New(mrand.NewSource(seed + int64(seq)*7919))
		offset := time.Duration(r.Int63n(int64(jitter)*2+1)) - jitter
		delay += offset
		if delay < 0 {
			delay = 0
		}
	}
	return delay
}

func DiscoverSourceIPs(sourceCIDR string) ([]string, error) {
	_, network, err := net.ParseCIDR(sourceCIDR)
	if err != nil {
		return nil, fmt.Errorf("parse source CIDR: %w", err)
	}

	var ips []string
	ifaces, err := net.Interfaces()
	if err != nil {
		return nil, fmt.Errorf("list interfaces: %w", err)
	}
	for _, iface := range ifaces {
		if iface.Flags&net.FlagUp == 0 {
			continue
		}
		addrs, err := iface.Addrs()
		if err != nil {
			continue
		}
		for _, addr := range addrs {
			ip := addrIP(addr)
			if ip == nil || ip.To4() == nil {
				continue
			}
			if network.Contains(ip) {
				value := ip.String()
				if !slices.Contains(ips, value) {
					ips = append(ips, value)
				}
			}
		}
	}
	slices.Sort(ips)
	return ips, nil
}

func addrIP(addr net.Addr) net.IP {
	switch v := addr.(type) {
	case *net.IPNet:
		return v.IP
	case *net.IPAddr:
		return v.IP
	default:
		return nil
	}
}

func randomSuffix(bytesLen int) string {
	b := make([]byte, bytesLen)
	if _, err := rand.Read(b); err != nil {
		return fmt.Sprintf("%08x", time.Now().UnixNano())
	}
	return hex.EncodeToString(b)
}
