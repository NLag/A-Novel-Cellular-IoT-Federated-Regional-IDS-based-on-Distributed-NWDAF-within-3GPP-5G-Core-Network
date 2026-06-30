"""eBPF module.
"""
# standard
from platform import release
from time import sleep
from threading import Thread, Lock
import ctypes as ct
from concurrent.futures import ThreadPoolExecutor
from copy import copy
import socket
# third-pary
from bcc import BPF
# from bcc import BPF, DEBUG_PREPROCESSOR, DEBUG_BTF
from pyroute2 import IPRoute
# internal
from core import cfg, metrics
from protocols.http2 import parse_http2_message
from protocols.pfcp import parse_pfcp_message_bundle
from protocols.ngap import parse_sctp_packet
from protocols.gtp import parse_gtpu_message, parse_ipv4_packet


logger = cfg.logging

for _logger in logger.Logger.manager.loggerDict:
    logger.getLogger(_logger).setLevel(cfg.logging.ERROR)

# Initialize global variables
IPR = IPRoute()
events_handlers_tasks = cfg.events_handlers_tasks
log_task_result = cfg.log_task_result


# ============================
# eBPF events handlers
# ============================
def return_event_class_common(size: int) -> ct.Structure:
    """Return a common event class.

    This function dynamically creates and returns a ctypes.Structure subclass, CommonEvent,
    with fields commonly used to represent network event data. The size of the `raw` field
    is calculated based on the provided size parameter and the sizes of the other fields.

    Args:
        size (int): The total size of the event structure in bytes.

    Returns:
        ct.Structure: A new ctypes.Structure subclass named CommonEvent with the following fields:
        - ip_src (ct.c_ubyte * 4): Source IP address as an array of 4 bytes.
        - ip_dest (ct.c_ubyte * 4): Destination IP address as an array of 4 bytes.
        - src_port (ct.c_uint16): Source port number.
        - dst_port (ct.c_uint16): Destination port number.
        - payload_length (ct.c_uint16): Length of the payload.
        - payload_offset (ct.c_uint16): Offset of the payload.
        - capturing_time (ct.c_uint64): Timestamp of when the event was captured.
        - layer (ct.c_uint8): Network layer identifier.
        - raw (ct.c_ubyte * N): Raw event data, where N is calculated based on the provided size minus the sizes of other fields.
    """
    class CommonEvent(ct.Structure):
        _fields_ = [
            ("ip_src", ct.c_ubyte * 4),
            ("ip_dest", ct.c_ubyte * 4),
            ("src_port", ct.c_uint16),
            ("dst_port", ct.c_uint16),
            ("payload_length", ct.c_uint16),
            ("payload_offset", ct.c_uint16),
            ("capturing_time", ct.c_uint64),
            ("layer", ct.c_uint8),
            ("raw", ct.c_ubyte * (
                size - ct.sizeof(ct.c_uint8) - ct.sizeof(ct.c_uint64) - 4*ct.sizeof(ct.c_uint16) - 2*ct.sizeof(ct.c_ubyte * 4)
            ))
        ]
    return CommonEvent


def handle_http2_event(ctx, data, size):
    """Handle HTTP/2 events.

    This function processes incoming HTTP/2 events by performing the following steps:
    1. Create a `CommonEvent` object from the raw event data.
    2. Parse the HTTP/2 message contained in the event by calling `parse_http2_message`.

    Args:
        ctx: The context associated with the event. This typically includes metadata and other
        relevant information for processing the event.
        data: The raw data buffer containing the HTTP/2 event.
        size: The size of the raw data buffer.
    """
    metrics.primitives_called.labels('handle_http2_event').inc()
    # Cast the event (read data from the buffer)
    event_obj = return_event_class_common(size)()
    ct.memmove(ct.addressof(event_obj), data, size)
    # Deep handling of the event
    parse_http2_message(event_obj, ctx, size)
    # Clean item to free memory
    del ctx, data, size


def handle_pfcp_event(ctx, data, size):
    """Handle PFCP events.

    This function processes incoming PFCP events by performing the following steps:
    1. Create a `CommonEvent` object from the raw event data.
    2. Parse the PFCP message contained in the event by calling `parse_pfcp_message`.

    Args:
        ctx: The context associated with the event. This typically includes metadata and other
        relevant information for processing the event.
        data: The raw data buffer containing the PFCP event.
        size: The size of the raw data buffer.
    """
    metrics.primitives_called.labels('handle_pfcp_event').inc()
    # Cast the event (read data from the buffer)
    event_obj = return_event_class_common(size)()
    ct.memmove(ct.addressof(event_obj), data, size)
    # Deep handling of the event
    parse_pfcp_message_bundle(event_obj, ctx, size)
    # Clean item to free memory
    del ctx, data, size, event_obj


def handle_ngap_event(ctx, data, size):
    """Handle NGAP events.

    This function processes incoming NGAP events by performing the following steps:
    1. Create a `CommonEvent` object from the raw event data.
    2. Parse the NGAP message contained in the event by calling `parse_ngap_message`.

    Args:
        ctx: The context associated with the event. This typically includes metadata and other
        relevant information for processing the event.
        data: The raw data buffer containing the NGAP event.
        size: The size of the raw data buffer.
    """
    metrics.primitives_called.labels('handle_ngap_event').inc()
    # Cast the event (read data from the buffer)
    event_obj = return_event_class_common(size)()
    ct.memmove(ct.addressof(event_obj), data, size)
    # Deep handling of the event
    parse_sctp_packet(event_obj, ctx, size)
    # Clean item to free memory
    del ctx, data, size, event_obj


def handle_gtpu_event(ctx, data, size):
    """Handle GTP-U events.

    This function processes incoming GTP-U events by performing the following steps:
    1. Create a `CommonEvent` object from the raw event data.
    2. Parse the GTP-U message contained in the event by calling `parse_gtpu_message`.

    Args:
        ctx: The context associated with the event. This typically includes metadata and other
        relevant information for processing the event.
        data: The raw data buffer containing the GTP-U event.
        size: The size of the raw data buffer.
    """
    metrics.primitives_called.labels('handle_gtpu_event').inc()
    # Cast the event (read data from the buffer)
    event_obj = return_event_class_common(size)()
    ct.memmove(ct.addressof(event_obj), data, size)
    # Deep handling of the event
    parse_gtpu_message(event_obj, ctx, size)
    # Clean item to free memory
    del ctx, data, size, event_obj


def handle_n6_ipv4_event(ctx, data, size):
    """Handle IPv4 events on the N6 interface.

    This function processes incoming NGAP events by performing the following steps:
    1. Create a `CommonEvent` object from the raw event data.
    2. Parse the IPv4 packet contained in the event by calling `parse_ipv4_packet`.

    Args:
        ctx: The context associated with the event. This typically includes metadata and other
        relevant information for processing the event.
        data: The raw data buffer containing the NGAP event.
        size: The size of the raw data buffer.
    """
    metrics.primitives_called.labels('handle_n6_ipv4_event').inc()
    # Cast the event (read data from the buffer)
    class Ipv4Event(ct.Structure):
        _fields_ = [
            ("ip_src", ct.c_ubyte * 4),
            ("ip_dest", ct.c_ubyte * 4),
            ("tot_len", ct.c_uint16),
            ("tos", ct.c_uint8),
            ("capturing_time", ct.c_uint64),
            ("layer", ct.c_uint8)
        ]
    event_obj = Ipv4Event()
    ct.memmove(ct.addressof(event_obj), data, size)
    # Deep handling of the event
    parse_ipv4_packet(event_obj, ctx, size)
    # Clean item to free memory
    del ctx, data, size, event_obj


# ============================
# eBPF events callbacks
# ============================
# Application layer
def http2_callback(ctx, data, size):
    """
HTTP/2 callback.
    """
    metrics.primitives_called.labels('http2_callback').inc()
    #while active_count() >= THREADS_MAX_NUM:
        # logger.warning(f"The total number of threads is equal to {active_count()}")
        # sleep(0.5)
    # reserve Thread(
    # reserve     target=handle_http2_event,
    # reserve     args=(ctx, data, size,),
    # reserve     name='handle_http2_event'
    # reserve ).start()
    events_handlers_tasks.submit(
        handle_http2_event,
        ctx, data, size
    ).add_done_callback(log_task_result)


def pfcp_callback(ctx, data, size):
    """
PFCP callback.
    """
    metrics.primitives_called.labels('pfcp_callback').inc()
    events_handlers_tasks.submit(
        handle_pfcp_event,
        ctx, data, size
    ).add_done_callback(log_task_result)


def ngap_callback(ctx, data, size):
    """
NGAP callback.
    """
    metrics.primitives_called.labels('ngap_callback').inc()
    events_handlers_tasks.submit(
        handle_ngap_event,
        ctx, data, size
    ).add_done_callback(log_task_result)


def gtpu_callback(ctx, data, size):
    """
GTP-U callback.
    """
    metrics.primitives_called.labels('gtpu_callback').inc()
    events_handlers_tasks.submit(
        handle_gtpu_event,
        ctx, data, size
    ).add_done_callback(log_task_result)


def n6_ipv4_callback(ctx, data, size):
    """
IPv4 on N6 callback.
    """
    metrics.primitives_called.labels('n6_ipv4_callback').inc()
    events_handlers_tasks.submit(
        handle_n6_ipv4_event,
        ctx, data, size
    ).add_done_callback(log_task_result)


class Ebpf():
    """Class for managing eBPF (Extended Berkeley Packet Filter) programs.

    This class provides functionalities to compile, prepare, attach, and detach eBPF programs for
    normal and N6 network interfaces. It supports TC (Traffic Control) and XDP (Express Data Path)
    programs, and allows for the use of either perf buffers or ring buffers.

    Attributes:
        monitor_https (bool): Indicates if HTTPS request monitoring via uprobe is enabled.
        use_ring_buffers (bool): Indicates if ring buffers are used.
        use_xdp (bool): Indicates if XDP programs are used.
        _ebpf_prog_prefix (str): Prefix for the names of compiled eBPF programs.
        ebpf_debug_level (int): Debug level for eBPF program compilation.
        ebpf_tc (BPF): Instance of the BPF object for TC programs.
        ebpf_fn_tc_ingress (BPF.Function): TC function for ingress packet processing.
        ebpf_fn_tc_egress (BPF.Function): TC function for egress packet processing.
        ebpf_xdp (BPF): Instance of the BPF object for XDP programs.
        ebpf_fn_xdp (BPF.Function): XDP function for packet processing.
        ebpf_tc_n6 (BPF): Instance of the BPF object for N6 TC programs.
        ebpf_fn_tc_ingress_n6 (BPF.Function): TC function for N6 ingress packet processing.
        ebpf_fn_tc_egress_n6 (BPF.Function): TC function for N6 egress packet processing.
        ebpf_xdp_n6 (BPF): Instance of the BPF object for N6 XDP programs.
        ebpf_fn_xdp_n6 (BPF.Function): XDP function for N6 packet processing.
        ebpf_uprobe_ssl (BPF): Instance of the BPF object for SSL uprobe programs.
        polling_buffers_started (bool): Indicates if polling for normal buffers has started.
        polling_buffers_started_n6 (bool): Indicates if polling for N6 buffers has started.
        _lock (Lock): Lock object for thread safety in normal interfaces.
        _lock_n6 (Lock): Lock object for thread safety in N6 interfaces.
    """
    __slots__ = [
        'monitor_https',
        'use_ring_buffers',
        'use_xdp',
        '_ebpf_prog_prefix',
        'ebpf_debug_level',
        'ebpf_tc',
        'ebpf_fn_tc_ingress',
        'ebpf_fn_tc_egress',
        'ebpf_xdp',
        'ebpf_fn_xdp',
        'ebpf_tc_n6',
        'ebpf_fn_tc_ingress_n6',
        'ebpf_fn_tc_egress_n6',
        'ebpf_xdp_n6',
        'ebpf_fn_xdp_n6',
        'ebpf_uprobe_ssl',
        'polling_buffers_started',
        'polling_buffers_started_n6',
        '_lock',
        '_lock_n6',
    ]

    def __init__(self):
        """Initializes the Ebpf object, setting default values for attributes and creating lock
        objects for thread safety.
        """
        self.polling_buffers_started = False
        self.polling_buffers_started_n6 = False
        self._lock = Lock()
        self._lock_n6 = Lock()

# ============================
# Compile and prepare TC and XDP eBPF programs
# ============================
    def prepare_programs(self, use_ring_buffers: bool, use_xdp: bool, monitor_https: bool=False, ebpf_debug_level: int=0):
        """Compiles and prepares eBPF programs based on the given parameters.

        Args:
            use_ring_buffers (bool): Whether to use ring buffers.
            use_xdp (bool): Whether to use XDP programs.
            monitor_https (bool, optional): Whether to monitor HTTPS requests via uprobe. Defaults to False.
            ebpf_debug_level (int, optional): Debug level for eBPF program compilation. Defaults to 0.
        """
        # Set variables
        self.monitor_https = monitor_https
        self.ebpf_debug_level = ebpf_debug_level
        self.use_xdp = use_xdp
        # Compile eBPF programs
        self._check_kernel_version(use_ring_buffers)
        self._compile_tc_for_normal_interfaces()
        self._compile_tc_for_n6_interfaces()
        if self.use_xdp:
            self._compile_xdp_for_normal_interfaces()
            self._compile_xdp_for_n6_interfaces()
        if self.monitor_https:
            self._compile_ebpf_uprobe_ssl()
        # Open buffers
        if self.use_ring_buffers:
            self._open_ring_buffers()
        else:
            self._open_perf_buffers()

# ============================
# eBPF programs attachment (public methods)
# ============================
    def attach_tc_xdp_to_pod_interface(self, pod: str, idx: int):
        """Attaches TC and/or XDP programs to a normal network interface of a pod.

        Args:
            pod (str): The name of the pod.
            idx (int): The index of the network interface.
        """
        # Create local variables
        if self.use_ring_buffers:
            b_tc = self.ebpf_tc
            fn_tc_ingress = self.ebpf_fn_tc_ingress
            fn_tc_egress = self.ebpf_fn_tc_egress
            if self.use_xdp:
                b_xdp = self.ebpf_xdp
                fn_xdp = self.ebpf_fn_xdp
        else:
            b_tc = copy(self.ebpf_tc)
            fn_tc_ingress = copy(self.ebpf_fn_tc_ingress)
            fn_tc_egress = copy(self.ebpf_fn_tc_egress)
            if self.use_xdp:
                b_xdp = copy(self.ebpf_xdp)
                fn_xdp = copy(self.ebpf_fn_xdp)

        # Add a clsact qdisc
        try:
            IPR.tc("add", "clsact", idx)
        except:
            logger.debug(f"clsact qdisc already exists for the pod {pod} interface {idx}")
        else:
            logger.debug(f"clsact qdisc created for the pod {pod} interface {idx}")
        # Attach the TC program to the egress layer
        try:
            IPR.tc(
                "add-filter", "bpf", idx, ":10",
                fd=fn_tc_egress.fd, name=fn_tc_egress.name,
                parent="ffff:fff3", classid=1, direct_action=True
            )
        except:
            logger.exception(f"failed to attach egress TC filter to the pod {pod} interface {idx}")
        else:
            logger.debug(f"egress TC filter attached to the pod {pod} interface {idx}")
            metrics.ebpf_programs_attached.labels('normal', 'tc', 'egress').inc()
        # Attach the XDP program to the ingress layer
        is_xdp_loaded = False
        device = socket.if_indextoname(idx)
        # if self.use_xdp:
        if self.use_xdp and 'veth' in device:
            try:
                # Try first to load XDP
                device = socket.if_indextoname(idx)
                b_xdp.attach_xdp(device, fn_xdp, 0)
            except:
                logger.exception(f"failed to load XDP program to the pod {pod} interface {idx}")
            else:
                is_xdp_loaded = True
                logger.debug(f"XDP program loaded to the pod {pod} interface {idx}")
                metrics.ebpf_programs_attached.labels('normal', 'xdp', 'ingress').inc()
                b_xdp.free_bcc_memory()
        # Attach the TC program to the ingress layer (if the XDP program has not been attached)
        if not is_xdp_loaded:
            try:
                IPR.tc(
                    "add-filter", "bpf", idx, ":10",
                    fd=fn_tc_ingress.fd, name=fn_tc_ingress.name,
                    parent="ffff:fff2", classid=1, direct_action=True
                )
            except:
                logger.exception(f"failed to attach ingress TC filter \
                    to the pod {pod} interface {idx}")
            else:
                logger.debug(f"ingress TC filter attached to the pod {pod} interface {idx}")
                metrics.ebpf_programs_attached.labels('normal', 'tc', 'ingress').inc()
                b_tc.free_bcc_memory()
        # Poll buffers
        if self.use_ring_buffers:
            # Start polling buffers
            with self._lock:
                if not self.polling_buffers_started:
                    self._start_polling_buffers()
                    self.polling_buffers_started = True
        else:
            # open and poll XDP perf buffers
            if self.use_xdp and is_xdp_loaded:
                # open XDP perf buffers
                b_xdp["http2_events"].open_perf_buffer(http2_callback, page_cnt=8192)
                b_xdp["pfcp_events"].open_perf_buffer(pfcp_callback, page_cnt=512)
                b_xdp["ngap_events"].open_perf_buffer(ngap_callback, page_cnt=512)
                b_xdp["gtpu_events"].open_perf_buffer(gtpu_callback, page_cnt=2048)
                # poll XDP perf buffers
                Thread(
                    target=self._poll_perf_buffer,
                    args=(b_xdp,),
                    name='_poll_perf_buffer b_xdp'
                ).start()
            # open and poll TC perf buffers
            # open
            b_tc["http2_events"].open_perf_buffer(http2_callback, page_cnt=8192)
            b_tc["pfcp_events"].open_perf_buffer(pfcp_callback, page_cnt=512)
            b_tc["ngap_events"].open_perf_buffer(ngap_callback, page_cnt=512)
            b_tc["gtpu_events"].open_perf_buffer(gtpu_callback, page_cnt=2048)
            # poll
            while 1:
                b_tc.perf_buffer_poll()

    def attach_tc_xdp_to_pod_n6_interface(self, pod: str, idx: int):
        """Attaches TC and/or XDP programs to an N6 network interface of the UPF pod.

        Args:
            pod (str): The name of the pod.
            idx (int): The index of the network interface.
        """
        # Create local variables
        if self.use_ring_buffers:
            b_tc_n6 = self.ebpf_tc_n6
            fn_tc_ingress_n6 = self.ebpf_fn_tc_ingress_n6
            fn_tc_egress_n6 = self.ebpf_fn_tc_egress_n6
            if self.use_xdp:
                b_xdp_n6 = self.ebpf_xdp_n6
                fn_xdp_n6 = self.ebpf_fn_xdp_n6
        else:
            b_tc_n6 = copy(self.ebpf_tc_n6)
            fn_tc_ingress_n6 = copy(self.ebpf_fn_tc_ingress_n6)
            fn_tc_egress_n6 = copy(self.ebpf_fn_tc_egress_n6)
            if self.use_xdp:
                b_xdp_n6 = copy(self.ebpf_xdp_n6)
                fn_xdp_n6 = copy(self.ebpf_fn_xdp_n6)

        # Add a clsact qdisc
        try:
            IPR.tc("add", "clsact", idx)
        except:
            logger.debug(f"clsact qdisc already exists for the pod {pod} interface {idx}")
        else:
            logger.debug(f"clsact qdisc created for the pod {pod} interface {idx}")
        # Attach the TC program to the egress layer
        try:
            IPR.tc(
                "add-filter", "bpf", idx, ":60",
                fd=fn_tc_egress_n6.fd, name=fn_tc_egress_n6.name,
                parent="ffff:fff3", classid=1, direct_action=True
            )
        except:
            logger.exception(f"failed to attach N6 ingress TC filter to the pod {pod} interface {idx}")
        else:
            logger.debug(f"N6 ingress TC filter attached to the pod {pod} interface {idx}")
            metrics.ebpf_programs_attached.labels('n6', 'tc', 'ingress').inc()
        # Attach the XDP program to the ingress layer
        is_xdp_loaded = False
        device = socket.if_indextoname(idx)
        # if self.use_xdp:
        if self.use_xdp and 'veth' in device:
            try:
                # Try first to load XDP
                device = socket.if_indextoname(idx)
                b_xdp_n6.attach_xdp(device, fn_xdp_n6, 0)
            except:
                logger.exception(f"failed to load N6 XDP program to the pod {pod} interface {idx}")
            else:
                is_xdp_loaded = True
                logger.debug(f"N6 XDP program loaded to the pod {pod} interface {idx}")
                metrics.ebpf_programs_attached.labels('n6', 'xdp', 'ingress').inc()
                b_xdp_n6.free_bcc_memory()
        # Attach the TC program to the ingress layer (if the XDP program has not been attached)
        if not is_xdp_loaded:
            try:
                IPR.tc(
                    "add-filter", "bpf", idx, ":60",
                    fd=fn_tc_ingress_n6.fd, name=fn_tc_ingress_n6.name,
                    parent="ffff:fff2", classid=1, direct_action=True
                )
            except:
                logger.exception(f"failed to attach N6 egress TC filter \
                    to the pod {pod} interface {idx}")
            else:
                logger.debug(f"N6 egress TC filter attached to the pod {pod} interface {idx}")
                metrics.ebpf_programs_attached.labels('n6', 'tc', 'egress').inc()
                b_tc_n6.free_bcc_memory()
        # Poll buffers
        if self.use_ring_buffers:
            # Start polling buffers
            with self._lock_n6:
                if not self.polling_buffers_started_n6:
                    self._start_polling_buffers_n6()
                    self.polling_buffers_started_n6 = True
        else:
            # open and poll XDP perf buffers
            if self.use_xdp and is_xdp_loaded:
                # open XDP perf buffers
                b_xdp_n6["ipv4_events"].open_perf_buffer(n6_ipv4_callback, page_cnt=2048)
                # poll XDP perf buffers
                Thread(
                    target=self._poll_perf_buffer,
                    args=(b_xdp_n6,),
                    name='_poll_perf_buffer b_xdp_n6'
                ).start()
            # open and poll TC perf buffers
            # open
            b_tc_n6["ipv4_events"].open_perf_buffer(n6_ipv4_callback, page_cnt=2048)
            # poll
            while 1:
                b_tc_n6.perf_buffer_poll()

    def detach_tc_xdp_from_pod_interface(self, pod: str, idx: int):
        """
        Detaches TC and/or XDP programs from all types of network interfaces of a pod (N6 or not).

        Args:
            pod (str): The name of the pod.
            idx (int): The index of the network interface.
        """
        # Delete the clsact qdisc
        try:
            IPR.tc("del", "clsact", idx)
        except:
            logger.debug(f"Cannot delete the clsact qdisc for the pod {pod} interface {idx}")
        else:
            logger.debug(f"clsact qdisc deleted for the pod {pod} interface {idx}")
        # Remove XDP programs (if XDP is used)
        if self.use_xdp:
            # Remove XDP program
            try:
                device = socket.if_indextoname(idx)
                self.ebpf_xdp.remove_xdp(device)
            except:
                logger.debug(f"Cannot delete remove the XDP program for the pod {pod} interface {idx}")
            else:
                logger.debug(f"XDP program removed for the pod {pod} interface {idx} device {device}")
            # Remove N6 XDP program
            try:
                device = socket.if_indextoname(idx)
                self.ebpf_xdp_n6.remove_xdp(device)
            except:
                logger.debug(f"Cannot delete remove the N6 XDP program \
                    for the pod {pod} interface {idx}")
            else:
                logger.debug(f"N6 XDP program removed \
                    for the pod {pod} interface {idx} device {device}")

# ============================
# eBPF programs compilation
# ============================
    def _check_kernel_version(self, use_ring_buffers: bool):
        """
        Checks if the kernel version is sufficient for using ring buffers.
        Note that minimum kernel version for supporting ring buffers is 5.8.0.

        Args:
            use_ring_buffers (bool): Whether ring buffers are requested.

        Returns:
            bool: Whether ring buffers can be used.
        """
        if use_ring_buffers:
            ring_minimal_kernel_version = (5, 8, 0)
            node_kernel_version = release()
            node_kernel_version = node_kernel_version.split('-', 1)[0]
            node_kernel_version = node_kernel_version.split('.')
            node_kernel_version = (int(x) for x in node_kernel_version)
            node_kernel_version = tuple(node_kernel_version)
            use_ring_buffers = bool(node_kernel_version >= ring_minimal_kernel_version)
        if use_ring_buffers:
            self._ebpf_prog_prefix = 'ring_'
            logger.info('Ring buffers will be used')
        else:
            self._ebpf_prog_prefix = 'perf_'
            logger.info('Perf buffers will be used')
        self.use_ring_buffers = use_ring_buffers
        return use_ring_buffers

    def _compile_tc_for_normal_interfaces(self):
        """Compiles TC filters for normal interfaces.
        """
        self.ebpf_tc = BPF(src_file=f'ebpf/{self._ebpf_prog_prefix}ebpf_program_tc.c',
                           debug=self.ebpf_debug_level)
        self.ebpf_fn_tc_ingress = self.ebpf_tc.load_func("trafic_handler_ingress", BPF.SCHED_CLS)
        self.ebpf_fn_tc_egress = self.ebpf_tc.load_func("trafic_handler_egress", BPF.SCHED_CLS)
        logger.debug("TC eBPF program for normal interfaces compiled")
        # Free compilation memory
        self.ebpf_tc.free_bcc_memory()

    def _compile_xdp_for_normal_interfaces(self):
        """Compiles XDP programs for normal interfaces.
        """
        self.ebpf_xdp = BPF(src_file=f'ebpf/{self._ebpf_prog_prefix}ebpf_program_xdp.c',
                            debug=self.ebpf_debug_level)
        self.ebpf_fn_xdp = self.ebpf_xdp.load_func("trafic_handler", BPF.XDP)
        logger.debug("XDP eBPF program for normal interfaces compiled")
        # Free compilation memory
        self.ebpf_xdp.free_bcc_memory()

    def _compile_tc_for_n6_interfaces(self):
        """Compiles TC filters for n6 interfaces.
        """
        self.ebpf_tc_n6 = BPF(src_file=f'ebpf/{self._ebpf_prog_prefix}ebpf_program_tc_n6.c',
                              debug=self.ebpf_debug_level)
        self.ebpf_fn_tc_ingress_n6 = self.ebpf_tc_n6.load_func("trafic_handler_ingress",
                                                               BPF.SCHED_CLS)
        self.ebpf_fn_tc_egress_n6 = self.ebpf_tc_n6.load_func("trafic_handler_egress",
                                                              BPF.SCHED_CLS)
        logger.debug("TC eBPF program for N6 interface compiled")
        # Free compilation memory
        self.ebpf_tc_n6.free_bcc_memory()

    def _compile_xdp_for_n6_interfaces(self):
        """Compiles XDP programs for n6 interfaces.
        """
        self.ebpf_xdp_n6 = BPF(src_file=f'ebpf/{self._ebpf_prog_prefix}ebpf_program_xdp_n6.c',
                               debug=self.ebpf_debug_level)
        self.ebpf_fn_xdp_n6 = self.ebpf_xdp_n6.load_func("trafic_handler", BPF.XDP)
        logger.debug("XDP eBPF program for N6 interface compiled")
        # Free compilation memory
        self.ebpf_xdp_n6.free_bcc_memory()

    def _compile_ebpf_uprobe_ssl(self):
        """Compiles uprobe eBPF program for monitoring HTTPS.

        Note: This method is currently a placeholder and does not compile the uprobe SSL program.
        """

        """
        self.ebpf_uprobe_ssl = BPF(src_file=f'ebpf/{self._ebpf_prog_prefix}ebpf_program_uprobe_ssl.c',
                                    debug=self.ebpf_debug_level)
        logger.debug("Uprobe eBPF program for SSL libraries compiled")
        self.ebpf_uprobe_ssl["perf_SSL_rw"].open_perf_buffer(print_event_rw)
        self.ebpf_uprobe_ssl.free_bcc_memory()
        """
        self.ebpf_uprobe_ssl = None

# ============================
# eBPF buffers management
# ============================
    def _open_perf_buffers(self):
        """Opens perf buffers for TC and XDP programs.
        """
        # TC
        self.ebpf_tc["http2_events"].open_perf_buffer(http2_callback, page_cnt=8192)
        self.ebpf_tc["pfcp_events"].open_perf_buffer(pfcp_callback, page_cnt=512)
        self.ebpf_tc["ngap_events"].open_perf_buffer(ngap_callback, page_cnt=512)
        self.ebpf_tc["gtpu_events"].open_perf_buffer(gtpu_callback, page_cnt=2048)
        # TC N6
        self.ebpf_tc_n6["ipv4_events"].open_perf_buffer(n6_ipv4_callback, page_cnt=2048)
        if self.use_xdp:
            # XDP
            self.ebpf_xdp["http2_events"].open_perf_buffer(http2_callback, page_cnt=8192)
            self.ebpf_xdp["pfcp_events"].open_perf_buffer(pfcp_callback, page_cnt=512)
            self.ebpf_xdp["ngap_events"].open_perf_buffer(ngap_callback, page_cnt=512)
            self.ebpf_xdp["gtpu_events"].open_perf_buffer(gtpu_callback, page_cnt=2048)
            # XDP N6
            self.ebpf_xdp_n6["ipv4_events"].open_perf_buffer(n6_ipv4_callback, page_cnt=2048)

    def _open_ring_buffers(self):
        """Opens ring buffers for TC and XDP programs.
        """
        # TC
        self.ebpf_tc["http2_events"].open_ring_buffer(http2_callback)
        self.ebpf_tc["pfcp_events"].open_ring_buffer(pfcp_callback)
        self.ebpf_tc["ngap_events"].open_ring_buffer(ngap_callback)
        self.ebpf_tc["gtpu_events"].open_ring_buffer(gtpu_callback)
        # TC N6
        self.ebpf_tc_n6["ipv4_events"].open_ring_buffer(n6_ipv4_callback)
        if self.use_xdp:
            # XDP
            self.ebpf_xdp["http2_events"].open_ring_buffer(http2_callback)
            self.ebpf_xdp["pfcp_events"].open_ring_buffer(pfcp_callback)
            self.ebpf_xdp["ngap_events"].open_ring_buffer(ngap_callback)
            self.ebpf_xdp["gtpu_events"].open_ring_buffer(gtpu_callback)
            # XDP N6
            self.ebpf_xdp_n6["ipv4_events"].open_ring_buffer(n6_ipv4_callback)

    @staticmethod
    def _poll_perf_buffer(ebpf_program):
        """Polls a perf buffer.

        Args:
            ebpf_program (BPF): The BPF object with the perf buffer to poll.
        """
        while 1:
            ebpf_program.perf_buffer_poll()

    @staticmethod
    def _poll_ring_buffer(ebpf_program):
        """Polls a ring buffer.

        Args:
            ebpf_program (BPF): The BPF object with the ring buffer to poll.
        """
        while 1:
            ebpf_program.ring_buffer_consume()
            sleep(0.5)

    def _start_polling_buffers(self):
        """Starts polling buffers, in a new thread, for normal network interfaces based on buffer type.
        """
        if self.use_ring_buffers:
            Thread(
                target=self._poll_ring_buffer,
                args=(self.ebpf_tc,),
                name='_poll_ring_buffer ebpf_tc'
            ).start()
            if self.use_xdp:
                Thread(
                    target=self._poll_ring_buffer,
                    args=(self.ebpf_xdp,),
                    name='_poll_ring_buffer ebpf_xdp'
                ).start()

    def _start_polling_buffers_n6(self):
        """Starts polling buffers, in a new thread, for N6 network interfaces based on buffer type.
        """
        if self.use_ring_buffers:
            Thread(
                target=self._poll_ring_buffer,
                args=(self.ebpf_tc_n6,),
                name='_poll_ring_buffer ebpf_tc_n6'
            ).start()
            if self.use_xdp:
                Thread(
                    target=self._poll_ring_buffer,
                    args=(self.ebpf_xdp_n6,),
                    name='_poll_ring_buffer ebpf_xdp_n6'
                ).start()


# Instantiate the Ebpf class
ebpf_instance = Ebpf()
