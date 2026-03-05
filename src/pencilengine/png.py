"""Minimal PNG RGBA reader/writer using only Python stdlib."""

from __future__ import annotations

import binascii
import struct
import zlib
from pathlib import Path


PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _paeth_predictor(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def read_png_rgba(path: str | Path) -> tuple[int, int, bytearray]:
    data = Path(path).read_bytes()
    if data[:8] != PNG_SIG:
        raise ValueError("Not a PNG file")

    i = 8
    width = height = None
    bit_depth = color_type = None
    idat = bytearray()
    while i < len(data):
        length = int.from_bytes(data[i : i + 4], "big")
        i += 4
        ctype = data[i : i + 4]
        i += 4
        chunk_data = data[i : i + length]
        i += length
        i += 4  # crc
        if ctype == b"IHDR":
            width, height, bit_depth, color_type, comp, flt, interlace = struct.unpack(
                ">IIBBBBB", chunk_data
            )
            if comp != 0 or flt != 0 or interlace != 0:
                raise ValueError("Unsupported PNG compression/filter/interlace mode")
        elif ctype == b"IDAT":
            idat.extend(chunk_data)
        elif ctype == b"IEND":
            break

    if width is None or height is None:
        raise ValueError("PNG missing IHDR")
    if bit_depth != 8 or color_type != 6:
        raise ValueError("Only 8-bit RGBA PNGs are supported")

    raw = zlib.decompress(bytes(idat))
    stride = width * 4
    out = bytearray(width * height * 4)
    pos = 0
    for y in range(height):
        filt = raw[pos]
        pos += 1
        row = bytearray(raw[pos : pos + stride])
        pos += stride
        prev = out[(y - 1) * stride : y * stride] if y > 0 else bytes(stride)
        if filt == 0:
            pass
        elif filt == 1:
            for x in range(4, stride):
                row[x] = (row[x] + row[x - 4]) & 0xFF
        elif filt == 2:
            for x in range(stride):
                row[x] = (row[x] + prev[x]) & 0xFF
        elif filt == 3:
            for x in range(stride):
                left = row[x - 4] if x >= 4 else 0
                row[x] = (row[x] + ((left + prev[x]) // 2)) & 0xFF
        elif filt == 4:
            for x in range(stride):
                left = row[x - 4] if x >= 4 else 0
                up = prev[x]
                up_left = prev[x - 4] if x >= 4 else 0
                row[x] = (row[x] + _paeth_predictor(left, up, up_left)) & 0xFF
        else:
            raise ValueError(f"Unsupported PNG filter type: {filt}")
        out[y * stride : (y + 1) * stride] = row
    return width, height, out


def _png_chunk(ctype: bytes, payload: bytes) -> bytes:
    length = struct.pack(">I", len(payload))
    crc = struct.pack(">I", binascii.crc32(ctype + payload) & 0xFFFFFFFF)
    return length + ctype + payload + crc


def write_png_rgba(path: str | Path, width: int, height: int, rgba: bytes) -> None:
    if len(rgba) != width * height * 4:
        raise ValueError("RGBA buffer has unexpected size")

    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)  # filter type: None
        row = rgba[y * stride : (y + 1) * stride]
        raw.extend(row)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(raw), level=9)
    out = bytearray(PNG_SIG)
    out.extend(_png_chunk(b"IHDR", ihdr))
    out.extend(_png_chunk(b"IDAT", idat))
    out.extend(_png_chunk(b"IEND", b""))
    Path(path).write_bytes(bytes(out))
