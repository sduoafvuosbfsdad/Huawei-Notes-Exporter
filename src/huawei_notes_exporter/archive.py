from __future__ import annotations

import gzip
import json
import math
import zipfile
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import BinaryIO, TypeAlias

from .errors import HiNoteError
from .models import ExtractedNote, ImageElement, NotePage, PageElement, TextElement
from .pencil import decode_pencilengine

Source: TypeAlias = str | Path | BinaryIO

DEFAULT_MAX_ENTRIES = 10_000
DEFAULT_MAX_UNCOMPRESSED_BYTES = 500 * 1024 * 1024


def extract_hinote(
    source: Source,
    *,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
) -> ExtractedNote:
    """Extract the embedded PDF, page metadata, and native vector annotations."""
    try:
        archive = zipfile.ZipFile(source)
    except (zipfile.BadZipFile, OSError) as exc:
        raise HiNoteError("The input is not a valid HiNote ZIP archive.") from exc

    with archive:
        _validate_archive(
            archive,
            max_entries=max_entries,
            max_uncompressed_bytes=max_uncompressed_bytes,
        )
        title, default_ratio, pdf_member, pdf_attachment_id = _discover_note(archive)
        pages, explicit_backgrounds = _discover_pages(
            archive, default_ratio, pdf_attachment_id
        )
        return ExtractedNote(
            title=title,
            embedded_pdf=archive.read(pdf_member),
            pages=pages,
            explicit_backgrounds=explicit_backgrounds,
        )


def _validate_archive(
    archive: zipfile.ZipFile,
    *,
    max_entries: int,
    max_uncompressed_bytes: int,
) -> None:
    if max_entries <= 0 or max_uncompressed_bytes <= 0:
        raise ValueError("Archive limits must be positive.")

    entries = archive.infolist()
    if not entries:
        raise HiNoteError("The HiNote archive is empty.")
    if len(entries) > max_entries:
        raise HiNoteError(
            f"The archive contains {len(entries)} entries; the limit is {max_entries}."
        )

    total_size = 0
    for entry in entries:
        member = PurePosixPath(entry.filename)
        if member.is_absolute() or ".." in member.parts:
            raise HiNoteError(f"Unsafe archive member: {entry.filename}")
        total_size += entry.file_size
        if total_size > max_uncompressed_bytes:
            raise HiNoteError("The uncompressed archive exceeds the configured limit.")


def _gzip_json(archive: zipfile.ZipFile, member: str) -> dict:
    try:
        value = json.loads(gzip.decompress(archive.read(member)).decode("utf-8"))
    except (KeyError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HiNoteError(f"Invalid Huawei metadata file: {member}") from exc
    if not isinstance(value, dict):
        raise HiNoteError(f"Invalid Huawei metadata object: {member}")
    return value


def _attachment_member(file_path: object) -> str:
    return f"files/{PurePosixPath(str(file_path or '')).name}"


def _discover_note(
    archive: zipfile.ZipFile,
) -> tuple[str, float, str, str | None]:
    names = set(archive.namelist())
    fallback_pdf = _find_embedded_pdf(archive)

    for member in archive.namelist():
        if "/" in member or not member.endswith(".jhinote"):
            continue
        if member == "custom_md.jhinote":
            continue
        payload = _gzip_json(archive, member).get("customNoteContent")
        if not isinstance(payload, dict):
            continue

        title = str(payload.get("noteTitle") or "Converted HiNote").strip()
        page_ratio = _positive_ratio(payload.get("pageRatio"), member, 0.706)
        for attachment in payload.get("attachment") or []:
            if not isinstance(attachment, dict):
                continue
            try:
                is_pdf = int(attachment.get("attachType", -1)) == 3
            except (TypeError, ValueError):
                is_pdf = False
            candidate = _attachment_member(attachment.get("filePath"))
            if is_pdf and candidate in names:
                attachment_id = attachment.get("id")
                return (
                    title,
                    page_ratio,
                    candidate,
                    str(attachment_id) if attachment_id else None,
                )
        if fallback_pdf:
            return title, page_ratio, fallback_pdf, None

    if fallback_pdf:
        return "Converted HiNote", 0.706, fallback_pdf, None
    raise HiNoteError("No imported PDF was found in the HiNote archive.")


def _find_embedded_pdf(archive: zipfile.ZipFile) -> str | None:
    for name in archive.namelist():
        if not name.startswith("files/") or name.endswith("/"):
            continue
        with archive.open(name) as stream:
            if stream.read(5) == b"%PDF-":
                return name
    return None


def _discover_pages(
    archive: zipfile.ZipFile,
    default_ratio: float,
    pdf_attachment_id: str | None,
) -> tuple[dict[int, NotePage], bool]:
    names = set(archive.namelist())
    pages: dict[int, NotePage] = {}
    explicit_backgrounds = False
    for member in archive.namelist():
        if not member.startswith("pages/") or not member.endswith(".jhinote"):
            continue
        payload = _gzip_json(archive, member).get("customNotePageContent")
        if not isinstance(payload, dict):
            continue
        try:
            page_number = int(payload["pageNumber"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HiNoteError(f"Missing page number in {member}.") from exc
        if page_number < 1 or page_number in pages:
            raise HiNoteError(f"Invalid or duplicate page number in {member}.")

        stroke_member = None
        for attachment in payload.get("attachment") or []:
            if not isinstance(attachment, dict):
                continue
            candidate = _attachment_member(attachment.get("filePath"))
            if candidate.endswith(".bin") and candidate in names:
                stroke_member = candidate
                break

        ratio = _positive_ratio(payload.get("pageRatio"), member, default_ratio)
        pencil = (
            decode_pencilengine(archive.read(stroke_member), stroke_member)
            if stroke_member
            else None
        )
        background_id = payload.get("bkgAttachmentId")
        pdf_page_index = None
        if background_id:
            explicit_backgrounds = True
            if pdf_attachment_id is None or str(background_id) == pdf_attachment_id:
                pdf_page_index = _background_index(payload, member)
        background = payload.get("background")
        pages[page_number] = NotePage(
            page_number,
            ratio,
            pencil,
            pdf_page_index,
            background=str(background) if background else None,
            page_color=_optional_int(payload.get("pageColor")),
            elements=_page_elements(archive, payload, member),
        )
    return pages, explicit_backgrounds


_TEXT_ELEMENT = 0
_IMAGE_ELEMENT = 1


def _page_elements(
    archive: zipfile.ZipFile, payload: dict, member: str
) -> tuple[PageElement, ...]:
    """Decode a page's text boxes and pictures, sorted into drawing order."""
    names = set(archive.namelist())
    decoded: list[tuple[float, PageElement]] = []
    for raw in payload.get("pageElement") or []:
        if not isinstance(raw, dict) or raw.get("isDelete"):
            continue
        try:
            kind = int(raw.get("elementType", -1))
            geometry = [
                float(raw.get(key) or 0.0)
                for key in ("positionX", "positionY", "width", "height", "angle")
            ]
            depth = float(raw.get("positionZ") or 0.0)
            scale = float(raw.get("scale") or 1.0)
        except (TypeError, ValueError) as exc:
            raise HiNoteError(f"Invalid page element in {member}.") from exc
        if not all(math.isfinite(value) for value in (*geometry, depth, scale)):
            raise HiNoteError(f"Invalid page element in {member}.")
        x, y, width, height, angle = geometry
        # ``scale`` resizes the box about its centre.
        x -= width * (scale - 1) / 2
        y -= height * (scale - 1) / 2
        width *= scale
        height *= scale
        if width <= 0 or height <= 0:
            continue

        element: PageElement
        if kind == _TEXT_ELEMENT:
            text, font_size, color = _parse_text_html(raw.get("html"))
            if not text.strip():
                text = str(raw.get("contentText") or "")
            if not text.strip():
                continue
            element = TextElement(x, y, width, height, angle, text, font_size, color)
        elif kind == _IMAGE_ELEMENT:
            image_member = _attachment_member(raw.get("filePath"))
            if image_member not in names:
                continue
            element = ImageElement(
                x, y, width, height, angle, archive.read(image_member)
            )
        else:
            continue
        decoded.append((depth, element))
    decoded.sort(key=lambda item: item[0])
    return tuple(element for _, element in decoded)


class _NoteHtmlParser(HTMLParser):
    """Collect the plain text, first font size and first colour of a text box."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.font_size: float | None = None
        self.color: tuple[int, int, int] | None = None
        self._elements = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.strip(): (value or "").strip() for name, value in attrs}
        if tag == "element":
            if self._elements:
                self.parts.append("\n")
            self._elements += 1
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "hw_font" and self.font_size is None:
            try:
                size = float(values.get("size", ""))
            except ValueError:
                size = math.nan
            if math.isfinite(size) and size > 0:
                self.font_size = size
        elif tag == "font" and self.color is None:
            self.color = _parse_color(values.get("color", ""))

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _parse_text_html(value: object) -> tuple[str, float | None, tuple[int, int, int]]:
    parser = _NoteHtmlParser()
    if isinstance(value, str):
        parser.feed(value)
        parser.close()
    return "".join(parser.parts), parser.font_size, parser.color or (0, 0, 0)


def _parse_color(value: str) -> tuple[int, int, int] | None:
    """Parse ``#RRGGBB`` or Android ``#AARRGGBB`` colours."""
    digits = value.lstrip("#")
    if len(digits) not in (6, 8):
        return None
    try:
        number = int(digits, 16)
    except ValueError:
        return None
    return ((number >> 16) & 0xFF, (number >> 8) & 0xFF, number & 0xFF)


def _optional_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _background_index(payload: dict, member: str) -> int:
    try:
        index = int(payload.get("bkgAttachmentIndex") or 0)
    except (TypeError, ValueError) as exc:
        raise HiNoteError(f"Invalid background page index in {member}.") from exc
    if index < 0:
        raise HiNoteError(f"Invalid background page index in {member}.")
    return index


def _positive_ratio(value: object, member: str, default: float) -> float:
    try:
        ratio = float(value or default)
    except (TypeError, ValueError) as exc:
        raise HiNoteError(f"Invalid page ratio in {member}.") from exc
    if ratio <= 0:
        raise HiNoteError(f"Invalid page ratio in {member}.")
    return ratio
