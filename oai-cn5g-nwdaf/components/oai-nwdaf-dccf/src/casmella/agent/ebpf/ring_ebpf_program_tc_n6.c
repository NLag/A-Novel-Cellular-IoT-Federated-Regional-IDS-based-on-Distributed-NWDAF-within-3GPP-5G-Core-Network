//#define KBUILD_MODNAME "trafic_handler"
#include <linux/pkt_cls.h>
#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/in.h>

#define RINGBUF_FLAGS 0  // BPF_RB_NO_WAKEUP

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
BPF_RINGBUF_OUTPUT(ipv4_events, 256);

static int trafic_handler(struct __sk_buff *skb, u64 capturing_time, __u8 layer)
{
  void *data = (void *)(long)skb->data;
  void *data_end = (void *)(long)skb->data_end;
  struct ethhdr *eth = data;

  if ( ((void*)eth + sizeof(*eth) <= data_end) && (eth->h_proto == htons(ETH_P_IP)) ) {

    /* Point to the IP Header */
    struct iphdr *ip = data + sizeof(*eth);

    /* Check that the size of the packet is good */
    if ( (void*)ip + sizeof(*ip) <= data_end ) {

            // reserve space within the ring buffer
            struct ipevt *ipv4_event = ipv4_events.ringbuf_reserve(sizeof(struct ipevt));
            if (!ipv4_event)
                return TC_ACT_OK;

            // fill the event
            ipv4_event->ip_src = ip->saddr;
            ipv4_event->ip_dest = ip->daddr;
            ipv4_event->tot_len = ntohs(ip->tot_len);
            ipv4_event->tos = ip->tos;
            ipv4_event->capturing_time = capturing_time;
            ipv4_event->layer = layer;

            // send the event
            ipv4_events.ringbuf_submit(ipv4_event, RINGBUF_FLAGS);

    }

  }

  return TC_ACT_OK;
}

int trafic_handler_ingress(struct __sk_buff *skb)
{
  u64 capturing_time = bpf_ktime_get_ns();
  return trafic_handler(skb, capturing_time, 0);
}

int trafic_handler_egress(struct __sk_buff *skb)
{
  u64 capturing_time = bpf_ktime_get_ns();
  return trafic_handler(skb, capturing_time, 1);
}
