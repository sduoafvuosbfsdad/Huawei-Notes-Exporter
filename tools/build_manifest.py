#!/usr/bin/env python3
"""Build a compact manifest from a Huawei Notes unzipped export."""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from typing import Any


def load_gz_json(path: Path) -> dict[str, Any]:
    return json.loads(gzip.decompress(path.read_bytes()))


def page_entry(page_path: Path) -> dict[str, Any]:
    obj = load_gz_json(page_path)
    content = obj["customNotePageContent"]
    file_names = [f["name"] for f in obj.get("fileList", [])]

    bin_name = None
    for attach in content.get("attachment", []):
        if attach.get("attachType") == 0:
            fp = attach.get("filePath") or ""
            bin_name = Path(fp).name if fp else None
            if bin_name:
                break

    preview_name = next((n for n in file_names if n.lower().endswith(".png")), None)

    return {
        "pageId": content.get("id"),
        "pageMetadataFile": page_path.name,
        "pageNumber": content.get("pageNumber"),
        "bkgAttachmentIndex": content.get("bkgAttachmentIndex"),
        "previewPng": preview_name,
        "inkBin": bin_name,
    }


def build_manifest(unzipped_dir: Path) -> dict[str, Any]:
    note_files = sorted(unzipped_dir.glob("*.jhinote"))
    if not note_files:
        raise FileNotFoundError(f"No root .jhinote found under: {unzipped_dir}")

    root_obj = load_gz_json(note_files[0])
    note = root_obj["customNoteContent"]
    note_id = note.get("id")

    pages_dir = unzipped_dir / "pages"
    pages = [page_entry(p) for p in sorted(pages_dir.glob("*.jhinote"))]
    pages.sort(key=lambda p: (p["pageNumber"] is None, p["pageNumber"]))

    return {
        "noteId": note_id,
        "rootMetadataFile": note_files[0].name,
        "rootFileList": [f["name"] for f in root_obj.get("fileList", [])],
        "pages": pages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--unzipped-dir",
        default="data/unzipped",
        type=Path,
        help="Directory containing extracted .hinote files.",
    )
    parser.add_argument(
        "--out",
        default="data/manifest.json",
        type=Path,
        help="Path to write manifest JSON.",
    )
    args = parser.parse_args()

    manifest = build_manifest(args.unzipped_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote manifest: {args.out}")
    print(f"noteId={manifest['noteId']} pages={len(manifest['pages'])}")
    linked = [p for p in manifest["pages"] if p["inkBin"] and p["previewPng"]]
    print(f"pages_with_ink_and_preview={len(linked)}")
    for p in linked:
        print(
            f"  page={p['pageNumber']} bkg={p['bkgAttachmentIndex']} "
            f"bin={p['inkBin']} preview={p['previewPng']}"
        )


if __name__ == "__main__":
    main()
