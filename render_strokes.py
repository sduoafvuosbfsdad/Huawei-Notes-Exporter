#!/usr/bin/env python3
"""Render extracted stroke JSON to transparent PNG (and optional SVG)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.pencilengine.png import write_png_rgba
from src.pencilengine.render import alpha_to_rgba, infer_canvas, render_alpha, write_svg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("strokes_json", type=Path, help="JSON from extract_strokes.py")
    parser.add_argument("--out", required=True, type=Path, help="Output PNG path")
    parser.add_argument("--svg-out", type=Path, help="Optional output SVG path")
    parser.add_argument("--width", type=int, help="Canvas width")
    parser.add_argument("--height", type=int, help="Canvas height")
    parser.add_argument("--scale", type=float, default=1.0, help="Coordinate scale")
    parser.add_argument("--dx", type=float, help="X translation")
    parser.add_argument("--dy", type=float, help="Y translation")
    parser.add_argument(
        "--width-scale",
        type=float,
        default=0.5,
        help="Multiplies pressure-based stroke width",
    )
    args = parser.parse_args()

    doc = json.loads(args.strokes_json.read_text(encoding="utf-8"))
    if args.width is None or args.height is None or args.dx is None or args.dy is None:
        inf_w, inf_h, inf_dx, inf_dy = infer_canvas(doc)
    else:
        inf_w, inf_h, inf_dx, inf_dy = args.width, args.height, 0.0, 0.0

    width = args.width if args.width is not None else inf_w
    height = args.height if args.height is not None else inf_h
    dx = args.dx if args.dx is not None else inf_dx
    dy = args.dy if args.dy is not None else inf_dy

    alpha = render_alpha(
        doc,
        width=width,
        height=height,
        scale=args.scale,
        dx=dx,
        dy=dy,
        width_scale=args.width_scale,
    )
    rgba = alpha_to_rgba(alpha, color=(0, 0, 0))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_png_rgba(args.out, width, height, rgba)
    print(f"Wrote PNG: {args.out} ({width}x{height})")
    print(
        f"transform scale={args.scale:.6f} dx={dx:.3f} dy={dy:.3f} "
        f"width_scale={args.width_scale:.3f}"
    )

    if args.svg_out:
        args.svg_out.parent.mkdir(parents=True, exist_ok=True)
        write_svg(
            doc,
            args.svg_out,
            width=width,
            height=height,
            scale=args.scale,
            dx=dx,
            dy=dy,
            width_scale=args.width_scale,
        )
        print(f"Wrote SVG: {args.svg_out}")


if __name__ == "__main__":
    main()
