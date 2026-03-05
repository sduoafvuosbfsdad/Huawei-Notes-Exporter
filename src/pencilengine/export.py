"""Export helpers for parsed PENCILENGINE data."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .parser import ParsedBin, parse_pencilengine_bin


def parsed_to_stroke_document(parsed: ParsedBin) -> dict[str, Any]:
    strokes = []
    for s in parsed.strokes:
        points = []
        for p in s.points:
            points.append(
                {
                    "x": p.x,
                    "y": p.y,
                    "t": p.t_u32,
                    "pressure": p.f3,
                    "width_base": p.f4,
                    "size_hint": p.f5,
                    "opacity_hint": p.f6,
                    "state": p.u7,
                    "seq": p.f8,
                    "offset": p.offset,
                    "raw_hex": p.raw_hex,
                }
            )
        strokes.append(
            {
                "index": s.stroke_index,
                "offset": s.offset,
                "total_length": s.total_length,
                "stroke_id_u32": s.stroke_id_u32,
                "stroke_uuid_hex": s.stroke_uuid_hex,
                "point_count": s.point_count,
                "point_stride": s.point_stride,
                "point_data_offset": s.point_data_offset,
                "metadata_words": s.metadata_words,
                "metadata_floats": s.metadata_floats,
                "points": points,
            }
        )

    xs = [p["x"] for s in strokes for p in s["points"]]
    ys = [p["y"] for s in strokes for p in s["points"]]
    bbox = {
        "min_x": min(xs) if xs else None,
        "min_y": min(ys) if ys else None,
        "max_x": max(xs) if xs else None,
        "max_y": max(ys) if ys else None,
    }

    return {
        "format": "pencilengine-strokes-v0",
        "source_bin": parsed.path,
        "source_size": parsed.size,
        "header": {
            "magic": parsed.header.magic,
            "header_len_u32": parsed.header.header_len_u32,
            "version_u16_a": parsed.header.version_u16_a,
            "version_u16_b": parsed.header.version_u16_b,
            "global_header_size": parsed.header.global_header_size,
            "raw_hex": parsed.header.raw_hex,
        },
        "global_words": parsed.global_words,
        "first_stroke_offset": parsed.first_stroke_offset,
        "stroke_count": len(strokes),
        "total_points": sum(s["point_count"] for s in strokes),
        "bbox": bbox,
        "strokes": strokes,
        "trailing_offset": parsed.trailing_offset,
        "trailing_hex": parsed.trailing_hex,
    }


def extract_strokes_to_document(path: str | Path) -> dict[str, Any]:
    parsed = parse_pencilengine_bin(path)
    return parsed_to_stroke_document(parsed)
