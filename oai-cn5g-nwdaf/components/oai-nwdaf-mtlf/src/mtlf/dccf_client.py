#!/usr/bin/env python3
"""
DCCF Client for MTLF
Subscribes to the DCCF (Ndccf_DataManagement) to collect analytics data
used as training input for IDS packet-classification models.

Spec reference: 3GPP TS 29.574 (Data Collection Coordination Function).
NOTE: TS 29.552 is the old NWDAF analytics spec — DCCF is defined in TS 29.574.

The subscription/notification pattern mirrors what oai-nwdaf-sbi does in
dccf_subscription.go, adapted here in Python for the MTLF.
"""
import asyncio
import logging
from datetime import datetime
from typing import Callable, Optional

import httpx

logger = logging.getLogger(__name__)


class DCCFClient:
    """
    Manages a subscription to the DCCF Ndccf_DataManagement service.
    Notifications received are forwarded to a handler callback so
    TrainingManager can accumulate data.
    """

    def __init__(self, dccf_endpoint: str, notification_uri: str, nf_instance_id: str):
        self.dccf_endpoint = dccf_endpoint.rstrip("/")
        self.notification_uri = notification_uri
        self.nf_instance_id = nf_instance_id
        self.subscription_id: Optional[str] = None
        self._notification_handler: Optional[Callable] = None

    def set_notification_handler(self, handler: Callable):
        """Register a callback that receives each DCCF notification payload."""
        self._notification_handler = handler

    async def subscribe(
        self,
        event_types: list[str],
        protocols: list[str],
        interval_seconds: int = 60,
    ) -> bool:
        """
        POST /ndccf-datamanagement/v1/subscriptions to register this MTLF
        as a consumer of analytics data.

        Returns True on success.
        """
        payload = {
            "notificationUri": self.notification_uri,
            "nfId": self.nf_instance_id,
            "eventTypes": event_types,
            "protocols": protocols,
            "notificationInterval": interval_seconds,
        }
        url = f"{self.dccf_endpoint}/ndccf-datamanagement/v1/subscriptions"
        logger.info(f"Subscribing to DCCF at {url}")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code in [200, 201]:
                    body = response.json()
                    self.subscription_id = body.get("subscriptionId")
                    logger.info(f"DCCF subscription created: {self.subscription_id}")
                    return True
                else:
                    logger.error(
                        f"DCCF subscription failed: {response.status_code} — {response.text}"
                    )
                    return False
        except httpx.ConnectError as e:
            logger.error(f"Cannot reach DCCF at {self.dccf_endpoint}: {e}")
            return False
        except Exception as e:
            logger.error(f"DCCF subscribe error: {e}")
            return False

    async def unsubscribe(self) -> bool:
        """DELETE /ndccf-datamanagement/v1/subscriptions/{id}"""
        if not self.subscription_id:
            return True
        url = (
            f"{self.dccf_endpoint}/ndccf-datamanagement/v1/subscriptions"
            f"/{self.subscription_id}"
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.delete(url)
                if response.status_code in [200, 204]:
                    logger.info(f"DCCF subscription {self.subscription_id} deleted")
                    self.subscription_id = None
                    return True
                else:
                    logger.warning(f"DCCF unsubscribe failed: {response.status_code}")
                    return False
        except Exception as e:
            logger.error(f"DCCF unsubscribe error: {e}")
            return False

    async def handle_notification(self, notification: dict):
        """
        Called by the FastAPI route when DCCF POSTs a notification to
        /mtlf-internal/dccf-notifications.

        Dispatches to the registered handler (TrainingManager.on_dccf_data).
        """
        if self._notification_handler:
            await self._notification_handler(notification)
        else:
            logger.debug("DCCF notification received (no handler registered)")

    async def fetch_nf_events(self, limit: int = 500) -> list:
        """
        Pull NF events directly for on-demand training data collection.
        GET /ndccf-datamanagement/v1/nf-events
        """
        url = f"{self.dccf_endpoint}/ndccf-datamanagement/v1/nf-events"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params={"limit": limit})
                response.raise_for_status()
                return response.json().get("events", [])
        except Exception as e:
            logger.error(f"DCCF fetch nf-events error: {e}")
            return []

    async def fetch_protocol_events(self, protocol: Optional[str] = None, limit: int = 500) -> list:
        """
        Pull raw protocol events.
        GET /ndccf-datamanagement/v1/data
        """
        url = f"{self.dccf_endpoint}/ndccf-datamanagement/v1/data"
        params: dict = {"limit": limit}
        if protocol:
            params["protocol"] = protocol
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json().get("events", [])
        except Exception as e:
            logger.error(f"DCCF fetch protocol events error: {e}")
            return []

    async def fetch_analytics(self, analytics_type: Optional[str] = None, time_window: int = 15) -> dict:
        """
        Pull analytics snapshot.
        GET /ndccf-datamanagement/v1/analytics
        """
        url = f"{self.dccf_endpoint}/ndccf-datamanagement/v1/analytics"
        params: dict = {"time_window": time_window}
        if analytics_type:
            params["analytics_type"] = analytics_type
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"DCCF fetch analytics error: {e}")
            return {}
