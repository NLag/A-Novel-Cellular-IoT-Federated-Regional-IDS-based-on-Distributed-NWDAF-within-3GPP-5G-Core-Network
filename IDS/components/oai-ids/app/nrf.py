from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import socket
import subprocess
import threading
import time


LOGGER = logging.getLogger("oai.ids.nrf")


@dataclass
class NrfRegistration:
    base_uri: str
    nf_instance_id: str
    nf_type: str
    nf_status: str
    service_name: str
    service_version: str
    heart_beat_timer: int
    host: str
    pod_ip: str
    http_port: int
    serving_region: str = "default"
    serving_tac: str = "000001"

    @property
    def resource_uri(self) -> str:
        return f"{self.base_uri.rstrip('/')}/nf-instances/{self.nf_instance_id}"

    def payload(self) -> dict:
        return {
            "nfInstanceId": self.nf_instance_id,
            "nfType": self.nf_type,
            "nfStatus": self.nf_status,
            "heartBeatTimer": self.heart_beat_timer,
            "fqdn": self.host,
            "ipv4Addresses": [self.pod_ip],
            "priority": 1,
            "capacity": 100,
            "load": 0,
            "customInfo": {
                "idsServingRegion": self.serving_region,
                "idsServingTac": self.serving_tac,
            },
            "nfServices": [
                {
                    "serviceInstanceId": f"{self.nf_instance_id}-http",
                    "serviceName": self.service_name,
                    "versions": [
                        {
                            "apiVersionInUri": self.service_version,
                            "apiFullVersion": "1.0.0",
                        }
                    ],
                    "scheme": "http",
                    "nfServiceStatus": "REGISTERED",
                    "ipEndPoints": [
                        {
                            "ipv4Address": self.pod_ip,
                            "port": self.http_port,
                            "transport": "TCP",
                        }
                    ],
                }
            ],
        }


class NrfClient:
    def __init__(self, registration: NrfRegistration):
        self.registration = registration

    def register(self) -> None:
        self._run(
            [
                "curl",
                "--silent",
                "--show-error",
                "--fail-with-body",
                "--http2-prior-knowledge",
                "-X",
                "PUT",
                self.registration.resource_uri,
                "-H",
                "Content-Type: application/json",
                "--data-binary",
                json.dumps(self.registration.payload()),
            ]
        )
        LOGGER.info("registered IDS NF instance %s with NRF", self.registration.nf_instance_id)

    def deregister(self) -> None:
        try:
            self._run(
                [
                    "curl",
                    "--silent",
                    "--show-error",
                    "--fail-with-body",
                    "--http2-prior-knowledge",
                    "-X",
                    "DELETE",
                    self.registration.resource_uri,
                ]
            )
            LOGGER.info(
                "deregistered IDS NF instance %s from NRF",
                self.registration.nf_instance_id,
            )
        except Exception as exc:  # pragma: no cover - shutdown best effort
            LOGGER.warning("failed to deregister IDS NF from NRF: %s", exc)

    def wait_until_registered(self, ready_event: threading.Event, stop_event: threading.Event) -> None:
        delay_seconds = 1.0
        while not stop_event.is_set():
            try:
                self.register()
                ready_event.set()
                return
            except Exception as exc:
                LOGGER.warning("NRF registration attempt failed: %s", exc)
                stop_event.wait(delay_seconds)
                delay_seconds = min(delay_seconds * 2.0, 10.0)

    @staticmethod
    def _run(command: list[str]) -> None:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            details = " ".join(
                item
                for item in (result.stderr.strip(), result.stdout.strip())
                if item
            )
            raise RuntimeError(details or "unknown error")


def discover_pod_ip(host: str) -> str:
    if pod_ip := socket.gethostbyname_ex(socket.gethostname())[2]:
        for address in pod_ip:
            if "." in address:
                return address
    return socket.gethostbyname(host)
