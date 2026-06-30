#!/usr/bin/env python3
"""
Training Manager for MTLF
Manages background IDS packet-classification training jobs as subprocesses.

Job lifecycle: PENDING → RUNNING → COMPLETED | FAILED

Per 3GPP TS 29.520, the MTLF is responsible for:
  - Receiving training requests (training job creation)
  - Running the ML training pipeline
  - Notifying subscribed AnLF instances when a model is ready
"""
import asyncio
import importlib
import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# Training job states (mirrors 3GPP TS 29.520 TrainingStatus)
STATUS_PENDING   = "PENDING"
STATUS_RUNNING   = "RUNNING"
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED    = "FAILED"
STATUS_CANCELLED = "CANCELLED"


@dataclass
class TrainingJob:
    job_id: str
    epochs: int
    scenario: str
    status: str = STATUS_PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    output_dir: Optional[str] = None
    error: Optional[str] = None
    metrics: Dict = field(default_factory=dict)
    model_id: Optional[str] = None                # set after COMPLETED
    recorded_files: list[dict[str, Any]] = field(default_factory=list)


class TrainingManager:
    """
    Manages IDS packet-classification training jobs for the MTLF.

    Calls the configured training script as a subprocess so the legacy research
    code is isolated from the MTLF process. IDS research scripts are expected to
    run from a shared-storage workspace because they currently write outputs
    relative to their working directory.
    """

    def __init__(
        self,
        config: dict,
        on_model_ready: Optional[Callable] = None,
        metadata_store: Optional[Any] = None,
    ):
        training_cfg = config.get("training", {})
        scenario_cfg = config.get("training_scenario", {})
        self.scenario = scenario_cfg.get("scenario", training_cfg.get("scenario", "regional"))
        self.models_dir = Path(training_cfg.get("models_dir", "/models"))
        self.default_epochs = training_cfg.get("default_epochs", 100)
        self.python_bin = training_cfg.get("python_bin", sys.executable)
        self.shared_storage_root = Path(
            config.get("shared_storage", {}).get("root", "/oai-5g-storage")
        )
        default_research_workspace = (
            self.shared_storage_root
            / "IDS_RELATED_STORAGE"
            / "TRAINING_CODE"
            / "IDS_NWDAF_DL_Research"
        )
        self.working_dir = Path(
            scenario_cfg.get(
                "working_dir",
                training_cfg.get("working_dir", str(default_research_workspace)),
            )
        )
        self.research_workspace = Path(
            scenario_cfg.get(
                "research_workspace",
                training_cfg.get("research_workspace", str(self.working_dir)),
            )
        )
        self.normalized_package = scenario_cfg.get(
            "normalized_package",
            training_cfg.get("normalized_package", "nwdaf_mtlf_model_training"),
        )
        self.scenario_scripts = scenario_cfg.get("scripts", {})
        self.scenario_definition = self._load_scenario_definition()
        self.script_path = str(self._select_script_path(training_cfg))
        self.model_architecture = scenario_cfg.get("model_architecture")
        self.pass_output_dir_args = bool(
            scenario_cfg.get("pass_output_dir_args", training_cfg.get("pass_output_dir_args", True))
        )
        self.record_outputs = bool(scenario_cfg.get("record_outputs", True))
        self.max_recorded_files = int(scenario_cfg.get("max_recorded_files", 1000))
        self.exclude_dirs = set(
            scenario_cfg.get(
                "metadata_exclude_dirs",
                ["datasets", ".git", "__pycache__", ".venv"],
            )
        )
        self.region = config.get("serving_area", {}).get("region")
        self.tac = config.get("serving_area", {}).get("tac")

        self._jobs: Dict[str, TrainingJob] = {}
        self._tasks: Dict[str, asyncio.Task] = {}
        self._on_model_ready = on_model_ready  # callback(job_id, model_dir)
        self._metadata_store = metadata_store

        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.working_dir.mkdir(parents=True, exist_ok=True)
        if not Path(self.script_path).is_file():
            logger.warning(
                "Training script not found at %s; training jobs will fail until the "
                "training workspace is mounted or training.script_path is updated",
                self.script_path,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_job(
        self,
        epochs: Optional[int] = None,
        scenario: Optional[str] = None,
    ) -> TrainingJob:
        """
        Create and enqueue a new training job.
        Returns the job immediately; training runs in the background.
        """
        requested_scenario = scenario or self.scenario
        if requested_scenario != self.scenario:
            raise ValueError(
                f"MTLF is booted for scenario {self.scenario!r}; "
                f"request for {requested_scenario!r} is not allowed"
            )
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        job = TrainingJob(
            job_id=job_id,
            epochs=epochs or self.default_epochs,
            scenario=self.scenario,
            output_dir=str(self.models_dir / job_id),
        )
        self._jobs[job_id] = job
        logger.info(f"Training job created: {job_id} (epochs={job.epochs})")

        task = asyncio.create_task(self._run_job(job_id))
        self._tasks[job_id] = task
        return job

    def get_job(self, job_id: str) -> Optional[TrainingJob]:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[TrainingJob]:
        return list(self._jobs.values())

    def set_metadata_store(self, metadata_store: Optional[Any]):
        self._metadata_store = metadata_store

    async def cancel_job(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            job = self._jobs.get(job_id)
            if job:
                job.status = STATUS_CANCELLED
            return True
        return False

    def job_to_dict(self, job: TrainingJob) -> dict:
        return {
            "jobId":       job.job_id,
            "status":      job.status,
            "scenario":    job.scenario,
            "epochs":      job.epochs,
            "outputDir":   job.output_dir,
            "modelId":     job.model_id,
            "metrics":     job.metrics,
            "recordedFiles": job.recorded_files,
            "error":       job.error,
            "createdAt":   job.created_at.isoformat(),
            "startedAt":   job.started_at.isoformat() if job.started_at else None,
            "completedAt": job.completed_at.isoformat() if job.completed_at else None,
        }

    # ------------------------------------------------------------------
    # DCCF data handler (called when DCCF pushes a notification)
    # ------------------------------------------------------------------

    async def on_dccf_data(self, notification: dict):
        """
        Receives DCCF analytics notifications.
        Currently logs the receipt; extend here to buffer data and trigger
        auto-retraining when enough new data has accumulated.
        """
        sub_id = notification.get("subscriptionId", "?")
        ts     = notification.get("timestamp", "?")
        logger.info(f"DCCF data received (sub={sub_id}, ts={ts}) — buffered for training")

    # ------------------------------------------------------------------
    # Internal training loop
    # ------------------------------------------------------------------

    async def _run_job(self, job_id: str):
        job = self._jobs[job_id]
        output_dir = job.output_dir
        os.makedirs(output_dir, exist_ok=True)

        job.status = STATUS_RUNNING
        job.started_at = datetime.utcnow()
        logger.info(f"Starting training job {job_id} → {output_dir}")

        if not Path(self.script_path).is_file():
            job.status = STATUS_FAILED
            job.completed_at = datetime.utcnow()
            job.error = (
                f"Training script not found: {self.script_path}. "
                "Mount the training workspace or update training.script_path."
            )
            logger.error(f"Training job {job_id} FAILED ({job.error})")
            return

        cmd = [self.python_bin, "-Bu", self.script_path]
        if self.pass_output_dir_args:
            cmd.extend([
                "--output-dir", output_dir,
                "--epochs", str(job.epochs),
            ])

        log_path = os.path.join(output_dir, "train.log")
        try:
            with open(log_path, "w") as log_fh:
                env = os.environ.copy()
                env.update({
                    "NWDAF_MTLF_SCENARIO": self.scenario,
                    "NWDAF_MTLF_MODEL_ARCHITECTURE": self.model_architecture or "",
                    "NWDAF_MTLF_RESEARCH_WORKSPACE": str(self.research_workspace),
                    "NWDAF_MTLF_NORMALIZED_PACKAGE": self.normalized_package,
                })
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=log_fh,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=str(self.working_dir),
                    env=env,
                )
                await proc.wait()

            if proc.returncode == 0:
                job.status = STATUS_COMPLETED
                job.completed_at = datetime.utcnow()
                job.model_id = f"model-{job_id}"
                job.metrics  = self._load_metrics(output_dir)
                job.recorded_files = self._record_job_outputs(job)
                logger.info(
                    f"Training job {job_id} COMPLETED "
                    f"(elapsed {(job.completed_at - job.started_at).total_seconds():.1f}s)"
                )
                if self._on_model_ready:
                    await self._on_model_ready(job_id, output_dir)
            else:
                job.status = STATUS_FAILED
                job.completed_at = datetime.utcnow()
                job.error = f"Process exited with code {proc.returncode}. See {log_path}"
                logger.error(f"Training job {job_id} FAILED (rc={proc.returncode})")

        except asyncio.CancelledError:
            job.status = STATUS_CANCELLED
            job.completed_at = datetime.utcnow()
            logger.info(f"Training job {job_id} cancelled")
        except Exception as e:
            job.status = STATUS_FAILED
            job.completed_at = datetime.utcnow()
            job.error = str(e)
            logger.error(f"Training job {job_id} error: {e}")

    def _load_scenario_definition(self) -> Optional[Any]:
        """
        Load scenario metadata from the normalized IDS/NWDAF training package.

        The package is expected to be import-safe: it must expose scenario
        metadata without importing the legacy training scripts or loading large
        datasets. MTLF can still run with configured legacy script paths if the
        package is unavailable during early development.
        """
        try:
            scenarios_module = importlib.import_module(f"{self.normalized_package}.scenarios")
            scenario_definition = scenarios_module.get_scenario(
                self.scenario,
                root=self.research_workspace,
            )
            logger.info(
                "Loaded normalized training scenario %s from package %s",
                self.scenario,
                self.normalized_package,
            )
            return scenario_definition
        except Exception as exc:
            logger.warning(
                "Could not load normalized training scenario %s from package %s: %s",
                self.scenario,
                self.normalized_package,
                exc,
            )
            return None

    def _select_script_path(self, training_cfg: dict) -> Path:
        scenario_script = self.scenario_scripts.get(self.scenario)
        if scenario_script:
            return Path(scenario_script)

        configured_script = training_cfg.get("script_path")
        if configured_script:
            return Path(configured_script)

        if self.scenario_definition is not None:
            return Path(self.scenario_definition.legacy_script)

        return self.research_workspace / "DL_multiclass_regional_models.py"

    def _load_metrics(self, output_dir: str) -> dict:
        """
        Parse known metrics files when a training script writes one.
        """
        csv_path = os.path.join(output_dir, "training_metrics.csv")
        if not os.path.isfile(csv_path):
            return {}
        try:
            import csv
            rows = []
            with open(csv_path) as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    rows.append(row)
            # Average RMSE / MAE across datasets
            rmses = [float(r["all_rmse"]) for r in rows if "all_rmse" in r]
            maes  = [float(r["all_mae"])  for r in rows if "all_mae"  in r]
            return {
                "datasets": len(rows),
                "avg_rmse": round(sum(rmses) / len(rmses), 6) if rmses else None,
                "avg_mae":  round(sum(maes)  / len(maes),  6) if maes  else None,
            }
        except Exception as e:
            logger.warning(f"Could not parse metrics from {csv_path}: {e}")
            return {}

    def _record_job_outputs(self, job: TrainingJob) -> list[dict[str, Any]]:
        if not self.record_outputs or self._metadata_store is None:
            return []

        output_paths = [Path(job.output_dir) / "train.log"]
        started_ts = job.started_at.timestamp() if job.started_at else 0
        for path in self.working_dir.rglob("*"):
            if not path.is_file():
                continue
            if any(part in self.exclude_dirs for part in path.parts):
                continue
            try:
                if path.stat().st_mtime >= started_ts:
                    output_paths.append(path)
            except OSError:
                continue
            if len(output_paths) >= self.max_recorded_files:
                break

        return self._metadata_store.record_files(
            output_paths,
            category="training-output",
            producer_nf="MTLF",
            region=self.region,
            tac=self.tac,
            job_id=job.job_id,
            model_id=job.model_id,
            training_scenario=job.scenario,
            metadata={
                "outputDir": job.output_dir,
                "workingDir": str(self.working_dir),
            },
        )
