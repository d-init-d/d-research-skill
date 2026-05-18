# OCR / Image-to-Text Extraction

Extract text from images and scanned PDFs using `scripts/ocr.py`. Tesseract is the OCR engine; it is optional and soft-fails with a helpful message when missing.

## When to Use

- Scanned PDFs where `pdftotext` returns empty text
- Screenshots of deleted social-media posts (Tier B archival)
- Photos of book pages, whiteboards, or handwritten notes
- Any image containing text that needs to enter the evidence ledger

## Prerequisites

- `tesseract-ocr` system package (optional; script degrades gracefully)
- `poppler-utils` for PDF-to-image conversion (`pdftoppm`)
- Language packs: `tesseract-ocr-eng` (default), `tesseract-ocr-vie`, etc.

## Usage

```bash
# Extract text from an image
python scripts/ocr.py text --in scan.png --lang eng

# Extract text from a scanned PDF (all pages)
python scripts/ocr.py pdf --in scanned.pdf --out text.txt

# Extract specific pages
python scripts/ocr.py pdf --in scanned.pdf --first-page 1 --last-page 5

# Emit evidence-ledger row
python scripts/ocr.py to-ledger --in scan.png --url https://example.com/doc --out-row row.csv

# List installed language packs
python scripts/ocr.py langs
```

## Privacy and Safety

- OCR runs locally via tesseract; no data leaves the machine
- Screenshots of social-media posts carry `verifiability = screenshot_only`
- Do not OCR private documents without user authorization
- OCR output confidence is inherently lower than direct text extraction

## Integration with PDF Extraction

If `scripts/pdf_extract.py text` returns empty or near-empty output, the PDF is likely scanned. Use `scripts/ocr.py pdf` instead:

```bash
# Try pdftotext first
python scripts/pdf_extract.py text --in doc.pdf --out text.txt

# If empty, fall back to OCR
python scripts/ocr.py pdf --in doc.pdf --out text.txt --lang eng
```

## Evidence Ledger Output

The `to-ledger` subcommand emits a full 19-column evidence-ledger row with:
- `access_method = "ocr"`
- `confidence = "medium"` (OCR accuracy varies)
- `verifiability_note` documenting the OCR source

## See Also

- `references/pdf-extraction.md` — PDF text extraction (pdftotext path)
- `references/data-extraction-toolbox.md` — broader extraction recipes
- `references/social-media-archival.md` — screenshot archival workflow
