import logging

from hpack.table import HeaderTable, table_entry_size
from hpack.exceptions import (
    HPACKDecodingError, OversizedHeaderListError, InvalidTableSizeError
)
from hpack.huffman import HuffmanEncoder
from hpack.huffman_constants import (
    REQUEST_CODES, REQUEST_CODES_LENGTH
)
from hpack.huffman_table import decode_huffman
from hpack.struct import HeaderTuple, NeverIndexedHeaderTuple

log = logging.getLogger(__name__)

from hpack import *

# Precompute 2^i for 1-8 for use in prefix calcs.
# Zero index is not used but there to save a subtraction
# as prefix numbers are not zero indexed.
_PREFIX_BIT_MAX_NUMBERS = [(2 ** i) - 1 for i in range(9)]

def _unicode_if_needed(header, raw):
    """
    Provides a header as a unicode string if raw is False, otherwise returns
    it as a bytestring.
    """
    name = bytes(header[0])
    value = bytes(header[1])
    if not raw:
        name = name.decode('utf-8')
        value = value.decode('utf-8')
    return header.__class__(name, value)

def decode_integer(data, prefix_bits):
    """
    This decodes an integer according to the wacky integer encoding rules
    defined in the HPACK spec. Returns a tuple of the decoded integer and the
    number of bytes that were consumed from ``data`` in order to get that
    integer.
    """
    if len(data) == 0:
        return 0, 0

    if prefix_bits < 1 or prefix_bits > 8:
        raise ValueError(
            "Prefix bits must be between 1 and 8, got %s" % prefix_bits
        )

    max_number = _PREFIX_BIT_MAX_NUMBERS[prefix_bits]
    index = 1
    shift = 0
    mask = (0xFF >> (8 - prefix_bits))

    try:
        number = data[0] & mask
        if number == max_number:
            while index < len(data):
                next_byte = data[index]
                index += 1

                if next_byte >= 128:
                    number += (next_byte - 128) << shift
                else:
                    number += next_byte << shift
                    break
                shift += 7

    except IndexError:
        raise HPACKDecodingError(
            "Unable to decode HPACK integer representation from %r" % data
        )

    log.debug("Decoded %d, consumed %d bytes", number, index)

    return number, index


def _decode_literal(data, should_index):
    total_consumed = 0

    # When should_index is true, if the low six bits of the first byte are
    # nonzero, the header name is indexed.
    # When should_index is false, if the low four bits of the first byte
    # are nonzero the header name is indexed.
    if should_index:
        indexed_name = data[0] & 0x3F
        name_len = 6
        __not_indexable = False
    else:
        high_byte = data[0]
        indexed_name = high_byte & 0x0F
        name_len = 4
        __not_indexable = high_byte & 0x10

    if indexed_name:
        # Indexed header name.
        __index, consumed = decode_integer(data, name_len)
        total_consumed = consumed
        length = 0
    else:
        # Literal header name. The first byte was consumed, so we need to
        # move forward.
        data = data[1:]

        length, consumed = decode_integer(data, 7)

        total_consumed = consumed + length + 1  # Since we moved forward 1.

    data = data[consumed + length:]

    # The header value is definitely length-based.
    length, consumed = decode_integer(data, 7)

    # Updated the total consumed length.
    total_consumed += length + consumed

    return total_consumed

class CustomDecoder(Decoder):
    def decode(self, data, raw=False):
        log.debug("Decoding %s", data)

        data_mem = memoryview(data)
        headers = []
        data_len = len(data)
        inflated_size = 0
        current_index = 0

        while current_index < data_len:
            # Work out what kind of header we're decoding.
            # If the high bit is 1, it's an indexed field.
            current = data[current_index]
            indexed = True if current & 0x80 else False

            # Otherwise, if the second-highest bit is 1 it's a field that does
            # alter the header table.
            literal_index = True if current & 0x40 else False

            # Otherwise, if the third-highest bit is 1 it's an encoding context
            # update.
            encoding_update = True if current & 0x20 else False

            ### These checks are added by me (Raouf)

            # Check if it is Literal Header Field without Indexing
            # literal_no_index = False if current & 0xf0 else True

            # Check if it is Literal Header Field Never Indexed
            # literal_never_indexed = True if current & 0x10 else False

            if indexed:
                try:
                    header, consumed = self._decode_indexed(
                        data_mem[current_index:]
                    )
                except:
                    index, consumed = decode_integer(data_mem[current_index:], 7) # See source code (https://github.com/python-hyper/hpack/blob/v4.0.0/src/hpack/hpack.py#L545)
                    header = None

            elif literal_index:
                # It's a literal header that does affect the header table.
                try:
                    header, consumed = self._decode_literal_index(
                        data_mem[current_index:]
                    )
                except:
                    consumed = _decode_literal(data_mem[current_index:], True)
                    header = None

            elif encoding_update:
                # It's an update to the encoding context. These are forbidden
                # in a header block after any actual header.
                try:
                    if headers:
                        raise HPACKDecodingError(
                            "Table size update not at the start of the block"
                        )
                    consumed = self._update_encoding_context(
                        data_mem[current_index:]
                    )
                    header = None
                except:
                    new_size, consumed = decode_integer(data_mem[current_index:], 5)
                    header = None

            else:
                # It's a literal header that does not affect the header table.
                try:
                    header, consumed = self._decode_literal_no_index(
                        data_mem[current_index:]
                    )
                except:
                    consumed = _decode_literal(data_mem[current_index:], False)
                    header = None

            if header:
                headers.append(header)
                inflated_size += table_entry_size(*header)

                if inflated_size > self.max_header_list_size:
                    raise OversizedHeaderListError(
                        "A header list larger than %d has been received" %
                        self.max_header_list_size
                    )

            current_index += consumed

        # Confirm that the table size is lower than the maximum. We do this
        # here to ensure that we catch when the max has been *shrunk* and the
        # remote peer hasn't actually done that.
        self._assert_valid_table_size()

        try:
            return [_unicode_if_needed(h, raw) for h in headers]
        except UnicodeDecodeError:
            raise HPACKDecodingError("Unable to decode headers as UTF-8.")
