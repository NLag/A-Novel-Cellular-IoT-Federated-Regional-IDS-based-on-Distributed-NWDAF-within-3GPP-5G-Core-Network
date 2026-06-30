import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.gtpu import (
    GTPU_G_PDU,
    GtpuDecapsulationError,
    decapsulate_gtpu,
    extract_ipv4_metadata,
)


class GtpuDecapsulationTests(unittest.TestCase):
    def test_decapsulate_simple_gtpu_packet(self):
        payload = b"\x45\x00\x00\x14"
        packet = struct.pack("!BBHI", 0x30, GTPU_G_PDU, len(payload), 0xABCDEF01) + payload

        decoded = decapsulate_gtpu(packet)

        self.assertEqual(decoded.teid, 0xABCDEF01)
        self.assertEqual(decoded.payload, payload)
        self.assertFalse(decoded.has_extension_headers)

    def test_decapsulate_gtpu_with_extension_header(self):
        payload = b"\x60\x00\x00\x00"
        optional_fields = struct.pack("!HBB", 0, 0, 0x85)
        extension_header = struct.pack("!BBBB", 1, 0x10, 0x09, 0)
        packet = (
            struct.pack("!BBHI", 0x34, GTPU_G_PDU, len(payload) + len(optional_fields) + len(extension_header), 0x1234)
            + optional_fields
            + extension_header
            + payload
        )

        decoded = decapsulate_gtpu(packet)

        self.assertEqual(decoded.teid, 0x1234)
        self.assertEqual(decoded.payload, payload)
        self.assertTrue(decoded.has_extension_headers)

    def test_rejects_truncated_payload(self):
        packet = struct.pack("!BBHI", 0x30, GTPU_G_PDU, 32, 0x1) + b"\x45\x00"

        with self.assertRaises(GtpuDecapsulationError):
            decapsulate_gtpu(packet)

    def test_extract_ipv4_metadata(self):
        payload = (
            b"\x45\x00\x00\x1c"
            b"\x00\x00\x00\x00"
            b"\x40\x01\x00\x00"
            b"\x0c\x01\x01\x64"
            b"\x08\x08\x08\x08"
            b"\x00" * 8
        )

        metadata = extract_ipv4_metadata(payload)

        self.assertIsNotNone(metadata)
        self.assertEqual(metadata.source_ip, "12.1.1.100")
        self.assertEqual(metadata.destination_ip, "8.8.8.8")
        self.assertEqual(metadata.protocol, 1)
        self.assertEqual(metadata.total_length, 28)


if __name__ == "__main__":
    unittest.main()
