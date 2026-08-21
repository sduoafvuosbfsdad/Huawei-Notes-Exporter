from __future__ import annotations

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
