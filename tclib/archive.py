"""Hedgehog Engine AR / ARL archives (uncompressed) and XCompress decompression."""
import os
import struct
import subprocess

XDEC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools', 'xdec', 'xdec.exe')


def decompress(src, dst):
    """Decompress an XCompress (LZX) file; uncompressed files are copied as-is."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    subprocess.run([XDEC, src, dst], check=True)


def read_ar(path):
    d = open(path, 'rb').read() if isinstance(path, str) else path
    _, header_size, _, _ = struct.unpack_from('<4I', d, 0)
    o = header_size
    out = []
    while o < len(d):
        size, dsize, doff = struct.unpack_from('<3I', d, o)
        name = d[o + 0x14:d.index(b'\0', o + 0x14)].decode('latin1')
        out.append((name, d[o + doff:o + doff + dsize]))
        o += size
    return out


def ar_extras(path):
    """Per-entry 8-byte metadata (timestamps) and the data alignment of an archive."""
    d = open(path, 'rb').read()
    o = 0x10
    extra = {}
    while o < len(d):
        size, _, _ = struct.unpack_from('<3I', d, o)
        name = d[o + 0x14:d.index(b'\0', o + 0x14)].decode('latin1')
        extra[name] = d[o + 12:o + 20]
        o += size
    return extra, struct.unpack_from('<I', d, 12)[0]


def write_ar(entries, align, extra):
    out = bytearray(struct.pack('<4I', 0, 0x10, 0x14, align))
    for name, data in entries:
        nb = name.encode('latin1') + b'\0'
        hdr_len = 0x14 + len(nb)
        start = len(out)
        data_off = hdr_len
        while (start + data_off) % align:
            data_off += 1
        size = data_off + len(data)
        out += struct.pack('<3I', size, len(data), data_off) + extra.get(name, b'\0' * 8) + nb
        out += b'\0' * (data_off - hdr_len) + data
    return bytes(out)


def write_arl(names, split_sizes):
    out = b'ARL2' + struct.pack('<%dI' % (len(split_sizes) + 1), len(split_sizes), *split_sizes)
    for n in names:
        nb = n.encode('latin1')
        out += bytes([len(nb)]) + nb
    return out


def read_arl(path):
    """returns (split sizes, raw name blob)"""
    d = open(path, 'rb').read()
    assert d[:4] == b'ARL2', path
    n = struct.unpack_from('<I', d, 4)[0]
    return list(struct.unpack_from('<%dI' % n, d, 8)), d[8 + 4 * n:]
