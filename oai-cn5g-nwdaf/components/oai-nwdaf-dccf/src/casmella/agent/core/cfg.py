"""
Common variables and functions
"""
# standard
import os
from os import environ
import gc
import logging
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from time import sleep
# third-pary
from cachetools import cached, LRUCache
# internal
from . import metrics

lock = Lock()

# Set logging configuration
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(threadName)s %(filename)s:%(lineno)d %(levelname)-10s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
for i in logging.Logger.manager.loggerDict:
    logging.getLogger(i).setLevel(logging.ERROR)
logger = logging

# Global variables
MY_NODE_NAME = environ.get('MY_NODE_NAME')
MONITOR_HTTPS = None
ip_address_infos = {}
pod_infos = {}
# Database configuration
DB_ENABLED = False
DB_PATH = '/data/casmella.db'
DB_RETENTION_HOURS = 24
server_and_client_labels = metrics.server_and_client_labels
# Caches
server_and_client_cache = LRUCache(maxsize=128)
# ThreadPoolExecutors
EVENTS_HANDLERS_MAX_NUM = 256
events_handlers_tasks = ThreadPoolExecutor(
    max_workers=EVENTS_HANDLERS_MAX_NUM, thread_name_prefix='EventHandler'
)
HOOKS_HANDLERS_MAX_NUM = 12
hooks_handlers_tasks = ThreadPoolExecutor(
    max_workers=HOOKS_HANDLERS_MAX_NUM, thread_name_prefix='HookHandler'
)


# ============================
# General functions and classes
# ============================
def log_task_result(future):
    try:
        result = future.result()
    except Exception as e:
        logging.exception('Task failed with exception: %s', e)


def log_dict_info(log_level=10, **kwargs):
    """
Log events.
    """
    logger.log(log_level, str(kwargs))


def find_file_folder(file_name, folder):
    """
Find a file in a folder.
    """
    for root, folders, files in os.walk(folder):
        for _file in folders + files:
            if file_name in _file:
                yield os.path.join(root, _file)


def garbage_collection():
    """
Garbage collection.
    """
    while 1:
        gc.collect()
        sleep(10)


def operation_time_single_write_item(_id, stream, item):
    """
Write response time item.
    """
    try:
        if _id in stream:
            logger.warning(f"id {_id} already exists in {stream}")
        # Write the item
        stream[_id] = item
    except:
        logger.warning(f"Cannot write {_id} in {stream}")


def operation_time_single_read_item(_id, stream, timeout=10):
    """
Read response time item.
    """
    operation_time_item = None
    for _iter in range(timeout):
        try:
            operation_time_item = stream[_id]
        except KeyError:
            sleep(1)
            continue
        else:
            del stream[_id]
            break
    return operation_time_item


def operation_time_buffer_write_item(_id, stream, item):
    """
Write response time item i a LIFO buffer.
    """
    try:
        if _id not in stream:
            # Initialize the list for that _id
            stream[_id] = []
        # Append the request time to that _id
        stream[_id].append(item)
    except:
        logger.warning(f"Cannot write {_id} in {stream}")


def operation_time_buffer_read_item(_id, stream, timeout=10):
    """
Read response time item from a LIFO buffer.
    """
    operation_time_item = None
    for _iter in range(timeout):
        try:
            stream[_id].sort()
            operation_time_item = stream[_id].pop(0)
        except KeyError:
            sleep(1)
            continue
        else:
            if not stream[_id]:  # stream[id] is empty #
                del stream[_id]
            break
    return operation_time_item


@cached(cache=server_and_client_cache, lock=Lock())
def retrive_server_and_client_from_ips(server_ip, client_ip, only_one_info_is_needed=False):
    """
Retrieve server and client Pods information from IP addresses.
    """
    metrics.primitives_called.labels('retrive_server_and_client_from_ips').inc()
    # Initialize source and destination
    server_and_client = dict().fromkeys(server_and_client_labels, 'uknown')
    server_and_client['server_ip_addr'] = server_ip
    server_and_client['client_ip_addr'] = client_ip
    # Retrieve PODs
    pod = 'uknown'
    peer_pod = 'uknown'
    loopend1 = 0
    loopend2 = 0
    our_range = range(3)    # Doing this n times means that we'll sleep (n-1) times
    for _iter in our_range:
        # for Server IP
        if not loopend1:
            try:
                ip_address_infos_ip = ip_address_infos[server_ip]
            except KeyError:
                if loopend2:    # Client IP found #
                    if _iter == our_range[-1]:    # Last iteration #
                        break
                    # Client IP found and not the last iteration #
                    sleep(0.5)
                    continue
            else:
                pod, interface = ip_address_infos_ip
                # Clean item to free memory
                del ip_address_infos_ip
                # Fill fields
                server_and_client['server_pod_name'] = pod
                server_and_client['server_interface_name'] = interface
                loopend1 = 1
                if loopend2 or only_one_info_is_needed:
                    break
        # for Client IP
        if not loopend2:
            try:
                ip_address_infos_peer_ip = ip_address_infos[client_ip]
            except KeyError:
                if _iter == our_range[-1]:    # Last iteration #
                    break
                sleep(0.5)
                continue
            else:
                peer_pod, peer_interface = ip_address_infos_peer_ip
                # Clean item to free memory
                del ip_address_infos_peer_ip
                # Fill fields
                server_and_client['client_pod_name'] = peer_pod
                server_and_client['client_interface_name'] = peer_interface
                if loopend1 or only_one_info_is_needed or (_iter == our_range[-1]):
                    # Server IP found or Last iteration #
                    break
                loopend2 = 1
                sleep(0.5)
                continue
    # Retrieve information about PODs
    # for POD
    if pod != 'uknown':
        try:
            podinfos_pod = pod_infos[pod]
        except KeyError:
            # Leave fields 'uknown"
            pass
        else:
            # Fill fields
            for key, value in podinfos_pod.items():
                server_and_client[f'server_{key}'] = value
    # for PEER POD
    if peer_pod != 'uknown':
        try:
            pod_infos_peer_pod = pod_infos[peer_pod]
        except KeyError:
            # Leave fields 'uknown"
            pass
        else:
            # Fill fields
            for key, value in pod_infos_peer_pod.items():
                server_and_client[f'client_{key}'] = value
    # Return source and destination
    return server_and_client


def retrive_src_and_dst_from_ips(src_ip, dst_ip, only_one_info_is_needed=False):
    """
Retrieve src and dst Pods information from IP addresses.
    """
    # Get server and client Pods
    server_and_client = \
        retrive_server_and_client_from_ips(src_ip, dst_ip, only_one_info_is_needed)
    # Replace server and client Pods by src and dst Pods respectively
    source_and_destination = {}
    for key, value in server_and_client.items():
        if 'server_' in key:
            new_key = key.replace('server_', 'src_')
            source_and_destination[new_key] = value
        elif 'client_' in key:
            new_key = key.replace('client_', 'dst_')
            source_and_destination[new_key] = value
    # Return source_and_destination
    return source_and_destination
