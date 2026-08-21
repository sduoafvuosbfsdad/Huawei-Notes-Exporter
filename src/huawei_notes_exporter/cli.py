from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .archive import DEFAULT_MAX_ENTRIES, DEFAULT_MAX_UNCOMPRESSED_BYTES
from .errors import HiNoteError
from .pdf import convert_hinote


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hinote-export",
        description=(
            "Export a Huawei Notes .hinote archive to PDF using the embedded "
            "document and decoded native PENCILENGINE vector strokes."
        ),
    )
    parser.add_argument("input", type=Path, help="Huawei Notes .hinote archive")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="output PDF (default: INPUT with a .pdf suffix)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="replace the output file if it already exists",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="print conversion statistics as JSON",
    )
    parser.add_argument(
        "--max-entries",
        type=_positive_int,
        default=DEFAULT_MAX_ENTRIES,
        metavar="N",
        help=f"maximum archive entries (default: {DEFAULT_MAX_ENTRIES})",
    )
    parser.add_argument(
        "--max-uncompressed-bytes",
        type=_positive_int,
        default=DEFAULT_MAX_UNCOMPRESSED_BYTES,
        metavar="N",
        help=(
            "maximum total uncompressed archive size "
            f"(default: {DEFAULT_MAX_UNCOMPRESSED_BYTES})"
        ),
    )
    parser.add_argument("--version", action="version", version=_version_string())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    source = args.input.expanduser()
    destination = (args.output or source.with_suffix(".pdf")).expanduser()

    try:
        _validate_paths(source, destination, force=args.force)
        result = _atomic_convert(
            source,
            destination,
            max_entries=args.max_entries,
            max_uncompressed_bytes=args.max_uncompressed_bytes,
        )
    except (HiNoteError, OSError) as exc:
        print(f"hinote-export: error: {exc}", file=sys.stderr)
        return 1

    if args.json_output:
        payload = {"output": str(destination), **result.as_dict()}
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        print(f"Exported {destination}")
        print(
            f"{result.pages} pages, {result.vector_pages} with vector ink, "
            f"{result.strokes} strokes, {result.points} points"
        )
    return 0


def _validate_paths(source: Path, destination: Path, *, force: bool) -> None:
    if not source.is_file():
        raise HiNoteError(f"Input file does not exist: {source}")
    if source.resolve() == destination.resolve():
        raise HiNoteError("Input and output paths must be different.")
    if not destination.parent.is_dir():
        raise HiNoteError(f"Output directory does not exist: {destination.parent}")
    if destination.exists() and not force:
        raise HiNoteError(f"Output already exists: {destination} (use --force)")


def _atomic_convert(
    source: Path,
    destination: Path,
    *,
    max_entries: int,
    max_uncompressed_bytes: int,
):
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        result = convert_hinote(
            source,
            temporary,
            max_entries=max_entries,
            max_uncompressed_bytes=max_uncompressed_bytes,
        )
        temporary.replace(destination)
        return result
    finally:
        temporary.unlink(missing_ok=True)


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def _version_string() -> str:
    try:
        package_version = version("huawei-notes-exporter")
    except PackageNotFoundError:
        package_version = "development"
    return f"%(prog)s {package_version}"


if __name__ == "__main__":
    raise SystemExit(main())
