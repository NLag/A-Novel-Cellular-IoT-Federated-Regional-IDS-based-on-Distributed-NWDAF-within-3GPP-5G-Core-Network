"""Database module for storing protocol events.

Provides SQLite database storage with background writer for non-blocking writes.
Designed for 3GPP compliance with OAI NWDAF integration.
"""
# standard
import json
import sqlite3
import threading
import time
from queue import Queue, Empty
from typing import Optional, Dict, Any

# internal
from . import cfg

# Module-level variables
_db_path: Optional[str] = None
_db_enabled: bool = False
_db_retention_hours: int = 24
_event_queue: Queue = Queue()
_writer_thread: Optional[threading.Thread] = None
_shutdown_event: threading.Event = threading.Event()

# Boot time offset for converting monotonic timestamps to wall clock timestamps
# eBPF uses bpf_ktime_get_ns() which returns monotonic time (nanoseconds since boot)
# We need to convert to wall clock time for proper timestamp storage
_boot_offset: float = time.time() - time.monotonic()

logger = cfg.logging


def initialize_database(db_path: str, enabled: bool = True, retention_hours: int = 24):
    """Initialize the database module.

    Args:
        db_path: Path to the SQLite database file
        enabled: Whether database storage is enabled
        retention_hours: Hours to retain data before cleanup
    """
    global _db_path, _db_enabled, _db_retention_hours, _writer_thread

    _db_path = db_path
    _db_enabled = enabled
    _db_retention_hours = retention_hours

    if not _db_enabled:
        logger.info("Database storage is disabled")
        return

    # Create database and tables
    _create_tables()

    # Start background writer thread
    _shutdown_event.clear()
    _writer_thread = threading.Thread(
        target=_background_writer,
        name='DatabaseWriter',
        daemon=True
    )
    _writer_thread.start()
    logger.info(f"Database initialized at {db_path}")


def _create_tables():
    """Create database tables if they don't exist."""
    conn = sqlite3.connect(_db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Main protocol events table - 3GPP compliant structure
    conn.execute("""
        CREATE TABLE IF NOT EXISTS protocol_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            protocol TEXT NOT NULL,
            event_type TEXT NOT NULL,
            src_ip TEXT,
            dst_ip TEXT,
            src_port INTEGER,
            dst_port INTEGER,
            src_pod_name TEXT,
            dst_pod_name TEXT,
            src_node_name TEXT,
            dst_node_name TEXT,
            metadata TEXT,
            created_at REAL DEFAULT (strftime('%s', 'now'))
        )
    """)

    # Create indexes for common queries
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_protocol_events_timestamp
        ON protocol_events(timestamp)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_protocol_events_protocol
        ON protocol_events(protocol, event_type)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_protocol_events_src_pod
        ON protocol_events(src_pod_name)
    """)

    conn.commit()
    conn.close()


def _background_writer():
    """Background thread for batch writing events to database."""
    batch_size = 100
    batch_timeout = 1.0  # seconds

    while not _shutdown_event.is_set():
        batch = []
        deadline = time.time() + batch_timeout

        # Collect events for batch
        while len(batch) < batch_size and time.time() < deadline:
            try:
                remaining = deadline - time.time()
                if remaining <= 0:
                    break
                event = _event_queue.get(timeout=min(remaining, 0.1))
                batch.append(event)
            except Empty:
                continue

        # Write batch to database
        if batch:
            _write_batch(batch)

        # Periodic cleanup
        if time.time() % 3600 < batch_timeout:
            _cleanup_old_events()


def _write_batch(batch: list):
    """Write a batch of events to the database."""
    try:
        conn = sqlite3.connect(_db_path)
        cursor = conn.cursor()

        cursor.executemany("""
            INSERT INTO protocol_events
            (timestamp, protocol, event_type, src_ip, dst_ip, src_port, dst_port,
             src_pod_name, dst_pod_name, src_node_name, dst_node_name, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, batch)

        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Database write error: {e}")


def _cleanup_old_events():
    """Remove events older than retention period."""
    if not _db_enabled or not _db_path:
        return

    try:
        cutoff = time.time() - (_db_retention_hours * 3600)
        conn = sqlite3.connect(_db_path)
        conn.execute("DELETE FROM protocol_events WHERE timestamp < ?", (cutoff,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Database cleanup error: {e}")


def insert_event(protocol: str, event_type: str, timestamp: float,
                 src_ip: str = None, dst_ip: str = None,
                 src_port: int = None, dst_port: int = None,
                 pod_info: Dict[str, Any] = None,
                 metadata: Dict[str, Any] = None):
    """Insert a protocol event into the database queue.

    Args:
        protocol: Protocol name (http2, pfcp, ngap, nas, gtp)
        event_type: Type of event (request, response, etc.)
        timestamp: Event timestamp (monotonic time from eBPF in seconds)
        src_ip: Source IP address
        dst_ip: Destination IP address
        src_port: Source port
        dst_port: Destination port
        pod_info: Pod/node information dictionary
        metadata: Additional event metadata
    """
    if not _db_enabled:
        return

    # Convert monotonic timestamp (from eBPF) to wall clock timestamp
    # eBPF uses bpf_ktime_get_ns() which returns time since boot
    # Add boot offset to get actual wall clock time
    wall_clock_timestamp = timestamp + _boot_offset

    # Extract pod info
    src_pod_name = None
    dst_pod_name = None
    src_node_name = None
    dst_node_name = None

    if pod_info:
        # Handle server/client naming convention
        src_pod_name = pod_info.get('src_pod_name') or pod_info.get('server_pod_name')
        dst_pod_name = pod_info.get('dst_pod_name') or pod_info.get('client_pod_name')
        src_node_name = pod_info.get('src_node_name') or pod_info.get('server_node_name')
        dst_node_name = pod_info.get('dst_node_name') or pod_info.get('client_node_name')

    # Serialize metadata
    metadata_json = json.dumps(metadata) if metadata else None

    # Queue event for batch writing (using wall clock timestamp)
    event = (
        wall_clock_timestamp, protocol, event_type, src_ip, dst_ip, src_port, dst_port,
        src_pod_name, dst_pod_name, src_node_name, dst_node_name, metadata_json
    )
    _event_queue.put(event)


def insert_http2_event(event_type: str, timestamp: float,
                       src_ip: str, dst_ip: str,
                       src_port: int, dst_port: int,
                       server_and_client: Dict[str, Any],
                       operation_id: str = None,
                       method: str = None, scheme: str = None,
                       path: str = None, status_code: str = None,
                       response_status: str = None, response_time: float = None):
    """Insert an HTTP/2 protocol event."""
    metadata = {
        'operation_id': operation_id,
        'method': method,
        'scheme': scheme,
        'path': path,
        'status_code': status_code,
        'response_status': response_status,
        'response_time': response_time
    }
    # Remove None values
    metadata = {k: v for k, v in metadata.items() if v is not None}

    insert_event(
        protocol='http2',
        event_type=event_type,
        timestamp=timestamp,
        src_ip=src_ip,
        dst_ip=dst_ip,
        src_port=src_port,
        dst_port=dst_port,
        pod_info=server_and_client,
        metadata=metadata
    )


def insert_pfcp_event(event_type: str, timestamp: float,
                      src_ip: str, dst_ip: str,
                      server_and_client: Dict[str, Any],
                      message_type: str = None,
                      seid: int = None, sequence_number: int = None,
                      response_time: float = None, cause: str = None):
    """Insert a PFCP protocol event."""
    metadata = {
        'message_type': message_type,
        'seid': seid,
        'sequence_number': sequence_number,
        'response_time': response_time,
        'cause': cause
    }
    metadata = {k: v for k, v in metadata.items() if v is not None}

    insert_event(
        protocol='pfcp',
        event_type=event_type,
        timestamp=timestamp,
        src_ip=src_ip,
        dst_ip=dst_ip,
        pod_info=server_and_client,
        metadata=metadata
    )


def insert_ngap_event(event_type: str, timestamp: float,
                      src_ip: str, dst_ip: str,
                      source_and_destination: Dict[str, Any],
                      message_type: str = None,
                      procedure: str = None,
                      ran_ue_ngap_id: int = None,
                      amf_ue_ngap_id: int = None,
                      cause: str = None):
    """Insert an NGAP protocol event."""
    metadata = {
        'message_type': message_type,
        'procedure': procedure,
        'ran_ue_ngap_id': ran_ue_ngap_id,
        'amf_ue_ngap_id': amf_ue_ngap_id,
        'cause': cause
    }
    metadata = {k: v for k, v in metadata.items() if v is not None}

    insert_event(
        protocol='ngap',
        event_type=event_type,
        timestamp=timestamp,
        src_ip=src_ip,
        dst_ip=dst_ip,
        pod_info=source_and_destination,
        metadata=metadata
    )


def insert_nas_event(event_type: str, timestamp: float,
                     src_ip: str, dst_ip: str,
                     source_and_destination: Dict[str, Any],
                     message_type: str = None,
                     registration_type: str = None,
                     cause: str = None,
                     response_time: float = None,
                     ngap_procedure: str = None):
    """Insert a NAS protocol event."""
    metadata = {
        'message_type': message_type,
        'registration_type': registration_type,
        'cause': cause,
        'response_time': response_time,
        'ngap_procedure': ngap_procedure
    }
    metadata = {k: v for k, v in metadata.items() if v is not None}

    insert_event(
        protocol='nas',
        event_type=event_type,
        timestamp=timestamp,
        src_ip=src_ip,
        dst_ip=dst_ip,
        pod_info=source_and_destination,
        metadata=metadata
    )


def insert_gtp_event(event_type: str, timestamp: float,
                     src_ip: str, dst_ip: str,
                     source_and_destination: Dict[str, Any],
                     message_type: str = None,
                     teid: int = None,
                     sequence_number: int = None,
                     inner_protocol: str = None):
    """Insert a GTP-U protocol event."""
    metadata = {
        'message_type': message_type,
        'teid': teid,
        'sequence_number': sequence_number,
        'inner_protocol': inner_protocol
    }
    metadata = {k: v for k, v in metadata.items() if v is not None}

    insert_event(
        protocol='gtp',
        event_type=event_type,
        timestamp=timestamp,
        src_ip=src_ip,
        dst_ip=dst_ip,
        pod_info=source_and_destination,
        metadata=metadata
    )


def get_events(protocol: str = None, start_time: float = None,
               end_time: float = None, limit: int = 1000) -> list:
    """Query events from the database.

    Args:
        protocol: Filter by protocol name
        start_time: Filter events after this timestamp
        end_time: Filter events before this timestamp
        limit: Maximum number of events to return

    Returns:
        List of event dictionaries
    """
    if not _db_enabled or not _db_path:
        return []

    try:
        conn = sqlite3.connect(_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT * FROM protocol_events WHERE 1=1"
        params = []

        if protocol:
            query += " AND protocol = ?"
            params.append(protocol)
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        # Convert to list of dicts
        events = []
        for row in rows:
            event = dict(row)
            if event.get('metadata'):
                event['metadata'] = json.loads(event['metadata'])
            events.append(event)

        return events
    except Exception as e:
        logger.error(f"Database query error: {e}")
        return []


def shutdown():
    """Shutdown the database module gracefully."""
    global _writer_thread

    if _writer_thread and _writer_thread.is_alive():
        _shutdown_event.set()
        _writer_thread.join(timeout=5)
        logger.info("Database writer thread stopped")
