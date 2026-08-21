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
