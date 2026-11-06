from __future__ import annotations

import struct

import pytest

from huawei_notes_exporter import HiNoteError, decode_pencilengine


def test_rejects_unknown_pencil_data() -> None:
    with pytest.raises(HiNoteError, match="Invalid PENCILENGINE"):
        decode_pencilengine(b"not pencil data")


def test_rejects_truncated_pencil_header() -> None:
    with pytest.raises(HiNoteError, match="Truncated PENCILENGINE"):
        decode_pencilengine(b"PENCILENGINE")


def test_decodes_legacy_version_10001(legacy_pencil_data: bytes) -> None:
    page = decode_pencilengine(legacy_pencil_data)

    assert page.canvas_width == 1000
    assert len(page.strokes) == 1
    assert page.strokes[0].points[0].x == 200
    assert page.strokes[0].points[-1].state == 6


def test_decodes_version_10002_with_shape_stroke_and_footer_payload(
    v12_pencil_data: bytes,
) -> None:
    page = decode_pencilengine(v12_pencil_data)

    assert len(page.strokes) == 2
    freehand, shape = page.strokes
    assert [point.state for point in freehand.points] == [4, 6, 5]
    assert {point.state for point in shape.points} == {4}
    assert shape.nominal_width == 5.0


def test_rejects_version_10002_with_trailing_garbage(v12_pencil_data: bytes) -> None:
    with pytest.raises(HiNoteError, match="footer"):
        decode_pencilengine(v12_pencil_data + b"\x00")


def test_rejects_unknown_point_state_sequence(legacy_pencil_data: bytes) -> None:
    data = bytearray(legacy_pencil_data)
    first_state = 0x88 + 0xB8 + 28
    struct.pack_into(">I", data, first_state, 6)
    with pytest.raises(HiNoteError, match="point-state sequence"):
        decode_pencilengine(bytes(data))
