"""Agent's core package.

This package implements the main logic of the Agent. It implements various functions for
communicating with Kubernetes API to retrieve data discovered by the Controller.

The Agent implements a closed loop that looks at the content of the custom resource and applies
the necessary actions. It copies `ipAddressInfos` and `podInfos` hashmaps directly into Python
dictionaries, allowing a fast access to the mapped data with an average time-complexity of O(1).

The entries in the `podInterfaces` hashmap are treated differently. We recall that the Agent is
deployed as a Kubernetes Daemonset, ensuring the presence of an instance on each node of the
Kubernetes cluster. Each instance shares the same Kernel with all the other Pods running on its node and therefore
will be able via eBPF to monitor the incoming and outgoing traffic of these Pods. To do so, it
selects the entries in `podInterfaces` corresponding to the node on which it is deployed and then performs the necessary operations for the entries that are not yet processed
(i.e. status is different from `HANDLED`).

Specifically, for the entries with status `ADDED`, the Agent instance takes care of attaching the
eBPF programs to all the interfaces in order to start monitoring the network traffic passing
through these interfaces. Then, it updates the status of the entries to `HANDLED` or `FAILED`
according to the result of the eBPF programs attachment operation.
For entries with a `DELETED` status, the Agent instance takes care of detaching the eBPF programs
monitoring and deleting the metrics concerning these Pods, in order to minimize the costs of
exposing and storing the metrics.

Each Agent instance also implements a cleaning function that runs at termination time. This
function takes care of stopping the closed loop described above, detaching the eBPF programs
concerning the entries with a `HANDLED` status and updating their status to `CLEANED` in order to
inform the system that they are no longer handled. By doing so, the Agent is robust to any kind
of failure (e.g. failures by the underlying infrastructure or the Kubernetes platform). Indeed,
in case of failure of an Agent instance, the cleaning function will have cleaned the underlying
infrastructure (detaching all eBPF programs) and will have restored the data in `topology` CR.
Then, the Kubernetes orchestrator takes care of the recovery service by launching a new instance
that will be able to provide the expected functionality by retrieving the data stored in the
`topology` CR.
"""
