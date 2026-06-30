"""
Controller's metrics module
"""
# standard
import logging
# third-pary
import uvicorn
from fastapi import FastAPI
from prometheus_client import make_asgi_app
from prometheus_client import Counter, Info
# from prometheus_client import Gauge, Summary
from prometheus_client import REGISTRY, PROCESS_COLLECTOR, PLATFORM_COLLECTOR, GC_COLLECTOR


# ==============================================================
# Metric-related variables
# ==============================================================
# Primitives
primitives_called = Counter(
    'casmella_controller_primitives_called',
    'Total number of Python methods calls (useful for debugging)',
    [
        'primitive'
    ]
)
# Pods Events
pods_events = Counter(
    'casmella_controller_pods_events', "Total number of Pods' events",
    [
        'event',
        'pod_hash',
        'pod_namespace',
        'replicaset_name',
        'deployment_name',
        'statefulset_name',
        'node_name',
        'cluster_name',
    ]
)
# Pods information
pods_information = Info(
    'casmella_controller_pods_information', 'Description of discovered Pods',
    [
        'pod_name',
    ]
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
# ==============================================================
def clear_prometheus_metrics_for_pod(pod_name: str):
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
        pods_information
    ]
    for _metric in metrics_list:
        with _metric._lock:
            label_values_list = []
            for labelvalues in _metric._metrics.keys():
                if pod_name in labelvalues:
                    label_values_list.append(labelvalues)
            for labelvalues in label_values_list:
                del _metric._metrics[labelvalues]
