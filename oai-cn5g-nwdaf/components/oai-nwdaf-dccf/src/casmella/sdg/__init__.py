"""
The SDG periodically retrieves metrics on 5G network traffic from the Prometheus API and builds a
dependency graph. The latter is defined by a set of nodes and edges corresponding respectively to
the 5G microservices and theirs links. The graph information is exposed in real-time via an API.
"""
