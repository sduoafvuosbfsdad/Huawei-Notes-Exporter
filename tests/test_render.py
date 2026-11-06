from __future__ import annotations

import io

from pypdf import PdfReader

from huawei_notes_exporter import convert_hinote, decode_pencilengine, extract_hinote
from huawei_notes_exporter.models import ImageElement, TextElement


def test_decodes_pen_type_and_opacity(elements_hinote: bytes) -> None:
    note = extract_hinote(io.BytesIO(elements_hinote))
    highlighter, airbrush = note.pages[1].pencil.strokes

    assert (highlighter.pen_type, round(highlighter.alpha, 3)) == (5, 0.8)
    assert (airbrush.pen_type, round(airbrush.alpha, 3)) == (4, 0.149)


def test_unset_opacity_defaults_to_opaque(v12_pencil_data: bytes) -> None:
    page = decode_pencilengine(v12_pencil_data)

    assert all(stroke.alpha == 1.0 for stroke in page.strokes)
    assert all(stroke.pen_type == 0 for stroke in page.strokes)


def test_extracts_page_elements_in_z_order(elements_hinote: bytes) -> None:
    page = extract_hinote(io.BytesIO(elements_hinote)).pages[1]

    assert page.background == "base3"
    assert page.page_color == -1
    text, image = page.elements
    assert isinstance(text, TextElement)
    assert text.text == "Hello\nWorld"
    assert text.font_size == 8.0
    assert text.color == (255, 0, 0)
    assert (text.x, text.y, text.width, text.height) == (0.1, 0.05, 0.8, 0.3)
    assert isinstance(image, ImageElement)
    assert image.data.startswith(b"\x89PNG")


def test_renders_paper_elements_and_translucent_ink(elements_hinote: bytes) -> None:
    output = io.BytesIO()
    convert_hinote(io.BytesIO(elements_hinote), output)

    output.seek(0)
    blank, backed = PdfReader(output).pages
    content = blank.get_contents().get_data()
    assert b"(Hello) Tj" in content
    assert b"(World) Tj" in content
    assert b" Do" in content  # the picture
    resources = blank["/Resources"]
    blend_modes = {
        str(state.get_object().get("/BM")) for state in resources["/ExtGState"].values()
    }
    assert "/Darken" in blend_modes  # highlighter
    # Grid rules are drawn on the blank page only, not over the imported PDF.
    grid_gray = b".866667 G"
    assert grid_gray in content
    assert grid_gray not in backed.get_contents().get_data()
