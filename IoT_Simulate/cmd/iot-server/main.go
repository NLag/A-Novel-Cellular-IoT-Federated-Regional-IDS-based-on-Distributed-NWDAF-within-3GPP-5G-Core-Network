package main

import (
	"bytes"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	mqttclient "github.com/eclipse/paho.mqtt.golang"
	mqttserver "github.com/mochi-mqtt/server/v2"
	"github.com/mochi-mqtt/server/v2/hooks/auth"
	"github.com/mochi-mqtt/server/v2/listeners"
	coap "github.com/plgd-dev/go-coap/v3"
	"github.com/plgd-dev/go-coap/v3/message"
	"github.com/plgd-dev/go-coap/v3/message/codes"
	"github.com/plgd-dev/go-coap/v3/mux"

	"iot_simulate/internal/sim"
)

func main() {
	var bind string
	var httpPort int
	var mqttPort int
	var coapPort int
	var out string

	flag.StringVar(&bind, "bind", "0.0.0.0", "Server bind address")
	flag.IntVar(&httpPort, "http-port", 8088, "HTTP ingest port")
	flag.IntVar(&mqttPort, "mqtt-port", 1883, "MQTT broker port")
	flag.IntVar(&coapPort, "coap-port", 5683, "CoAP UDP port")
	flag.StringVar(&out, "out", "iot_server_events.jsonl", "JSONL server event output path, or '-' for stdout")
	flag.Parse()

	logger, err := sim.NewEventLogger(out)
	if err != nil {
		fatal(err)
	}
	defer logger.Close()

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	servers, err := startServers(ctx, logger, bind, httpPort, mqttPort, coapPort)
	if err != nil {
		fatal(err)
	}

	_ = logger.Write(sim.Event{
		Role:   "server",
		Event:  "server_started",
		Status: "ok",
		Fields: map[string]any{
			"bind":      bind,
			"http_port": httpPort,
			"mqtt_port": mqttPort,
			"coap_port": coapPort,
		},
	})

	<-ctx.Done()
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if servers.http != nil {
		_ = servers.http.Shutdown(shutdownCtx)
	}
	if servers.mqttSubscriber != nil && servers.mqttSubscriber.IsConnected() {
		servers.mqttSubscriber.Disconnect(250)
	}
	if servers.mqttBroker != nil {
		_ = servers.mqttBroker.Close()
	}
	_ = logger.Write(sim.Event{Role: "server", Event: "server_stopped", Status: "ok"})
}

type runningServers struct {
	http           *http.Server
	mqttBroker     *mqttserver.Server
	mqttSubscriber mqttclient.Client
}

func startServers(ctx context.Context, logger *sim.EventLogger, bind string, httpPort, mqttPort, coapPort int) (runningServers, error) {
	httpServer := startHTTPServer(logger, bind, httpPort)

	broker, subscriber, err := startMQTTServer(logger, bind, mqttPort)
	if err != nil {
		_ = httpServer.Close()
		return runningServers{}, err
	}

	if err := startCoAPServer(ctx, logger, bind, coapPort); err != nil {
		_ = httpServer.Close()
		_ = broker.Close()
		if subscriber != nil && subscriber.IsConnected() {
			subscriber.Disconnect(250)
		}
		return runningServers{}, err
	}

	return runningServers{http: httpServer, mqttBroker: broker, mqttSubscriber: subscriber}, nil
}

func startHTTPServer(logger *sim.EventLogger, bind string, port int) *http.Server {
	mux := http.NewServeMux()
	mux.HandleFunc("/ingest/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost && r.Method != http.MethodPut {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 2<<20))
		if err != nil {
			http.Error(w, "read body", http.StatusBadRequest)
			return
		}
		defer r.Body.Close()
		meta := payloadMetadata(body)
		_ = logger.Write(sim.Event{
			Role:        "server",
			Event:       "message_received",
			Protocol:    sim.ProtocolHTTP,
			DeviceID:    firstNonEmpty(r.Header.Get("X-Device-ID"), meta.DeviceID),
			DeviceType:  firstNonEmpty(r.Header.Get("X-Device-Type"), meta.DeviceType),
			SourceIP:    meta.SourceIP,
			RemoteAddr:  r.RemoteAddr,
			Path:        r.URL.Path,
			PayloadSize: len(body),
			Status:      "ok",
		})
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		_, _ = w.Write([]byte(`{"status":"accepted"}`))
	})
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte("ok\n"))
	})

	server := &http.Server{
		Addr:              net.JoinHostPort(bind, strconv.Itoa(port)),
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
	}
	go func() {
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			_ = logger.Write(sim.Event{
				Role:     "server",
				Event:    "http_server_failed",
				Protocol: sim.ProtocolHTTP,
				Status:   "error",
				Error:    err.Error(),
			})
		}
	}()
	return server
}

func startMQTTServer(logger *sim.EventLogger, bind string, port int) (*mqttserver.Server, mqttclient.Client, error) {
	broker := mqttserver.New(&mqttserver.Options{InlineClient: true})
	if err := broker.AddHook(new(auth.AllowHook), nil); err != nil {
		return nil, nil, fmt.Errorf("add mqtt allow hook: %w", err)
	}
	tcp := listeners.NewTCP(listeners.Config{
		ID:      "iot-mqtt",
		Address: net.JoinHostPort(bind, strconv.Itoa(port)),
	})
	if err := broker.AddListener(tcp); err != nil {
		return nil, nil, fmt.Errorf("add mqtt listener: %w", err)
	}
	go func() {
		if err := broker.Serve(); err != nil {
			_ = logger.Write(sim.Event{
				Role:     "server",
				Event:    "mqtt_broker_failed",
				Protocol: sim.ProtocolMQTT,
				Status:   "error",
				Error:    err.Error(),
			})
		}
	}()

	var subscriber mqttclient.Client
	subscribeHost := bind
	if bind == "0.0.0.0" || bind == "::" || bind == "" {
		subscribeHost = "127.0.0.1"
	}
	opts := mqttclient.NewClientOptions().
		AddBroker("tcp://" + net.JoinHostPort(subscribeHost, strconv.Itoa(port))).
		SetClientID("iot-server-jsonl-subscriber").
		SetCleanSession(true).
		SetConnectTimeout(10 * time.Second).
		SetDefaultPublishHandler(func(_ mqttclient.Client, msg mqttclient.Message) {
			meta := payloadMetadata(msg.Payload())
			_ = logger.Write(sim.Event{
				Role:        "server",
				Event:       "message_received",
				Protocol:    sim.ProtocolMQTT,
				DeviceID:    meta.DeviceID,
				DeviceType:  meta.DeviceType,
				SourceIP:    meta.SourceIP,
				Topic:       msg.Topic(),
				PayloadSize: len(msg.Payload()),
				Status:      "ok",
			})
		})

	subscriber = mqttclient.NewClient(opts)
	deadline := time.Now().Add(5 * time.Second)
	for {
		token := subscriber.Connect()
		token.Wait()
		if token.Error() == nil {
			break
		}
		if time.Now().After(deadline) {
			_ = broker.Close()
			return nil, nil, fmt.Errorf("connect internal mqtt subscriber: %w", token.Error())
		}
		time.Sleep(200 * time.Millisecond)
	}
	token := subscriber.Subscribe("#", 0, nil)
	token.Wait()
	if token.Error() != nil {
		_ = broker.Close()
		subscriber.Disconnect(250)
		return nil, nil, fmt.Errorf("subscribe internal mqtt logger: %w", token.Error())
	}
	return broker, subscriber, nil
}

func startCoAPServer(ctx context.Context, logger *sim.EventLogger, bind string, port int) error {
	router := mux.NewRouter()
	router.DefaultHandleFunc(func(w mux.ResponseWriter, r *mux.Message) {
		body, _ := io.ReadAll(r.Body())
		path, _ := r.Options().Path()
		meta := payloadMetadata(body)
		remote := ""
		if conn := w.Conn(); conn != nil && conn.RemoteAddr() != nil {
			remote = conn.RemoteAddr().String()
		}
		_ = logger.Write(sim.Event{
			Role:        "server",
			Event:       "message_received",
			Protocol:    sim.ProtocolCoAP,
			DeviceID:    meta.DeviceID,
			DeviceType:  meta.DeviceType,
			SourceIP:    meta.SourceIP,
			RemoteAddr:  remote,
			Path:        "/" + strings.TrimPrefix(path, "/"),
			PayloadSize: len(body),
			Status:      "ok",
		})
		if err := w.SetResponse(codes.Changed, message.TextPlain, bytes.NewReader([]byte("changed"))); err != nil {
			_ = logger.Write(sim.Event{
				Role:     "server",
				Event:    "coap_response_failed",
				Protocol: sim.ProtocolCoAP,
				Status:   "error",
				Error:    err.Error(),
			})
		}
	})

	addr := net.JoinHostPort(bind, strconv.Itoa(port))
	go func() {
		if err := coap.ListenAndServe("udp", addr, router); err != nil && ctx.Err() == nil {
			_ = logger.Write(sim.Event{
				Role:     "server",
				Event:    "coap_server_failed",
				Protocol: sim.ProtocolCoAP,
				Status:   "error",
				Error:    err.Error(),
			})
		}
	}()
	return nil
}

type payloadMeta struct {
	DeviceID   string `json:"device_id"`
	DeviceType string `json:"device_type"`
	SourceIP   string `json:"source_ip"`
}

func payloadMetadata(payload []byte) payloadMeta {
	payload = bytes.TrimSpace(payload)
	var meta payloadMeta
	_ = json.Unmarshal(payload, &meta)
	return meta
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if value != "" {
			return value
		}
	}
	return ""
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, "iot-server:", err)
	os.Exit(1)
}
