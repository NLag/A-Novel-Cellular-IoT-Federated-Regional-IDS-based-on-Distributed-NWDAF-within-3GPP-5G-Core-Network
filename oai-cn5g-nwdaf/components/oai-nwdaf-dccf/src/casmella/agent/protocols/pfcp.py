"""PFCP parsing module.
"""
# standard
from threading import Thread
import socket
# internal
from core import cfg, metrics, database
from core.custom_types import ThreadSafeTtlDict

# Global variables
IGNORE_SENT_REQUESTS_AND_RECEIVED_RESPONSES = True
MY_NODE_NAME = cfg.MY_NODE_NAME
pfcp_response_time_stream = ThreadSafeTtlDict()
operation_time_single_write_item = cfg.operation_time_single_write_item
operation_time_single_read_item = cfg.operation_time_single_read_item
retrive_server_and_client_from_ips = cfg.retrive_server_and_client_from_ips
log_dict_info = cfg.log_dict_info
logger = cfg.logging
events_handlers_tasks = cfg.events_handlers_tasks

# Set logging configuration
for i in logger.Logger.manager.loggerDict:
    logger.getLogger(i).setLevel(cfg.logging.ERROR)

# PFCP header first byte content
PFCP_VERSION = int('0b11100000', 2)
PFCP_FO = int('0b00000100', 2)
PFCP_MP = int('0b00000010', 2)
PFCP_S = int('0b00000001', 2)

# PFCP header last byte content
PFCP_MESSAGE_PRIORITY = int('0b11110000', 2)

# PFCP message types (3GPP TS 29.244 7.3)
pfcp_message_types = {
    1: 'HeartbeatRequest',
    2: 'HeartbeatResponse',
    3: 'PFDManagementRequest',
    4: 'PFDManagementResponse',
    5: 'AssociationSetupRequest',
    6: 'AssociationSetupResponse',
    7: 'AssociationUpdateRequest',
    8: 'AssociationUpdateResponse',
    9: 'AssociationReleaseRequest',
    10: 'AssociationReleaseResponse',
    11: 'VersionNotSupportedResponse',
    12: 'NodeReportRequest',
    13: 'NodeReportResponse',
    14: 'SessionSetDeletionRequest',
    15: 'SessionSetDeletionResponse',
    50: 'SessionEstablishmentRequest',
    51: 'SessionEstablishmentResponse',
    52: 'SessionModificationRequest',
    53: 'SessionModificationResponse',
    54: 'SessionDeletionRequest',
    55: 'SessionDeletionResponse',
    56: 'SessionReportRequest',
    57: 'SessionReportResponse'
}

# IE Cause Value (3GPP TS 29.244 8.2.1)
ie_cause_values = {
    # Acceptance
    0: 'reserved',
    1: 'sucess',
    2: 'More Usage Report to send',
    # Rejection
    64: 'reason not specified',
    65: 'Session context not found',
    66: 'Mandatory IE missing',
    67: 'Conditional IE missing',
    68: 'Invalid length',
    69: 'Mandatory IE incorrect',
    70: 'Invalid Forwarding Policy',
    71: 'Invalid F-TEID allocation option',
    72: 'No established PFCP Association',
    73: 'Rule creation or modification Failure',
    74: 'PFCP entity in congestion',
    75: 'No resources available',
    76: 'Service not supported',
    77: 'System failure',
    78: 'Redirection Requested',
    79: 'All dynamic addresses are occupied',
}


class PfcpMessage:
    """PFCP message class.

    This class parses and represents a PFCP (Packet Forwarding Control Protocol) message,
    extracting relevant header fields and the user payload.

    Attributes:
        pfcp_header (dict): A dictionary containing parsed PFCP header fields.
        cause_ie (dict): A dictionary containing the 'Cause' IE type and value.
        err (str or int): Error message or code indicating the parsing result.
    """
    __slots__ = [
        'pfcp_header',
        'cause_ie',
        'err'
    ]

    def __init__(self, pfcp_message: bytes):
        """Initialize a PfcpMessage object by parsing a PFCP message.

        This function performs the following steps:

        1. Validate the message length.
            - If the length of the message is less than 11 bytes, the initialization is aborted.
        2. Parse the PFCP header to extract:
            - Version
            - Flags (FO, MP, S)
            - Message type (as both integer and string)
            - Message length
        3. Parse additional header fields based on whether the message is node-related or \
        session-related:
            - For session-related messages (`S` flag set):
                - Extract SEID (Session Endpoint Identifier)
                - Extract sequence number
                - Extract message priority
            - For node-related messages (`S` flag not set):
                - Extract sequence number
        4. Parse Information Elements (IEs) from the PFCP message:
            - Iterate through the IEs in the message.
            - Extract IE type, length, and value.
            - Specifically handle the 'Cause' IE (type 19) to extract its value and map it to a
            predefined cause description if available.
        5. Handle errors:
            - Check if the offset exceeds the message length and set an error message if
            applicable.
            - Set an error code (`err`) to 0 if no errors are found.

        Args:
            pfcp_message (bytes): The raw PFCP message bytes.
        """
        if len(pfcp_message) < 8:
            return
        self.pfcp_header = {}
        # get version
        self.pfcp_header['Version'] = (PFCP_VERSION & pfcp_message[0]) / 32
        # get flags
        self.pfcp_header['FO'] = bool(PFCP_FO & pfcp_message[0])
        self.pfcp_header['MP'] = bool(PFCP_MP & pfcp_message[0])
        self.pfcp_header['S'] = bool(PFCP_S & pfcp_message[0])
        # get the message type as int
        self.pfcp_header['message_type'] = pfcp_message[1]  # second byte
        if self.pfcp_header['message_type'] in pfcp_message_types:
            # get message type as string
            self.pfcp_header['message_type'] = \
                pfcp_message_types[self.pfcp_header['message_type']]
        # get message length as int
        self.pfcp_header['message_length'] = \
            int.from_bytes(pfcp_message[2:4], byteorder='big', signed=False)    # 2 bytes
        # parse header fileds
        # depending on wether this is a node-related message or a session-related message
        if self.pfcp_header['S']:
            if len(pfcp_message) < 16:
                return
            self.pfcp_header['SEID'] = \
                int.from_bytes(pfcp_message[4:12], byteorder='big', signed=False)   # 8 bytes
            self.pfcp_header['sequence_number'] = \
                int.from_bytes(pfcp_message[12:15], byteorder='big', signed=False)  # 3 bytes
            self.pfcp_header['messsage_priority'] = PFCP_MESSAGE_PRIORITY & pfcp_message[15]
            offset = 16
        else:
            self.pfcp_header['sequence_number'] = \
                int.from_bytes(pfcp_message[4:7], byteorder='big', signed=False)    # 3 bytes
            offset = 8

        # get a list of IE
        # self.IElist = []
        # search IE cause
        self.cause_ie = {'type': 19, 'value': 'none'}
        while offset < (self.pfcp_header['message_length'] + 4):
            # parse an IE
            information_element = {}
            information_element['type'] = \
                int.from_bytes(pfcp_message[offset:offset + 2],
                               byteorder='big', signed=False)   # 2 bytes
            information_element['length'] = \
                int.from_bytes(pfcp_message[offset + 2:offset + 4],
                               byteorder='big', signed=False)   # 2 bytes
            if information_element['type'] == 19:
                # Cause IE
                information_element['value'] = pfcp_message[offset + 4]
                # information_element['value'] = \
                #   int.from_bytes(pfcp_message[offset + 4], byteorder='big', signed=False) # 1 byte
                if information_element['value'] in ie_cause_values:
                    information_element['value'] = \
                        ie_cause_values[information_element['value']]
                self.cause_ie = information_element
            # self.IElist.append(IE)
            offset += information_element['length'] + 4
        if offset > (self.pfcp_header['message_length'] + 4):
            self.err = "The offset exceeds message length"
        else:
            self.err = 0


def get_pfcp_list(pfcp_data: bytes):
    """Extract and parse PFCP (Packet Forwarding Control Protocol) messages from a PFCP bundle.

    This function performs the following steps:

    1. Initialize an offset to zero to start reading from the beginning of the PFCP data.
    2. Iterate through the PFCP data until the entire bundle is processed.
        - Extract the PFCP message bytes from the current offset.
        - Create a `PfcpMessage` instance to parse the extracted message bytes.
        - Update the offset by adding the length of the parsed message and the header size.
        - Check for parsing errors and yield the parsed message if no errors are found.

    Args:
        pfcp_data (bytes): The raw bytes of the PFCP bundle to be parsed.

    Yields:
        PfcpMessage: A parsed PFCP message object for each message in the bundle.
    """
    offset = 0
    while offset < len(pfcp_data):
        packet_bytes = pfcp_data[offset:]
        pdu = PfcpMessage(packet_bytes)
        offset += pdu.pfcp_header['message_length'] + 4
        if pdu.err == 0:
            yield pdu


def parse_pfcp_message(pfcp_message: PfcpMessage, event_arg: tuple, layer: int):
    """Parse a PFCP (Packet Forwarding Control Protocol) message and extract relevant information
    for metrics and logs.

    This function performs the following steps:

    1. Extract and store event-related information including layer, capturing time, \
    source/destination IPs, source/destination ports, and payload details.
    2. Parse the PFCP message to extract:
        - Message type (request or response).
        - Sequence number.
        - Message length.
        - Procedure related to session or server node.
        - Cause IE for response messages.
    3. Handle specific processing if the message is a request or response:
        - For requests:
            - Retrieve server and client information.
            - Check if the server node matches the current node.
            - Store the capturing time and sequence number.
        - For responses:
            - Retrieve server and client information.
            - Check if the server node matches the current node.
            - Retrieve the request capturing time.
            - Calculate the response time.
            - Warn if the response time is less or equal to 0.
    4. Update metrics for PFCP requests and responses, including response times, and log the \
    final event information.

    Args:
        pfcp_message (PfcpMessage): The parsed PFCP message object.
        event_arg (tuple): The event argument containing source IP, destination IP, source port, destination port, and capturing time.
        layer (int): The eBPF layer of the event.
    """
    metrics.primitives_called.labels('parse_pfcp_message').inc()
    # Read event infos
    src_ip, dst_ip, src_port, dst_port, capturing_time = event_arg

    # Clean item to free memory
    del event_arg

    # Get pfcp message type
    message_type = str(pfcp_message.pfcp_header['message_type'])
    request_or_response = 'request' if 'Request' in message_type \
        else 'response' if 'Response' in message_type else 'uknown'

    # Check the eBPF layer of the event
    # condition_exit = (((layer == 0) or (layer == 2)) and \
    #   request_or_response == 'request' ) or ((layer == 1) and request_or_response == 'response')
    # if condition_exit:
    #    return

    # Get pfcp fields
    sequence_number = pfcp_message.pfcp_header['sequence_number']
    message_length = pfcp_message.pfcp_header['message_length'] + 4
    # because this filed doesn't count the 2 first bytes
    procedure_related_to = 'session' if pfcp_message.pfcp_header['S'] else 'server_node'
    if request_or_response == 'response':
        cause = str(pfcp_message.cause_ie['value'])
        response_status = 'success' if cause in ('none', 'sucess', 'More Usage Report to send') \
            else 'failure'

    # Clean item to free memory
    del layer, pfcp_message

    server_and_client = {}

    # if Request push in pfcp_response_time_stream
    if request_or_response == 'request':

        # Get Pods information
        server_and_client = \
            retrive_server_and_client_from_ips(server_ip=dst_ip, client_ip=src_ip,
                                               only_one_info_is_needed=False)

        # Check node concerned by the event
        if IGNORE_SENT_REQUESTS_AND_RECEIVED_RESPONSES and \
            server_and_client['server_node_name'] != MY_NODE_NAME:
            if cfg.DEBUG_EVENTS:
                log_dict_info(
                    event='ignored', protocol='pfcp',
                    message_type=message_type, request_or_response=request_or_response,
                    **server_and_client,
                )
            return

        request_unique_id = (src_ip, dst_ip, src_port, dst_port, sequence_number)
        # No need for a list because the sequence number is
        # unique to a peer of (request, response)
        operation_time_single_write_item(request_unique_id,
                                         pfcp_response_time_stream, capturing_time)

    # if Response pop pfcp_response_time_stream
    elif request_or_response == 'response':

        # Get Pods information
        server_and_client = \
            retrive_server_and_client_from_ips(server_ip=src_ip, client_ip=dst_ip,
                                               only_one_info_is_needed=False)

        # Check node concerned by the event
        if IGNORE_SENT_REQUESTS_AND_RECEIVED_RESPONSES and \
            server_and_client['server_node_name'] != MY_NODE_NAME:
            if cfg.DEBUG_EVENTS:
                log_dict_info(
                    reason='event', protocol='pfcp',
                    message_type=message_type, request_or_response=request_or_response,
                    **server_and_client,
                )
            return

        if message_type != 'VersionNotSupportedResponse':
            #  Because this response has no corresponding request

            # Because this is a reponse, so dst_ip and src_ip are inverted
            request_unique_id = (dst_ip, src_ip, dst_port, src_port, sequence_number)
            # Get response time
            response_time = 0
            capturing_time_request = \
                operation_time_single_read_item(request_unique_id,
                                                pfcp_response_time_stream, timeout=5)
            if capturing_time_request:
                response_time = capturing_time - capturing_time_request
            # Clean item to free memory
            del request_unique_id, capturing_time_request
            # Warn if response time is less or equal to 0
            if response_time <= 0:
                logger.warning("response_time of PFCP request "
                               f"{response_time} is less or equal to 0")

    # if server_and_client['server_node_name'] == MY_NODE_NAME:  # alredy checked
    event_info = {
        'protocol': 'pfcp',
        'rr': request_or_response,
        'procedure_related_to': procedure_related_to,
        'message_type': message_type,
    }

    if request_or_response == 'request':
        metrics.pfcp_requests.labels(**event_info, **server_and_client).inc()
        response_time = None
        # Store in database
        database.insert_pfcp_event(
            event_type='request',
            timestamp=capturing_time,
            src_ip=src_ip,
            dst_ip=dst_ip,
            server_and_client=server_and_client,
            message_type=message_type,
            sequence_number=sequence_number
        )
    elif request_or_response == 'response':
        event_info.update({
            'status': response_status,
            'cause': cause,
        })
        metrics.pfcp_responses.labels(**event_info, **server_and_client).inc()
        if response_time > 0:
            metrics.pfcp_response_time.labels(**event_info, **server_and_client
                                              ).observe(response_time)
        # Store in database
        database.insert_pfcp_event(
            event_type='response',
            timestamp=capturing_time,
            src_ip=src_ip,
            dst_ip=dst_ip,
            server_and_client=server_and_client,
            message_type=message_type,
            sequence_number=sequence_number,
            response_time=response_time if response_time > 0 else None,
            cause=cause
        )

    event_info_extra = {
        'src_port': src_port,
        'dst_port': dst_port,
        'length': message_length,
        'response_time': response_time,
        'capturing_time': capturing_time,
    }

    log_dict_info(20, **event_info, **event_info_extra, **server_and_client)


# PFCP bundle
def parse_pfcp_message_bundle(pfcp_event, ctx, size):
    """Parse a bundle of PFCP (Packet Forwarding Control Protocol) messages and extract individual \
    PFCP messages, which are further processed.

    This function performs the following steps:

    1. Extract and store event-related information including layer, capturing time, \
    source/destination IPs, source/destination ports, and payload details.
    2. Parse the PFCP bundle and extract individual PFCP messages:
        - Extract the payload bytes from the PFCP event.
        - Verify the payload length.
        - Iterate through the PFCP messages in the bundle.
        - For each PFCP message, submit a task to handle its parsing.

    Args:
        pfcp_event: The event containing PFCP bundle. This object should have attributes:
            - `layer` (str): The layer of the network stack.
            - `payload_length` (int): The length of the PFCP bundle.
            - `payload_offset` (int): The offset of the PFCP bundle within the raw data.
            - `ip_src` (bytes): The source IP address in binary format.
            - `ip_dest` (bytes): The destination IP address in binary format.
            - `src_port` (int): The source port number.
            - `dst_port` (int): The destination port number.
            - `capturing_time` (int): The time at which the packet was captured, in microseconds.
            - `raw` (bytearray): The raw packet data.
        ctx: The context of the event.
        size: The size of the SCTP event.
    """
    metrics.primitives_called.labels('parse_pfcp_message_bundle').inc()
    # get information about the event
    event_arg = {
        'src_ip': socket.inet_ntop(socket.AF_INET, pfcp_event.ip_src),
        'dst_ip': socket.inet_ntop(socket.AF_INET, pfcp_event.ip_dest),
        'src_port': pfcp_event.src_port,
        'dst_port': pfcp_event.dst_port,
        'capturing_time': pfcp_event.capturing_time / 1000000000  # Convert nanoseconds to seconds
    }
    layer = pfcp_event.layer
    payload_length = pfcp_event.payload_length
    payload_offset = pfcp_event.payload_offset

    if cfg.DEBUG_EVENTS:
        # Debug the event
        log_dict_info(protocol='pfcp', layer=layer, ctx=ctx, size=size,
                      raw=bytes(bytearray(pfcp_event.raw)),
                      length=payload_length, offset=payload_offset, **event_arg)

    # Read payload bytes
    debut = payload_offset
    fin = debut + payload_length
    pfcp_payload = memoryview(bytes(bytearray(pfcp_event.raw[debut:fin])))
    if not pfcp_payload:
        return

    # Clean item to free memory
    del ctx, size, debut, fin, payload_offset, pfcp_event

    # for pfcp_pdu in pfcp_list:
    for pfcp_pdu in get_pfcp_list(pfcp_payload):
        events_handlers_tasks.submit(
            parse_pfcp_message,
            pfcp_pdu, event_arg.values(), layer
        )

    # Clean item to free memory
    pfcp_payload.release()
