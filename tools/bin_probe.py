#!/usr/bin/env python3
"""Forensics-first probe for Huawei PENCILENGINE .bin files."""

from __future__ import annotations

import argparse
import json
import math
import struct
from collections import Counter
from pathlib import Path
from typing import Any


MAGIC = b"PENCILENGINE"


def read_u16(data: bytes, off: int, endian: str) -> int:
    return int.from_bytes(data[off : off + 2], endian, signed=False)


def read_u32(data: bytes, off: int, endian: str) -> int:
    return int.from_bytes(data[off : off + 4], endian, signed=False)


def read_f32(data: bytes, off: int, endian: str) -> float:
    fmt = ">f" if endian == "big" else "<f"
    return struct.unpack(fmt, data[off : off + 4])[0]


def ascii_safe(chunk: bytes) -> str:
    return "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)


def hexdump_lines(data: bytes, length: int = 256) -> list[str]:
    out = []
    view = data[:length]
    for off in range(0, len(view), 16):
        c = view[off : off + 16]
        hex_part = " ".join(f"{b:02x}" for b in c)
        out.append(f"{off:08x}  {hex_part:<47}  {ascii_safe(c)}")
    return out


def endian_hints(data: bytes) -> dict[str, Any]:
    sample_limit = min(len(data), 4096)
    offsets4 = list(range(0, sample_limit - 3, 4))

    def score(endian: str) -> dict[str, Any]:
        small_u32 = 0
        plausible_len = 0
        plausible_float = 0
        for off in offsets4:
            u32 = read_u32(data, off, endian)
            if u32 <= 1_000_000:
                small_u32 += 1
            if 0 < u32 <= len(data) - off - 4:
                plausible_len += 1

            f = read_f32(data, off, endian)
            if math.isfinite(f) and abs(f) <= 100_000:
                plausible_float += 1
        n = len(offsets4) or 1
        return {
            "small_u32_ratio": small_u32 / n,
            "plausible_len_ratio": plausible_len / n,
            "plausible_float_ratio": plausible_float / n,
            "score": (small_u32 + plausible_len + plausible_float) / (3 * n),
        }

    be = score("big")
    le = score("little")
    likely = "big-endian" if be["score"] >= le["score"] else "little-endian"
    return {"big": be, "little": le, "likely": likely}


def scan_markers(data: bytes) -> dict[str, Any]:
    markers: dict[str, Any] = {}
    markers["magic_offsets"] = [i for i in range(len(data)) if data.startswith(MAGIC, i)]

    words = Counter(data[i : i + 4] for i in range(0, len(data) - 3, 4))
    markers["repeated_u32_words"] = [
        {"word_hex": w.hex(), "count": c}
        for w, c in words.most_common(20)
        if c > 2
    ]

    ascii_runs = []
    i = 0
    while i < len(data):
        if 32 <= data[i] <= 126:
            j = i + 1
            while j < len(data) and 32 <= data[j] <= 126:
                j += 1
            if j - i >= 4:
                ascii_runs.append({"offset": i, "text": data[i:j].decode("ascii", errors="ignore")})
            i = j
        i += 1
    markers["ascii_runs"] = ascii_runs[:40]
    return markers


def detect_length_prefixed(data: bytes) -> list[dict[str, Any]]:
    out = []
    for off in range(0, len(data) - 8, 4):
        for endian in ("big", "little"):
            n = read_u32(data, off, endian)
            if 8 <= n <= 512 and off + 4 + n <= len(data):
                sig = data[off + 4 : off + 12]
                out.append(
                    {
                        "offset": off,
                        "endianness": endian,
                        "length": n,
                        "signature_hex": sig.hex(),
                    }
                )
    out.sort(key=lambda r: (r["offset"], r["endianness"], r["length"]))
    dedup = []
    seen = set()
    for row in out:
        k = (row["offset"], row["endianness"], row["length"])
        if k in seen:
            continue
        seen.add(k)
        dedup.append(row)
    return dedup[:200]


def detect_chunk_candidates(data: bytes) -> list[dict[str, Any]]:
    candidates = []
    for off in range(0, len(data) - 12, 4):
        count_be = read_u32(data, off, "big")
        stride_be = read_u32(data, off + 4, "big")
        if 1 <= count_be <= 200_000 and 4 <= stride_be <= 256:
            block = count_be * stride_be
            end = off + 8 + block
            if end <= len(data):
                sig = data[off + 8 : off + 16].hex()
                candidates.append(
                    {
                        "offset": off,
                        "endianness": "big",
                        "count": count_be,
                        "stride": stride_be,
                        "length_guess": block,
                        "end_offset": end,
                        "signature_hex": sig,
                    }
                )

    # Keep map concise: earliest non-overlapping candidates prioritized.
    candidates.sort(key=lambda c: (c["offset"], c["length_guess"]))
    selected = []
    last_end = -1
    for cand in candidates:
        if cand["offset"] < last_end:
            continue
        selected.append(cand)
        last_end = cand["end_offset"]
        if len(selected) >= 80:
            break
    return selected


def probe(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    info: dict[str, Any] = {
        "file": str(path),
        "size": len(data),
        "magic_ascii": data[:12].decode("ascii", errors="replace"),
        "first_256_hexdump": hexdump_lines(data, 256),
        "endian_hints": endian_hints(data),
        "marker_scan": scan_markers(data),
        "length_prefixed_candidates": detect_length_prefixed(data),
        "chunk_map_candidates": detect_chunk_candidates(data),
    }
    return info


def print_report(report: dict[str, Any]) -> None:
    print(f"File: {report['file']}")
    print(f"Size: {report['size']} bytes")
    print(f"Magic: {report['magic_ascii']!r}")
    print("\nFirst 256 bytes (hex + ASCII):")
    for line in report["first_256_hexdump"]:
        print(line)

    eh = report["endian_hints"]
    print("\nEndian-ness hints:")
    print(f"  likely={eh['likely']}")
    for k in ("big", "little"):
        s = eh[k]
        print(
            f"  {k}: score={s['score']:.3f} "
            f"small_u32={s['small_u32_ratio']:.3f} "
            f"len={s['plausible_len_ratio']:.3f} "
            f"float={s['plausible_float_ratio']:.3f}"
        )

    ms = report["marker_scan"]
    print("\nRepeated marker scan:")
    print(f"  magic offsets: {ms['magic_offsets']}")
    print("  top repeated 4-byte words:")
    for row in ms["repeated_u32_words"][:10]:
        print(f"    {row['word_hex']} x {row['count']}")

    print("\nLength-prefix candidates (first 25):")
    for row in report["length_prefixed_candidates"][:25]:
        print(
            f"  off=0x{row['offset']:08x} endian={row['endianness']:<6} "
            f"len={row['length']:<4} sig={row['signature_hex']}"
        )

    print("\nCandidate chunk map (count/stride headers):")
    for row in report["chunk_map_candidates"][:25]:
        print(
            f"  off=0x{row['offset']:08x} {row['endianness']:<3} "
            f"count={row['count']:<6} stride={row['stride']:<4} "
            f"len≈{row['length_guess']:<8} end=0x{row['end_offset']:08x} "
            f"sig={row['signature_hex']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Path to a PENCILENGINE .bin file")
    parser.add_argument("--json-out", type=Path, help="Optional path to save probe report JSON")
    args = parser.parse_args()

    report = probe(args.path)
    print_report(report)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote JSON report: {args.json_out}")


if __name__ == "__main__":
    main()
