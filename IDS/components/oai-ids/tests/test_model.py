import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.model import build_model, classify_packet, vectorize_packet


class PlaceholderModelTests(unittest.TestCase):
    def test_vectorize_packet_has_fixed_length(self):
        vector = vectorize_packet(b"\x01\x02\x03", 8)

        self.assertEqual(len(vector.values), 8)
        self.assertAlmostEqual(vector.values[0], 1.0 / 255.0)
        self.assertEqual(vector.values[-1], 0.0)
        self.assertEqual(vector.original_size, 3)
        self.assertEqual(vector.clipped_size, 3)

    def test_heuristic_model_is_deterministic(self):
        packet_vector = vectorize_packet(bytes(range(16)), 16)
        model_a = build_model(packet_mtu=16, seed=1337, hidden_layers=[8, 4])
        model_b = build_model(packet_mtu=16, seed=1337, hidden_layers=[8, 4])

        result_a = classify_packet(model_a, packet_vector)
        result_b = classify_packet(model_b, packet_vector)

        self.assertEqual(result_a.predicted_index, result_b.predicted_index)
        self.assertEqual(result_a.predicted_class, result_b.predicted_class)
        self.assertAlmostEqual(result_a.score, result_b.score)
        self.assertEqual(result_a.reason, result_b.reason)

    def test_large_packet_crosses_size_threshold(self):
        packet_vector = vectorize_packet(b"\x01" * 64, 128)
        model = build_model(
            packet_mtu=128,
            seed=1337,
            malicious_packet_size_threshold=32,
        )

        result = classify_packet(model, packet_vector)

        self.assertEqual(result.predicted_class, "malicious")
        self.assertEqual(result.reason, "packet-size-threshold")

    def test_force_benign_mode_for_smoke_tests(self):
        packet_vector = vectorize_packet(b"\xff" * 64, 128)
        model = build_model(packet_mtu=128, seed=1337, mode="force-benign")

        result = classify_packet(model, packet_vector)

        self.assertEqual(result.predicted_class, "benign")
        self.assertEqual(result.score, 0.99)


if __name__ == "__main__":
    unittest.main()
