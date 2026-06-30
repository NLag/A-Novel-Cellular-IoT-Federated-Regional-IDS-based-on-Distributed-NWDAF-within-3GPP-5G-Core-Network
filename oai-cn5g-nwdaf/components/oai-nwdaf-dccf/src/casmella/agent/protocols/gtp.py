"""GTP-U parsing module.
"""
# standard
import socket
# internal
from .qos import get_qfi_info
from core import cfg, metrics, database
from core.custom_types import ThreadSafeTtlDict


# Global variables
MY_NODE_NAME = cfg.MY_NODE_NAME
gtpu_forwarding_time = ThreadSafeTtlDict()
operation_time_buffer_write_item = cfg.operation_time_buffer_write_item
operation_time_buffer_read_item = cfg.operation_time_buffer_read_item
retrive_server_and_client_from_ips = cfg.retrive_server_and_client_from_ips
retrive_src_and_dst_from_ips = cfg.retrive_src_and_dst_from_ips
log_dict_info = cfg.log_dict_info
logger = cfg.logging

# Set logging configuration
for i in logger.Logger.manager.loggerDict:
    logger.getLogger(i).setLevel(cfg.logging.ERROR)

# GTP header first byte content
GTPU_VERSION = int('0b11100000', 2)
GTPU_PT = int('0b00010000', 2)
GTPU_E = int('0b00000100', 2)    # indicates the presence of Next Extension Header filed
GTPU_S = int('0b00000010', 2)    # indicates the presence of Sequence Number field
GTPU_PN = int('0b00000001', 2)   # indicates the presence of N-PDU Number flag

# GTP-U extension header content (TS 38.415 V15.2.0)
# ==> plus simple et implémentée par UERANSIM & Free5GC
# 1st byte
PDU_TYPE = int('0b11110000', 2)
# 2nd byte
PPP = int('0b10000000', 2)
RQI = int('0b01000000', 2)
QFI = int('0b00111111', 2)
# 3rd byte
PPI = int('0b11100000', 2)

# GTP-U message types
gtpu_message_types = {
    1: 'EchoRequest',
    2: 'EchoResponse',
    26: 'ErrorIndication',
    31: 'SupportedExtensionHeadersNotification',
    254: 'EndMarker',
    255: 'G-PDU'
}

# GTP-U extension header types (TS 29.281 V16.2.0)
extension_header_types = {
    0: 'No more extension headers',
    1: 'Reserved Control Plane only',
    2: 'Reserved Control Plane only',
    3: 'Long PDCP PDU Number',
    32: 'Service Class Indicator',
    64: 'UDP Port',
    129: 'RAN Container',
    130: 'Long PDCP PDU Number',
    131: 'Xw RAN Container',
    132: 'NR RAN Container',
    133: 'PDU Session Container',
    192: 'PDCP PDU Number',
    193: 'Reserved Control Plane only',
    194: 'Reserved Control Plane only'
}


class GtpuMessage:
    """GTP-U message class.

    This class parses and represents a GTP-U (GPRS Tunneling Protocol User Plane) message,
    extracting relevant header fields and the user payload.

    Attributes:
        gtpu_header (dict): Parsed header fields of the GTP-U message.
        gtpu_user_payload (memoryview): The user payload of the GTP-U message.
        gtpu_message (memoryview): The raw GTP-U message.
    """
    __slots__ = [
        'gtpu_header',
        'gtpu_user_payload',
        'gtpu_message'
    ]

    def __init__(self, gtpu_message: bytes):
        """Initialize a GtpuMessage object by parsing a GTP-U message.

        This function performs the following steps:

        1. Convert the raw GTP-U message bytes to a memoryview for efficient slicing.
        2. Validate the message length.
            - If the length of the message is less than 11 bytes, the initialization is aborted.
        3. Extract and store the following header fields int the `gtpu_header` dictionary:
            - **Version**: Extracted from the first byte.
            - **Flags**: Extracted and parsed from the first byte.
            - **Message Type**: Extracted from the second byte and mapped to its string equivalent.
            - **Message Length**: Extracted from the third and fourth bytes.
            - **TEID**: Extracted from the fifth to eighth bytes.
            - **Sequence Number**: Conditionally extracted based on the S flag.
            - **N-PDU Number**: Conditionally extracted based on the PN flag.
            - **Next Extension Header Field**: Conditionally extracted based on the E flag.
        4. Parse the extension headers if present.
        5. Store the remaining part of the message and the original GTP-U message bytes as \
        `gtpu_user_payload` and `gtpu_message` respectively.

        Args:
            gtpu_message (bytes): The raw GTP-U message bytes.
        """
        gtpu_message = memoryview(gtpu_message)
        if len(gtpu_message) < 11:
            return
        # Parse the message
        self.gtpu_header = {}
        # get version
        self.gtpu_header['Version'] = (GTPU_VERSION & gtpu_message[0]) / 32
        # get flags
        self.gtpu_header['PT'] = int((GTPU_PT & gtpu_message[0]) / 16)
        self.gtpu_header['E'] = bool(GTPU_E & gtpu_message[0])
        self.gtpu_header['S'] = bool(GTPU_S & gtpu_message[0])
        self.gtpu_header['PN'] = bool(GTPU_PN & gtpu_message[0])
        # get the message type as int
        self.gtpu_header['message_type_int'] = gtpu_message[1]  # second byte
        # get message type as string
        try:
            self.gtpu_header['message_type'] = \
                gtpu_message_types[self.gtpu_header['message_type_int']]
        except KeyError:
            self.gtpu_header['message_type'] = 'uknown'
        # get message length as int
        self.gtpu_header['message_length'] = \
            int.from_bytes(gtpu_message[2:4], byteorder='big', signed=False)    # 2 bytes
        # get TEID as int
        self.gtpu_header['TEID'] = \
            int.from_bytes(gtpu_message[4:8], byteorder='big', signed=False)    # 2 bytes
        offset = 8
        # get the sequence number if present (3 bytes)
        self.gtpu_header['sequence_number'] = \
            int.from_bytes(gtpu_message[offset:offset + 2], byteorder='big', signed=False) \
            if self.gtpu_header['S'] else None
        offset += 2
        # get the N-PDU number if present (1 byte)
        self.gtpu_header['NPDU_number'] = gtpu_message[offset] if self.gtpu_header['PN'] else None
        offset += 1
        # get the Next Extension Header Field if present (1 byte)
        next_extension_header_type = gtpu_message[offset] if self.gtpu_header['E'] else None
        offset += 1
        # Advance the offset through extension headers
        while next_extension_header_type:
            # get the length as int
            extension_header_length = gtpu_message[offset]
            # get the get the Next Extension Header as int
            next_extension_header_type = gtpu_message[offset + 4 * extension_header_length - 1]
            # move the offset
            offset += 4 * extension_header_length
        # get the payload
        self.gtpu_user_payload = gtpu_message[offset:]
        # Store the message bytes
        self.gtpu_message = gtpu_message

    def get_extension_headers(self):
        """Get the GTP-U extension headers as a generator object.

        This function performs the following steps:

        1. Initialize the offset to point to the start of the extension headers.
        2. Conditionally parse extension headers based on the Next Extension Header Field:
            - Extract the extension header length.
            - Extract the extension header type and map it to its string equivalent.
            - Extract and store the extension header content.
            - Conditionally decode the PDU Session Container extension header to extract PDU type \
            and QFI (QoS Flow Identifier).
            - Yield the parsed extension header dictionary.
            - Advance the offset to the next extension header.

        Yields:
            dict: Parsed extension header information.
        """
        # Parse extension headers
        gtpu_message = self.gtpu_message
        offset = 11
        # get the Next Extension Header Field if present (1 byte)
        next_extension_header_type = gtpu_message[offset] if self.gtpu_header['E'] else None
        offset += 1
        while next_extension_header_type:
            # parse the extension header
            e_header = {}
            # get the type as string
            try:
                e_header['type'] = extension_header_types[next_extension_header_type]
            except KeyError:
                e_header['type'] = 'uknown'
            # get the length as int
            extension_header_length = gtpu_message[offset]
            e_header['length'] = extension_header_length
            # get the content as bytes
            e_header['content'] = gtpu_message[offset + 1:offset + 4 * extension_header_length - 1]
            # check if it is a PDU Session Container
            if next_extension_header_type == 133:
                # parse PDU Session Container
                e_header['decoded_content'] = {}
                e_header['decoded_content']['PDU_Type'] = \
                    int((PDU_TYPE & gtpu_message[offset + 1]) / 16)
                if e_header['decoded_content']['PDU_Type'] == 0:
                    e_header['decoded_content']['PPP'] = int((PPP & gtpu_message[offset + 2]) / 128)
                    e_header['decoded_content']['RQI'] = int((RQI & gtpu_message[offset + 2]) / 64)
                e_header['decoded_content']['QFI'] = int(QFI & gtpu_message[offset + 2])
            # get the get the Next Extension Header as int
            next_extension_header_type = gtpu_message[offset + 4 * extension_header_length - 1]
            e_header['next'] = next_extension_header_type
            # move the offset
            offset += 4 * extension_header_length
            # Yield the extension header
            yield e_header


def parse_gtpu_message(gtpu_event, ctx, size):
    """Parse a GTP-U message and extract relevant information for metrics and logs.

    This function performs the following steps:

    1. Extract and store event-related information including layer, capturing time, \
    source/destination IPs, source/destination ports, and payload details.
    2. Parse the GTP-U message and extract information.
        - Extract the GTP-U message payload from the event and parse it using the `GtpuMessage` \
        class.
        - Extract the message type and extension headers from the parsed message.
        - Conditionally parse the PDU Session Container extension header to extract PDU type and \
        QFI.
        - Extract 5QI information based on QFI.
    3. Determine the server and client information, based on the message type, by calling the \
    `retrive_server_and_client_from_ips` function.
    4. Handle specific processing if the message is from/to the current node:
        - For uplink traffic: Extract the UE destination IP and store the forwarding time.
        - For downlink traffic: Extract the UE source IP, calculate forwarding time, and update \
        metrics.
    5. Update metrics related to GTP-U messages and log the final event information.

    Args:
        gtpu_event: The event containing GTP-U message data. This object should have attributes:

            - `layer` (str): The layer of the network stack.
            - `payload_length` (int): The length of the GTP-U payload.
            - `payload_offset` (int): The offset of the GTP-U payload within the raw data.
            - `ip_src` (bytes): The source IP address in binary format.
            - `ip_dest` (bytes): The destination IP address in binary format.
            - `src_port` (int): The source port number.
            - `dst_port` (int): The destination port number.
            - `capturing_time` (int): The time at which the packet was captured, in microseconds.
            - `raw` (bytearray): The raw packet data.

        ctx: The context of the event.
        size: The size of the GTP-U event.
    """
    metrics.primitives_called.labels('parse_gtpu_message').inc()

    # Read event infos
    layer = gtpu_event.layer
    capturing_time = gtpu_event.capturing_time / 1000000000  # Convert nanoseconds to seconds
    src_ip = socket.inet_ntop(socket.AF_INET, gtpu_event.ip_src)
    dst_ip = socket.inet_ntop(socket.AF_INET, gtpu_event.ip_dest)
    src_port = gtpu_event.src_port
    dst_port = gtpu_event.dst_port
    payload_length = gtpu_event.payload_length
    payload_offset = gtpu_event.payload_offset

    if cfg.DEBUG_EVENTS:
        # Debug the event
        log_dict_info(protocol='gtp', layer=layer, ctx=ctx, size=size,
                      raw=bytes(bytearray(gtpu_event.raw)),
                      length=payload_length, offset=payload_offset, capturing_time=capturing_time,
                      src_ip=src_ip, dst_ip=dst_ip, src_port=src_port, dst_port=dst_port)

    # read GTP-U bytes
    debut = payload_offset
    fin = payload_offset + payload_length
    gtpu_payload = memoryview(bytes(bytearray(gtpu_event.raw[debut:fin])))
    if not gtpu_payload:
        return

    # Clean item to free memory
    del ctx, size, debut, fin, payload_offset, gtpu_event

    # parse the GTP-U message
    gtpu_parsed = GtpuMessage(gtpu_payload)
    message_type_int = gtpu_parsed.gtpu_header['message_type_int']
    message_type = gtpu_parsed.gtpu_header['message_type']
    teid = gtpu_parsed.gtpu_header.get('TEID')
    eheaders = gtpu_parsed.get_extension_headers()  # This is a generator
    gtpu_user_payload = gtpu_parsed.gtpu_user_payload

    # Clean item to free memory
    gtpu_payload.release()
    del gtpu_payload, gtpu_parsed

    server_and_client = {}
    if message_type_int in [1, 31, 254, 255]:        # treated as a request
        server_and_client = \
            retrive_server_and_client_from_ips(server_ip=dst_ip, client_ip=src_ip,
                                               only_one_info_is_needed=False)
    elif message_type_int in [2, 26]:                # treated as a response
        # the order helps the LRU cache
        server_and_client = \
            retrive_server_and_client_from_ips(server_ip=src_ip, client_ip=dst_ip,
                                               only_one_info_is_needed=False)

    pdu_type = 'uknown'
    qfi_value = 'uknown'
    if message_type == 'G-PDU':
        # get PDU type and QFI
        for eheader in eheaders:
            if eheader['type'] == 'PDU Session Container':
                pdu_type = eheader['decoded_content']['PDU_Type']
                qfi_value = eheader['decoded_content']['QFI']

    if server_and_client['server_node_name'] == MY_NODE_NAME:

        session_type = 'uknown'
        direction = 'uknown'
        # handle the forwarding time
        if pdu_type == 1:   # Uplink trafic
            direction = 'uplink'
            # check that it's an IPv4 packet
            if (int('0b11110000', 2) & gtpu_user_payload[0]) / 16 == 4:
                session_type = "IPv4"
                # get the destination IP address in the UE packet
                dst_ip_ue = bytes(bytearray(gtpu_user_payload[16:20]))
                # dst_ip_ue = int.from_bytes(dst_ip_ue , "big")
                # dst_ip_ue = dst_ip_ue.to_bytes(4, 'little')
                dst_ip_ue = socket.inet_ntop(socket.AF_INET, dst_ip_ue)
                operation_time_buffer_write_item((dst_ip_ue, direction),
                                                 gtpu_forwarding_time, capturing_time)
                # Clean item to free memory
                del dst_ip_ue
        elif pdu_type == 0:   # Donwlink trafic
            direction = 'downlink'

            # check that it's an IPv4 packet
            if (int('0b11110000', 2) & gtpu_user_payload[0]) / 16 == 4:
                session_type = "IPv4"
                # get the source IP address in the UE packet
                src_ip_ue = bytes(bytearray(gtpu_user_payload[12:16]))
                src_ip_ue = socket.inet_ntop(socket.AF_INET, src_ip_ue)
                forwarding_time = 0
                capturing_time_request = \
                    operation_time_buffer_read_item((src_ip_ue, direction),
                                                    gtpu_forwarding_time, timeout=5)
                if capturing_time_request:
                    forwarding_time = capturing_time - capturing_time_request
                # Clean item to free memory
                del src_ip_ue, capturing_time_request

        # get 5QI
        fiveqi_value, fiveqi_type = get_qfi_info(qfi_value)

        event_info = {
            'protocol': 'gtpu',
            'direction': direction,
            'session_type': session_type,
            'fiveqi': fiveqi_value,
            'fiveqi_type': fiveqi_type,
            'message_type_int': message_type_int,
            'message_type': message_type,
        }

        metrics.gtpu_messages.labels(**event_info, **server_and_client).inc()
        metrics.gtpu_bytes.labels(**event_info, **server_and_client
                                  ).observe(payload_length)

        # Store in database
        database.insert_gtp_event(
            event_type=direction,
            timestamp=capturing_time,
            src_ip=src_ip,
            dst_ip=dst_ip,
            source_and_destination=server_and_client,
            message_type=message_type,
            teid=teid
        )

        event_info_extra = {
            'qfi': qfi_value,
            'src_port': src_port,
            'dst_port': dst_port,
            'length': payload_length,
            'capturing_time': capturing_time,
        }

        # update upf_forwarding_time metric
        if event_info['direction'] == 'downlink':
            if forwarding_time <= 0:
                # warn if forwarding_time is less or equal to 0
                logger.warning("forwarding_time of user data message "
                               f"{forwarding_time} is less or equal to 0")
            else:
                server_and_client_restricted = {}
                for key, value in server_and_client.items():
                    if 'client_' in key:
                        new_key = key.replace('client_', '')
                        server_and_client_restricted[new_key] = value
                metrics.upf_forwarding_time.labels(session_type='ipv4', direction='downlink',
                                                   **server_and_client_restricted
                                                   ).observe(forwarding_time)
            event_info_extra['forwarding_time'] = forwarding_time

        log_dict_info(20, **event_info, **event_info_extra, **server_and_client)


def parse_ipv4_packet(ipv4_event, ctx, size):
    """Parse an IPv4 packet and extract relevant information for metrics.

    This function performs the following steps:

    1. Extract and store event-related information including layer, capturing time, \
       source/destination IPs, total length, and DSCP.
    2. Determine the server and client information based on IP addresses by calling the \
    `retrive_server_and_client_from_ips` function.
    3. Determine the traffic direction and process accordingly:
        - For downlink traffic:
            - Restrict source and destination information to relevant fields.
            - Store the capturing time for the source IP in the operation time buffer.
        - For uplink traffic:
            - Restrict source and destination information to relevant fields.
            - Retrieve and calculate forwarding time, logging a warning if the time is less than or equal to 0.
            - Update the `upf_forwarding_time` metric with the calculated forwarding time.
    4. Update metrics related to IPv4 packets and log event information.

    Args:
        ipv4_event: The event containing IPv4 packet data.
        ctx: The context of the event.
        size: The size of the IPv4 packet.
    """
    metrics.primitives_called.labels('parse_ipv4_packet').inc()
    # Read event infos
    layer = ipv4_event.layer
    capturing_time = ipv4_event.capturing_time / 1000000000  # Convert nanoseconds to seconds
    src_ip = socket.inet_ntop(socket.AF_INET, ipv4_event.ip_src)
    dst_ip = socket.inet_ntop(socket.AF_INET, ipv4_event.ip_dest)
    tot_len = ipv4_event.tot_len
    dscp = (ipv4_event.tos & int('0b11111100', 2)) / 4    # read the dscp from tos field
    if int(dscp) == dscp:
        dscp = int(dscp)
    else:
        logger.warning(f'{dscp} DSCP calculated from {ipv4_event.tos} is not an integer')

    if cfg.DEBUG_EVENTS:
        # Debug the event
        log_dict_info(protocol='ipv4', layer=layer, ctx=ctx, size=size,
                      length=tot_len, capturing_time=capturing_time,
                      src_ip=src_ip, dst_ip=dst_ip)

    # Clean item to free memory
    del ctx, size, ipv4_event

    source_and_destination = {}
    source_and_destination = retrive_src_and_dst_from_ips(src_ip, dst_ip,
                                                          only_one_info_is_needed=True)

    event_info = {
        'protocol': 'ipv4',
        'dscp': dscp,
    }

    event_info_extra = {
        'length': tot_len,
        'capturing_time': capturing_time,
    }

    if source_and_destination['dst_node_name'] == MY_NODE_NAME:
        # DL trafic
        event_info['direction'] = 'downlink'
        # delete useless information
        source_and_destination_restricted = {}
        for key, value in source_and_destination.items():
            if 'dst_' in key:
                new_key = key.replace('dst_', '')
                source_and_destination_restricted[new_key] = value
        del source_and_destination
        # store the capturing time
        operation_time_buffer_write_item((src_ip, 'downlink'), gtpu_forwarding_time,
                                         capturing_time)

    elif source_and_destination['src_node_name'] == MY_NODE_NAME:
        # UL trafic
        event_info['direction'] = 'uplink'
        # delete useless information
        source_and_destination_restricted = {}
        for key, value in source_and_destination.items():
            if 'src_' in key:
                new_key = key.replace('src_', '')
                source_and_destination_restricted[new_key] = value
        del source_and_destination
        # get the forwarding time
        forwarding_time = 0
        capturing_time_request = operation_time_buffer_read_item((dst_ip, 'uplink'),
                                                                 gtpu_forwarding_time,
                                                                 timeout=5)
        if capturing_time_request:
            forwarding_time = capturing_time - capturing_time_request
        # Clean item to free memory
        del capturing_time_request
        # warn if forwarding_time is less or equal to 0
        if forwarding_time <= 0:
            logger.warning("forwarding_time of user data message "
                           f"{forwarding_time} is less or equal to 0")
        else:
            metrics.upf_forwarding_time.labels(session_type='ipv4', direction='uplink',
                                               **source_and_destination_restricted
                                               ).observe(forwarding_time)

        event_info_extra['forwarding_time'] = forwarding_time

    else:
        return

    metrics.n6_ip_packets.labels(**event_info, **source_and_destination_restricted).inc()
    metrics.n6_ip_bytes.labels(**event_info, **source_and_destination_restricted
                               ).observe(tot_len)

    log_dict_info(20, **event_info, **event_info_extra, **source_and_destination_restricted)
