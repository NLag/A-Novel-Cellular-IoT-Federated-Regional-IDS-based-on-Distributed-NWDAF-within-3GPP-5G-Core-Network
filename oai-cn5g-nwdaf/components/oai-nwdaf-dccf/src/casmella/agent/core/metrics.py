"""Metrics module.
"""
# standard
import logging
# third-pary
import uvicorn
from fastapi import FastAPI
from prometheus_client import make_asgi_app
from prometheus_client import make_wsgi_app
from prometheus_client import Counter, Histogram
# from prometheus_client import Gauge, Summary
from prometheus_client import REGISTRY, PROCESS_COLLECTOR, PLATFORM_COLLECTOR, GC_COLLECTOR


# ==============================================================
# Common variables
one_endpoint_labels = [
    'ip_addr',
    'pod_name',
    'interface_name',
    'pod_hash',
    'pod_namespace',
    'replicaset_name',
    'deployment_name',
    'statefulset_name',
    'node_name',
    'cluster_name',
]
server_and_client_labels = [f'server_{key}' for key in one_endpoint_labels]
server_and_client_labels.extend([f'client_{key}' for key in one_endpoint_labels])
source_and_destination_labels = [f'src_{key}' for key in one_endpoint_labels]
source_and_destination_labels.extend([f'dst_{key}' for key in one_endpoint_labels])

# ==============================================================
# Metric-related variables
# primitives
primitives_called = Counter(
    'casmella_agent_primitives_called',
    'Total number of Python methods calls (useful for debugging)',
    [
        'primitive'
    ]
)
# eBPF programs
ebpf_programs_attached = Counter(
    'casmella_agent_ebpf_programs_attached', 'Total number of attached eBPF programs',
    [
        'interface',
        'type',
        'direction',
    ]
)
# HTTP
http_requests = Counter(
    'casmella_5g_http_requests', 'Total number of HTTP requests',
    [
        'protocol',
        'rr',
        'operationId',
        'scheme',
        'method',
    ] + server_and_client_labels
)
http_responses = Counter(
    'casmella_5g_http_responses', 'Total number of HTTP responses',
    [
        'protocol',
        'rr',
        'operationId',
        'status',
        'status_code',
    ] + server_and_client_labels
)
http_response_time = Histogram(
    'casmella_5g_http_response_time_ms', 'A histogram of HTTP response times',
    [
        'protocol',
        'rr',
        'operationId',
        'status',
        'status_code',
    ] + server_and_client_labels,
    buckets=[2.5, 5.0, 10.0, 25.0, 50.0, 75.0, 100.0, 250.0,
             500.0, 750.0, 1000.0, 2500.0, 5000.0, 10000.0]
)
# PFCP
pfcp_requests = Counter(
    'casmella_5g_pfcp_requests', 'Total number of PFCP requests',
    [
        'protocol',
        'rr',
        'procedure_related_to',
        'message_type',
    ] + server_and_client_labels
)
pfcp_responses = Counter(
    'casmella_5g_pfcp_responses', 'Total number of PFCP responses',
    [
        'protocol',
        'rr',
        'procedure_related_to',
        'message_type',
        'status',
        'cause',
    ] + server_and_client_labels
)
pfcp_response_time = Histogram(
    'casmella_5g_pfcp_response_time_ms', 'A histogram of PFCP response times',
    [
        'protocol',
        'rr',
        'procedure_related_to',
        'message_type',
        'status',
        'cause',
    ] + server_and_client_labels,
    buckets=[2.5, 5.0, 10.0, 25.0, 50.0, 75.0, 100.0, 250.0,
             500.0, 750.0, 1000.0, 2500.0, 5000.0, 10000.0]
)
# NGAP
ngap_requests = Counter(
    'casmella_5g_ngap_requests', 'Total number of NGAP requests',
    [
        'protocol',
        'rr',
        'procedure_code',
        'procedure',
        'procedure_class',
        'message_type',
        'cause_layer',
        'cause',
    ] + server_and_client_labels
)
ngap_responses = Counter(
    'casmella_5g_ngap_responses', 'Total number of NGAP responses',
    [
        'protocol',
        'rr',
        'procedure_code',
        'procedure',
        'procedure_class',
        'message_type',
        'cause_layer',
        'cause',
        'status',
    ] + server_and_client_labels
)
ngap_response_time = Histogram(
    'casmella_5g_ngap_response_time_ms', 'A histogram of NGAP response times',
    [
        'protocol',
        'rr',
        'procedure_code',
        'procedure',
        'procedure_class',
        'message_type',
        'cause_layer',
        'cause',
        'status',
    ] + server_and_client_labels,
    buckets=[2.5, 5.0, 10.0, 25.0, 50.0, 75.0, 100.0, 250.0,
             500.0, 750.0, 1000.0, 2500.0, 5000.0, 10000.0]
)
# NAS
nas_messages = Counter(
    'casmella_5g_nas_messages', 'Total number of NAS messages',
    [
        'protocol',
        'message_type_int',
        'message_type',
        'registration_type',
        'cause',
        'ngap_procedure',
    ] + source_and_destination_labels
)
# UE procedures
ue_registration_time = Histogram(
    'casmella_5g_ue_registration_time_ms', 'A histogram of UE registration times',
    [
        'protocol',
        'message_type_int',
        'message_type',
        'registration_type',
        'cause',
        'ngap_procedure',
    ] + one_endpoint_labels,
    buckets=[200.0, 250.0, 300.0, 350.0, 400.0, 450.0, 500.0, 600.0,
             700.0, 800.0, 900.0, 1000.0, 1200.0, 1400.0, 1600.0, 1800.0,
             2000.0, 2333.0, 2666.0, 3000.0, 5000.0, 10000.0]
)
# QoS
qos_flows = Counter(
    'casmella_5g_qos_flows', 'Total number of QoS flows',
    [
        'action',
        'fiveqi_type',
        'fiveqi_value'
    ]
)
# GTP-U
gtpu_messages = Counter(
    'casmella_5g_gtpu_messages', 'Total number of GTP-U messages',
    [
        'protocol',
        'direction',
        'session_type',
        'fiveqi',
        'fiveqi_type',
        # 'dscp',
        'message_type_int',
        'message_type',
    ] + server_and_client_labels
)
gtpu_bytes = Histogram(
    'casmella_5g_gtpu_bytes', 'A histogram of GTP-U messages size',
    [
        'protocol',
        'direction',
        'session_type',
        'fiveqi',
        'fiveqi_type',
        # 'dscp',
        'message_type_int',
        'message_type',
    ] + server_and_client_labels
)

# IPv4 on UPF N6 interface
n6_ip_packets = Counter(
    'casmella_5g_n6_ip_packets', 'Total number of IP packets on N6 interface',
    [
        'protocol',
        'direction',
        'dscp',
    ] + one_endpoint_labels
)
n6_ip_bytes = Histogram(
    'casmella_5g_n6_ip_bytes', 'A histogram of IP packets length on N6 interface',
    [
        'protocol',
        'direction',
        'dscp',
    ] + one_endpoint_labels
)

# UPF
upf_forwarding_time = Histogram(
    'casmella_5g_upf_forwarding_time_ms', 'A histogram of UPF forwarding times',
    [
        'session_type',
        'direction',
    ] + one_endpoint_labels
)


# ==============================================================
# Prometheus-related variables
# ==============================================================
PROM_PORT = 9950
# Disable default Prometheus metrics
REGISTRY.unregister(GC_COLLECTOR)
REGISTRY.unregister(PLATFORM_COLLECTOR)
REGISTRY.unregister(PROCESS_COLLECTOR)
# REGISTRY.unregister(REGISTRY._names_to_collectors['python_gc_objects_collected_total'])

# Prometheus server
logging.getLogger("uvicorn.access").disabled = True
logging.getLogger("uvicorn.error").disabled = True
app = FastAPI(debug=False)
# Add prometheus asgi middleware to route /metrics requests
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/health")
async def health_check() -> str:
    """API endpoint for health check.

    This route is used to determine if the application is running and responsive.
    It's often used by load balancers or monitoring tools to check the health status
    of the application.

    Returns:
        str: A simple confirmation message indicating the health status of the application. The
        message "Health check passed!" signifies that the application is operational.
    """
    return "Health check passed!"


def start_prometheus_endpoint():
    """Run the Prometheus endpoint to expose the metrics.
    """
    uvicorn.run(app, host='0.0.0.0', port=PROM_PORT, log_level='error')


# ==============================================================
# Prometheus-related functions
def clear_prometheus_metrics_for_pod(pod_name):
    """Clear all Prometheus metrics related to a pod.

    This function clears all the Prometheus metrics associated with a specific pod.
    It iterates through a predefined list of metrics, and for each metric, it acquires the lock
    to ensure thread safety, finds all metric labels that include the pod name, and deletes those
    metrics.

    Clearing metrics for deleted pods helps save memory and optimize the collection operation.

    Args:
        pod_name (str): The Pod for which the metrics will be cleared
    """
    metrics_list = [
        http_requests,
        http_responses,
        http_response_time,
        nas_messages,
        ue_registration_time,
        qos_flows,
        ngap_requests,
        ngap_response_time,
        pfcp_requests,
        pfcp_responses,
        pfcp_response_time,
        gtpu_messages,
        gtpu_bytes,
        n6_ip_packets,
        n6_ip_bytes,
        upf_forwarding_time
    ]
    for _metric in metrics_list:
        with _metric._lock:
            label_values_list = []
            for labelvalues in _metric._metrics.keys():
                if pod_name in labelvalues:
                    label_values_list.append(labelvalues)
            for labelvalues in label_values_list:
                del _metric._metrics[labelvalues]
