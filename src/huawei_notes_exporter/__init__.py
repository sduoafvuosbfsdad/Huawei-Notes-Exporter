"""Huawei Notes archive extraction and vector PDF export."""

from .archive import extract_hinote
from .errors import HiNoteError
from .models import ExportResult, ExtractedNote, PencilPage, Point, Stroke
from .pdf import convert_hinote, export_pdf
from .pencil import decode_pencilengine

__all__ = [
    "ExportResult",
    "ExtractedNote",
    "HiNoteError",
    "PencilPage",
    "Point",
    "Stroke",
    "convert_hinote",
    "decode_pencilengine",
    "export_pdf",
    "extract_hinote",
]
