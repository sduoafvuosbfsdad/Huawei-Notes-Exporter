"""Stroke rendering for extracted PENCILENGINE JSON."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any


def infer_canvas(stroke_doc: dict[str, Any], padding: int = 16) -> tuple[int, int, float, float]:
    bbox = stroke_doc.get("bbox", {})
    min_x = bbox.get("min_x")
    min_y = bbox.get("min_y")
    max_x = bbox.get("max_x")
    max_y = bbox.get("max_y")
    if min_x is None or min_y is None or max_x is None or max_y is None:
        return 1024, 1024, 0.0, 0.0
    width = int(math.ceil(max_x - min_x + 2 * padding))
    height = int(math.ceil(max_y - min_y + 2 * padding))
    dx = -min_x + padding
    dy = -min_y + padding
    return width, height, dx, dy


def _point_width(point: dict[str, Any], width_scale: float) -> float:
    pressure = float(point.get("pressure", 0.2))
    size_hint = float(point.get("size_hint", point.get("width_base", 2.0)))
    width = pressure * size_hint * width_scale
    return max(1.0, width)


def _draw_disk(alpha: bytearray, width: int, height: int, cx: float, cy: float, radius: float) -> None:
    if radius <= 0.6:
        x = int(round(cx))
        y = int(round(cy))
        if 0 <= x < width and 0 <= y < height:
            idx = y * width + x
            alpha[idx] = 255
        return

    r2 = radius * radius
    xmin = max(0, int(math.floor(cx - radius)))
    xmax = min(width - 1, int(math.ceil(cx + radius)))
    ymin = max(0, int(math.floor(cy - radius)))
    ymax = min(height - 1, int(math.ceil(cy + radius)))
    for y in range(ymin, ymax + 1):
        dy = (y + 0.5) - cy
        row = y * width
        for x in range(xmin, xmax + 1):
            dx = (x + 0.5) - cx
            if (dx * dx) + (dy * dy) <= r2:
                alpha[row + x] = 255


def _draw_segment(
    alpha: bytearray,
    width: int,
    height: int,
    x0: float,
    y0: float,
    r0: float,
    x1: float,
    y1: float,
    r1: float,
) -> None:
    dx = x1 - x0
    dy = y1 - y0
    dist = math.hypot(dx, dy)
    steps = max(1, int(dist * 1.5))
    for i in range(steps + 1):
        t = i / steps
        x = x0 + (dx * t)
        y = y0 + (dy * t)
        r = r0 + ((r1 - r0) * t)
        _draw_disk(alpha, width, height, x, y, r)


def render_alpha(
    stroke_doc: dict[str, Any],
    *,
    width: int,
    height: int,
    scale: float = 1.0,
    dx: float = 0.0,
    dy: float = 0.0,
    width_scale: float = 0.5,
) -> bytearray:
    alpha = bytearray(width * height)
    for stroke in stroke_doc.get("strokes", []):
        pts = stroke.get("points", [])
        if not pts:
            continue
        prev = None
        for pt in pts:
            x = (float(pt["x"]) * scale) + dx
            y = (float(pt["y"]) * scale) + dy
            radius = _point_width(pt, width_scale) * scale * 0.5
            if prev is None:
                _draw_disk(alpha, width, height, x, y, radius)
            else:
                _draw_segment(
                    alpha,
                    width,
                    height,
                    prev[0],
                    prev[1],
                    prev[2],
                    x,
                    y,
                    radius,
                )
            prev = (x, y, radius)
    return alpha


def alpha_to_rgba(alpha: bytes, *, color: tuple[int, int, int] = (0, 0, 0)) -> bytes:
    rgba = bytearray(len(alpha) * 4)
    r, g, b = color
    for i, a in enumerate(alpha):
        base = i * 4
        rgba[base] = r
        rgba[base + 1] = g
        rgba[base + 2] = b
        rgba[base + 3] = a
    return bytes(rgba)


def write_svg(
    stroke_doc: dict[str, Any],
    out_path: str | Path,
    *,
    width: int,
    height: int,
    scale: float = 1.0,
    dx: float = 0.0,
    dy: float = 0.0,
    width_scale: float = 0.5,
    stroke_color: str = "#000000",
) -> None:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        ),
        '<rect width="100%" height="100%" fill="none"/>',
    ]
    for stroke in stroke_doc.get("strokes", []):
        pts = stroke.get("points", [])
        if len(pts) < 2:
            continue
        avg_width = 0.0
        for pt in pts:
            avg_width += _point_width(pt, width_scale) * scale
        avg_width /= len(pts)
        d_parts = []
        for i, pt in enumerate(pts):
            x = (float(pt["x"]) * scale) + dx
            y = (float(pt["y"]) * scale) + dy
            cmd = "M" if i == 0 else "L"
            d_parts.append(f"{cmd} {x:.3f} {y:.3f}")
        d = " ".join(d_parts)
        lines.append(
            f'<path d="{d}" fill="none" stroke="{stroke_color}" '
            f'stroke-width="{max(1.0, avg_width):.3f}" stroke-linecap="round" '
            f'stroke-linejoin="round"/>'
        )
    lines.append("</svg>")
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
