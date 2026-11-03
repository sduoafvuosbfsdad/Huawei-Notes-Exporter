from __future__ import annotations

import io

from pypdf import PdfReader

from huawei_notes_exporter import convert_hinote


def test_conversion_preserves_pdf_and_adds_vector_ink(
    synthetic_hinote: bytes,
) -> None:
    output = io.BytesIO()
    result = convert_hinote(io.BytesIO(synthetic_hinote), output)

    assert result.as_dict() == {
        "title": "Synthetic Note",
        "pages": 1,
        "vector_pages": 1,
        "strokes": 1,
        "points": 2,
    }

    output.seek(0)
    reader = PdfReader(output)
    assert len(reader.pages) == 1
    assert reader.pages[0].mediabox.width == 600
    assert reader.pages[0].mediabox.height == 900
    assert reader.metadata.title == "Synthetic Note"
    content = reader.pages[0].get_contents().get_data()
    assert b"Synthetic HiNote page" in content
    assert b" RG" in content
    assert b" c" in content


def test_blank_and_pdf_backed_pages_are_emitted_in_note_order(
    mixed_background_hinote: bytes,
) -> None:
    output = io.BytesIO()
    result = convert_hinote(io.BytesIO(mixed_background_hinote), output)

    assert result.pages == 2
    assert result.vector_pages == 2
    assert result.strokes == 3

    output.seek(0)
    reader = PdfReader(output)
    blank, backed = reader.pages
    assert b"Synthetic HiNote page" not in blank.get_contents().get_data()
    assert float(blank.mediabox.width) == 600
    assert round(float(blank.mediabox.height)) == round(600 / 0.70695555)
    assert b"Synthetic HiNote page" in backed.get_contents().get_data()
