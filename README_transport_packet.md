# Transport Packet Module README

This module defines the header and packet structure for the HIL-RIG transport protocol.

It intentionally only models the packet format. Protocol behaviour such as state-transition rules, keep-alive timeout handling, state-change acknowledgement sequencing, checksum implementation, retransmission, and application-level actions should live in higher-level protocol code.

The implementation lives in `transport_structure.py`.

---

## What it supports

- Building packets from logical payload bits
- Decoding packets from raw 32-bit words or bytes
- Serialising packets back to words or bytes
- Handling non-byte-aligned payloads
- Slicing payload bits directly
- Validating header fields
- Converting between bytes, words, and payload-bit representations
- Carrying explicit HIL-RIG transport states
- Carrying a keep-alive bit in the header

---

## Quick start

```python
from transport_structure import (
    TransportPacket,
    TransportPacketState,
    TransportStateChangeFlag,
)

packet = TransportPacket.build(
    sequence_number=1,
    acknowledgement_number=2,
    payload_bits_as_int=0b101101,
    payload_bit_length=6,
    source_bit=1,
    ack_bit=1,
    rst_bit=0,
    syn_bit=0,
    fin_bit=0,
    current_state=TransportPacketState.CONFIGURING,
    change_state_flag=TransportStateChangeFlag.ARMED,
    state_change_ack=0,
    keep_alive_bit=1,
    reserved=0,
    window_size=64,
    checksum=0,
)

print(packet)
print(packet.to_words())
print(packet.to_bytes())
print(packet.payload_bytes)
print(packet.get_payload_bits(0, 3))
```

---

## Wire format overview

A packet contains:

- a **4-word header**
- followed by **0 or more payload words**

All words are 32-bit unsigned values.

### Header layout

#### Word 0

| Field | Width |
|---|---:|
| `sequence_number` | 32 bits |

#### Word 1

| Field | Width |
|---|---:|
| `acknowledgement_number` | 32 bits |

#### Word 2

| Field | Width | Bit position |
|---|---:|---|
| `padding_length_bits` | 5 bits | 31..27 |
| `source_bit` | 1 bit | 26 |
| `ack_bit` | 1 bit | 25 |
| `rst_bit` | 1 bit | 24 |
| `syn_bit` | 1 bit | 23 |
| `fin_bit` | 1 bit | 22 |
| `current_state` | 3 bits | 21..19 |
| `change_state_flag` | 3 bits | 18..16 |
| `state_change_ack` | 1 bit | 15 |
| `keep_alive_bit` | 1 bit | 14 |
| `reserved` | 14 bits | 13..0 |

The keep-alive bit comes immediately after `state_change_ack`. It consumes one bit from the previously 15-bit reserved section, so `reserved` is now limited to 14 bits.

#### Word 3

| Field | Width |
|---|---:|
| `window_size` | 16 bits |
| `checksum` | 16 bits |

---

## Transport states

The brainstorm document defines six protocol states. These are represented by the 3-bit `TransportPacketState` enum:

| State | Value | Meaning |
|---|---:|---|
| `TransportPacketState.IDLE` | 0 | HIL-RIG is waiting for instructions from the host |
| `TransportPacketState.CONFIGURING` | 1 | HIL-RIG is receiving, validating, and applying configuration/instructions |
| `TransportPacketState.ARMED` | 2 | HIL-RIG is configured and waiting for an execute signal |
| `TransportPacketState.RUNNING` | 3 | HIL-RIG is applying instructions and recording data |
| `TransportPacketState.REPORTING` | 4 | HIL-RIG is transferring captured results back to the host |
| `TransportPacketState.FAULT` | 5 | A fault has been detected |
| `TransportPacketState.RESERVED_6` | 6 | Reserved |
| `TransportPacketState.RESERVED_7` | 7 | Reserved |

`TransportStateChangeFlag` uses the same 3-bit values. It represents the state value being requested or notified, not the logic for whether that transition is allowed.

The older `VALUE_0` to `VALUE_7` enum names are retained as aliases for compatibility, but new code should use the explicit names above.

---

## Keep-alive bit

`keep_alive_bit` is a single-bit header field. It is included so higher-level protocol code can maintain the connection between the host and HIL-RIG.

This module does not implement keep-alive timing, timeout handling, retries, or fault signalling. It only validates, stores, parses, and serialises the bit.

---

## Payload representation

Internally, the packet stores the payload as:

- `payload_bits_as_int`
- `payload_bit_length`

The transmitted payload is padded with zero bits on the **least significant end** until the payload length becomes a whole number of 32-bit words.

For example, a 17-bit payload is transmitted as:

- 17 real payload bits
- 15 zero padding bits

`padding_length_bits` is calculated automatically when using `TransportPacket.build(...)`.

---

## Main classes

## `TransportPacket`

The main packet class. Use it to build, parse, inspect, and serialise packets.

### `TransportPacket.build(...)`

Builds a packet from logical payload bits and header fields.

```python
packet = TransportPacket.build(
    sequence_number=100,
    acknowledgement_number=50,
    payload_bits_as_int=0b10101101101101011,
    payload_bit_length=17,
    source_bit=1,
    ack_bit=1,
    rst_bit=0,
    syn_bit=1,
    fin_bit=0,
    current_state=TransportPacketState.RUNNING,
    change_state_flag=TransportStateChangeFlag.REPORTING,
    state_change_ack=0,
    keep_alive_bit=1,
    reserved=0x1234,
    window_size=0x0040,
    checksum=0xBEEF,
)

print(packet.header.padding_length_bits)   # 15
print(packet.payload_words)                # transmitted payload words
print(packet.payload_bytes)                # logical payload bytes
```

### `TransportPacket.from_words(words)`

Parses a packet from a NumPy array of `np.uint32` words.

```python
import numpy as np
from transport_structure import TransportPacket

words = np.array(
    [
        0x12345678,
        0x9ABCDEF0,
        0x78004000,
        0x004000FF,
        0x48656C6C,
        0x6F000000,
    ],
    dtype=np.uint32,
)

packet = TransportPacket.from_words(words)

print(packet.header)
print(packet.payload_words)
print(packet.payload_bytes)
print(packet.payload_bit_length)
```

### `TransportPacket.from_bytes(data)`

Parses a packet from raw bytes. The byte string must represent a whole number of 32-bit words.

```python
from transport_structure import TransportPacket

raw = b"\x12\x34\x56\x78" * 4
packet = TransportPacket.from_bytes(raw)
```

### `packet.to_words()`

Serialises the whole packet back into a NumPy `np.uint32` array.

```python
words = packet.to_words()
print(words.dtype)   # uint32
print(words)
```

### `packet.to_bytes()`

Serialises the whole packet to big-endian raw bytes.

```python
raw_bytes = packet.to_bytes()
print(raw_bytes)
```

### `packet.get_payload_bits(start_bit, bit_count)`

Returns a slice of the logical payload.

Bit numbering is big-endian across the logical payload:

- bit `0` is the most significant logical payload bit
- larger indices move toward the least significant end

```python
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
    current_state=TransportPacketState.IDLE,
    change_state_flag=TransportStateChangeFlag.IDLE,
    state_change_ack=0,
    keep_alive_bit=0,
    reserved=0,
    window_size=0,
    checksum=0,
)

print(bin(packet.get_payload_bits(0, 3)))   # 0b110
print(bin(packet.get_payload_bits(3, 3)))   # 0b101
print(bin(packet.get_payload_bits(6, 6)))   # 0b11001 or 0b011001 depending on display context
```

---

## `TransportPacketHeader`

Represents the fixed four-word packet header.

You normally do not need to instantiate this directly when creating a new packet, because `TransportPacket.build(...)` calculates the padding field and creates the header for you.

```python
from transport_structure import (
    TransportPacketHeader,
    TransportPacketState,
    TransportStateChangeFlag,
)

header = TransportPacketHeader(
    sequence_number=1,
    acknowledgement_number=2,
    padding_length_bits=15,
    source_bit=1,
    ack_bit=0,
    rst_bit=0,
    syn_bit=1,
    fin_bit=0,
    current_state=TransportPacketState.ARMED,
    change_state_flag=TransportStateChangeFlag.RUNNING,
    state_change_ack=1,
    keep_alive_bit=1,
    reserved=0x1234,
    window_size=64,
    checksum=0,
)

print(header)
print(header.to_words())
```

The header constructor validates:

- `padding_length_bits` is 0 to 31
- all single-bit fields are 0 or 1
- `current_state` fits in 3 bits
- `change_state_flag` fits in 3 bits
- `reserved` fits in 14 bits
- `window_size` and `checksum` fit in 16 bits

---

## `TransportPacketConverter`

Conversion helpers for lower-level code:

- `words_to_bytes(words)`
- `bytes_to_words(data)`
- `payload_bits_to_words(payload_bits_as_int, payload_bit_length)`
- `payload_bytes_to_words(payload_bytes, padding_length_bits=0)`

---

## `TransportPacketValidator`

Validation helpers used internally by the packet and header classes. They are also available if a caller wants explicit pre-validation.

Important public validators include:

- `validate_words_array(words)`
- `validate_u32_value(value, field_name)`
- `validate_non_negative_int(value, field_name)`
- `validate_bit_value(value, field_name)`
- `validate_payload_bits(payload_bits_as_int, payload_bit_length)`
- `validate_header_fields(header)`

---

## Checksum status

`compute_checksum(...)` and `verify_checksum(...)` are present as API stubs, but the checksum algorithm has not been defined yet.

Calling `verify_checksum()` currently raises `NotImplementedError`.

---

## Minimal end-to-end example

```python
from transport_structure import (
    TransportPacket,
    TransportPacketState,
    TransportStateChangeFlag,
)

outgoing = TransportPacket.build(
    sequence_number=123,
    acknowledgement_number=122,
    payload_bits_as_int=0b1011001110001,
    payload_bit_length=13,
    source_bit=1,
    ack_bit=1,
    rst_bit=0,
    syn_bit=0,
    fin_bit=0,
    current_state=TransportPacketState.CONFIGURING,
    change_state_flag=TransportStateChangeFlag.ARMED,
    state_change_ack=0,
    keep_alive_bit=1,
    reserved=0,
    window_size=32,
    checksum=0,
)

wire_words = outgoing.to_words()
incoming = TransportPacket.from_words(wire_words)

assert incoming.header.sequence_number == 123
assert incoming.header.keep_alive_bit == 1
assert incoming.payload_bits_as_int == 0b1011001110001
assert incoming.payload_bit_length == 13
assert incoming.get_payload_bits(0, 5) == 0b10110

print("Round-trip OK")
```
