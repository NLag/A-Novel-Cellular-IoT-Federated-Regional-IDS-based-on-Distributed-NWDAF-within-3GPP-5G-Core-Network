"""The Agent is the cornerstone of Casmella. It runs on each node of the cluster and requires to be in a privileged mode. Our Agent relies on the eBPF technology to
observe the network traffic between the 5G CNFs and then reports metrics and logs. We recall that eBPF is a technology allowing to run programs at the Linux kernel
level in an efficient and secure way. eBPF doesn't require neither the modification nor the recompilation of the kernel source code, permitting hence the extension
of the kernel functionality at runtime.

The Linux kernel exposes several attachment points (i.e., hooks) to which eBPF programs can be associated. For each attachment point, an eBPF program will have
access to event-related data and metadata (e.g., network packets in bytes and the memory address of the beginning and end of the packet, etc.) on which it can
trigger actions that will be performed by the kernel (e.g., delivering a packet to the next point in the kernel networking stack, dropping a network packet,
forwarding a packet to another interface, etc.).

In Casmella, we leverage eBPF to implement Traffic Control (TC) and Express Data Path (XDP) programs which will efficiently handle networking-related events.
These two programs are attached to two layers of the kernel's networking stack (TC and XDP layers) which are similar in their characteristics and can be used for
similar purposes. However, they offer complementary functionalities. XDP is the closest layer to the Network Interface Card (NIC) providing hence the best possible
network performance, but, it only manages ingress packets. TC for its part achieves lower performance, but, it  handles both ingress and egress packets.

Our implemented eBPF programs will be instantiated for each interface. Each eBPF program's instance will be executed for every network packet passing through this interface.
"""
