"""K8s module.
"""
# standard
from threading import Lock
# third-pary
from kubernetes import client, config
from kubernetes.client.rest import ApiException
# internal
from . import cfg

logger = cfg.logging

for i in logger.Logger.manager.loggerDict:
    logger.getLogger(i).setLevel(cfg.logging.ERROR)

# Initialize global variables
K8S_RESOURCES_LOCK_OBJECTS = {
    # A dict enabling to read and update Kubernetes CRs in thread-safe manner.
    'topology': Lock(),
    'hooklist': Lock(),
    'fiveqiinfo': Lock(),
}

# Load K8s configuration and APIs
config.load_incluster_config()
logger.debug("Kubernetes configuration loaded...")
custom_api_instance = client.CustomObjectsApi()


def get_topology_resource(name: str) -> tuple:
    """Retrieve the topology resource from the Kubernetes API.

    This function fetches the specified Custom Resource (CR) of type `topologies` from the Kubernetes
    API and extracts the `ipAddressInfos` and `podInfos` from its definition.

    Args:
        name (str): The name of the topology resource to retrieve.

    Returns:
        tuple: A tuple containing two dictionaries:
            - The first dictionary contains the `ipAddressInfos` from the topology resource.
            - The second dictionary contains the `podInfos` from the topology resource.
    """
    with K8S_RESOURCES_LOCK_OBJECTS['topology']:
        try:
            custom_resource = custom_api_instance.get_cluster_custom_object(
                group='casmella.com',
                version='v1alpha',
                plural='topologies',
                name=name,
            )
            _x = custom_resource['spec']['ipAddressInfos']
            _y = custom_resource['spec']['podInfos']
        except ApiException:
            _x, _y = {}, {}
    # Return dictionaries
    return _x, _y


def get_hooklist_resource(name: str) -> tuple:
    """
    Retrieve and parse the hooklist resource from the Kubernetes API.

    This function fetches the specified Custom Resource (CR) of type `hooklists` from the Kubernetes
    API and extracts the `podInterfaces` and `podSslLibPaths` from its definition.
    If the configuration setting `MONITOR_HTTPS` is enabled, it also extracts `podSslLibPaths`;
    otherwise, an empty dictionary is returned for `podSslLibPaths`.

    Args:
        name (str): The name of the hooklist resource to retrieve.

    Returns:
        tuple: A tuple containing two dictionaries:
            - The first dictionary contains the `podInterfaces` from the hooklist resource.
            - The second dictionary contains the `podSslLibPaths` from the hooklist resource \
            if `MONITOR_HTTPS` is enabled; otherwise, an empty dictionary.
    """
    with K8S_RESOURCES_LOCK_OBJECTS['hooklist']:
        try:
            custom_resource = custom_api_instance.get_cluster_custom_object(
                group='casmella.com',
                version='v1alpha',
                plural="hooklists",
                name=name,
            )
            _z = custom_resource['spec']['podInterfaces']
            _w = custom_resource['spec']['podSslLibPaths'] if cfg.MONITOR_HTTPS else {}
        except ApiException:
            _z, _w = {}, {}
    # Return dictionaries
    return _z, _w


def get_fiveqiinfo_resource(name: str) -> tuple:
    """
    Retrieve and parse the fiveqiinfo resource from the Kubernetes API.

    This function fetches the specified Custom Resource (CR) of type `fiveqiinfos` from the
    Kubernetes API and extracts the entire specification (`spec`) of the resource.

    Args:
        name (str): The name of the fiveqiinfo resource to retrieve.

    Returns:
        dict: A dictionary containing the `spec` of the fiveqiinfo resource. If the resource cannot \
        be retrieved, an empty dictionary is returned.
    """
    with K8S_RESOURCES_LOCK_OBJECTS['fiveqiinfo']:
        try:
            custom_resource = custom_api_instance.get_cluster_custom_object(
                group='casmella.com',
                version='v1alpha',
                plural='fiveqiinfos',
                name=name,
            )
            qfiinfo_spec = custom_resource['spec']
        except ApiException:
            qfiinfo_spec = {}
    # Return dictionaries
    return qfiinfo_spec


def patch_custom_resource(singular: str, plural: str, spec_to_patch: dict):
    """Patch a specification to an existing custom resource in the Kubernetes cluster.

    This function patches the `spec` field of a specified custom resource in the Kubernetes cluster
    with the given data.
    It handles different exceptions to ensure robustness and logs appropriate messages.

    Args:
        singular (str): The singular name of the custom resource to be patched.
        plural (str): The plural name of the custom resource to be patched.
        spec_to_patch (dict): The specification data to patch into the custom resource.
    """
    patch_resource = {
        'spec': spec_to_patch
    }
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
    except Exception:
        logger.exception(
            f"Unhandled exception when patching the {singular} resource with {patch_resource}"
        )
    else:
        logger.debug(f"The {singular} resource has been patched with {patch_resource}")


if __name__ == '__main__':
    logger.error("This module cannot be run as main")
