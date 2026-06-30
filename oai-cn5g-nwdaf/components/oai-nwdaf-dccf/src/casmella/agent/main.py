"""Agent's main module.
"""
# standard
import argparse
from threading import Thread
from time import sleep
import signal
from os import kill, getpid
# third-pary
import yaml
# from kubernetes.client.rest import ApiException
# from kubernetes.stream import stream
# internal
from core import cfg, metrics, core, database
from ebpf.ebpf import ebpf_instance
from protocols import http2, ngap, pfcp
from protocols.http2 import load_openapi_operations

parser = argparse.ArgumentParser()
parser.add_argument('-c', '--config', default='/config/agent-config.yaml',
                    help='Path to the config file')
parser.add_argument('-o', '--openapi', default='/config/openapi-operations.yaml',
                    help='Path to the OpenAPI operations file')
args = parser.parse_args()

SafeLoader = yaml.loader.SafeLoader

logger = cfg.logging
for i in logger.Logger.manager.loggerDict:
    logger.getLogger(i).setLevel(cfg.logging.ERROR)


def load_configuration_file(config_file_path):
    """
Load the configuration.
    """
    with open(config_file_path, encoding='utf8', errors='ignore') as openned_file:
        config_data = yaml.load(openned_file, Loader=SafeLoader)
        cfg.USE_RING_BUFFERS = config_data.get('use_ring_buffers', True)
        cfg.USE_XDP = config_data.get('use_xdp', False)
        cfg.MONITOR_HTTPS = \
            config_data.get('monitor_https', None)
        cfg.DEBUG_EVENTS = config_data.get('debug_events', None)
        cfg.DEBUG_OPERATION_TIME_STREAMS = \
            config_data.get('debug_operation_time_streams', None)
        core.N6_INTERFACE_NAMES = \
            tuple(config_data.get('n6_interface_names', ()))
        metrics.PROM_PORT = config_data.get('prom_port', 9950)

        ignore_sent_requests_and_received_responses = config_data.get(
            'ignore_sent_requests_and_received_responses', {})
        http2.IGNORE_SENT_REQUESTS_AND_RECEIVED_RESPONSES = \
            ignore_sent_requests_and_received_responses.get('http2', True)
        ngap.IGNORE_SENT_REQUESTS_AND_RECEIVED_RESPONSES = \
            ignore_sent_requests_and_received_responses.get('ngap', False)
        pfcp.IGNORE_SENT_REQUESTS_AND_RECEIVED_RESPONSES = \
            ignore_sent_requests_and_received_responses.get('pfcp', True)

        # Database configuration
        db_config = config_data.get('database', {})
        cfg.DB_ENABLED = db_config.get('enabled', False)
        cfg.DB_PATH = db_config.get('path', '/data/casmella.db')
        cfg.DB_RETENTION_HOURS = db_config.get('retention_hours', 24)


def initialize_ebpf_module(use_ring_buffers, use_xdp):
    """
Initialize the eBPF user-space module.
    """
    ebpf_instance.prepare_programs(
        use_ring_buffers=use_ring_buffers,
        use_xdp=use_xdp,
        monitor_https=cfg.MONITOR_HTTPS,
        ebpf_debug_level=0
    )


def main():
    """
The main function.
    """
    # Load global configuration
    load_configuration_file(args.config)
    load_openapi_operations(args.openapi)

    # Initialize the database
    database.initialize_database(
        db_path=cfg.DB_PATH,
        enabled=cfg.DB_ENABLED,
        retention_hours=cfg.DB_RETENTION_HOURS
    )

    # Initialize the eBPF user-space module
    initialize_ebpf_module(cfg.USE_RING_BUFFERS, cfg.USE_XDP)

    # Run the Prometheus endpoint
    Thread(
        target=metrics.start_prometheus_endpoint,
        name='start_prometheus_endpoint'
    ).start()
    logger.debug("HTTP server exposing Prometheus metrics started")

    # Execute the control loop
    try:
        Thread(
            target=core.topology_control_loop,
            name='topology_control_loop'
        ).start()
    except:
        # Send SIGTERM signal to itself
        kill(getpid(), signal.SIGTERM)

    # Execute Garbage Colelction
    """
    Thread(
        target=cfg.garbage_collection,
        name='garbage_collection'
    ).start()
    """

    # Debug operation time streams
    if cfg.DEBUG_OPERATION_TIME_STREAMS:
        Thread(
            target=core.debug_operation_time_streams,
            name='debug_operation_time_streams'
        ).start()

    # Catch SIGTERM signal
    signal.signal(signal.SIGTERM, core.sigterm_handler)

    # Keep the main thread alive
    while 1:
        sleep(3600)


if __name__ == '__main__':
    main()
