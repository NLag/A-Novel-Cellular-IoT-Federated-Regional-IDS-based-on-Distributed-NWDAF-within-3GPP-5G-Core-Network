package attack

import (
	"bufio"
	"fmt"
	"net"
	"os"
	"slices"
	"strings"
	"time"
)

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
			if ip == nil || ip.To4() == nil || !network.Contains(ip) {
				continue
			}
			value := ip.String()
			if !slices.Contains(ips, value) {
				ips = append(ips, value)
			}
		}
	}
	slices.Sort(ips)
	return ips, nil
}

func WaitForSourceIPs(sourceCIDR string, explicit []string, filePath string, wait time.Duration) ([]string, error) {
	var sourceIPs []string
	sourceIPs = append(sourceIPs, explicit...)
	if filePath != "" {
		fileIPs, err := ReadSourceIPFile(filePath)
		if err != nil {
			return nil, err
		}
		sourceIPs = append(sourceIPs, fileIPs...)
	}
	if len(sourceIPs) > 0 {
		return UniqueValidIPs(sourceIPs)
	}
	deadline := time.Now().Add(wait)
	for {
		discovered, err := DiscoverSourceIPs(sourceCIDR)
		if err != nil {
			return nil, err
		}
		if len(discovered) > 0 {
			return discovered, nil
		}
		if time.Now().After(deadline) {
			return nil, fmt.Errorf("no source IPs discovered in %s within %s", sourceCIDR, wait)
		}
		time.Sleep(1 * time.Second)
	}
}

func ReadSourceIPFile(path string) ([]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("open source IP file: %w", err)
	}
	defer f.Close()
	var out []string
	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		item := strings.TrimSpace(scanner.Text())
		if item != "" && !strings.HasPrefix(item, "#") {
			out = append(out, item)
		}
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("read source IP file: %w", err)
	}
	return out, nil
}

func UniqueValidIPs(values []string) ([]string, error) {
	var out []string
	for _, value := range values {
		value = strings.TrimSpace(value)
		ip := net.ParseIP(value)
		if ip == nil || ip.To4() == nil {
			return nil, fmt.Errorf("invalid source IP %q", value)
		}
		if !slices.Contains(out, ip.String()) {
			out = append(out, ip.String())
		}
	}
	slices.Sort(out)
	return out, nil
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
