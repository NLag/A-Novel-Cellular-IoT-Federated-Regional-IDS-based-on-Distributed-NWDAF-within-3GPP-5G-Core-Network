"""Controller's main Module.
"""
# standard
import argparse
import logging
from threading import Thread
# third-party
import yaml
# internal
import core, metrics

parser = argparse.ArgumentParser()
parser.add_argument('-c', '--config', default='../config/controller-config.yaml',
                    help='Path to the config file')
args = parser.parse_args()

SafeLoader = yaml.loader.SafeLoader

# ###### Set logging configuration
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(threadName)s %(filename)s:%(lineno)d %(levelname)-10s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
for i in logging.Logger.manager.loggerDict:
    logging.getLogger(i).setLevel(logging.ERROR)

logger = core.logging
for i in logger.Logger.manager.loggerDict:
    logger.getLogger(i).setLevel(core.logging.ERROR)


def load_configuration_file(config_file_path='../config/controller-config.yaml') -> list:
    """Load and apply the configuration

    Args:
        config_file_path (str, optional): The path to the configuration file. Defaults to '../config/controller-config.yaml'.

    Returns:
        list: The list of kubernetes pods watchers
    """
    watchers = ()
    with open(config_file_path, encoding='utf8', errors='ignore') as openned_file:
        config_data = yaml.load(openned_file, Loader=SafeLoader)
        core.CLUSTER_NAME = config_data.get('cluster_name', 'cluster01')
        core.MONITOR_HTTPS = config_data.get('monitor_https', None)
        core.EXCLUDED_INTERFACES = tuple(config_data.get('excluded_interfaces', ()))
        metrics.PROM_PORT = config_data.get('prom_port', 9950)
        watchers = tuple(config_data.get('watchers', ()))
    return watchers



def main():
    """The main function
    """
    watchers = load_configuration_file(args.config)

    # Initialize custom resources
    topology_spec = {
        "ipAddressInfos": {},
        "podInfos": {},
    }
    hooklist_spec = {
        "podInterfaces": {},
        "podSslLibPaths": {},
    }
    fiveqiinfo_spec = {
        # Kubernetes CR's cannot be intialized with an empty spec.
        # "ignored", 0 is a combination that is used only to intialize the CR,
        # and it will be ignored by the Agent
        "ignored": "0",
    }
    core.initialize_custom_resource('Topology', 'topology', 'topologies', topology_spec)
    core.initialize_custom_resource('HookList', 'hooklist', 'hooklists', hooklist_spec)
    core.initialize_custom_resource('FiveqiInfo', 'fiveqiinfo', 'fiveqiinfos', fiveqiinfo_spec)

    # Run the Prometheus endpoint in a separate Thread
    Thread(
        target=metrics.start_prometheus_endpoint,
        name='start_prometheus_endpoint'
    ).start()
    logger.debug("HTTP server exposing Prometheus metrics started")

    # Run Pods Watchers in separate Threads
    try:
        for watcher in watchers:
            watcher_name = watcher['name']
            namespace = watcher.get('namespace', None)
            label_selector = watcher['label_selector']
            Thread(
                target=core.watch_pods_matching_label_selector,
                args=(label_selector, namespace),
                name=watcher_name
            ).start()
    finally:
        pass


if __name__ == '__main__':
    main()
