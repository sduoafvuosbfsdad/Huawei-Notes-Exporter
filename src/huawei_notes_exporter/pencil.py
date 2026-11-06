from __future__ import annotations

import math
import struct

from .errors import HiNoteError
from .models import PencilPage, Point, Stroke

_MAGIC = b"PENCILENGINE"
_FILE_HEADER_SIZE = 0x88
_POINT_SIZE = 36
_SUPPORTED_VERSIONS = {0x00010000, 0x00010001}
# Stroke records written by newer Huawei Notes builds (e.g. 12.4.3 on
# HarmonyOS 4.3) are tagged 1.2 but share the 1.1 byte layout.
_SUPPORTED_STROKE_VERSIONS = _SUPPORTED_VERSIONS | {0x00010002}
_FOOTER_HEADER_SIZE = 0x28
_FOOTER_RECORD_TYPE = 3


def decode_pencilengine(data: bytes, source_name: str = "stroke.bin") -> PencilPage:
    """Decode a Huawei PENCILENGINE page into immutable vector stroke records."""
    if data[: len(_MAGIC)] != _MAGIC:
        raise HiNoteError(f"Invalid PENCILENGINE data in {source_name}.")
    if len(data) < _FILE_HEADER_SIZE:
        raise HiNoteError(f"Truncated PENCILENGINE header in {source_name}.")

    stroke_count = struct.unpack_from(">I", data, 0x70)[0]
    canvas_width = struct.unpack_from(">I", data, 0x80)[0]
    file_version = struct.unpack_from(">I", data, 0x10)[0]
    if file_version not in _SUPPORTED_VERSIONS:
        raise HiNoteError(f"Unsupported PENCILENGINE version in {source_name}.")
    if not 0 < canvas_width <= 100_000:
        raise HiNoteError(f"Invalid canvas width in {source_name}.")

    position = _FILE_HEADER_SIZE
    strokes: list[Stroke] = []
    stroke_versions: set[int] = set()
    for stroke_index in range(stroke_count):
        if position + 0xB8 > len(data):
            raise HiNoteError(f"Truncated stroke {stroke_index} in {source_name}.")

        header_size, reserved, version = struct.unpack_from(">III", data, position)
        if (
            header_size != 0x30
            or reserved != 0
            or version not in _SUPPORTED_STROKE_VERSIONS
        ):
            raise HiNoteError(
                f"Unsupported stroke record {stroke_index} in {source_name}."
            )
        stroke_versions.add(version)

        blue, green, red = (
            struct.unpack_from(">f", data, position + offset)[0]
            for offset in (0x7C, 0x80, 0x84)
        )
        nominal_width = struct.unpack_from(">f", data, position + 0x90)[0]
        pen_type = struct.unpack_from(">I", data, position + 0x74)[0]
        alpha = struct.unpack_from(">f", data, position + 0x88)[0]
        # Records that leave the opacity unset (older exports) are opaque.
        alpha = min(alpha, 1.0) if math.isfinite(alpha) and alpha > 0 else 1.0
        point_count = struct.unpack_from(">I", data, position + 0xA8)[0]
        point_stride = struct.unpack_from(">I", data, position + 0xAC)[0]
        if point_stride != _POINT_SIZE or point_count > 2_000_000:
            raise HiNoteError(
                f"Unsupported point array in stroke {stroke_index} of {source_name}."
            )

        if version == 0x00010000:
            payload_size = struct.unpack_from(">I", data, position + 0x0C)[0]
            point_start = position + 0xB4
            record_end = position + header_size + payload_size
        else:
            point_start = position + 0xB8
            record_end = point_start + point_count * point_stride
        if record_end > len(data):
            raise HiNoteError(
                f"Stroke {stroke_index} exceeds the bounds of {source_name}."
            )

        point_end = point_start + point_count * point_stride
        if point_end > record_end:
            raise HiNoteError(
                f"Point data exceeds stroke {stroke_index} in {source_name}."
            )

        color = tuple(
            max(0, min(255, round(channel * 255))) for channel in (red, green, blue)
        )
        points = tuple(
            _decode_point(
                data,
                point_start + index * point_stride,
                stroke_index,
                source_name,
                version,
            )
            for index in range(point_count)
        )
        _validate_point_states(points, stroke_index, source_name)
        if not math.isfinite(nominal_width) or nominal_width <= 0:
            raise HiNoteError(
                f"Invalid pen width in stroke {stroke_index} of {source_name}."
            )
        strokes.append(
            Stroke(
                color=color,
                nominal_width=nominal_width,
                points=points,
                pen_type=pen_type,
                alpha=alpha,
            )
        )
        position = record_end

    if len(stroke_versions) > 1:
        raise HiNoteError(f"Mixed stroke versions in {source_name}.")
    record_version = next(iter(stroke_versions), file_version)
    if not _is_valid_footer(data, position, record_version):
        raise HiNoteError(f"Unsupported PENCILENGINE footer in {source_name}.")
    return PencilPage(canvas_width=canvas_width, strokes=tuple(strokes))


def _is_valid_footer(data: bytes, position: int, record_version: int) -> bool:
    """Accept the trailing record that follows the last stroke.

    The footer is a self-describing record: a 0x28-byte header
    (size, type 3, version, payload size, UUID, 8 reserved bytes) followed by
    ``payload size`` bytes. The payload is non-empty when the page holds
    shape-recognized strokes, so its length varies. Older exports are also
    matched by their historical fixed footer sizes.
    """
    remaining = len(data) - position
    if remaining >= _FOOTER_HEADER_SIZE:
        header_size, record_type, _, payload_size = struct.unpack_from(
            ">IIII", data, position
        )
        if (
            header_size == _FOOTER_HEADER_SIZE
            and record_type == _FOOTER_RECORD_TYPE
            and remaining == _FOOTER_HEADER_SIZE + payload_size
        ):
            return True
    if record_version == 0x00010002:
        return False
    return remaining == (40 if record_version == 0x00010000 else 72)


def _decode_point(
    data: bytes,
    offset: int,
    stroke_index: int,
    source_name: str,
    version: int,
) -> Point:
    if version == 0x00010000:
        _, x, y, elapsed_ms, pressure, _, _, min_factor, state = struct.unpack_from(
            ">fffIffffI", data, offset
        )
    else:
        x, y, elapsed_ms, pressure, _, _, min_factor, state, _ = struct.unpack_from(
            ">ffIffffIf", data, offset
        )
    if not all(math.isfinite(value) for value in (x, y, pressure, min_factor)):
        raise HiNoteError(
            f"Non-finite point data in stroke {stroke_index} of {source_name}."
        )
    return Point(
        x=x,
        y=y,
        elapsed_ms=elapsed_ms,
        pressure=max(0.0, min(1.0, pressure)),
        min_factor=max(0.0, min(1.0, min_factor)),
        state=state,
    )


def _validate_point_states(
    points: tuple[Point, ...], stroke_index: int, source_name: str
) -> None:
    if not points:
        return
    if len(points) == 1:
        if points[0].state not in {4, 5}:
            raise HiNoteError(
                "Unsupported single-point state in "
                f"stroke {stroke_index} of {source_name}."
            )
        return
    # Freehand strokes go 4 (down), 6... (move), 5/6 (up). Shape-recognized
    # strokes (circles, lines, ...) are generated outlines whose points are
    # all tagged 4. Rendering ignores the state, so both are accepted.
    freehand = (
        points[0].state == 4
        and points[-1].state in {5, 6}
        and all(point.state == 6 for point in points[1:-1])
    )
    generated_shape = all(point.state == 4 for point in points)
    valid = freehand or generated_shape
    if not valid:
        raise HiNoteError(
            "Unsupported point-state sequence in "
            f"stroke {stroke_index} of {source_name}."
        )
