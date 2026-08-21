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
- Pressure-sensitive line width
- Curves, dots, ticks, circles, and handwriting placement
- PDF metadata derived from the Huawei note title

Huawei sometimes adds blank note pages beyond the imported document. The
export uses the embedded PDF's page count, so that padding is omitted.

## Format support

The decoder supports the format observed in Huawei Notes `hinote_1.0.4`
archives:

- gzip-compressed `.jhinote` JSON metadata
- big-endian `PENCILENGINE` containers
- `0x00010000` and `0x00010001` stroke-record layouts
- 36-byte point records with start/move/end states
- embedded PDF page backgrounds

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
