# HIL-RIG Protocol Simulation Layer

This module implements a stateful protocol layer above `transport_structure.py`.
It does not work with raw bytes, COBS framing, sockets, serial ports, or NumPy
word arrays directly. Instead, `HostDevice` and `RigDevice` exchange already-built
`TransportPacket` objects.

The goal is to make protocol behaviour easy to test and compare for assessment
work. A test or simulation can choose to pass packets normally, drop packets,
delay packets, or mutate packet fields to model corruption.

---

## File layout

```text
transport_structure.py
    Packet/header representation and bit-level structure.

protocol.py
    Stateful host/rig protocol behaviour using TransportPacket objects.

test_protocol.py
    Unit tests for state changes, keep-alives, acknowledgements, and faults.
```

---

## Main classes

## `ProtocolDevice`

Base class shared by the host and rig.

Responsibilities:

- store the local protocol state
- build `TransportPacket` objects
- track sequence and acknowledgement numbers
- track the last sent and received timestamps
- track keep-alive timeouts
- track pending state-change acknowledgements
- log protocol events
- count useful protocol statistics
- enter `FAULT` when timeout rules fail

You normally instantiate `HostDevice` or `RigDevice`, not `ProtocolDevice`
directly.

---

## `HostDevice`

Represents the external host.

Main responsibilities:

- request configuration start
- send configuration payload packets
- signal configuration completion
- send an execute signal
- receive state-change notifications from the rig
- acknowledge rig state changes
- receive reporting/result packets
- confirm reporting completion

Important methods:

```python
host.start_configuration(timestamp_ms)
host.send_configuration_packet(config_payload, config_payload_bit_length, timestamp_ms)
host.finish_configuration(timestamp_ms)
host.send_execute_signal(timestamp_ms)
host.confirm_result_transfer_complete(timestamp_ms)
host.receive_packet(packet, timestamp_ms)
host.tick(timestamp_ms)
```

---

## `RigDevice`

Represents the HIL-RIG.

Main responsibilities:

- start in `IDLE`
- move to `CONFIGURING` when requested by the host
- accept simulated configuration packets
- move to `ARMED` when configuration is complete
- move to `RUNNING` when an execute signal is received
- move to `REPORTING` when the simulated test completes
- send queued result payloads
- return to `IDLE` when reporting is acknowledged
- enter `FAULT` on protocol-level errors/timeouts

Important methods:

```python
rig.receive_packet(packet, timestamp_ms)
rig.accept_configuration_packet(packet, timestamp_ms)
rig.complete_configuration(timestamp_ms)
rig.receive_execute_signal(packet, timestamp_ms)
rig.complete_test(timestamp_ms)
rig.queue_result_payload(payload_bits_as_int, payload_bit_length)
rig.send_result_packet(timestamp_ms)
rig.reset(timestamp_ms)
rig.tick(timestamp_ms)
```

---

## Support data classes

## `ProtocolConfig`

Holds protocol timing and retry configuration.

Example:

```python
from protocol import ProtocolConfig

config = ProtocolConfig(
    keep_alive_interval_ms=500,
    keep_alive_timeout_ms=1500,
    state_ack_timeout_ms=500,
    max_retries=3,
    default_host_window_size=1024,
    default_rig_window_size=256,
    running_window_size=1,
    fault_window_size=16,
)
```

All time values are in milliseconds. The simulation or unit test supplies the
current timestamp explicitly.

## `ProtocolEvent`

A timestamped log entry produced by a device. Events are stored in
`device.event_log`.

## `ProtocolStats`

Counters that help compare protocol behaviour across scenarios. Examples:

- packets sent
- packets received
- packets rejected
- retransmissions
- keep-alive packets sent/received
- keep-alive timeouts
- faults entered

## `PacketDeliveryResult`

Returned by `receive_packet()`.

Fields:

```python
accepted: bool
reason: str
response_packets: list[TransportPacket]
events: list[ProtocolEvent]
```

---

## Typical packet flow

The caller manually passes packets between the devices:

```python
from protocol import HostDevice, RigDevice, ProtocolConfig

config = ProtocolConfig()
host = HostDevice(config)
rig = RigDevice(config)

# Host asks the rig to enter CONFIGURING.
pkt = host.start_configuration(timestamp_ms=0)
rig_result = rig.receive_packet(pkt, timestamp_ms=10)

# Deliver rig responses back to the host.
for response in rig_result.response_packets:
    host.receive_packet(response, timestamp_ms=20)

# Host sends configuration data.
cfg = host.send_configuration_packet(
    config_payload=0b101101,
    config_payload_bit_length=6,
    timestamp_ms=30,
)
rig.receive_packet(cfg, timestamp_ms=40)

# Host finishes configuration.
finish = host.finish_configuration(timestamp_ms=50)
rig_result = rig.receive_packet(finish, timestamp_ms=60)
```

The devices do not deliver packets automatically. This is intentional. It lets a
unit test or simulation decide exactly what happens to each packet.

---

## Simulating dropped packets

To drop a packet, simply do not call `receive_packet()` on the receiver.

```python
pkt = host.start_configuration(timestamp_ms=0)

# Packet is dropped here, so rig.receive_packet(pkt, ...) is not called.

# Time passes. The host still expects a state-change acknowledgement.
outgoing = host.tick(timestamp_ms=600)
```

Depending on `ProtocolConfig`, `tick()` may retransmit the state-change packet or
enter `FAULT` after retry exhaustion.

---

## Simulating disconnection

Do not deliver packets for longer than `keep_alive_timeout_ms`, then call
`tick()`.

```python
host.connected = True
host.last_packet_received_timestamp_ms = 0

outgoing = host.tick(timestamp_ms=2000)

assert host.state.name == "FAULT"
```

This models a connection that has gone silent.

---

## Simulating corruption

Because this layer does not work with raw bytes, corruption is modelled by
mutating the packet object or creating a packet with inconsistent protocol
fields before delivery.

Examples of detectable corruption:

- wrong `source_bit`
- stale or duplicate `sequence_number`
- acknowledgement number ahead of packets actually sent
- unexpected state transition

Example:

```python
pkt = host.send_keep_alive(timestamp_ms=0)

# Delivering this packet back to the host is invalid because the source bit says
# it came from the host, not the rig.
result = host.receive_packet(pkt, timestamp_ms=10)

assert not result.accepted
```

---

## State-change handling

The `TransportPacket` header contains:

- `current_state`
- `change_state_flag`
- `state_change_ack`

The protocol layer uses these fields as follows:

- `request_state_change(...)` updates the local state and sends a packet with
  `change_state_flag` set to the new state.
- The receiver may acknowledge this with `state_change_ack = 1`.
- The sender tracks the pending state change until the acknowledgement arrives.
- If the acknowledgement is dropped, `tick()` can retransmit the state-change
  packet.
- If retries are exhausted, the device enters `FAULT`.

For ordinary packets, the protocol layer treats `TransportStateChangeFlag.IDLE`
as the neutral/no-state-change value. Explicit reset and reporting-complete
behaviour are handled through dedicated methods.

---

## Keep-alive handling

The updated header has a dedicated `keep_alive_bit`. The protocol layer uses it
for connection liveness simulation.

- `send_keep_alive(timestamp_ms)` creates a packet with `keep_alive_bit = 1`.
- `receive_packet(...)` records when a keep-alive is received.
- `tick(timestamp_ms)` checks whether the peer has gone silent.
- If the timeout is exceeded, the device can enter `FAULT`.

---

## Window size behaviour

`ProtocolDevice.get_window_size()` chooses the advertised window based on the
current state:

- `RUNNING` uses `running_window_size`, normally very small.
- `FAULT` uses `fault_window_size`.
- Host uses `default_host_window_size` in normal states.
- Rig uses `default_rig_window_size` in normal states.

This gives the assessment a simple way to compare how the protocol behaves when
some states intentionally restrict traffic.

---

## Running the tests

From the directory containing the files:

```bash
python -m unittest test_protocol.py
```

The tests cover:

- configuration start and acknowledgement
- configuration payload handling
- transition to `ARMED`
- execute signal and transition to `RUNNING`
- reporting/result transfer
- keep-alive generation
- keep-alive timeout to `FAULT`
- dropped state acknowledgement retransmission
- corrupted source-bit rejection
- duplicate sequence-number rejection
