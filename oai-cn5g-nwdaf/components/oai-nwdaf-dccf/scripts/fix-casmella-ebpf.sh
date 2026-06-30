#!/bin/bash
# Fix Casmella eBPF compilation errors

EBPF_FILE="/casmella/casmella/ebpf/perf_ebpf_program_tc.c"

echo "Patching Casmella eBPF program..."

# Fix 1: Make trafic_handler static inline
sed -i 's/__attribute__((section(".bpf.fn.trafic_handler")))$/static __always_inline/' $EBPF_FILE
sed -i 's/^int trafic_handler(struct __sk_buff \*skb)$/int trafic_handler(struct __sk_buff *skb, u64 capturing_time, __u8 layer)/' $EBPF_FILE

echo "✓ eBPF patches applied"
