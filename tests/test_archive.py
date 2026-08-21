from __future__ import annotations

import io
import zipfile

import pytest

from huawei_notes_exporter import HiNoteError, extract_hinote


def test_extracts_pdf_metadata_and_native_strokes(synthetic_hinote: bytes) -> None:
    note = extract_hinote(io.BytesIO(synthetic_hinote))

    assert note.title == "Synthetic Note"
    assert note.embedded_pdf.startswith(b"%PDF-")
    assert note.pages[1].pencil is not None
    assert len(note.pages[1].pencil.strokes) == 1
    assert note.pages[1].pencil.strokes[0].color == (232, 64, 38)


def test_rejects_path_traversal_archive() -> None:
    source = io.BytesIO()
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("../note.jhinote", b"unsafe")
    source.seek(0)

    with pytest.raises(HiNoteError, match="Unsafe archive member"):
        extract_hinote(source)


def test_rejects_non_zip() -> None:
    with pytest.raises(HiNoteError, match="valid HiNote ZIP"):
        extract_hinote(io.BytesIO(b"not a zip"))
