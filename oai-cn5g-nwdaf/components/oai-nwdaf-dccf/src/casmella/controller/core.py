"""
Controller's core module
"""
# standard
import logging
import re
from threading import Thread, Lock
import json
from time import sleep
# third-party
from kubernetes import client, config, watch
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream
# internal
import metrics


# Set logging configuration
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(threadName)s %(filename)s:%(lineno)d %(levelname)-10s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
for i in logging.Logger.manager.loggerDict:
    logging.getLogger(i).setLevel(logging.ERROR)
logger = logging

# Initialize global variables
CLUSTER_NAME = 'minikube'
MONITOR_HTTPS = None
EXCLUDED_INTERFACES = ()
K8S_RESOURCES_LOCK_OBJECTS = {
    'topology': Lock(),
    'hooklist': Lock(),
}

# Load K8s configuration and APIs
config.load_incluster_config()
logger.debug("Kubernetes configuration loaded...")
custom_api_instance = client.CustomObjectsApi()
apps_api_instance = client.AppsV1Api()
core_api_instance = client.CoreV1Api()
# all available methods on
# https://raw.githubusercontent.com/kubernetes-client/python/master/kubernetes/docs/CoreV1Api.md


def initialize_custom_resource(kind: str, singular: str, plural: str, spec: dict):
    """Initialize a Custom Resource (CR) used by the Controller and the Agent to communicate
    metadata on discovered Pods.

    Args:
        kind (str): Kubernetes CR's kind
        singular (str): Kubernetes CR's singular
        plural (str): Kubernetes CR's plural
        spec (dict): init spec
    """
    custom_resource = {
        "apiVersion": "casmella.com/v1alpha",
        "kind": kind,
        "metadata": {"name": f"casmella-{singular}"},
        "spec": spec,
    }
    try:
        _api_response = custom_api_instance.create_cluster_custom_object(
            group='casmella.com',
            version='v1alpha',
            plural=plural,
            body=custom_resource,
        )
        logger.debug(f"The {singular} resource has been created")
    except ApiException as _e:
        if _e.status == 409:
            logger.debug(f"The {singular} resource already exists")
            return
        logger.exception("Exception when calling CustomObjectsApi->create_cluster_custom_object")


def patch_custom_resource(singular: str, plural: str, spec_to_patch: dict):
    """Patch a spec to an existing Custom Resource

    Args:
        singular (str): Kubernetes CR's kind
        plural (str): Kubernetes CR's plural
        spec_to_patch (dict): spec to be patched
    """
    patch_resource = {
        'spec': spec_to_patch
    }
    with K8S_RESOURCES_LOCK_OBJECTS[singular]:
        try:
            _api_response = custom_api_instance.patch_cluster_custom_object(
                group='casmella.com',
                version='v1alpha',
                plural=plural,
                name=f'casmella-{singular}',
                body=patch_resource,
            )
        except ApiException as _e:
            if _e.status == 403:
                logger.debug(f"Cannot patch the {singular} resource for this reason: {_e.reason}")
                return
            logger.exception(f"Cannot patch the {singular} resource with {patch_resource}")
        # except:
        #    logger.exception(
        #        f"Unhandled exception when patching the {singular} resource with {patch_resource}"
        #    )
        else:
            logger.debug(f"The {singular} resource has been patched with {patch_resource}")


def get_filesystem(pod_namespace, pod_name, container_name) -> str:
    """Get the path to the filesystem of a container in a given Pod.
    The return value will be used to attach uprobes (for handling HTTPS events).

    Args:
        pod_namespace (_type_): Pod's namespace
        pod_name (_type_): Pod's name
        container_name (_type_): Container's name

    Returns:
        str: The Container's filesystem on the host
    """
    mergeddir = None
    stderr = True   # bool
    stdin = False   # bool
    stdout = True   # bool
    tty = False     # bool
    command = ['mount | grep overlay']
    # Launch the command into the POD
    for _iter in range(15):
        try:
            resp = stream(
                core_api_instance.connect_get_namespaced_pod_exec,
                pod_name, pod_namespace, container=container_name, command=command,
                stderr=stderr, stdin=stdin, stdout=stdout, tty=tty
            )
        except ApiException as _e:
            continue
        else:
            mergeddir = 'uknown'
            for _line in resp.split("\n"):
                if "overlay" in _line:
                    mergeddir = _line[_line.find("upperdir"):].split(",")[0] + "/../merged"
                    mergeddir = mergeddir[mergeddir.find("/"):]
                    break
    return mergeddir


def get_iflink(pod_namespace, pod_name, container_name, interface_name) -> str:
    """Get the index of the parent interface on the worker node
    of a given network interface within a container

    Args:
        pod_namespace (_type_): Pod's namespace
        pod_name (_type_): Pod's name
        container_name (_type_): Container's name
        interface_name (_type_): Interface's namespace

    Returns:
        str: The return value will be used to attach TC filters
    """
    stderr = True   # bool
    stdin = False   # bool
    stdout = True   # bool
    tty = False     # bool

    def _exec(cmd):
        """Run a command list in the pod, return stripped stdout or None on failure."""
        for _iter in range(3):
            try:
                resp = stream(
                    core_api_instance.connect_get_namespaced_pod_exec,
                    pod_name, pod_namespace, container=container_name, command=cmd,
                    stderr=stderr, stdin=stdin, stdout=stdout, tty=tty
                )
                resp = resp.strip() if resp else None
                if resp:
                    return resp
            except Exception as _e:
                logger.debug(f"_exec {cmd} on {pod_name}/{container_name} attempt {_iter} failed: {_e}")
                continue
        return None

    # Primary: read iflink sysfs entry (works when /sys is mounted)
    resp = _exec(['cat', f'/sys/class/net/{interface_name}/iflink'])
    if resp:
        try:
            int(resp)
            return resp
        except ValueError:
            pass

    # Fallback: parse peer index from 'ip -o link show <iface>' output
    # Example output: "5: eth0@if36: <BROADCAST,...>" → extract 36
    resp = _exec(['ip', '-o', 'link', 'show', interface_name])
    if resp:
        match = re.search(r'@if(\d+)', resp)
        if match:
            logger.debug(f"iflink for {pod_name}/{interface_name} found via ip link: {match.group(1)}")
            return match.group(1)

    logger.warning(f"Could not determine iflink for {pod_name}/{interface_name}")
    return None


def find_network_interfaces(pod_object: client.V1Pod) -> tuple:
    """Extract information about the main and additional (added by using multus)
    network interfaces within the Pod

    Args:
        pod_object (client.V1Pod): See https://github.com/kubernetes-client/python/blob/master/kubernetes/docs/V1Pod.md

    Returns:
        tuple: A tuple containing:
            pod_interface_for_this_pod_content: a Python dict with:
                -   keys: network interfaces'names
                -   values: the index of the peer network interface on the host

            ip_address_info: a Python dict with:
                -   keys: IP addresses
                -   values: (pod_name, interface_name) tuples
    """
    pod_interface_for_this_pod_content = {}
    ip_address_info = {}
    pod_name = pod_object.metadata.name
    namespace = pod_object.metadata.namespace
    # Find a container with a non distroless
    for container in pod_object.spec.containers:
        if container.name != 'linkerd-proxy':
            container_name = container.name
    # See the comment
    # https://github.com/k8snetworkplumbingwg/multus-cni/issues/468#issuecomment-607977200
    annotations = pod_object.metadata.annotations or {}
    if 'k8s.v1.cni.cncf.io/network-status' in annotations:
        # Get the k8s.v1.cni.cncf.io/network-status field into a python dictionary
        network_status = annotations['k8s.v1.cni.cncf.io/network-status']
        network_status = json.loads(network_status)
        # Extract information about the found interfaces
        for interface in network_status:
            # Get the interface name in the Pod
            interface_name = interface.get('interface', 'eth0')
            if interface_name != '':
                # Check that the interface is not excluded
                if interface_name in EXCLUDED_INTERFACES:
                    continue
                # Get the peer interface index on the worker node
                if_index = get_iflink(namespace, pod_name, container_name, interface_name)
                if if_index is None:
                    logger.error(pod_name + " " + container_name)
                    continue
                # Store information about the interface in podInterfaces
                if_index = int(if_index)
                pod_interface_for_this_pod_content[interface_name] = if_index
                # Store information about the interface in ipAddresses
                for ip_address in interface['ips']:
                    ip_address_info[ip_address] = (pod_name, interface_name)
                    logger.debug(f"Discovered {ip_address}: {ip_address_info[ip_address]}")
    else:
        # Fallback for clusters without Multus CNI: discover the default eth0 interface
        logger.debug(f"No Multus annotation on {pod_name}, falling back to eth0 discovery")
        interface_name = 'eth0'
        if interface_name not in EXCLUDED_INTERFACES:
            if_index = get_iflink(namespace, pod_name, container_name, interface_name)
            if if_index is not None:
                try:
                    if_index = int(if_index)
                    pod_interface_for_this_pod_content[interface_name] = if_index
                    # Use the Pod IP from the status field
                    pod_ip = pod_object.status.pod_ip
                    if pod_ip:
                        ip_address_info[pod_ip] = (pod_name, interface_name)
                        logger.debug(f"Discovered (fallback) {pod_ip}: {ip_address_info[pod_ip]}")
                except (ValueError, TypeError):
                    logger.error(f"Could not parse iflink index for {pod_name}/{interface_name}")
            else:
                logger.warning(f"Could not get iflink for {pod_name}/{interface_name}")
    return pod_interface_for_this_pod_content, ip_address_info


def find_filesystems(pod_object: client.V1Pod) -> list:
    """Extract information about the Pods' filesystems

    Args:
        pod_object (client.V1Pod): See https://github.com/kubernetes-client/python/blob/master/kubernetes/docs/V1Pod.md

    Returns:
        list: The list of filesystems of Pods' Containers
    """
    pod_filesystem_path_for_this_pod_content = []
    pod_name = pod_object.metadata.name
    namespace = pod_object.metadata.namespace
    for container in pod_object.spec.containers:
        if container.name != 'linkerd-proxy':
            container_name = container.name
            mergeddir = get_filesystem(namespace, pod_name, container_name)
            logger.debug(mergeddir)
            pod_filesystem_path_for_this_pod_content.append(mergeddir)
    return pod_filesystem_path_for_this_pod_content


def get_pod_info_extra(pod_object: client.V1Pod) -> dict:
    """Get more detailled information about the Pod

    Args:
        pod_object (client.V1Pod): See https://github.com/kubernetes-client/python/blob/master/kubernetes/docs/V1Pod.md

    Returns:
        dict: A dict with Pod's metadata
    """
    node_name = pod_object.spec.node_name
    namespace = pod_object.metadata.namespace
    pod_hash = pod_object.metadata.labels['pod-template-hash']
    replicaset_name = 'none'
    deployment_name = 'none'
    statefulset_name = 'none'
    for pod_owner in pod_object.metadata.owner_references:
        if pod_owner.kind == 'ReplicaSet':
            replicaset_name = pod_owner.name
            try:
                replicaset_object = apps_api_instance.read_namespaced_replica_set(
                    replicaset_name, namespace
                )
            except ApiException:
                logger.exception("Exception when calling AppsV1Api->read_namespaced_replica_set")

            for replicaset_owner in replicaset_object.metadata.owner_references:
                if replicaset_owner.kind == 'Deployment':
                    deployment_name = replicaset_owner.name
        elif pod_owner.kind == 'StatefulSet':
            statefulset_name = pod_owner.name
    pod_info_extra = {
        'pod_hash': pod_hash,
        'pod_namespace': namespace,
        'replicaset_name': replicaset_name,
        'deployment_name': deployment_name,
        'statefulset_name': statefulset_name,
        'node_name': node_name,
        'cluster_name': CLUSTER_NAME
    }
    return pod_info_extra


def handle_added_pod(pod_object: client.V1Pod):
    """Handle an added Pod.

    This function updates custom resources 'topology' and 'hooklist'.
    - In the 'topology' CR, it records information about the created Pod, including its IP address(es).
    - In the 'hooklist' CR, it records information about the network interfaces and filesystems of the containers.

    Args:
        pod_object (client.V1Pod): See https://github.com/kubernetes-client/python/blob/master/kubernetes/docs/V1Pod.md
    """
    metrics.primitives_called.labels('handle_added_pod').inc()
    # Get the name of the Pod and the hosting node
    pod_name = pod_object.metadata.name
    node_name = pod_object.spec.node_name
    # Prepare the data
    ip_address_info = {}
    pod_info = {pod_name: {}}
    pod_interface = {pod_name: {'status': 'ADDED', 'content': {}, 'node': node_name}}
    # Initialize the spec for the hooklists CR
    hooks_to_patch = {
        'podInterfaces': {},
        'podSslLibPaths': {}
    }
    # Initialize the spec for the topolgy CR
    infos_to_patch = {
        'ipAddressInfos': {},
        'podInfos': {}
    }
    # Fill the data
    pod_interface[pod_name]['content'], ip_address_info = find_network_interfaces(pod_object)
    infos_to_patch['ipAddressInfos'] = ip_address_info
    if not pod_interface[pod_name]['content']:
        # No interfaces found — don't write empty content to hooklist; the watcher
        # will re-emit ADDED if the pod restarts, otherwise a manual rollout is needed
        logger.warning(f"No interfaces found for {pod_name}, skipping hooklist update")
        infos_to_patch['podInfos'] = pod_info
        patch_custom_resource('topology', 'topologies', infos_to_patch)
        return
    hooks_to_patch['podInterfaces'] = pod_interface
    if MONITOR_HTTPS:
        pod_ssl_lib_path = {pod_name: {'status': 'ADDED', 'content': [], 'node': node_name}}
        pod_ssl_lib_path[pod_name]['content'] = find_filesystems(pod_object)
        hooks_to_patch['podSslLibPaths'] = pod_ssl_lib_path
    # Update the hooklist resource
    hooks_to_patch.update(infos_to_patch)
    patch_custom_resource('hooklist', 'hooklists', hooks_to_patch)
    # Store information about the Pod
    pod_info_extra = get_pod_info_extra(pod_object)
    pod_info[pod_name] = pod_info_extra
    logger.debug(f"Discovered {pod_name}: {pod_info[pod_name]}")
    # Update the topology resource
    infos_to_patch['podInfos'] = pod_info
    patch_custom_resource('topology', 'topologies', infos_to_patch)
    # Update the info metric
    metrics.pods_information.labels(pod_name=pod_name).info(pod_info_extra)
    # Increment the events metric
    pods_events_labels = pod_info_extra.copy()
    pods_events_labels['event'] = 'added'
    metrics.pods_events.labels(**pods_events_labels).inc()


def handle_deleted_pod(pod_object: client.V1Pod):
    """Handle a deleted Pod.

    This function updates custom resources 'topology' and 'hooklist'.
    - In the 'topology' CR, it clears information about the deleted Pod, including its IP address(es).
    - In the 'hooklist' CR, it updates the status of the hooks related to the deleted Pod.

    Args:
        pod_object (client.V1Pod): See https://github.com/kubernetes-client/python/blob/master/kubernetes/docs/V1Pod.md
    """
    metrics.primitives_called.labels('handle_deleted_pod').inc()
    # Get the name of the Pod
    pod_name = pod_object.metadata.name

    logger.debug(f"Pod {pod_name} will be deleted")

    # Update status of hooks
    hooks_to_patch = {
        'podInterfaces': {pod_name: {'status': 'DELETED'}},
    }
    if MONITOR_HTTPS:
        hooks_to_patch['podSslLibPaths'] = {pod_name: {'status': 'DELETED'}}

    # Delete infos
    infos_to_patch = {
        'ipAddressInfos': {},
        'podInfos': {pod_name: None}
    }

    # Get IPs to be deleted
    ip_address_info = {}
    with K8S_RESOURCES_LOCK_OBJECTS['topology']:
        topology_resource = custom_api_instance.get_cluster_custom_object(
            group='casmella.com',
            version='v1alpha',
            plural='topologies',
            name='casmella-topology',
        )
    ip_address_infos = topology_resource['spec']['ipAddressInfos']
    for ip_address in ip_address_infos:
        if ip_address_infos[ip_address][0] == pod_name:
            logger.debug(f"IP {ip_address} will be deleted")
            ip_address_info[ip_address] = None
    infos_to_patch['ipAddressInfos'] = ip_address_info

    # Update the hooklist resource
    patch_custom_resource('hooklist', 'hooklists', hooks_to_patch)
    # Update the topology resource
    patch_custom_resource('topology', 'topologies', infos_to_patch)

    # Update the events metric
    pod_info_extra = topology_resource['spec'].get('podInfos', {}).get(pod_name)
    if pod_info_extra:
        pods_events_labels = pod_info_extra.copy()
        pods_events_labels['event'] = 'deleted'
        metrics.pods_events.labels(**pods_events_labels).inc()
    else:
        logger.warning(f"Pod {pod_name} not found in podInfos, skipping events metric update")

    # Clear Prometheus metrics
    metrics.clear_prometheus_metrics_for_pod(pod_name)


def watch_pods_matching_label_selector(label_selector: str, namespace=None):
    """Watch for pods matching the pre-defined label selector in the appropriate namespace.

    It's worthnoting that the Controller communicates its data to the Agent based on a declarative approach.
    In fact, the data discovered by the Controller on the Pods includes information about their deployment on Kubernetes and information about their network interfaces and IP addresses.
    This data is then written to the Kubernetes API server using custom resources (CR).
    This is a concept that consists in extending the Kubernetes API through Custom Resource Definitions (CRDs)
    (See https://kubernetes.io/docs/concepts/extend-kubernetes/api-extension/custom-resources/).
    In fact, it allows to define new types of Kubernetes resources in addition to the standard ones (e.g. Pods, Deployments, etc.).

    The discovered data is categorized into 4 hashmap data structures, written within 2 CRs.
    The 'ipAddressInfos' and 'podInfos' are written in the 'topology' CR,
    while 'podInterfaces' and 'podSslLibPaths' are written in the 'hooklist' CR.

    Hashmaps description:
    - 'ipAddressInfos' to map IP addresses to combinations of (pod-name, network-interface),
    - 'podInfos' to map Pods to combinations of (k8s-namespace, k8s-podhash, k8s-deployment, k8s-replicaset, k8s-statefulset, k8s-node),
    and
    - 'podInterfaces' including, for each Pod, the mapping between its network interfaces and the index of the parent network interface on the node hosting that Pod.
    - 'podSslLibPaths' including a list of key and value for each Pod, each representing the name of the network interface within the Pod's network namespace and the index of the parent network interface on the node hosting that Pod.

    Entries in the 'podInterfaces' and 'podSslLibPaths' hashmaps, are noted by a status field,
    where possible values are :
    - 'ADDED' for entries added by the Controller and not yet processed by the Agent.
    - 'DELETED' for entries deleted by the Controller and not yet processed by the Agent.
    - 'HANDLED' for entries processed by the Agent successfully.
    - 'FAILED' for entries processed by the Agent unsuccessfully (e.g. the Agent fails to attach the eBPF program to the network interface in question).

    Following the events, 'ADDED' and 'DELETED' status are to be set by the Controller
    while 'HANDLED' and 'FAILED' status are to be set by the Agent.

    This function calls other functions in new threads to achieve the described behavior of the Controller:
    - handle_added_pod for ADDED Pods
    - handle_deleted_pod for DELETED Pods

    Args:
        label_selector (str): Kubernetes label selector to be used for filtering the 5G Pods.
            See https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/
        namespace (str, optional): The namespace where to look for the 5G Pods. Defaults to None.
    """
    resource_version = None
    while 1:
        logger.debug(
            f"Running watch_pods_matching_label_selector({label_selector}, {namespace})"
        )
        # select only running PODs (not necessary ready)
        # https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#pod-phase
        # https://github.com/kubernetes-client/python/blob/master/kubernetes/docs/V1PodStatus.md

        # if_index_counter_local = {}
        field_selector = 'status.phase!=Pending'

        try:
            # https://kubernetes.io/docs/reference/using-api/api-concepts/#efficient-detection-of-changes
            _watch = watch.Watch()
            list_namespaced_pod_local = client.CoreV1Api().list_namespaced_pod
            list_pod_for_all_namespaces_local = client.CoreV1Api().list_pod_for_all_namespaces
            # Create the streaming object
            if namespace:
                watcher = _watch.stream(list_namespaced_pod_local, namespace=namespace,
                                        label_selector=label_selector,
                                        field_selector=field_selector,
                                        resource_version=resource_version)
            else:
                watcher = _watch.stream(list_pod_for_all_namespaces_local,
                                        label_selector=label_selector,
                                        field_selector=field_selector,
                                        resource_version=resource_version)

            for _event in watcher:
                pod_object = _event['object']
                resource_version = pod_object.metadata.resource_version

                if _event['type'] in ['ADDED']:
                    Thread(target=handle_added_pod, args=(pod_object,)).start()

                elif _event['type'] == 'DELETED':
                    Thread(target=handle_deleted_pod, args=(pod_object,)).start()

        except ApiException:
            logger.exception("ApiException when calling list_pod_for_all_namespaces")
            sleep(1)

        except:
            logger.exception("Uknown exception when calling list_pod_for_all_namespaces \
                             and the watcher will be relaunched")
            sleep(1)

        finally:
            # Get the last resource version in order to re-run the Watcher
            if namespace:
                pods_list = list_namespaced_pod_local(namespace=namespace,
                                                      label_selector=label_selector,
                                                      field_selector=field_selector)
            else:
                pods_list = list_pod_for_all_namespaces_local(label_selector=label_selector,
                                                              field_selector=field_selector)
            resource_version = pods_list.metadata.resource_version
            logger.debug(f"watch_pods_matching_label_selector({label_selector}, {namespace}) \
                will be relaunched with resource version {resource_version}")


if __name__ == '__main__':
    logger.error("This module cannot be run as main")
