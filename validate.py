#!/usr/bin/env python3
"""Validate rendered strokes against a preview PNG with scale+translate search."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.pencilengine.alignment import validate_against_preview
from src.pencilengine.png import read_png_rgba, write_png_rgba
from src.pencilengine.render import alpha_to_rgba


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("strokes_json", type=Path, help="JSON from extract_strokes.py")
    parser.add_argument("--preview", required=True, type=Path, help="Ground-truth preview PNG")
    parser.add_argument("--out", required=True, type=Path, help="Overlay PNG output")
    parser.add_argument(
        "--ink-out",
        type=Path,
        help="Optional transformed transparent ink render PNG",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        help="Optional JSON report output path",
    )
    parser.add_argument(
        "--dark-threshold",
        type=int,
        default=80,
        help="Dark pixel threshold used to extract ink/text mask from preview",
    )
    parser.add_argument(
        "--width-scale",
        type=float,
        default=0.5,
        help="Multiplies pressure-based stroke width during rasterization",
    )
    args = parser.parse_args()

    doc = json.loads(args.strokes_json.read_text(encoding="utf-8"))
    w, h, preview = read_png_rgba(args.preview)
    transform, metrics, render_mask, overlay = validate_against_preview(
        doc,
        preview_rgba=bytes(preview),
        preview_width=w,
        preview_height=h,
        dark_threshold=args.dark_threshold,
        width_scale=args.width_scale,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_png_rgba(args.out, w, h, overlay)
    if args.ink_out:
        args.ink_out.parent.mkdir(parents=True, exist_ok=True)
        ink_rgba = alpha_to_rgba(render_mask, color=(0, 0, 0))
        write_png_rgba(args.ink_out, w, h, ink_rgba)

    report = {
        "preview": str(args.preview),
        "transform": {
            "scale": transform.scale,
            "dx": transform.dx,
            "dy": transform.dy,
            "point_match_score": transform.score,
        },
        "metrics": metrics,
        "dark_threshold": args.dark_threshold,
        "width_scale": args.width_scale,
    }
    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    print(f"Wrote overlay: {args.out}")
    if args.ink_out:
        print(f"Wrote transformed ink: {args.ink_out}")
    if args.report_out:
        print(f"Wrote report: {args.report_out}")


if __name__ == "__main__":
    main()
