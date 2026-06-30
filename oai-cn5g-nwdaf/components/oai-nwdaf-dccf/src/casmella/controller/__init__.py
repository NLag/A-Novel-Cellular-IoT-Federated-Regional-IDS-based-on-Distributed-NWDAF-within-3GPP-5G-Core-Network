"""The Casmella's Controller is responsible for the service discovery. To do so, it periodically
communicates with the Kubernetes API to retrieve information about the 5G microservices and their
networks. We recall that the deployment unit under Kubernetes is called Pod. It corresponds to a
logical representation of the desired state of one or more containers.

For each created Pod, Kubernetes will call the underlying container runtime (e.g.,  Docker,
Containerd, etc.), through the CRI (Container Runtime Interface), in order to create the Pod's
containers.
This step also includes the creation of a network namespace dedicated to the containers
belonging to the Pod, in order to ensure network resource isolation.
At this stage, the network namespace is created but is still empty.
This is where Kubernetes is going to call a networking plugin,
through the CNI (Container Network Interface),
in order to  i) create the network interfaces in the Pods network namespaces and
ii) apply the necessary network configuration so that a Pod can communicate with the network.
Specifically, the networking plugin creates a veth (virtual Ethernet) pair and inserts
one end of this pair into the Pod network namespace and the other end to a bridge
on the host network namespace.

Note also that Pods are low-level Kubernetes objects.
They are generally  managed by other high-level Kubernetes objects (e.g., Deployments,
Replicasets, Statefulsets, Daemonsets, etc.) in order to facilitate the operations of
autoscaling, upgrades, auto-healing, data persistence, etc.

In this context, the Casmella's Controller dynamically discovers Pods belonging to a 5G service,
based on pre-defined label-based filtering.
Then, it collects detailed information about each Pod before making it available
to the Casmella's Agent.
This information includes the names of Kubernetes high-level objects managing the Pod,
as well as other network-related information such as IP addresses of
the Pod's network interfaces and their peer in the host network namespace.
"""
