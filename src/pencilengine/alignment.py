"""Image alignment utilities for validating decoded strokes."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from .render import render_alpha


@dataclass
class Transform:
    scale: float
    dx: float
    dy: float
    score: float


def build_dark_mask(preview_rgba: bytes, threshold: int = 80) -> bytearray:
    mask = bytearray(len(preview_rgba) // 4)
    j = 0
    for i in range(0, len(preview_rgba), 4):
        r = preview_rgba[i]
        g = preview_rgba[i + 1]
        b = preview_rgba[i + 2]
        mask[j] = 1 if (r < threshold and g < threshold and b < threshold) else 0
        j += 1
    return mask


def collect_sample_points(stroke_doc: dict[str, Any], step: int = 1) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    idx = 0
    for stroke in stroke_doc.get("strokes", []):
        for pt in stroke.get("points", []):
            if (idx % step) == 0:
                pts.append((float(pt["x"]), float(pt["y"])))
            idx += 1
    return pts


def score_transform(
    points: list[tuple[float, float]],
    dark_mask: bytes,
    width: int,
    height: int,
    *,
    scale: float,
    dx: float,
    dy: float,
) -> float:
    if not points:
        return 0.0
    good = 0
    total = 0
    for x, y in points:
        px = int(round((x * scale) + dx))
        py = int(round((y * scale) + dy))
        if 0 <= px < width and 0 <= py < height:
            total += 1
            if dark_mask[(py * width) + px]:
                good += 1
    if total == 0:
        return 0.0
    return good / total


def _frange(start: float, stop: float, step: float) -> list[float]:
    vals = []
    i = 0
    while True:
        v = start + (i * step)
        if v > stop + 1e-12:
            break
        vals.append(v)
        i += 1
    return vals


def search_scale_translate(
    stroke_doc: dict[str, Any],
    dark_mask: bytes,
    width: int,
    height: int,
    *,
    sample_step: int = 2,
    scale_range: tuple[float, float] = (0.7, 1.2),
    shift_range: tuple[float, float] = (-120.0, 120.0),
) -> Transform:
    points = collect_sample_points(stroke_doc, step=sample_step)
    if not points:
        return Transform(scale=1.0, dx=0.0, dy=0.0, score=0.0)

    best = Transform(scale=1.0, dx=0.0, dy=0.0, score=-1.0)

    # Coarse grid.
    coarse_scales = _frange(scale_range[0], scale_range[1], 0.02)
    coarse_shifts = _frange(shift_range[0], shift_range[1], 12.0)
    for s in coarse_scales:
        for dx in coarse_shifts:
            for dy in coarse_shifts:
                score = score_transform(points, dark_mask, width, height, scale=s, dx=dx, dy=dy)
                if score > best.score:
                    best = Transform(scale=s, dx=dx, dy=dy, score=score)

    # Medium refinement around coarse best.
    med_scales = _frange(best.scale - 0.02, best.scale + 0.02, 0.004)
    med_shifts_x = _frange(best.dx - 12.0, best.dx + 12.0, 2.0)
    med_shifts_y = _frange(best.dy - 12.0, best.dy + 12.0, 2.0)
    for s in med_scales:
        for dx in med_shifts_x:
            for dy in med_shifts_y:
                score = score_transform(points, dark_mask, width, height, scale=s, dx=dx, dy=dy)
                if score > best.score:
                    best = Transform(scale=s, dx=dx, dy=dy, score=score)

    # Fine refinement.
    fine_scales = _frange(best.scale - 0.004, best.scale + 0.004, 0.001)
    fine_shifts_x = _frange(best.dx - 2.0, best.dx + 2.0, 0.5)
    fine_shifts_y = _frange(best.dy - 2.0, best.dy + 2.0, 0.5)
    for s in fine_scales:
        for dx in fine_shifts_x:
            for dy in fine_shifts_y:
                score = score_transform(points, dark_mask, width, height, scale=s, dx=dx, dy=dy)
                if score > best.score:
                    best = Transform(scale=s, dx=dx, dy=dy, score=score)

    return best


def compare_masks(render_mask: bytes, dark_mask: bytes) -> dict[str, float]:
    intersection = 0
    render_px = 0
    dark_px = 0
    for a, d in zip(render_mask, dark_mask):
        r = 1 if a else 0
        render_px += r
        dark_px += d
        if r and d:
            intersection += 1
    union = render_px + dark_px - intersection
    precision = intersection / render_px if render_px else 0.0
    recall = intersection / dark_px if dark_px else 0.0
    iou = intersection / union if union else 0.0
    return {
        "intersection": float(intersection),
        "render_pixels": float(render_px),
        "dark_pixels": float(dark_px),
        "precision": precision,
        "recall": recall,
        "iou": iou,
        "alignment_error": 1.0 - precision,
    }


def overlay_preview_with_mask(preview_rgba: bytes, mask: bytes) -> bytes:
    out = bytearray(preview_rgba)
    for i, a in enumerate(mask):
        if not a:
            continue
        p = i * 4
        # Blend red on top for visual validation.
        out[p] = min(255, int((0.35 * out[p]) + (0.65 * 255)))
        out[p + 1] = int(0.35 * out[p + 1])
        out[p + 2] = int(0.35 * out[p + 2])
        out[p + 3] = 255
    return bytes(out)


def validate_against_preview(
    stroke_doc: dict[str, Any],
    *,
    preview_rgba: bytes,
    preview_width: int,
    preview_height: int,
    dark_threshold: int = 80,
    width_scale: float = 0.5,
) -> tuple[Transform, dict[str, float], bytes, bytes]:
    dark_mask = build_dark_mask(preview_rgba, threshold=dark_threshold)
    transform = search_scale_translate(
        stroke_doc,
        dark_mask,
        preview_width,
        preview_height,
    )

    render_mask = render_alpha(
        stroke_doc,
        width=preview_width,
        height=preview_height,
        scale=transform.scale,
        dx=transform.dx,
        dy=transform.dy,
        width_scale=width_scale,
    )
    metrics = compare_masks(render_mask, dark_mask)
    overlay = overlay_preview_with_mask(preview_rgba, render_mask)
    return transform, metrics, bytes(render_mask), overlay
