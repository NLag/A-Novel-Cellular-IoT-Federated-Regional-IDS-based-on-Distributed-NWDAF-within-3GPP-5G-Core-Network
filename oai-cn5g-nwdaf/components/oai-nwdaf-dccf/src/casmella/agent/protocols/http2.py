"""HTTP/2 parsing module.
"""
# standard
from threading import Lock
import socket
import re
from urllib.parse import urlparse
# third-party
import yaml
from cachetools import cached, LFUCache
# from cachetools import cached, LRUCache, LFUCache, TTLCache
# internal
from .customized_hpack import CustomDecoder, HPACKDecodingError
from core import cfg, metrics, database
from core.custom_types import ThreadSafeDict, ThreadSafeTtlDict

# Global variables
SafeLoader = yaml.loader.SafeLoader
IGNORE_SENT_REQUESTS_AND_RECEIVED_RESPONSES = True
MY_NODE_NAME = cfg.MY_NODE_NAME
decoders = ThreadSafeDict()
openapi_operations = {}
openapi_id_cache = LFUCache(maxsize=256)
http2_response_time = ThreadSafeTtlDict()
http2_data_to_headers = {}
operation_time_buffer_write_item = cfg.operation_time_buffer_write_item
operation_time_buffer_read_item = cfg.operation_time_buffer_read_item
retrive_server_and_client_from_ips = cfg.retrive_server_and_client_from_ips
log_dict_info = cfg.log_dict_info
logger = cfg.logging

# Set logging configuration
for i in logger.Logger.manager.loggerDict:
    logger.getLogger(i).setLevel(cfg.logging.ERROR)

# Get headerblock
def get_http2_headerblock(http2_pdu: bytes) -> bytes:
    """Extract the HTTP/2 header block from the given HTTP/2 PDU.

    This function performs the following steps:
    1. Determine if the PDU contains padding or priority fields by checking specific flags.
    2. Adjust the start and end offsets for the header block based on the presence of padding and priority fields.
    3. Extract and return the header block from the PDU based on the calculated offsets.

    Args:
        http2_pdu (bytes): The HTTP/2 protocol data unit (PDU) from which the header block is to \
            be extracted.

    Returns:
        bytes: The extracted header block from the HTTP/2 PDU.
    """
    # Flags
    # HTTP2_END_HEADERS = int('0b00000100',2)
    # HTTP2_END_STREAM = int('0b00000001',2)
    # Check it additional fields are present
    padded = bool(http2_pdu[4] & int('0b00001000', 2))
    priority = bool(http2_pdu[4] & int('0b00100000', 2))
    start_offset = 9
    end_offset = len(http2_pdu)
    if padded:
        start_offset += 1
        end_offset -= http2_pdu[0]
    if priority:
        start_offset += 5
    # Get the header block
    return http2_pdu[start_offset:end_offset]


# Decode headers
def decode_headers(headerblock:bytes, src_ip: str, dst_ip:str) -> tuple:
    """Decode HTTP/2 headers from the given header block.

    This function performs the following steps:
    1. Determine the appropriate decoder instance based on the source and destination IP addresses.
        - If a decoder for the given peer (combination of `src_ip` and `dst_ip`) exists, use it.
        - Otherwise, create a new `CustomDecoder` instance and associate it with the peer.
    2. Attempt to decode the HTTP/2 header block using the selected decoder.
        - If decoding fails with an `HPACKDecodingError`, return `None` for the headers and `False`
        for the decode status.
        - If decoding succeeds, filter out headers that start with `:` (except for
        `:authority`).
    3. Return the decoded headers and a boolean indicating whether decoding was successful.

    Args:
        headerblock (bytes): The HTTP/2 header block to decode.
        src_ip (str): The source IP address associated with the HTTP/2 message.
        dst_ip (str): The destination IP address associated with the HTTP/2 message.

    Returns:
        tuple:
            - `decoded_headers` (list): A list of decoded HTTP/2 headers where each header is a
            tuple of (name, value).
            - `decoded` (bool): A boolean indicating whether the header block was successfully
            decoded.
    """
    # decoder = CustomDecoder()
    # try:
    #   decoded_headers = decoder.decode(headerblock)
    # except:
    #    decoded_headers = None
    #    decoded = False
    # else:
    #    decoded = True
    #
    # global decoders
    if (src_ip, dst_ip) in decoders:
        peer = (src_ip, dst_ip)
    elif (dst_ip, src_ip) in decoders:
        peer = (dst_ip, src_ip)
    else:
        peer = (src_ip, dst_ip)
        decoders[peer] = CustomDecoder()
    try:
        decoded_headers = decoders[peer].decode(headerblock)
    except HPACKDecodingError:
        decoded_headers = None
        decoded = False
    else:
        decoded = True
    # Excract only fields starting with ':'
    # The ':authority' header will not be used
    decoded_headers = [header for header in decoded_headers
                       if (header[0].startswith(":") and header[0] != ':authority')]
    return decoded_headers, decoded


# Parse HTTP/2 headers
def parse_http2_headers(decoded_headers: list) -> tuple:
    """Parse decoded HTTP/2 headers to determine if the message is a request or a response and
    extract relevant information.

    This function performs the following steps:
    1. Check the first header to determine if it is a response or request.
        - If the first header is `:status`, it is identified as a response.
        - If the first header is `:method`, it is identified as a request.
    2. For a response:
        - Extract the status code.
        - Determine the response status (`success` for 2xx and 3xx codes, `failure` for 4xx and 5xx
        codes).
        - If the status code is invalid (not a 3-digit number), mark it as `errored`.
        - Return the response type, status code, response status, and placeholder values for method,
        scheme, and path.
    3. For a request:
        - Extract the HTTP method and normalize it to lowercase.
        - Validate the HTTP method against a list of known methods, marking it as `errored` if it is unknown.
        - Extract the entire HTTP path and parse it to get the path component.
        - Extract the HTTP scheme and validate it, marking it as `errored` if it is neither `http` nor `https`.
        - Return the request type, method, scheme, entire path, and parsed path.

    Args:
        decoded_headers (list): A list of decoded HTTP/2 headers where each header is a tuple of
        (name, value).

    Returns:
        tuple:
            - `message_type` (str): Either 'response' or 'request' indicating the type of HTTP/2 message.
            - `details` (tuple): Contains relevant details for the message type:
                - For 'response': (status_code, response_status, None, None).
                - For 'request': (http_method, http_scheme, entire_http_path, http_path).
    """
    if decoded_headers[0][0] == ':status':
        # This is a response
        status_code = decoded_headers[0][1]
        response_status = 'failure' if status_code[0] in ('4', '5') else 'success'
        if not (status_code.isdigit() and len(status_code) == 3):
            status_code = 'errored'
            response_status = 'errored'
        return 'response', (status_code, response_status, None, None)
    # This is a request
    try:
        http_method = \
            [header[1] for header in decoded_headers if header[0] == ':method'][0]
    except IndexError:
        http_method = 'uknown'
        # logger.error(all_decoded_headers)
    else:
        http_method = http_method.lower()
        http_mothods_list = (
            'get', 'post', 'put',
            'delete', 'head', 'options',
            'connect', 'trace', 'patch'
            )
        if http_method not in http_mothods_list:
            http_method = 'errored'
    try:
        entire_http_path = \
            [header[1] for header in decoded_headers if header[0] == ':path'][0]
    except IndexError:
        entire_http_path = 'uknown'
        http_path = 'uknown'
    else:
        http_path = urlparse(entire_http_path).path
    try:
        http_scheme = \
            [header[1] for header in decoded_headers if header[0] == ':scheme'][0]
    except IndexError:
        http_scheme = 'uknown'
    else:
        if http_scheme not in ('http', 'https'):
            http_scheme = 'errored'
    # Return headers
    return 'request', (http_method, http_scheme, entire_http_path, http_path)


# Load OpenAPI specs
def load_openapi_operations(openapi_operations_file_path='openapi-operations-r16.yaml'):
    """
Load OpenAPI specs.
    """
    with open(openapi_operations_file_path, encoding='utf8',
              errors='ignore') as openapi_file:
        globals()['openapi_operations'] = yaml.load(openapi_file, Loader=SafeLoader)


# Get OperationId for HTTP path
def find_operation_id_for_http_path(path_template_methods: dict, http_method: str) -> str:
    """Find the OpenAPI operationId for a given HTTP/2 path based on the HTTP method.

    This function performs the following steps:
    1. Check if the provided HTTP method is not 'unknown'.
        - If a valid HTTP method is provided, look up the operationId in the
        `_path_template_methods` dictionary.
        - Return the operationId if found; otherwise, return 'unknown'.
    2. If the HTTP method is 'unknown', iterate through a predefined list of HTTP methods (`patch`,
    `put`, `delete`, `options`).
        - Attempt to find an operationId in the `_path_template_methods` dictionary for each
        method.
        - Return the first found operationId.
        - If no operationId is found for any of these methods, return 'unknown'.

    Args:
        path_template_methods (dict): A dictionary mapping HTTP methods to OpenAPI operationIds.
        http_method (str): The HTTP method for which to find the operationId.

    Returns:
        str: The OpenAPI operationId associated with the given HTTP method, or 'unknown' if not
        found.
    """
    if http_method != 'uknown':
        operation_id = path_template_methods.get(http_method, 'uknown')
        return operation_id
    operation_id = 'uknown'
    for _method in ('patch', 'put', 'delete', 'options'):
        try:
            operation_id = path_template_methods[_method]
        except KeyError:
            continue
        else:
            break
    return operation_id


# Get OperationId
@cached(cache=openapi_id_cache, lock=Lock())
def find_operation_id(http_method: str, http_path: str) -> str:
    """Find the OpenAPI operationId for a given HTTP/2 method and path.

    This function performs the following steps:
    1. Increment the 'find_operation_id' primitive call metric.
    2. Initialize the `operation_id` as 'unknown'.
    3. Check if the provided `http_path` is not 'unknown'.
        - If the `http_path` is valid, iterate through the `openapi_operations` dictionary.
        - For each `_path_template`, compile it into a regular expression pattern.
        - Check if the `http_path` matches the pattern of `_path_template`.
        - If a match is found, call `find_operation_id_for_http_path` to get the `operation_id` based on the `http_method`.
        - Break the loop once a matching template is found.
    4. Handle any `KeyError` exceptions by logging a warning message.
    5. Return the `operation_id`.

    Args:
        http_method (str): The HTTP method for which to find the operationId (e.g., 'get', 'post').
        http_path (str): The HTTP path for which to find the operationId.

    Returns:
        str: The OpenAPI operationId associated with the given HTTP method and path, or 'unknown'
        if not found.
    """
    metrics.primitives_called.labels('find_operation_id').inc()
    operation_id = 'uknown'
    if http_path != 'uknown':
        try:
            for _path_template, _path_template_methods in openapi_operations.items():
                # Check if http_path match the pattern of _path_template
                _pattern = re.compile(_path_template)
                if _pattern.fullmatch(http_path):    # Path found #
                    operation_id = \
                        find_operation_id_for_http_path(_path_template_methods, http_method)
                    break
        except KeyError:
            logger.warning(f'Uknown OPENAPI OPERATION: \
                (method: {http_method}, path: {http_path})')
    # Return operation_id
    return operation_id


def parse_http2_message(http2_event, ctx, size):
    """Parse an HTTP/2 message and extract relevant information for metrics.

    This function performs the following steps:
    1. Extract and store event-related information including layer, capturing time,
    source/destination IPs, source/destination ports, and payload details.
    2. Parse the HTTP/2 message and extract information.
        - Extract the payload bytes from the HTTP/2 event.
        - Determine if the payload is an HTTP/2 HEADERS frame.
        - If the frame is a HEADERS frame:
            - Verify the frame length.
            - Extract the stream ID and header block.
            - Decode the headers using the `decode_headers` function.
            - If headers cannot be decoded, log an error and return.
            - Parse the decoded headers to determine if the message is a request or response.
    3. Handle specific processing if the message is from/to the current node:
        - For requests:
            - Check the layer of the event.
            - Find the OpenAPI operationId using the `find_operation_id` function.
            - Store the capturing time and operationId.
            - Prepare and log event information.
            - Retrieve server and client information.
            - Update metrics for HTTP requests.
        - For responses:
            - Check the layer of the event.
            - Retrieve the response time and operationId.
            - Calculate the response time.
            - Prepare and log event information.
            - Retrieve server and client information.
            - Update metrics for HTTP responses and response times.
    4. Log the final event information.

    Args:
        http2_event: The event containing HTTP/2 message data. This object should have attributes:
            - `layer` (str): The layer of the network stack.
            - `payload_length` (int): The length of the HTTP/2 payload.
            - `payload_offset` (int): The offset of the HTTP/2 payload within the raw data.
            - `ip_src` (bytes): The source IP address in binary format.
            - `ip_dest` (bytes): The destination IP address in binary format.
            - `src_port` (int): The source port number.
            - `dst_port` (int): The destination port number.
            - `capturing_time` (int): The time at which the packet was captured, in microseconds.
            - `raw` (bytearray): The raw packet data.
        ctx: The context of the event.
        size: The size of the HTTP/2 event.
    """
    metrics.primitives_called.labels('parse_http2_message').inc()
    # Get event fields
    layer = http2_event.layer
    capturing_time = http2_event.capturing_time / 1000000000  # Convert nanoseconds to seconds
    src_ip = socket.inet_ntop(socket.AF_INET, http2_event.ip_src)
    dst_ip = socket.inet_ntop(socket.AF_INET, http2_event.ip_dest)
    src_port = http2_event.src_port
    dst_port = http2_event.dst_port
    payload_length = http2_event.payload_length
    payload_offset = http2_event.payload_offset

    if cfg.DEBUG_EVENTS:
        # Debug the event
        log_dict_info(protocol='http2', layer=layer, ctx=ctx, size=size,
                      raw=bytes(bytearray(http2_event.raw)),
                      length=payload_length, offset=payload_offset,
                      capturing_time=capturing_time,
                      src_ip=src_ip, dst_ip=dst_ip, src_port=src_port, dst_port=dst_port)

    # Read payload bytes
    debut = payload_offset
    fin = debut + payload_length
    http2_pdu = memoryview(bytes(bytearray(http2_event.raw[debut:fin])))
    if not http2_pdu:
        return

    # Clean item to free memory
    del ctx, size, debut, fin, payload_offset, http2_event

    if http2_pdu[3] == 0x1:    # HEADERS frame #
        # Check header length
        http2_length = int.from_bytes(http2_pdu[:3], byteorder='big', signed=False)
        if http2_length != len(http2_pdu[9:]):
            return
        # Get Stream Id
        stream_id = str(int.from_bytes(http2_pdu[5:9], byteorder='big'))
        # Get HeaderBlock
        headerblock = get_http2_headerblock(http2_pdu)
        # Decode headers
        decoded_headers, decoded = decode_headers(headerblock, src_ip, dst_ip)
        if (not decoded) or (not decoded_headers):
            logger.error(f'Cannot decode HTTP2 header block {bytes(http2_pdu)} \
                ({decoded_headers}, {decoded})')
            return

        if cfg.DEBUG_EVENTS:
            # Debug decoded headers
            logger.debug(f"Decoded headers src ip: {src_ip}, dst_ip: {dst_ip}, "
                         f"http2_pdu: {bytes(http2_pdu)}, decoded_headers: {decoded_headers}")

        # Clean item to free memory
        http2_pdu.release()
        headerblock.release()
        del http2_pdu, headerblock

        request_or_response, parsed_headers = parse_http2_headers(decoded_headers)
        # Clean item to free memory
        del decoded_headers

        if request_or_response == 'request':
            http_method, http_scheme, entire_http_path, http_path = parsed_headers
            # Check the eBPF layer of the event
            if IGNORE_SENT_REQUESTS_AND_RECEIVED_RESPONSES and \
                layer in (0, 2):     # Reported by XDP or TC ingres layer
                if cfg.DEBUG_EVENTS:
                    log_dict_info(
                        event='ignored', protocol='http2',
                        request_or_response=request_or_response,
                        parsed_headers=parsed_headers,
                        src_ip=src_ip, dst_ip=dst_ip,
                    )
                return
            # get operationId
            operation_id = find_operation_id(http_method, http_path)
            # GET unique ID of the request
            stream_unique_id = (src_ip, dst_ip, src_port, dst_port, stream_id)
            # Store the timestamp
            item = (capturing_time, operation_id)
            operation_time_buffer_write_item(stream_unique_id, http2_response_time, item)
            # Prepare event infos
            event_info = {
                'protocol': 'http2',
                'rr': 'request',
                'operationId': operation_id,
                'scheme': http_scheme,
                'method': http_method,
            }
            event_info_extra = {
                'src_port': src_port,
                'dst_port': dst_port,
                'path': entire_http_path,
                'capturing_time': capturing_time,
            }
            # Get source and destrination
            server_and_client = \
                retrive_server_and_client_from_ips(server_ip=dst_ip, client_ip=src_ip,
                                                   only_one_info_is_needed=False)
            # Update metrics
            metrics.http_requests.labels(**event_info, **server_and_client).inc()
            # Store in database
            database.insert_http2_event(
                event_type='request',
                timestamp=capturing_time,
                src_ip=src_ip,
                dst_ip=dst_ip,
                src_port=src_port,
                dst_port=dst_port,
                server_and_client=server_and_client,
                operation_id=operation_id,
                method=http_method,
                scheme=http_scheme,
                path=entire_http_path
            )

        elif request_or_response == 'response':
            status_code, response_status = parsed_headers[:2]
            # Check the eBPF layer of the event
            if IGNORE_SENT_REQUESTS_AND_RECEIVED_RESPONSES and \
                layer == 1:  # Reported by TC egress layer
                if cfg.DEBUG_EVENTS:
                    log_dict_info(
                        event='ignored', protocol='http2',
                        request_or_response=request_or_response,
                        parsed_headers=parsed_headers,
                        src_ip=src_ip, dst_ip=dst_ip,
                    )
                return
            # if server_and_client['server_node_name'] == MY_NODE_NAME:
            # Get the response_time and delete the item for that stream_id
            # Because this is a reponse, so dst_ip and src_ip are inverted
            stream_unique_id = (dst_ip, src_ip, dst_port, src_port, stream_id)
            response_time = 0
            operation_id = "request_uknown"
            response_time_item = \
                operation_time_buffer_read_item(stream_unique_id,
                                                http2_response_time, timeout=5)
            if response_time_item:
                capturing_time_request, operation_id = response_time_item
                response_time = capturing_time - capturing_time_request
                # Clean item to free memory
                del response_time_item, capturing_time_request
            # warn if response time is less or equal to 0
            if response_time <= 0:
                logger.warning("response_time of HTTP2 request "
                               f"{response_time} is less or equal to 0")
            # Prepare event infos
            event_info = {
                'protocol': 'http2',
                'rr': 'response',
                'operationId': operation_id,
                'status': response_status,
                'status_code': status_code,
            }
            event_info_extra = {
                'src_port': src_port,
                'dst_port': dst_port,
                'response_time': response_time,
                'capturing_time': capturing_time,
            }
            # Get source and destrination
            server_and_client = \
                retrive_server_and_client_from_ips(server_ip=src_ip, client_ip=dst_ip,
                                                   only_one_info_is_needed=False)
            # Update metrics
            metrics.http_responses.labels(**event_info, **server_and_client).inc()
            if response_time > 0:
                metrics.http_response_time.labels(**event_info, **server_and_client
                                                  ).observe(response_time)
            # Store in database
            database.insert_http2_event(
                event_type='response',
                timestamp=capturing_time,
                src_ip=src_ip,
                dst_ip=dst_ip,
                src_port=src_port,
                dst_port=dst_port,
                server_and_client=server_and_client,
                operation_id=operation_id,
                status_code=status_code,
                response_status=response_status,
                response_time=response_time if response_time > 0 else None
            )

        log_dict_info(20, **event_info, **event_info_extra, **server_and_client)
