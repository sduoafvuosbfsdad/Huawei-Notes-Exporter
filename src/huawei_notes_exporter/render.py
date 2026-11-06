"""Draw Huawei note page content (paper, text boxes, pictures, ink) as PDF.

Geometry constants below were calibrated against the page thumbnails that
Huawei Notes stores in each export (``files/*_<timestamp>.jpg``). Page
coordinates come from the PENCILENGINE canvas, whose width maps to the page
width (1000 units in observed exports).
"""

from __future__ import annotations

import io
import math
from collections.abc import Callable
from dataclasses import dataclass

from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

from .models import ImageElement, PageElement, PencilPage, Point, Stroke, TextElement

# --- Paper ------------------------------------------------------------------

# "base3" is the square-grid paper: squares of 5.845% of the page width.
# Rows start at the top edge; columns are laid out from a rule just inside
# the right edge, and the left and top page edges carry a rule as well.
_GRID_BACKGROUNDS = {"base3": 0.05845}
_GRID_GRAY = 0xDD / 255
_GRID_LINE_FRACTION = 0.0013  # rule width as a fraction of the page width
_GRID_RIGHT_INSET = 0.002


def draw_paper(
    output: canvas.Canvas,
    background: str | None,
    page_color: int | None,
    page_width: float,
    page_height: float,
) -> None:
    """Fill a blank (non-PDF) page with its paper colour and template."""
    if page_color is not None and (page_color & 0xFFFFFF) != 0xFFFFFF:
        red, green, blue = _argb_rgb(page_color)
        output.setFillColorRGB(red, green, blue)
        output.rect(0, 0, page_width, page_height, stroke=0, fill=1)

    square = _GRID_BACKGROUNDS.get(background or "")
    if not square:
        return
    spacing = page_width * square
    output.saveState()
    output.setStrokeGray(_GRID_GRAY)
    output.setLineWidth(page_width * _GRID_LINE_FRACTION)
    output.setLineCap(0)
    line_width = page_width * _GRID_LINE_FRACTION
    output.line(line_width / 2, 0, line_width / 2, page_height)
    x = page_width * (1 - _GRID_RIGHT_INSET)
    while x > spacing / 2:
        output.line(x, 0, x, page_height)
        x -= spacing
    output.line(
        0, page_height - line_width / 2, page_width, page_height - line_width / 2
    )
    y = page_height - spacing
    while y >= -1e-6:
        output.line(0, y, page_width, y)
        y -= spacing
    output.restoreState()


def _argb_rgb(value: int) -> tuple[float, float, float]:
    return tuple(((value >> shift) & 0xFF) / 255 for shift in (16, 8, 0))


# --- Text boxes and pictures ------------------------------------------------

# A Huawei font size of 1.0 measures 25.5 canvas units (1/1000 page width).
_FONT_UNITS = 25.5 / 1000
# Inner padding of a text box, as a fraction of the page width.
_TEXT_PADDING = 0.03
# Baseline of the first line below the padded top, in font-size units.
_TEXT_ASCENT = 0.93
_TEXT_LINE_HEIGHT = 1.17
_LATIN_FONT = "Helvetica"
# Huawei's UI font is narrower than Helvetica; condense to match its widths.
_LATIN_CONDENSE = 0.88
_CJK_FONT = "STSong-Light"


def draw_elements(
    output: canvas.Canvas,
    elements: tuple[PageElement, ...],
    page_width: float,
    page_height: float,
) -> None:
    for element in elements:
        left = element.x * page_width
        width = element.width * page_width
        height = element.height * page_height
        bottom = page_height - element.y * page_height - height
        output.saveState()
        if element.angle:
            # Android rotates clockwise for positive angles (radians) about
            # the box centre; PDF space has y pointing up.
            output.translate(left + width / 2, bottom + height / 2)
            output.rotate(-math.degrees(element.angle))
            output.translate(-(left + width / 2), -(bottom + height / 2))
        if isinstance(element, ImageElement):
            _draw_image(output, element, left, bottom, width, height)
        else:
            _draw_text(output, element, left, bottom, width, height, page_width)
        output.restoreState()


def _draw_image(
    output: canvas.Canvas,
    element: ImageElement,
    left: float,
    bottom: float,
    width: float,
    height: float,
) -> None:
    try:
        image = ImageReader(io.BytesIO(element.data))
        image.getSize()
    except Exception:  # noqa: BLE001 - undecodable pictures are skipped
        return
    output.drawImage(image, left, bottom, width, height, mask="auto")


def _draw_text(
    output: canvas.Canvas,
    element: TextElement,
    left: float,
    bottom: float,
    width: float,
    height: float,
    page_width: float,
) -> None:
    font = _font_for(element.text)
    condense = _LATIN_CONDENSE if font == _LATIN_FONT else 1.0
    size = (element.font_size or 8.0) * _FONT_UNITS * page_width
    padding = _TEXT_PADDING * page_width
    max_width = max(width - 2 * padding, size) / condense
    lines = _wrap(element.text, font, size, max_width)
    red, green, blue = (channel / 255 for channel in element.color)
    text = output.beginText()
    text.setFont(font, size)
    text.setHorizScale(condense * 100)
    text.setFillColorRGB(red, green, blue)
    baseline = bottom + height - padding - _TEXT_ASCENT * size
    for line in lines:
        text.setTextOrigin(left + padding, baseline)
        text.textOut(line)
        baseline -= _TEXT_LINE_HEIGHT * size
    output.drawText(text)


def _font_for(text: str) -> str:
    try:
        text.encode("cp1252")
    except UnicodeEncodeError:
        if _CJK_FONT not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont(_CJK_FONT))
        return _CJK_FONT
    return _LATIN_FONT


def _wrap(text: str, font: str, size: float, max_width: float) -> list[str]:
    def fits(value: str) -> bool:
        return pdfmetrics.stringWidth(value, font, size) <= max_width

    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}" if line else word
            if fits(candidate) or not line:
                line = candidate
            else:
                lines.append(line)
                line = word
            # Break words longer than the box (e.g. CJK runs without spaces).
            while not fits(line) and len(line) > 1:
                cut = len(line) - 1
                while cut > 1 and not fits(line[:cut]):
                    cut -= 1
                lines.append(line[:cut])
                line = line[cut:]
        lines.append(line)
    return lines


# --- Ink --------------------------------------------------------------------

# Huawei pen tool ids (stroke header offset 0x74).
PEN_FOUNTAIN = 1
PEN_BALLPOINT = 2
PEN_FINE = 3
PEN_AIRBRUSH = 4
PEN_HIGHLIGHTER = 5
PEN_PENCIL = 11
PEN_MARKER = 12
PEN_GEL = 13

# Airbrush strokes are built from overlapping translucent dabs; the core
# reaches the opacity of eight overlapping record-alpha dabs. Each dab is a
# soft disc whose opacity fades over its outer 40%.
_AIRBRUSH_DABS = 8
_AIRBRUSH_RINGS = 4
_AIRBRUSH_CORE = 0.6
_AIRBRUSH_SPACING = 0.12  # dab spacing as a fraction of the dab diameter
_CURVE_STEPS = 8


@dataclass(frozen=True, slots=True)
class _PenStyle:
    # Width in canvas units for one point; None means constant width.
    width: Callable[[Stroke, Point], float]
    constant_width: bool
    # Per-point opacity multiplier (pencil darkness follows pressure).
    opacity: Callable[[Stroke, Point], float] | None = None
    # Translucent ink: "darken" (highlighter, pencil) or "airbrush".
    mode: str = "normal"


def _pressure_width(scale: float) -> Callable[[Stroke, Point], float]:
    def width(stroke: Stroke, point: Point) -> float:
        return (
            scale
            * stroke.nominal_width
            * (point.min_factor + (1.0 - point.min_factor) * point.pressure)
        )

    return width


def _fixed_width(scale: float) -> Callable[[Stroke, Point], float]:
    return lambda stroke, _point: scale * stroke.nominal_width


_PEN_STYLES = {
    PEN_FOUNTAIN: _PenStyle(_pressure_width(0.8), False),
    PEN_BALLPOINT: _PenStyle(_fixed_width(0.8), True),
    PEN_FINE: _PenStyle(_pressure_width(0.5), False, mode="darken"),
    PEN_AIRBRUSH: _PenStyle(_fixed_width(1.0), True, mode="airbrush"),
    PEN_HIGHLIGHTER: _PenStyle(_fixed_width(0.95), True, mode="darken"),
    PEN_PENCIL: _PenStyle(
        _fixed_width(1.3),
        False,
        opacity=lambda _stroke, point: min(1.0, max(0.15, 2.4 * point.pressure)),
        mode="darken",
    ),
    PEN_MARKER: _PenStyle(_fixed_width(2.7), True),
    PEN_GEL: _PenStyle(_fixed_width(1.3), True),
}
# Unknown or legacy pens: pressure-sensitive width at the nominal size.
_DEFAULT_STYLE = _PenStyle(_pressure_width(1.0), False)
_MIN_WIDTH = 0.35


def draw_ink(
    output: canvas.Canvas,
    pencil: PencilPage,
    page_ratio: float,
    page_width: float,
    page_height: float,
) -> None:
    logical_height = pencil.canvas_width / page_ratio
    scale_x = page_width / pencil.canvas_width
    scale_y = page_height / logical_height
    transform = _Transform(scale_x, scale_y, page_height)
    output.saveState()
    output.setLineCap(1)
    output.setLineJoin(1)
    for stroke in pencil.strokes:
        if stroke.points:
            style = _PEN_STYLES.get(stroke.pen_type, _DEFAULT_STYLE)
            output.saveState()
            _draw_stroke(output, stroke, style, transform)
            output.restoreState()
    output.restoreState()


@dataclass(frozen=True, slots=True)
class _Transform:
    scale_x: float
    scale_y: float
    page_height: float

    @property
    def width_scale(self) -> float:
        return (self.scale_x + self.scale_y) * 0.5

    def x(self, value: float) -> float:
        return value * self.scale_x

    def y(self, value: float) -> float:
        return self.page_height - value * self.scale_y


def _draw_stroke(
    output: canvas.Canvas, stroke: Stroke, style: _PenStyle, t: _Transform
) -> None:
    if style.mode == "airbrush":
        _draw_airbrush(output, stroke, style, t)
        return

    darken = style.mode == "darken" or stroke.alpha < 1.0
    if darken:
        # Pre-mix the ink with white and paint with the Darken blend mode:
        # identical to translucent ink on white paper, while overlapping
        # pieces of the same stroke do not build up darker spots.
        output.setBlendMode("Darken")

    def set_color(opacity: float) -> None:
        rgb = [channel / 255 for channel in stroke.color]
        if darken:
            rgb = [1.0 - opacity * (1.0 - channel) for channel in rgb]
        output.setStrokeColorRGB(*rgb)
        output.setFillColorRGB(*rgb)

    def width(point: Point) -> float:
        return max(_MIN_WIDTH, style.width(stroke, point)) * t.width_scale

    def opacity(point: Point) -> float:
        factor = style.opacity(stroke, point) if style.opacity else 1.0
        return stroke.alpha * factor

    points = stroke.points
    if len(points) == 1:
        set_color(opacity(points[0]))
        output.circle(
            t.x(points[0].x), t.y(points[0].y), width(points[0]) / 2, stroke=0, fill=1
        )
        return

    if style.constant_width and style.opacity is None:
        set_color(opacity(points[0]))
        output.setLineWidth(width(points[0]))
        output.drawPath(_smooth_path(output, points, t), stroke=1, fill=0)
        return

    for index, (start, end) in enumerate(zip(points[:-1], points[1:], strict=True)):
        set_color((opacity(start) + opacity(end)) / 2)
        output.setLineWidth((width(start) + width(end)) / 2)
        path = output.beginPath()
        path.moveTo(t.x(start.x), t.y(start.y))
        c1x, c1y, c2x, c2y = _control_points(points, index)
        path.curveTo(t.x(c1x), t.y(c1y), t.x(c2x), t.y(c2y), t.x(end.x), t.y(end.y))
        output.drawPath(path, stroke=1, fill=0)


def _draw_airbrush(
    output: canvas.Canvas, stroke: Stroke, style: _PenStyle, t: _Transform
) -> None:
    """Spray paint: translucent soft dabs stamped along the smoothed path.

    Like Huawei's airbrush, dabs overlap, so the core builds up to roughly
    ``1 - (1 - alpha) ** 8``, stroke ends fade out and self-crossings darken.
    """
    diameter = max(_MIN_WIDTH, style.width(stroke, stroke.points[0]))
    spacing = diameter * _AIRBRUSH_SPACING
    # Each dab is a stack of concentric discs; count how many disc layers
    # overlap at the centre line so the core reaches the target opacity.
    radii = [
        diameter / 2 * (1 - (1 - _AIRBRUSH_CORE) * ring / (_AIRBRUSH_RINGS - 1))
        for ring in range(_AIRBRUSH_RINGS)
    ]
    layers = sum(2 * radius for radius in radii) / spacing
    core = 1.0 - (1.0 - stroke.alpha) ** _AIRBRUSH_DABS
    alpha = 1.0 - (1.0 - core) ** (1.0 / layers)
    red, green, blue = (channel / 255 for channel in stroke.color)
    output.setFillColorRGB(red, green, blue)
    output.setFillAlpha(alpha)
    # Fill each disc separately so overlapping dabs blend with each other.
    for x, y in _resample(stroke.points, spacing):
        for radius in radii:
            output.circle(t.x(x), t.y(y), radius * t.width_scale, stroke=0, fill=1)


def _resample(points: tuple[Point, ...], spacing: float) -> list[tuple[float, float]]:
    """Points every ``spacing`` canvas units along the smoothed stroke."""
    samples = [(points[0].x, points[0].y)]
    carried = 0.0
    for index in range(len(points) - 1):
        start, end = points[index], points[index + 1]
        c1x, c1y, c2x, c2y = _control_points(points, index)
        previous = (start.x, start.y)
        for step in range(1, _CURVE_STEPS + 1):
            u = step / _CURVE_STEPS
            v = 1 - u
            current = (
                v**3 * start.x
                + 3 * v * v * u * c1x
                + 3 * v * u * u * c2x
                + u**3 * end.x,
                v**3 * start.y
                + 3 * v * v * u * c1y
                + 3 * v * u * u * c2y
                + u**3 * end.y,
            )
            length = math.dist(previous, current)
            while carried + length >= spacing:
                fraction = (spacing - carried) / length
                previous = (
                    previous[0] + (current[0] - previous[0]) * fraction,
                    previous[1] + (current[1] - previous[1]) * fraction,
                )
                samples.append(previous)
                length = math.dist(previous, current)
                carried = 0.0
            carried += length
            previous = current
    return samples


def _smooth_path(output: canvas.Canvas, points: tuple[Point, ...], t: _Transform):
    path = output.beginPath()
    path.moveTo(t.x(points[0].x), t.y(points[0].y))
    for index in range(len(points) - 1):
        end = points[index + 1]
        c1x, c1y, c2x, c2y = _control_points(points, index)
        path.curveTo(t.x(c1x), t.y(c1y), t.x(c2x), t.y(c2y), t.x(end.x), t.y(end.y))
    return path


def _control_points(
    points: tuple[Point, ...], index: int
) -> tuple[float, float, float, float]:
    """Catmull-Rom control points for the segment ``index -> index + 1``."""
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
