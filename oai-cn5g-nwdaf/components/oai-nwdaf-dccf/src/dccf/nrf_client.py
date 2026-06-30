#!/usr/bin/env python3
"""
NRF Client for NWDAF-DCCF NF Registration
Implements 3GPP TS 29.510 NFManagement API
"""
import logging
import asyncio
import os
import json
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

class NRFClient:
    """NRF Client for NF Registration and Heartbeat"""

    def __init__(self, config: dict):
        self.nrf_endpoint = config.get('nrf', {}).get('endpoint', '')
        self.auto_register = config.get('nrf', {}).get('auto_register', False)
        self.heartbeat_interval = config.get('nrf', {}).get('heartbeat_interval', 10)

        # NWDAF NF Profile
        nwdaf_config = config.get('nwdaf', {})
        self.nf_instance_id = nwdaf_config.get('nfInstanceId', '58f8ec8c-8a94-5ab1-86f6-7c989cb0cb74')
        self.nf_type = nwdaf_config.get('nfType', 'NWDAF')
        self.ipv4_address = nwdaf_config.get('ipv4Address') or os.getenv('POD_IP', '')
        self.nf_services = nwdaf_config.get('nfServices', [])

        self._registered = False
        self._heartbeat_task: Optional[asyncio.Task] = None

    def _curl_json(self, method: str, url: str, payload=None, content_type: str = "application/json") -> tuple[int, str, str]:
        """
        Send a JSON request to OAI NRF using HTTP/2 prior knowledge.

        The OAI NRF h2c endpoint closes plain HTTP/1.1 requests without a
        response. Python's standard clients do not support h2c prior knowledge,
        so use curl in the same way as the DCCF AMF/SMF subscription client.
        """
        cmd = [
            "curl",
            "--http2-prior-knowledge",
            "-sS",
            "-w",
            "\n%{http_code}",
            "-X",
            method,
            "-H",
            f"Content-Type: {content_type}",
            "-H",
            "Accept: application/json",
        ]

        if payload is not None:
            cmd.extend(["-d", json.dumps(payload)])

        cmd.append(url)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        stdout = result.stdout or ""
        if "\n" in stdout:
            body, status_text = stdout.rsplit("\n", 1)
        else:
            body, status_text = "", stdout

        try:
            status_code = int(status_text.strip())
        except ValueError:
            status_code = 0

        if result.returncode != 0 and status_code == 0:
            raise RuntimeError(result.stderr.strip() or f"curl exited with {result.returncode}")

        return status_code, body, result.stderr

    def _build_nf_profile(self) -> dict:
        """Build 3GPP compliant NF Profile for registration"""
        return {
            "nfInstanceId": self.nf_instance_id,
            "nfType": self.nf_type,
            "nfStatus": "REGISTERED",
            "heartBeatTimer": self.heartbeat_interval,
            "ipv4Addresses": [self.ipv4_address] if self.ipv4_address else [],
            "nfServices": self._build_nf_services(),
            "nwdafInfo": {
                "eventIds": [
                    "NF_LOAD",
                    "UE_MOBILITY",
                    "UE_COMM",
                    "QOS_SUSTAINABILITY",
                    "ABNORMAL_BEHAVIOUR"
                ],
                "nwdafEvents": [
                    "NF_LOAD",
                    "UE_MOBILITY"
                ]
            }
        }

    def _build_nf_services(self) -> list:
        """Build NF Services list for registration"""
        services = []
        for svc in self.nf_services:
            service = {
                "serviceInstanceId": svc.get('serviceInstanceId', ''),
                "serviceName": svc.get('serviceName', ''),
                "versions": svc.get('versions', []),
                "scheme": svc.get('scheme', 'http'),
                "nfServiceStatus": "REGISTERED"
            }

            # Add IP endpoints
            ip_endpoints = svc.get('ipEndPoints', [])
            if ip_endpoints:
                normalized_endpoints = []
                for endpoint in ip_endpoints:
                    normalized_endpoint = dict(endpoint)
                    if not normalized_endpoint.get("ipv4Address") and self.ipv4_address:
                        normalized_endpoint["ipv4Address"] = self.ipv4_address
                    normalized_endpoints.append(normalized_endpoint)
                service["ipEndPoints"] = normalized_endpoints

            services.append(service)
        return services

    async def register(self) -> bool:
        """Register NWDAF-DCCF with NRF"""
        if not self.auto_register:
            logger.info("NRF auto-registration disabled")
            return False

        if not self.nrf_endpoint:
            logger.warning("NRF endpoint not configured")
            return False

        nf_profile = self._build_nf_profile()
        url = f"{self.nrf_endpoint}/nnrf-nfm/v1/nf-instances/{self.nf_instance_id}"

        logger.info(f"Registering with NRF at {url}")
        logger.debug(f"NF Profile: {nf_profile}")

        try:
            status_code, body, stderr = await asyncio.to_thread(
                self._curl_json,
                "PUT",
                url,
                nf_profile,
            )

            if status_code in [200, 201]:
                self._registered = True
                logger.info(f"Successfully registered with NRF (status: {status_code})")

                # Start heartbeat
                await self._start_heartbeat()
                return True

            logger.error(f"NRF registration failed: {status_code} - {body or stderr}")
            return False

        except Exception as e:
            logger.error(f"NRF registration error: {e}")
            return False

    async def deregister(self) -> bool:
        """Deregister from NRF"""
        if not self._registered:
            return True

        # Stop heartbeat
        if self._heartbeat_task:
            self._heartbeat_task.cancel()

        url = f"{self.nrf_endpoint}/nnrf-nfm/v1/nf-instances/{self.nf_instance_id}"

        try:
            status_code, body, stderr = await asyncio.to_thread(
                self._curl_json,
                "DELETE",
                url,
            )

            if status_code in [200, 204]:
                self._registered = False
                logger.info("Successfully deregistered from NRF")
                return True

            logger.error(f"NRF deregistration failed: {status_code} - {body or stderr}")
            return False

        except Exception as e:
            logger.error(f"NRF deregistration error: {e}")
            return False

    async def _start_heartbeat(self):
        """Start heartbeat task"""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self):
        """Send periodic heartbeats to NRF"""
        while self._registered:
            await asyncio.sleep(self.heartbeat_interval)

            if not self._registered:
                break

            url = f"{self.nrf_endpoint}/nnrf-nfm/v1/nf-instances/{self.nf_instance_id}"

            try:
                # PATCH with heartbeat update
                patch_data = [
                    {
                        "op": "replace",
                        "path": "/nfStatus",
                        "value": "REGISTERED"
                    }
                ]
                status_code, body, stderr = await asyncio.to_thread(
                    self._curl_json,
                    "PATCH",
                    url,
                    patch_data,
                    "application/json-patch+json",
                )

                if status_code in [200, 204]:
                    logger.debug("NRF heartbeat successful")
                elif status_code == 404:
                    logger.warning("NF not found in NRF, re-registering...")
                    await self.register()
                else:
                    logger.warning(f"NRF heartbeat failed: {status_code} - {body or stderr}")

            except Exception as e:
                logger.error(f"NRF heartbeat error: {e}")

    @property
    def is_registered(self) -> bool:
        return self._registered
