"""Transport packet parsing and construction utilities.

This module provides a small, well-documented packet model for a transport-like
protocol represented as a sequence of 32-bit words. The API supports:

- decoding packets from raw words or bytes
- building packets from logical payload bits and header fields
- serialising packets back to words or bytes
- slicing payload bits even when the payload is not byte aligned
- validating header fields at construction time
- stubs for checksum that can be implemented later

The packet payload is stored internally as a single integer plus an explicit
logical bit length. All other payload representations are derived from that
single source of truth to prevent internal drift.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Optional, Union

import numpy as np
import numpy.typing as npt


UInt32Array = npt.NDArray[np.uint32]
StateValue = Union[int, "TransportPacketState"]
StateChangeValue = Union[int, "TransportStateChangeFlag"]


class TransportPacketState(IntEnum):
    """Generic 3-bit transport state enumeration.

    The protocol-specific meaning of each value can be assigned later without
    changing the wire format. Using an enum at the interface makes debugging,
    logging, and later refactoring easier than passing raw integers everywhere.
    """

    VALUE_0 = 0
    VALUE_1 = 1
    VALUE_2 = 2
    VALUE_3 = 3
    VALUE_4 = 4
    VALUE_5 = 5
    VALUE_6 = 6
    VALUE_7 = 7


class TransportStateChangeFlag(IntEnum):
    """Generic 3-bit requested-state-change enumeration."""

    VALUE_0 = 0
    VALUE_1 = 1
    VALUE_2 = 2
    VALUE_3 = 3
    VALUE_4 = 4
    VALUE_5 = 5
    VALUE_6 = 6
    VALUE_7 = 7


class TransportPacketValidator:
    """Validation helpers for transport packet objects and fields."""

    @staticmethod
    def validate_words_array(words: object) -> None:
        """Validate that *words* is a 1D ``numpy.ndarray`` of ``np.uint32``.

        :param words: Object expected to contain packet words.
        :raises TypeError: If the input is not a NumPy array of ``np.uint32``.
        :raises ValueError: If the input is not one-dimensional.
        """

        if not isinstance(words, np.ndarray):
            raise TypeError("words must be a numpy.ndarray")

        if words.dtype != np.uint32:
            raise TypeError(f"words must have dtype np.uint32, got {words.dtype}")

        if words.ndim != 1:
            raise ValueError("words must be a 1D numpy array")

    @staticmethod
    def validate_u32_value(value: int, field_name: str) -> None:
        """Validate that *value* fits in an unsigned 32-bit integer."""

        if not isinstance(value, int):
            raise TypeError(f"{field_name} must be an int")

        if value < 0 or value > 0xFFFFFFFF:
            raise ValueError(f"{field_name} must fit in uint32")

    @staticmethod
    def validate_non_negative_int(value: int, field_name: str) -> None:
        """Validate that *value* is a non-negative integer."""

        if not isinstance(value, int):
            raise TypeError(f"{field_name} must be an int")

        if value < 0:
            raise ValueError(f"{field_name} must be non-negative")

    @staticmethod
    def validate_bit_value(value: int, field_name: str) -> None:
        """Validate a single-bit field."""

        if value not in (0, 1):
            raise ValueError(f"{field_name} must be 0 or 1")

    @staticmethod
    def validate_payload_bits(payload_bits_as_int: int, payload_bit_length: int) -> None:
        """Validate logical payload bit representation.

        :param payload_bits_as_int: Integer containing the logical payload bits.
        :param payload_bit_length: Number of valid payload bits in the integer.
        :raises TypeError: If the values are not integers.
        :raises ValueError: If the length is negative, the payload is negative,
            or the payload cannot fit within the requested bit length.
        """

        TransportPacketValidator.validate_non_negative_int(
            payload_bit_length, "payload_bit_length"
        )
        TransportPacketValidator.validate_non_negative_int(
            payload_bits_as_int, "payload_bits_as_int"
        )

        if payload_bit_length == 0 and payload_bits_as_int != 0:
            raise ValueError(
                "payload_bits_as_int must be 0 when payload_bit_length is 0"
            )

        if payload_bit_length > 0 and payload_bits_as_int >= (1 << payload_bit_length):
            raise ValueError(
                "payload_bits_as_int does not fit within payload_bit_length bits"
            )

    @staticmethod
    def validate_header_fields(header: "TransportPacketHeader") -> None:
        """Validate all header fields.

        :param header: Header instance to validate.
        :raises TypeError: If a field type is invalid.
        :raises ValueError: If a field is outside its allowed wire-format range.
        """

        TransportPacketValidator.validate_u32_value(
            header.sequence_number, "sequence_number"
        )
        TransportPacketValidator.validate_u32_value(
            header.acknowledgement_number, "acknowledgement_number"
        )

        if not (0 <= header.padding_length_bits <= 31):
            raise ValueError("padding_length_bits must be in range 0..31")

        TransportPacketValidator.validate_bit_value(header.source_bit, "source_bit")
        TransportPacketValidator.validate_bit_value(header.ack_bit, "ack_bit")
        TransportPacketValidator.validate_bit_value(header.rst_bit, "rst_bit")
        TransportPacketValidator.validate_bit_value(header.syn_bit, "syn_bit")
        TransportPacketValidator.validate_bit_value(header.fin_bit, "fin_bit")

        if not (0 <= header.current_state <= 0x7):
            raise ValueError("current_state must fit in 3 bits")

        if not (0 <= header.change_state_flag <= 0x7):
            raise ValueError("change_state_flag must fit in 3 bits")

        TransportPacketValidator.validate_bit_value(
            header.state_change_ack, "state_change_ack"
        )

        if not (0 <= header.reserved <= 0x7FFF):
            raise ValueError("reserved must fit in 15 bits")

        if not (0 <= header.window_size <= 0xFFFF):
            raise ValueError("window_size must fit in 16 bits")

        if not (0 <= header.checksum <= 0xFFFF):
            raise ValueError("checksum must fit in 16 bits")


class TransportPacketConverter:
    """Conversions between bytes, words, and payload bit representations."""

    @staticmethod
    def words_to_bytes(words: UInt32Array) -> bytes:
        """Convert a ``np.uint32`` word array to big-endian bytes."""

        TransportPacketValidator.validate_words_array(words)
        return words.astype(">u4", copy=False).tobytes()

    @staticmethod
    def bytes_to_words(data: bytes) -> UInt32Array:
        """Convert big-endian bytes to a ``np.uint32`` word array.

        :param data: Byte string whose length must be a multiple of four.
        :raises ValueError: If the byte length is not word aligned.
        """

        if len(data) % 4 != 0:
            raise ValueError("Byte length must be a multiple of 4")

        return np.frombuffer(data, dtype=">u4").astype(np.uint32)

    @staticmethod
    def payload_bits_to_words(
        payload_bits_as_int: int,
        payload_bit_length: int,
    ) -> tuple[UInt32Array, int]:
        """Convert logical payload bits into transmitted payload words.

        The logical payload is left-shifted so that any required padding occupies
        the least-significant transmitted bits. This matches the decode path,
        which removes padding by right-shifting the padded payload value.

        :param payload_bits_as_int: Payload bits represented as an integer.
        :param payload_bit_length: Number of valid bits in the payload integer.
        :return: Tuple of ``(payload_words, padding_length_bits)``.
        """

        TransportPacketValidator.validate_payload_bits(
            payload_bits_as_int=payload_bits_as_int,
            payload_bit_length=payload_bit_length,
        )

        if payload_bit_length == 0:
            return np.array([], dtype=np.uint32), 0

        padded_bit_length = ((payload_bit_length + 31) // 32) * 32
        padding_length_bits = padded_bit_length - payload_bit_length

        # The transmitted payload contains the logical payload followed by zero
        # padding bits in the least-significant positions.
        transmitted_value = payload_bits_as_int << padding_length_bits
        padded_byte_length = padded_bit_length // 8
        padded_bytes = transmitted_value.to_bytes(padded_byte_length, byteorder="big")

        return TransportPacketConverter.bytes_to_words(padded_bytes), padding_length_bits

    @staticmethod
    def payload_bytes_to_words(
        payload_bytes: bytes,
        padding_length_bits: int = 0,
    ) -> UInt32Array:
        """Convert payload bytes plus explicit padding into payload words.

        This helper is retained for byte-aligned callers, but the more general
        packet builder uses logical payload bits directly.
        """

        if not (0 <= padding_length_bits <= 31):
            raise ValueError("padding_length_bits must be in range 0..31")

        total_payload_bits = len(payload_bytes) * 8 + padding_length_bits
        padded_word_count = (total_payload_bits + 31) // 32
        padded_byte_count = padded_word_count * 4

        payload_as_int = int.from_bytes(payload_bytes, byteorder="big") if payload_bytes else 0
        payload_as_int <<= padding_length_bits

        padded_bytes = payload_as_int.to_bytes(padded_byte_count, byteorder="big")
        return TransportPacketConverter.bytes_to_words(padded_bytes)


class TransportPacketHeader:
    """Represents the fixed four-word transport packet header."""

    def __init__(
        self,
        sequence_number: int,
        acknowledgement_number: int,
        padding_length_bits: int,
        source_bit: int,
        ack_bit: int,
        rst_bit: int,
        syn_bit: int,
        fin_bit: int,
        current_state: StateValue,
        change_state_flag: StateChangeValue,
        state_change_ack: int,
        reserved: int,
        window_size: int,
        checksum: int,
    ) -> None:
        """Initialise a packet header and validate all fields immediately.

        :param sequence_number: 32-bit sequence number.
        :param acknowledgement_number: 32-bit acknowledgement number.
        :param padding_length_bits: Number of zero padding bits appended to the
            payload in the transmitted form.
        :param source_bit: Source selector bit.
        :param ack_bit: ACK flag.
        :param rst_bit: RST flag.
        :param syn_bit: SYN flag.
        :param fin_bit: FIN flag.
        :param current_state: Current 3-bit state value or enum.
        :param change_state_flag: Requested 3-bit state change or enum.
        :param state_change_ack: State-change acknowledgement bit.
        :param reserved: 15-bit reserved field.
        :param window_size: 16-bit advertised window size.
        :param checksum: 16-bit checksum field.
        """

        self.sequence_number = sequence_number
        self.acknowledgement_number = acknowledgement_number
        self.padding_length_bits = padding_length_bits
        self.source_bit = source_bit
        self.ack_bit = ack_bit
        self.rst_bit = rst_bit
        self.syn_bit = syn_bit
        self.fin_bit = fin_bit
        self.current_state = int(current_state)
        self.change_state_flag = int(change_state_flag)
        self.state_change_ack = state_change_ack
        self.reserved = reserved
        self.window_size = window_size
        self.checksum = checksum

        TransportPacketValidator.validate_header_fields(self)

    @classmethod
    def from_words(cls, words: UInt32Array) -> "TransportPacketHeader":
        """Decode a header from the first four packet words."""

        TransportPacketValidator.validate_words_array(words)

        if words.size < 4:
            raise ValueError("Need at least 4 words to decode TransportPacket header")

        word0 = int(words[0])
        word1 = int(words[1])
        word2 = int(words[2])
        word3 = int(words[3])

        return cls(
            sequence_number=word0,
            acknowledgement_number=word1,
            padding_length_bits=(word2 >> 27) & 0x1F,
            source_bit=(word2 >> 26) & 0x1,
            ack_bit=(word2 >> 25) & 0x1,
            rst_bit=(word2 >> 24) & 0x1,
            syn_bit=(word2 >> 23) & 0x1,
            fin_bit=(word2 >> 22) & 0x1,
            current_state=TransportPacketState((word2 >> 19) & 0x7),
            change_state_flag=TransportStateChangeFlag((word2 >> 16) & 0x7),
            state_change_ack=(word2 >> 15) & 0x1,
            reserved=word2 & 0x7FFF,
            window_size=(word3 >> 16) & 0xFFFF,
            checksum=word3 & 0xFFFF,
        )

    def to_words(self) -> UInt32Array:
        """Serialise the header to four big-endian 32-bit words."""

        TransportPacketValidator.validate_header_fields(self)

        word0 = np.uint32(self.sequence_number)
        word1 = np.uint32(self.acknowledgement_number)

        word2 = np.uint32(
            ((self.padding_length_bits & 0x1F) << 27)
            | ((self.source_bit & 0x1) << 26)
            | ((self.ack_bit & 0x1) << 25)
            | ((self.rst_bit & 0x1) << 24)
            | ((self.syn_bit & 0x1) << 23)
            | ((self.fin_bit & 0x1) << 22)
            | ((self.current_state & 0x7) << 19)
            | ((self.change_state_flag & 0x7) << 16)
            | ((self.state_change_ack & 0x1) << 15)
            | (self.reserved & 0x7FFF)
        )

        word3 = np.uint32(
            ((self.window_size & 0xFFFF) << 16)
            | (self.checksum & 0xFFFF)
        )

        return np.array([word0, word1, word2, word3], dtype=np.uint32)

    def __repr__(self) -> str:
        """Return a debug-friendly representation of the header."""

        return (
            "TransportPacketHeader("
            f"sequence_number={self.sequence_number}, "
            f"acknowledgement_number={self.acknowledgement_number}, "
            f"padding_length_bits={self.padding_length_bits}, "
            f"source_bit={self.source_bit}, "
            f"ack_bit={self.ack_bit}, "
            f"rst_bit={self.rst_bit}, "
            f"syn_bit={self.syn_bit}, "
            f"fin_bit={self.fin_bit}, "
            f"current_state={self.current_state}, "
            f"change_state_flag={self.change_state_flag}, "
            f"state_change_ack={self.state_change_ack}, "
            f"reserved=0x{self.reserved:04X}, "
            f"window_size={self.window_size}, "
            f"checksum=0x{self.checksum:04X}"
            ")"
        )


class TransportPacket:
    """Represents a complete transport packet.

    The packet stores the payload in exactly one canonical form:
    ``payload_bits_as_int`` plus ``payload_bit_length``. Byte and word views are
    derived on demand to avoid the object drifting out of sync.
    """

    HEADER_WORD_COUNT = 4

    def __init__(
        self,
        header: TransportPacketHeader,
        payload_bits_as_int: int,
        payload_bit_length: int,
        original_words: Optional[UInt32Array] = None,
    ) -> None:
        """Initialise a packet from a validated header and logical payload bits.

        :param header: Parsed or constructed packet header.
        :param payload_bits_as_int: Logical payload bits represented as an int.
        :param payload_bit_length: Number of valid payload bits.
        :param original_words: Optional original word array from decode. This is
            stored only for debugging and round-trip inspection.
        """

        TransportPacketValidator.validate_header_fields(header)
        TransportPacketValidator.validate_payload_bits(
            payload_bits_as_int=payload_bits_as_int,
            payload_bit_length=payload_bit_length,
        )

        expected_padding = self.compute_padding_length_bits(payload_bit_length)
        if header.padding_length_bits != expected_padding:
            raise ValueError(
                "header.padding_length_bits does not match payload_bit_length"
            )

        self.header = header
        self._payload_bits_as_int = payload_bits_as_int
        self._payload_bit_length = payload_bit_length
        self._original_words = None if original_words is None else original_words.copy()

    @property
    def original_words(self) -> Optional[UInt32Array]:
        """Return a copy of the originally decoded words, if available."""

        if self._original_words is None:
            return None
        return self._original_words.copy()

    @property
    def payload_bits_as_int(self) -> int:
        """Return the logical payload bits as a single integer."""

        return self._payload_bits_as_int

    @property
    def payload_bit_length(self) -> int:
        """Return the number of valid payload bits."""

        return self._payload_bit_length

    @property
    def payload_words(self) -> UInt32Array:
        """Return the transmitted payload words derived from the logical payload."""

        words, _ = TransportPacketConverter.payload_bits_to_words(
            payload_bits_as_int=self._payload_bits_as_int,
            payload_bit_length=self._payload_bit_length,
        )
        return words

    @property
    def payload_bytes(self) -> bytes:
        """Return the logical payload bytes with no transmitted padding bits.

        For payloads that are not byte aligned, the payload occupies the least
        significant bits of the final byte. For example, a 5-bit payload value of
        ``0b10101`` is returned as ``b"\x15"``.
        """

        if self._payload_bit_length == 0:
            return b""

        payload_byte_length = (self._payload_bit_length + 7) // 8
        return self._payload_bits_as_int.to_bytes(payload_byte_length, byteorder="big")

    @staticmethod
    def compute_padding_length_bits(payload_bit_length: int) -> int:
        """Return the transmitted zero-padding length required for a payload.

        Payloads are padded to a whole number of 32-bit words. The current
        header layout exposes five bits for the padding length field, so
        the result must fit in the range 0..31. With this layout, any payload
        padded to a whole number of 32-bit words is representable.
        """

        TransportPacketValidator.validate_non_negative_int(
            payload_bit_length, "payload_bit_length"
        )

        if payload_bit_length == 0:
            return 0

        padded_bit_length = ((payload_bit_length + 31) // 32) * 32
        padding_length_bits = padded_bit_length - payload_bit_length

        return padding_length_bits

    @classmethod
    def build(
        cls,
        *,
        sequence_number: int,
        acknowledgement_number: int,
        payload_bits_as_int: int,
        payload_bit_length: int,
        source_bit: int,
        ack_bit: int,
        rst_bit: int,
        syn_bit: int,
        fin_bit: int,
        current_state: StateValue,
        change_state_flag: StateChangeValue,
        state_change_ack: int,
        reserved: int,
        window_size: int,
        checksum: int = 0,
    ) -> "TransportPacket":
        """Build a packet from logical payload bits and header fields.

        This is the primary construction path for new packets. It calculates
        ``padding_length_bits`` automatically from the logical payload length so
        the header and payload cannot silently drift out of sync.

        :param sequence_number: 32-bit sequence number.
        :param acknowledgement_number: 32-bit acknowledgement number.
        :param payload_bits_as_int: Logical payload represented as an integer.
        :param payload_bit_length: Number of valid payload bits.
        :param source_bit: Source selector bit.
        :param ack_bit: ACK flag.
        :param rst_bit: RST flag.
        :param syn_bit: SYN flag.
        :param fin_bit: FIN flag.
        :param current_state: Current state or enum.
        :param change_state_flag: Requested state change or enum.
        :param state_change_ack: State-change acknowledgement bit.
        :param reserved: 15-bit reserved field.
        :param window_size: 16-bit window size.
        :param checksum: 16-bit checksum. Left explicit for now until the
            checksum algorithm is defined.
        :return: Newly constructed packet.
        """

        TransportPacketValidator.validate_payload_bits(
            payload_bits_as_int=payload_bits_as_int,
            payload_bit_length=payload_bit_length,
        )

        header = TransportPacketHeader(
            sequence_number=sequence_number,
            acknowledgement_number=acknowledgement_number,
            padding_length_bits=cls.compute_padding_length_bits(payload_bit_length),
            source_bit=source_bit,
            ack_bit=ack_bit,
            rst_bit=rst_bit,
            syn_bit=syn_bit,
            fin_bit=fin_bit,
            current_state=current_state,
            change_state_flag=change_state_flag,
            state_change_ack=state_change_ack,
            reserved=reserved,
            window_size=window_size,
            checksum=checksum,
        )

        return cls(
            header=header,
            payload_bits_as_int=payload_bits_as_int,
            payload_bit_length=payload_bit_length,
        )

    @classmethod
    def from_words(cls, words: UInt32Array) -> "TransportPacket":
        """Decode a packet from a raw ``np.uint32`` word array."""

        TransportPacketValidator.validate_words_array(words)

        if words.size < cls.HEADER_WORD_COUNT:
            raise ValueError("TransportPacket must contain at least 4 header words")

        header = TransportPacketHeader.from_words(words[: cls.HEADER_WORD_COUNT])
        payload_words = words[cls.HEADER_WORD_COUNT :].copy()
        payload_bytes_padded = TransportPacketConverter.words_to_bytes(payload_words)

        total_payload_bits = len(payload_bytes_padded) * 8
        padding_length_bits = header.padding_length_bits

        if padding_length_bits > total_payload_bits:
            raise ValueError("Padding length exceeds payload size")

        payload_bit_length = total_payload_bits - padding_length_bits

        if total_payload_bits == 0:
            payload_bits_as_int = 0
        else:
            padded_payload_value = int.from_bytes(payload_bytes_padded, byteorder="big")
            payload_bits_as_int = padded_payload_value >> padding_length_bits

        return cls(
            header=header,
            payload_bits_as_int=payload_bits_as_int,
            payload_bit_length=payload_bit_length,
            original_words=words,
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "TransportPacket":
        """Decode a packet from raw big-endian bytes."""

        words = TransportPacketConverter.bytes_to_words(data)
        return cls.from_words(words)

    def to_words(self) -> UInt32Array:
        """Serialise the complete packet to words.

        The payload words are always derived from the logical payload and the
        header is re-validated before packing. This prevents stale payload words
        from being reused after any header manipulation.
        """

        header_words = self.header.to_words()
        return np.concatenate((header_words, self.payload_words))

    def to_bytes(self) -> bytes:
        """Serialise the complete packet to big-endian bytes."""

        return TransportPacketConverter.words_to_bytes(self.to_words())

    def get_payload_bits(self, start_bit: int, bit_count: int) -> int:
        """Return a slice of the logical payload as an integer.

        Bit numbering is big-endian across the logical payload. Bit 0 is the
        most significant logical payload bit and increasing indices move toward
        the least significant bit.

        Example for payload ``0b110101`` with length 6:

        - ``get_payload_bits(0, 3)`` returns ``0b110``
        - ``get_payload_bits(3, 3)`` returns ``0b101``

        :param start_bit: Start index in the logical payload bit stream.
        :param bit_count: Number of bits to extract.
        :return: Requested payload slice as an integer.
        """

        TransportPacketValidator.validate_non_negative_int(start_bit, "start_bit")
        TransportPacketValidator.validate_non_negative_int(bit_count, "bit_count")

        if start_bit + bit_count > self._payload_bit_length:
            raise ValueError("Requested payload bit slice exceeds payload length")

        if bit_count == 0:
            return 0

        shift_amount = self._payload_bit_length - (start_bit + bit_count)
        mask = (1 << bit_count) - 1
        return (self._payload_bits_as_int >> shift_amount) & mask

    @staticmethod
    def compute_checksum(_: bytes) -> int:
        """Compute a packet checksum.

        The wire-format checksum field already exists, but the actual algorithm
        has not been defined yet. This stub makes the public API explicit now so
        later implementation work does not require reshaping the packet model.
        """

        raise NotImplementedError("Checksum algorithm has not been implemented yet")

    def verify_checksum(self) -> bool:
        """Verify the packet checksum against the current packet bytes."""

        computed_checksum = self.compute_checksum(self.to_bytes())
        return computed_checksum == self.header.checksum

    def __repr__(self) -> str:
        """Return a debug-friendly representation of the packet."""

        return (
            "TransportPacket("
            f"header={self.header!r}, "
            f"payload_words={self.payload_words.tolist()}, "
            f"payload_bytes={self.payload_bytes!r}, "
            f"payload_bit_length={self.payload_bit_length}"
            ")"
        )


if __name__ == "__main__":
    example_packet = TransportPacket.build(
        sequence_number=0x12345678,
        acknowledgement_number=0x9ABCDEF0,
        payload_bits_as_int=int.from_bytes(b"Hello", byteorder="big"),
        payload_bit_length=40,
        source_bit=1,
        ack_bit=0,
        rst_bit=0,
        syn_bit=0,
        fin_bit=0,
        current_state=TransportPacketState.VALUE_0,
        change_state_flag=TransportStateChangeFlag.VALUE_0,
        state_change_ack=1,
        reserved=0,
        window_size=0x0040,
        checksum=0x00FF,
    )

    print(example_packet.header)
    print(example_packet.payload_words)
    print(example_packet.payload_bytes)
    print(example_packet)
