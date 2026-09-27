import unittest
from pathlib import Path

from nwdaf_mtlf_model_training import (
    CLASS_NAMES,
    DEFAULT_NUM_CLASSES,
    DEFAULT_NUM_REGIONS,
    DEFAULT_PACKET_LEN,
    DEFAULT_SEQUENCE_LEN,
    default_workspace_manifest,
    get_scenario,
    scenario_definitions,
    scenario_keys,
)


class ManifestTests(unittest.TestCase):
    def test_constants_match_current_multiclass_experiment_shape(self):
        self.assertEqual(DEFAULT_NUM_CLASSES, 6)
        self.assertEqual(len(CLASS_NAMES), DEFAULT_NUM_CLASSES)
        self.assertEqual(DEFAULT_NUM_REGIONS, 5)
        self.assertEqual(DEFAULT_SEQUENCE_LEN, 256)
        self.assertEqual(DEFAULT_PACKET_LEN, 1500)

    def test_manifest_points_to_active_dataset_split_without_scanning_files(self):
        manifest = default_workspace_manifest(Path("/workspace"))

        self.assertEqual(manifest.legacy_library, Path("/workspace/IDS_lib.py"))
        self.assertIn(
            Path("/workspace/DL_multiclass_federated.py"),
            manifest.training_scripts,
        )

        active = manifest.dataset_splits[0]
        self.assertEqual(active.name, "active-noslowite-nosqlmap")
        self.assertEqual(
            active.train_path,
            Path("/workspace/datasets/federated_datasets_noslowite_nosqlmap/train"),
        )
        self.assertEqual(
            active.eval_path,
            Path("/workspace/datasets/federated_datasets_noslowite_nosqlmap/eval"),
        )


class ScenarioTests(unittest.TestCase):
    def test_scenario_registry_has_the_four_supported_workflows(self):
        self.assertEqual(
            scenario_keys(),
            (
                "centralized",
                "federated-averaging",
                "federated-distillation",
                "regional",
            ),
        )

    def test_scenario_definitions_point_to_legacy_scripts_without_importing_them(self):
        scenarios = {item.key: item for item in scenario_definitions(Path("/workspace"))}

        self.assertEqual(
            scenarios["centralized"].legacy_script,
            Path("/workspace/DL_multiclass_centralize.py"),
        )
        self.assertEqual(
            scenarios["federated-averaging"].training_strategy,
            "fedavg",
        )
        self.assertTrue(scenarios["federated-distillation"].uses_public_dataset)
        self.assertEqual(scenarios["regional"].dataset_split_name, "simple")

    def test_legacy_command_is_rendered_but_not_executed(self):
        scenario = get_scenario("federated-distillation", root=Path("/workspace"))

        self.assertEqual(
            scenario.legacy_command(),
            ("python", "/workspace/DL_multiclass_Federated_Distillation.py"),
        )


if __name__ == "__main__":
    unittest.main()
