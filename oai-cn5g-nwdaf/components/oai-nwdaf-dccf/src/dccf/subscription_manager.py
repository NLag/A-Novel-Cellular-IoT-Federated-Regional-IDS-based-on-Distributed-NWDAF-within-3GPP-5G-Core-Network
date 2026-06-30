#!/usr/bin/env python3
"""
Subscription Manager for DCCF
Implements 3GPP TS 29.552 Ndccf_DataManagement subscription/notification
"""
import asyncio
import httpx
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Subscription:
    """Represents a data subscription from an NWDAF consumer"""
    subscription_id: str
    notification_uri: str
    nf_id: str
    event_types: List[str]  # e.g., ["NF_LOAD", "UE_MOBILITY", "QOS_SUSTAINABILITY"]
    protocols: List[str]  # e.g., ["http2", "ngap", "pfcp"]
    expiry_time: Optional[datetime] = None
    notification_interval: int = 60  # seconds
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_notification: Optional[datetime] = None


class SubscriptionManager:
    """Manages subscriptions and notifications for Ndccf_DataManagement"""

    def __init__(self):
        self._subscriptions: Dict[str, Subscription] = {}
        self._notification_tasks: Dict[str, asyncio.Task] = {}
        self._http_client = httpx.AsyncClient(timeout=10.0)

    async def create_subscription(
        self,
        notification_uri: str,
        nf_id: str,
        event_types: List[str] = None,
        protocols: List[str] = None,
        expiry_time: Optional[datetime] = None,
        notification_interval: int = 60
    ) -> Subscription:
        """
        Create a new subscription

        Args:
            notification_uri: URI to send notifications to
            nf_id: NF instance ID of the subscriber
            event_types: Analytics event types to subscribe to
            protocols: Protocol types to subscribe to
            expiry_time: When the subscription expires
            notification_interval: Interval between notifications in seconds

        Returns:
            Created subscription
        """
        subscription_id = f"sub-{uuid.uuid4().hex[:12]}"

        subscription = Subscription(
            subscription_id=subscription_id,
            notification_uri=notification_uri,
            nf_id=nf_id,
            event_types=event_types or ["NF_LOAD", "UE_MOBILITY", "QOS_SUSTAINABILITY"],
            protocols=protocols or ["http2", "ngap", "pfcp", "gtpu", "nas"],
            expiry_time=expiry_time,
            notification_interval=notification_interval
        )

        self._subscriptions[subscription_id] = subscription
        logger.info(f"Created subscription {subscription_id} for {nf_id} -> {notification_uri}")

        # Start periodic notification task
        task = asyncio.create_task(self._notification_loop(subscription_id))
        self._notification_tasks[subscription_id] = task

        return subscription

    async def get_subscription(self, subscription_id: str) -> Optional[Subscription]:
        """Get a subscription by ID"""
        return self._subscriptions.get(subscription_id)

    async def list_subscriptions(self) -> List[Subscription]:
        """List all active subscriptions"""
        return list(self._subscriptions.values())

    async def update_subscription(
        self,
        subscription_id: str,
        event_types: List[str] = None,
        protocols: List[str] = None,
        notification_interval: int = None
    ) -> Optional[Subscription]:
        """Update an existing subscription"""
        subscription = self._subscriptions.get(subscription_id)
        if not subscription:
            return None

        if event_types:
            subscription.event_types = event_types
        if protocols:
            subscription.protocols = protocols
        if notification_interval:
            subscription.notification_interval = notification_interval

        logger.info(f"Updated subscription {subscription_id}")
        return subscription

    async def delete_subscription(self, subscription_id: str) -> bool:
        """Delete a subscription"""
        if subscription_id not in self._subscriptions:
            return False

        # Cancel notification task
        if subscription_id in self._notification_tasks:
            self._notification_tasks[subscription_id].cancel()
            del self._notification_tasks[subscription_id]

        del self._subscriptions[subscription_id]
        logger.info(f"Deleted subscription {subscription_id}")
        return True

    async def notify_all(self, analytics_data: dict, protocol: str = None):
        """
        Notify all relevant subscribers of new data

        Args:
            analytics_data: The analytics data to send
            protocol: Optional protocol filter
        """
        for subscription_id, subscription in self._subscriptions.items():
            # Check if subscription matches the protocol filter
            if protocol and protocol not in subscription.protocols:
                continue

            await self._send_notification(subscription, analytics_data)

    async def _notification_loop(self, subscription_id: str):
        """Periodic notification loop for a subscription"""
        while subscription_id in self._subscriptions:
            subscription = self._subscriptions[subscription_id]

            # Check expiry
            if subscription.expiry_time and datetime.utcnow() > subscription.expiry_time:
                logger.info(f"Subscription {subscription_id} expired")
                await self.delete_subscription(subscription_id)
                break

            # Wait for the notification interval
            await asyncio.sleep(subscription.notification_interval)

            # Skip if subscription was deleted during sleep
            if subscription_id not in self._subscriptions:
                break

            # Get fresh data and send notification
            # Note: This would normally fetch from database
            # For now, we'll trigger on-demand notifications

    async def _send_notification(self, subscription: Subscription, data: dict):
        """Send notification to a subscriber"""
        notification = {
            "subscriptionId": subscription.subscription_id,
            "notificationType": "DATA_NOTIFICATION",
            "timestamp": datetime.utcnow().isoformat(),
            "analyticsData": data
        }

        try:
            response = await self._http_client.post(
                subscription.notification_uri,
                json=notification,
                headers={"Content-Type": "application/json"}
            )

            if response.status_code in [200, 201, 204]:
                subscription.last_notification = datetime.utcnow()
                logger.debug(f"Notification sent to {subscription.notification_uri}")
            else:
                logger.warning(
                    f"Notification to {subscription.notification_uri} failed: "
                    f"{response.status_code}"
                )

        except Exception as e:
            logger.error(f"Failed to send notification to {subscription.notification_uri}: {e}")

    async def trigger_notification(self, subscription_id: str, data: dict):
        """Manually trigger a notification for a specific subscription"""
        subscription = self._subscriptions.get(subscription_id)
        if subscription:
            await self._send_notification(subscription, data)

    def to_dict(self, subscription: Subscription) -> dict:
        """Convert subscription to API response format"""
        return {
            "subscriptionId": subscription.subscription_id,
            "notificationUri": subscription.notification_uri,
            "nfId": subscription.nf_id,
            "eventTypes": subscription.event_types,
            "protocols": subscription.protocols,
            "expiryTime": subscription.expiry_time.isoformat() if subscription.expiry_time else None,
            "notificationInterval": subscription.notification_interval,
            "createdAt": subscription.created_at.isoformat(),
            "lastNotification": subscription.last_notification.isoformat() if subscription.last_notification else None
        }

    async def close(self):
        """Cleanup resources"""
        # Cancel all notification tasks
        for task in self._notification_tasks.values():
            task.cancel()
        self._notification_tasks.clear()

        # Close HTTP client
        await self._http_client.aclose()


# Global subscription manager instance
subscription_manager = SubscriptionManager()


def get_subscription_manager() -> SubscriptionManager:
    """Get the global subscription manager instance"""
    return subscription_manager
