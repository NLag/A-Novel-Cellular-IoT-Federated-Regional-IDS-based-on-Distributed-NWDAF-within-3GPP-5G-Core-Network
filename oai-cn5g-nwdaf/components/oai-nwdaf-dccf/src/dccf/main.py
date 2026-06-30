#!/usr/bin/env python3
"""
NWDAF-DCCF Service
Provides NRF registration and Ndccf DataManagement API
Reads analytics data from Casmella's SQLite database
"""
import os
import signal
import asyncio
from datetime import datetime
from typing import Any, Optional, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import logging
import yaml

from nrf_client import NRFClient
from database_reader import DatabaseReader
from mongo_report_store import MongoIdsReportStore
from subscription_manager import get_subscription_manager, SubscriptionManager
from nf_event_subscription import NFEventSubscriptionClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# NTP epoch starts at 1900-01-01, Unix epoch starts at 1970-01-01
# Difference in seconds between the two epochs
SECONDS_SINCE_FIRST_EPOCH = 2208988800


def normalize_timestamp(timestamp_input) -> str:
    """
    Normalize timestamp to Unix epoch format.

    SMF sends NTP timestamps (seconds since 1900-01-01)
    AMF sends Unix timestamps (seconds since 1970-01-01)

    Detect NTP timestamps and convert to Unix epoch for consistency.

    Args:
        timestamp_input: Timestamp (may be int, float, string - Unix or NTP epoch, or ISO format)

    Returns:
        Normalized timestamp string (Unix epoch or ISO format)
    """
    try:
        # Handle different input types
        if isinstance(timestamp_input, (int, float)):
            timestamp_val = float(timestamp_input)
        elif isinstance(timestamp_input, str):
            # Try to parse string as number
            try:
                timestamp_val = float(timestamp_input)
            except ValueError:
                # Not a numeric string, assume ISO format or other string format
                return timestamp_input
        else:
            # Unknown type, return as-is
            logger.warning(f"Unknown timestamp type: {type(timestamp_input)}, value: {timestamp_input}")
            return str(timestamp_input)

        # If timestamp > 2^31 (year 2038 in Unix epoch), assume it's NTP format
        # NTP timestamps for year 2025 are around 3.9 billion
        # Unix timestamps for year 2025 are around 1.7 billion
        if timestamp_val > 2147483648:  # 2^31 (Jan 19, 2038 in Unix epoch)
            # Convert from NTP to Unix epoch
            unix_timestamp = timestamp_val - SECONDS_SINCE_FIRST_EPOCH
            logger.info(f"Converted NTP timestamp {timestamp_val} to Unix {unix_timestamp}")
            return str(int(unix_timestamp))

        # Already Unix epoch or small value
        return str(int(timestamp_val))

    except Exception as e:
        # Log the error and return original value
        logger.error(f"Error normalizing timestamp {timestamp_input}: {e}")
        return str(timestamp_input)

app = FastAPI(
    title="NWDAF-DCCF",
    description="NWDAF Data Collection Coordination Function - 3GPP TS 29.574",
    version="1.0.0"
)

# Global instances
nrf_client: Optional[NRFClient] = None
db_reader: Optional[DatabaseReader] = None
nf_event_client: Optional[NFEventSubscriptionClient] = None
mongo_report_store: Optional[MongoIdsReportStore] = None
config: dict = {}
_ids_reports: List[dict[str, Any]] = []


def _filter_memory_ids_reports(
    region: Optional[str] = None,
    predicted_class: Optional[str] = None,
    limit: int = 100,
) -> List[dict[str, Any]]:
    reports = list(_ids_reports)
    if region:
        reports = [report for report in reports if report.get("region") == region]
    if predicted_class:
        def _predicted_class(report_entry: dict) -> str:
            nested_report = report_entry.get("report")
            if not isinstance(nested_report, dict):
                nested_report = {}
            return report_entry.get("predictedClass") or nested_report.get("predictedClass")

        reports = [
            report
            for report in reports
            if _predicted_class(report) == predicted_class
        ]
    return reports[-limit:]


def _connect_mongo_report_store() -> Optional[MongoIdsReportStore]:
    global mongo_report_store

    if mongo_report_store is not None:
        return mongo_report_store

    mongo_cfg = config.get("mongodb", {})
    if not mongo_cfg.get("enabled", False):
        return None

    try:
        mongo_report_store = MongoIdsReportStore(
            uri=mongo_cfg.get("uri", ""),
            database_name=mongo_cfg.get("database_name", "testing"),
            collection_name=mongo_cfg.get("ids_reports_collection", "ids_reports"),
            timeout_ms=int(mongo_cfg.get("timeout_ms", 3000)),
        )
        return mongo_report_store
    except Exception as exc:
        logger.warning(
            "MongoDB IDS report store unavailable; using fallback storage: %s",
            exc,
        )
        return None


def _drop_mongo_report_store():
    global mongo_report_store

    if mongo_report_store is not None:
        try:
            mongo_report_store.close()
        except Exception as exc:
            logger.debug("Error closing MongoDB IDS report store: %s", exc)
        mongo_report_store = None


def load_config(config_path: str = None) -> dict:
    """Load DCCF configuration"""
    config_path = config_path or os.getenv('DCCF_CONFIG_PATH', '/config/dccf-config.yaml')
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.warning(f"Config file not found: {config_path}, using defaults")
        return {
            "nwdaf": {
                "nfInstanceId": "58f8ec8c-8a94-5ab1-86f6-7c989cb0cb74",
                "nfType": "NWDAF"
            },
            "nrf": {
                "endpoint": "",
                "auto_register": False,
                "heartbeat_interval": 10
            },
            "ndccf": {
                "port": 8081,
                "database_path": "/data/casmella.db"
            },
            "dccf": {
                "callback_uri": "http://oai-nwdaf-dccf:8081"
            },
            "nf_subscriptions": {
                "enabled": False,
                "use_http2": True
            },
            "mongodb": {
                "enabled": False,
                "uri": "mongodb://oai-nwdaf-database:27017",
                "database_name": "testing",
                "ids_reports_collection": "ids_reports",
                "timeout_ms": 3000
            }
        }


@app.on_event("startup")
async def startup_event():
    """Initialize DCCF service on startup"""
    global nrf_client, db_reader, nf_event_client, mongo_report_store, config

    logger.info("NWDAF-DCCF Service Starting...")

    # Load configuration
    config = load_config()
    nf_instance_id = config.get('nwdaf', {}).get('nfInstanceId', 'unknown')
    logger.info(f"NF Instance ID: {nf_instance_id}")

    # Initialize database reader
    server_cfg = config.get('ndccf') or config.get('nadrf') or {}
    db_path = server_cfg.get('database_path', '/data/casmella.db')
    db_reader = DatabaseReader(db_path)
    logger.info(f"Database reader initialized: {db_path}")

    mongo_cfg = config.get("mongodb", {})
    if mongo_cfg.get("enabled", False):
        _connect_mongo_report_store()

    # Initialize NRF client and register
    nrf_client = NRFClient(config)
    if nrf_client.auto_register:
        success = await nrf_client.register()
        if success:
            logger.info("Successfully registered with NRF as NWDAF")
        else:
            logger.warning("Failed to register with NRF - service will continue without registration")
    else:
        logger.info("NRF auto-registration disabled")

    # Initialize NF event subscriptions (AMF, SMF)
    callback_uri = config.get('dccf', {}).get('callback_uri', 'http://oai-nwdaf-dccf:8081')
    nf_event_client = NFEventSubscriptionClient(config, callback_uri)

    if config.get('nf_subscriptions', {}).get('enabled', False):
        logger.info("Subscribing to NF events (AMF, SMF)...")
        results = await nf_event_client.subscribe_all()
        for nf_type, sub_id in results.items():
            if sub_id:
                logger.info(f"Subscribed to {nf_type} events: {sub_id}")
            else:
                logger.warning(f"Failed to subscribe to {nf_type} events")
    else:
        logger.info("NF event subscriptions disabled")

    logger.info("NWDAF-DCCF Service Started Successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global nrf_client, nf_event_client, mongo_report_store

    # Cleanup subscription manager
    sub_manager = get_subscription_manager()
    await sub_manager.close()
    logger.info("Subscription manager closed")

    # Unsubscribe from NF events
    if nf_event_client:
        await nf_event_client.unsubscribe_all()
        logger.info("Unsubscribed from NF events")

    if nrf_client and nrf_client.is_registered:
        await nrf_client.deregister()
        logger.info("Deregistered from NRF")

    if mongo_report_store:
        mongo_report_store.close()
        logger.info("MongoDB IDS report store closed")


# NF Event Notification Handlers
@app.post("/dccf/amf-notifications")
async def handle_amf_notification(notification: dict):
    """
    Handle AMF event notifications

    3GPP TS 29.518 - Namf_EventExposure Notify
    """
    logger.info(f"Received AMF notification: {notification.get('notifyCorrelationId', 'unknown')}")

    if db_reader is None:
        raise HTTPException(status_code=503, detail="Database not available")

    # Process each report in the notification
    reports = notification.get("reportList", [])
    for report in reports:
        event_type = report.get("type", "UNKNOWN")
        timestamp = report.get("timeStamp", datetime.utcnow().isoformat())

        # Normalize timestamp (convert NTP to Unix epoch if needed)
        timestamp = normalize_timestamp(timestamp)

        # Store the event in database
        event_data = {
            "source": "AMF",
            "event_type": event_type,
            "timestamp": timestamp,
            "data": report
        }

        try:
            db_reader.store_nf_event(event_data)
            logger.debug(f"Stored AMF event: {event_type}")
        except Exception as e:
            logger.error(f"Failed to store AMF event: {e}")

    return {"status": "ok", "processed": len(reports)}


@app.post("/dccf/smf-notifications")
async def handle_smf_notification(notification: dict):
    """
    Handle SMF event notifications

    3GPP TS 29.508 - Nsmf_EventExposure Notify
    """
    logger.info(f"Received SMF notification: {notification.get('notifId', 'unknown')}")
    logger.debug(f"SMF notification payload: {notification}")

    if db_reader is None:
        raise HTTPException(status_code=503, detail="Database not available")

    # Process each event notification
    event_notifs = notification.get("eventNotifs", [])
    logger.info(f"SMF notification contains {len(event_notifs)} event(s)")

    for event_notif in event_notifs:
        event_type = event_notif.get("event", "UNKNOWN")
        timestamp_raw = event_notif.get("timeStamp", datetime.utcnow().isoformat())

        # Log the raw timestamp before normalization
        logger.debug(f"Raw SMF timestamp: {timestamp_raw} (type: {type(timestamp_raw)})")

        # Normalize timestamp (convert NTP to Unix epoch if needed)
        timestamp = normalize_timestamp(timestamp_raw)

        logger.info(f"Processing SMF event: type='{event_type}', raw_timestamp={timestamp_raw}, normalized_timestamp={timestamp}")
        logger.debug(f"Event details: {event_notif}")

        # Store the event in database
        event_data = {
            "source": "SMF",
            "event_type": event_type,
            "timestamp": timestamp,
            "data": event_notif
        }

        try:
            db_reader.store_nf_event(event_data)
            logger.info(f"✓ Stored SMF event: {event_type}")
        except Exception as e:
            logger.error(f"Failed to store SMF event: {e}")

    return {"status": "ok", "processed": len(event_notifs)}


# Health endpoints
@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "NWDAF-DCCF",
        "nfInstanceId": config.get('nwdaf', {}).get('nfInstanceId', ''),
        "servingArea": config.get('serving_area', {}),
        "nrfRegistered": nrf_client.is_registered if nrf_client else False,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/ready")
async def readiness():
    """Readiness check"""
    if db_reader is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return {"status": "ready"}


# Ndccf DataManagement API (3GPP TS 29.552)
@app.get("/ndccf-datamanagement/v1/analytics")
async def get_analytics(
    analytics_type: Optional[str] = Query(None, description="Type of analytics: NF_LOAD, UE_MOBILITY, QOS_SUSTAINABILITY"),
    time_window: int = Query(15, description="Time window in minutes")
):
    """
    Retrieve analytics data from DCCF

    3GPP TS 29.552 - Ndccf_DataManagement service
    """
    if db_reader is None:
        raise HTTPException(status_code=503, detail="Database not available")

    if analytics_type == "NF_LOAD":
        return db_reader.get_nf_load_analytics(time_window_minutes=time_window)
    elif analytics_type == "UE_MOBILITY":
        return db_reader.get_ue_mobility_analytics(time_window_minutes=time_window)
    elif analytics_type == "QOS_SUSTAINABILITY":
        return db_reader.get_qos_sustainability_analytics(time_window_minutes=time_window)
    else:
        # Return all analytics types
        return {
            "nfLoad": db_reader.get_nf_load_analytics(time_window_minutes=time_window),
            "ueMobility": db_reader.get_ue_mobility_analytics(time_window_minutes=time_window),
            "qosSustainability": db_reader.get_qos_sustainability_analytics(time_window_minutes=time_window)
        }


@app.get("/ndccf-datamanagement/v1/data")
async def get_data(
    protocol: Optional[str] = Query(None, description="Protocol: http2, ngap, pfcp, nas, gtpu"),
    event_type: Optional[str] = Query(None, description="Event type filter"),
    limit: int = Query(100, le=1000, description="Maximum results")
):
    """
    Retrieve raw protocol event data

    Used by NWDAF to fetch data for analytics computation
    """
    if db_reader is None:
        raise HTTPException(status_code=503, detail="Database not available")

    events = db_reader.get_events(
        protocol=protocol,
        event_type=event_type,
        limit=limit
    )

    return {
        "events": events,
        "count": len(events),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/ndccf-datamanagement/v1/nf-events")
async def get_nf_events(
    source: Optional[str] = Query(None, description="Source: AMF, SMF"),
    event_type: Optional[str] = Query(None, description="Event type filter"),
    limit: int = Query(100, le=1000, description="Maximum results")
):
    """
    Retrieve NF event data (AMF/SMF notifications)

    Used by NWDAF to fetch NF-specific events for analytics
    3GPP TS 29.552 - Ndccf_DataManagement
    """
    if db_reader is None:
        raise HTTPException(status_code=503, detail="Database not available")

    events = db_reader.get_nf_events(
        source=source,
        event_type=event_type,
        limit=limit
    )

    return {
        "events": events,
        "count": len(events),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/ndccf-datamanagement/v1/ids-reports", status_code=201)
async def create_ids_report(report: dict):
    """
    Store IDS detection reports for the IDS/NWDAF lab integration.

    This is a DCCF-local compatibility endpoint used until the project adds a
    dedicated ADRF storage service for IDS reports.
    """
    nested_report = report.get("report")
    if not isinstance(nested_report, dict):
        nested_report = {}
    report_id = report.get("reportId") or nested_report.get("reportId")
    if not report_id:
        raise HTTPException(status_code=400, detail="reportId is required")

    stored_report = {
        **report,
        "reportId": report_id,
        "region": report.get("region") or nested_report.get("region") or config.get('serving_area', {}).get("region"),
        "tac": report.get("tac") or nested_report.get("tac") or config.get('serving_area', {}).get("tac"),
        "receivedAt": datetime.utcnow().isoformat(),
    }
    storage_backend = "memory"
    active_mongo_store = _connect_mongo_report_store()
    if active_mongo_store is not None:
        try:
            active_mongo_store.store_ids_report(stored_report)
            storage_backend = "mongodb"
        except Exception as exc:
            logger.error(f"Failed to persist IDS report {report_id} in MongoDB: {exc}")
            _drop_mongo_report_store()
    if storage_backend == "memory" and db_reader is not None:
        try:
            db_reader.store_ids_report(stored_report)
            storage_backend = "sqlite"
        except Exception as exc:
            logger.error(f"Failed to persist IDS report {report_id}: {exc}")
    _ids_reports.append(stored_report)
    logger.info(f"Stored IDS report {report_id}")
    if storage_backend == "mongodb" and active_mongo_store is not None:
        total_stored = active_mongo_store.get_ids_report_count()
    elif storage_backend == "sqlite" and db_reader is not None:
        total_stored = db_reader.get_ids_report_count()
    else:
        total_stored = len(_ids_reports)
    return {
        "status": "stored",
        "reportId": report_id,
        "storage": storage_backend,
        "count": total_stored,
    }


@app.get("/ndccf-datamanagement/v1/ids-reports")
async def list_ids_reports(
    region: Optional[str] = Query(None, description="Serving region filter"),
    predicted_class: Optional[str] = Query(None, description="IDS predicted class filter"),
    limit: int = Query(100, le=1000, description="Maximum reports")
):
    """List recent IDS reports stored by the DCCF compatibility endpoint."""
    storage_backend = "memory"
    active_mongo_store = _connect_mongo_report_store()
    if active_mongo_store is not None:
        try:
            reports = active_mongo_store.get_ids_reports(
                region=region,
                predicted_class=predicted_class,
                limit=limit,
            )
            total_stored = active_mongo_store.get_ids_report_count(region=region)
            storage_backend = "mongodb"
        except Exception as exc:
            logger.error(f"Failed to query IDS reports from MongoDB: {exc}")
            _drop_mongo_report_store()
    if storage_backend == "memory" and db_reader is not None:
        try:
            reports = db_reader.get_ids_reports(
                region=region,
                predicted_class=predicted_class,
                limit=limit,
            )
            total_stored = db_reader.get_ids_report_count(region=region)
            storage_backend = "sqlite"
        except Exception as exc:
            logger.error(f"Failed to query IDS reports from SQLite: {exc}")
    if storage_backend == "memory":
        reports = _filter_memory_ids_reports(
            region=region,
            predicted_class=predicted_class,
            limit=limit,
        )
        total_stored = len(_filter_memory_ids_reports(region=region, limit=1000))
    return {
        "reports": reports,
        "count": len(reports),
        "totalStored": total_stored,
        "storage": storage_backend,
        "servingArea": config.get('serving_area', {}),
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/ndccf-datamanagement/v1/stats")
async def get_stats():
    """Get database statistics"""
    if db_reader is None:
        raise HTTPException(status_code=503, detail="Database not available")
    active_mongo_store = _connect_mongo_report_store()
    ids_report_storage = "sqlite"
    try:
        ids_report_total = db_reader.get_ids_report_count()
    except Exception as exc:
        logger.error(f"Failed to count SQLite IDS reports: {exc}")
        ids_report_storage = "memory"
        ids_report_total = len(_ids_reports)
    if active_mongo_store is not None:
        try:
            ids_report_total = active_mongo_store.get_ids_report_count()
            ids_report_storage = "mongodb"
        except Exception as exc:
            logger.error(f"Failed to count MongoDB IDS reports: {exc}")
            _drop_mongo_report_store()

    return {
        "totalEvents": db_reader.get_event_count(),
        "eventsByProtocol": {
            "http2": db_reader.get_event_count("http2"),
            "ngap": db_reader.get_event_count("ngap"),
            "pfcp": db_reader.get_event_count("pfcp"),
            "nas": db_reader.get_event_count("nas"),
            "gtpu": db_reader.get_event_count("gtpu")
        },
        "nfEvents": {
            "total": db_reader.get_nf_event_count(),
            "amf": db_reader.get_nf_event_count("AMF"),
            "smf": db_reader.get_nf_event_count("SMF")
        },
        "idsReports": {
            "total": ids_report_total,
            "storage": ids_report_storage
        },
        "timestamp": datetime.utcnow().isoformat()
    }


# Subscription management (3GPP TS 29.552)
@app.get("/ndccf-datamanagement/v1/subscriptions")
async def list_subscriptions():
    """List all active subscriptions"""
    sub_manager = get_subscription_manager()
    subscriptions = await sub_manager.list_subscriptions()
    return {
        "subscriptions": [sub_manager.to_dict(sub) for sub in subscriptions]
    }


@app.post("/ndccf-datamanagement/v1/subscriptions", status_code=201)
async def create_subscription(subscription: dict):
    """
    Create analytics subscription

    3GPP TS 29.552 - Ndccf_DataManagement Subscribe
    """
    sub_manager = get_subscription_manager()

    # Extract subscription parameters
    notification_uri = subscription.get("notificationUri")
    if not notification_uri:
        raise HTTPException(status_code=400, detail="notificationUri is required")

    nf_id = subscription.get("nfId", "unknown")
    event_types = subscription.get("eventTypes", ["NF_LOAD", "UE_MOBILITY", "QOS_SUSTAINABILITY"])
    protocols = subscription.get("protocols", ["http2", "ngap", "pfcp", "gtpu", "nas"])
    notification_interval = subscription.get("notificationInterval", 60)

    # Parse expiry time if provided
    expiry_time = None
    if "expiryTime" in subscription:
        try:
            expiry_time = datetime.fromisoformat(subscription["expiryTime"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

    # Create subscription
    sub = await sub_manager.create_subscription(
        notification_uri=notification_uri,
        nf_id=nf_id,
        event_types=event_types,
        protocols=protocols,
        expiry_time=expiry_time,
        notification_interval=notification_interval
    )

    return sub_manager.to_dict(sub)


@app.get("/ndccf-datamanagement/v1/subscriptions/{subscription_id}")
async def get_subscription(subscription_id: str):
    """Get a specific subscription"""
    sub_manager = get_subscription_manager()
    sub = await sub_manager.get_subscription(subscription_id)

    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    return sub_manager.to_dict(sub)


@app.put("/ndccf-datamanagement/v1/subscriptions/{subscription_id}")
async def update_subscription(subscription_id: str, subscription: dict):
    """Update an existing subscription"""
    sub_manager = get_subscription_manager()

    sub = await sub_manager.update_subscription(
        subscription_id=subscription_id,
        event_types=subscription.get("eventTypes"),
        protocols=subscription.get("protocols"),
        notification_interval=subscription.get("notificationInterval")
    )

    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    return sub_manager.to_dict(sub)


@app.delete("/ndccf-datamanagement/v1/subscriptions/{subscription_id}", status_code=204)
async def delete_subscription(subscription_id: str):
    """Delete a subscription"""
    sub_manager = get_subscription_manager()

    deleted = await sub_manager.delete_subscription(subscription_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Subscription not found")

    return None


@app.post("/ndccf-datamanagement/v1/subscriptions/{subscription_id}/notify")
async def trigger_notification(subscription_id: str):
    """Manually trigger a notification for a subscription (for testing)"""
    sub_manager = get_subscription_manager()
    sub = await sub_manager.get_subscription(subscription_id)

    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    if db_reader is None:
        raise HTTPException(status_code=503, detail="Database not available")

    # Get analytics data based on subscription event types
    analytics_data = {}
    if "NF_LOAD" in sub.event_types:
        analytics_data["nfLoad"] = db_reader.get_nf_load_analytics()
    if "UE_MOBILITY" in sub.event_types:
        analytics_data["ueMobility"] = db_reader.get_ue_mobility_analytics()
    if "QOS_SUSTAINABILITY" in sub.event_types:
        analytics_data["qosSustainability"] = db_reader.get_qos_sustainability_analytics()

    await sub_manager.trigger_notification(subscription_id, analytics_data)

    return {"status": "notification_sent"}


# NRF registration status
@app.get("/nrf/status")
async def nrf_status():
    """Get NRF registration status"""
    return {
        "registered": nrf_client.is_registered if nrf_client else False,
        "nfInstanceId": config.get('nwdaf', {}).get('nfInstanceId', ''),
        "nrfEndpoint": config.get('nrf', {}).get('endpoint', '')
    }


@app.post("/nrf/register")
async def trigger_registration():
    """Manually trigger NRF registration"""
    if nrf_client is None:
        raise HTTPException(status_code=503, detail="NRF client not initialized")

    success = await nrf_client.register()
    if success:
        return {"status": "registered"}
    else:
        raise HTTPException(status_code=500, detail="Registration failed")


if __name__ == "__main__":
    # Note: Use hypercorn for HTTP/2 support in production
    # For development: python3 -m hypercorn main:app --bind 0.0.0.0:8081
    runtime_config = load_config()
    server_cfg = runtime_config.get('ndccf') or runtime_config.get('nadrf') or {}
    port = int(os.getenv("DCCF_PORT", str(server_cfg.get("port", 8081))))
    logger.info(f"Starting DCCF service on port {port}")
    logger.info("Note: Run with hypercorn for HTTP/2 support: hypercorn main:app --bind 0.0.0.0:8081")
    # Fallback to basic server if run directly
    try:
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=port)
    except ImportError:
        logger.error("uvicorn not installed, use: pip install uvicorn OR run with: hypercorn main:app")
