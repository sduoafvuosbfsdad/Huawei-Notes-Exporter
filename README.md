# Huawei Notes Ink Reverse Engineering (PENCILENGINE)

This repository reverse engineers Huawei Notes `.bin` ink payloads found inside `.hinote` exports.

## What Is Included

- Metadata manifest builder:
  - `tools/build_manifest.py`
- Binary forensics/probing:
  - `tools/bin_probe.py`
  - `research/dump_bin_forensics.py`
- Parser library:
  - `src/pencilengine/parser.py`
- Required CLIs:
  - `extract_strokes.py`
  - `render_strokes.py`
  - `validate.py`
- Format write-up:
  - `FORMAT.md`
- Tests:
  - `tests/`

## Data Layout

- Unzipped source:
  - `data/unzipped/`
- Page/bin mapping:
  - `data/manifest.json`
- Debug artifacts:
  - `data/debug/`

## Reproducible Workflow

1. Build manifest from unzipped `.hinote`:

```bash
python3 tools/build_manifest.py --unzipped-dir data/unzipped --out data/manifest.json
```

2. Probe raw binary structure:

```bash
python3 tools/bin_probe.py data/unzipped/files/53d1088bd634cba318c4d27cc9371070.bin --json-out data/debug/53d1088b_probe.json
python3 tools/bin_probe.py data/unzipped/files/9def0e3d381fa1c2e41f7f80d88503a3.bin --json-out data/debug/9def0e3d_probe.json
```

3. Generate deeper forensic dumps:

```bash
python3 research/dump_bin_forensics.py data/unzipped/files/53d1088bd634cba318c4d27cc9371070.bin --out data/debug/53d1088b_forensics.json
python3 research/dump_bin_forensics.py data/unzipped/files/9def0e3d381fa1c2e41f7f80d88503a3.bin --out data/debug/9def0e3d_forensics.json
```

4. Extract strokes to open JSON:

```bash
python3 extract_strokes.py data/unzipped/files/53d1088bd634cba318c4d27cc9371070.bin --out data/debug/53d1088b_strokes.json
```

5. Render strokes (transparent background):

```bash
python3 render_strokes.py data/debug/53d1088b_strokes.json --out data/debug/53d1088b_render.png --svg-out data/debug/53d1088b_render.svg
```

6. Validate against Huawei preview PNG (auto alignment scale+translate):

```bash
python3 validate.py \
  data/debug/53d1088b_strokes.json \
  --preview data/unzipped/files/71e46e4aad83a6f0f8e10169ea3fc4d1.png \
  --out data/debug/53d1088b_overlay.png \
  --ink-out data/debug/53d1088b_ink_aligned.png \
  --report-out data/debug/53d1088b_validate.json
```

## CLI Reference

### `extract_strokes.py`

```bash
python3 extract_strokes.py <path_to_bin> --out out.json
```

Outputs parsed strokes with offsets, raw fields, and decoded point records.

### `render_strokes.py`

```bash
python3 render_strokes.py out.json --out out.png
```

Optional:

- `--width`, `--height`
- `--scale`, `--dx`, `--dy`
- `--width-scale`
- `--svg-out out.svg`

### `validate.py`

```bash
python3 validate.py out.json --preview preview.png --out overlay.png
```

Performs automatic scale+translate registration and reports alignment metrics.

## Running Tests

```bash
python3 -m unittest discover -s tests -v
```
