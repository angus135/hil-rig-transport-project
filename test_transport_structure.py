"""Unit tests for ``transport_structure.py``."""

import unittest

import numpy as np

from transport_structure import (
    TransportPacket,
    TransportPacketHeader,
    TransportPacketState,
    TransportStateChangeFlag,
)


class TransportPacketTests(unittest.TestCase):
    """Exercise packet build, parse, and validation behaviour."""

    def test_build_round_trip_for_non_byte_aligned_payload(self) -> None:
        """A packet built from logical payload bits should round-trip cleanly."""

        packet = TransportPacket.build(
            sequence_number=1,
            acknowledgement_number=2,
            payload_bits_as_int=0b10101101101101011,
            payload_bit_length=17,
            source_bit=1,
            ack_bit=1,
            rst_bit=0,
            syn_bit=1,
            fin_bit=0,
            current_state=TransportPacketState.VALUE_2,
            change_state_flag=TransportStateChangeFlag.VALUE_5,
            state_change_ack=0,
            reserved=0x55AA,
            window_size=0x1234,
            checksum=0xBEEF,
        )

        self.assertEqual(packet.header.padding_length_bits, 15)
        decoded = TransportPacket.from_words(packet.to_words())

        self.assertEqual(decoded.payload_bits_as_int, 0b10101101101101011)
        self.assertEqual(decoded.payload_bit_length, 17)
        self.assertEqual(decoded.header.padding_length_bits, 15)
        np.testing.assert_array_equal(decoded.to_words(), packet.to_words())

    def test_payload_bytes_are_derived_from_single_source_of_truth(self) -> None:
        """Derived byte view should match the logical payload bits."""

        packet = TransportPacket.build(
            sequence_number=0,
            acknowledgement_number=0,
            payload_bits_as_int=0xABCDE,
            payload_bit_length=20,
            source_bit=0,
            ack_bit=0,
            rst_bit=0,
            syn_bit=0,
            fin_bit=0,
            current_state=TransportPacketState.VALUE_0,
            change_state_flag=TransportStateChangeFlag.VALUE_0,
            state_change_ack=0,
            reserved=0,
            window_size=0,
            checksum=0,
        )

        self.assertEqual(packet.payload_bytes, b"\x0A\xBC\xDE")
        self.assertEqual(packet.payload_words.tolist(), [0xABCDE000])

    def test_get_payload_bits_uses_big_endian_bit_indices(self) -> None:
        """Bit slices should align with on-wire logical bit ordering."""

        packet = TransportPacket.build(
            sequence_number=0,
            acknowledgement_number=0,
            payload_bits_as_int=0b110101011001001011,
            payload_bit_length=18,
            source_bit=0,
            ack_bit=0,
            rst_bit=0,
            syn_bit=0,
            fin_bit=0,
            current_state=TransportPacketState.VALUE_0,
            change_state_flag=TransportStateChangeFlag.VALUE_0,
            state_change_ack=0,
            reserved=0,
            window_size=0,
            checksum=0,
        )

        self.assertEqual(packet.get_payload_bits(0, 3), 0b110)
        self.assertEqual(packet.get_payload_bits(3, 3), 0b101)
        self.assertEqual(packet.get_payload_bits(1, 4), 0b1010)
        self.assertEqual(packet.get_payload_bits(6, 6), 0b011001)

    def test_header_validation_occurs_during_construction(self) -> None:
        """Invalid header values should be rejected immediately."""

        with self.assertRaisesRegex(ValueError, "range 0..31"):
            TransportPacketHeader(
                sequence_number=0,
                acknowledgement_number=0,
                padding_length_bits=32,
                source_bit=0,
                ack_bit=0,
                rst_bit=0,
                syn_bit=0,
                fin_bit=0,
                current_state=TransportPacketState.VALUE_0,
                change_state_flag=TransportStateChangeFlag.VALUE_0,
                state_change_ack=0,
                reserved=0,
                window_size=0,
                checksum=0,
            )

    def test_packet_constructor_rejects_header_payload_mismatch(self) -> None:
        """Manual construction should fail if header padding and payload disagree."""

        header = TransportPacketHeader(
            sequence_number=0,
            acknowledgement_number=0,
            padding_length_bits=5,
            source_bit=0,
            ack_bit=0,
            rst_bit=0,
            syn_bit=0,
            fin_bit=0,
            current_state=TransportPacketState.VALUE_0,
            change_state_flag=TransportStateChangeFlag.VALUE_0,
            state_change_ack=0,
            reserved=0,
            window_size=0,
            checksum=0,
        )

        with self.assertRaisesRegex(ValueError, "does not match payload_bit_length"):
            TransportPacket(
                header=header,
                payload_bits_as_int=0x0ABCDEF,
                payload_bit_length=28,
            )

    def test_from_words_preserves_original_words_copy(self) -> None:
        """Decoded packets should expose a defensive copy of original words."""

        packet = TransportPacket.build(
            sequence_number=0x11111111,
            acknowledgement_number=0x22222222,
            payload_bits_as_int=0x1ABCD,
            payload_bit_length=17,
            source_bit=1,
            ack_bit=0,
            rst_bit=0,
            syn_bit=0,
            fin_bit=1,
            current_state=TransportPacketState.VALUE_3,
            change_state_flag=TransportStateChangeFlag.VALUE_4,
            state_change_ack=1,
            reserved=0x1234,
            window_size=0x4567,
            checksum=0x89AB,
        )

        words = packet.to_words()
        decoded = TransportPacket.from_words(words)
        original_words = decoded.original_words
        self.assertIsNotNone(original_words)
        np.testing.assert_array_equal(original_words, words)
        original_words[0] = np.uint32(0)
        self.assertNotEqual(int(decoded.original_words[0]), 0)


    def test_build_supports_full_five_bit_padding_range(self) -> None:
        """A 1-bit payload should now be representable with 31 padding bits."""

        packet = TransportPacket.build(
            sequence_number=3,
            acknowledgement_number=4,
            payload_bits_as_int=0b1,
            payload_bit_length=1,
            source_bit=1,
            ack_bit=0,
            rst_bit=0,
            syn_bit=0,
            fin_bit=0,
            current_state=TransportPacketState.VALUE_1,
            change_state_flag=TransportStateChangeFlag.VALUE_2,
            state_change_ack=1,
            reserved=0x1234,
            window_size=0x5678,
            checksum=0x9ABC,
        )

        self.assertEqual(packet.header.padding_length_bits, 31)
        decoded = TransportPacket.from_words(packet.to_words())
        self.assertEqual(decoded.payload_bits_as_int, 1)
        self.assertEqual(decoded.payload_bit_length, 1)
        self.assertEqual(decoded.header.padding_length_bits, 31)

    def test_reserved_field_is_limited_to_fifteen_bits(self) -> None:
        """The reserved field should reject values that need more than 15 bits."""

        with self.assertRaisesRegex(ValueError, "reserved must fit in 15 bits"):
            TransportPacketHeader(
                sequence_number=0,
                acknowledgement_number=0,
                padding_length_bits=0,
                source_bit=0,
                ack_bit=0,
                rst_bit=0,
                syn_bit=0,
                fin_bit=0,
                current_state=TransportPacketState.VALUE_0,
                change_state_flag=TransportStateChangeFlag.VALUE_0,
                state_change_ack=0,
                reserved=0x8000,
                window_size=0,
                checksum=0,
            )

    def test_compute_checksum_stub_is_explicit(self) -> None:
        """Checksum verification should clearly indicate missing implementation."""

        packet = TransportPacket.build(
            sequence_number=0,
            acknowledgement_number=0,
            payload_bits_as_int=0,
            payload_bit_length=0,
            source_bit=0,
            ack_bit=0,
            rst_bit=0,
            syn_bit=0,
            fin_bit=0,
            current_state=TransportPacketState.VALUE_0,
            change_state_flag=TransportStateChangeFlag.VALUE_0,
            state_change_ack=0,
            reserved=0,
            window_size=0,
            checksum=0,
        )

        with self.assertRaises(NotImplementedError):
            packet.verify_checksum()


if __name__ == "__main__":
    unittest.main()
