#!/usr/bin/env python3
"""
MTLF — Model Training Logical Function
Implements Nnwdaf_MLModelProvision service (3GPP TS 29.520 Release 17)

The MTLF is the sub-function of NWDAF responsible for training ML models
(TS 23.288 §6.2A). Externally it exposes the Nnwdaf_MLModelProvision service
which allows consumers (AnLF, other NFs) to subscribe to trained model
availability notifications.

Standardized API surface (TS 29.520 Table 6.1.3.2-1):
  POST   /nnwdaf-mlmodelprovision/v1/subscriptions          Subscribe
  DELETE /nnwdaf-mlmodelprovision/v1/subscriptions/{subId}  Unsubscribe

  GET    /nnwdaf-mlmodelprovision/v1/ml-models              List models
  GET    /nnwdaf-mlmodelprovision/v1/ml-models/{modelId}    Get model info
  GET    /nnwdaf-mlmodelprovision/v1/ml-models/{modelId}/manifest  IDS metadata
  GET    /nnwdaf-mlmodelprovision/v1/ml-models/{modelId}/file  Download model

Non-standardized (proprietary, not part of 3GPP spec):
  POST   /proprietary/v1/training-jobs        Trigger training job
  GET    /proprietary/v1/training-jobs        List jobs
  GET    /proprietary/v1/training-jobs/{id}   Job status
  DELETE /proprietary/v1/training-jobs/{id}   Cancel job
Internal callback (not NF-visible):
  POST   /mtlf-internal/dccf-notifications    Receive DCCF push data

Health / management:
  GET    /health
  GET    /ready
  GET    /nrf/status
  POST   /nrf/register
"""
import logging
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, FileResponse

from nrf_client import NRFClient
from dccf_client import DCCFClient
from training_manager import TrainingManager
from subscription_manager import get_subscription_manager
from storage_metadata import StorageMetadataStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="NWDAF-MTLF",
    description=(
        "Model Training Logical Function — "
        "Nnwdaf_MLModelProvision, 3GPP TS 29.520 Release 17"
    ),
    version="17.0.0",
)

# ---------------------------------------------------------------------------
# 3GPP ProblemDetails helper (TS 29.571 §5.2.5)
# ---------------------------------------------------------------------------

def problem(status: int, title: str, detail: str, instance: str = "") -> JSONResponse:
    """Return a 3GPP-compliant ProblemDetails error response."""
    body = {
        "type":     "about:blank",
        "title":    title,
        "status":   status,
        "detail":   detail,
    }
    if instance:
        body["instance"] = instance
    return JSONResponse(status_code=status, content=body,
                        media_type="application/problem+json")


# ---------------------------------------------------------------------------
# Global singletons
# ---------------------------------------------------------------------------

nrf_client:       Optional[NRFClient]       = None
dccf_client:      Optional[DCCFClient]      = None
training_manager: Optional[TrainingManager] = None
storage_metadata_store: Optional[StorageMetadataStore] = None
config:           dict = {}

# In-memory model registry  { model_id: {...} }
_model_registry: dict = {}


def build_model_registry_entry(
    model_id: str,
    job_id: str,
    model_dir: str,
    metrics: dict[str, Any],
    base_uri: str,
    nf_instance_id: str,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry = {
        "modelId":            model_id,
        "modelVersion":       model_id,
        "jobId":              job_id,
        "modelDir":           model_dir,
        "artifactFileName":   "model.pt",
        "metrics":            metrics,
        "createdAt":          datetime.utcnow().isoformat(),
        "mLEvent":            "ABNORMAL_BEHAVIOUR",
        "trainingScenario":   "regional",
        "framework":          "pytorch",
        "frameworkVersion":   "",
        "architecture":       "Transformer",
        "modelParameters":    {},
        "artifactType":       "pytorch-state-dict",
        "sourceNfInstanceId": nf_instance_id,
        "idsCompatible":      False,
        "compatibilityNote": (
            "IDS packet-classification artifact produced by MTLF. IDS runtime "
            "loading and checksum validation are tracked in Workstream 2.3."
        ),
        "mlModelUrl":         (
            f"{base_uri}/nnwdaf-mlmodelprovision/v1/ml-models/{model_id}/file"
        ),
        "manifestUrl":        (
            f"{base_uri}/nnwdaf-mlmodelprovision/v1/ml-models/{model_id}/manifest"
        ),
    }
    if overrides:
        entry.update(overrides)
    return entry


def build_ids_model_manifest(entry: dict[str, Any]) -> dict[str, Any]:
    """Expose a stable IDS-facing manifest for a trained NWDAF model."""
    return {
        "modelVersion": entry.get("modelVersion", entry.get("modelId", "")),
        "architecture": entry.get("architecture", "Transformer"),
        "modelParameters": entry.get("modelParameters", {}),
        "artifactType": entry.get("artifactType", "pytorch-state-dict"),
        "labelMap": entry.get("labelMap", {}),
        "packetSize": entry.get("packetSize"),
        "sequenceSize": entry.get("sequenceSize"),
        "checksum": entry.get("checksum", ""),
        "source": {
            "nf": "NWDAF",
            "nfInstanceId": entry.get("sourceNfInstanceId", ""),
            "uri": entry.get("mlModelUrl", ""),
        },
        "mLEvent": entry.get("mLEvent", "ABNORMAL_BEHAVIOUR"),
        "metrics": entry.get("metrics", {}),
        "servingArea": entry.get("servingArea", {}),
        "trainingScenario": entry.get("trainingScenario", ""),
        "framework": entry.get("framework", ""),
        "frameworkVersion": entry.get("frameworkVersion", ""),
        "datasetManifest": entry.get("datasetManifest", {}),
        "evaluation": entry.get("evaluation", {}),
        "idsCompatible": entry.get("idsCompatible", False),
        "compatibilityNote": entry.get(
            "compatibilityNote",
            "IDS packet-classification artifact produced by MTLF. IDS runtime "
            "loading and checksum validation are tracked in Workstream 2.3.",
        ),
    }


def seed_test_stub_model(runtime_config: dict[str, Any], nf_instance_id: str) -> None:
    stub_cfg = runtime_config.get("test_stub_model", {})
    if not stub_cfg.get("enabled", False):
        return

    model_id = str(stub_cfg.get("model_id", "stub-latest"))
    if model_id in _model_registry:
        return

    training_cfg = runtime_config.get("training", {})
    models_dir = Path(training_cfg.get("models_dir", "/models"))
    model_dir = models_dir / model_id
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "model.pt"
    weight_bytes = int(stub_cfg.get("weight_bytes", 4096))
    if not model_path.exists():
        model_path.write_bytes(os.urandom(weight_bytes))

    digest = hashlib.sha256()
    with model_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)

    base_uri = runtime_config.get("callback_uri", "http://localhost:8082")
    checksum = f"sha256:{digest.hexdigest()}"
    _model_registry[model_id] = build_model_registry_entry(
        model_id=model_id,
        job_id=str(stub_cfg.get("job_id", "stub-latest-job")),
        model_dir=str(model_dir),
        metrics={
            "stub": True,
            "weightBytes": model_path.stat().st_size,
        },
        base_uri=base_uri,
        nf_instance_id=nf_instance_id,
        overrides={
            "architecture": str(stub_cfg.get("architecture", "stub-random-weights")),
            "modelParameters": {},
            "artifactType": str(stub_cfg.get("artifact_type", "stub-random-weights")),
            "artifactFileName": model_path.name,
            "checksum": checksum,
            "servingArea": runtime_config.get("serving_area", {}),
            "trainingScenario": runtime_config.get("training_scenario", {}).get("scenario", "stub"),
            "idsCompatible": False,
            "compatibilityNote": (
                "Development stub model with random bytes. It exists only to "
                "exercise IDS/NWDAF metadata, notification, and file-serving "
                "interactions."
            ),
        },
    )
    record_shared_file_metadata(
        model_path,
        category="model",
        job_id=str(stub_cfg.get("job_id", "stub-latest-job")),
        model_id=model_id,
        training_scenario=runtime_config.get("training_scenario", {}).get("scenario", "stub"),
        metadata={"stub": True, "weightBytes": model_path.stat().st_size},
    )
    logger.info(f"Seeded test stub model {model_id} at {model_path}")


def connect_storage_metadata_store() -> Optional[StorageMetadataStore]:
    global storage_metadata_store

    if storage_metadata_store is not None:
        return storage_metadata_store

    mongo_cfg = config.get("mongodb", {})
    shared_cfg = config.get("shared_storage", {})
    if not mongo_cfg.get("enabled", False) or not shared_cfg.get("metadata_enabled", True):
        return None

    try:
        storage_metadata_store = StorageMetadataStore(
            uri=mongo_cfg.get("uri", ""),
            database_name=mongo_cfg.get("database_name", "testing"),
            collection_name=mongo_cfg.get("storage_metadata_collection", "storage_metadata"),
            storage_root=shared_cfg.get("root", "/oai-5g-storage"),
            timeout_ms=int(mongo_cfg.get("timeout_ms", 3000)),
        )
        return storage_metadata_store
    except Exception as exc:
        logger.warning(
            "Shared-storage metadata store unavailable; files will still be written: %s",
            exc,
        )
        return None


def drop_storage_metadata_store():
    global storage_metadata_store

    if storage_metadata_store is not None:
        try:
            storage_metadata_store.close()
        except Exception as exc:
            logger.debug("Error closing shared-storage metadata store: %s", exc)
        storage_metadata_store = None


def record_shared_file_metadata(
    file_path: str | Path,
    *,
    category: str,
    job_id: str | None = None,
    model_id: str | None = None,
    training_scenario: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    store = connect_storage_metadata_store()
    if store is None:
        return None
    try:
        return store.record_file(
            file_path,
            category=category,
            producer_nf="MTLF",
            region=config.get("serving_area", {}).get("region"),
            tac=config.get("serving_area", {}).get("tac"),
            job_id=job_id,
            model_id=model_id,
            training_scenario=training_scenario,
            metadata=metadata,
        )
    except Exception as exc:
        logger.warning("Could not record shared-storage metadata for %s: %s", file_path, exc)
        return None


def find_job_model_artifact(job: Any, model_dir: str) -> Path | None:
    candidates: list[Path] = []
    if job:
        for record in getattr(job, "recorded_files", []) or []:
            absolute_path = record.get("absolutePath")
            if absolute_path and Path(absolute_path).suffix in {".pt", ".pth"}:
                candidates.append(Path(absolute_path))
    model_dir_path = Path(model_dir)
    for pattern in ("model.pt", "*.pt", "*.pth"):
        candidates.extend(model_dir_path.glob(pattern))

    existing = [path for path in candidates if path.is_file()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(path: str = None) -> dict:
    path = path or os.getenv("MTLF_CONFIG_PATH", "/config/mtlf-config.yaml")
    try:
        with open(path) as fh:
            return yaml.safe_load(fh)
    except FileNotFoundError:
        logger.warning(f"Config not found at {path}, using defaults")
        return {
            "mtlf":     {"nfInstanceId": "nwdaf-mtlf-001", "nfType": "NWDAF",
                         "ipv4Address": ""},
            "nrf":      {"endpoint": "", "auto_register": False},
            "server":   {"port": 8082},
            "dccf":     {
                "endpoint": "http://oai-nwdaf-dccf:8081",
                "notification_uri": (
                    "http://oai-nwdaf-mtlf-service:8082"
                    "/mtlf-internal/dccf-notifications"
                ),
                "event_types":         ["NF_LOAD", "UE_MOBILITY"],
                "protocols":           ["http2", "ngap", "pfcp"],
                "notification_interval": 60,
            },
            "training": {
                "script_path":    "/oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research/DL_multiclass_regional_models.py",
                "models_dir":     "/oai-5g-storage/IDS_RELATED_STORAGE/MODEL",
                "default_epochs": 100,
                "python_bin":     "python3",
                "pass_output_dir_args": False,
                "working_dir": "/oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research",
                "research_workspace": "/oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research",
                "normalized_package": "nwdaf_mtlf_model_training",
            },
            "training_scenario": {
                "scenario": "regional",
                "model_architecture": "Transformer",
                "model_architectures": {
                    "MLP": {"hidden_dim": 256},
                    "CNN": {},
                    "RNN": {"hidden_dim": 256, "num_layers": 1},
                    "GRU": {"hidden_dim": 256, "num_layers": 1},
                    "LSTM": {"hidden_dim": 256, "num_layers": 1},
                    "Transformer": {"hidden_dim": 256, "nhead": 8, "num_layers": 2},
                },
                "working_dir": "/oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research",
                "research_workspace": "/oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research",
                "normalized_package": "nwdaf_mtlf_model_training",
                "pass_output_dir_args": False,
                "record_outputs": True,
                "scripts": {
                    "centralized": "/oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research/DL_multiclass_centralize.py",
                    "regional": "/oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research/DL_multiclass_regional_models.py",
                    "federated-averaging": "/oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research/DL_multiclass_federated.py",
                    "federated-distillation": "/oai-5g-storage/IDS_RELATED_STORAGE/TRAINING_CODE/IDS_NWDAF_DL_Research/DL_multiclass_Federated_Distillation.py",
                },
            },
            "shared_storage": {
                "root": "/oai-5g-storage",
                "metadata_enabled": True,
            },
            "mongodb": {
                "enabled": False,
                "uri": "mongodb://oai-nwdaf-database:27017",
                "database_name": "testing",
                "storage_metadata_collection": "storage_metadata",
                "timeout_ms": 3000,
            },
            "test_stub_model": {
                "enabled": False,
                "model_id": "stub-latest",
                "job_id": "stub-latest-job",
                "weight_bytes": 4096,
                "notify_existing_on_subscribe": True,
            },
            "callback_uri": "http://oai-nwdaf-mtlf-service:8082",
        }


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    global nrf_client, dccf_client, training_manager, config

    logger.info("MTLF Service Starting (Nnwdaf_MLModelProvision, TS 29.520 Rel-17)...")
    config = load_config()

    nf_instance_id = config.get("mtlf", {}).get("nfInstanceId", "nwdaf-mtlf-001")
    logger.info(f"NF Instance ID: {nf_instance_id}")
    logger.info(
        "MTLF training scenario: %s",
        config.get("training_scenario", {}).get("scenario", config.get("training", {}).get("scenario", "regional")),
    )
    connect_storage_metadata_store()

    # NRF registration (TS 29.510)
    nrf_client = NRFClient(config)
    if nrf_client.auto_register:
        success = await nrf_client.register()
        if success:
            logger.info("MTLF registered with NRF")
        else:
            logger.warning("NRF registration failed — continuing without it")

    # Training manager with model-ready callback
    async def _on_model_ready(job_id: str, model_dir: str):
        model_id = f"model-{job_id}"
        job = training_manager.get_job(job_id)
        metrics = job.metrics if job else {}
        artifact_path = find_job_model_artifact(job, model_dir)
        base_uri = config.get("callback_uri", "http://localhost:8082")
        nf_instance_id = config.get("mtlf", {}).get("nfInstanceId", "nwdaf-mtlf-001")
        scenario_cfg = config.get("training_scenario", {})
        model_architecture = scenario_cfg.get("model_architecture", "Transformer")
        model_parameters = scenario_cfg.get("model_architectures", {}).get(model_architecture, {})
        _model_registry[model_id] = build_model_registry_entry(
            model_id=model_id,
            job_id=job_id,
            model_dir=str(artifact_path.parent if artifact_path else Path(model_dir)),
            metrics=metrics,
            base_uri=base_uri,
            nf_instance_id=nf_instance_id,
            overrides={
                "servingArea": config.get("serving_area", {}),
                "trainingScenario": scenario_cfg.get("scenario"),
                "architecture": model_architecture,
                "modelParameters": model_parameters,
                "artifactType": "pytorch-state-dict",
                "artifactFileName": artifact_path.name if artifact_path else "model.pt",
                "idsCompatible": False,
                "compatibilityNote": (
                    "Research training artifact produced by MTLF. IDS runtime "
                    "loading and checksum validation are tracked in Workstream 2.3."
                ),
            },
        )
        if artifact_path:
            record_shared_file_metadata(
                artifact_path,
                category="model",
                job_id=job_id,
                model_id=model_id,
                training_scenario=config.get("training_scenario", {}).get("scenario"),
                metadata={"metrics": metrics},
            )
        logger.info(f"Model {model_id} registered from job {job_id}")
        sub_mgr = get_subscription_manager()
        await sub_mgr.notify_model_ready(job_id, model_id, metrics)

    training_manager = TrainingManager(
        config,
        on_model_ready=_on_model_ready,
        metadata_store=storage_metadata_store,
    )
    seed_test_stub_model(config, nf_instance_id)

    # DCCF subscription (TS 29.574 Ndccf_DataManagement)
    dccf_cfg = config.get("dccf", {})
    dccf_client = DCCFClient(
        dccf_endpoint=dccf_cfg.get("endpoint", ""),
        notification_uri=dccf_cfg.get("notification_uri", ""),
        nf_instance_id=nf_instance_id,
    )
    dccf_client.set_notification_handler(training_manager.on_dccf_data)

    if dccf_cfg.get("endpoint"):
        success = await dccf_client.subscribe(
            event_types=dccf_cfg.get("event_types", ["NF_LOAD", "UE_MOBILITY"]),
            protocols=dccf_cfg.get("protocols", ["http2", "ngap", "pfcp"]),
            interval_seconds=dccf_cfg.get("notification_interval", 60),
        )
        if success:
            logger.info("Subscribed to DCCF for training data (TS 29.574)")
        else:
            logger.warning("DCCF subscription failed — training data will not be pushed")

    logger.info("MTLF Service Started")


@app.on_event("shutdown")
async def shutdown_event():
    global storage_metadata_store

    if dccf_client:
        await dccf_client.unsubscribe()
    sub_mgr = get_subscription_manager()
    await sub_mgr.close()
    if nrf_client and nrf_client.is_registered:
        await nrf_client.deregister()
    drop_storage_metadata_store()
    logger.info("MTLF Service Stopped")


# ===========================================================================
# Nnwdaf_MLModelProvision — Standardized API (TS 29.520 §6.3.3)
# ===========================================================================

# ---------------------------------------------------------------------------
# Subscriptions resource
# POST   /nnwdaf-mlmodelprovision/v1/subscriptions
# DELETE /nnwdaf-mlmodelprovision/v1/subscriptions/{subscriptionId}
# ---------------------------------------------------------------------------

@app.post("/nnwdaf-mlmodelprovision/v1/subscriptions", status_code=201)
async def create_subscription(request: Request, body: dict):
    """
    Nnwdaf_MLModelProvision_Subscribe (TS 29.520 §6.3.3.3.1)

    Request body: NnwdafMLModelProvisionSubsc
      - notifUri      (required) — callback URI for notifications
      - notifCorreId  (required) — correlation ID echoed back in every notification
      - mLModels      (required) — list of { mLEvent, mLEventFilter, tgtUe, nwdafIds }
      - suppFeat      (optional) — supported features bitmap
      - expiry        (optional) — subscription expiry (DateTime)
    """
    notif_uri = body.get("notifUri")
    if not notif_uri:
        return problem(400, "Bad Request", "notifUri is required",
                       str(request.url))

    notif_corre_id = body.get("notifCorreId")
    if not notif_corre_id:
        return problem(400, "Bad Request", "notifCorreId is required",
                       str(request.url))

    ml_models = body.get("mLModels")
    if not ml_models:
        return problem(400, "Bad Request", "mLModels is required",
                       str(request.url))

    sub_mgr = get_subscription_manager()
    sub = await sub_mgr.create_subscription(
        notif_uri=notif_uri,
        notif_corre_id=notif_corre_id,
        ml_models=ml_models,
        supp_feat=body.get("suppFeat"),
        expiry=body.get("expiry"),
    )
    stub_cfg = config.get("test_stub_model", {})
    if stub_cfg.get("notify_existing_on_subscribe", False) and _model_registry:
        latest = max(
            _model_registry.values(),
            key=lambda entry: entry.get("createdAt", ""),
        )
        await sub_mgr.notify_subscription_model_ready(
            sub=sub,
            job_id=latest.get("jobId", ""),
            model_id=latest.get("modelId", ""),
            metrics=latest.get("metrics", {}),
        )
    location = (
        f"/nnwdaf-mlmodelprovision/v1/subscriptions/{sub.subscription_id}"
    )
    response_body = sub_mgr.to_dict(sub)
    return Response(
        content=__import__("json").dumps(response_body),
        status_code=201,
        headers={"Location": location, "Content-Type": "application/json"},
    )


@app.delete("/nnwdaf-mlmodelprovision/v1/subscriptions/{sub_id}", status_code=204)
async def delete_subscription(sub_id: str, request: Request):
    """Nnwdaf_MLModelProvision_Unsubscribe (TS 29.520 §6.3.3.3.2)"""
    sub_mgr = get_subscription_manager()
    deleted = await sub_mgr.delete_subscription(sub_id)
    if not deleted:
        return problem(404, "Not Found",
                       f"Subscription {sub_id} not found",
                       str(request.url))
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# ML Models resource (model discovery)
# GET /nnwdaf-mlmodelprovision/v1/ml-models
# GET /nnwdaf-mlmodelprovision/v1/ml-models/{modelId}
# GET /nnwdaf-mlmodelprovision/v1/ml-models/{modelId}/manifest
# GET /nnwdaf-mlmodelprovision/v1/ml-models/{modelId}/file   ← download
# ---------------------------------------------------------------------------

@app.get("/nnwdaf-mlmodelprovision/v1/ml-models")
async def list_models():
    """List all available trained ML models."""
    return {"mlModels": list(_model_registry.values())}


@app.get("/nnwdaf-mlmodelprovision/v1/ml-models/{model_id}")
async def get_model(model_id: str, request: Request):
    """
    Get ML model metadata.
    Response includes mLFileAddr.mlModelUrl for consumers to download.
    """
    entry = _model_registry.get(model_id)
    if not entry:
        return problem(404, "Not Found",
                       f"Model {model_id} not found", str(request.url))
    return entry


@app.get("/nnwdaf-mlmodelprovision/v1/ml-models/{model_id}/manifest")
async def get_model_manifest(model_id: str, request: Request):
    """
    Return an IDS-facing model manifest.
    This compatibility endpoint is intentionally explicit about whether the
    current NWDAF model can be consumed directly by oai-ids.
    """
    entry = _model_registry.get(model_id)
    if not entry:
        return problem(404, "Not Found",
                       f"Model {model_id} not found", str(request.url))
    return build_ids_model_manifest(entry)


@app.get("/nnwdaf-mlmodelprovision/v1/ml-models/{model_id}/file")
async def download_model(model_id: str, request: Request):
    """
    Serve the trained model file over HTTP so AnLF can fetch it.
    mLFileAddr.mlModelUrl in notifications points here (TS 29.520 MLModelAddr).
    """
    entry = _model_registry.get(model_id)
    if not entry:
        return problem(404, "Not Found",
                       f"Model {model_id} not found", str(request.url))
    model_path = Path(entry["modelDir"]) / entry.get("artifactFileName", "model.pt")
    if not model_path.exists():
        return problem(404, "Not Found",
                       f"Model file for {model_id} not found on disk",
                       str(request.url))
    return FileResponse(
        path=str(model_path),
        media_type="application/octet-stream",
        filename=f"{model_id}.pt",
    )


@app.delete("/nnwdaf-mlmodelprovision/v1/ml-models/{model_id}", status_code=204)
async def delete_model(model_id: str, request: Request):
    if model_id not in _model_registry:
        return problem(404, "Not Found",
                       f"Model {model_id} not found", str(request.url))
    del _model_registry[model_id]
    return Response(status_code=204)


# ===========================================================================
# Proprietary: Training Job management (not standardized — internal MTLF)
# Per TS 23.288 §6.2A, training job triggering is not exposed as an external
# 3GPP SBI. These routes are under /proprietary/v1/ to make that clear.
# ===========================================================================

@app.post("/proprietary/v1/training-jobs", status_code=201)
async def create_training_job(request: Request, body: dict = None):
    """Trigger a new IDS training job. Proprietary — not part of TS 29.520."""
    if training_manager is None:
        return problem(503, "Service Unavailable",
                       "Training manager not initialised", str(request.url))
    training_manager.set_metadata_store(connect_storage_metadata_store())
    epochs = body.get("epochs") if body else None
    scenario = body.get("scenario") if body else None
    try:
        job = await training_manager.create_job(epochs=epochs, scenario=scenario)
    except ValueError as exc:
        return problem(400, "Bad Request", str(exc), str(request.url))
    location = f"/proprietary/v1/training-jobs/{job.job_id}"
    return Response(
        content=__import__("json").dumps(training_manager.job_to_dict(job)),
        status_code=201,
        headers={"Location": location, "Content-Type": "application/json"},
    )


@app.get("/proprietary/v1/training-jobs")
async def list_training_jobs(request: Request):
    if training_manager is None:
        return problem(503, "Service Unavailable",
                       "Training manager not initialised", str(request.url))
    return {"jobs": [training_manager.job_to_dict(j)
                     for j in training_manager.list_jobs()]}


@app.get("/proprietary/v1/training-jobs/{job_id}")
async def get_training_job(job_id: str, request: Request):
    if training_manager is None:
        return problem(503, "Service Unavailable",
                       "Training manager not initialised", str(request.url))
    job = training_manager.get_job(job_id)
    if not job:
        return problem(404, "Not Found",
                       f"Job {job_id} not found", str(request.url))
    return training_manager.job_to_dict(job)


@app.delete("/proprietary/v1/training-jobs/{job_id}", status_code=204)
async def cancel_training_job(job_id: str, request: Request):
    if training_manager is None:
        return problem(503, "Service Unavailable",
                       "Training manager not initialised", str(request.url))
    cancelled = await training_manager.cancel_job(job_id)
    if not cancelled:
        return problem(404, "Not Found",
                       f"Job {job_id} not found or already done",
                       str(request.url))
    return Response(status_code=204)


@app.get("/proprietary/v1/training-scenario")
async def get_training_scenario():
    scenario_cfg = config.get("training_scenario", {})
    return {
        "scenario": scenario_cfg.get("scenario", config.get("training", {}).get("scenario", "regional")),
        "modelArchitecture": scenario_cfg.get("model_architecture", ""),
        "modelParameters": scenario_cfg.get("model_architectures", {}).get(
            scenario_cfg.get("model_architecture", ""),
            {},
        ),
        "modelArchitectures": scenario_cfg.get("model_architectures", {}),
        "workingDir": scenario_cfg.get("working_dir"),
        "researchWorkspace": scenario_cfg.get(
            "research_workspace",
            config.get("training", {}).get("research_workspace"),
        ),
        "normalizedPackage": scenario_cfg.get(
            "normalized_package",
            config.get("training", {}).get("normalized_package"),
        ),
        "resolvedScriptPath": training_manager.script_path if training_manager else None,
        "scripts": scenario_cfg.get("scripts", {}),
        "sharedStorage": config.get("shared_storage", {}),
        "metadataStoreEnabled": storage_metadata_store is not None,
        "servingArea": config.get("serving_area", {}),
    }


@app.get("/proprietary/v1/storage/files")
async def list_storage_files(
    category: str | None = None,
    training_scenario: str | None = None,
    limit: int = 100,
):
    store = connect_storage_metadata_store()
    if store is None:
        return {
            "files": [],
            "count": 0,
            "storage": "unavailable",
            "detail": "MongoDB shared-storage metadata store is unavailable",
        }
    files = store.list_files(
        category=category,
        region=config.get("serving_area", {}).get("region"),
        training_scenario=training_scenario,
        limit=limit,
    )
    return {
        "files": files,
        "count": len(files),
        "storage": "mongodb",
        "servingArea": config.get("serving_area", {}),
    }


# ===========================================================================
# Internal: DCCF notification receiver (TS 29.574)
# ===========================================================================

@app.post("/mtlf-internal/dccf-notifications")
async def receive_dccf_notification(notification: dict, request: Request):
    """
    DCCF (TS 29.574 Ndccf_DataManagement) pushes analytics data here.
    Not visible to other NFs — internal MTLF callback only.
    """
    if dccf_client is None:
        return problem(503, "Service Unavailable",
                       "DCCF client not initialised", str(request.url))
    await dccf_client.handle_notification(notification)
    return {"status": "ok"}


# ===========================================================================
# Health / NRF management
# ===========================================================================

@app.get("/health")
async def health():
    return {
        "status":               "healthy",
        "service":              "NWDAF-MTLF",
        "nfInstanceId":         config.get("mtlf", {}).get("nfInstanceId", ""),
        "servingArea":          config.get("serving_area", {}),
        "trainingScenario":     config.get("training_scenario", {}).get("scenario", ""),
        "sharedStorage":        config.get("shared_storage", {}),
        "storageMetadata":      "mongodb" if storage_metadata_store else "unavailable",
        "nrfRegistered":        nrf_client.is_registered if nrf_client else False,
        "dccfSubscriptionId":   dccf_client.subscription_id if dccf_client else None,
        "timestamp":            datetime.utcnow().isoformat(),
    }


@app.get("/ready")
async def readiness(request: Request):
    if training_manager is None:
        return problem(503, "Service Unavailable",
                       "Training manager not initialised", str(request.url))
    return {"status": "ready"}


@app.get("/nrf/status")
async def nrf_status():
    return {
        "registered":   nrf_client.is_registered if nrf_client else False,
        "nfInstanceId": config.get("mtlf", {}).get("nfInstanceId", ""),
        "nrfEndpoint":  config.get("nrf", {}).get("endpoint", ""),
    }


@app.post("/nrf/register")
async def trigger_registration(request: Request):
    if nrf_client is None:
        return problem(503, "Service Unavailable",
                       "NRF client not initialised", str(request.url))
    success = await nrf_client.register()
    if success:
        return {"status": "registered"}
    return problem(500, "Internal Server Error",
                   "NRF registration failed", str(request.url))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    runtime_config = load_config()
    port = int(os.getenv("MTLF_PORT", runtime_config.get("server", {}).get("port", 8082)))
    logger.info(f"Starting MTLF on port {port}")
    try:
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=port)
    except ImportError:
        logger.error("uvicorn not installed — run: hypercorn main:app --bind 0.0.0.0:8082")
