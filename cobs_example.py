from cobs import cobs

data = b'hello\x00world'

encoded = cobs.encode(data)
print(encoded)  # no 0x00 bytes inside

decoded = cobs.decode(encoded)
print(decoded)  # b'hello\x00world'