#!/usr/bin/env python3
"""
NF Event Subscription Client for DCCF
Subscribes to AMF and SMF events per 3GPP TS 29.518 and TS 29.508
"""
import logging
import subprocess
import json
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class NFEventSubscriptionClient:
    """Client for subscribing to NF events (AMF, SMF)"""

    def __init__(self, config: dict, callback_uri: str):
        self.callback_uri = callback_uri
        self.subscriptions = {}  # nf_type -> subscription_id
        self.nf_instance_id = config.get('nwdaf', {}).get('nfInstanceId', '58f8ec8c-8a94-5ab1-86f6-7c989cb0cb74')

        # NF endpoints from config
        nf_subscriptions = config.get('nf_subscriptions', {})
        self.amf_config = nf_subscriptions.get('amf', config.get('amf', {})) or {}
        self.smf_config = nf_subscriptions.get('smf', config.get('smf', {})) or {}
        self.amf_endpoint = self.amf_config.get('endpoint', '')
        self.smf_endpoint = self.smf_config.get('endpoint', '')

        # NF subscription enable flags
        subscriptions_enabled = nf_subscriptions.get('enabled', False)
        self.amf_enabled = self.amf_config.get('enabled', subscriptions_enabled and bool(self.amf_endpoint))
        self.smf_enabled = self.smf_config.get('enabled', subscriptions_enabled and bool(self.smf_endpoint))

        # HTTP version configuration (default to HTTP/2 for OAI compatibility)
        self.use_http2 = nf_subscriptions.get('use_http2', True)
        self.amf_notification_path = self.amf_config.get('notification_path', '/dccf/amf-notifications')
        self.smf_notification_path = self.smf_config.get('notification_path', '/dccf/smf-notifications')

        # Event types to subscribe to
        # AMF event types to subscribe to
        # Using correct event names from 3GPP TS 29.518 / OAI AMF implementation
        self.amf_events = self.amf_config.get('events', [
            "REGISTRATION_STATE_REPORT",
            "CONNECTIVITY_STATE_REPORT",
            "REACHABILITY_REPORT",
            "LOCATION_REPORT"
        ])

        self.smf_events = self.smf_config.get('events', [
            "PDU_SES_EST",
            "PDU_SES_REL",
            "QOS_MON",
            "UP_PATH_CH",
            "PLMN_CH",
            "DISPERSION"
        ])

    def _callback_url(self, path: str) -> str:
        if not path:
            return self.callback_uri
        normalized_path = path if path.startswith('/') else f'/{path}'
        return f"{self.callback_uri.rstrip('/')}{normalized_path}"

    async def subscribe_to_amf(self) -> Optional[str]:
        """Subscribe to AMF events (Namf_EventExposure)"""
        if not self.amf_enabled:
            logger.info("AMF event subscriptions disabled in configuration")
            return None
            
        if not self.amf_endpoint:
            logger.warning("AMF endpoint not configured")
            return None

        # 3GPP TS 29.518: AmfEventSubscription - required fields per NWDAF client
        # Required: eventList, eventNotifyUri, notifyCorrelationId, nfId
        subscription_data = {
            "subscription": {
                "eventList": [{"type": event} for event in self.amf_events],
                "eventNotifyUri": self._callback_url(self.amf_notification_path),
                "notifyCorrelationId": f"dccf-amf-{datetime.utcnow().isoformat()}",
                "nfId": self.nf_instance_id,
            }
        }

        url = f"{self.amf_endpoint}/namf-evts/v1/subscriptions"
        logger.info(f"Subscribing to AMF events using HTTP/2 (h2c) at {url}")

        try:
            # Use curl with --http2-prior-knowledge because httpx doesn't support h2c prior knowledge
            # OAI AMF's nghttp2 server requires HTTP/2 connection preface, not HTTP/1.1 Upgrade
            result = subprocess.run(
                [
                    'curl', '--http2-prior-knowledge', '-v',
                    '-H', 'Content-Type: application/json',
                    '-H', 'Accept: application/json',
                    '-d', json.dumps(subscription_data),
                    url
                ],
                capture_output=True,
                text=True,
                timeout=10
            )

            # Parse response from stderr (curl outputs to stderr with -v)
            stderr = result.stderr
            stdout = result.stdout

            # Check for HTTP 201 Created in stderr
            if '< HTTP/2 201' in stderr or '< HTTP/2 200' in stderr:
                try:
                    response_data = json.loads(stdout)
                    # Try multiple possible field names for subscription ID
                    sub_id = response_data.get('subscriptionId') or response_data.get('subId') or ''
                    self.subscriptions['AMF'] = sub_id
                    logger.info(f"Successfully subscribed to AMF events using HTTP/2: {sub_id}")
                    logger.debug(f"AMF response: {stdout}")
                    return sub_id
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse AMF response: {stdout}")
                    return None
            else:
                logger.error(f"AMF subscription failed. Response: {stdout}, Debug: {stderr}")
                return None

        except subprocess.TimeoutExpired:
            logger.error(f"AMF subscription timeout after 10s")
            return None
        except Exception as e:
            logger.error(f"AMF subscription error: {e}")
            return None

    async def subscribe_to_smf(self) -> Optional[str]:
        """Subscribe to SMF events (Nsmf_EventExposure)"""
        if not self.smf_endpoint:
            logger.warning("SMF endpoint not configured")
            return None

        subscription_data = {
            "eventSubs": [{"event": event} for event in self.smf_events],
            "notifUri": self._callback_url(self.smf_notification_path),
            "notifId": f"dccf-smf-{datetime.utcnow().isoformat()}",
            "suppFeat": "1"
        }

        # Note: OAI SMF uses underscore in route: /nsmf_event-exposure (not hyphen)
        url = f"{self.smf_endpoint}/nsmf_event-exposure/v1/subscriptions"
        logger.info(f"Subscribing to SMF events using HTTP/2 (h2c) at {url}")

        try:
            # Use curl with --http2-prior-knowledge for same reason as AMF
            result = subprocess.run(
                [
                    'curl', '--http2-prior-knowledge', '-v',
                    '-H', 'Content-Type: application/json',
                    '-H', 'Accept: application/json',
                    '-d', json.dumps(subscription_data),
                    url
                ],
                capture_output=True,
                text=True,
                timeout=10
            )

            stderr = result.stderr
            stdout = result.stdout

            if '< HTTP/2 201' in stderr or '< HTTP/2 200' in stderr:
                try:
                    response_data = json.loads(stdout)
                    sub_id = response_data.get('subId', '')
                    self.subscriptions['SMF'] = sub_id
                    logger.info(f"Successfully subscribed to SMF events using HTTP/2: {sub_id}")
                    logger.debug(f"SMF response: {stdout}")
                    return sub_id
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse SMF response: {stdout}")
                    return None
            elif '< HTTP/2 404' in stderr:
                logger.warning(f"SMF does not implement Nsmf_EventExposure API (HTTP 404) - this is normal for some OAI deployments")
                return None
            else:
                logger.error(f"SMF subscription failed. Response: {stdout}, Debug: {stderr}")
                return None

        except subprocess.TimeoutExpired:
            logger.error(f"SMF subscription timeout after 10s")
            return None
        except Exception as e:
            logger.error(f"SMF subscription error: {e}")
            return None

    async def subscribe_all(self) -> dict:
        """Subscribe to all configured NF events"""
        results = {}

        if self.amf_endpoint:
            results['AMF'] = await self.subscribe_to_amf()

        if self.smf_endpoint:
            results['SMF'] = await self.subscribe_to_smf()

        return results

    async def unsubscribe_from_amf(self) -> bool:
        """Unsubscribe from AMF events"""
        sub_id = self.subscriptions.get('AMF')
        if not sub_id:
            return True

        url = f"{self.amf_endpoint}/namf-evts/v1/subscriptions/{sub_id}"

        try:
            result = subprocess.run(
                ['curl', '--http2-prior-knowledge', '-X', 'DELETE', url],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                logger.info(f"Unsubscribed from AMF: {sub_id}")
                del self.subscriptions['AMF']
                return True
            return False
        except Exception as e:
            logger.error(f"AMF unsubscribe error: {e}")
            return False

    async def unsubscribe_from_smf(self) -> bool:
        """Unsubscribe from SMF events"""
        sub_id = self.subscriptions.get('SMF')
        if not sub_id:
            return True

        url = f"{self.smf_endpoint}/nsmf_event-exposure/v1/subscriptions/{sub_id}"

        try:
            result = subprocess.run(
                ['curl', '--http2-prior-knowledge', '-X', 'DELETE', url],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                logger.info(f"Unsubscribed from SMF: {sub_id}")
                del self.subscriptions['SMF']
                return True
            return False
        except Exception as e:
            logger.error(f"SMF unsubscribe error: {e}")
            return False

    async def unsubscribe_all(self):
        """Unsubscribe from all NF events"""
        await self.unsubscribe_from_amf()
        await self.unsubscribe_from_smf()
