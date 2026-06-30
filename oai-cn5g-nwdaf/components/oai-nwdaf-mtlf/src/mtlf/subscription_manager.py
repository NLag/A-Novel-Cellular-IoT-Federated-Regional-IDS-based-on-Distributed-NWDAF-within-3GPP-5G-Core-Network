#!/usr/bin/env python3
"""
Subscription Manager for MTLF — Nnwdaf_MLModelProvision (3GPP TS 29.520 Rel-17)

Manages consumer subscriptions (AnLF, other NFs) for ML model-ready events.
Schema strictly follows TS 29.520:
  - NnwdafMLModelProvisionSubsc  (Table 6.3.3.2-2)  — subscription request/response
  - NnwdafMLModelProvisionNotif  (Table 6.3.3.2-4)  — notification to consumers
  - MLModelInfo                  (Table 6.3.3.2-5)  — per-model info in notification
  - MLModelAddr                  (Table 6.3.3.2-6)  — model file address
  - NwdafEvent                   (Table 6.3.3.3-1)  — standardized event IDs

Key compliance points:
  - notifUri / notifCorreId are the canonical field names (not notificationUri)
  - mLModels[] carries the list of requested model events (not mlEventIds)
  - Notifications echo notifCorreId (not subscriptionId) for correlation
  - mLModelInfo is a list (array), not a single object
  - mLFileAddr.mlModelUrl must be an HTTP(S) URI (not file://)
  - NwdafEvent enum: use ABNORMAL_BEHAVIOUR for anomaly detection
"""
import logging
import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Standardized NwdafEvent values (TS 29.520 Table 6.3.3.3-1)
# Use these for mLEvent — do NOT invent custom strings.
# ---------------------------------------------------------------------------
NWDAF_EVENT_ABNORMAL_BEHAVIOUR    = "ABNORMAL_BEHAVIOUR"
NWDAF_EVENT_NF_LOAD               = "NF_LOAD"
NWDAF_EVENT_UE_MOBILITY           = "UE_MOBILITY"
NWDAF_EVENT_UE_COMM               = "UE_COMM"
NWDAF_EVENT_QOS_SUSTAINABILITY     = "QOS_SUSTAINABILITY"
NWDAF_EVENT_SERVICE_EXPERIENCE     = "SERVICE_EXPERIENCE"
NWDAF_EVENT_USER_DATA_CONGESTION   = "USER_DATA_CONGESTION"
NWDAF_EVENT_NSI_LOAD_LEVEL        = "NSI_LOAD_LEVEL"

# Accuracy enum (TS 29.520 Table 6.3.3.3-2)
ACCURACY_HIGH   = "HIGH"
ACCURACY_MEDIUM = "MEDIUM"
ACCURACY_LOW    = "LOW"


@dataclass
class MLModelSubscription:
    """
    NnwdafMLModelProvisionSubsc (TS 29.520 Table 6.3.3.2-2)

    Fields mapped to spec names:
      subscription_id  ← subscriptionId  (assigned by MTLF, returned in response)
      notif_uri        ← notifUri        (required — consumer callback URI)
      notif_corre_id   ← notifCorreId    (required — echoed in every notification)
      ml_models        ← mLModels        (required — list of MLModel request objects)
      supp_feat        ← suppFeat        (optional — feature negotiation bitmap)
      expiry           ← expiry          (optional — subscription expiry DateTime)
    """
    subscription_id: str
    notif_uri:       str
    notif_corre_id:  str
    ml_models:       List[dict]          # list of { mLEvent, mLEventFilter?, tgtUe?, ... }
    supp_feat:       Optional[str] = None
    expiry:          Optional[str] = None
    created_at:      datetime = field(default_factory=datetime.utcnow)
    last_notif_at:   Optional[datetime] = None


class MLSubscriptionManager:
    """
    Manages Nnwdaf_MLModelProvision subscriptions and sends model-ready
    notifications per TS 29.520 §6.3.3.3.
    """

    def __init__(self):
        self._subscriptions: Dict[str, MLModelSubscription] = {}
        self._http_client = httpx.AsyncClient(timeout=10.0)

    async def create_subscription(
        self,
        notif_uri:      str,
        notif_corre_id: str,
        ml_models:      List[dict],
        supp_feat:      Optional[str] = None,
        expiry:         Optional[str] = None,
    ) -> MLModelSubscription:
        sub_id = f"mtsub-{uuid.uuid4().hex[:12]}"
        sub = MLModelSubscription(
            subscription_id=sub_id,
            notif_uri=notif_uri,
            notif_corre_id=notif_corre_id,
            ml_models=ml_models,
            supp_feat=supp_feat,
            expiry=expiry,
        )
        self._subscriptions[sub_id] = sub
        logger.info(f"ML subscription created: {sub_id} → {notif_uri}")
        return sub

    async def get_subscription(self, sub_id: str) -> Optional[MLModelSubscription]:
        return self._subscriptions.get(sub_id)

    async def list_subscriptions(self) -> List[MLModelSubscription]:
        return list(self._subscriptions.values())

    async def delete_subscription(self, sub_id: str) -> bool:
        if sub_id not in self._subscriptions:
            return False
        del self._subscriptions[sub_id]
        logger.info(f"ML subscription deleted: {sub_id}")
        return True

    async def notify_model_ready(
        self,
        job_id:    str,
        model_id:  str,
        metrics:   dict,
    ):
        """
        Send NnwdafMLModelProvisionNotif (TS 29.520 Table 6.3.3.2-4) to all
        subscribers whose mLModels list includes ABNORMAL_BEHAVIOUR or NF_LOAD.

        Notification body:
          notifCorreId — echoed from the subscription (required for correlation)
          mLModelInfo  — array of MLModelInfo objects (Table 6.3.3.2-5)
            mLEvent       — NwdafEvent (standardized)
            mLFileAddr    — MLModelAddr (Table 6.3.3.2-6)
              mlModelUrl  — HTTP URI to download the model (not file://)
            accuracy      — Accuracy enum: HIGH | MEDIUM | LOW
            validityPeriod — TimeWindow (optional)
        """
        for sub in list(self._subscriptions.values()):
            await self.notify_subscription_model_ready(sub, job_id, model_id, metrics)

    async def notify_subscription_model_ready(
        self,
        sub:       MLModelSubscription,
        job_id:    str,
        model_id:  str,
        metrics:   dict,
    ):
        """
        Send one model-ready notification to a specific subscription.
        Used for dev/test bootstrap when MTLF already has a latest model before
        IDS creates the subscription.
        """
        from main import _model_registry
        entry = _model_registry.get(model_id, {})
        ml_model_url = entry.get("mlModelUrl", "")
        manifest_url = entry.get("manifestUrl", "")

        ml_model_info = [
            {
                "mLEvent":   NWDAF_EVENT_ABNORMAL_BEHAVIOUR,
                "mLFileAddr": {
                    "mlModelUrl": ml_model_url,
                },
                "accuracy":  ACCURACY_HIGH,
                "idsModelManifestUrl": manifest_url,
            }
        ]

        # Check expiry
        if sub.expiry:
            try:
                exp_dt = datetime.fromisoformat(sub.expiry.replace("Z", "+00:00"))
                if datetime.utcnow() > exp_dt.replace(tzinfo=None):
                    logger.info(f"Subscription {sub.subscription_id} expired, skipping")
                    return
            except Exception:
                pass

        # Only notify subscribers that requested ABNORMAL_BEHAVIOUR
        requested_events = {m.get("mLEvent") for m in sub.ml_models}
        if NWDAF_EVENT_ABNORMAL_BEHAVIOUR not in requested_events:
            logger.debug(
                f"Subscription {sub.subscription_id} does not request "
                f"ABNORMAL_BEHAVIOUR — skipping notification"
            )
            return

        notification = {
            "notifCorreId": sub.notif_corre_id,
            "mLModelInfo":  ml_model_info,
        }

        max_attempts = 5
        for attempt in range(1, max_attempts + 1):
            try:
                response = await self._http_client.post(
                    sub.notif_uri,
                    json=notification,
                    headers={"Content-Type": "application/json"},
                )
                if response.status_code in [200, 201, 202, 204]:
                    sub.last_notif_at = datetime.utcnow()
                    logger.info(
                        f"NnwdafMLModelProvisionNotif sent to {sub.notif_uri} "
                        f"(model={model_id}, corrId={sub.notif_corre_id}, "
                        f"attempt={attempt})"
                    )
                    return
                logger.warning(
                    f"Notification to {sub.notif_uri} failed on attempt "
                    f"{attempt}/{max_attempts}: {response.status_code}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to notify {sub.notif_uri} on attempt "
                    f"{attempt}/{max_attempts}: {e}"
                )
            if attempt < max_attempts:
                await asyncio.sleep(2)

        logger.error(
            f"Failed to notify {sub.notif_uri} after {max_attempts} attempts"
        )

    def to_dict(self, sub: MLModelSubscription) -> dict:
        """
        Serialize to NnwdafMLModelProvisionSubsc response format.
        The subscription response adds subscriptionId to the request body.
        """
        d = {
            "subscriptionId": sub.subscription_id,
            "notifUri":       sub.notif_uri,
            "notifCorreId":   sub.notif_corre_id,
            "mLModels":       sub.ml_models,
        }
        if sub.supp_feat is not None:
            d["suppFeat"] = sub.supp_feat
        if sub.expiry is not None:
            d["expiry"] = sub.expiry
        return d

    async def close(self):
        await self._http_client.aclose()


# Global singleton
_manager = MLSubscriptionManager()


def get_subscription_manager() -> MLSubscriptionManager:
    return _manager
