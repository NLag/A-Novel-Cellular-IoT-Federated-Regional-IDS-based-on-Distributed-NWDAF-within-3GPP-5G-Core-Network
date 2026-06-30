#!/usr/bin/env python3
"""
MongoDB-backed IDS report storage for DCCF.

This is the primary storage path for IDS reports in the NWDAF lab. The DCCF
SQLite store remains a local fallback for environments where MongoDB is not
available.
"""
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class MongoIdsReportStore:
    """Stores IDS reports in the NWDAF MongoDB database."""

    def __init__(
        self,
        uri: str,
        database_name: str,
        collection_name: str,
        timeout_ms: int = 3000,
    ):
        from pymongo import MongoClient

        self.client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
        self.database = self.client[database_name]
        self.collection = self.database[collection_name]
        self.client.admin.command("ping")
        self.collection.create_index("reportId", unique=True)
        self.collection.create_index("region")
        self.collection.create_index("predictedClass")
        logger.info(
            "Connected to MongoDB IDS report store %s/%s",
            database_name,
            collection_name,
        )

    def store_ids_report(self, report: Dict):
        report_id = report.get("reportId")
        if not report_id:
            raise ValueError("reportId is required")
        document = dict(report)
        document["_id"] = report_id
        self.collection.replace_one({"_id": report_id}, document, upsert=True)
        logger.debug("Stored IDS report in MongoDB: %s", report_id)

    def get_ids_reports(
        self,
        region: Optional[str] = None,
        predicted_class: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        query = {}
        if region:
            query["region"] = region
        if predicted_class:
            query["predictedClass"] = predicted_class

        cursor = (
            self.collection.find(query)
            .sort("receivedAt", -1)
            .limit(limit)
        )
        reports = []
        for document in cursor:
            document.pop("_id", None)
            reports.append(document)
        return reports

    def get_ids_report_count(self, region: Optional[str] = None) -> int:
        query = {}
        if region:
            query["region"] = region
        return self.collection.count_documents(query)

    def close(self):
        self.client.close()
