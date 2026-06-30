import csv
import hashlib
import json
import tempfile
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.dataset_capture import (
    CAPTURE_LEVEL_MODEL_READY,
    CAPTURE_LEVEL_PACKET_CAPTURE,
    CAPTURE_LEVEL_REPORT_ONLY,
    DatasetCaptureConfig,
    DatasetCaptureWriter,
    MODEL_READY_FIELDNAMES,
    ensure_model_ready_csv_schema,
    predicted_label,
)


class DatasetCaptureWriterTests(unittest.TestCase):
    def test_report_only_capture_omits_packet_bytes_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = DatasetCaptureConfig(
                enabled=True,
                level=CAPTURE_LEVEL_REPORT_ONLY,
                storage_root=tmpdir,
                scenario_id="scenario-metadata",
            )
            writer = DatasetCaptureWriter(
                config,
                ids_instance_id="ids-paris",
                region="region-paris",
                tac="000001",
                model_version="placeholder-v1",
            )
            writer.capture_packet(
                timestamp=123.0,
                peer="10.0.0.1:2152",
                teid=469,
                raw_gtpu_packet=b"raw",
                inner_packet=b"inner",
                ue_ip="12.1.1.101",
                ipv4_metadata=None,
                report={"reportId": "report-1"},
                detector_features={},
            )
            writer.close()

            event = json.loads(
                writer.paths.events_path.read_text(encoding="utf-8").splitlines()[0]
            )
            self.assertNotIn("rawGtpuHex", event)
            self.assertNotIn("packetHex", event)
            self.assertEqual(event["rawGtpuSha256"], hashlib.sha256(b"raw").hexdigest())
            self.assertEqual(
                event["innerPacketSha256"], hashlib.sha256(b"inner").hexdigest()
            )

    def test_model_ready_capture_writes_manifest_jsonl_and_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = DatasetCaptureConfig(
                enabled=True,
                level=CAPTURE_LEVEL_MODEL_READY,
                storage_root=tmpdir,
                relative_path="IDS_RELATED_STORAGE/DATASETS",
                scenario_id="scenario-1",
                traffic_class="attack",
                attack_label="mqtt-publish-flood",
                generator="Attacker_Simulate",
                sequence_size=2,
                split="train",
                numeric_label=2,
            )
            writer = DatasetCaptureWriter(
                config,
                ids_instance_id="ids-paris",
                region="region-paris",
                tac="000001",
                model_version="placeholder-v1",
            )
            record = writer.capture_packet(
                timestamp=123.0,
                peer="10.0.0.1:2152",
                teid=469,
                raw_gtpu_packet=b"gtpu",
                inner_packet=b"\x45\x00packet",
                ue_ip="12.1.1.101",
                ipv4_metadata={
                    "sourceIp": "12.1.1.101",
                    "destinationIp": "192.168.49.1",
                    "protocol": 6,
                    "totalLength": 32,
                },
                report={
                    "reportId": "report-1",
                    "predictedClass": "malicious",
                    "score": 0.99,
                    "detector": {"reason": "test"},
                },
                detector_features={"packet_size": 8},
            )
            writer.close()

            self.assertEqual(record["packetIndex"], 0)
            self.assertTrue(writer.paths.manifest_path.exists())
            self.assertTrue(writer.paths.events_path.exists())
            self.assertTrue(writer.paths.model_ready_path.exists())

            manifest = json.loads(writer.paths.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["scenarioId"], "scenario-1")
            self.assertEqual(manifest["level"], CAPTURE_LEVEL_MODEL_READY)

            event = json.loads(
                writer.paths.events_path.read_text(encoding="utf-8").splitlines()[0]
            )
            self.assertEqual(event["ueIp"], "12.1.1.101")
            self.assertEqual(event["attackLabel"], "mqtt-publish-flood")
            self.assertEqual(event["packetHex"], b"\x45\x00packet".hex())
            self.assertNotIn("rawGtpuHex", event)

            with writer.paths.model_ready_path.open("r", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["packet_hex"], b"\x45\x00packet".hex())
            self.assertEqual(rows[0]["label"], "2")
            self.assertEqual(rows[0]["numeric_label"], "2")
            self.assertEqual(rows[0]["predicted_class"], "malicious")
            self.assertEqual(rows[0]["predicted_label"], "1")
            self.assertEqual(rows[0]["predicted_score"], "0.99")
            self.assertEqual(rows[0]["detector_reason"], "test")

    def test_model_ready_capture_preserves_benign_and_malicious_predictions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = DatasetCaptureConfig(
                enabled=True,
                level=CAPTURE_LEVEL_MODEL_READY,
                storage_root=tmpdir,
                scenario_id="mixed-predictions",
                traffic_class="normal",
                attack_label="benign",
                split="train",
                numeric_label=0,
            )
            writer = DatasetCaptureWriter(
                config,
                ids_instance_id="ids-paris",
                region="region-paris",
                tac="000001",
                model_version="placeholder-v1",
            )
            for predicted_class in ("benign", "malicious"):
                writer.capture_packet(
                    timestamp=123.0,
                    peer="10.0.0.1:2152",
                    teid=469,
                    raw_gtpu_packet=b"gtpu",
                    inner_packet=b"\x45\x00packet-" + predicted_class.encode(),
                    ue_ip="12.1.1.101",
                    ipv4_metadata=None,
                    report={
                        "reportId": f"report-{predicted_class}",
                        "predictedClass": predicted_class,
                        "score": 0.1 if predicted_class == "benign" else 0.9,
                        "detector": {"name": "test-detector", "reason": "unit-test"},
                    },
                    detector_features={},
                )
            writer.close()

            events = [
                json.loads(line)
                for line in writer.paths.events_path.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual([event["predictedClass"] for event in events], ["benign", "malicious"])
            self.assertEqual([event["predictedLabel"] for event in events], [0, 1])

            with writer.paths.model_ready_path.open("r", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 2)
            self.assertEqual([row["numeric_label"] for row in rows], ["0", "0"])
            self.assertEqual([row["predicted_class"] for row in rows], ["benign", "malicious"])
            self.assertEqual([row["predicted_label"] for row in rows], ["0", "1"])

    def test_packet_capture_level_includes_raw_gtpu(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = DatasetCaptureConfig(
                enabled=True,
                level=CAPTURE_LEVEL_PACKET_CAPTURE,
                storage_root=tmpdir,
                scenario_id="scenario-raw",
            )
            writer = DatasetCaptureWriter(
                config,
                ids_instance_id="ids-paris",
                region="region-paris",
                tac="000001",
                model_version="placeholder-v1",
            )
            writer.capture_packet(
                timestamp=123.0,
                peer="10.0.0.1:2152",
                teid=469,
                raw_gtpu_packet=b"raw",
                inner_packet=b"inner",
                ue_ip=None,
                ipv4_metadata=None,
                report={"reportId": "report-1"},
                detector_features={},
            )
            writer.close()

            event = json.loads(
                writer.paths.events_path.read_text(encoding="utf-8").splitlines()[0]
            )
            self.assertEqual(event["rawGtpuHex"], b"raw".hex())
            self.assertEqual(event["packetHex"], b"inner".hex())

    def test_existing_model_ready_csv_schema_is_upgraded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "model_ready.csv"
            path.write_text(
                "scenario_id,packet_hex,numeric_label\n"
                "legacy,4500,0\n",
                encoding="utf-8",
            )

            self.assertTrue(ensure_model_ready_csv_schema(path, MODEL_READY_FIELDNAMES))

            with path.open("r", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["scenario_id"], "legacy")
            self.assertEqual(rows[0]["packet_hex"], "4500")
            self.assertEqual(rows[0]["numeric_label"], "0")
            self.assertEqual(rows[0]["predicted_class"], "")
            self.assertEqual(rows[0]["predicted_label"], "")

    def test_predicted_label_mapping(self):
        self.assertEqual(predicted_label("benign"), 0)
        self.assertEqual(predicted_label("malicious"), 1)
        self.assertEqual(predicted_label("attack"), 1)
        self.assertEqual(predicted_label("unknown-class"), -1)


if __name__ == "__main__":
    unittest.main()
