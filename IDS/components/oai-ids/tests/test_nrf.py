import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.nrf import NrfRegistration


class NrfRegistrationTests(unittest.TestCase):
    def test_payload_contains_ids_service_and_serving_metadata(self):
        registration = NrfRegistration(
            base_uri="http://oai-nrf:80/nnrf-nfm/v1",
            nf_instance_id="ids-region-paris",
            nf_type="AF",
            nf_status="REGISTERED",
            service_name="oai-ids-monitoring",
            service_version="v1",
            heart_beat_timer=30,
            host="oai-ids",
            pod_ip="10.244.0.10",
            http_port=8080,
            serving_region="region-paris",
            serving_tac="000001",
        )

        payload = registration.payload()

        self.assertEqual(payload["nfType"], "AF")
        self.assertEqual(payload["customInfo"]["idsServingRegion"], "region-paris")
        self.assertEqual(payload["customInfo"]["idsServingTac"], "000001")
        self.assertEqual(payload["nfServices"][0]["serviceName"], "oai-ids-monitoring")
        self.assertEqual(payload["nfServices"][0]["ipEndPoints"][0]["port"], 8080)


if __name__ == "__main__":
    unittest.main()
