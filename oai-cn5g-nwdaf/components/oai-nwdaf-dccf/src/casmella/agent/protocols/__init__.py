"""Protocol analysis package.

This package implements various classes and functions for protocol analysis of 5G exchanges,
including the reporting of metrics and logs.

The user-space part of the agent implements a list of primitives allowing the management of events
pushed by the kernel-space part. Specifically, the user-space agent periodically reads the events
in the Ring buffers and calls for each event a primitive to process it, according to the identified
protocol.

The implemented primitives do on the one hand protocol analysis on the advanced network packet in
order to extract interesting information that are highly dependent on the used protocol (e.g.
method, scheme, path, status code, and operationId for HTTP/2 and message type, procedure code for
NGAP, etc.). This operation requires taking into account certain complexities (compression of
HTTP/2 headers using HPACK algorithm, encoding of NGAP messages based on ASN1, etc.), which would
not be possible at the kernel level because of its limitations.

On the other hand, they extract information about the 2 Kubernetes Pods that are part of the
network exchange to be handled. This is done by matching the IP addresses extracted from the
network packet to the Kubernetes Pods and then retrieving information about the Pods through the
`ipAddressInfos` and `podInfos` hashmaps respectively. Then, the primitives write logs from
extracted data and update the corresponding metrics. The latter include metrics for observing the
protocols themselves (e.g. message counts, request and response counts, and response time
observations) and metrics related to the 5G system (e.g. UE registration time, QoS flow counts,
and time required for the UPF to forward packets between the N3 and N6 interfaces in both
directions).
"""
