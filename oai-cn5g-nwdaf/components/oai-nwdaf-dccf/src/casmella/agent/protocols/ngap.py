"""SCTP and NGAP parsing module.
"""
# standard
from threading import Thread, Lock
import socket
from copy import copy
# internal
from . import ngap_asn1
from .nas import parse_nas_message
from .qos import get_qfi_info, store_qfi_info
from core import cfg, metrics, database
from core.custom_types import ThreadSafeTtlDict

# Global variables
IGNORE_SENT_REQUESTS_AND_RECEIVED_RESPONSES = True
MY_NODE_NAME = cfg.MY_NODE_NAME
ngap_object = ngap_asn1.NGAP_PDU_Descriptions.NGAP_PDU
ngap_response_time_stream = ThreadSafeTtlDict()
qfi_to_fiveqi = ThreadSafeTtlDict()
operation_time_buffer_write_item = cfg.operation_time_buffer_write_item
operation_time_buffer_read_item = cfg.operation_time_buffer_read_item
retrive_server_and_client_from_ips = cfg.retrive_server_and_client_from_ips
log_dict_info = cfg.log_dict_info
logger = cfg.logging
events_handlers_tasks = cfg.events_handlers_tasks

# Set logging configuration
for i in logger.Logger.manager.loggerDict:
    logger.getLogger(i).setLevel(cfg.logging.ERROR)

# NGAP class 1 procedures
ngap_procedures_class1 = (
    0,
    10,
    12,
    13,
    14,
    20,
    21,
    25,
    26,
    27,
    28,
    29,
    32,
    35,
    40,
    41,
    58,
    59,
    43,
    60,
    51
)


class SctpChunk:
    """SCTP chunk class.

    This class represents an SCTP (Stream Control Transmission Protocol) chunk. An SCTP
    chunk consists of a header and a value, with optional padding to ensure that the
    chunk size is a multiple of 4 bytes.

    Attributes:
        chunk_header (dict): A dictionary containing the chunk header fields:
            - 'Type': The type of the SCTP chunk.
            - 'Flags': The flags associated with the SCTP chunk.
            - 'Length': The length of the SCTP chunk (excluding padding).
        chunk_value (bytes): The actual data payload of the SCTP chunk.
        padding (bytes): Padding bytes added to make the chunk size a multiple of 4.
    """
    __slots__ = [
        'chunk_header',
        'chunk_value',
        'padding'
    ]

    def __init__(self, sctp_chunk):
        if len(sctp_chunk) < 4:
            return
        self.chunk_header = {}
        # get chunk header fields
        self.chunk_header['Type'] = sctp_chunk[0]
        self.chunk_header['Flags'] = sctp_chunk[1]
        self.chunk_header['Length'] = \
            int.from_bytes(sctp_chunk[2:4], byteorder='big', signed=False)  # 2 bytes

        # get chunk value
        padding_size = 4 - self.chunk_header['Length'] % 4
        # length_with_padding_size = self.chunk_header['Length'] + padding_size
        chunk_header_length = 4
        self.chunk_value = sctp_chunk[chunk_header_length:self.chunk_header['Length']]
        if padding_size == 4:
            padding_size = 0
        self.padding = b'0' * padding_size


def get_sctp_data_chunks(sctp_chunks_bytes: bytes):
    """
    Get the list of SCTP data chunks within an SCTP bundle as a generator object.

    Args:
        sctp_chunks_bytes (bytes): The raw bytes of SCTP chunks.

    Yields:
        SctpChunk: The next SCTP data chunk in the sequence.
    """
    offset = 0
    while offset < len(sctp_chunks_bytes):
        chunk_bytes = sctp_chunks_bytes[offset:]
        pdu = SctpChunk(chunk_bytes)
        offset = offset + pdu.chunk_header['Length'] + len(pdu.padding)
        if pdu.chunk_header['Type'] == 0:
            # this a DATA chunk
            yield pdu
        # if (pdu.chunk_header['Length'] + len(pdu.padding) % 4) !=:
            # print("ERROR when calculating padding_size!")


def parse_ngap_pdu_session_resource_setup_request_transfer(protocol_ies: list):
    """Parse NGAP PDU session resource setup request transfer IEs.

    This function performs the following operations:
    1. Initialize the QoS flow event type as 'create'.
    2. Iterate over the list of protocol IEs (Information Elements).
    3. For each IE, check if its ID is 136, which corresponds to the QoS flow setup request list.
    4. If the IE ID is 136:
       a. Extract the list of QoS flows from the value field of the IE.
       b. For each QoS flow in the list:
          i. Extract the QoS Flow Identifier (QFI).
          ii. Extract the QoS Characteristics, including:
              - The type of 5QI (QoS Identifier).
              - The value of 5QI.
          iii. Yield a tuple containing the QoS flow event type ('create'), QFI, 5QI value, and
          5QI type.

    Args:
        protocol_ies (list): A list of protocol Information Elements (IEs) to be parsed.

    Yields:
        tuple: A tuple containing the QoS flow event type, QoS Flow Identifier (QFI), 5QI value,
        and 5QI type.
    """
    qos_flow_event_type = 'create'
    for element in protocol_ies:
        if element['id'] == 136:  # 136 ==  qos flow setup request list
            qos_flow_list = element['value'][1]
            for flow in qos_flow_list:
                qfi_value = flow['qosFlowIdentifier']
                fiveqi_info = flow['qosFlowLevelQosParameters']['qosCharacteristics']
                fiveqi_type = fiveqi_info[0]
                fiveqi_value = fiveqi_info[1]['fiveQI']
                yield qos_flow_event_type, qfi_value, fiveqi_value, fiveqi_type


def parse_ngap_pdu_session_resource_modify_request_transfer(protocol_ies: list):
    """
    Parse NGAP PDU session resource modify request transfer IEs.

    This function performs the following operations:
    1. Initialize the QoS flow event type as 'modify'.
    2. Iterate over the list of protocol IEs (Information Elements).
    3. For each IE, check if its ID is 136, which corresponds to the QoS flow setup request list.
    4. If the IE ID is 136:
       a. Extract the list of QoS flows from the value field of the IE.
       b. For each QoS flow in the list:
          i. Extract the QoS Flow Identifier (QFI).
          ii. Attempt to extract the QoS Characteristics from the flow, including:
              - The type of 5QI (QoS Identifier).
              - The value of 5QI.
          iii. If the QoS Characteristics are missing, set the 5QI value and type to 'unknown'.
          iv. Yield a tuple containing the QoS flow event type ('modify'), QFI, 5QI value, and
          5QI type.

    Args:
        protocol_ies (list): A list of protocol Information Elements (IEs) to be parsed.

    Yields:
        tuple: A tuple containing the QoS flow event type, QoS Flow Identifier (QFI), 5QI value, and 5QI type.
    """
    qos_flow_event_type = 'modify'
    for element in protocol_ies:
        if element['id'] == 136:  # 136 ==  qos flow setup request list
            qos_flow_list = element['value'][1]
            for flow in qos_flow_list:
                qfi_value = flow['qosFlowIdentifier']
                try:
                    fiveqi_info = flow['qosFlowLevelQosParameters']['qosCharacteristics']
                    fiveqi_type = fiveqi_info[0]
                    fiveqi_value = fiveqi_info[1]['fiveQI']
                except KeyError:
                    fiveqi_value = 'uknown'
                    fiveqi_type = 'uknown'
                yield qos_flow_event_type, qfi_value, fiveqi_value, fiveqi_type


def parse_ngap_ies(message: str, protocol_ies: list):
    """
    Parse NGAP (Next Generation Application Protocol) Information Elements (IEs).

    This function processes a list of protocol IEs based on the type of NGAP message.
    1. It extracts relevant information elements based on their IDs and yields key details.
    2. It also handles specific types of NGAP messages to extract QoS flow information and
    NAS (Non-Access Stratum) messages.
        - The function first determines if the provided message type is one of the special types
        that require additional parsing.
        - For special messages, it processes nested elements to extract QoS flow and NAS message
        details.
        - QoS flow details are extracted using helper functions
        `parse_ngap_pdu_session_resource_setup_request_transfer` and
        `parse_ngap_pdu_session_resource_modify_request_transfer`.

    Args:
        message (str): The type of NGAP message, which determines the processing logic.
        protocol_ies (list): A list of protocol Information Elements (IEs) to be parsed.
        Each element is expected to be a dictionary containing at least 'id' and 'value' fields.

    Yields:
        tuple: Depending on the type of IE, the function yields tuples with the following formats:
            - ('Cause IE', (cause_layer, cause)): For Cause IE (element ID 15), yields the cause layer and cause code.
            - ('RAN_UE_NGAP_ID', ran_ue_ngap_id): For RAN-UE-NGAP-ID (element ID 85), yields the RAN-UE-NGAP-ID.
            - ('NAS message', nas_pdu): For NAS PDU (element IDs 37 or 38), yields the NAS message as a memoryview.
            - ('NAS message', nas_pdu): For NAS messages within specific types of NGAP messages, yields the NAS message as a memoryview.
            - ('QoS Flow', qos_flow_event): For QoS flows within PDU session resource setup or modify requests, yields the QoS flow event details.
    """
    special_message = message in ('PDUSessionResourceSetupRequest',
                                  'PDUSessionResourceModifyRequest',
                                  'InitialContextSetupRequest')
    for element in protocol_ies:
        if element['id'] == 15:
            # Get Cause IE
            information_element = element['value']
            cause_layer = information_element[0]
            cause = information_element[1]
            yield 'Cause IE', (cause_layer, cause)

        elif element['id'] == 85:
            # Get RAN-UE-NGAP-ID if present
            information_element = element['value']
            yield 'RAN_UE_NGAP_ID', information_element[1]

        elif (element['id'] == 38) or (element['id'] == 37):
            # Get NAS PDU
            information_element = element['value']
            nas_pdu = memoryview(information_element[1])
            yield 'NAS message', nas_pdu

        if special_message and 'PDUSessionResource' in element['value'][0]:
            for _element in element['value'][1]:
                if 'pDUSessionNAS-PDU' in _element:
                    # Get NAS PDU
                    nas_pdu = memoryview(_element['pDUSessionNAS-PDU'])
                    yield 'NAS message', nas_pdu
                if 'NAS-PDU' in _element:
                    # Get NAS PDU
                    nas_pdu = memoryview(_element['NAS-PDU'])
                    yield 'NAS message', nas_pdu

                # find QoS flows to be created
                if 'pDUSessionResourceSetupRequestTransfer' in _element:
                    _ies_list = \
                        _element['pDUSessionResourceSetupRequestTransfer'][1]['protocolIEs']
                    qos_flow_events = \
                        parse_ngap_pdu_session_resource_setup_request_transfer(_ies_list)
                    for qos_flow_event in qos_flow_events:
                        yield 'QoS Flow', qos_flow_event

                # find QoS flows to be modified
                if 'pDUSessionResourceModifyRequestTransfer' in _element:
                    _ies_list = \
                        _element['pDUSessionResourceModifyRequestTransfer'][1]['protocolIEs']
                    qos_flow_events = \
                        parse_ngap_pdu_session_resource_modify_request_transfer(_ies_list)
                    for qos_flow_event in qos_flow_events:
                        yield 'QoS Flow', qos_flow_event


def parse_ngap_message(ngap_pdu: bytes, event_arg: tuple, layer: int):
    """
    Parse an NGAP (Next Generation Application Protocol) message and extract relevant information
    for metrics and logs.

    This function processes an NGAP PDU (Protocol Data Unit), extracts key details, calculates
    response times, and logs various metrics. It handles different types of NGAP messages and
    their associated IEs (Information Elements). The function also interacts with metrics and
    event handlers to manage QoS flow and NAS messages.

    This function performs the following steps:
    1. Extract and store event-related information including layer, capturing time,
    source/destination IPs, source/destination ports, and payload details.
    2. Parse the NGAP message and extract information.
        - Create a copy of the `NGAP` object and decode the provided PDU using the `from_aper`
        method.
        - Extract functions for retrieving values from the decoded PDU.
        - Extract the message type and procedure code from the decoded PDU.
        - Determine the procedure and its class based on the procedure code.
    3. Determine the server and client information, based on the message type, by calling the
    `retrive_server_and_client_from_ips` function.
    4. Handle specific processing if the message is from/to the current node:
        - For initiating messages: Record request times for procedure class 1.
        - For response messages: Calculate response times and log any anomalies if response time
        is less than or equal to zero.
    5. Parse NGAP IEs.
        - Extract message name and protocol IEs from the decoded PDU.
        - Handle parsing of various IEs such as Cause IE, RAN-UE-NGAP-ID, NAS messages, and QoS
        flows.
        - Use helper functions to parse NAS messages (in separate Threads) and handle QoS flow
        creation or modification.
        - Use helper functions to handle QoS flow creation or modification.
        - Update metrics related to QoS flows and log related event information
    4. Update metrics for NGAP requests and responses, including response times, and log the
    final event information.

    Args:
        ngap_pdu (object): The NGAP PDU object to be parsed. This object should have a `from_aper` method for decoding and a `release` method for cleanup.
        event_arg (tuple): A tuple containing event-related information:
            - src_ip (str): Source IP address of the NGAP message.
            - dst_ip (str): Destination IP address of the NGAP message.
            - src_port (int): Source port of the NGAP message.
            - dst_port (int): Destination port of the NGAP message.
            - capturing_time (float): The time at which the message was captured.
        layer (object): An object representing the layer in which the NGAP message was captured. This parameter is not used within the function but is included in the signature for consistency.
    """
    metrics.primitives_called.labels('parse_ngap_message').inc()

    procedures = ngap_asn1.NGAP_Constants._val_[:66]
    # global ngap_response_time_stream

    # Read event infos
    src_ip, dst_ip, src_port, dst_port, capturing_time = event_arg

    # Clean item to free memory
    del event_arg

    # Decode ngap_pdu
    decoded_ngap_pdu = copy(ngap_object)
    length = len(ngap_pdu)
    decoded_ngap_pdu.from_aper(bytes(ngap_pdu))
    # Keep fonctions that will be used
    decoded_ngap_pdu_get_val = decoded_ngap_pdu.get_val()
    decoded_ngap_pdu_get_val_at = decoded_ngap_pdu.get_val_at

    # Clean item to free memory
    try:
        ngap_pdu.release()
    except:
        logger.warning(f"{ngap_pdu} ngap_pdu of type "
                       f"{type(ngap_pdu)} has no release() method")
    del layer, ngap_pdu, decoded_ngap_pdu

    # retrieve NGAP information (message_type and procedure_code)
    message_type = decoded_ngap_pdu_get_val[0]
    procedure_code = decoded_ngap_pdu_get_val_at([message_type, 'procedureCode'])
    procedure = procedures[procedure_code]
    procedure_class = 1 if int(procedure_code) in ngap_procedures_class1 else 2

    # Get resource and destination
    server_and_client = {}
    if message_type == 'initiatingMessage':
        # request
        server_and_client = \
            retrive_server_and_client_from_ips(server_ip=dst_ip, client_ip=src_ip,
                                               only_one_info_is_needed=False)
    else:
        # response (the order helps the LRU cache)
        server_and_client = \
            retrive_server_and_client_from_ips(server_ip=src_ip, client_ip=dst_ip,
                                               only_one_info_is_needed=False)

    if IGNORE_SENT_REQUESTS_AND_RECEIVED_RESPONSES and \
        server_and_client['server_node_name'] != MY_NODE_NAME:
        if cfg.DEBUG_EVENTS:
            log_dict_info(
                event='ignored', protocol='ngap', message_type=message_type,
                procedure_code=procedure_code, procedure=procedure, procedure_class=procedure_class,
                **server_and_client,
            )
        return

    cause_layer = 'none'
    cause = 'none'
    if message_type is not None:
        # Handle response time
        if message_type == 'initiatingMessage':    # Request #
            if procedure_class == 1:
                request_unique_id = (src_ip, dst_ip, src_port, dst_port, procedure_code)
                operation_time_buffer_write_item(request_unique_id,
                                                    ngap_response_time_stream, capturing_time)
        else:   # Response #
            if procedure_class == 1:
                # Because this is a reponse, so dst_ip and src_ip are inverted
                request_unique_id = (dst_ip, src_ip, dst_port, src_port, procedure_code)
                response_time = 0
                capturing_time_request = \
                    operation_time_buffer_read_item(request_unique_id,
                                                    ngap_response_time_stream, timeout=5)
                if capturing_time_request:
                    response_time = capturing_time - capturing_time_request
                # Clean item to free memory
                del request_unique_id, capturing_time_request
                # warn if response time is less or equal to 0
                if response_time <= 0:
                    logger.warning("response_time of NGAP request "
                                    f"{response_time} is less or equal to 0")
            else:
                logger.warning("Found an NGAP response with a Class 2 procedure")

        try:
            # Get the message name as a string
            message = decoded_ngap_pdu_get_val_at([message_type, 'value'])[0]
            # Get all IEs as a list
            protocol_ies = \
                decoded_ngap_pdu_get_val_at([message_type, 'value',
                                                message, 'protocolIEs'])
        except:
            logger.exception("cannot read IEs from NGAP message: "
                                f"procedure and message type are {message_type} {procedure}")
            to_be_logged = decoded_ngap_pdu_get_val
            logger.error(to_be_logged)
        else:
            # Clean item to free memory
            del decoded_ngap_pdu_get_val_at, decoded_ngap_pdu_get_val

            # call parse_nas_message if the NGAP message contains a NAS message
            event_arg = {
                'src_ip': src_ip,
                'dst_ip': dst_ip,
                'ngap_message_type': message_type,
                'ngap_procedure': procedure,
                'ran_ue_ngap_id': None,
                'capturing_time': capturing_time
            }

            for information_type, information in parse_ngap_ies(message, protocol_ies):
                if information_type == 'Cause IE':
                    cause_layer, cause = information
                elif information_type == 'RAN_UE_NGAP_ID':
                    event_arg['ran_ue_ngap_id'] = information
                elif information_type == 'NAS message':
                    events_handlers_tasks.submit(
                        parse_nas_message,
                        information, event_arg.values()
                    )
                elif information_type == 'QoS Flow':
                    action, qfi_value, fiveqi_value, fiveqi_type = information
                    if action == 'modify' and fiveqi_value == 'uknown':
                        fiveqi_value, fiveqi_type = get_qfi_info(qfi_value)
                    if action == 'create':
                        store_qfi_info(qfi_value, fiveqi_value, fiveqi_type)
                    metrics.qos_flows.labels(action, fiveqi_type,
                                                    str(fiveqi_value)).inc()
    # Prepare event infos
    event_info = {
        'protocol': 'ngap',
        'rr': 'request' if message_type == 'initiatingMessage' else 'response',
        'procedure_code': procedure_code,
        'procedure': procedure,
        'procedure_class': procedure_class,
        'message_type': message_type,
        'cause_layer': cause_layer,
        'cause': cause,
    }

    if message_type == 'initiatingMessage':
        metrics.ngap_requests.labels(**event_info, **server_and_client).inc()
        response_time = None
        # Store in database
        database.insert_ngap_event(
            event_type='request',
            timestamp=capturing_time,
            src_ip=src_ip,
            dst_ip=dst_ip,
            source_and_destination=server_and_client,
            message_type=message_type,
            procedure=procedure,
            cause=cause if cause != 'none' else None
        )
    else:
        event_info['status'] = 'success' if message_type == 'successfulOutcome' else 'failure'
        metrics.ngap_responses.labels(**event_info, **server_and_client).inc()
        if response_time > 0:
            metrics.ngap_response_time.labels(**event_info, **server_and_client
                                                ).observe(response_time)
        # Store in database
        database.insert_ngap_event(
            event_type='response',
            timestamp=capturing_time,
            src_ip=src_ip,
            dst_ip=dst_ip,
            source_and_destination=server_and_client,
            message_type=message_type,
            procedure=procedure,
            cause=cause if cause != 'none' else None
        )

    event_info_extra = {
        'src_port': src_port,
        'dst_port': dst_port,
        'length': length,
        'response_time': response_time,
        'capturing_time': capturing_time,
    }

    log_dict_info(20, **event_info, **event_info_extra, **server_and_client)


# SCTP Packet (may be a bundle)
def parse_sctp_packet(ngap_event, ctx, size):
    """Parse an SCTP (Stream Control Transmission Protocol) packet and extract NGAP
    (Next Generation Application Protocol) messages. SCTP payloads are parsed to extract NGAP
    messages, which are further processed

    This function performs the following steps:
    1. Extract and store event-related information including layer, capturing time,
    source/destination IPs, source/destination ports, and payload details.
    2. Parse the SCTP packet and extract chunks:
        - Use the `get_sctp_data_chunks` function to iterate over SCTP data chunks.
        - For each data chunk, extract the chunk value and check the PPID (Protocol Payload Identifier).
        - If the PPID indicates an NGAP message (PPID == 60):
            - Extract the NGAP PDU from the chunk value.
            - Submit the NGAP PDU for further parsing using the `parse_ngap_message` function.

    Args:
        ngap_event: The event containing SCTP packet data. This object should have attributes:
            - `layer` (str): The layer of the network stack.
            - `payload_length` (int): The length of the SCTP payload.
            - `payload_offset` (int): The offset of the SCTP payload within the raw data.
            - `ip_src` (bytes): The source IP address in binary format.
            - `ip_dest` (bytes): The destination IP address in binary format.
            - `src_port` (int): The source port number.
            - `dst_port` (int): The destination port number.
            - `capturing_time` (int): The time at which the packet was captured, in microseconds.
            - `raw` (bytearray): The raw packet data.
        ctx: The context of the event.
        size: The size of the SCTP event.
    """
    metrics.primitives_called.labels('parse_sctp_packet').inc()
    # Read event infos
    layer = ngap_event.layer
    payload_length = ngap_event.payload_length
    payload_offset = ngap_event.payload_offset
    event_arg = {
        'src_ip': socket.inet_ntop(socket.AF_INET, ngap_event.ip_src),
        'dst_ip': socket.inet_ntop(socket.AF_INET, ngap_event.ip_dest),
        'src_port': ngap_event.src_port,
        'dst_port': ngap_event.dst_port,
        'capturing_time': ngap_event.capturing_time / 1000000000  # Convert nanoseconds to seconds
    }

    if cfg.DEBUG_EVENTS:
        log_dict_info(protocol='ngap', layer=layer, ctx=ctx, size=size,
                      raw=bytes(bytearray(ngap_event.raw)),
                      length=payload_length, offset=payload_offset, **event_arg)

    # Read payload bytes
    debut = payload_offset
    fin = payload_offset + payload_length
    sctp_chunks_bytes = memoryview(bytes(bytearray(
        ngap_event.raw[payload_offset:payload_offset + payload_length]
    )))
    if not sctp_chunks_bytes:
        return

    # Clean item to free memory
    del ctx, size, debut, fin, payload_offset, ngap_event

    # Parse the payload
    for data_chunk in get_sctp_data_chunks(sctp_chunks_bytes):
        chunk_value = data_chunk.chunk_value
        sctp_ppid = int.from_bytes(chunk_value[8:12], byteorder='big', signed=False)    # 2 bytes
        if sctp_ppid == 60:
            # this an NGAP message
            ngap_pdu = chunk_value[12:]
            events_handlers_tasks.submit(
                parse_ngap_message,
                ngap_pdu, event_arg.values(), layer
            )
