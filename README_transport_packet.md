# Transport Packet Module README

This module provides a small packet model for a transport-like protocol stored as a sequence of 32-bit words.

It supports:
- building packets from logical payload bits
- decoding packets from raw words or bytes
- serialising packets back to words or bytes
- handling non-byte-aligned payloads
- slicing payload bits directly
- validating header values
- converting between bytes, words, and payload-bit representations

The implementation lives in `transport_packet_updated.py` .

---

## Quick start

```python
import numpy as np

from transport_packet_updated import (
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
    current_state=TransportPacketState.VALUE_2,
    change_state_flag=TransportStateChangeFlag.VALUE_1,
    state_change_ack=0,
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

### Header layout

#### Word 0
- `sequence_number` (32 bits)

#### Word 1
- `acknowledgement_number` (32 bits)

#### Word 2
- `padding_length_bits` (5 bits, bits 31..27)
- `source_bit` (1 bit)
- `ack_bit` (1 bit)
- `rst_bit` (1 bit)
- `syn_bit` (1 bit)
- `fin_bit` (1 bit)
- `current_state` (3 bits)
- `change_state_flag` (3 bits)
- `state_change_ack` (1 bit)
- `reserved` (15 bits)

#### Word 3
- `window_size` (16 bits)
- `checksum` (16 bits)

### Payload representation

Internally, the packet stores the payload as:
- `payload_bits_as_int`
- `payload_bit_length`

The transmitted payload is padded with zero bits on the **least significant end** until the payload length becomes a whole number of 32 bits.

So if you have a 17-bit payload, the transmitted form contains:
- 17 real payload bits
- 15 zero padding bits

---

## Main classes

## `TransportPacket`

This is the main class you will usually use.

Use it to:
- build new packets
- parse existing packets
- inspect header and payload fields
- serialise packets back to raw words or bytes

### `TransportPacket.build(...)`

Builds a packet from logical payload bits and header fields.

This is the recommended way to create new packets because it automatically calculates `padding_length_bits` so the header and payload stay consistent.

```python
from transport_packet_updated import (
    TransportPacket,
    TransportPacketState,
    TransportStateChangeFlag,
)

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
    current_state=TransportPacketState.VALUE_2,
    change_state_flag=TransportStateChangeFlag.VALUE_5,
    state_change_ack=0,
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
from transport_packet_updated import TransportPacket

words = np.array(
    [
        0x12345678,
        0x9ABCDEF0,
        0x78000000,
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

Parses a packet from raw bytes.

The byte string must represent a whole number of 32-bit words.

```python
from transport_packet_updated import TransportPacket

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

Bit numbering is **big-endian across the logical payload**:
- bit `0` is the most significant logical payload bit
- larger indices move toward the least significant end

Example:

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
    current_state=0,
    change_state_flag=0,
    state_change_ack=0,
    reserved=0,
    window_size=0,
    checksum=0,
)

print(bin(packet.get_payload_bits(0, 3)))   # 0b110
print(bin(packet.get_payload_bits(3, 3)))   # 0b101
print(bin(packet.get_payload_bits(6, 6)))   # 0b11001 or 0b011001 depending on display context
```

### `TransportPacket.compute_padding_length_bits(payload_bit_length)`

Returns how many zero padding bits are needed to pad a logical payload to a whole number of 32-bit words.

```python
from transport_packet_updated import TransportPacket

print(TransportPacket.compute_padding_length_bits(0))    # 0
print(TransportPacket.compute_padding_length_bits(1))    # 31
print(TransportPacket.compute_padding_length_bits(17))   # 15
print(TransportPacket.compute_padding_length_bits(32))   # 0
print(TransportPacket.compute_padding_length_bits(33))   # 31
```

### `packet.payload_bits_as_int`

Returns the logical payload as an integer.

```python
print(packet.payload_bits_as_int)
print(bin(packet.payload_bits_as_int))
```

### `packet.payload_bit_length`

Returns the number of valid payload bits.

```python
print(packet.payload_bit_length)
```

### `packet.payload_words`

Returns the **transmitted** payload words, including any required zero padding at the least significant end.

```python
print(packet.payload_words)
```

### `packet.payload_bytes`

Returns the **logical** payload bytes without transmitted padding bits.

For non-byte-aligned payloads, the payload occupies the least significant bits of the final byte.

Example:

```python
packet = TransportPacket.build(
    sequence_number=0,
    acknowledgement_number=0,
    payload_bits_as_int=0b10101,
    payload_bit_length=5,
    source_bit=0,
    ack_bit=0,
    rst_bit=0,
    syn_bit=0,
    fin_bit=0,
    current_state=0,
    change_state_flag=0,
    state_change_ack=0,
    reserved=0,
    window_size=0,
    checksum=0,
)

print(packet.payload_bytes)   # b'\x15'
```

### `packet.original_words`

If the packet was created using `from_words(...)` or `from_bytes(...)`, this returns a defensive copy of the original decoded word array.

If the packet was created with `build(...)`, this returns `None`.

```python
decoded = TransportPacket.from_words(packet.to_words())
print(decoded.original_words)
```

### `packet.verify_checksum()`

This exists as part of the public API, but it is currently **not implemented** because the checksum algorithm has not been defined yet.

```python
try:
    packet.verify_checksum()
except NotImplementedError as exc:
    print(exc)
```

## `TransportPacketHeader`

Represents the fixed four-word packet header.

You normally do not need to instantiate this directly when creating a new packet, because `TransportPacket.build(...)` does it for you.

You may still use it directly if you need manual control.

### `TransportPacketHeader(...)`

Constructs a header and validates all fields immediately.

```python
from transport_packet_updated import TransportPacketHeader

header = TransportPacketHeader(
    sequence_number=1,
    acknowledgement_number=2,
    padding_length_bits=15,
    source_bit=1,
    ack_bit=0,
    rst_bit=0,
    syn_bit=1,
    fin_bit=0,
    current_state=0,
    change_state_flag=0,
    state_change_ack=1,
    reserved=0x1234,
    window_size=64,
    checksum=0,
)

print(header)
```

### `TransportPacketHeader.from_words(words)`

Parses the first four words of a packet into a header.

```python
import numpy as np
from transport_packet_updated import TransportPacketHeader

header_words = np.array(
    [0x12345678, 0x9ABCDEF0, 0x78001234, 0x004000FF],
    dtype=np.uint32,
)

header = TransportPacketHeader.from_words(header_words)
print(header.sequence_number)
print(header.window_size)
print(header.checksum)
```

### `header.to_words()`

Serialises the header back to four `np.uint32` words.

```python
header_words = header.to_words()
print(header_words)
```

---

## `TransportPacketConverter`

This class contains conversion helpers.

These are useful when you want to work at a slightly lower level than `TransportPacket`.

### `TransportPacketConverter.words_to_bytes(words)`

Converts a `np.uint32` array into big-endian bytes.

```python
import numpy as np
from transport_packet_updated import TransportPacketConverter

words = np.array([0x12345678, 0x9ABCDEF0], dtype=np.uint32)
raw = TransportPacketConverter.words_to_bytes(words)
print(raw)   # b'\x124Vx\x9a\xbc\xde\xf0'
```

### `TransportPacketConverter.bytes_to_words(data)`

Converts big-endian bytes into a `np.uint32` array.

The byte length must be a multiple of 4.

```python
from transport_packet_updated import TransportPacketConverter

raw = b"\x12\x34\x56\x78\x9A\xBC\xDE\xF0"
words = TransportPacketConverter.bytes_to_words(raw)
print(words)
```

### `TransportPacketConverter.payload_bits_to_words(payload_bits_as_int, payload_bit_length)`

Converts logical payload bits into transmitted payload words.

Returns:
- `payload_words`
- `padding_length_bits`

This is useful if you want to inspect how a logical payload will appear on the wire.

```python
from transport_packet_updated import TransportPacketConverter

words, padding = TransportPacketConverter.payload_bits_to_words(
    payload_bits_as_int=0b101011,
    payload_bit_length=6,
)

print(words)
print(padding)   # 26
```

### `TransportPacketConverter.payload_bytes_to_words(payload_bytes, padding_length_bits=0)`

Converts byte-aligned payload bytes into transmitted words, with optional extra padding bits.

This helper is more limited than `payload_bits_to_words(...)` because it assumes you are starting from bytes.

```python
from transport_packet_updated import TransportPacketConverter

words = TransportPacketConverter.payload_bytes_to_words(
    payload_bytes=b"Hi",
    padding_length_bits=16,
)

print(words)
```

---

## `TransportPacketValidator`

This class contains validation helpers.

In most normal usage, you will not call these directly because validation already happens inside the packet and header constructors.

They are still useful if you want explicit validation in your own code.

### `TransportPacketValidator.validate_words_array(words)`

Checks that `words` is:
- a NumPy array
- one-dimensional
- `dtype=np.uint32`

```python
import numpy as np
from transport_packet_updated import TransportPacketValidator

words = np.array([1, 2, 3], dtype=np.uint32)
TransportPacketValidator.validate_words_array(words)
```

### `TransportPacketValidator.validate_u32_value(value, field_name)`

Checks that a value fits in an unsigned 32-bit integer.

```python
from transport_packet_updated import TransportPacketValidator

TransportPacketValidator.validate_u32_value(123, "sequence_number")
```

### `TransportPacketValidator.validate_non_negative_int(value, field_name)`

Checks that a value is an integer and is not negative.

```python
from transport_packet_updated import TransportPacketValidator

TransportPacketValidator.validate_non_negative_int(5, "payload_bit_length")
```

### `TransportPacketValidator.validate_bit_value(value, field_name)`

Checks that a field is either `0` or `1`.

```python
from transport_packet_updated import TransportPacketValidator

TransportPacketValidator.validate_bit_value(1, "ack_bit")
```

### `TransportPacketValidator.validate_payload_bits(payload_bits_as_int, payload_bit_length)`

Checks that:
- `payload_bit_length >= 0`
- `payload_bits_as_int >= 0`
- the payload fits within the specified bit length
- if `payload_bit_length == 0`, then `payload_bits_as_int` must be `0`

```python
from transport_packet_updated import TransportPacketValidator

TransportPacketValidator.validate_payload_bits(
    payload_bits_as_int=0b10101,
    payload_bit_length=5,
)
```

### `TransportPacketValidator.validate_header_fields(header)`

Checks that a `TransportPacketHeader` instance fits the wire format.

```python
from transport_packet_updated import TransportPacketHeader, TransportPacketValidator

header = TransportPacketHeader(
    sequence_number=1,
    acknowledgement_number=2,
    padding_length_bits=0,
    source_bit=0,
    ack_bit=0,
    rst_bit=0,
    syn_bit=0,
    fin_bit=0,
    current_state=0,
    change_state_flag=0,
    state_change_ack=0,
    reserved=0,
    window_size=0,
    checksum=0,
)

TransportPacketValidator.validate_header_fields(header)
```

---

## Enums

## `TransportPacketState`

Represents the current 3-bit state field.

Available values:
- `TransportPacketState.VALUE_0`
- `TransportPacketState.VALUE_1`
- `TransportPacketState.VALUE_2`
- `TransportPacketState.VALUE_3`
- `TransportPacketState.VALUE_4`
- `TransportPacketState.VALUE_5`
- `TransportPacketState.VALUE_6`
- `TransportPacketState.VALUE_7`

Example:

```python
from transport_packet_updated import TransportPacketState

state = TransportPacketState.VALUE_3
print(int(state))   # 3
```

## `TransportStateChangeFlag`

Represents the requested 3-bit state-change field.

Available values:
- `TransportStateChangeFlag.VALUE_0`
- `TransportStateChangeFlag.VALUE_1`
- `TransportStateChangeFlag.VALUE_2`
- `TransportStateChangeFlag.VALUE_3`
- `TransportStateChangeFlag.VALUE_4`
- `TransportStateChangeFlag.VALUE_5`
- `TransportStateChangeFlag.VALUE_6`
- `TransportStateChangeFlag.VALUE_7`

Example:

```python
from transport_packet_updated import TransportStateChangeFlag

flag = TransportStateChangeFlag.VALUE_5
print(int(flag))   # 5
```

---

## Common usage patterns

## 1. Build a new packet and send it

```python
packet = TransportPacket.build(
    sequence_number=10,
    acknowledgement_number=9,
    payload_bits_as_int=int.from_bytes(b"Hello", byteorder="big"),
    payload_bit_length=40,
    source_bit=1,
    ack_bit=1,
    rst_bit=0,
    syn_bit=0,
    fin_bit=0,
    current_state=0,
    change_state_flag=0,
    state_change_ack=0,
    reserved=0,
    window_size=256,
    checksum=0,
)

raw_bytes = packet.to_bytes()
```

## 2. Decode received words and inspect the payload

```python
received_packet = TransportPacket.from_words(received_words)

print(received_packet.header.sequence_number)
print(received_packet.payload_bit_length)
print(received_packet.payload_bits_as_int)
print(received_packet.payload_bytes)
```

## 3. Extract fields from a bit-packed payload

```python
payload = received_packet.payload_bits_as_int
length = received_packet.payload_bit_length

first_4_bits = received_packet.get_payload_bits(0, 4)
next_6_bits = received_packet.get_payload_bits(4, 6)
last_3_bits = received_packet.get_payload_bits(length - 3, 3)
```

## 4. Work directly with payload-to-word conversion

```python
payload_words, padding_bits = TransportPacketConverter.payload_bits_to_words(
    payload_bits_as_int=0b111001,
    payload_bit_length=6,
)

print(payload_words)
print(padding_bits)
```

---

## Important notes

- `TransportPacket.build(...)` is the safest way to create packets.
- `payload_words` are the **transmitted** words and may include zero padding bits.
- `payload_bytes` are the **logical** payload bytes and do not include transmitted padding bits.
- For non-byte-aligned payloads, the final byte in `payload_bytes` uses only its least significant bits for the final partial byte.
- `verify_checksum()` is intentionally present but not implemented yet.
- `from_words(...)` expects a NumPy array with `dtype=np.uint32`.

---

## Minimal end-to-end example

```python
import numpy as np

from transport_packet_updated import (
    TransportPacket,
    TransportPacketState,
    TransportStateChangeFlag,
)

# Build a packet.
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
    current_state=TransportPacketState.VALUE_1,
    change_state_flag=TransportStateChangeFlag.VALUE_0,
    state_change_ack=0,
    reserved=0,
    window_size=32,
    checksum=0,
)

wire_words = outgoing.to_words()

# Decode the same packet again.
incoming = TransportPacket.from_words(wire_words)

assert incoming.header.sequence_number == 123
assert incoming.payload_bits_as_int == 0b1011001110001
assert incoming.payload_bit_length == 13
assert incoming.get_payload_bits(0, 5) == 0b10110

print("Round-trip OK")
```
