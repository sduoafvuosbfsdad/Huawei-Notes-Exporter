"""End-to-end checks against a real Huawei Notes export (hinote_1.0.5).

``data/hinote-test-file.zip`` is the sample attached to issue #1: a blank
grid page with typed text, an inserted picture and every pen type, followed
by an imported PDF page with handwriting. Huawei stores a rendered thumbnail
of each page in the archive; the visual test compares our PDF against them.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from pypdf import PdfReader

from huawei_notes_exporter import convert_hinote, extract_hinote
from huawei_notes_exporter.cli import main

SAMPLE = Path(__file__).parent / "data" / "hinote-test-file.zip"
# Huawei's page thumbnails, in note page order.
THUMBNAILS = (
    "files/1505527b512b4fff824581193276af1f_202611011052_47909.jpg",
    "files/747d97cde7c14fb684f50139288ad14b_202611011053_39485.jpg",
)
# Mean absolute RGB difference (0-255) to the thumbnail, per page. The
# exporter scores 4.1 and 2.8 with pdfium; the thresholds leave headroom
# for renderer differences while catching lost content (12.2 for page 1
# before text, pictures, grid paper and pen styles were rendered).
MAX_MEAN_DIFF = (5.5, 3.5)


@pytest.fixture(scope="module")
def sample_pdf() -> bytes:
    output = io.BytesIO()
    result = convert_hinote(SAMPLE, output)
    assert result.as_dict() == {
        "title": "hinote-export-test",
        "pages": 2,
        "vector_pages": 2,
        "strokes": 18,
        "points": 1166,
    }
    return output.getvalue()


def test_sample_decodes_every_page_element() -> None:
    note = extract_hinote(SAMPLE)

    first, second = note.pages[1], note.pages[2]
    assert first.background == "base3"
    assert first.pdf_page_index is None
    assert [type(element).__name__ for element in first.elements] == [
        "TextElement",
        "ImageElement",
    ]
    assert first.elements[0].text == "Test"
    assert {stroke.pen_type for stroke in first.pencil.strokes} == {
        1,
        2,
        3,
        4,
        5,
        11,
        12,
        13,
    }
    assert second.pdf_page_index == 0
    assert second.elements == ()


def test_sample_pdf_contains_text_picture_and_original_document(
    sample_pdf: bytes,
) -> None:
    blank, backed = PdfReader(io.BytesIO(sample_pdf)).pages
    blank_content = blank.get_contents().get_data()
    assert b"(Test) Tj" in blank_content
    assert b" Do" in blank_content
    assert "Test – PDF Dokument" in backed.extract_text()


def test_sample_cli_export(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    destination = tmp_path / "sample.pdf"

    assert main([str(SAMPLE), "--output", str(destination), "--json"]) == 0

    stats = json.loads(capsys.readouterr().out)
    assert stats["pages"] == 2
    assert stats["strokes"] == 18
    assert destination.read_bytes().startswith(b"%PDF-")


def test_sample_matches_huawei_thumbnails(sample_pdf: bytes) -> None:
    np = pytest.importorskip("numpy")
    pdfium = pytest.importorskip("pypdfium2")
    image = pytest.importorskip("PIL.Image")

    document = pdfium.PdfDocument(sample_pdf)
    with zipfile.ZipFile(SAMPLE) as archive:
        for index, (name, limit) in enumerate(
            zip(THUMBNAILS, MAX_MEAN_DIFF, strict=True)
        ):
            thumbnail = image.open(io.BytesIO(archive.read(name))).convert("RGB")
            page = document[index]
            rendered = (
                page.render(scale=thumbnail.width / page.get_width())
                .to_pil()
                .convert("RGB")
                .resize(thumbnail.size)
            )
            difference = np.abs(
                np.asarray(thumbnail, dtype=float) - np.asarray(rendered, dtype=float)
            ).mean()
            assert difference < limit, f"page {index + 1}: mean diff {difference:.2f}"
