"""SDG main module.
"""
import argparse
import logging
import time
import json
import yaml
import flask
from flask import Flask, jsonify
from prom import PrometheusInstance

parser = argparse.ArgumentParser()
parser.add_argument('-c', '--config', default='../config/sdg-config.yaml',
                    help='Path to the config file')
args = parser.parse_args()

SafeLoader = yaml.loader.SafeLoader

app = Flask(__name__)


def load_configuration_file(config_file_path='../config/sdg-config.yaml') -> int:
    """Load and apply the configuration

    Args:
        config_file_path (str, optional): The path to the configuration file. Defaults to '../config/sdg-config.yaml'.

    Returns:
        int: The port number on which the SDG will be listening
    """
    global prom
    with open(config_file_path, encoding='utf8', errors='ignore') as openned_file:
        config_data = yaml.load(openned_file, Loader=SafeLoader)
        prom_address = config_data.get('prom_address',
            'prom-kube-prometheus-stack-prometheus.prometheus.svc.cluster.local:9090')
        sdg_port = config_data.get('sdg_port', 80)
    prom = PrometheusInstance(prom_address)
    return sdg_port


def calculate_graph(timestamp=None) -> dict:
    """Calculate a network graph based on metrics from a Prometheus instance.

    This function queries a Prometheus instance to gather metrics related to
    network protocol exchanges within a 5G environment. It constructs a graph
    where nodes represent servers (or other network entities), and edges
    represent communication links between these nodes. Each node and edge is
    enriched with metrics such as request rate, response latency, and success rate,
    both overall and for specific protocols (e.g., HTTP/2, PFCP, NGAP).

    Args:
        timestamp (str | float, optional): A Unix timestamp to use for the Prometheus queries. If not
        provided, the current time is used.

    Returns:
        dict: A dictionary containing two keys:
            - "nodes": A list of dictionaries, each representing a network node with \
            associated metrics. Each node dictionary contains:
                - `id` (str): The unique identifier of the node.
                - `title` (str): The name of the node.
                - `mainstat` (float): The main statistic (request rate) for the node.
                - `secondaryStat` (float): The 99th percentile of response time for the node.
                - `arc__failed` (float): The failure rate (1 - success rate) for the node.
                - `arc__passed` (float): The success rate for the node.
                - Protocol-specific details for request rate, response time, and success rate.
            - "edges": A list of dictionaries, each representing an edge (a communication link \
            between two nodes) with associated metrics. Each edge dictionary contains:
                - `id` (str): The unique identifier of the edge (combination of source and target \
                nodes).
                - `source` (str): The ID of the source node.
                - `target` (str): The ID of the target node.
                - `mainstat` (float): The main statistic (request rate) for the edge.
                - `secondaryStat` (float): The 99th percentile of response time for the edge.
                - Protocol-specific details for request rate, response time, and success rate.

    Notes:
        - The function is tailored for a 5G network monitoring use case but can be adapted for \
          other environments with similar metrics.
        - The Prometheus queries use a 5-minute rate window to calculate the metrics.
    """
    timestamp = time.time() if not timestamp else timestamp
    nodes = []
    edges = []
    nodes_ids = []
    #edges_ids = []
    _protocols = [
        'http2',
        'pfcp',
        'ngap',
    ]
    _queries = {
        'vertices-rate': 'sum(rate({__name__=~"casmella_5g_.*_requests_total"}[5m])) by (server_deployment_name)',
        'vertices-rate-protocol': 'sum(rate({__name__=~"casmella_5g_.*_requests_total"}[5m])) by (server_deployment_name, protocol)',
        'vertices-latency': 'histogram_quantile(0.99, sum(rate({__name__=~"casmella_5g_.*_response_time_ms_bucket"}[5m])) by (le, server_deployment_name))',
        'vertices-latency-protocol': 'histogram_quantile(0.99, sum(rate({__name__=~"casmella_5g_.*_response_time_ms_bucket"}[5m])) by (le, server_deployment_name, protocol))',
        'vertices-successrate': 'sum(rate({__name__=~"casmella_5g_.*_responses_total", status="success"}[5m]))by(server_deployment_name) / sum(rate({__name__=~"casmella_5g_.*_responses_total"}[5m]))by(server_deployment_name)',
        'vertices-successrate-protocol': 'sum(rate({__name__=~"casmella_5g_.*_responses_total", status="success"}[5m]))by(server_deployment_name, protocol) / sum(rate({__name__=~"casmella_5g_.*_responses_total"}[5m]))by(server_deployment_name, protocol)',
        'edges-rate': 'sum(rate({__name__=~"casmella_5g_.*_requests_total"}[5m])) by (server_deployment_name, client_deployment_name)',
        'edges-rate-protocol': 'sum(rate({__name__=~"casmella_5g_.*_requests_total"}[5m])) by (server_deployment_name, client_deployment_name, protocol)',
        'edges-latency': 'histogram_quantile(0.99, sum(rate({__name__=~"casmella_5g_.*_response_time_ms_bucket"}[5m])) by (le, server_deployment_name, client_deployment_name))',
        'edges-latency-protocol': 'histogram_quantile(0.99, sum(rate({__name__=~"casmella_5g_.*_response_time_ms_bucket"}[5m])) by (le, server_deployment_name, client_deployment_name, protocol))',
        'edges-successrate': 'sum(rate({__name__=~"casmella_5g_.*_responses_total", status="success"}[5m]))by(server_deployment_name, client_deployment_name) / sum(rate({__name__=~"casmella_5g_.*_responses_total"}[5m]))by(server_deployment_name, client_deployment_name)',
        'edges-successrate-protocol': 'sum(rate({__name__=~"casmella_5g_.*_responses_total", status="success"}[5m]))by(server_deployment_name, client_deployment_name, protocol) / sum(rate({__name__=~"casmella_5g_.*_responses_total"}[5m]))by(server_deployment_name, client_deployment_name, protocol)',
    }
    queries_results = {}
    # Perform queries
    for metric, query in _queries.items():
        queries_results[metric] = prom.instant_query(query=query, timestamp=timestamp)
        queries_results[metric] = list(queries_results[metric])
        queries_results[metric][0] = queries_results[metric][0].fillna(0.0)
    # Fetch server vertices
    df, err = queries_results['vertices-rate']
    if not err:
        for labelvalues, rate in df.items():
            vertice_name = json.loads(labelvalues)['server_deployment_name']
            vertice = {
                'id': vertice_name,
                'title': vertice_name,
                'mainstat': rate,
                'secondaryStat': queries_results['vertices-latency'][0].get(labelvalues, 0),
                'arc__failed': 1 - queries_results['vertices-successrate'][0].get(labelvalues, 0),
                'arc__passed': queries_results['vertices-successrate'][0].get(labelvalues, 0),
            }
            for protocol in _protocols:
                labelvalues_protocol = json.loads(labelvalues)
                labelvalues_protocol['protocol'] = protocol
                labelvalues_protocol = dict(sorted(labelvalues_protocol.items()))
                labelvalues_protocol = json.dumps(labelvalues_protocol)
                vertice[f'detail__{protocol}_requests_rate'] = queries_results['vertices-rate-protocol'][0].get(labelvalues_protocol, 0)
                vertice[f'detail__{protocol}_response_time'] = queries_results['vertices-latency-protocol'][0].get(labelvalues_protocol, 0)
                vertice[f'detail__{protocol}_success_rate'] = queries_results['vertices-successrate-protocol'][0].get(labelvalues_protocol, 0)
            nodes.append(vertice)
            nodes_ids.append(vertice_name)
    # Fetch edges and only-client vertices
    df, err = queries_results['edges-rate']
    if not err:
        for labelvalues, rate in df.items():
            server_name, client_name = json.loads(labelvalues)['server_deployment_name'], json.loads(labelvalues)['client_deployment_name']
            edge = {
                'id': labelvalues,
                'source': client_name,
                'target': server_name,
                'mainstat': rate,
                'secondaryStat': queries_results['edges-latency'][0].get(labelvalues, 0),
                'detail__success_rate': queries_results['edges-successrate'][0].get(labelvalues, 0),
            }
            for protocol in _protocols:
                labelvalues_protocol = json.loads(labelvalues)
                labelvalues_protocol['protocol'] = protocol
                labelvalues_protocol = dict(sorted(labelvalues_protocol.items()))
                labelvalues_protocol = json.dumps(labelvalues_protocol)
                edge[f'detail__{protocol}_requests_rate'] = queries_results['edges-rate-protocol'][0].get(labelvalues_protocol, 0)
                edge[f'detail__{protocol}_response_time'] = queries_results['edges-latency-protocol'][0].get(labelvalues_protocol, 0)
                edge[f'detail__{protocol}_success_rate'] = queries_results['edges-successrate-protocol'][0].get(labelvalues_protocol, 0)
            edges.append(edge)
            # Add vertices that are only clients
            if client_name not in nodes_ids:
                vertice = {
                    'id': client_name,
                    'title': client_name,
                    'mainstat': 0,
                    'secondaryStat': 0,
                    'arc__failed': 0,
                    'arc__passed': 1,
                }
                for protocol in _protocols:
                    vertice[f'detail__{protocol}_requests_rate'] = 0
                    vertice[f'detail__{protocol}_response_time'] = 0
                    vertice[f'detail__{protocol}_success_rate'] = 0
                nodes.append(vertice)
                nodes_ids.append(client_name)
    # Return results
    return {"nodes": nodes, "edges": edges}


@app.route('/api/graph/data-timestamped/<timestamp>')
def fetch_graph_data_timestamped(timestamp: str) -> flask.Response:
    """ API endpoint to fetch network graph data for a specific timestamp.

    This route allows clients to retrieve a graph representation of network protocol exchanges
    based on metrics collected at a specified timestamp. The graph data is generated using the
    `calculate_graph` function, which queries a Prometheus instance to gather relevant metrics.

    Args:
        timestamp (str): A string representing a Unix timestamp. This timestamp is passed to the
        `calculate_graph` function to retrieve metrics at the specific point in time.

    Returns:
        flask.Response: A JSON response containing the network graph data. The response includes:
            - "nodes": A list of dictionaries representing network nodes with associated metrics.
            - "edges": A list of dictionaries representing edges (communication links) between \
            nodes, with associated metrics.
    """
    return jsonify(calculate_graph(timestamp=timestamp))


@app.route('/api/graph/data')
def fetch_graph_data() -> flask.Response:
    """API endpoint to fetch the current network graph data.

    This route allows clients to retrieve a graph representation of the current network
    protocol exchanges. The graph data is generated using the `calculate_graph` function, which
    queries a Prometheus instance to gather relevant metrics at the current time.

    Returns:
        flask.Response: A JSON response containing the current network graph data. The response
        includes:

        - "nodes": A list of dictionaries representing network nodes with associated metrics \
        such as request rates, response times, and success rates.
        - "edges": A list of dictionaries representing edges (communication links) between \
        nodes, with associated metrics such as request rates, response times, and success \
        rates.
    """
    return jsonify(calculate_graph())


@app.route('/api/graph/fields')
def fetch_graph_fields() -> flask.Response:
    """
    API endpoint to retrieve the field definitions for nodes and edges in the network graph.

    This route provides clients with the schema for the graph data, detailing the fields used in
    the nodes and edges of the graph. Each field includes its name, type, and additional
    attributes such as display name or color coding when applicable.

    Returns:
        flask.Response: A JSON object containing two main sections:
            - "nodes_fields": A list of dictionaries, each representing a field in the nodes of
            the graph. Fields include:
                - "field_name": The name of the field.
                - "type": The data type of the field (e.g., "string", "number").
                - "color" (optional): The color associated with the field value (e.g., "red").
                - "displayName" (optional): A user-friendly name for the field.
            - "edges_fields": A list of dictionaries, each representing a field in the edges of
            the graph. Fields follow the same structure as node fields.

    Notes:
        - This endpoint is useful for clients that need to understand the structure of the graph data
          before processing or visualizing it.
    """
    nodes_fields = [
        {"field_name": "id", "type": "string"},
        {"field_name": "title", "type": "string"},
        {"field_name": "mainstat", "type": "number"},             # requests rate
        {"field_name": "secondaryStat", "type": "number"},        # response time
        {"field_name": "arc__failed", "type": "number", "color": "red"},
        {"field_name": "arc__passed", "type": "number", "color": "green"},
        #{"field_name": "detail__success_rate", "type": "number", "displayName": "Overall success rate"},
        {"field_name": "detail__http2_requests_rate", "type": "number", "displayName": "HTTP/2 requests rate"},
        {"field_name": "detail__http2_response_time", "type": "number", "displayName": "HTTP/2 response time"},
        {"field_name": "detail__http2_success_rate", "type": "number", "displayName": "HTTP/2 success rate"},
        {"field_name": "detail__pfcp_requests_rate", "type": "number", "displayName": "PFCP requests rate"},
        {"field_name": "detail__pfcp_response_time", "type": "number", "displayName": "PFCP response time"},
        {"field_name": "detail__pfcp_success_rate", "type": "number", "displayName": "PFCP success rate"},
        {"field_name": "detail__ngap_requests_rate", "type": "number", "displayName": "NGAP requests rate"},
        {"field_name": "detail__ngap_response_time", "type": "number", "displayName": "NGAP response time"},
        {"field_name": "detail__ngap_success_rate", "type": "number", "displayName": "NGAP success rate"},
    ]
    edges_fields = [
        {"field_name": "id", "type": "string"},
        {"field_name": "source", "type": "string"},
        {"field_name": "target", "type": "string"},
        {"field_name": "mainstat", "type": "number"},             # requests rate
        {"field_name": "secondaryStat", "type": "number"},        # response time
        {"field_name": "detail__success_rate", "type": "number", "displayName": "Overall success rate"},
        {"field_name": "detail__http2_requests_rate", "type": "number", "displayName": "HTTP/2 requests rate"},
        {"field_name": "detail__http2_response_time", "type": "number", "displayName": "HTTP/2 response time"},
        {"field_name": "detail__http2_success_rate", "type": "number", "displayName": "HTTP/2 success rate"},
        {"field_name": "detail__pfcp_requests_rate", "type": "number", "displayName": "PFCP requests rate"},
        {"field_name": "detail__pfcp_response_time", "type": "number", "displayName": "PFCP response time"},
        {"field_name": "detail__pfcp_success_rate", "type": "number", "displayName": "PFCP success rate"},
        {"field_name": "detail__ngap_requests_rate", "type": "number", "displayName": "NGAP requests rate"},
        {"field_name": "detail__ngap_response_time", "type": "number", "displayName": "NGAP response time"},
        {"field_name": "detail__ngap_success_rate", "type": "number", "displayName": "NGAP success rate"},
    ]
    result = {
        "nodes_fields": nodes_fields,
        "edges_fields": edges_fields
    }
    return jsonify(result)


@app.route('/api/health')
def check_health() -> str:
    """API endpoint for health check.

    This route is used to determine if the application is running and responsive.
    It's often used by load balancers or monitoring tools to check the health status
    of the application.

    Returns:
        str: A simple confirmation message indicating the health status of the application. The
        message "Health check passed!" signifies that the application is operational.
    """
    return "Health check passed!"


def main():
    """The main entry point of the Flask application.

    This function initializes and starts the Flask web server, allowing it to listen for
    incoming HTTP requests on all network interfaces (`0.0.0.0`) and on port 80. This setup
    is suitable for deployment in environments where the application should be accessible
    from other machines or services within the same network.

    Notes:
        - Running the application on `0.0.0.0` makes it accessible externally, which is
          necessary for a Kubernetes deployment.
    """
    sdg_port = load_configuration_file(args.config)
    app.run(host='0.0.0.0', port=sdg_port)


if __name__ == '__main__':
    main()
