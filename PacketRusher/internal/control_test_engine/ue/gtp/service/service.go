/**
 * SPDX-License-Identifier: Apache-2.0
 * © Copyright 2023 Hewlett Packard Enterprise Development LP
 */
package service

import (
	"fmt"
	"hash/fnv"
	"my5G-RANTester/config"
	gnbContext "my5G-RANTester/internal/control_test_engine/gnb/context"
	"my5G-RANTester/internal/control_test_engine/ue/context"

	gtpLink "github.com/free5gc/go-gtp5gnl/linkcmd"
	gtpTunnel "github.com/free5gc/go-gtp5gnl/tuncmd"

	log "github.com/sirupsen/logrus"
	"github.com/vishvananda/netlink"

	"net"
	"net/netip"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

type gtpRuleIDs struct {
	farUplink   uint32
	farDownlink uint32
	pdrDownlink uint32
	pdrUplink   uint32
	qer         uint32
}

type sharedGnbTunnel struct {
	name       string
	gnbIp      netip.Addr
	stopSignal chan bool
	refs       int
}

type sharedGnbTunnelRegistry struct {
	lock    sync.Mutex
	tunnels map[string]*sharedGnbTunnel
}

var (
	gtpRuleIDGenerator atomic.Uint32
	sharedTunnels      = sharedGnbTunnelRegistry{tunnels: map[string]*sharedGnbTunnel{}}
)

func SetupGtpInterface(ue *context.UEContext, msg gnbContext.UEMessage) {
	gnbPduSession := msg.GNBPduSessions[0]
	pduSession, err := ue.GetPduSession(uint8(gnbPduSession.GetPduSessionId()))
	if pduSession == nil || err != nil {
		log.Error("[GNB][GTP] Aborting the setup of PDU Session ", gnbPduSession.GetPduSessionId(), ", this PDU session was not succesfully configured on the UE's side.")
		return
	}
	pduSession.GnbPduSession = gnbPduSession

	if ue.TunnelMode == config.TunnelDisabled {
		log.Info(fmt.Sprintf("[UE][GTP] Interface for UE %s has not been created. Tunnel has been disabled.", ue.GetMsin()))
		return
	}

	if pduSession.Id != 1 {
		log.Warn("[GNB][GTP] Only one tunnel per UE is supported for now, no tunnel will be created for second PDU Session of given UE")
		return
	}

	// get UE GNB IP.
	pduSession.SetGnbIp(msg.GnbIp)

	ueGnbIp := pduSession.GetGnbIp()
	upfIp := pduSession.GnbPduSession.GetUpfIp()
	qfi := pduSession.GnbPduSession.GetQosId()
	ueIp := pduSession.GetIp()
	msin := ue.GetMsin()
	nameInf, releaseTunnel := setupGtpLink(ue, pduSession, ueGnbIp)
	vrfInf := fmt.Sprintf("vrf%s", msin)
	ruleIDs := allocateGtpRuleIDs()

	// Create FAR for uplink.
	cmdAddFar := []string{nameInf,
		strconv.FormatUint(uint64(ruleIDs.farUplink), 10),
		"--action", "2",
	}
	log.Debug("[UE][GTP] Setting up GTP Forwarding Action Rule for ", strings.Join(cmdAddFar, " "))
	if err := gtpTunnel.CmdAddFAR(cmdAddFar); err != nil {
		log.Fatal("[GNB][GTP] Unable to create FAR: ", err)
		return
	}

	// Create FAR for downlink.
	cmdAddFar = []string{nameInf,
		strconv.FormatUint(uint64(ruleIDs.farDownlink), 10),
		"--action", "2",
		"--hdr-creation", "0", strconv.FormatUint(uint64(gnbPduSession.GetTeidUplink()), 10), upfIp, "2152", // Outer Header Creation
	}
	log.Debug("[UE][GTP] Setting up GTP Forwarding Action Rule for ", strings.Join(cmdAddFar, " "))
	if err := gtpTunnel.CmdAddFAR(cmdAddFar); err != nil {
		log.Fatal("[UE][GTP] Unable to create FAR ", err)
		return
	}

	// Create PDR for uplink.
	cmdAddPdr := []string{nameInf,
		strconv.FormatUint(uint64(ruleIDs.pdrDownlink), 10),
		"--pcd", "1", // Precedence = 1
		"--hdr-rm", "0", // Outer Header Removal = GTP-U/UDP/IPv4
		"--ue-ipv4", ueIp, // UE IP Address
		"--f-teid", strconv.FormatUint(uint64(gnbPduSession.GetTeidDownlink()), 10), msg.GnbIp.String(), // F-TEID
		"--far-id", strconv.FormatUint(uint64(ruleIDs.farUplink), 10),
		"--src-intf", "1", // Source Interface = Core
	}
	log.Debug("[UE][GTP] Setting up GTP Packet Detection Rule for ", strings.Join(cmdAddPdr, " "))
	if err := gtpTunnel.CmdAddPDR(cmdAddPdr); err != nil {
		log.Fatal("[GNB][GTP] Unable to create FAR: ", err)
		return
	}

	cmdAddPdr = []string{nameInf,
		strconv.FormatUint(uint64(ruleIDs.pdrUplink), 10),
		"--pcd", "2", // Precedence = 2
		"--ue-ipv4", ueIp, // UE IP Address
		"--far-id", strconv.FormatUint(uint64(ruleIDs.farDownlink), 10),
		"--src-intf", "0", // Source Interface = Access
		"--gtpu-src-ip", ueGnbIp.String(), // GTP-U source IP address (not part of PFCP spec)
	}
	if qfi > 0 {
		// Create QER for downlink.
		cmdAddQer := []string{nameInf,
			strconv.FormatUint(uint64(ruleIDs.qer), 10),
			"--qfi", strconv.FormatInt(qfi, 10), // QFI
		}
		log.Debug("[UE][GTP] Setting Up QFI", strings.Join(cmdAddQer, " "))
		if err := gtpTunnel.CmdAddQER(cmdAddQer); err != nil {
			log.Fatal("[UE][GTP] Unable to create QER:", err)
			return
		}
		cmdAddPdr = append(cmdAddPdr,
			"--qer-id", strconv.FormatUint(uint64(ruleIDs.qer), 10),
		)
	}

	// Create PDR for downlink.
	log.Debug("[UE][GTP] Setting Up GTP Packet Detection Rule for ", strings.Join(cmdAddPdr, " "))
	if err := gtpTunnel.CmdAddPDR(cmdAddPdr); err != nil {
		log.Fatal("[UE][GTP] Unable to create FAR ", err)
		return
	}

	// Find TUN network interface.
	link, err := netlink.LinkByName(nameInf)
	if err != nil {
		log.Fatal("[UE][GTP] Unable to find GTP interface ", nameInf, ": ", err)
	}
	pduSession.SetTunInterface(link)

	// Add UE IP Address onto the TUN network interface.
	addrTun := &netlink.Addr{
		IPNet: &net.IPNet{
			IP:   net.ParseIP(ueIp).To4(),
			Mask: net.IPv4Mask(255, 255, 255, 255),
		},
	}
	if err := netlink.AddrReplace(link, addrTun); err != nil {
		log.Fatal("[UE][DATA] Error in adding IP for virtual interface", err)
		return
	}

	// Configure routing policy or VRF for the UE.
	tableId := gnbPduSession.GetTeidUplink()
	switch ue.TunnelMode {
	case config.TunnelTun:
		rule := netlink.NewRule()
		rule.Priority = 100
		rule.Table = int(tableId)
		rule.Src = addrTun.IPNet
		_ = netlink.RuleDel(rule)

		if err := netlink.RuleAdd(rule); err != nil {
			log.Fatal("[UE][DATA] Unable to create routing policy rule for UE", err)
			return
		}
		pduSession.SetTunRule(rule)
	case config.TunnelVrf:
		vrfDevice := &netlink.Vrf{
			LinkAttrs: netlink.LinkAttrs{
				Name: vrfInf,
			},
			Table: tableId,
		}
		_ = netlink.LinkDel(vrfDevice)

		if err := netlink.LinkAdd(vrfDevice); err != nil {
			log.Fatal("[UE][DATA] Unable to create VRF for UE", err)
			return
		}

		if err := netlink.LinkSetMaster(link, vrfDevice); err != nil {
			log.Fatal("[UE][DATA] Unable to set GTP tunnel as slave of VRF interface", err)
			return
		}

		if err := netlink.LinkSetUp(vrfDevice); err != nil {
			log.Fatal("[UE][DATA] Unable to set interface VRF UP", err)
			return
		}
		pduSession.SetVrfDevice(vrfDevice)
	}

	// Insert default route from the UE to the Data Network.
	route := &netlink.Route{
		Dst:       &net.IPNet{IP: net.IPv4zero, Mask: net.CIDRMask(0, 32)}, // default
		LinkIndex: link.Attrs().Index,                                      // dev val<MSIN>
		Scope:     netlink.SCOPE_LINK,                                      // scope link
		Protocol:  4,                                                       // proto static
		Priority:  1,                                                       // metric 1
		Table:     int(tableId),                                            // table <ECI>
	}
	if err := netlink.RouteReplace(route); err != nil {
		log.Fatal("[GNB][GTP] Unable to create Kernel Route ", err)
	}
	pduSession.SetTunRoute(route)
	pduSession.SetTunnelCleanup(func() {
		cleanupGtpPduSession(nameInf, ruleIDs, qfi > 0, link, addrTun, pduSession.GetTunRule(), pduSession.GetTunRoute(), pduSession.GetVrfDevice())
		releaseTunnel()
	})

	log.Info(fmt.Sprintf("[UE][GTP] Interface %s has successfully been configured for UE %s", nameInf, ueIp))
	switch ue.TunnelMode {
	case config.TunnelTun:
		log.Info(fmt.Sprintf("[UE][GTP] You can do traffic for this UE by binding to IP %s, eg:", ueIp))
		log.Info(fmt.Sprintf("[UE][GTP] iperf3 -B %s -c IPERF_SERVER -p PORT -t 9000", ueIp))
	case config.TunnelVrf:
		log.Info(fmt.Sprintf("[UE][GTP] You can do traffic for this UE using VRF %s, eg:", vrfInf))
		log.Info(fmt.Sprintf("[UE][GTP] sudo ip vrf exec %s iperf3 -c IPERF_SERVER -p PORT -t 9000", vrfInf))
	}
}

func setupGtpLink(ue *context.UEContext, pduSession *context.UEPDUSession, gnbIp netip.Addr) (string, func()) {
	if ue.TunnelMode == config.TunnelTun {
		tunnel := acquireSharedGnbTunnel(gnbIp)
		time.Sleep(time.Second)
		return tunnel.name, func() {
			releaseSharedGnbTunnel(gnbIp)
		}
	}

	nameInf := fmt.Sprintf("val%s", ue.GetMsin())
	stopSignal := make(chan bool)

	_ = gtpLink.CmdDel(nameInf)

	if pduSession.GetStopSignal() != nil {
		close(pduSession.GetStopSignal())
		time.Sleep(time.Second)
	}

	go func() {
		// This function should not return as long as the GTP-U UDP socket is open.
		if err := gtpLink.CmdAddWithStopCh(nameInf, 1, 131072, gnbIp.String(), "", stopSignal); err != nil {
			log.Fatal("[GNB][GTP] Unable to create Kernel GTP interface: ", err, ue.GetMsin(), nameInf)
			return
		}
	}()

	pduSession.SetStopSignal(stopSignal)
	time.Sleep(time.Second)

	return nameInf, func() {
		close(stopSignal)
		_ = gtpLink.CmdDel(nameInf)
	}
}

func acquireSharedGnbTunnel(gnbIp netip.Addr) *sharedGnbTunnel {
	key := gnbIp.String()

	sharedTunnels.lock.Lock()
	defer sharedTunnels.lock.Unlock()

	if tunnel := sharedTunnels.tunnels[key]; tunnel != nil {
		tunnel.refs++
		log.Debug("[GNB][GTP] Reusing shared GTP interface ", tunnel.name, " for gNB N3 ", key, ", refs=", tunnel.refs)
		return tunnel
	}

	tunnel := &sharedGnbTunnel{
		name:       sharedTunnelName(gnbIp),
		gnbIp:      gnbIp,
		stopSignal: make(chan bool),
		refs:       1,
	}
	_ = gtpLink.CmdDel(tunnel.name)
	sharedTunnels.tunnels[key] = tunnel

	go func() {
		// This function should not return as long as the shared GTP-U UDP socket is open.
		if err := gtpLink.CmdAddWithStopCh(tunnel.name, 1, 131072, tunnel.gnbIp.String(), "", tunnel.stopSignal); err != nil {
			log.Fatal("[GNB][GTP] Unable to create shared Kernel GTP interface: ", err, tunnel.name)
			return
		}
	}()

	log.Info("[GNB][GTP] Created shared GTP interface ", tunnel.name, " for gNB N3 ", key)
	return tunnel
}

func releaseSharedGnbTunnel(gnbIp netip.Addr) {
	key := gnbIp.String()

	sharedTunnels.lock.Lock()
	tunnel := sharedTunnels.tunnels[key]
	if tunnel == nil {
		sharedTunnels.lock.Unlock()
		return
	}
	tunnel.refs--
	if tunnel.refs > 0 {
		log.Debug("[GNB][GTP] Keeping shared GTP interface ", tunnel.name, " for gNB N3 ", key, ", refs=", tunnel.refs)
		sharedTunnels.lock.Unlock()
		return
	}
	delete(sharedTunnels.tunnels, key)
	sharedTunnels.lock.Unlock()

	close(tunnel.stopSignal)
	time.Sleep(100 * time.Millisecond)
	_ = gtpLink.CmdDel(tunnel.name)
	log.Info("[GNB][GTP] Removed shared GTP interface ", tunnel.name, " for gNB N3 ", key)
}

func sharedTunnelName(gnbIp netip.Addr) string {
	hash := fnv.New32a()
	_, _ = hash.Write([]byte(gnbIp.String()))
	return fmt.Sprintf("gnb%08x", hash.Sum32())
}

func allocateGtpRuleIDs() gtpRuleIDs {
	base := gtpRuleIDGenerator.Add(10)
	return gtpRuleIDs{
		farUplink:   base + 1,
		farDownlink: base + 2,
		pdrDownlink: base + 3,
		pdrUplink:   base + 4,
		qer:         base + 5,
	}
}

func cleanupGtpPduSession(nameInf string, ids gtpRuleIDs, hasQer bool, link netlink.Link, addr *netlink.Addr, rule *netlink.Rule, route *netlink.Route, vrf *netlink.Vrf) {
	_ = gtpTunnel.CmdDeletePDR([]string{nameInf, strconv.FormatUint(uint64(ids.pdrDownlink), 10)})
	_ = gtpTunnel.CmdDeletePDR([]string{nameInf, strconv.FormatUint(uint64(ids.pdrUplink), 10)})
	if hasQer {
		_ = gtpTunnel.CmdDeleteQER([]string{nameInf, strconv.FormatUint(uint64(ids.qer), 10)})
	}
	_ = gtpTunnel.CmdDeleteFAR([]string{nameInf, strconv.FormatUint(uint64(ids.farUplink), 10)})
	_ = gtpTunnel.CmdDeleteFAR([]string{nameInf, strconv.FormatUint(uint64(ids.farDownlink), 10)})

	if route != nil {
		_ = netlink.RouteDel(route)
	}
	if rule != nil {
		_ = netlink.RuleDel(rule)
	}
	if addr != nil && link != nil {
		_ = netlink.AddrDel(link, addr)
	}
	if vrf != nil {
		_ = netlink.LinkSetDown(vrf)
		_ = netlink.LinkDel(vrf)
	}
}
