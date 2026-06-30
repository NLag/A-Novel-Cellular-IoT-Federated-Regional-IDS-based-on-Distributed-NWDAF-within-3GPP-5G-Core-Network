#!/usr/bin/env python3
"""MongoDB metadata records for files stored in OAI_5G_STORAGE."""
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

logger = logging.getLogger(__name__)


class StorageMetadataStore:
    """Records shared-storage file metadata in the NWDAF MongoDB database."""

    def __init__(
        self,
        uri: str,
        database_name: str,
        collection_name: str,
        storage_root: str,
        timeout_ms: int = 3000,
    ):
        from pymongo import MongoClient

        self.storage_root = Path(storage_root).resolve()
        self.client = MongoClient(uri, serverSelectionTimeoutMS=timeout_ms)
        self.database = self.client[database_name]
        self.collection = self.database[collection_name]
        self.client.admin.command("ping")
        self.collection.create_index("storagePath", unique=True)
        self.collection.create_index("category")
        self.collection.create_index("region")
        self.collection.create_index("trainingScenario")
        self.collection.create_index("jobId")
        logger.info(
            "Connected to MongoDB shared-storage metadata %s/%s",
            database_name,
            collection_name,
        )

    def close(self):
        self.client.close()

    def _relative_path(self, file_path: Path) -> str:
        resolved = file_path.resolve()
        try:
            return str(resolved.relative_to(self.storage_root))
        except ValueError as exc:
            raise ValueError(
                f"{resolved} is outside shared storage root {self.storage_root}"
            ) from exc

    def record_file(
        self,
        file_path: str | Path,
        *,
        category: str,
        producer_nf: str,
        region: Optional[str] = None,
        tac: Optional[str] = None,
        job_id: Optional[str] = None,
        model_id: Optional[str] = None,
        training_scenario: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        path = Path(file_path)
        if not path.is_file():
            raise ValueError(f"shared-storage metadata target is not a file: {path}")

        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)

        stat = path.stat()
        storage_path = self._relative_path(path)
        document = {
            "storagePath": storage_path,
            "absolutePath": str(path.resolve()),
            "category": category,
            "producerNf": producer_nf,
            "region": region,
            "tac": tac,
            "jobId": job_id,
            "modelId": model_id,
            "trainingScenario": training_scenario,
            "sizeBytes": stat.st_size,
            "sha256": digest.hexdigest(),
            "modifiedAt": datetime.utcfromtimestamp(stat.st_mtime).isoformat(),
            "recordedAt": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }
        self.collection.replace_one(
            {"storagePath": storage_path},
            document,
            upsert=True,
        )
        return document

    def record_files(
        self,
        file_paths: Iterable[str | Path],
        **kwargs,
    ) -> list[Dict[str, Any]]:
        records = []
        for file_path in file_paths:
            try:
                records.append(self.record_file(file_path, **kwargs))
            except Exception as exc:
                logger.warning("Could not record shared-storage file %s: %s", file_path, exc)
        return records

    def list_files(
        self,
        *,
        category: Optional[str] = None,
        region: Optional[str] = None,
        training_scenario: Optional[str] = None,
        limit: int = 100,
    ) -> list[Dict[str, Any]]:
        query = {}
        if category:
            query["category"] = category
        if region:
            query["region"] = region
        if training_scenario:
            query["trainingScenario"] = training_scenario
        cursor = (
            self.collection.find(query)
            .sort("recordedAt", -1)
            .limit(limit)
        )
        records = []
        for document in cursor:
            document.pop("_id", None)
            records.append(document)
        return records
