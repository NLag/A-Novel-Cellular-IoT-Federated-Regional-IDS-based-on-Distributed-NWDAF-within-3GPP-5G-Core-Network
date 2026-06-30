"""QoS management (QoS flows) module.
"""
# standard
from threading import Lock
# third-pary
from cachetools import cached, LRUCache
# internal
from core import cfg
from core.k8s import get_fiveqiinfo_resource, patch_custom_resource

logger = cfg.logging

for i in logger.Logger.manager.loggerDict:
    logger.getLogger(i).setLevel(cfg.logging.ERROR)

qfi_info_cache = LRUCache(maxsize=128)


def store_qfi_info(qfi_value: int, fiveqi_value: int, fiveqi_type: str):
    """Store QFI info.

    This function stores the mapping between QFI value and its corresponding 5QI value and type
    in a custom resource.

    Args:
        qfi_value (int): QFI value.
        fiveqi_value (int): 5QI value.
        fiveqi_type (str): 5QI type.
    """
    spec_to_patch = {qfi_value: (fiveqi_value, fiveqi_type)}
    patch_custom_resource('fiveqiinfo', 'fiveqiinfo', spec_to_patch)


@cached(cache=qfi_info_cache, lock=Lock())
def get_qfi_info(qfi_value: int) -> tuple:
    """Get QFI info.

    This function retrieves the 5QI value and type corresponding to the provided QFI value. It
    uses caching to minimize access to the underlying resource.

    Args:
        qfi_value (int): QFI value.

    Returns:
        tuple[int, str]: A tuple containing the 5QI value and 5QI type.
    """
    qfiinfo_spec = get_fiveqiinfo_resource('casmella-fiveqiinfo')
    try:
        fiveqi_value, fiveqi_type = qfiinfo_spec[str(qfi_value)]
    except KeyError:
        fiveqi_value = 'uknown'
        fiveqi_type = 'uknown'
        logger.warning(f'qfi_to_fiveqi has value {qfiinfo_spec}')
    return fiveqi_value, fiveqi_type
