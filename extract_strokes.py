#!/usr/bin/env python3
"""Extract Huawei PENCILENGINE strokes into an open JSON document."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.pencilengine.export import extract_strokes_to_document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path_to_bin", type=Path, help="Path to PENCILENGINE .bin")
    parser.add_argument("--out", required=True, type=Path, help="Output JSON path")
    args = parser.parse_args()

    doc = extract_strokes_to_document(args.path_to_bin)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2), encoding="utf-8")

    bbox = doc["bbox"]
    print(f"Wrote: {args.out}")
    print(f"source_bin={doc['source_bin']} size={doc['source_size']}")
    print(f"first_stroke_offset=0x{doc['first_stroke_offset']:x}")
    print(f"stroke_count={doc['stroke_count']} total_points={doc['total_points']}")
    print(
        "bbox="
        f"({bbox['min_x']:.3f},{bbox['min_y']:.3f}).."
        f"({bbox['max_x']:.3f},{bbox['max_y']:.3f})"
    )
    print(f"trailing_offset=0x{doc['trailing_offset']:x}")


if __name__ == "__main__":
    main()
