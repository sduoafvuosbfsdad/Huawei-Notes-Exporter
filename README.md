# Huawei Notes Exporter

| Message from the human: This is completely written by gpt 5.6 sol, it worked for me so I guess ill put it up. Highlight issues and ill get it fixed when I see it 

A focused command-line tool for converting Huawei Notes `.hinote` exports into
PDFs with the original document pages and clean, native vector handwriting.

It decodes Huawei's `PENCILENGINE` binary records directly—coordinates,
pressure, pen width, colour, and point states. It does **not** trace the
low-resolution preview images, so handwriting remains sharp when zoomed or
printed.

## Install

Python 3.10 or newer is required.

```bash
python -m pip install .
```

For development:

```bash
python -m pip install -e '.[dev]'
```

## Use

```bash
hinote-export MyNotes.hinote
```

The default output is `MyNotes.pdf` next to the input archive. Choose another
path with `--output`:

```bash
hinote-export MyNotes.hinote --output exported/chemistry.pdf
```

Replace an existing output and print machine-readable statistics:

```bash
hinote-export MyNotes.hinote --output chemistry.pdf --force --json
```

The package can also be run without the installed command wrapper:

```bash
python -m huawei_notes_exporter MyNotes.hinote
```

Run `hinote-export --help` for archive safety-limit options.

## Python API

```python
from huawei_notes_exporter import convert_hinote

result = convert_hinote("MyNotes.hinote", "MyNotes.pdf")
print(result.pages, result.strokes, result.points)
```

Use `extract_hinote()` when you need the decoded note model without writing a
PDF, or `decode_pencilengine()` to parse a single Huawei stroke binary.

## What is preserved

- The original embedded PDF pages and dimensions
- Native black and coloured pen strokes
- Per-pen appearance: ballpoint, fountain pen (pressure-sensitive width),
  pencil (pressure-dependent darkness), translucent highlighter, and soft
  airbrush spray
- Curves, dots, ticks, circles, and handwriting placement
- Note pages added in the app, including the square-grid paper (`base3`)
  and paper colour
- Typed text boxes and inserted pictures, drawn beneath the ink
- PDF metadata derived from the Huawei note title

Pen appearance, the grid, and text placement were calibrated against the
page thumbnails stored in Huawei exports. Text uses Helvetica (or a CJK
font for non-Latin text) rather than Huawei's own UI font, so glyph shapes
differ slightly.

Huawei sometimes adds blank note pages beyond the imported document. The
export uses the embedded PDF's page count, so that padding is omitted.

## Format support

The decoder supports the format observed in Huawei Notes `hinote_1.0.4`
and `hinote_1.0.5` archives:

- gzip-compressed `.jhinote` JSON metadata
- big-endian `PENCILENGINE` containers
- `0x00010000` and `0x00010001` stroke-record layouts
- 36-byte point records with start/move/end states
- pen tool and opacity fields in stroke records
- embedded PDF page backgrounds
- `pageElement` text boxes (`elementType` 0) and pictures (`elementType` 1)

Huawei has not published this binary format. Unknown record layouts are
rejected instead of being guessed or raster-traced. If a newer export is not
supported, please open an issue with the Huawei Notes app version and the exact
error message. Do not attach private notes to public issues.

## Security

Archives are read in place and never extracted to user-controlled paths.
Absolute paths, parent-directory traversal, excessive entry counts, and
oversized uncompressed archives are rejected. CLI output is written to a
temporary sibling file and atomically renamed only after successful conversion.

## License

MIT
