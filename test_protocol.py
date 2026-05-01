"""Unit tests for the stateful protocol simulation layer."""

import unittest

from protocol import HostDevice, ProtocolConfig, RigDevice
from transport_structure import TransportPacketState, TransportStateChangeFlag


class ProtocolDeviceTests(unittest.TestCase):
    """Exercise host/rig state changes, keep-alives, and fault scenarios."""

    def make_devices(self):
        config = ProtocolConfig(
            keep_alive_interval_ms=100,
            keep_alive_timeout_ms=300,
            state_ack_timeout_ms=100,
            max_retries=2,
            default_host_window_size=1024,
            default_rig_window_size=128,
            running_window_size=1,
            fault_window_size=16,
        )
        return HostDevice(config), RigDevice(config)

    def test_host_can_start_configuration_and_rig_acknowledges(self):
        host, rig = self.make_devices()

        request = host.start_configuration(timestamp_ms=0)
        self.assertEqual(request.header.current_state, TransportPacketState.CONFIGURING)
        self.assertEqual(request.header.change_state_flag, TransportStateChangeFlag.CONFIGURING)

        result = rig.receive_packet(request, timestamp_ms=10)

        self.assertTrue(result.accepted)
        self.assertEqual(rig.state, TransportPacketState.CONFIGURING)
        self.assertGreaterEqual(len(result.response_packets), 2)
        self.assertTrue(any(p.header.state_change_ack for p in result.response_packets))

        ack_packet = next(p for p in result.response_packets if p.header.state_change_ack)
        host.receive_packet(ack_packet, timestamp_ms=20)
        self.assertIsNone(host.pending_state_change)

    def test_configuration_payload_and_finish_moves_rig_to_armed(self):
        host, rig = self.make_devices()

        start = host.start_configuration(timestamp_ms=0)
        rig_responses = rig.receive_packet(start, timestamp_ms=10).response_packets
        for packet in rig_responses:
            host.receive_packet(packet, timestamp_ms=20)

        config_packet = host.send_configuration_packet(
            config_payload=0b101101,
            config_payload_bit_length=6,
            timestamp_ms=30,
        )
        rig.receive_packet(config_packet, timestamp_ms=40)
        self.assertEqual(rig.configuration_packets_received, 1)
        self.assertTrue(rig.configuration_valid)

        finish_packet = host.finish_configuration(timestamp_ms=50)
        finish_result = rig.receive_packet(finish_packet, timestamp_ms=60)

        self.assertEqual(rig.state, TransportPacketState.ARMED)
        self.assertEqual(len(finish_result.response_packets), 1)
        self.assertEqual(
            finish_result.response_packets[0].header.current_state,
            TransportPacketState.ARMED,
        )

    def test_execute_signal_moves_rig_to_running(self):
        host, rig = self.make_devices()
        rig.state = TransportPacketState.ARMED
        host.rig_state_view = TransportPacketState.ARMED

        execute = host.send_execute_signal(timestamp_ms=100)
        result = rig.receive_packet(execute, timestamp_ms=110)

        self.assertTrue(result.accepted)
        self.assertEqual(rig.state, TransportPacketState.RUNNING)
        self.assertEqual(result.response_packets[0].header.current_state, TransportPacketState.RUNNING)
        self.assertEqual(result.response_packets[0].header.window_size, 1)

    def test_complete_test_reporting_and_result_ack_flow(self):
        host, rig = self.make_devices()
        rig.state = TransportPacketState.RUNNING
        rig.queue_result_payload(0xABCD, 16)

        reporting_notice = rig.complete_test(timestamp_ms=200)
        self.assertEqual(rig.state, TransportPacketState.REPORTING)
        host_responses = host.receive_packet(reporting_notice, timestamp_ms=210).response_packets
        self.assertTrue(any(p.header.state_change_ack for p in host_responses))

        result_packet = rig.send_result_packet(timestamp_ms=220)
        self.assertIsNotNone(result_packet)
        host.receive_packet(result_packet, timestamp_ms=230)

        self.assertEqual(host.result_packets_received, 1)
        self.assertEqual(host.received_result_payloads[0], (0xABCD, 16))

        ok_packet = host.confirm_result_transfer_complete(timestamp_ms=240)
        rig_response = rig.receive_packet(ok_packet, timestamp_ms=250).response_packets

        self.assertEqual(rig.state, TransportPacketState.IDLE)
        self.assertEqual(rig_response[0].header.current_state, TransportPacketState.IDLE)

    def test_tick_sends_keep_alive_after_interval(self):
        host, rig = self.make_devices()
        host.connected = True
        host.last_packet_received_timestamp_ms = 0
        host.last_keep_alive_sent_timestamp_ms = 0

        outgoing = host.tick(timestamp_ms=100)

        self.assertEqual(len(outgoing), 1)
        self.assertEqual(outgoing[0].header.keep_alive_bit, 1)
        self.assertEqual(host.stats.keep_alive_packets_sent, 1)

        result = rig.receive_packet(outgoing[0], timestamp_ms=110)
        self.assertTrue(result.accepted)
        self.assertEqual(rig.stats.keep_alive_packets_received, 1)

    def test_keep_alive_timeout_enters_fault(self):
        host, _ = self.make_devices()
        host.connected = True
        host.last_packet_received_timestamp_ms = 0

        outgoing = host.tick(timestamp_ms=301)

        self.assertEqual(host.state, TransportPacketState.FAULT)
        self.assertTrue(host.faulted)
        self.assertEqual(host.stats.keep_alive_timeouts, 1)
        self.assertEqual(len(outgoing), 1)
        self.assertEqual(outgoing[0].header.current_state, TransportPacketState.FAULT)

    def test_dropped_state_ack_causes_retransmission_then_fault(self):
        host, _ = self.make_devices()

        host.start_configuration(timestamp_ms=0)
        first_tick = host.tick(timestamp_ms=100)
        second_tick = host.tick(timestamp_ms=200)
        third_tick = host.tick(timestamp_ms=300)

        self.assertEqual(len(first_tick), 1)
        self.assertEqual(len(second_tick), 1)
        self.assertEqual(host.stats.retransmissions, 2)
        self.assertEqual(host.state, TransportPacketState.FAULT)
        self.assertEqual(len(third_tick), 1)
        self.assertEqual(third_tick[0].header.current_state, TransportPacketState.FAULT)

    def test_unexpected_source_bit_is_rejected_as_corruption(self):
        host, rig = self.make_devices()

        packet_from_host = host.send_keep_alive(timestamp_ms=0)
        result = host.receive_packet(packet_from_host, timestamp_ms=10)

        self.assertFalse(result.accepted)
        self.assertIn("source bit", result.reason)
        self.assertEqual(host.stats.packets_corrupted_detected, 1)
        self.assertEqual(rig.stats.packets_received, 0)

    def test_duplicate_sequence_number_is_rejected(self):
        host, rig = self.make_devices()

        packet = host.send_keep_alive(timestamp_ms=0)
        first = rig.receive_packet(packet, timestamp_ms=10)
        second = rig.receive_packet(packet, timestamp_ms=20)

        self.assertTrue(first.accepted)
        self.assertFalse(second.accepted)
        self.assertIn("duplicate", second.reason)
        self.assertEqual(rig.stats.packets_dropped_detected, 1)


if __name__ == "__main__":
    unittest.main()
