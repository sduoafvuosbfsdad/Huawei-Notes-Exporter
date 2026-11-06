from __future__ import annotations

import gzip
import io
import json
import struct
import zipfile

import pytest
from reportlab.pdfgen import canvas


def _synthetic_pdf() -> bytes:
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(600, 900))
    pdf.setFont("Helvetica", 18)
    pdf.drawString(80, 780, "Synthetic HiNote page")
    pdf.showPage()
    pdf.save()
    return stream.getvalue()


def _synthetic_stroke() -> bytes:
    stroke_start = 0x88
    record_size = 0x100
    payload_size = record_size - 0x30
    data = bytearray(stroke_start + record_size + 40)
    data[:12] = b"PENCILENGINE"
    struct.pack_into(">I", data, 0x10, 0x00010000)
    struct.pack_into(">I", data, 0x70, 1)
    struct.pack_into(">I", data, 0x80, 1000)
    struct.pack_into(">I", data, 0x84, 625)
    struct.pack_into(">IIII", data, stroke_start, 0x30, 0, 0x00010000, payload_size)
    struct.pack_into(">fff", data, stroke_start + 0x7C, 0.1490196, 0.2509804, 0.9098039)
    struct.pack_into(">f", data, stroke_start + 0x90, 3.0)
    struct.pack_into(">I", data, stroke_start + 0xA8, 2)
    struct.pack_into(">I", data, stroke_start + 0xAC, 36)
    point_start = stroke_start + 0xB4
    struct.pack_into(
        ">fffIffffI",
        data,
        point_start,
        0.0,
        200.0,
        300.0,
        0,
        0.8,
        2.3,
        10.0,
        0.2,
        4,
    )
    struct.pack_into(
        ">fffIffffI",
        data,
        point_start + 36,
        1.0,
        800.0,
        900.0,
        16,
        0.8,
        2.3,
        10.0,
        0.2,
        5,
    )
    return bytes(data)


def _gzip_payload(value: dict) -> bytes:
    return gzip.compress(json.dumps(value).encode())


@pytest.fixture
def synthetic_hinote() -> bytes:
    note = {
        "customNoteContent": {
            "noteTitle": "Synthetic Note",
            "pageRatio": 0.706,
            "attachment": [
                {
                    "attachType": 3,
                    "filePath": "/data/user/0/com.huawei.hinote/files/source_pdf",
                }
            ],
        }
    }
    page = {
        "customNotePageContent": {
            "pageNumber": 1,
            "pageRatio": 0.706,
            "attachment": [
                {
                    "attachType": 0,
                    "filePath": "/data/user/0/com.huawei.hinote/files/strokes.bin",
                }
            ],
        }
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("note.jhinote", _gzip_payload(note))
        archive.writestr("pages/page.jhinote", _gzip_payload(page))
        archive.writestr("files/source_pdf", _synthetic_pdf())
        archive.writestr("files/strokes.bin", _synthetic_stroke())
    return stream.getvalue()


@pytest.fixture
def legacy_pencil_data() -> bytes:
    stroke_start = 0x88
    point_start = stroke_start + 0xB8
    data = bytearray(point_start + 2 * 36 + 72)
    data[:12] = b"PENCILENGINE"
    struct.pack_into(">I", data, 0x10, 0x00010001)
    struct.pack_into(">I", data, 0x70, 1)
    struct.pack_into(">I", data, 0x80, 1000)
    struct.pack_into(">I", data, 0x84, 625)
    struct.pack_into(">IIII", data, stroke_start, 0x30, 0, 0x00010001, 42)
    struct.pack_into(">III", data, stroke_start + 0x20, 0x44, 0x30, 0x74)
    struct.pack_into(">fff", data, stroke_start + 0x7C, 0.1490196, 0.2509804, 0.9098039)
    struct.pack_into(">f", data, stroke_start + 0x90, 3.0)
    struct.pack_into(">I", data, stroke_start + 0xA8, 2)
    struct.pack_into(">I", data, stroke_start + 0xAC, 36)
    struct.pack_into(
        ">ffIffffIf",
        data,
        point_start,
        200.0,
        300.0,
        0,
        0.8,
        2.3,
        10.0,
        0.2,
        4,
        0.0,
    )
    struct.pack_into(
        ">ffIffffIf",
        data,
        point_start + 36,
        800.0,
        900.0,
        16,
        0.8,
        2.3,
        10.0,
        0.2,
        6,
        1.0,
    )
    return bytes(data)


def _v12_stroke(
    points: list[tuple[float, float, int]],
    width: float,
    pen_type: int = 0,
    alpha: float = 0.0,
) -> bytes:
    """One version-1.2 stroke record (same byte layout as 1.1)."""
    header_size = 0x30
    body = bytearray(0xB8 - header_size + len(points) * 36)
    record = bytearray(header_size) + body
    struct.pack_into(">IIII", record, 0, header_size, 0, 0x00010002, len(body))
    struct.pack_into(">III", record, 0x20, 0x44, 0x30, 0x74)
    struct.pack_into(">f", record, 0x90, width)
    struct.pack_into(">I", record, 0x74, pen_type)
    struct.pack_into(">f", record, 0x88, alpha)
    struct.pack_into(">II", record, 0xA8, len(points), 36)
    for index, (x, y, state) in enumerate(points):
        struct.pack_into(
            ">ffIffffIf",
            record,
            0xB8 + index * 36,
            x,
            y,
            index * 8,
            1.0,
            0.0,
            0.0,
            0.2,
            state,
            float(index),
        )
    return bytes(record)


def _v12_footer(payload: bytes) -> bytes:
    footer = bytearray(0x28)
    struct.pack_into(">IIII", footer, 0, 0x28, 3, 0x00010000, len(payload))
    return bytes(footer) + payload


def build_v12_pencil(
    strokes: list[bytes], footer_payload: bytes = b"", canvas_width: int = 1000
) -> bytes:
    header = bytearray(0x88)
    header[:12] = b"PENCILENGINE"
    struct.pack_into(">I", header, 0x10, 0x00010001)
    struct.pack_into(">I", header, 0x70, len(strokes))
    struct.pack_into(">II", header, 0x80, canvas_width, canvas_width)
    return bytes(header) + b"".join(strokes) + _v12_footer(footer_payload)


@pytest.fixture
def v12_pencil_data() -> bytes:
    """Mirrors Huawei Notes 12.4.3 output: freehand + shape-recognized strokes.

    The shape stroke's points are all tagged state 4, and the footer carries a
    payload (referencing the shape) so it is longer than the bare 40 bytes.
    """
    freehand = _v12_stroke(
        [(100.0, 100.0, 4), (150.0, 120.0, 6), (200.0, 90.0, 5)], 3.0
    )
    circle = _v12_stroke(
        [(500.0 + 50.0 * (i % 2), 500.0 + 50.0 * (i // 2), 4) for i in range(5)], 5.0
    )
    return build_v12_pencil([freehand, circle], footer_payload=bytes(56))


@pytest.fixture
def mixed_background_hinote() -> bytes:
    """A note whose page 1 is blank and page 2 is backed by imported PDF page 1."""
    note = {
        "customNoteContent": {
            "noteTitle": "Mixed Note",
            "pageRatio": 0.70695555,
            "attachment": [
                {
                    "attachType": 3,
                    "id": "pdf-attachment",
                    "filePath": "/data/data/com.huawei.hinote/files/source_pdf",
                }
            ],
        }
    }
    stroke = _v12_stroke([(100.0, 100.0, 4), (900.0, 1300.0, 5)], 3.0)

    def page(number: int, stroke_name: str, background: str | None) -> dict:
        content = {
            "pageNumber": number,
            "pageRatio": 0.70695555,
            "attachment": [
                {
                    "attachType": 0,
                    "filePath": f"/data/data/com.huawei.hinote/files/{stroke_name}",
                }
            ],
        }
        if background:
            content["bkgAttachmentId"] = background
            content["bkgAttachmentIndex"] = 0
        return {"customNotePageContent": content}

    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("note.jhinote", _gzip_payload(note))
        archive.writestr("pages/a.jhinote", _gzip_payload(page(1, "blank.bin", None)))
        archive.writestr(
            "pages/b.jhinote", _gzip_payload(page(2, "pdf.bin", "pdf-attachment"))
        )
        archive.writestr("files/source_pdf", _synthetic_pdf())
        archive.writestr("files/blank.bin", build_v12_pencil([stroke]))
        archive.writestr("files/pdf.bin", build_v12_pencil([stroke, stroke]))
    return stream.getvalue()


_PNG_1X1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c4944415408d763f8cfc0f01f0005000201e5270ede0000000049454e44ae426082"
)


@pytest.fixture
def elements_hinote() -> bytes:
    """A blank grid page with a text box, a picture and highlighter ink,
    followed by a PDF-backed page (mirrors hinote_1.0.5 exports)."""
    note = {
        "customNoteContent": {
            "noteTitle": "Elements Note",
            "pageRatio": 0.70695555,
            "attachment": [
                {
                    "attachType": 3,
                    "id": "pdf-attachment",
                    "filePath": "/data/data/com.huawei.hinote/files/source_pdf",
                }
            ],
        }
    }
    blank_page = {
        "customNotePageContent": {
            "pageNumber": 1,
            "pageRatio": 0.70695555,
            "background": "base3",
            "pageColor": -1,
            "attachment": [
                {
                    "attachType": 0,
                    "filePath": "/data/data/com.huawei.hinote/files/ink.bin",
                }
            ],
            "pageElement": [
                {
                    "elementType": 1,
                    "filePath": "/data/data/com.huawei.hinote/files/image/pic.png",
                    "positionX": 0.5,
                    "positionY": 0.6,
                    "positionZ": -5,
                    "width": 0.4,
                    "height": 0.3,
                    "angle": 0.0,
                    "scale": 1.0,
                },
                {
                    "elementType": 0,
                    "contentText": "fallback",
                    "html": (
                        '<note><element type="TEXT"><hw_font size ="8.0">'
                        '<font color ="#ffff0000">Hello</font></hw_font></element>'
                        '<element type="TEXT">World</element></note>'
                    ),
                    "positionX": 0.1,
                    "positionY": 0.05,
                    "positionZ": -9,
                    "width": 0.8,
                    "height": 0.3,
                    "angle": 0.0,
                    "scale": 1.0,
                },
                {
                    "elementType": 0,
                    "contentText": "deleted",
                    "isDelete": 1,
                    "positionX": 0.1,
                    "positionY": 0.5,
                    "width": 0.5,
                    "height": 0.1,
                },
            ],
        }
    }
    backed_page = {
        "customNotePageContent": {
            "pageNumber": 2,
            "pageRatio": 0.70695555,
            "background": "base3",
            "bkgAttachmentId": "pdf-attachment",
            "bkgAttachmentIndex": 0,
        }
    }
    highlighter = _v12_stroke(
        [(100.0, 100.0, 4), (300.0, 120.0, 6), (500.0, 90.0, 5)],
        25.0,
        pen_type=5,
        alpha=0.8,
    )
    airbrush = _v12_stroke(
        [(100.0, 600.0, 4), (300.0, 650.0, 6), (500.0, 600.0, 5)],
        40.0,
        pen_type=4,
        alpha=0.149,
    )
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("note.jhinote", _gzip_payload(note))
        archive.writestr("pages/a.jhinote", _gzip_payload(blank_page))
        archive.writestr("pages/b.jhinote", _gzip_payload(backed_page))
        archive.writestr("files/source_pdf", _synthetic_pdf())
        archive.writestr("files/ink.bin", build_v12_pencil([highlighter, airbrush]))
        archive.writestr("files/pic.png", _PNG_1X1)
    return stream.getvalue()
