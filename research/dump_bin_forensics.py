#!/usr/bin/env python3
"""Generate offline forensic dumps for PENCILENGINE bins."""

from __future__ import annotations

import argparse
import json
import math
import struct
from collections import Counter
from pathlib import Path
from typing import Any


def shannon_entropy(chunk: bytes) -> float:
    if not chunk:
        return 0.0
    c = Counter(chunk)
    n = len(chunk)
    h = 0.0
    for count in c.values():
        p = count / n
        h -= p * math.log2(p)
    return h


def candidate_reads(data: bytes, max_offset: int = 0x200) -> list[dict[str, Any]]:
    rows = []
    for off in range(0, min(len(data) - 4, max_offset), 4):
        raw = data[off : off + 4]
        rows.append(
            {
                "offset": off,
                "raw_hex": raw.hex(),
                "u32_be": int.from_bytes(raw, "big"),
                "u32_le": int.from_bytes(raw, "little"),
                "f32_be": struct.unpack(">f", raw)[0],
                "f32_le": struct.unpack("<f", raw)[0],
            }
        )
    return rows


def entropy_windows(data: bytes, window: int = 1024) -> list[dict[str, Any]]:
    out = []
    for off in range(0, len(data), window):
        chunk = data[off : off + window]
        out.append(
            {
                "offset": off,
                "length": len(chunk),
                "entropy": shannon_entropy(chunk),
                "zero_ratio": chunk.count(0) / len(chunk),
            }
        )
    return out


def find_stroke_chunks(data: bytes) -> list[dict[str, Any]]:
    sig = bytes.fromhex("000000440000003000000074")
    out = []
    i = 0
    while True:
        off = data.find(sig, i)
        if off < 0:
            break
        # Hypothesis: point_count and stride are at +0x88/+0x8c relative to this signature.
        if off + 0x90 <= len(data):
            count = int.from_bytes(data[off + 0x88 : off + 0x8C], "big")
            stride = int.from_bytes(data[off + 0x8C : off + 0x90], "big")
            if 1 <= count <= 200_000 and stride == 0x24:
                point_data_off = off + 0x98
                point_data_len = count * stride
                trailer_off = point_data_off + point_data_len
                out.append(
                    {
                        "offset": off,
                        "count": count,
                        "stride": stride,
                        "point_data_offset": point_data_off,
                        "point_data_length": point_data_len,
                        "trailer_offset": trailer_off,
                    }
                )
        i = off + 1
    return out


def summarize_record_fields(data: bytes, strokes: list[dict[str, Any]]) -> dict[str, Any]:
    # Interpret each 0x24-byte point as: >ffIffffIf (hypothesis only).
    field_stats: dict[str, dict[str, float]] = {}
    names = ["x", "y", "t_u32", "f3", "f4", "f5", "f6", "u7", "f8"]
    for name in names:
        field_stats[name] = {"min": float("inf"), "max": float("-inf")}

    def update(name: str, value: float) -> None:
        field_stats[name]["min"] = min(field_stats[name]["min"], float(value))
        field_stats[name]["max"] = max(field_stats[name]["max"], float(value))

    monotonic_t = 0
    total_strokes = 0
    for s in strokes:
        off = s["point_data_offset"]
        count = s["count"]
        stride = s["stride"]
        t_prev = None
        ok = True
        for i in range(count):
            rec = data[off + i * stride : off + (i + 1) * stride]
            if len(rec) != 0x24:
                ok = False
                break
            x, y, t_u32, f3, f4, f5, f6, u7, f8 = struct.unpack(">ffIffffIf", rec)
            vals = [x, y, t_u32, f3, f4, f5, f6, u7, f8]
            for n, v in zip(names, vals):
                update(n, float(v))
            if t_prev is not None and t_u32 < t_prev:
                ok = False
            t_prev = t_u32
        total_strokes += 1
        if ok:
            monotonic_t += 1

    for n in names:
        if field_stats[n]["min"] == float("inf"):
            field_stats[n]["min"] = None
            field_stats[n]["max"] = None

    return {
        "field_ranges": field_stats,
        "monotonic_t_strokes": monotonic_t,
        "total_strokes": total_strokes,
    }


def build_report(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    strokes = find_stroke_chunks(data)
    report = {
        "file": str(path),
        "size": len(data),
        "header_hex_256": data[:256].hex(),
        "candidate_reads_first_0x200": candidate_reads(data, max_offset=0x200),
        "entropy_windows_1k": entropy_windows(data, 1024),
        "repeating_signature_44_30_74_count": len(strokes),
        "stroke_chunk_candidates": strokes,
        "point_record_hypothesis": summarize_record_fields(data, strokes),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    report = build_report(args.path)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {args.out}")
    print(f"stroke_chunk_candidates={report['repeating_signature_44_30_74_count']}")
    pr = report["point_record_hypothesis"]
    print(f"monotonic_t_strokes={pr['monotonic_t_strokes']}/{pr['total_strokes']}")


if __name__ == "__main__":
    main()
