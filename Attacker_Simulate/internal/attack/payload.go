package attack

import (
	"encoding/binary"
	"encoding/json"
	"math/rand"
	"net"
	"strings"
	"time"
)

type AttackPayload struct {
	Scenario  string  `json:"scenario"`
	Level     string  `json:"level"`
	SourceIP  string  `json:"source_ip"`
	Target    string  `json:"target"`
	Sequence  int     `json:"sequence"`
	Metric    float64 `json:"metric"`
	Padding   string  `json:"padding,omitempty"`
	Timestamp string  `json:"timestamp"`
}

func GeneratePayload(cfg Config, sourceIP string, seq int) []byte {
	r := rand.New(rand.NewSource(time.Now().UnixNano() + int64(seq)))
	payload := AttackPayload{
		Scenario:  cfg.Scenario,
		Level:     cfg.Level,
		SourceIP:  sourceIP,
		Target:    cfg.Target,
		Sequence:  seq,
		Metric:    r.Float64(),
		Timestamp: time.Now().UTC().Format(time.RFC3339Nano),
	}
	body := mustJSON(payload)
	if len(body) >= cfg.PayloadBytes {
		return body
	}
	paddingLen := cfg.PayloadBytes - len(body)
	for range 4 {
		payload.Padding = strings.Repeat("x", paddingLen)
		body = mustJSON(payload)
		if len(body) == cfg.PayloadBytes {
			return body
		}
		if len(body) > cfg.PayloadBytes {
			paddingLen -= len(body) - cfg.PayloadBytes
		} else {
			paddingLen += cfg.PayloadBytes - len(body)
		}
		if paddingLen < 0 {
			paddingLen = 0
		}
	}
	return body
}

func mustJSON(v any) []byte {
	body, err := json.Marshal(v)
	if err != nil {
		return []byte("{}")
	}
	return body
}

func BuildIPv4TCPSYN(srcIP, dstIP net.IP, srcPort, dstPort int, seq uint32) []byte {
	src := srcIP.To4()
	dst := dstIP.To4()
	ipHeaderLen := 20
	tcpHeaderLen := 20
	packet := make([]byte, ipHeaderLen+tcpHeaderLen)

	packet[0] = 0x45
	packet[1] = 0
	binary.BigEndian.PutUint16(packet[2:4], uint16(len(packet)))
	binary.BigEndian.PutUint16(packet[4:6], uint16(rand.Intn(65535)))
	binary.BigEndian.PutUint16(packet[6:8], 0x4000)
	packet[8] = 64
	packet[9] = 6
	copy(packet[12:16], src)
	copy(packet[16:20], dst)
	binary.BigEndian.PutUint16(packet[10:12], checksum(packet[:ipHeaderLen]))

	tcp := packet[ipHeaderLen:]
	binary.BigEndian.PutUint16(tcp[0:2], uint16(srcPort))
	binary.BigEndian.PutUint16(tcp[2:4], uint16(dstPort))
	binary.BigEndian.PutUint32(tcp[4:8], seq)
	tcp[12] = 5 << 4
	tcp[13] = 0x02
	binary.BigEndian.PutUint16(tcp[14:16], 64240)

	pseudo := make([]byte, 12+tcpHeaderLen)
	copy(pseudo[0:4], src)
	copy(pseudo[4:8], dst)
	pseudo[8] = 0
	pseudo[9] = 6
	binary.BigEndian.PutUint16(pseudo[10:12], uint16(tcpHeaderLen))
	copy(pseudo[12:], tcp)
	binary.BigEndian.PutUint16(tcp[16:18], checksum(pseudo))
	return packet
}

func BuildIPv4ICMPEcho(srcIP, dstIP net.IP, id, seq int, payload []byte) []byte {
	src := srcIP.To4()
	dst := dstIP.To4()
	ipHeaderLen := 20
	icmpHeaderLen := 8
	packet := make([]byte, ipHeaderLen+icmpHeaderLen+len(payload))

	packet[0] = 0x45
	binary.BigEndian.PutUint16(packet[2:4], uint16(len(packet)))
	binary.BigEndian.PutUint16(packet[4:6], uint16(rand.Intn(65535)))
	binary.BigEndian.PutUint16(packet[6:8], 0x4000)
	packet[8] = 64
	packet[9] = 1
	copy(packet[12:16], src)
	copy(packet[16:20], dst)
	binary.BigEndian.PutUint16(packet[10:12], checksum(packet[:ipHeaderLen]))

	icmp := packet[ipHeaderLen:]
	icmp[0] = 8
	icmp[1] = 0
	binary.BigEndian.PutUint16(icmp[4:6], uint16(id))
	binary.BigEndian.PutUint16(icmp[6:8], uint16(seq))
	copy(icmp[8:], payload)
	binary.BigEndian.PutUint16(icmp[2:4], checksum(icmp))
	return packet
}

func checksum(data []byte) uint16 {
	sum := uint32(0)
	for len(data) >= 2 {
		sum += uint32(binary.BigEndian.Uint16(data[:2]))
		data = data[2:]
	}
	if len(data) == 1 {
		sum += uint32(data[0]) << 8
	}
	for sum>>16 != 0 {
		sum = (sum & 0xffff) + (sum >> 16)
	}
	return ^uint16(sum)
}

func RandomIPInCIDR(cidr string) net.IP {
	ip, network, err := net.ParseCIDR(cidr)
	if err != nil {
		return net.IPv4(12, 1, byte(rand.Intn(255)), byte(rand.Intn(254)+1))
	}
	ip = ip.To4()
	ones, bits := network.Mask.Size()
	if bits != 32 || ones >= 31 {
		return append(net.IP(nil), ip...)
	}
	hostBits := 32 - ones
	maxHosts := uint32(1 << hostBits)
	offset := uint32(rand.Int31n(int32(maxHosts-2))) + 1
	base := binary.BigEndian.Uint32(ip)
	out := make(net.IP, 4)
	binary.BigEndian.PutUint32(out, base+offset)
	return out
}
