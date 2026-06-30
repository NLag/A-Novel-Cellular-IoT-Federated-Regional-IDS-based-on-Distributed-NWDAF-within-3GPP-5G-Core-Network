//#define KBUILD_MODNAME "trafic_handler"
#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/in.h>

/* IP layer events */
struct ipevt {
    __be32 ip_src;
    __be32 ip_dest;
    __u16	tot_len;
    __u8	tos;
    __u64 capturing_time;
    __u8 layer;
};

/* IP layer event buffers */
BPF_PERF_OUTPUT(ipv4_events);

int trafic_handler(struct xdp_md *ctx)
{
  u64 capturing_time = bpf_ktime_get_ns();
  void *data = (void *)(long)ctx->data;
  void *data_end = (void *)(long)ctx->data_end;
  struct ethhdr *eth = data;

  if ( ((void*)eth + sizeof(*eth) <= data_end) && (eth->h_proto == htons(ETH_P_IP)) ) {

    /* Point to the IP Header */
    struct iphdr *ip = data + sizeof(*eth);

    /* Check that the size of the packet is good */
    if ( (void*)ip + sizeof(*ip) <= data_end ) {

            struct ipevt ipv4_event = {};

            // fill the event
            ipv4_event.ip_src = ip->saddr;
            ipv4_event.ip_dest = ip->daddr;
            ipv4_event.tot_len = ntohs(ip->tot_len);
            ipv4_event.tos = ip->tos;
            ipv4_event.capturing_time = capturing_time;
            ipv4_event.layer = 2;

            // send the event
            ipv4_events.perf_submit(skb, &ipv4_event, sizeof(ipv4_event));

    }

  }

  return XDP_PASS;
}