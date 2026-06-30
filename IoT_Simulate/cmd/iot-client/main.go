package main

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"flag"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"

	mqtt "github.com/eclipse/paho.mqtt.golang"
	"github.com/plgd-dev/go-coap/v3/message"
	"github.com/plgd-dev/go-coap/v3/message/codes"
	"github.com/plgd-dev/go-coap/v3/options"
	coapudp "github.com/plgd-dev/go-coap/v3/udp"

	"iot_simulate/internal/sim"
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
	var protocols stringList
	var sourceIPFile string
	var sourceCIDR string
	var serverHost string
	var out string
	var child bool
	var profileJSON string
	var minDevices int
	var maxDevices int
	var httpPort int
	var mqttPort int
	var coapPort int
	var payloadMin int
	var payloadMax int
	var messageCount int
	var runDuration time.Duration
	var waitSources time.Duration

	flag.Var(&explicitSourceIPs, "source-ip", "UE source IP to bind from; may be repeated or comma-separated")
	flag.Var(&protocols, "protocols", "Protocols to use: http,mqtt,coap")
	flag.StringVar(&sourceIPFile, "source-ip-file", "", "File containing UE source IPs, one per line")
	flag.StringVar(&sourceCIDR, "source-cidr", "12.1.0.0/16", "CIDR used for automatic UE source IP discovery")
	flag.StringVar(&serverHost, "server", "host.minikube.internal", "IoT server hostname or IP")
	flag.StringVar(&out, "out", "iot_client_events.jsonl", "JSONL client event output path, or '-' for stdout")
	flag.BoolVar(&child, "device-child", false, "Run one simulated device profile; used internally by parent process")
	flag.StringVar(&profileJSON, "profile-json", "", "Base64-encoded DeviceProfile JSON for --device-child")
	flag.IntVar(&minDevices, "min-devices", 10, "Minimum simulated IoT device processes")
	flag.IntVar(&maxDevices, "max-devices", 20, "Maximum simulated IoT device processes")
	flag.IntVar(&httpPort, "http-port", 8088, "HTTP server port")
	flag.IntVar(&mqttPort, "mqtt-port", 1883, "MQTT broker port")
	flag.IntVar(&coapPort, "coap-port", 5683, "CoAP server UDP port")
	flag.IntVar(&payloadMin, "payload-min-bytes", 64, "Minimum generated payload size")
	flag.IntVar(&payloadMax, "payload-max-bytes", 512, "Maximum generated payload size")
	flag.IntVar(&messageCount, "message-count", 0, "Messages to send per simulated device; 0 means run until --duration")
	flag.DurationVar(&runDuration, "duration", 3*time.Hour, "Traffic generation duration per simulated device; 0 disables the duration limit")
	flag.DurationVar(&waitSources, "wait-sources", 60*time.Second, "Time to wait for auto-discovered UE source IPs")
	flag.Parse()

	logger, err := sim.NewEventLogger(out)
	if err != nil {
		fatal(err)
	}
	defer logger.Close()

	if child {
		profile, err := decodeProfile(profileJSON)
		if err != nil {
			fatal(err)
		}
		if err := runDevice(context.Background(), logger, profile); err != nil {
			_ = logger.Write(sim.Event{
				Role:     "client",
				Event:    "device_failed",
				Protocol: profile.Protocol,
				DeviceID: profile.ID,
				SourceIP: profile.SourceIP,
				Error:    err.Error(),
			})
			os.Exit(1)
		}
		return
	}

	sourceIPs, err := resolveSourceIPs(explicitSourceIPs, sourceIPFile, sourceCIDR, waitSources)
	if err != nil {
		fatal(err)
	}

	profiles, err := sim.GenerateProfiles(sim.ProfileOptions{
		ServerHost:      serverHost,
		HTTPPort:        httpPort,
		MQTTPort:        mqttPort,
		CoAPPort:        coapPort,
		MinDevices:      minDevices,
		MaxDevices:      maxDevices,
		MessageCount:    messageCount,
		Duration:        runDuration,
		PayloadMinBytes: payloadMin,
		PayloadMaxBytes: payloadMax,
		Protocols:       protocols,
		SourceIPs:       sourceIPs,
	})
	if err != nil {
		fatal(err)
	}

	_ = logger.Write(sim.Event{
		Role:   "client",
		Event:  "client_started",
		Status: "ok",
		Fields: map[string]any{
			"device_count":  len(profiles),
			"duration":      runDuration.String(),
			"message_count": messageCount,
			"source_ips":    sourceIPs,
			"server":        serverHost,
		},
	})

	exe, err := os.Executable()
	if err != nil {
		fatal(err)
	}

	var children []*exec.Cmd
	for _, profile := range profiles {
		encoded, err := encodeProfile(profile)
		if err != nil {
			fatal(err)
		}
		cmd := exec.Command(exe, "--device-child", "--profile-json", encoded, "--out", out)
		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
		if err := cmd.Start(); err != nil {
			fatal(fmt.Errorf("start child for %s: %w", profile.ID, err))
		}
		children = append(children, cmd)
	}

	failed := 0
	for _, cmd := range children {
		if err := cmd.Wait(); err != nil {
			failed++
			_ = logger.Write(sim.Event{
				Role:  "client",
				Event: "child_failed",
				Error: err.Error(),
			})
		}
	}
	if failed > 0 {
		os.Exit(1)
	}

	_ = logger.Write(sim.Event{
		Role:   "client",
		Event:  "client_completed",
		Status: "ok",
		Fields: map[string]any{"device_count": len(profiles)},
	})
}

func runDevice(ctx context.Context, logger *sim.EventLogger, profile sim.DeviceProfile) error {
	if err := sleepContext(ctx, profile.StartupDelay()); err != nil {
		return nil
	}

	deviceCtx := ctx
	cancel := func() {}
	if duration := profile.Duration(); duration > 0 {
		deviceCtx, cancel = context.WithTimeout(ctx, duration)
	}
	defer cancel()

	_ = logger.Write(sim.Event{
		Role:       "client",
		Event:      "device_started",
		Protocol:   profile.Protocol,
		DeviceID:   profile.ID,
		DeviceType: profile.DeviceType,
		SourceIP:   profile.SourceIP,
		Status:     "ok",
		Fields: map[string]any{
			"duration_seconds": profile.DurationSeconds,
			"message_count":    profile.MessageCount,
		},
	})

	var err error
	switch profile.Protocol {
	case sim.ProtocolHTTP:
		err = runHTTPDevice(deviceCtx, logger, profile)
	case sim.ProtocolMQTT:
		err = runMQTTDevice(deviceCtx, logger, profile)
	case sim.ProtocolCoAP:
		err = runCoAPDevice(deviceCtx, logger, profile)
	default:
		err = fmt.Errorf("unsupported protocol %q", profile.Protocol)
	}

	status := "ok"
	errText := ""
	if err != nil {
		status = "error"
		errText = err.Error()
	}
	_ = logger.Write(sim.Event{
		Role:       "client",
		Event:      "device_completed",
		Protocol:   profile.Protocol,
		DeviceID:   profile.ID,
		DeviceType: profile.DeviceType,
		SourceIP:   profile.SourceIP,
		Status:     status,
		Error:      errText,
	})
	return err
}

func runHTTPDevice(ctx context.Context, logger *sim.EventLogger, profile sim.DeviceProfile) error {
	ip := net.ParseIP(profile.SourceIP)
	if ip == nil {
		return fmt.Errorf("invalid source IP %q", profile.SourceIP)
	}
	client := &http.Client{
		Timeout: 10 * time.Second,
		Transport: &http.Transport{
			DialContext: (&net.Dialer{
				Timeout:   5 * time.Second,
				LocalAddr: &net.TCPAddr{IP: ip},
			}).DialContext,
		},
	}
	url := "http://" + net.JoinHostPort(profile.ServerHost, strconv.Itoa(profile.HTTPPort)) + profile.Path
	for seq := 0; canSendMessage(ctx, profile, seq); seq++ {
		if !waitForMessageSlot(ctx, profile, seq) {
			break
		}
		payload := sim.GeneratePayload(profile, seq)
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(payload))
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return err
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("X-Device-ID", profile.ID)
		req.Header.Set("X-Device-Type", profile.DeviceType)
		resp, err := client.Do(req)
		status := "ok"
		errText := ""
		if err != nil {
			status = "error"
			errText = err.Error()
			if ctx.Err() != nil {
				return nil
			}
		} else {
			resp.Body.Close()
			if resp.StatusCode >= 400 {
				status = "error"
				errText = resp.Status
			}
		}
		_ = logger.Write(sim.Event{
			Role:        "client",
			Event:       "message_sent",
			Protocol:    sim.ProtocolHTTP,
			DeviceID:    profile.ID,
			DeviceType:  profile.DeviceType,
			SourceIP:    profile.SourceIP,
			Path:        profile.Path,
			PayloadSize: len(payload),
			Status:      status,
			Error:       errText,
		})
		if errText != "" {
			return fmt.Errorf("http send failed: %s", errText)
		}
	}
	return nil
}

func runMQTTDevice(ctx context.Context, logger *sim.EventLogger, profile sim.DeviceProfile) error {
	ip := net.ParseIP(profile.SourceIP)
	if ip == nil {
		return fmt.Errorf("invalid source IP %q", profile.SourceIP)
	}
	opts := mqtt.NewClientOptions().
		AddBroker("tcp://" + net.JoinHostPort(profile.ServerHost, strconv.Itoa(profile.MQTTPort))).
		SetClientID(profile.ID).
		SetCleanSession(true).
		SetConnectTimeout(10 * time.Second).
		SetWriteTimeout(10 * time.Second).
		SetKeepAlive(30 * time.Second)
	opts.SetDialer(&net.Dialer{
		Timeout:   5 * time.Second,
		LocalAddr: &net.TCPAddr{IP: ip},
	})

	client := mqtt.NewClient(opts)
	if token := client.Connect(); !token.WaitTimeout(15 * time.Second) {
		return fmt.Errorf("mqtt connect timeout")
	} else if token.Error() != nil {
		return token.Error()
	}
	defer client.Disconnect(250)

	for seq := 0; canSendMessage(ctx, profile, seq); seq++ {
		if !waitForMessageSlot(ctx, profile, seq) {
			break
		}
		payload := sim.GeneratePayload(profile, seq)
		token := client.Publish(profile.Topic, 0, false, payload)
		token.Wait()
		status := "ok"
		errText := ""
		if token.Error() != nil {
			status = "error"
			errText = token.Error().Error()
		}
		_ = logger.Write(sim.Event{
			Role:        "client",
			Event:       "message_sent",
			Protocol:    sim.ProtocolMQTT,
			DeviceID:    profile.ID,
			DeviceType:  profile.DeviceType,
			SourceIP:    profile.SourceIP,
			Topic:       profile.Topic,
			PayloadSize: len(payload),
			Status:      status,
			Error:       errText,
		})
		if errText != "" {
			return fmt.Errorf("mqtt publish failed: %s", errText)
		}
	}
	return nil
}

func runCoAPDevice(ctx context.Context, logger *sim.EventLogger, profile sim.DeviceProfile) error {
	ip := net.ParseIP(profile.SourceIP)
	if ip == nil {
		return fmt.Errorf("invalid source IP %q", profile.SourceIP)
	}
	conn, err := coapudp.Dial(
		net.JoinHostPort(profile.ServerHost, strconv.Itoa(profile.CoAPPort)),
		options.WithDialer(&net.Dialer{LocalAddr: &net.UDPAddr{IP: ip}}),
	)
	if err != nil {
		return err
	}
	defer conn.Close()

	for seq := 0; canSendMessage(ctx, profile, seq); seq++ {
		if !waitForMessageSlot(ctx, profile, seq) {
			break
		}
		payload := sim.GeneratePayload(profile, seq)
		resp, err := conn.Post(ctx, profile.Path, message.AppJSON, bytes.NewReader(payload))
		status := "ok"
		errText := ""
		if err != nil {
			status = "error"
			errText = err.Error()
			if ctx.Err() != nil {
				return nil
			}
		} else if resp.Code() != codes.Changed && resp.Code() != codes.Content && resp.Code() != codes.Created {
			status = "error"
			errText = resp.Code().String()
		}
		_ = logger.Write(sim.Event{
			Role:        "client",
			Event:       "message_sent",
			Protocol:    sim.ProtocolCoAP,
			DeviceID:    profile.ID,
			DeviceType:  profile.DeviceType,
			SourceIP:    profile.SourceIP,
			Path:        profile.Path,
			PayloadSize: len(payload),
			Status:      status,
			Error:       errText,
		})
		if errText != "" {
			return fmt.Errorf("coap send failed: %s", errText)
		}
	}
	return nil
}

func canSendMessage(ctx context.Context, profile sim.DeviceProfile, seq int) bool {
	if profile.MessageCount > 0 && seq >= profile.MessageCount {
		return false
	}
	select {
	case <-ctx.Done():
		return false
	default:
		return true
	}
}

func waitForMessageSlot(ctx context.Context, profile sim.DeviceProfile, seq int) bool {
	if seq == 0 {
		return canSendMessage(ctx, profile, seq)
	}
	delay := sim.JitterDelay(profile.Interval(), profile.Jitter(), seq, profile.Seed)
	return sleepContext(ctx, delay) == nil && canSendMessage(ctx, profile, seq)
}

func sleepContext(ctx context.Context, delay time.Duration) error {
	if delay <= 0 {
		return ctx.Err()
	}
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

func resolveSourceIPs(explicit stringList, filePath, cidr string, wait time.Duration) ([]string, error) {
	var ips []string
	for _, ip := range explicit {
		parsed := net.ParseIP(ip)
		if parsed == nil {
			return nil, fmt.Errorf("invalid --source-ip %q", ip)
		}
		ips = append(ips, parsed.String())
	}
	if filePath != "" {
		content, err := os.ReadFile(filePath)
		if err != nil {
			return nil, fmt.Errorf("read source IP file: %w", err)
		}
		for _, line := range strings.Split(string(content), "\n") {
			line = strings.TrimSpace(line)
			if line == "" || strings.HasPrefix(line, "#") {
				continue
			}
			parsed := net.ParseIP(line)
			if parsed == nil {
				return nil, fmt.Errorf("invalid source IP in file %q", line)
			}
			ips = append(ips, parsed.String())
		}
	}
	if len(ips) > 0 {
		return dedupe(ips), nil
	}

	deadline := time.Now().Add(wait)
	for {
		discovered, err := sim.DiscoverSourceIPs(cidr)
		if err != nil {
			return nil, err
		}
		if len(discovered) > 0 {
			return discovered, nil
		}
		if time.Now().After(deadline) {
			return nil, fmt.Errorf("no source IPs discovered in %s before timeout %s", cidr, wait)
		}
		time.Sleep(time.Second)
	}
}

func dedupe(values []string) []string {
	seen := map[string]bool{}
	var out []string
	for _, value := range values {
		if !seen[value] {
			out = append(out, value)
			seen[value] = true
		}
	}
	return out
}

func encodeProfile(profile sim.DeviceProfile) (string, error) {
	b, err := json.Marshal(profile)
	if err != nil {
		return "", err
	}
	return base64.StdEncoding.EncodeToString(b), nil
}

func decodeProfile(encoded string) (sim.DeviceProfile, error) {
	var profile sim.DeviceProfile
	b, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil {
		return profile, err
	}
	err = json.Unmarshal(b, &profile)
	return profile, err
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, "iot-client:", err)
	os.Exit(1)
}
