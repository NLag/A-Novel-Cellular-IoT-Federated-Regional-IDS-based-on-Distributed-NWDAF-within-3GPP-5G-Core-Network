"""eBPF package.

This package implements the eBPF class for managing and communicating with eBPF programs. It also
implemet various callback functions to handle the events reported by eBPF programs.

Once the kernel-space programs (eBPF programs) are attached to the network interfaces on the node,
they will be executed for each network packet passing through these interfaces. For each execution,
the input depends on the layer running the eBPF program at kernel level (`struct xdp_md` for XDP
and `struct __sk_buff` for TC). However, our XDP and TC programs work very similarly and use the
following information that is available at both layers: the `data` and `data_end` pointers to the
beginning and end of the network packet respectively.

The algorithm implemented by the kernel-space programs eBPF program consists in filtering the
candidate events to be part of 5G communications (i.e. communications based on protocols used in
5G) and then writing the bytes from the application layer of the network packet ideally into a
Ring buffer. In fact, Ring buffers are eBPF maps in the form of circular buffers allowing to push
per-event data to user-space. They are very similar to their Perf buffers predecessors with
improvements on memory and latency overheads.
"""
