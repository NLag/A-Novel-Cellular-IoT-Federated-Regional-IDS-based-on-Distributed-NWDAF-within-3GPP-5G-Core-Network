from __future__ import annotations

from dataclasses import dataclass
import struct


GTPU_G_PDU = 0xFF


class GtpuDecapsulationError(ValueError):
    """Raised when a duplicated GTP-U packet cannot be decoded safely."""


@dataclass(frozen=True)
class GtpuPacket:
    teid: int
    payload: bytes
    message_length: int
    has_extension_headers: bool


@dataclass(frozen=True)
class Ipv4Metadata:
    source_ip: str
    destination_ip: str
    protocol: int
    total_length: int


def _format_ipv4_address(raw_address: bytes) -> str:
    return ".".join(str(part) for part in raw_address)


def extract_ipv4_metadata(packet: bytes) -> Ipv4Metadata | None:
    if len(packet) < 20:
        return None

    version = packet[0] >> 4
    if version != 4:
        return None

    ihl = (packet[0] & 0x0F) * 4
    if ihl < 20 or len(packet) < ihl:
        return None

    total_length = struct.unpack("!H", packet[2:4])[0]
    if total_length < ihl:
        return None

    return Ipv4Metadata(
        source_ip=_format_ipv4_address(packet[12:16]),
        destination_ip=_format_ipv4_address(packet[16:20]),
        protocol=packet[9],
        total_length=total_length,
    )


def _parse_extension_headers(packet: bytes, offset: int, next_extension: int, end: int) -> int:
    while next_extension != 0:
        if offset + 2 > end:
            raise GtpuDecapsulationError("truncated extension header")

        ext_length = packet[offset]
        if ext_length == 0:
            raise GtpuDecapsulationError("invalid zero-length extension header")

        total_length = ext_length * 4
        if offset + total_length > end:
            raise GtpuDecapsulationError("extension header exceeds message length")

        next_extension = packet[offset + total_length - 1]
        offset += total_length

    return offset


def decapsulate_gtpu(packet: bytes) -> GtpuPacket:
    if len(packet) < 8:
        raise GtpuDecapsulationError("packet too short for GTP-U header")

    flags, message_type, message_length, teid = struct.unpack("!BBHI", packet[:8])
    version = flags >> 5
    protocol_type = (flags >> 4) & 0x01
    has_extension = bool(flags & 0x04)
    has_sequence = bool(flags & 0x02)
    has_npdu = bool(flags & 0x01)

    if version != 1 or protocol_type != 1:
        raise GtpuDecapsulationError("unsupported GTP-U version or protocol type")
    if message_type != GTPU_G_PDU:
        raise GtpuDecapsulationError("unsupported GTP-U message type")

    end = 8 + message_length
    if end > len(packet):
        raise GtpuDecapsulationError("declared GTP-U payload exceeds packet length")

    offset = 8
    if has_extension or has_sequence or has_npdu:
        if end < offset + 4:
            raise GtpuDecapsulationError("truncated optional GTP-U fields")
        next_extension = packet[offset + 3]
        offset += 4
        offset = _parse_extension_headers(packet, offset, next_extension, end)

    if offset > end:
        raise GtpuDecapsulationError("invalid payload offset")

    return GtpuPacket(
        teid=teid,
        payload=packet[offset:end],
        message_length=message_length,
        has_extension_headers=has_extension,
    )
