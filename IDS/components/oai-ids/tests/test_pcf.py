import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import IdsConfig, TrafficInfluenceConfig
from app.pcf import build_sm_policy_context, ids_traffic_influence_uri, sm_policy_uri


class PcfClientTests(unittest.TestCase):
    def test_builds_oai_sm_policy_context(self):
        config = IdsConfig()
        config.serving_area.mcc = "001"
        config.serving_area.mnc = "01"
        config.traffic_influence = TrafficInfluenceConfig(
            enabled=True,
            mode="sm-policy-probe",
            pcf_base_uri="http://oai-pcf:80/npcf-smpolicycontrol/v1",
            supi="imsi-001010000000001",
            pdu_session_id=1,
            pdu_session_type="IPV4",
            dnn="oai",
            snssai_sst=1,
            snssai_sd="000001",
            notification_uri="http://oai-ids:8080/nids-event-exposure/v1/notifications",
        )

        payload = build_sm_policy_context(config)

        self.assertEqual(payload["supi"], "imsi-001010000000001")
        self.assertEqual(payload["pduSessionId"], 1)
        self.assertEqual(payload["pduSessionType"], "IPV4")
        self.assertEqual(payload["dnn"], "oai")
        self.assertEqual(payload["sliceInfo"], {"sst": 1, "sd": "000001"})
        self.assertEqual(payload["servingNetwork"], {"mcc": "001", "mnc": "01"})
        self.assertEqual(payload["accessType"], "3GPP_ACCESS")
        self.assertEqual(payload["ratType"], "NR")

    def test_sm_policy_uri_appends_resource_once(self):
        self.assertEqual(
            sm_policy_uri("http://oai-pcf:80/npcf-smpolicycontrol/v1"),
            "http://oai-pcf:80/npcf-smpolicycontrol/v1/sm-policies",
        )
        self.assertEqual(
            sm_policy_uri("http://oai-pcf:80/npcf-smpolicycontrol/v1/sm-policies"),
            "http://oai-pcf:80/npcf-smpolicycontrol/v1/sm-policies",
        )

    def test_ids_traffic_influence_uri_appends_resource_once(self):
        self.assertEqual(
            ids_traffic_influence_uri("http://oai-pcf:80/npcf-smpolicycontrol/v1"),
            "http://oai-pcf:80/npcf-smpolicycontrol/v1/ids-traffic-influence",
        )
        self.assertEqual(
            ids_traffic_influence_uri(
                "http://oai-pcf:80/npcf-smpolicycontrol/v1/sm-policies"
            ),
            "http://oai-pcf:80/npcf-smpolicycontrol/v1/ids-traffic-influence",
        )


if __name__ == "__main__":
    unittest.main()
