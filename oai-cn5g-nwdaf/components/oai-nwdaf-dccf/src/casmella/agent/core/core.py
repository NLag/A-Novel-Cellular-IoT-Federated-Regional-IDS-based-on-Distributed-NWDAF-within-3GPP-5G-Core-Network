"""Controller's core module.

Controlling changes on the 'topology' and 'hooklist' custom resources.
"""
# standard
from threading import Lock, Thread, active_count
from concurrent.futures import ThreadPoolExecutor
from time import sleep
import signal
from os import kill, getpid
# third-pary
# internal
from . import cfg, metrics
from .custom_types import ThreadSafeDict
from .k8s import get_topology_resource, get_hooklist_resource, patch_custom_resource
from ebpf.ebpf import ebpf_instance

logger = cfg.logging

for i in logger.Logger.manager.loggerDict:
    logger.getLogger(i).setLevel(cfg.logging.ERROR)

# Initialize global variables
TOPOLOGY_CONTROL_LOOP_CONDITION = True
N6_INTERFACE_NAMES = ()
MY_NODE_NAME = cfg.MY_NODE_NAME
count_attached_programs = ThreadSafeDict()
hooks_handlers_tasks = cfg.hooks_handlers_tasks
log_task_result = cfg.log_task_result


def debug_operation_time_streams_iteration():
    """Logs the length of various protocol response time streams and the number of active threads.

    This function has to be used only for debugging purposes.
    It collects and logs the length of different response time streams for various protocols
    such as HTTP/2, PFCP, NGAP, NAS, and GTP. It also logs the number of active threads
    currently running in the system.
    """
    import threading
    import sys
    import gc
    from protocols import http2, pfcp, ngap, nas, gtp
    log_debug = {
        'http2_response_time': len(http2.http2_response_time),
        'decoders': len(http2.decoders),
        'pfcp_response_time_stream': len(pfcp.pfcp_response_time_stream),
        'ngap_response_time_stream': len(ngap.ngap_response_time_stream),
        'nas_registration_queue': len(nas.nas_registration_queue),
        'gtpu_forwarding_time': len(gtp.gtpu_forwarding_time),
    }
    logger.debug(f"Dicts: {log_debug}")
    # Debug the number of running threads
    logger.warning(f"Threads: The total number of threads is equal to {active_count()}")


def debug_operation_time_streams():
    """Continuously logs the lengths of various protocol response time streams and the number of active threads.

    This function runs an infinite loop that repeatedly calls `debug_operation_time_streams_iteration`
    every 60 seconds.

    The function logs this information every 60 seconds, making it useful for debugging purposes.
    """
    while 1:
        debug_operation_time_streams_iteration()
        sleep(60)


def handle_one_pod_interface_added(pod_name: str, interface_name: str, idx: int):
    """Handle a single network interface of an added Pod.

    This function manages the network interface when a new Pod is added.
    It performs the following steps:

    1. Checks if there is already an attached program to the specified interface.
    2. If there is an attached program, increments the count for that interface \
    (This applies for example when multiple MACVLAN/IPVLAN interfaces share the same master \
    interface).
        * If the interface is already being tracked (`idx` is in `count_attached_programs`), \
        increments the count.
    3. If there is no attached program, attaches the appropriate filter to the interface based on \
    its type. (This applies, for instance, to veth peers or MACVLAN/IPVLAN interfaces that utilize \
    a master interface without any eBPF program attached).
        * If the interface is not being tracked:
        * Adds it to `count_attached_programs` with a count of 1.
        * Attaches the appropriate filter using eBPF based on the interface type.
            * For N6 interfaces (indicated by `interface_name` being in `N6_INTERFACE_NAMES`), \
            attaches an N6 IPv4 filter.
            * For other interfaces, attaches filters for protocols like HTTP2, NGAP, PFCP, \
            and GTP-U.

    Args:
        pod_name (str): The name of the Pod being handled.
        interface_name (str): The name of the network interface in the Pod being added.
        idx (int): The index of the network interface on the host.
    """
    # Check if there is an already attached program to this interface
    if idx in count_attached_programs:
        count_attached_programs[idx] += 1
    else:     # attach filter
        count_attached_programs[idx] = 1
        # attach tc program
        if interface_name in N6_INTERFACE_NAMES:
            # attach (N6 IPv4) filter
            ebpf_instance.attach_tc_xdp_to_pod_n6_interface(pod_name, idx)
        else:
            # attach (HTTP2, NGAP, PFCP, GTP-U) filter
            ebpf_instance.attach_tc_xdp_to_pod_interface(pod_name, idx)


def handle_one_pod_interface_deleted(pod_name: str, interface_name: str, idx: int):
    """Handle a single network interface of a deleted Pod.

    This function manages the network interface when a Pod is deleted.
    It performs the following steps:

    1. Updates the count of attached programs for the specified interface.
    2. If the interface count reaches zero (i.e., no Pod's interfaces are using this interface),
    detaches all eBPF programs from that interface.
    3. Clears Prometheus metrics associated with the Pod.

    Args:
        pod_name (str): The name of the Pod being handled.
        interface_name (str): The name of the network interface in the Pod being deleted.
        idx (int): The index of the network interface on the host.
    """
    # Update the count of attached program to this interface
    try:
        count_attached_programs[idx] -= 1
    except KeyError:
        logger.exception(f"Network interface ({interface_name}, {idx}) \
            has been marked DELETED but does not exist")
    # Check if idx will no more be observed
    if count_attached_programs[idx] == 0:
        # Detach all eBPF programs
        ebpf_instance.detach_tc_xdp_from_pod_interface(pod_name, idx)
    # Clear Prometheus metrics
    metrics.clear_prometheus_metrics_for_pod(pod_name)


def handle_one_pod_filesystem(pod_name: str, filesystem_path: str):
    """Handle a single filesystem of an added Pod.

    This function is designed to manage libraries within the filesystem of a newly added Pod.
    It currently focuses on handling instances of the `libssl.so` library.
    The function performs the following steps:

    1. Searches for instances of `libssl.so` within the specified `filesystem_path` of the Pod.
    2. Attach a uprobe eBPF Program to the the libraries found.

    Note:
        Currently, the functionality to attach uprobe eBPF programs is not used.
        The code is prepared to attach an eBPF program (e.g., `ebpf_instance.attach_openssl`)
        to the located libraries but this is commented out.

    Args:
        pod_name (str): The name of the Pod being handled.
        filesystem_path (str): The path to the filesystem where the library is located.
    """
    # Handling only openssl library for instance
    for lib_path in cfg.find_file_folder("libssl.so", filesystem_path):
        # ebpf_instance.attach_openssl(pod_name, lib_path)
        logger.debug(f"Uprobe not atatched to ({pod_name}, {lib_path}) \
            (Not implemented yet)")


def handle_pod_networking_changes(_status: str, pod_name: str, interfaces_dict: dict) -> tuple:
    """Track and handle changes in networking hooks for a Pod.

    This function manages networking hooks when the status of a Pod changes.
    It performs different actions based on the Pod's status:

    * **Added or Cleaned Pods**: Processes interfaces to handle new or cleaned Pods by invoking \
    `handle_one_pod_interface_added` for each interface.
        * Sets `patch_needed` to `True`.
        * For each interface in `interfaces_dict`, submits a task to handle the interface addition or cleaning.
        * Logs a warning if the interface index is `None`.
    * **Deleted Pods**: Processes interfaces to handle Pod deletions by invoking \
    `handle_one_pod_interface_deleted` for each interface.
        * Sets `patch_needed` to `True`.
        * For each interface in `interfaces_dict`, submits a task to handle the interface deletion.

    Args:
        _status (str): The status of the Pod. Can be 'ADDED', 'CLEANED', or 'DELETED'.
        pod_name (str): The name of the Pod whose networking changes are being handled.
        interfaces_dict (dict): A dictionary where keys are interface names and values are their corresponding indices.

    Returns:
        tuple: A tuple cotaining:
            * `pod_interface_for_this_pod` (dict or None): A dictionary indicating the status of \
            handling for the Pod's interfaces, or `None` if no interfaces were handled.
            * `patch_needed` (bool): A boolean indicating whether a patch to the custom resource \
            is needed.
    """
    pod_interface_for_this_pod = None
    patch_needed = False
    # Handle added Pods
    if _status in ('ADDED', 'CLEANED'):
        if not interfaces_dict:
            # Controller hasn't discovered interfaces yet — leave entry untouched
            # so the controller can retry and populate content later
            logger.debug(f"Pod {pod_name} has no interfaces yet, skipping until controller retries")
            return None, False
        patch_needed = True
        for interface_name, idx in interfaces_dict.items():
            if idx:
                hooks_handlers_tasks.submit(
                    handle_one_pod_interface_added,
                    pod_name, interface_name, idx
                ).add_done_callback(log_task_result)
                pod_interface_for_this_pod = {'status': 'HANDLED'}
            else:
                logger.warning("index for the interface {interface_name} \
                    in the Pod {pod_name} is None")
                pod_interface_for_this_pod = {'status': 'HANDLED'}
    # Handle deleted Pods
    if _status == 'DELETED':
        patch_needed = True
        for interface_name, idx in interfaces_dict.items():
            hooks_handlers_tasks.submit(
                handle_one_pod_interface_deleted,
                pod_name, interface_name, idx
            ).add_done_callback(log_task_result)
    return pod_interface_for_this_pod, patch_needed


def handle_pod_ssl_changes(_status: str, pod_name: str, ssllib_list: list) -> tuple:
    """Track and handle changes in SSL hooks for a Pod.

    This function manages networking hooks when the status of a Pod changes.
    It performs different actions based on the Pod's status:

    * **Added or Cleaned Pods**: Processes the list of SSL libraries to handle new or cleaned
    Pods by invoking `handle_one_pod_filesystem` for each filesystem path.
        * Sets `patch_needed` to `True`.
        * For each filesystem path in `ssllib_list`, submits a task to handle the SSL library.
        * Logs a warning if the filesystem path is `None`.
        * Sets `pod_ssl_lib_path_for_this_pod` to `{'status': 'HANDLED'}` after handling or
        `{'status': 'FAILED'}` if the filesystem path is `None`.
    * **Deleted Pods**: Marks the SSL library paths as needing to be handled for deletion.
        * Sets `patch_needed` to `True`.
        * Sets `pod_ssl_lib_path_for_this_pod` to `None`.

    Args:
        _status (str): The status of the Pod. Can be 'ADDED', 'CLEANED', or 'DELETED'.
        pod_name (str): The name of the Pod whose SSL changes are being handled.
        ssllib_list (list): A list of filesystem paths to SSL libraries in the Pod.

    Returns:
        tuple:
            * `pod_ssl_lib_path_for_this_pod` (dict or None): A dictionary indicating the status of
            handling for the Pod's SSL libraries, or `None` if the status is 'DELETED'.
            * `patch_needed` (bool): A boolean indicating whether a patch to the custom resource
            is needed.
    """
    patch_needed = False
    # Handle added Pods
    if _status in ('ADDED', 'CLEANED'):
        patch_needed = True
        for filesystem_path in ssllib_list:
            if filesystem_path:
                hooks_handlers_tasks.submit(
                    handle_one_pod_filesystem,
                    pod_name, filesystem_path
                ).add_done_callback(log_task_result)
                pod_ssl_lib_path_for_this_pod = {'status': 'HANDLED'}
            else:
                logger.warning("filesystem_path in the Pod {pod_name} is None")
                pod_ssl_lib_path_for_this_pod = {'status': 'FAILED'}
    # Handle deleted Pods
    elif _status == 'DELETED':
        patch_needed = True
        pod_ssl_lib_path_for_this_pod = None
    return pod_ssl_lib_path_for_this_pod, patch_needed


def track_changes_on_hooks(hooks_dict: dict):
    """Track changes on hooks.

    This function iterates over a dictionary of hooks to identify and yield changes based on the
    hook's status, content, and node. It yields tuples indicating the status, key, and content of
    each hook that requires action.

    Args:
        hooks_dict (dict): A dictionary where keys are hook identifiers and values are dictionaries
        containing hook information. Each value dictionary should contain the keys 'status',
        'content', and 'node'.

    Yields:
        tuple: A tuple containing:
            * `status` (str): The status of the hook, e.g., 'ADDED', 'DELETED', 'INCOMPLETE'.
            * `key` (str): The identifier key of the hook.
            * `content` (Any): The content associated with the hook, e.g., network interfaces or
            Containers' filesystem paths.
    """
    for _k, _v in hooks_dict.items():
        if not {'status', 'content', 'node'}.issubset(_v.keys()):
            yield 'INCOMPLETE', _k, _v.get('node', 'uknown')
            continue
        if _v['node'] == MY_NODE_NAME and _v['status'] not in ('HANDLED', 'FAILED', 'INCOMPLETE'):
            # e.g. for network interfaces 'ADDED', 'pod1', {'eth0': 10}
            # e.g. for ssl lib paths 'DELETED', 'pod1', ['fs1_path', 'fs2_path']
            yield _v['status'], _k, _v['content']


def topology_control_loop_iteration():
    """Perform a single iteration of the topology control loop.

    This function handles the following tasks:

    1. Updates the IP address information and retrieves the latest Pod information.
        * Initializes `patch_needed` to track if any changes require patching the custom resources.
        * Updates `cfg.ip_address_infos` and `cfg.pod_infos` by calling `get_topology_resource`.
    2. Retrieves the current state of network interfaces and SSL library paths from hooklist \
    resources.
        * Retrieves `pod_interfaces` and `pod_ssl_lib_paths` by calling `get_hooklist_resource`.
    3. Tracks and processes changes in network interfaces and SSL libraries.
        * Iterates over the results from `track_changes_on_hooks` applied to `pod_interfaces`.
        * If the hook status is 'INCOMPLETE', marks the hook as incomplete in `hooks_to_patch`.
        * Otherwise, processes the hook using `handle_pod_networking_changes` and updates \
        `patch_needed` accordingly.
        * If `cfg.MONITOR_HTTPS` is enabled, iterates over the results from `track_changes_on_hooks` \
        applied to `pod_ssl_lib_paths`.
        * If the hook status is 'INCOMPLETE', marks the hook as incomplete in `hooks_to_patch`.
        * Otherwise, processes the hook using `handle_pod_ssl_changes` and updates `patch_needed` \
        accordingly.
    4. Updates the status of hooks and patches the custom resources if needed.
        * Calls `patch_custom_resource` to update the hooklist resources `patch_needed` is true.
    """
    # Initialize patch_needed
    patch_needed = False
    # Update ipAddressInfos and get the new podInfos
    cfg.ip_address_infos, cfg.pod_infos  = get_topology_resource("casmella-topology")
    pod_interfaces, pod_ssl_lib_paths = get_hooklist_resource("casmella-hooklist")

    # Initialize status of hooks
    hooks_to_patch = {
        'podInterfaces': {},
        'podSslLibPaths': {},
    }

    # Handle changes on network interfaces
    for _status, pod_name, interfaces_dict in track_changes_on_hooks(pod_interfaces):
        if _status == 'INCOMPLETE':
            hooks_to_patch['podInterfaces'][pod_name] = {
                'status': 'INCOMPLETE',
                'content': (),
                'node': interfaces_dict
            }
        else:
            hooks_to_patch['podInterfaces'][pod_name], _patch_needed = \
                handle_pod_networking_changes(_status, pod_name, interfaces_dict)
            patch_needed = patch_needed or _patch_needed

    # Handle changes on ssl libs
    if cfg.MONITOR_HTTPS:
        for _status, pod_name, ssllib_list in track_changes_on_hooks(pod_ssl_lib_paths):
            if _status == 'INCOMPLETE':
                hooks_to_patch['podSslLibPaths:'][pod_name] = {
                    'status': 'INCOMPLETE',
                    'content': (),
                    'node': interfaces_dict
                }
            else:
                hooks_to_patch['podSslLibPaths:'][pod_name], _patch_needed = \
                    handle_pod_ssl_changes(_status, pod_name, ssllib_list)
                patch_needed = patch_needed or _patch_needed

    if patch_needed:
        # Update status of hooks
        patch_custom_resource('hooklist', 'hooklists', hooks_to_patch)


def topology_control_loop():
    """Execute the topology control loop.

    This function runs in a loop while the global condition `TOPOLOGY_CONTROL_LOOP_CONDITION` is True.
    It performs the following tasks:

    1. Calls `topology_control_loop_iteration` to process the current state of the topology.
    2. Sleeps for a short period (1 second) before the next iteration.

    If an exception occurs or the loop exits, the function sends a SIGTERM signal to terminate
    the process gracefully.
    """
    try:
        while TOPOLOGY_CONTROL_LOOP_CONDITION:
            topology_control_loop_iteration()
            # Sleep before the next iteration
            sleep(1)
    finally:
        # Send SIGTERM signal to itself
        logger.warning("The topology_control_loop will send SIGTERM signal")
        kill(getpid(), signal.SIGTERM)


def cleanup_all():
    """Clean up function.

    Perform cleanup operations for pod interfaces and SSL library paths.

    This function is designed to clean up resources associated with pod interfaces and SSL library paths.
    It performs the following steps:

    1. Initializes a dictionary (`hooks_to_patch`) to store the status of hooks to be patched.
    2. Retrieves `pod_interfaces` and `pod_ssl_lib_paths` from the hook list resource.
        * It calls the `get_hooklist_resource` function.
    3. Logs the current state of `pod_interfaces` for debugging purposes.
    4. Iterates over the `pod_interfaces` to clean up interfaces on the current node.
    5. For each valid pod interface, submits a task to detach eBPF programs and updates the status \
    to 'CLEANED'.
    6. Patches the custom resource with the updated hook statuses.

    The function ensures that incomplete or invalid pod interface information is logged and skipped,
    and it submits tasks to detach eBPF programs.
    """
    logger.debug("Running the cleanup function")

    # Initialize status of hooks
    hooks_to_patch = {
        'podInterfaces': {},
        'podSslLibPaths': {},
    }

    pod_interfaces, pod_ssl_lib_paths = get_hooklist_resource("casmella-hooklist")

    # Clean item to free memory
    del pod_ssl_lib_paths

    logger.debug(f"pod_interfaces: {pod_interfaces}")

    for pod_name, _pod_dict in pod_interfaces.items():
        if not {'status', 'content', 'node'}.issubset(_pod_dict.keys()):
            logger.warning(f"{pod_name} cannot be cleaned because its information incomplete")
            continue
        if _pod_dict['node'] == MY_NODE_NAME and _pod_dict['status'] not in ('INCOMPLETE'):
            hooks_to_patch['podInterfaces'][pod_name] = {'status': 'CLEANED'}
            for _interface, idx in _pod_dict['content'].items():
                hooks_handlers_tasks.submit(
                    ebpf_instance.detach_tc_xdp_from_pod_interface,
                    pod_name, idx
                ).add_done_callback(log_task_result)

    # Update status of hooks
    patch_custom_resource('hooklist', 'hooklists', hooks_to_patch)


def sigterm_handler(signum: int, frame):
    """Handles the SIGTERM signal for graceful shutdown and cleanup.

    This function is designed to handle the SIGTERM signal, allowing for a graceful shutdown of the application.
    When a SIGTERM signal is received (by the application, the orchetsration platform or the hosting
    node), the function performs the following steps:

    1. Logs a warning message indicating that the SIGTERM signal was received.
    2. Sets a global condition to stop the topology control loop.
        * It sets the `TOPOLOGY_CONTROL_LOOP_CONDITION` global variable to False.
    3. Waits for 3 seconds to allow any ongoing operations to finish.
    4. Calls a cleanup function to perform necessary cleanup operations.
    5. Logs a debug message indicating that a SIGKILL signal will be sent.
    6. Sends a SIGKILL signal to terminate the Agent's process immediately.

    Args:
        signum (int): The signal number.
        frame (frame object): The current stack frame.
    """
    logger.warning(f"SIGTERM signal received ({signum}, {frame})")
    # Stop the topology_control_loop
    global TOPOLOGY_CONTROL_LOOP_CONDITION
    TOPOLOGY_CONTROL_LOOP_CONDITION = False
    sleep(3)
    cleanup_all()
    logger.debug("SIGKILL signal will be sent")
    kill(getpid(), signal.SIGKILL)


if __name__ == '__main__':
    logger.error("This module cannot be run as main")
