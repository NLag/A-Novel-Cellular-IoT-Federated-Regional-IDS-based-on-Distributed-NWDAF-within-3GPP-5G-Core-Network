"""NAS parsing module.
"""
# third-pary
from pycrate_mobile import NAS5G, TS24501_FGMM, TS24501_FGSM, TS24501_IE
# internal
from core import cfg, metrics, database
from core.custom_types import ThreadSafeTtlDict

# Global variables
MY_NODE_NAME = cfg.MY_NODE_NAME
nas_message_types_dict = TS24501_FGMM._FGMM_dict
nas_message_types_dict.update(TS24501_FGSM._FGSM_dict)
nas_registration_queue = ThreadSafeTtlDict()
operation_time_single_write_item = cfg.operation_time_single_write_item
operation_time_single_read_item = cfg.operation_time_single_read_item
retrive_src_and_dst_from_ips = cfg.retrive_src_and_dst_from_ips
log_dict_info = cfg.log_dict_info
logger = cfg.logging

# Set logging configuration
for i in logger.Logger.manager.loggerDict:
    logger.getLogger(i).setLevel(cfg.logging.ERROR)


def parse_nas_message(nas_pdu: bytes, event_arg: tuple):
    """Parse NAS (Non-Access Stratum) message and extract relevant information for metrics and
    logs.

    This function performs the following steps:

    1. Extract and store event-related information including source/destination IPs, \
    NGAP message type, NGAP procedure, RAN UE NGAP ID, and capturing time.
    2. Parse the NAS message and extract information:
        - Decode the NAS message.
        - If the message is encrypted, decrypt it and decode again.
        - Extract the message type.
        - Extract cause information if present.
    3. Handle specific processing if the message is a Registration Request, Accept or Reject:
        - For requests:
            - Record request times.
            - Record registration type.
        - For responses:
            - Calculate response times and log any anomalies if response time is less than or
            equal to zero.
            - Extract and match the registration type.
    4. Update metrics related to NAS messages and log the final event information.

    Args:
        nas_pdu: The NAS message PDU (Protocol Data Unit).
        event_arg: A tuple containing event-related information.
            - `src_ip` (str): The layer of the network stack.
            - `dst_ip` (str): The length of the PFCP bundle.
            - `ngap_message_type` (int): The offset of the PFCP bundle within the raw data.
            - `ngap_procedure` (bytes): The source IP address in binary format.
            - `ran_ue_ngap_id` (bytes): The destination IP address in binary format.
            - `capturing_time` (int): The source port number.
    """
    metrics.primitives_called.labels('parse_nas_message').inc()
    # Debug the event
    if cfg.DEBUG_EVENTS:
        log_dict_info(protocol='nas',
                      raw=bytes(nas_pdu),
                      event_arg=event_arg)
    # Read event infos
    src_ip, dst_ip, ngap_message_type, ngap_procedure, ran_ue_ngap_id, capturing_time  = event_arg

    # Clean item to free memory
    del event_arg

    decoded_message, err = NAS5G.parse_NAS5G(buf=bytes(nas_pdu), inner=False)    # décoder
    if bool(err):
        logger.error(f"Cannot decode the NAS message {bytes(nas_pdu)} because of the error {err}")
        return

    length = decoded_message.get_len()    # return total length in bytes

    # Copy the cleartext PDU if it encrypted
    protected = 'false'
    if 'NASMessage' in decoded_message.get_val_d():
        protected = 'true'
        nas_pdu = memoryview(decoded_message.get_val_d()['NASMessage'])
        decoded_message, err = NAS5G.parse_NAS5G(bytes(nas_pdu))
        if bool(err):
            logger.error(f"Cannot decode the NAS message {bytes(nas_pdu)}")
            return

    # get the message type
    try:
        message_type_int = decoded_message[0].get_val_d()['Type']
    except KeyError:
        logger.warning(f"Cannot get the type of the NAS message {bytes(nas_pdu)}")
        message_type_int = -1
        message_type = 'uknown'
    else:
        try:
            message_type = nas_message_types_dict[message_type_int]
        except KeyError:
            message_type = 'uknown'
            logger.warning(f"Unable to recognize NAS message type {message_type_int}")

    # Clean item to free memory
    del nas_pdu, err

    registration_type = 'none'
    cause_int = 'none'
    cause = 'none'
    response_time = None

    if message_type_int in (66, 68):
        # if it is a Registration Accept (66) or a Registration Reject (68)
        response_time = 0
        response_id = (src_ip, ran_ue_ngap_id)    # direction of the message AMF->gNB
        response_time_item = \
            operation_time_single_read_item(response_id,
                                            nas_registration_queue, timeout=5)
        capturing_time_request, registration_type = None, 'request_uknown'
        if response_time_item:
            capturing_time_request, registration_type = response_time_item
            response_time = capturing_time - capturing_time_request
        # Clean item to free memory
        del response_id, response_time_item, capturing_time_request
        # warn if response time is less or equal to 0
        if response_time <= 0:
            logger.warning("response_time of NAS registration "
                           f"{response_time} is less or equal to 0")

    # parse IEs
    for nas_ie in decoded_message:
        # get registration type if present (it is only present in Registration requests)
        if nas_ie._name == '5GSRegType':
            registration_type_int = nas_ie.get_val_d()['5GSRegType']['Value']
            try:
                registration_type = TS24501_IE._FGSRegType_dict[registration_type_int]
            except KeyError:
                registration_type = 'uknown'
            # store information about the registration request
            request_id = (dst_ip, ran_ue_ngap_id)    # direction of the message gNB->AMF
            item = (capturing_time, registration_type)
            operation_time_single_write_item(request_id, nas_registration_queue, item)
            # Clean item to free memory
            del request_id, item
        # get 5GMM cause
        elif nas_ie._name == '5GMMCause':
            cause_int = nas_ie.get_val_d()['5GMMCause']
            try:
                cause = TS24501_IE._FGMMCause_dict[cause_int]
            except KeyError:
                cause = 'uknown'
        # get 5GSM cause
        elif nas_ie._name == '5GSMCause':
            cause_int = nas_ie.get_val_d()['5GSMCause']
            try:
                cause = TS24501_IE._FGSMCause_dict[cause_int]
            except KeyError:
                cause = 'uknown'

    # Clean item to free memory
    del decoded_message

    event_info = {
        'protocol': 'nas',
        'message_type_int': message_type_int,
        'message_type': message_type,
        'registration_type': registration_type,
        'cause': cause,
        'ngap_procedure': ngap_procedure,
    }

    # retrive information about source and destination
    source_and_destination = retrive_src_and_dst_from_ips(src_ip, dst_ip)

    # this metric is labelled by AMF and AN infos
    metrics.nas_messages.labels(**event_info, **source_and_destination).inc()

    if message_type_int in (66, 68):
        # if it is a Registration Accept (66) or a Registration Reject (68)
        if response_time > 0:
            source_and_destination_restricted = {}
            for key in source_and_destination:
                if 'src_' in key:
                    new_key = key.replace('src_', '')
                    source_and_destination_restricted[new_key] = \
                        source_and_destination[key]
            # this metrics is labelled by AMF infos
            metrics.ue_registration_time.labels(**event_info,
                                                **source_and_destination_restricted
                                                ).observe(response_time)

    # Store in database
    database.insert_nas_event(
        event_type=message_type,
        timestamp=capturing_time,
        src_ip=src_ip,
        dst_ip=dst_ip,
        source_and_destination=source_and_destination,
        message_type=message_type,
        registration_type=registration_type if registration_type != 'none' else None,
        cause=cause if cause != 'none' else None,
        response_time=response_time if response_time and response_time > 0 else None,
        ngap_procedure=ngap_procedure
    )

    event_info_extra = {
        'ngap_message_type': ngap_message_type,
        'protected': protected,
        'cause_int': cause_int,
        'length': length,
        'capturing_time': capturing_time,
        'nas_response_time': response_time
    }

    # log the event
    log_dict_info(20, **event_info, **source_and_destination, **event_info_extra)
