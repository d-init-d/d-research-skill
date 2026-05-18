# PDF Extraction

Use this file when you need to extract text, metadata, or tables from a
PDF file as part of a research workflow. The script
`scripts/pdf_extract.py` wraps poppler-utils and optional pdfplumber
into a single CLI with subcommands that integrate directly with the
evidence ledger.

## Prerequisites

### Required: poppler-utils

The `text`, `meta`, and `to-ledger` subcommands shell out to `pdftotext`
and `pdfinfo`. Install the system package before use:

```bash
# Debian / Ubuntu
sudo apt-get install -y poppler-utils

# macOS (Homebrew)
brew install poppler

# Windows (Chocolatey)
choco install poppler
```

If the binaries are missing, the script exits with code 2 and prints
which binary is needed.

### Optional: pdfplumber (tables only)

The `tables` subcommand requires the Python package `pdfplumber`. If it
is not installed, the subcommand prints a warning to stderr and exits 0
without producing output.

```bash
pip install pdfplumber
```

## Subcommand reference

### text

Extract full text from a PDF.

```bash
python scripts/pdf_extract.py text --in report.pdf
python scripts/pdf_extract.py text --in report.pdf --out report.txt
```

Writes to stdout by default. Use `--out` to write to a file instead.

### meta

Extract metadata as JSON (title, author, dates, page count).

```bash
python scripts/pdf_extract.py meta --in report.pdf
python scripts/pdf_extract.py meta --in report.pdf --out meta.json
```

Output example:

```json
{
  "title": "Annual Report 2024",
  "author": "Research Team",
  "creation_date": "Mon Jan 15 10:30:00 2024",
  "modification_date": "Tue Feb 20 14:00:00 2024",
  "page_count": 42,
  "producer": "LaTeX",
  "creator": "pdflatex"
}
```

### tables

Extract tables as CSV files (one per detected table). Requires
pdfplumber.

```bash
python scripts/pdf_extract.py tables --in report.pdf --out-dir ./tables/
```

Output files are named `p{page}_t{table}.csv` — for example,
`p1_t1.csv` is the first table on page 1.

### to-ledger

Generate an evidence-ledger CSV row from a PDF. Combines `meta` and
`text` extraction into a single row that conforms to the
`templates/evidence-ledger.csv` schema.

```bash
python scripts/pdf_extract.py to-ledger \
  --in report.pdf \
  --url "https://example.org/report.pdf" \
  --out-row evidence-ledger.csv
```

The row is appended to the target CSV (header is written automatically
if the file is empty or does not exist).

### self-test

Run offline validation against `examples/fixtures/test.pdf`. Exercises
text, meta, and to-ledger subcommands (and tables if pdfplumber is
available). If poppler-utils is missing, the self-test prints a skip
message and exits 0; the actual `text`, `meta`, and `to-ledger`
subcommands still fail with exit code 2 until poppler is installed.

```bash
python scripts/pdf_extract.py self-test
```

## Evidence-ledger integration

The `to-ledger` subcommand maps PDF metadata to the ledger schema
defined in `references/evidence-ledger.md`:

| Ledger field | Source |
|---|---|
| `claim_id` | `PDF_` + first 8 hex chars of SHA-256(url + title) |
| `claim` | `Extracted from: <title>` |
| `source_url` | The `--url` argument |
| `source_type` | `pdf` |
| `access_method` | `pdf_extract` |
| `evidence` | First 500 characters of extracted text |
| `date_published` | `creation_date` from pdfinfo (if available) |
| `date_accessed` | Today's date (ISO 8601) |
| `confidence` | `medium` |

All other fields (`sub_question`, `quote_or_anchor`, `contradiction`,
`notes`) are populated with safe defaults. Edit the row after generation
to add context-specific values.

## When to use this vs other extraction methods

| Situation | Recommended approach |
|---|---|
| PDF with selectable text | `pdf_extract.py text` |
| PDF metadata cataloging | `pdf_extract.py meta` |
| PDF with data tables | `pdf_extract.py tables` |
| Scanned/image-only PDF | OCR tool (Tesseract), then text extraction |
| PDF behind a login wall | Produce a blocker report (`references/blocker-report.md`) |
| Non-PDF structured data | See `references/data-extraction-toolbox.md` |

## Scanned / image-only PDFs

If `pdftotext` returns empty or near-empty output, the PDF is likely scanned (image-only). Use `scripts/ocr.py pdf` instead:

```bash
# Try pdftotext first
python scripts/pdf_extract.py text --in doc.pdf --out text.txt

# If empty, fall back to OCR
python scripts/ocr.py pdf --in doc.pdf --out text.txt --lang eng
```

See `references/ocr.md` for full OCR documentation.

## See also

- `references/data-extraction-toolbox.md` — full extraction recipe catalog
- `references/extraction-methods.md` — extraction strategy and decision rules
- `references/evidence-ledger.md` — ledger schema and CSV quoting rules
- `references/ocr.md` — OCR extraction for scanned documents
- `templates/evidence-ledger.csv` — row template for positive and negative rows
- `scripts/pdf_extract.py` — the script itself
- `scripts/ocr.py` — OCR fallback for scanned PDFs
