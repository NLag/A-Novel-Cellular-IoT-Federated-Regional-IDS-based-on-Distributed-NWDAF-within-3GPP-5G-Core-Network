"""Workspace manifest helpers for the research training tree.

The manifest gives later refactors one stable place to discover the legacy
scripts, prepared dataset locations, and result directories without scanning
large artifact files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatasetSplit:
    name: str
    train_path: Path
    eval_path: Path
    has_public_private_train_split: bool = True


@dataclass(frozen=True)
class WorkspaceManifest:
    root: Path
    legacy_library: Path
    training_scripts: tuple[Path, ...]
    dataset_splits: tuple[DatasetSplit, ...]
    dataset_artifact_dirs: tuple[Path, ...]
    result_artifact_dirs: tuple[Path, ...]
    notebook_files: tuple[Path, ...]


def default_workspace_manifest(root: str | Path = ".") -> WorkspaceManifest:
    workspace_root = Path(root)
    datasets_root = workspace_root / "datasets"

    return WorkspaceManifest(
        root=workspace_root,
        legacy_library=workspace_root / "IDS_lib.py",
        training_scripts=(
            workspace_root / "DL_multiclass_centralize.py",
            workspace_root / "DL_multiclass_federated.py",
            workspace_root / "DL_multiclass_Federated_Distillation.py",
            workspace_root / "DL_multiclass_regional_models.py",
        ),
        dataset_splits=(
            DatasetSplit(
                name="active-noslowite-nosqlmap",
                train_path=datasets_root / "federated_datasets_noslowite_nosqlmap" / "train",
                eval_path=datasets_root / "federated_datasets_noslowite_nosqlmap" / "eval",
            ),
            DatasetSplit(
                name="noslowite",
                train_path=datasets_root / "federated_datasets_noslowite" / "train",
                eval_path=datasets_root / "federated_datasets_noslowite" / "eval",
            ),
            DatasetSplit(
                name="simple",
                train_path=datasets_root / "simple_federated_datasets" / "train",
                eval_path=datasets_root / "simple_federated_datasets" / "eval",
            ),
            DatasetSplit(
                name="realistic",
                train_path=datasets_root / "realistic_federated_datasets" / "TA_df",
                eval_path=datasets_root / "realistic_federated_datasets" / "TA_eval_df",
                has_public_private_train_split=False,
            ),
        ),
        dataset_artifact_dirs=(
            workspace_root / "datasets",
            workspace_root / "TA_df",
            workspace_root / "TA_eval_df",
        ),
        result_artifact_dirs=(
            workspace_root / "result*",
            workspace_root / "old_results",
            workspace_root / "result_centralized0809",
        ),
        notebook_files=(
            workspace_root / "train_test_data_federated_simple.ipynb",
            workspace_root / "train_test_data_federated_realistic.ipynb",
            workspace_root / "result_analyse.ipynb",
            workspace_root / "test.ipynb",
        ),
    )

