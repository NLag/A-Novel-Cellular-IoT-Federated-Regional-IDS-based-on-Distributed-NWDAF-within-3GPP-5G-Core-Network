import tempfile
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import load_config


class ConfigTests(unittest.TestCase):
    def test_loads_ids_runtime_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "ids.yaml"
            config_path.write_text(
                """
ids:
  host: oai-ids
  instanceId: ids-region-paris
  servingArea:
    region: region-paris
    mcc: "001"
    mnc: "01"
    tac: "000001"
  reports:
    storage: file
    file_path: /tmp/oai-ids/reports.jsonl
  datasetCapture:
    enabled: true
    level: model-ready
    storage_root: /oai-5g-storage
    relative_path: IDS_RELATED_STORAGE/DATASETS
    scenario_id: smoke-benign-paris
    traffic_class: normal
    attack_label: benign
    attack_variant: none
    generator: IoT_Simulate
    generator_metadata:
      min_devices: 2
    include_raw_gtpu: false
    include_inner_packet: true
    sequence_size: 200
    split: train
    numeric_label: 0
  classifier:
    mode: force-benign
    malicious_packet_size_threshold: 64
    high_byte_ratio_threshold: 0.5
  modelRegistry:
    enabled: true
    mode: placeholder
    model_version: region-paris-placeholder-v1
    architecture: deterministic-placeholder
    artifact_type: placeholder
    source_nf: NWDAF
    source_nf_instance_id: nwdaf-region-paris
    sequence_size: 1
    label_map:
      0: benign
      1: malicious
  countermeasures:
    mode: observe-only
    active_enabled: false
    smf_pdu_session_release_enabled: true
    smf_base_uri: http://oai-smf:80
  trafficInfluence:
    enabled: true
    mode: sm-policy-probe
    pcf_base_uri: http://oai-pcf:80/npcf-smpolicycontrol/v1
    supi: imsi-001010000000001
    dnn: oai
    snssai_sst: 1
    duplication_policy_id: ids-duplication
  nwdafIntegration:
    enabled: true
    mode: subscribe
    base_uri: http://oai-nwdaf-mtlf-service:8082/nnwdaf-mlmodelprovision/v1
    notification_uri: http://oai-ids:8080/nids-model-management/v1/model-notifications
    fetch_model_metadata: true
    report_forwarding_enabled: true
    report_forwarding_uri: http://oai-nwdaf-dccf:8081/ndccf-datamanagement/v1/ids-reports
    notif_correlation_id: ids-paris-model-updates
    ml_event: ABNORMAL_BEHAVIOUR
""",
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.instance_id, "ids-region-paris")
        self.assertEqual(config.serving_area.region, "region-paris")
        self.assertEqual(config.serving_area.tac, "000001")
        self.assertEqual(config.reports.storage, "file")
        self.assertTrue(config.dataset_capture.enabled)
        self.assertEqual(config.dataset_capture.level, "model-ready")
        self.assertEqual(config.dataset_capture.storage_root, "/oai-5g-storage")
        self.assertEqual(
            config.dataset_capture.relative_path, "IDS_RELATED_STORAGE/DATASETS"
        )
        self.assertEqual(config.dataset_capture.scenario_id, "smoke-benign-paris")
        self.assertEqual(config.dataset_capture.traffic_class, "normal")
        self.assertEqual(config.dataset_capture.attack_label, "benign")
        self.assertEqual(config.dataset_capture.attack_variant, "none")
        self.assertEqual(config.dataset_capture.generator, "IoT_Simulate")
        self.assertEqual(config.dataset_capture.generator_metadata["min_devices"], 2)
        self.assertFalse(config.dataset_capture.include_raw_gtpu)
        self.assertTrue(config.dataset_capture.include_inner_packet)
        self.assertEqual(config.dataset_capture.sequence_size, 200)
        self.assertEqual(config.dataset_capture.split, "train")
        self.assertEqual(config.dataset_capture.numeric_label, 0)
        self.assertEqual(config.classifier.mode, "force-benign")
        self.assertEqual(config.classifier.malicious_packet_size_threshold, 64)
        self.assertEqual(config.classifier.high_byte_ratio_threshold, 0.5)
        self.assertTrue(config.model_registry.enabled)
        self.assertEqual(
            config.model_registry.model_version, "region-paris-placeholder-v1"
        )
        self.assertEqual(config.model_registry.source_nf, "NWDAF")
        self.assertEqual(config.model_registry.source_nf_instance_id, "nwdaf-region-paris")
        self.assertEqual(config.model_registry.sequence_size, 1)
        self.assertEqual(config.model_registry.label_map[0], "benign")
        self.assertEqual(config.countermeasures.mode, "observe-only")
        self.assertFalse(config.countermeasures.active_enabled)
        self.assertTrue(config.countermeasures.smf_pdu_session_release_enabled)
        self.assertEqual(config.countermeasures.smf_base_uri, "http://oai-smf:80")
        self.assertTrue(config.traffic_influence.enabled)
        self.assertEqual(config.traffic_influence.mode, "sm-policy-probe")
        self.assertEqual(config.traffic_influence.dnn, "oai")
        self.assertTrue(config.nwdaf_integration.enabled)
        self.assertEqual(config.nwdaf_integration.mode, "subscribe")
        self.assertEqual(
            config.nwdaf_integration.base_uri,
            "http://oai-nwdaf-mtlf-service:8082/nnwdaf-mlmodelprovision/v1",
        )
        self.assertEqual(
            config.nwdaf_integration.notification_uri,
            "http://oai-ids:8080/nids-model-management/v1/model-notifications",
        )
        self.assertTrue(config.nwdaf_integration.fetch_model_metadata)
        self.assertTrue(config.nwdaf_integration.report_forwarding_enabled)
        self.assertEqual(
            config.nwdaf_integration.report_forwarding_uri,
            "http://oai-nwdaf-dccf:8081/ndccf-datamanagement/v1/ids-reports",
        )
        self.assertEqual(
            config.nwdaf_integration.notif_correlation_id,
            "ids-paris-model-updates",
        )
        self.assertEqual(config.nwdaf_integration.ml_event, "ABNORMAL_BEHAVIOUR")


if __name__ == "__main__":
    unittest.main()
