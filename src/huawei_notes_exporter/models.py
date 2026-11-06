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


@dataclass(frozen=True, slots=True)
class PencilPage:
    canvas_width: int
    strokes: tuple[Stroke, ...]


@dataclass(frozen=True, slots=True)
class NotePage:
    number: int
    ratio: float
    pencil: PencilPage | None
    # Zero-based page of the embedded PDF drawn behind this page, or None for
    # a blank note page. Only meaningful when the note declares backgrounds.
    pdf_page_index: int | None = None


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
