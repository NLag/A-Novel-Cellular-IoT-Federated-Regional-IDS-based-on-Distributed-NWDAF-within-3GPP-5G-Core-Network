import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import IdsConfig
from app.model_registry import ModelArtifactError, ModelRegistryClient, load_model_runtime


class ModelRegistryTests(unittest.TestCase):
    def test_loads_default_placeholder_artifact_metadata(self):
        config = IdsConfig()
        config.classifier.packet_mtu = 128
        config.model_registry.model_version = "placeholder-test-v1"
        config.model_registry.source_nf = "NWDAF"
        config.model_registry.source_nf_instance_id = "nwdaf-test"

        runtime = load_model_runtime(config)

        self.assertEqual(runtime.registry_status, "loaded-default-placeholder")
        self.assertEqual(runtime.metadata.model_version, "placeholder-test-v1")
        self.assertEqual(runtime.metadata.architecture, "deterministic-placeholder")
        self.assertEqual(runtime.metadata.artifact_type, "placeholder")
        self.assertEqual(runtime.metadata.packet_size, 128)
        self.assertEqual(runtime.metadata.sequence_size, 1)
        self.assertEqual(runtime.metadata.label_map[0], "benign")
        self.assertEqual(runtime.metadata.source_nf, "NWDAF")
        self.assertEqual(runtime.metadata.source_nf_instance_id, "nwdaf-test")

    def test_loads_local_placeholder_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "model.json"
            artifact_path.write_text(
                json.dumps(
                    {
                        "modelVersion": "region-1-v2",
                        "architecture": "deterministic-placeholder",
                        "artifactType": "placeholder",
                        "labelMap": {"0": "benign", "1": "malicious"},
                        "packetSize": 256,
                        "sequenceSize": 4,
                        "source": {
                            "nf": "NWDAF",
                            "nfInstanceId": "nwdaf-region-1",
                            "uri": "http://nwdaf/models/region-1-v2",
                        },
                        "runtime": {
                            "mode": "force-benign",
                            "seed": 1,
                        },
                    }
                ),
                encoding="utf-8",
            )

            config = IdsConfig()
            config.model_registry.artifact_path = str(artifact_path)

            runtime = ModelRegistryClient(config).load()

        self.assertEqual(runtime.registry_status, "loaded-local-artifact")
        self.assertEqual(runtime.metadata.model_version, "region-1-v2")
        self.assertEqual(runtime.metadata.packet_size, 256)
        self.assertEqual(runtime.metadata.sequence_size, 4)
        self.assertEqual(runtime.metadata.source_nf_instance_id, "nwdaf-region-1")
        self.assertEqual(runtime.detector.mode, "force-benign")

    def test_rejects_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "model.json"
            artifact_path.write_text("{}", encoding="utf-8")

            config = IdsConfig()
            config.model_registry.artifact_path = str(artifact_path)
            config.model_registry.checksum = "sha256:not-the-real-checksum"

            with self.assertRaises(ModelArtifactError):
                ModelRegistryClient(config).load()

    def test_rejects_non_placeholder_artifact_for_now(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "model.json"
            payload = {
                "modelVersion": "torch-v1",
                "architecture": "Transformer",
                "artifactType": "pytorch-state-dict",
            }
            artifact_path.write_text(json.dumps(payload), encoding="utf-8")
            checksum = "sha256:" + hashlib.sha256(
                artifact_path.read_bytes()
            ).hexdigest()

            config = IdsConfig()
            config.model_registry.artifact_path = str(artifact_path)
            config.model_registry.checksum = checksum

            with self.assertRaises(ModelArtifactError):
                ModelRegistryClient(config).load()


if __name__ == "__main__":
    unittest.main()
