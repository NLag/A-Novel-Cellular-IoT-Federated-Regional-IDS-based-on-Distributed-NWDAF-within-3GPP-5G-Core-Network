#!/usr/bin/env python3
"""
Docker container network interface discovery
Replaces Kubernetes-based discovery from Casmella
"""
import docker
import subprocess
import json
import time
import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DockerDiscovery:
    def __init__(self):
        # Try to connect to Docker - handle both rootless and regular Docker
        docker_host = os.environ.get('DOCKER_HOST')
        
        try:
            if docker_host:
                logger.info(f"Using DOCKER_HOST: {docker_host}")
                self.client = docker.DockerClient(base_url=docker_host)
            else:
                logger.info("Using default Docker socket")
                self.client = docker.from_env()
            
            # Test connection
            self.client.ping()
            logger.info("Connected to Docker successfully")
        except Exception as e:
            logger.warning(f"Failed to connect to Docker: {e}")
            logger.warning("Docker discovery will not be available. This is OK if not using Docker mode.")
            self.client = None
    
    def get_container_interfaces_simple(self, container_name):
        """Get container interfaces using Docker API (simpler approach)"""
        if not self.client:
            return []
        try:
            container = self.client.containers.get(container_name)
            
            # Get network settings from container
            networks = container.attrs.get('NetworkSettings', {}).get('Networks', {})
            
            interfaces = []
            for net_name, net_config in networks.items():
                # Use Docker's network info
                interfaces.append({
                    'container': container_name,
                    'network': net_name,
                    'ip': net_config.get('IPAddress', ''),
                    'ifname': 'eth0',  # Docker default
                    'protocols': self.guess_protocols(container_name)
                })
                logger.info(f"Found network in {container_name}: {net_name} ({net_config.get('IPAddress')})")
            
            return interfaces
            
        except docker.errors.NotFound:
            logger.warning(f"Container {container_name} not found")
            return []
        except Exception as e:
            logger.error(f"Error discovering {container_name}: {e}", exc_info=True)
            return []
    
    def guess_protocols(self, container_name):
        """Guess protocols based on container name"""
        protocols = []
        
        if 'amf' in container_name.lower():
            protocols = ['http2', 'ngap']
        elif 'smf' in container_name.lower():
            protocols = ['http2', 'pfcp']
        elif 'upf' in container_name.lower():
            protocols = ['gtpu', 'pfcp']
        else:
            protocols = ['http2']
        
        return protocols
    
    def discover_all_containers(self, name_patterns):
        """Discover all containers matching patterns"""
        discovery_map = {}
        
        if not self.client:
            logger.warning("Docker client not available, skipping container discovery")
            return discovery_map
        
        for pattern in name_patterns:
            try:
                # Find containers by name pattern
                containers = self.client.containers.list(
                    filters={'name': pattern}
                )
                
                for container in containers:
                    name = container.name
                    logger.info(f"Discovering {name}...")
                    interfaces = self.get_container_interfaces_simple(name)
                    
                    if interfaces:
                        discovery_map[name] = interfaces
                    
            except Exception as e:
                logger.error(f"Failed to discover pattern {pattern}: {e}")
        
        return discovery_map
    
    def write_topology_file(self, discovery_map, output_file='/tmp/topology.json'):
        # Convert to Casmella topology format
        pod_interfaces = {}
        
        for container, interfaces in discovery_map.items():
            # Create interface name to index mapping
            interface_dict = {}
            for iface in interfaces:
                ifname = iface.get('ifname', 'eth0')
                # In Docker, we don't have real ifindex, use dummy value
                # Casmella will work with container network namespace
                interface_dict[ifname] = 1
            
            pod_interfaces[container] = {
                'status': 'ADDED',
                'content': interface_dict,
                'node': 'docker-host'
            }
        
        topology = {
            'podInterfaces': pod_interfaces,
            'ipAddressInfos': {},
            'podInfos': {}
        }
        
        with open(output_file, 'w') as f:
            json.dump(topology, f, indent=2)
        
        logger.info(f"Topology written to {output_file}")
        logger.info(f"Discovered {len(pod_interfaces)} containers")

if __name__ == "__main__":
    discovery = DockerDiscovery()
    
    # Monitor OAI containers
    patterns = ['oai-amf', 'oai-smf', 'vpp-upf']
    
    while True:
        logger.info("Discovering containers...")
        discovery_map = discovery.discover_all_containers(patterns)
        discovery.write_topology_file(discovery_map)
        
        time.sleep(30)  # Update every 30 seconds