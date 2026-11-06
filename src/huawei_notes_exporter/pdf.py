from __future__ import annotations

import io
import re
from pathlib import Path
from typing import BinaryIO, TypeAlias

from pypdf import PageObject, PdfReader, PdfWriter
from reportlab.pdfgen import canvas

from .archive import (
    DEFAULT_MAX_ENTRIES,
    DEFAULT_MAX_UNCOMPRESSED_BYTES,
    Source,
    extract_hinote,
)
from .errors import HiNoteError
from .models import (
    ExportResult,
    ExtractedNote,
    NotePage,
    PencilPage,
    Point,
    Stroke,
)

Destination: TypeAlias = str | Path | BinaryIO


def convert_hinote(
    source: Source,
    destination: Destination,
    *,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
) -> ExportResult:
    """Convert a .hinote archive to a PDF containing native vector ink."""
    note = extract_hinote(
        source,
        max_entries=max_entries,
        max_uncompressed_bytes=max_uncompressed_bytes,
    )
    return export_pdf(note, destination)


def export_pdf(note: ExtractedNote, destination: Destination) -> ExportResult:
    """Overlay decoded Huawei ink on the original embedded PDF."""
    try:
        reader = PdfReader(io.BytesIO(note.embedded_pdf))
    except Exception as exc:
        raise HiNoteError("The PDF embedded in the HiNote archive is invalid.") from exc
    if not reader.pages:
        raise HiNoteError("The embedded PDF has no pages.")

    writer = PdfWriter()
    vector_pages = 0
    stroke_total = 0
    point_total = 0
    reference_width = float(reader.pages[0].mediabox.width)
    for note_page, source_page in _page_plan(note, reader):
        pencil = note_page.pencil if note_page else None
        if pencil and pencil.strokes:
            vector_pages += 1
            stroke_total += len(pencil.strokes)
            point_total += sum(len(stroke.points) for stroke in pencil.strokes)

        if source_page is not None:
            writer.add_page(source_page)
        else:
            # A note page without a PDF background (a page the user added in
            # the app). Match the PDF width and the page's own aspect ratio.
            writer.add_blank_page(reference_width, reference_width / note_page.ratio)
        output_page = writer.pages[-1]
        page_width = float(output_page.mediabox.width)
        page_height = float(output_page.mediabox.height)
        overlay = _make_overlay(
            pencil,
            note_page.ratio if note_page else 1.0,
            page_width,
            page_height,
        )
        if overlay is not None:
            output_page.merge_page(overlay)

    title = _clean_title(note.title)
    writer.add_metadata(
        {
            "/Title": title,
            "/Subject": "Huawei HiNote exported with decoded vector annotations",
            "/Creator": "huawei-notes-exporter",
        }
    )
    try:
        writer.write(destination)
    except OSError as exc:
        raise HiNoteError("The exported PDF could not be written.") from exc

    return ExportResult(
        title=title,
        pages=len(writer.pages),
        vector_pages=vector_pages,
        strokes=stroke_total,
        points=point_total,
    )


def _page_plan(
    note: ExtractedNote, reader: PdfReader
) -> list[tuple[NotePage | None, PageObject | None]]:
    """Pair each output page with its note metadata and PDF background.

    When page metadata names its background, note pages are emitted in note
    order: PDF-backed pages use the referenced PDF page and the rest are blank.
    Otherwise note page N is overlaid on PDF page N (legacy exports).
    """
    if not note.explicit_backgrounds:
        return [
            (note.pages.get(number), source_page)
            for number, source_page in enumerate(reader.pages, 1)
        ]

    plan: list[tuple[NotePage | None, PageObject | None]] = []
    for number in sorted(note.pages):
        note_page = note.pages[number]
        index = note_page.pdf_page_index
        if index is not None and index >= len(reader.pages):
            raise HiNoteError(f"Page {number} references missing PDF page {index + 1}.")
        plan.append((note_page, reader.pages[index] if index is not None else None))
    return plan


def _make_overlay(
    pencil: PencilPage | None,
    page_ratio: float,
    page_width: float,
    page_height: float,
):
    if pencil is None or not pencil.strokes:
        return None
    stream = io.BytesIO()
    output = canvas.Canvas(
        stream, pagesize=(page_width, page_height), pageCompression=1
    )
    _draw_pencil_page(output, pencil, page_ratio, page_width, page_height)
    output.showPage()
    output.save()
    stream.seek(0)
    return PdfReader(stream).pages[0]


def _draw_pencil_page(
    output: canvas.Canvas,
    pencil: PencilPage,
    page_ratio: float,
    page_width: float,
    page_height: float,
) -> None:
    logical_height = pencil.canvas_width / page_ratio
    scale_x = page_width / pencil.canvas_width
    scale_y = page_height / logical_height
    width_scale = (scale_x + scale_y) * 0.5
    output.setLineCap(1)
    output.setLineJoin(1)

    def px(value: float) -> float:
        return value * scale_x

    def py(value: float) -> float:
        return page_height - value * scale_y

    for stroke in pencil.strokes:
        if not stroke.points:
            continue
        red, green, blue = stroke.color
        output.setStrokeColorRGB(red / 255, green / 255, blue / 255)
        output.setFillColorRGB(red / 255, green / 255, blue / 255)
        if len(stroke.points) == 1:
            radius = _point_width(stroke, stroke.points[0]) * width_scale * 0.5
            output.circle(
                px(stroke.points[0].x), py(stroke.points[0].y), radius, stroke=0, fill=1
            )
            continue

        for index, (start, end) in enumerate(
            zip(stroke.points[:-1], stroke.points[1:], strict=True)
        ):
            c1x, c1y, c2x, c2y = _control_points(stroke.points, index)
            output.setLineWidth(_segment_width(stroke, start, end) * width_scale)
            path = output.beginPath()
            path.moveTo(px(start.x), py(start.y))
            path.curveTo(px(c1x), py(c1y), px(c2x), py(c2y), px(end.x), py(end.y))
            output.drawPath(path, stroke=1, fill=0)


def _point_width(stroke: Stroke, point: Point) -> float:
    return max(
        0.35,
        stroke.nominal_width
        * (point.min_factor + (1.0 - point.min_factor) * point.pressure),
    )


def _segment_width(stroke: Stroke, start: Point, end: Point) -> float:
    return (_point_width(stroke, start) + _point_width(stroke, end)) * 0.5


def _control_points(
    points: tuple[Point, ...], index: int
) -> tuple[float, float, float, float]:
    p0 = points[max(index - 1, 0)]
    p1 = points[index]
    p2 = points[index + 1]
    p3 = points[min(index + 2, len(points) - 1)]
    return (
        p1.x + (p2.x - p0.x) / 6,
        p1.y + (p2.y - p0.y) / 6,
        p2.x - (p3.x - p1.x) / 6,
        p2.y - (p3.y - p1.y) / 6,
    )


def _clean_title(value: str) -> str:
    value = re.sub(r"[\x00-\x1f]+", " ", value).strip()
    return value[:250] or "Converted HiNote"
