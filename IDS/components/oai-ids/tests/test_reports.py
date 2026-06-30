import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import IdsConfig
from app.main import build_detection_report


class DetectionReportTests(unittest.TestCase):
    def test_detection_report_includes_5g_and_detector_metadata(self):
        config = IdsConfig()
        config.instance_id = "ids-test"
        config.serving_area.region = "paris"
        config.serving_area.mcc = "001"
        config.serving_area.mnc = "01"
        config.serving_area.tac = "000001"

        report = build_detection_report(
            config=config,
            teid=0x1D5,
            packet_size=88,
            predicted_class="benign",
            score=0.92,
            source="gtpu",
            ue_ip="12.1.1.100",
            detector={"name": "deterministic-placeholder", "reason": "test"},
            model_artifact={
                "modelVersion": "placeholder-v1",
                "architecture": "deterministic-placeholder",
            },
            metadata={"ipv4": {"destinationIp": "8.8.8.8"}},
        )

        self.assertEqual(report["idsInstanceId"], "ids-test")
        self.assertEqual(report["region"], "paris")
        self.assertEqual(report["mcc"], "001")
        self.assertEqual(report["mnc"], "01")
        self.assertEqual(report["tac"], "000001")
        self.assertEqual(report["teid"], 0x1D5)
        self.assertEqual(report["ueIp"], "12.1.1.100")
        self.assertEqual(report["predictedClass"], "benign")
        self.assertEqual(report["action"], "none")
        self.assertEqual(report["countermeasures"], [])
        self.assertEqual(report["detector"]["name"], "deterministic-placeholder")
        self.assertEqual(report["modelArtifact"]["modelVersion"], "placeholder-v1")
        self.assertEqual(report["metadata"]["ipv4"]["destinationIp"], "8.8.8.8")

    def test_malicious_report_plans_observe_only_countermeasures(self):
        config = IdsConfig()
        config.countermeasures.mode = "observe-only"

        report = build_detection_report(
            config=config,
            teid=0x1D5,
            packet_size=512,
            predicted_class="malicious",
            score=0.99,
            source="gtpu",
            ue_ip="12.1.1.100",
        )

        self.assertEqual(report["action"], "observe-only-countermeasure-planned")
        self.assertEqual(len(report["countermeasures"]), 4)
        self.assertEqual(report["countermeasures"][0]["name"], "smf-pdu-session-release")
        self.assertEqual(report["countermeasures"][0]["status"], "observe-only")
        self.assertFalse(report["countermeasures"][0]["called"])
        self.assertEqual(report["countermeasures"][0]["context"]["ueIp"], "12.1.1.100")
        self.assertEqual(report["countermeasures"][0]["context"]["teid"], 0x1D5)

    def test_active_countermeasure_requires_global_and_per_action_gates(self):
        config = IdsConfig()
        config.countermeasures.mode = "active"
        config.countermeasures.active_enabled = True
        config.countermeasures.smf_pdu_session_release_enabled = True

        report = build_detection_report(
            config=config,
            teid=0x1D5,
            packet_size=512,
            predicted_class="malicious",
            score=0.99,
            source="gtpu",
            ue_ip="12.1.1.100",
        )

        statuses = {item["name"]: item["status"] for item in report["countermeasures"]}
        self.assertEqual(statuses["smf-pdu-session-release"], "stub-active-not-called")
        self.assertEqual(statuses["amf-ue-context-release"], "blocked-by-config")
        self.assertEqual(report["action"], "countermeasure-stub-not-called")


if __name__ == "__main__":
    unittest.main()
