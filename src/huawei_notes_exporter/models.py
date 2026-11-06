from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float
    elapsed_ms: int
    pressure: float
    min_factor: float
    state: int


@dataclass(frozen=True, slots=True)
class Stroke:
    color: tuple[int, int, int]
    nominal_width: float
    points: tuple[Point, ...]
    # Huawei pen tool id (stroke header offset 0x74); 0 when absent.
    pen_type: int = 0
    # Stroke opacity in [0, 1] (stroke header offset 0x88).
    alpha: float = 1.0


@dataclass(frozen=True, slots=True)
class PencilPage:
    canvas_width: int
    strokes: tuple[Stroke, ...]


@dataclass(frozen=True, slots=True)
class TextElement:
    """A typed text box. Geometry is in fractions of the page size."""

    x: float
    y: float
    width: float
    height: float
    angle: float
    text: str
    # Huawei font size (the ``hw_font size`` attribute), or None if absent.
    font_size: float | None
    color: tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class ImageElement:
    """An inserted picture. Geometry is in fractions of the page size."""

    x: float
    y: float
    width: float
    height: float
    angle: float
    data: bytes


PageElement = TextElement | ImageElement


@dataclass(frozen=True, slots=True)
class NotePage:
    number: int
    ratio: float
    pencil: PencilPage | None
    # Zero-based page of the embedded PDF drawn behind this page, or None for
    # a blank note page. Only meaningful when the note declares backgrounds.
    pdf_page_index: int | None = None
    # Paper template name (e.g. "base3" = square grid) and ARGB paper colour.
    background: str | None = None
    page_color: int | None = None
    # Text boxes and pictures, in drawing (z) order. Drawn below the ink.
    elements: tuple[PageElement, ...] = ()


@dataclass(frozen=True, slots=True)
class ExtractedNote:
    title: str
    embedded_pdf: bytes
    pages: dict[int, NotePage]
    # True when page metadata names its PDF background explicitly
    # (bkgAttachmentId). Older exports lack it and map note page N to PDF
    # page N.
    explicit_backgrounds: bool = False


@dataclass(frozen=True, slots=True)
class ExportResult:
    title: str
    pages: int
    vector_pages: int
    strokes: int
    points: int

    def as_dict(self) -> dict[str, str | int]:
        return {
            "title": self.title,
            "pages": self.pages,
            "vector_pages": self.vector_pages,
            "strokes": self.strokes,
            "points": self.points,
        }
