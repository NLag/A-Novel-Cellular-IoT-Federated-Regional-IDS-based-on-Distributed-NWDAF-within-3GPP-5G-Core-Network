//#define KBUILD_MODNAME "trafic_handler"
#include <linux/pkt_cls.h>
#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/in.h>
#include <linux/udp.h>
#include <linux/tcp.h>
#include <linux/sctp.h>

#define MAX_RAW_SIZE 1024
#define GTPU_PAYLOAD_SIZE 20
#define RINGBUF_FLAGS BPF_RB_NO_WAKEUP  // BPF_RB_NO_WAKEUP
#define find_min(a,b) \
   ({ __typeof__ (a) _a = (a); \
       __typeof__ (b) _b = (b); \
     _a < _b ? _a : _b; })

// Headers
struct http2hdr {
  // See RFC 7540 section 4.1
  u8 length0;
  u8 length1;
  u8 length2;
	u8 type;
	u8 flags;
	__be32 stream_id;
};

/* Transort layer events data */


/* Application layer events */
struct evt {
    __be32 ip_src;
    __be32 ip_dest;
    __u16 src_port;
    __u16 dst_port;
    __u16 payload_length;
    __u16 payload_offset;
    __u64 capturing_time;
    __u8 layer;
    unsigned char raw[MAX_RAW_SIZE];
};
#define BASE_EVENT_SIZE ((u64)(&((struct evt*)0)->raw))

struct httpevt {
    __be32 ip_src;
    __be32 ip_dest;
    u8 reqresp;
    u16 length;
    u16 ofset;
};
struct ngapevt {
    __be32 ip_src;
    __be32 ip_dest;
    //__u16 src_port;
    //__u16 dst_port;
    u16 length;
    u16 payload_offset;
    u64 capturing_time;
};

/* Application layer per-cpu arrays */
BPF_PERCPU_ARRAY(events_array, struct evt, 1);

/* Application layer event buffers */
BPF_RINGBUF_OUTPUT(http2_events, 512);
BPF_RINGBUF_OUTPUT(pfcp_events, 256);
BPF_RINGBUF_OUTPUT(ngap_events, 256);
BPF_RINGBUF_OUTPUT(gtpu_events, 256);

static int trafic_handler(struct __sk_buff *skb, u64 capturing_time, __u8 layer)
{
  u32 len = skb->data_end - skb->data;
  void *data = (void *)(long)skb->data;
  void *data_end = (void *)(long)skb->data_end;
  struct ethhdr *eth = data;

  if ( ((void*)eth + sizeof(*eth) <= data_end) && (eth->h_proto == htons(ETH_P_IP)) ) {

    /* Point to the IP Header */
    struct iphdr *ip = data + sizeof(*eth);

    /* Check that the size of the packet is good */
    if ( (void*)ip + sizeof(*ip) <= data_end ) {

    /* Calculate the IP Header length in bytes */
    u16 ip_header_length = ip->ihl << 2;

    /* if the transport protocol is TCP */
    if ( ip->protocol == IPPROTO_TCP ) {

      /* Point to the TCP Header */
      struct tcphdr *tcp = (void*)ip + ip_header_length;

      /* Check that the size of the packet is good */
      if ( (void*)tcp + sizeof(*tcp) <= data_end ) {

        /* Calculate the TCP Header length in bytes */
        u16 tcp_header_length = tcp->doff << 2;

        u16 payload_offset = sizeof(*eth) + ip_header_length + tcp_header_length;
        u16 payload_length = ntohs(ip->tot_len) - ip_header_length - tcp_header_length;

        /* Filter HTTP/2 messages -- 9 octets is the size of the HTTP/2 Header */
        if(payload_length >= 9){
          // See RFC 7540 section 4.1

          struct http2hdr *http2 = (void*)tcp + tcp_header_length;

          if ( (void*)http2 + sizeof(*http2) <= data_end ) {

          //u8 frame_type = load_byte(skb , payload_offset + 3);
          u8 frame_type = http2->type;
          // network byte order
          u32 data_length;
          data_length = http2->length0*256*256 + http2->length1*256 + http2->length2;

          /* The type of the frame for HEADERS is equal to 1 */
          if( (data_length == payload_length-9) && (frame_type == 1) ){

            // read from per-cpu array
            u32 zero = 0;
            struct evt *http2_event = events_array.lookup(&zero);
            if (!http2_event)
                return TC_ACT_OK;

            // fill the event
            http2_event->ip_src = ip->saddr;
            http2_event->ip_dest = ip->daddr;
            http2_event->src_port = ntohs(tcp->source);
            http2_event->dst_port = ntohs(tcp->dest);
            http2_event->payload_length = payload_length;
            http2_event->payload_offset = 0;
            http2_event->capturing_time = capturing_time;
            http2_event->layer = layer;

            // get the size of raw bytes and the event
            unsigned char *raw_offset = (void*)http2;
            unsigned int raw_size = (unsigned int)find_min((u32)payload_length, (u32)MAX_RAW_SIZE);
            if (raw_size <= 0){
              return TC_ACT_OK;
            }
            u64 event_size = (u64)BASE_EVENT_SIZE + raw_size;

            // copy raw bytes
            int ret = bpf_probe_read_kernel(&http2_event->raw, raw_size & (MAX_RAW_SIZE-1), (unsigned char *)raw_offset);

            // send the event
            http2_events.ringbuf_output(http2_event, event_size & (MAX_RAW_SIZE-1), RINGBUF_FLAGS);
            return TC_ACT_OK;

          }
          }
        }

        return TC_ACT_OK; // TCP but not HTTP2
      }

    }


    /* if the transport protocol is SCTP */
    if (ip->protocol == IPPROTO_SCTP) {
      /* Point to the SCTP Header */
      struct sctphdr *sctp = (void*)ip + ip_header_length;

    /* Check that the size of the packet is good */
    if ( (void*)sctp + sizeof(*sctp) <= data_end ) {

      /* Point to the SCTP Chunk Header */
      struct sctp_chunkhdr *sctpchunk = (void*)sctp + sizeof(*sctp);

      /* Check that the size of the packet is good */
      if ( ((void*)sctpchunk + sizeof(*sctpchunk) <= data_end) ) {

        /* if the first SCTP Chunk is not transporting DATA and the SCTP packet is not a bundle*/
        //u16 max_padding = 3;
        //u16 payload_length = ntohs(ip->tot_len) - ip_header_length - sizeof(*sctp);
        //if( (sctpchunk->type != 0) && (ntohs(sctpchunk->length) + max_padding) >= payload_length ) ){
          //return TC_ACT_OK;
        //}

            // Check if this packet contains a bundle of chunks
            u8 isItBundle = 0;
            u16 payload_length = ntohs(ip->tot_len) - ip_header_length - sizeof(*sctp);
            u16 max_padding = 3;
            if ( ( ntohs(sctpchunk->length) + max_padding ) < payload_length )
              isItBundle = 1;

            // If not a bundle, check if this packet contains an NGAP payload
            if( isItBundle == 0 ){
            if( sctpchunk->type != 0 ){
              return TC_ACT_OK;
            }
            else {  /// This is a DATA chunk
              // Point to the SCTP Data Header
              struct sctp_datahdr *sctpdata = (void*)sctpchunk + sizeof(*sctpchunk);
              // Check that the size of the packet is good
              if( (void*)sctpdata + sizeof(*sctpdata) <= data_end ){
                // TS 38.412: 60 is the Payload Protocol Identifier of NGAP
                // The order in which encode this paramater is not specified in the rfc but is byte order in linux headers
                if( (sctpdata->ppid == 60) || (sctpdata->ppid == htonl(60)) ){
                  //pass
                }
                else{
                  return TC_ACT_OK;
                }
              }
            }
            }

            /// This packet is a bundle or contains NGAP payload ///

            // read from per-cpu array
            u32 zero = 0;
            struct evt *ngap_event = events_array.lookup(&zero);
            if (!ngap_event)
                return TC_ACT_OK;

            // fill the event
            ngap_event->ip_src = ip->saddr;
            ngap_event->ip_dest = ip->daddr;
            ngap_event->src_port = ntohs(sctp->source);
            ngap_event->dst_port = ntohs(sctp->dest);
            ngap_event->payload_length = payload_length;
            ngap_event->payload_offset = 0;
            ngap_event->capturing_time = capturing_time;
            ngap_event->layer = layer;

            // get the size of raw bytes and the event
            unsigned char *raw_offset = (void*)sctpchunk;
            unsigned int raw_size = (unsigned int)find_min((u32)payload_length, (u32)MAX_RAW_SIZE);
            if (raw_size <= 0){
              return TC_ACT_OK;
            }
            u64 event_size = (u64)BASE_EVENT_SIZE + raw_size;

            // copy raw bytes
            int ret = bpf_probe_read_kernel(&ngap_event->raw, raw_size & (MAX_RAW_SIZE-1), (unsigned char *)raw_offset);

            // send the event
            ngap_events.ringbuf_output(ngap_event, event_size & (MAX_RAW_SIZE-1), RINGBUF_FLAGS);

            return TC_ACT_OK;


            /* OLD
            // get information about the event
            struct ngapevt ngap_event = {};

            ngap_event.ip_src = ip->saddr;
            ngap_event.ip_dest = ip->daddr;
            //ngap_event.src_port = ntohs(sctp->source);
            //ngap_event.dst_port = ntohs(sctp->dest);
            // ngap_event.stream = ntohs(sctpdata->stream);
            // The NGAP length will include only the length of the payload, exlucidng any pading, the chunk and the data headers
            ngap_event.length = ntohs(ip->tot_len) - ip_header_length - sizeof(*sctp);
            // This will represent the the payload offset in the entire packet
            ngap_event.payload_offset = ( (void*)sctp + sizeof(*sctp) ) - (void*)eth;
            ngap_event.capturing_time = capturing_time;
            OLD */

      }

    }

    return TC_ACT_OK;

    }

    /* if the transport protocol is UDP */
    if (ip->protocol == IPPROTO_UDP) {
      /* Point to the UDP Header */
      struct udphdr *udp = (void*)ip + ip_header_length;

    /* Check that the size of the packet is good */
    if ( (void*)udp + sizeof(*udp) <= data_end ) {

      __u16 payload_length = ntohs(udp->len) - sizeof(*udp);

      /* Regargind the standards, 2152 is the port number used for GTP-U */
      if ( (udp->dest == htons(2152)) || (udp->source == htons(2152)) ) {

            // read from per-cpu array
            u32 zero = 0;
            struct evt *gtpu_event = events_array.lookup(&zero);
            if (!gtpu_event)
                return TC_ACT_OK;

            // fill the event
            gtpu_event->ip_src = ip->saddr;
            gtpu_event->ip_dest = ip->daddr;
            gtpu_event->src_port = ntohs(udp->source);
            gtpu_event->dst_port = ntohs(udp->dest);
            gtpu_event->payload_length = payload_length;
            gtpu_event->payload_offset = 0;
            gtpu_event->capturing_time = capturing_time;
            gtpu_event->layer = layer;

            // get the size of raw bytes and the event
            unsigned char *raw_offset = (void*)udp + sizeof(*udp);
            unsigned int raw_size = (unsigned int)find_min((u32)payload_length, (u32)MAX_RAW_SIZE);
            if (raw_size <= 0){
              return TC_ACT_OK;
            }
            u64 event_size = (u64)BASE_EVENT_SIZE + raw_size;

            // copy raw bytes
            int ret = bpf_probe_read_kernel(&gtpu_event->raw, raw_size & (MAX_RAW_SIZE-1), (unsigned char *)raw_offset);

            // send the event
            gtpu_events.ringbuf_output(gtpu_event, event_size & (MAX_RAW_SIZE-1), RINGBUF_FLAGS);

            return TC_ACT_OK;

      }

      /* Regargind the standards ==> request(dest=8805) et response(src=8805) */
      if ( (udp->dest == htons(8805)) || (udp->source == htons(8805)) ) {

            // read from per-cpu array
            u32 zero = 0;
            struct evt *pfcp_event = events_array.lookup(&zero);
            if (!pfcp_event)
                return TC_ACT_OK;

            // fill the event
            pfcp_event->ip_src = ip->saddr;
            pfcp_event->ip_dest = ip->daddr;
            pfcp_event->src_port = ntohs(udp->source);
            pfcp_event->dst_port = ntohs(udp->dest);
            pfcp_event->payload_length = payload_length;
            pfcp_event->payload_offset = 0;
            pfcp_event->capturing_time = capturing_time;
            pfcp_event->layer = layer;

            // get the size of raw bytes and the event
            unsigned char *raw_offset = (void*)udp + sizeof(*udp);
            unsigned int raw_size = (unsigned int)find_min((u32)payload_length, (u32)MAX_RAW_SIZE);
            if (raw_size <= 0){
              return TC_ACT_OK;
            }
            u64 event_size = (u64)BASE_EVENT_SIZE + raw_size;

            // copy raw bytes
            int ret = bpf_probe_read_kernel(&pfcp_event->raw, raw_size & (MAX_RAW_SIZE-1), (unsigned char *)raw_offset);

            // send the event
            pfcp_events.ringbuf_output(pfcp_event, event_size & (MAX_RAW_SIZE-1), RINGBUF_FLAGS);

            return TC_ACT_OK;

      }

    }

    return TC_ACT_OK; // UDP but nor GTP-U nor PFCP

    }

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
