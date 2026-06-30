import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import IdsConfig, NwdafIntegrationConfig
from app.nwdaf import (
    build_ids_report_record,
    build_ml_model_subscription,
    ml_model_info_uri_from_file_url,
    ml_model_subscription_uri,
    ml_model_subscriptions_uri,
    parse_model_update_notification,
)


class NwdafIntegrationTests(unittest.TestCase):
    def test_builds_ml_model_subscription_payload(self):
        config = IdsConfig()
        config.nwdaf_integration = NwdafIntegrationConfig(
            enabled=True,
            mode="subscribe",
            notification_uri="http://oai-ids:8080/nids-model-management/v1/model-notifications",
            notif_correlation_id="ids-corr-1",
            ml_event="ABNORMAL_BEHAVIOUR",
            supported_features="0",
            expiry="2026-12-31T23:59:59Z",
        )

        payload = build_ml_model_subscription(config)

        self.assertEqual(
            payload["notifUri"],
            "http://oai-ids:8080/nids-model-management/v1/model-notifications",
        )
        self.assertEqual(payload["notifCorreId"], "ids-corr-1")
        self.assertEqual(payload["mLModels"], [{"mLEvent": "ABNORMAL_BEHAVIOUR"}])
        self.assertEqual(payload["suppFeat"], "0")
        self.assertEqual(payload["expiry"], "2026-12-31T23:59:59Z")

    def test_ml_model_subscription_uri_helpers_append_once(self):
        self.assertEqual(
            ml_model_subscriptions_uri(
                "http://oai-nwdaf-mtlf-service:8082/nnwdaf-mlmodelprovision/v1"
            ),
            "http://oai-nwdaf-mtlf-service:8082/nnwdaf-mlmodelprovision/v1/subscriptions",
        )
        self.assertEqual(
            ml_model_subscriptions_uri(
                "http://oai-nwdaf-mtlf-service:8082/nnwdaf-mlmodelprovision/v1/subscriptions"
            ),
            "http://oai-nwdaf-mtlf-service:8082/nnwdaf-mlmodelprovision/v1/subscriptions",
        )
        self.assertEqual(
            ml_model_subscription_uri(
                "http://oai-nwdaf-mtlf-service:8082/nnwdaf-mlmodelprovision/v1",
                "mtsub-1",
            ),
            "http://oai-nwdaf-mtlf-service:8082/nnwdaf-mlmodelprovision/v1/subscriptions/mtsub-1",
        )

    def test_ml_model_info_uri_strips_file_suffix(self):
        self.assertEqual(
            ml_model_info_uri_from_file_url(
                "http://nwdaf/nnwdaf-mlmodelprovision/v1/ml-models/model-1/file"
            ),
            "http://nwdaf/nnwdaf-mlmodelprovision/v1/ml-models/model-1",
        )
        self.assertEqual(
            ml_model_info_uri_from_file_url(
                "http://nwdaf/nnwdaf-mlmodelprovision/v1/ml-models/model-1"
            ),
            "http://nwdaf/nnwdaf-mlmodelprovision/v1/ml-models/model-1",
        )

    def test_parses_mtlf_model_ready_notification(self):
        payload = {
            "notifCorreId": "ids-corr-1",
            "mLModelInfo": [
                {
                    "mLEvent": "ABNORMAL_BEHAVIOUR",
                    "mLFileAddr": {
                        "mlModelUrl": (
                            "http://oai-nwdaf-mtlf-service:8082/"
                            "nnwdaf-mlmodelprovision/v1/ml-models/model-job-abc/file"
                        )
                    },
                    "accuracy": "HIGH",
                    "idsModelManifestUrl": (
                        "http://oai-nwdaf-mtlf-service:8082/"
                        "nnwdaf-mlmodelprovision/v1/ml-models/model-job-abc/manifest"
                    ),
                }
            ],
        }

        update = parse_model_update_notification(payload)

        self.assertEqual(update.correlation_id, "ids-corr-1")
        self.assertEqual(update.event, "ABNORMAL_BEHAVIOUR")
        self.assertEqual(update.model_id, "model-job-abc")
        self.assertEqual(update.accuracy, "HIGH")
        self.assertTrue(update.manifest_url.endswith("/model-job-abc/manifest"))
        self.assertTrue(update.model_url.endswith("/model-job-abc/file"))

    def test_rejects_model_notification_without_model_url(self):
        with self.assertRaises(ValueError):
            parse_model_update_notification({"notifCorreId": "ids-corr-1"})

    def test_builds_ids_report_record_for_dccf(self):
        config = IdsConfig()
        config.instance_id = "ids-region-paris"
        config.serving_area.region = "region-paris"
        report = {
            "reportId": "report-1",
            "timestamp": 123.0,
            "predictedClass": "malicious",
            "score": 0.99,
            "ueIp": "12.1.1.10",
            "teid": 7,
            "packetSize": 256,
            "action": "monitor",
        }

        record = build_ids_report_record(config, report)

        self.assertEqual(record["sourceNf"], "IDS")
        self.assertEqual(record["idsInstanceId"], "ids-region-paris")
        self.assertEqual(record["region"], "region-paris")
        self.assertEqual(record["reportId"], "report-1")
        self.assertEqual(record["predictedClass"], "malicious")
        self.assertEqual(record["report"], report)


if __name__ == "__main__":
    unittest.main()
