#!/usr/bin/env python3
"""
NRF Client for MTLF (Model Training Logical Function)
Registers the MTLF with the NRF as an NWDAF instance per 3GPP TS 29.510.

Service name: nnwdaf-mlmodelprovision  (TS 29.520 Table 6.1.3.2-1)
NF Type:      NWDAF                    (TS 29.510 §6.1.6.2.18)

The MTLF is a logical sub-function of NWDAF (TS 23.288 §6.2A).
It registers with nfType=NWDAF and exposes the nnwdaf-mlmodelprovision service.
"""
import asyncio
import json
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class NRFClient:
    """NRF Client for MTLF NF Registration and Heartbeat"""

    def __init__(self, config: dict):
        self.nrf_endpoint = config.get("nrf", {}).get("endpoint", "")
        self.auto_register = config.get("nrf", {}).get("auto_register", False)
        self.heartbeat_interval = config.get("nrf", {}).get("heartbeat_interval", 30)

        mtlf_cfg = config.get("mtlf", {})
        self.nf_instance_id = mtlf_cfg.get("nfInstanceId", "nwdaf-mtlf-001")
        self.nf_type = mtlf_cfg.get("nfType", "NWDAF")
        self.ipv4_address = mtlf_cfg.get("ipv4Address") or os.getenv("POD_IP", "")
        self.nf_services = mtlf_cfg.get("nfServices", [])

        self._registered = False
        self._heartbeat_task: Optional[asyncio.Task] = None

    def _curl_json(
        self,
        method: str,
        url: str,
        payload=None,
        content_type: str = "application/json",
    ) -> tuple[int, str, str]:
        """
        Send JSON to OAI NRF using HTTP/2 prior knowledge.

        The OAI NRF h2c endpoint closes plain HTTP/1.1 requests without a
        response. Python HTTP clients used here do not support h2c prior
        knowledge, so match the working DCCF NRF client and use curl.
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
            raise RuntimeError(
                result.stderr.strip() or f"curl exited with {result.returncode}"
            )
        return status_code, body, result.stderr

    def _build_nf_profile(self) -> dict:
        """
        Build 3GPP-compliant NF Profile for MTLF registration.
        MTLF registers as nfType=NWDAF with service nnwdaf-mlmodelprovision.

        NwdafInfo.mlAnalyticsList per TS 29.510 Table 6.1.6.2.18-1:
          mlEvent  — NwdafEvent (TS 29.520 Table 6.3.3.3-1), no custom strings
          nfType   — optional, identifies the target NF type for analytics

        NOTE: 'accuracy' is NOT a field of MlAnalyticsInfo in TS 29.510 —
        it belongs in the MLModelInfo notification payload only.
        """
        return {
            "nfInstanceId": self.nf_instance_id,
            "nfType":       self.nf_type,           # "NWDAF"
            "nfStatus":     "REGISTERED",
            "heartBeatTimer": self.heartbeat_interval,
            "ipv4Addresses": [self.ipv4_address] if self.ipv4_address else [],
            "nfServices":   self._build_nf_services(),
            # NwdafInfo per TS 29.510 Table 6.1.6.2.18-1
            "nwdafInfo": {
                "analyticsDelay": 0,
                # mlAnalyticsList: list of MlAnalyticsInfo
                # mlEvent must be a standardized NwdafEvent (TS 29.520 Table 6.3.3.3-1)
                # IDS packet-classification models detect abnormal behaviour.
                "mlAnalyticsList": [
                    {
                        "mlEvent": "ABNORMAL_BEHAVIOUR",
                        "nfType":  "NWDAF",
                    },
                    {
                        "mlEvent": "NF_LOAD",
                        "nfType":  "NWDAF",
                    },
                    {
                        "mlEvent": "UE_MOBILITY",
                        "nfType":  "NWDAF",
                    },
                ]
            },
        }

    def _build_nf_services(self) -> list:
        services = []
        for svc in self.nf_services:
            service = {
                "serviceInstanceId": svc.get("serviceInstanceId", ""),
                # TS 29.520 Table 6.1.3.2-1: service name is nnwdaf-mlmodelprovision
                "serviceName": svc.get("serviceName", "nnwdaf-mlmodelprovision"),
                "versions": svc.get("versions", []),
                "scheme": svc.get("scheme", "http"),
                "nfServiceStatus": "REGISTERED",
            }
            if svc.get("ipEndPoints"):
                normalized_endpoints = []
                for endpoint in svc["ipEndPoints"]:
                    normalized_endpoint = dict(endpoint)
                    if not normalized_endpoint.get("ipv4Address") and self.ipv4_address:
                        normalized_endpoint["ipv4Address"] = self.ipv4_address
                    normalized_endpoints.append(normalized_endpoint)
                service["ipEndPoints"] = normalized_endpoints
            services.append(service)
        return services

    async def register(self) -> bool:
        if not self.auto_register:
            logger.info("NRF auto-registration disabled")
            return False
        if not self.nrf_endpoint:
            logger.warning("NRF endpoint not configured")
            return False

        url = f"{self.nrf_endpoint}/nnrf-nfm/v1/nf-instances/{self.nf_instance_id}"
        profile = self._build_nf_profile()
        logger.info(f"Registering MTLF with NRF at {url}")

        try:
            status_code, body, stderr = await asyncio.to_thread(
                self._curl_json,
                "PUT",
                url,
                profile,
            )
            if status_code in [200, 201]:
                self._registered = True
                logger.info(f"MTLF registered with NRF (status {status_code})")
                await self._start_heartbeat()
                return True

            logger.error(f"NRF registration failed: {status_code} — {body or stderr}")
            return False
        except Exception as e:
            logger.error(f"NRF registration error: {e}")
            return False

    async def deregister(self) -> bool:
        if not self._registered:
            return True
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
                logger.info("MTLF deregistered from NRF")
                return True

            logger.error(f"NRF deregistration failed: {status_code} — {body or stderr}")
            return False
        except Exception as e:
            logger.error(f"NRF deregistration error: {e}")
            return False

    async def _start_heartbeat(self):
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self):
        while self._registered:
            await asyncio.sleep(self.heartbeat_interval)
            if not self._registered:
                break
            url = f"{self.nrf_endpoint}/nnrf-nfm/v1/nf-instances/{self.nf_instance_id}"
            try:
                patch_data = [
                    {"op": "replace", "path": "/nfStatus", "value": "REGISTERED"}
                ]
                status_code, body, stderr = await asyncio.to_thread(
                    self._curl_json,
                    "PATCH",
                    url,
                    patch_data,
                    "application/json-patch+json",
                )
                if status_code in [200, 204]:
                    logger.debug("NRF heartbeat OK")
                elif status_code == 404:
                    logger.warning("MTLF not found in NRF, re-registering...")
                    await self.register()
                else:
                    logger.warning(
                        f"NRF heartbeat failed: {status_code} — {body or stderr}"
                    )
            except Exception as e:
                logger.error(f"NRF heartbeat error: {e}")

    @property
    def is_registered(self) -> bool:
        return self._registered
