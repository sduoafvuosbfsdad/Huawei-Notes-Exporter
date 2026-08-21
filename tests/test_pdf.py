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
