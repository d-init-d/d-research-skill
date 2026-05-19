# Multi-Format Extraction

Unified extraction from DOCX, EPUB, XLSX, mbox, and HTML structured data using `scripts/multi_extract.py`.

## Supported Formats

| Format | Backend | Dependency |
|---|---|---|
| DOCX | pandoc | Optional (soft-fail) |
| EPUB | pandoc | Optional (soft-fail) |
| XLSX | stdlib zipfile + XML | None |
| mbox | stdlib mailbox | None |
| HTML (JSON-LD + microdata + RDFa) | stdlib html.parser | None |

## Usage

```bash
# Extract text (auto-detects format)
python scripts/multi_extract.py text --in report.docx
python scripts/multi_extract.py text --in data.xlsx
python scripts/multi_extract.py text --in archive.mbox

# Extract metadata
python scripts/multi_extract.py meta --in data.xlsx

# Extract tables (XLSX → one CSV per sheet)
python scripts/multi_extract.py tables --in data.xlsx --out-dir tables/

# Extract structured data from HTML (JSON-LD, microdata, RDFa)
python scripts/multi_extract.py structured --in page.html

# Search mbox archive
python scripts/multi_extract.py mbox-search --in archive.mbox --q "research" --from "sender@example.com"

# Emit evidence-ledger row
python scripts/multi_extract.py to-ledger --in data.xlsx --url https://example.com/data.xlsx --out-row row.csv
```

## XLSX Extraction (No External Dependencies)

XLSX files are ZIP archives containing XML. The script extracts cell values using stdlib `zipfile` only — no `openpyxl` or other pip packages.

Supported cell types:
- **Shared strings** (`t="s"`): cell `<v>` is an integer index into `xl/sharedStrings.xml`
- **Inline strings** (`t="inlineStr"`): cell contains `<is><t>text</t></is>` or rich text runs
- **Numeric / cached values**: cell `<v>` holds the literal value

Sparse column preservation: cell references like `A1`, `C1`, `AA3` are parsed to compute 0-based column indexes, so a row with only A1 and C1 outputs `["value_a", "", "value_c"]` (preserving the blank B column). This applies to both `text` and `tables` subcommands.

## HTML Structured Extraction

The `structured` subcommand extracts three types of structured data:

- **JSON-LD**: `<script type="application/ld+json">` blocks parsed as JSON
- **Microdata**: elements with `itemscope`/`itemtype`/`itemprop` attributes
- **RDFa**: elements with `typeof`/`property`/`content` attributes

Output keys: `json_ld`, `microdata`, `rdfa`, `source`.

## Soft-Fail Behavior

- If pandoc is missing, DOCX/EPUB commands print a helpful install message and exit non-zero
- XLSX, mbox, and HTML extraction always work (stdlib only)
- Self-test passes even without pandoc (skips pandoc-dependent assertions)

## Metadata Extraction

`meta` reads metadata directly from the file format using stdlib only:

- **DOCX/XLSX**: `docProps/core.xml` (Dublin Core: dc:title, dc:creator, dcterms:modified)
- **EPUB**: `META-INF/container.xml` → OPF package metadata

No pandoc required for metadata extraction.

## See Also

- `references/data-extraction-toolbox.md` — broader extraction recipes
- `references/pdf-extraction.md` — PDF-specific extraction
- `references/ocr.md` — OCR for scanned documents
- `scripts/extract_tables.py` — HTML table extraction
