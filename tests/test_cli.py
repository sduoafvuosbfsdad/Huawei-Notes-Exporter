from __future__ import annotations

import json
from pathlib import Path

from pypdf import PdfReader

from huawei_notes_exporter.cli import main


def _write_archive(path: Path, payload: bytes) -> Path:
    path.write_bytes(payload)
    return path


def test_cli_exports_default_output(
    tmp_path: Path, synthetic_hinote: bytes, capsys
) -> None:
    source = _write_archive(tmp_path / "note.hinote", synthetic_hinote)

    assert main([str(source)]) == 0

    output = tmp_path / "note.pdf"
    assert output.is_file()
    assert len(PdfReader(output).pages) == 1
    assert "1 pages, 1 with vector ink" in capsys.readouterr().out


def test_cli_json_and_force(tmp_path: Path, synthetic_hinote: bytes, capsys) -> None:
    source = _write_archive(tmp_path / "note.hinote", synthetic_hinote)
    output = tmp_path / "custom.pdf"
    output.write_bytes(b"old")

    assert main([str(source), "-o", str(output), "--force", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["output"] == str(output)
    assert payload["strokes"] == 1
    assert output.read_bytes().startswith(b"%PDF-")


def test_cli_refuses_to_overwrite(
    tmp_path: Path, synthetic_hinote: bytes, capsys
) -> None:
    source = _write_archive(tmp_path / "note.hinote", synthetic_hinote)
    output = tmp_path / "note.pdf"
    output.write_bytes(b"keep")

    assert main([str(source)]) == 1
    assert output.read_bytes() == b"keep"
    assert "use --force" in capsys.readouterr().err
