"""Training scenario registry.

The legacy research scripts currently represent four main workflows. This
registry gives those workflows stable names and metadata without importing the
scripts themselves, because importing them can load large datasets immediately.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScenarioDefinition:
    key: str
    title: str
    training_strategy: str
    legacy_script: Path
    dataset_split_name: str
    model_scope: str
    uses_public_dataset: bool
    package_targets: tuple[str, ...]
    description: str

    def legacy_command(self) -> tuple[str, str]:
        return ("python", str(self.legacy_script))


def scenario_definitions(root: str | Path = ".") -> tuple[ScenarioDefinition, ...]:
    workspace_root = Path(root)

    return (
        ScenarioDefinition(
            key="centralized",
            title="Centralized model training",
            training_strategy="centralized",
            legacy_script=workspace_root / "DL_multiclass_centralize.py",
            dataset_split_name="active-noslowite-nosqlmap",
            model_scope="one global model per architecture",
            uses_public_dataset=True,
            package_targets=("data", "models", "training", "evaluation"),
            description=(
                "Train each architecture on a combined centralized dataset, then "
                "evaluate and save model checkpoints and confusion matrices."
            ),
        ),
        ScenarioDefinition(
            key="federated-averaging",
            title="Averaging federated learning",
            training_strategy="fedavg",
            legacy_script=workspace_root / "DL_multiclass_federated.py",
            dataset_split_name="active-noslowite-nosqlmap",
            model_scope="one regional model per region plus averaged global model",
            uses_public_dataset=False,
            package_targets=("data", "models", "training", "federated", "evaluation"),
            description=(
                "Train regional models on private regional data and average model "
                "weights each communication round."
            ),
        ),
        ScenarioDefinition(
            key="federated-distillation",
            title="Federated distillation",
            training_strategy="feddistill",
            legacy_script=workspace_root / "DL_multiclass_Federated_Distillation.py",
            dataset_split_name="active-noslowite-nosqlmap",
            model_scope="one regional model per region with public-data distillation",
            uses_public_dataset=True,
            package_targets=("data", "models", "training", "federated", "evaluation"),
            description=(
                "Use a public/shared dataset to exchange soft labels between "
                "regional models, then continue private regional training."
            ),
        ),
        ScenarioDefinition(
            key="regional",
            title="Separate regional model training",
            training_strategy="regional",
            legacy_script=workspace_root / "DL_multiclass_regional_models.py",
            dataset_split_name="simple",
            model_scope="independent model per region",
            uses_public_dataset=False,
            package_targets=("data", "models", "training", "evaluation"),
            description=(
                "Train and evaluate independent regional models without global "
                "weight averaging or distillation."
            ),
        ),
    )


def scenario_keys() -> tuple[str, ...]:
    return tuple(scenario.key for scenario in scenario_definitions())


def get_scenario(key: str, root: str | Path = ".") -> ScenarioDefinition:
    for scenario in scenario_definitions(root):
        if scenario.key == key:
            return scenario
    valid_keys = ", ".join(scenario_keys())
    raise KeyError(f"unknown scenario {key!r}; valid scenarios: {valid_keys}")

