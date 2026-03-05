"""Parser for Huawei Notes PENCILENGINE ink binaries.

The parser intentionally preserves unknown fields and raw offsets to support
format forensics while still exposing a practical stroke model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import struct
from pathlib import Path
from typing import Any


MAGIC = b"PENCILENGINE"
GLOBAL_HEADER_MIN = 0x88
POINT_RECORD_SIZE = 0x24
STROKE_FIXED_OVERHEAD = 0xB8
STROKE_PREFIX_SIGNATURE = (
    b"\x00\x00\x000"  # prelude marker
    b"\x00\x00\x00\x00"  # prelude flags
    b"\x00\x01\x00\x01"  # prelude version-ish marker
)
STROKE_SECTION_SIGNATURE = (
    b"\x00\x00\x00D"
    b"\x00\x00\x000"
    b"\x00\x00\x00t"
)


def _u32be(data: bytes, off: int) -> int:
    return int.from_bytes(data[off : off + 4], "big", signed=False)


def _f32be(data: bytes, off: int) -> float:
    return struct.unpack(">f", data[off : off + 4])[0]


@dataclass
class FileHeader:
    magic: str
    offset: int
    header_len_u32: int
    version_u16_a: int
    version_u16_b: int
    global_header_size: int
    raw_hex: str


@dataclass
class PointRecord:
    offset: int
    x: float
    y: float
    t_u32: int
    f3: float
    f4: float
    f5: float
    f6: float
    u7: int
    f8: float
    raw_hex: str


@dataclass
class StrokeChunk:
    stroke_index: int
    offset: int
    total_length: int
    point_count: int
    point_stride: int
    point_data_offset: int
    prelude_marker: int
    prelude_flags: int
    prelude_version_marker: int
    stroke_id_u32: int
    stroke_uuid_hex: str
    section_marker_44: int
    section_marker_30: int
    section_marker_74: int
    metadata_words: dict[str, int]
    metadata_floats: dict[str, float]
    points: list[PointRecord]
    raw_prefix_hex: str


@dataclass
class ParsedBin:
    path: str
    size: int
    header: FileHeader
    global_words: dict[str, int]
    first_stroke_offset: int
    strokes: list[StrokeChunk]
    trailing_offset: int
    trailing_hex: str

    def to_intermediate_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_intermediate_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_intermediate_dict(), indent=indent)


def _find_first_stroke_offset(data: bytes) -> int:
    for off in range(GLOBAL_HEADER_MIN, len(data) - 0xB8, 4):
        if data[off : off + 12] != STROKE_PREFIX_SIGNATURE:
            continue
        if data[off + 0x20 : off + 0x2C] != STROKE_SECTION_SIGNATURE:
            continue
        point_stride = _u32be(data, off + 0xAC)
        point_count = _u32be(data, off + 0xA8)
        if point_stride != POINT_RECORD_SIZE:
            continue
        end = off + STROKE_FIXED_OVERHEAD + (point_count * point_stride)
        if end <= len(data):
            return off
    raise ValueError("Could not locate first stroke chunk")


def _parse_stroke(data: bytes, stroke_index: int, off: int) -> StrokeChunk:
    if data[off : off + 12] != STROKE_PREFIX_SIGNATURE:
        raise ValueError(f"Invalid stroke prefix signature at 0x{off:08x}")
    if data[off + 0x20 : off + 0x2C] != STROKE_SECTION_SIGNATURE:
        raise ValueError(f"Invalid stroke section signature at 0x{off:08x}")

    point_count = _u32be(data, off + 0xA8)
    point_stride = _u32be(data, off + 0xAC)
    if point_stride != POINT_RECORD_SIZE:
        raise ValueError(
            f"Unexpected point stride {point_stride} at 0x{off + 0xAC:08x}"
        )
    if point_count <= 0:
        raise ValueError(f"Non-positive point count {point_count} at 0x{off:08x}")

    point_data_offset = off + STROKE_FIXED_OVERHEAD
    total_len = STROKE_FIXED_OVERHEAD + (point_count * point_stride)
    end = off + total_len
    if end > len(data):
        raise ValueError(f"Stroke at 0x{off:08x} exceeds file size")

    metadata_words: dict[str, int] = {}
    metadata_floats: dict[str, float] = {}
    for rel in range(0x2C, 0xB8, 4):
        key = f"0x{rel:02x}"
        metadata_words[key] = _u32be(data, off + rel)
        metadata_floats[key] = _f32be(data, off + rel)

    points: list[PointRecord] = []
    for i in range(point_count):
        rec_off = point_data_offset + (i * point_stride)
        raw = data[rec_off : rec_off + point_stride]
        x, y, t_u32, f3, f4, f5, f6, u7, f8 = struct.unpack(">ffIffffIf", raw)
        points.append(
            PointRecord(
                offset=rec_off,
                x=x,
                y=y,
                t_u32=t_u32,
                f3=f3,
                f4=f4,
                f5=f5,
                f6=f6,
                u7=u7,
                f8=f8,
                raw_hex=raw.hex(),
            )
        )

    return StrokeChunk(
        stroke_index=stroke_index,
        offset=off,
        total_length=total_len,
        point_count=point_count,
        point_stride=point_stride,
        point_data_offset=point_data_offset,
        prelude_marker=_u32be(data, off),
        prelude_flags=_u32be(data, off + 0x04),
        prelude_version_marker=_u32be(data, off + 0x08),
        stroke_id_u32=_u32be(data, off + 0x0C),
        stroke_uuid_hex=data[off + 0x10 : off + 0x20].hex(),
        section_marker_44=_u32be(data, off + 0x20),
        section_marker_30=_u32be(data, off + 0x24),
        section_marker_74=_u32be(data, off + 0x28),
        metadata_words=metadata_words,
        metadata_floats=metadata_floats,
        points=points,
        raw_prefix_hex=data[off : off + STROKE_FIXED_OVERHEAD].hex(),
    )


def parse_pencilengine_bin(path: str | Path) -> ParsedBin:
    p = Path(path)
    data = p.read_bytes()
    if len(data) < GLOBAL_HEADER_MIN:
        raise ValueError("File too small to be a valid PENCILENGINE binary")
    if not data.startswith(MAGIC):
        raise ValueError("Missing PENCILENGINE magic")

    header = FileHeader(
        magic=MAGIC.decode("ascii"),
        offset=0,
        header_len_u32=_u32be(data, 0x0C),
        version_u16_a=int.from_bytes(data[0x10:0x12], "big"),
        version_u16_b=int.from_bytes(data[0x12:0x14], "big"),
        global_header_size=GLOBAL_HEADER_MIN,
        raw_hex=data[:GLOBAL_HEADER_MIN].hex(),
    )

    global_words = {
        f"0x{off:02x}": _u32be(data, off)
        for off in range(0x0C, GLOBAL_HEADER_MIN, 4)
    }

    first_stroke = _find_first_stroke_offset(data)
    strokes: list[StrokeChunk] = []
    off = first_stroke
    stroke_index = 0
    while off + STROKE_FIXED_OVERHEAD <= len(data):
        if data[off : off + 12] != STROKE_PREFIX_SIGNATURE:
            break
        if data[off + 0x20 : off + 0x2C] != STROKE_SECTION_SIGNATURE:
            break
        stroke = _parse_stroke(data, stroke_index, off)
        strokes.append(stroke)
        off = off + stroke.total_length
        stroke_index += 1

    return ParsedBin(
        path=str(p),
        size=len(data),
        header=header,
        global_words=global_words,
        first_stroke_offset=first_stroke,
        strokes=strokes,
        trailing_offset=off,
        trailing_hex=data[off:].hex(),
    )
