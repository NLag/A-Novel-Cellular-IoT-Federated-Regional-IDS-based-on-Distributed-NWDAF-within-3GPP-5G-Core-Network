#!/usr/bin/env python3
"""
Database Reader for DCCF Service
Reads protocol events from Casmella's SQLite database
"""
import sqlite3
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class DatabaseReader:
    """Reads protocol events from Casmella's database"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._check_database()

    def _check_database(self):
        """Check if database exists and is accessible"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='protocol_events'")
                if not cursor.fetchone():
                    logger.warning(f"Database table 'protocol_events' not found at {self.db_path}")
                else:
                    logger.info(f"Connected to Casmella database at {self.db_path}")
        except Exception as e:
            logger.error(f"Cannot connect to database at {self.db_path}: {e}")

    @contextmanager
    def _get_connection(self):
        """Get a database connection"""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def get_events(
        self,
        protocol: Optional[str] = None,
        event_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Query protocol events from database

        Args:
            protocol: Filter by protocol (http2, pfcp, ngap, nas, gtpu)
            event_type: Filter by event type
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum number of results

        Returns:
            List of event dictionaries
        """
        query = "SELECT * FROM protocol_events WHERE 1=1"
        params = []

        if protocol:
            query += " AND protocol = ?"
            params.append(protocol)

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)

        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())

        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error querying events: {e}")
            return []

    def get_nf_load_analytics(self, nf_type: Optional[str] = None, time_window_minutes: int = 15) -> Dict:
        """
        Get NF Load analytics (3GPP event type)

        Args:
            nf_type: Filter by NF type (AMF, SMF, UPF, etc.)
            time_window_minutes: Time window for analytics

        Returns:
            NF Load analytics data
        """
        start_time = datetime.utcnow() - timedelta(minutes=time_window_minutes)

        query = """
            SELECT
                src_pod_name,
                dst_pod_name,
                protocol,
                COUNT(*) as event_count,
                AVG(CAST(json_extract(metadata, '$.response_time_ms') AS REAL)) as avg_response_time
            FROM protocol_events
            WHERE timestamp >= ? AND protocol = 'http2'
            GROUP BY src_pod_name, dst_pod_name, protocol
        """

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, [start_time.isoformat()])
                rows = cursor.fetchall()

                return {
                    "analyticsType": "NF_LOAD",
                    "timeWindow": {
                        "startTime": start_time.isoformat(),
                        "endTime": datetime.utcnow().isoformat()
                    },
                    "nfLoadData": [
                        {
                            "nfInstanceId": row['src_pod_name'] or row['dst_pod_name'],
                            "eventCount": row['event_count'],
                            "avgResponseTimeMs": row['avg_response_time']
                        }
                        for row in rows
                    ]
                }
        except Exception as e:
            logger.error(f"Error getting NF Load analytics: {e}")
            return {"analyticsType": "NF_LOAD", "nfLoadData": []}

    def get_ue_mobility_analytics(self, time_window_minutes: int = 15) -> Dict:
        """
        Get UE Mobility analytics from NGAP events

        Args:
            time_window_minutes: Time window for analytics

        Returns:
            UE Mobility analytics data
        """
        start_time = datetime.utcnow() - timedelta(minutes=time_window_minutes)

        query = """
            SELECT
                event_type,
                COUNT(*) as event_count,
                metadata
            FROM protocol_events
            WHERE timestamp >= ? AND protocol = 'ngap'
            GROUP BY event_type
        """

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, [start_time.isoformat()])
                rows = cursor.fetchall()

                return {
                    "analyticsType": "UE_MOBILITY",
                    "timeWindow": {
                        "startTime": start_time.isoformat(),
                        "endTime": datetime.utcnow().isoformat()
                    },
                    "mobilityEvents": [
                        {
                            "eventType": row['event_type'],
                            "count": row['event_count']
                        }
                        for row in rows
                    ]
                }
        except Exception as e:
            logger.error(f"Error getting UE Mobility analytics: {e}")
            return {"analyticsType": "UE_MOBILITY", "mobilityEvents": []}

    def get_qos_sustainability_analytics(self, time_window_minutes: int = 15) -> Dict:
        """
        Get QoS Sustainability analytics from GTP-U and PFCP events

        Args:
            time_window_minutes: Time window for analytics

        Returns:
            QoS Sustainability analytics data
        """
        start_time = datetime.utcnow() - timedelta(minutes=time_window_minutes)

        query = """
            SELECT
                protocol,
                event_type,
                COUNT(*) as event_count
            FROM protocol_events
            WHERE timestamp >= ? AND protocol IN ('gtpu', 'pfcp')
            GROUP BY protocol, event_type
        """

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, [start_time.isoformat()])
                rows = cursor.fetchall()

                return {
                    "analyticsType": "QOS_SUSTAINABILITY",
                    "timeWindow": {
                        "startTime": start_time.isoformat(),
                        "endTime": datetime.utcnow().isoformat()
                    },
                    "qosEvents": [
                        {
                            "protocol": row['protocol'],
                            "eventType": row['event_type'],
                            "count": row['event_count']
                        }
                        for row in rows
                    ]
                }
        except Exception as e:
            logger.error(f"Error getting QoS analytics: {e}")
            return {"analyticsType": "QOS_SUSTAINABILITY", "qosEvents": []}

    def get_event_count(self, protocol: Optional[str] = None) -> int:
        """Get total event count"""
        query = "SELECT COUNT(*) FROM protocol_events"
        params = []

        if protocol:
            query += " WHERE protocol = ?"
            params.append(protocol)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Error getting event count: {e}")
            return 0

    def _ensure_nf_events_table(self):
        """Create nf_events table if it doesn't exist"""
        create_table_sql = """
            CREATE TABLE IF NOT EXISTS nf_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                data TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(create_table_sql)
                conn.commit()
        except Exception as e:
            logger.error(f"Error creating nf_events table: {e}")

    def store_nf_event(self, event_data: Dict):
        """
        Store an NF event (AMF/SMF notification) in the database

        Args:
            event_data: Dict with source, event_type, timestamp, data
        """
        import json

        # Ensure table exists
        self._ensure_nf_events_table()

        insert_sql = """
            INSERT INTO nf_events (source, event_type, timestamp, data)
            VALUES (?, ?, ?, ?)
        """

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(insert_sql, [
                    event_data.get('source', 'UNKNOWN'),
                    event_data.get('event_type', 'UNKNOWN'),
                    event_data.get('timestamp', datetime.utcnow().isoformat()),
                    json.dumps(event_data.get('data', {}))
                ])
                conn.commit()
                logger.debug(f"Stored NF event: {event_data.get('source')} - {event_data.get('event_type')}")
        except Exception as e:
            logger.error(f"Error storing NF event: {e}")
            raise

    def get_nf_events(
        self,
        source: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Query NF events from database

        Args:
            source: Filter by source (AMF, SMF)
            event_type: Filter by event type
            limit: Maximum number of results

        Returns:
            List of event dictionaries
        """
        import json

        # Ensure table exists
        self._ensure_nf_events_table()

        query = "SELECT * FROM nf_events WHERE 1=1"
        params = []

        if source:
            query += " AND source = ?"
            params.append(source)

        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()
                result = []
                for row in rows:
                    row_dict = dict(row)
                    if row_dict.get('data'):
                        try:
                            row_dict['data'] = json.loads(row_dict['data'])
                        except:
                            pass
                    result.append(row_dict)
                return result
        except Exception as e:
            logger.error(f"Error querying NF events: {e}")
            return []

    def get_nf_event_count(self, source: Optional[str] = None) -> int:
        """Get NF event count"""
        # Ensure table exists
        self._ensure_nf_events_table()

        query = "SELECT COUNT(*) FROM nf_events"
        params = []

        if source:
            query += " WHERE source = ?"
            params.append(source)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Error getting NF event count: {e}")
            return 0

    def _ensure_ids_reports_table(self):
        """Create ids_reports table if it doesn't exist."""
        create_table_sql = """
            CREATE TABLE IF NOT EXISTS ids_reports (
                report_id TEXT PRIMARY KEY,
                region TEXT,
                tac TEXT,
                predicted_class TEXT,
                timestamp TEXT,
                received_at TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(create_table_sql)
                conn.commit()
        except Exception as e:
            logger.error(f"Error creating ids_reports table: {e}")

    def store_ids_report(self, report: Dict):
        """
        Store an IDS detection report in the local DCCF database.

        Args:
            report: Normalized IDS report record with reportId and metadata.
        """
        import json

        self._ensure_ids_reports_table()
        report_id = report.get("reportId")
        if not report_id:
            raise ValueError("reportId is required")

        insert_sql = """
            INSERT OR REPLACE INTO ids_reports (
                report_id,
                region,
                tac,
                predicted_class,
                timestamp,
                received_at,
                data
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(insert_sql, [
                    report_id,
                    report.get("region"),
                    report.get("tac"),
                    report.get("predictedClass"),
                    str(report.get("timestamp")) if report.get("timestamp") is not None else None,
                    report.get("receivedAt", datetime.utcnow().isoformat()),
                    json.dumps(report),
                ])
                conn.commit()
                logger.debug(f"Stored IDS report: {report_id}")
        except Exception as e:
            logger.error(f"Error storing IDS report {report_id}: {e}")
            raise

    def get_ids_reports(
        self,
        region: Optional[str] = None,
        predicted_class: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Query IDS reports from the local DCCF database."""
        import json

        self._ensure_ids_reports_table()
        query = "SELECT data FROM ids_reports WHERE 1=1"
        params = []

        if region:
            query += " AND region = ?"
            params.append(region)
        if predicted_class:
            query += " AND predicted_class = ?"
            params.append(predicted_class)

        query += " ORDER BY received_at DESC LIMIT ?"
        params.append(limit)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                rows = cursor.fetchall()
                reports = []
                for row in rows:
                    try:
                        reports.append(json.loads(row["data"]))
                    except Exception:
                        logger.warning("Skipping malformed IDS report row")
                return reports
        except Exception as e:
            logger.error(f"Error querying IDS reports: {e}")
            return []

    def get_ids_report_count(self, region: Optional[str] = None) -> int:
        """Get IDS report count."""
        self._ensure_ids_reports_table()
        query = "SELECT COUNT(*) FROM ids_reports"
        params = []
        if region:
            query += " WHERE region = ?"
            params.append(region)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"Error getting IDS report count: {e}")
            return 0
