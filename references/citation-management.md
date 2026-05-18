# Citation Management

This skill handles bibliographic references for academic writing, ensuring consistent formatting, proper metadata, and export to standard formats.

## When to Use

Apply citation management in these scenarios:

- **Academic papers**: Journal articles, conference proceedings, technical reports
- **Theses and dissertations**: Comprehensive bibliographies with annotated references
- **Literature reviews**: Organized citation collections with deduplication
- **Technical documentation**: References to source materials, datasets, or prior work
- **Any document requiring a reference list**: Ensure DOIs/URLs are present for all entries

## Citation Data Model

Each reference follows this structured schema:

```json
{
  "type": "article|book|conference|report|web|dataset|software",
  "title": "Full title of work",
  "authors": [
    {"family": "Smith", "given": "John A.", "orcid": "0000-0001-2345-6789"}
  ],
  "year": 2024,
  "journal": "Journal Name (optional)",
  "volume": "12 (optional)",
  "issue": "3 (optional)",
  "pages": "45-67 (optional)",
  "publisher": "Publisher Name (optional)",
  "doi": "10.1234/example.doi",
  "url": "https://example.com/paper (optional)",
  "accessed": "2024-01-15 (optional, for web sources)",
  "abstract": "Paper abstract (optional)"
}
```

**Required fields**: type, title, authors (at least one), year, plus type-specific fields:
- `article`: journal, volume, pages, doi
- `book`: publisher
- `conference`: journal or proceedings, pages, doi
- `report`: institution
- `web`: url, accessed
- `dataset`: archive (e.g., Zenodo, Figshare)
- `software`: version, url

## BibTeX Export

BibTeX is the standard format for LaTeX documents and reference managers.

**File structure**: Save as `.bib` file with one entry per reference.

**Entry types**:
```
@article{AuthorYear_ShortTitle,
  author = {Smith, John A. and Doe, Jane},
  title = {Full Paper Title Here},
  journal = {Journal Name},
  year = {2024},
  volume = {12},
  number = {3},
  pages = {45--67},
  doi = {10.1234/example}
}

@book{AuthorYear_ShortTitle,
  author = {Smith, John A.},
  title = {Book Title},
  publisher = {Publisher Name},
  year = {2023}
}

@inproceedings{AuthorYear_ShortTitle,
  author = {Smith, John A.},
  title = {Conference Paper Title},
  booktitle = {Proceedings of Conference Name},
  year = {2024},
  pages = {100--115},
  doi = {10.1234/conf}
}

@techreport{AuthorYear_ShortTitle,
  author = {Smith, John A.},
  title = {Report Title},
  institution = {Organization Name},
  year = {2024},
  doi = {10.1234/report}
}

@misc{AuthorYear_ShortTitle,
  author = {Smith, John A.},
  title = {Resource Title},
  year = {2024},
  url = {https://example.com/resource}
}

@online{AuthorYear_ShortTitle,
  author = {Smith, John A.},
  title = {Webpage Title},
  year = {2024},
  url = {https://example.com/page},
  urldate = {2024-01-15}
}

@dataset{AuthorYear_ShortTitle,
  author = {Smith, John A.},
  title = {Dataset Title},
  year = {2024},
  publisher = {Zenodo},
  doi = {10.5281/zenodo.1234567}
}
```

**Key format**: `{LastName}{Year}_{ShortTitle}` with no spaces or special characters except underscore.

**Export from the evidence-ledger CSV** (the script consumes `templates/evidence-ledger.csv`, not JSON):
```bash
python3 scripts/citation_export.py export \
  --file evidence.csv \
  --format bibtex \
  --out citations.bib
```

Note: the bundled `scripts/citation_export.py` currently emits BibTeX `@misc` entries built from the evidence-ledger schema. The richer entry types shown above (`@article`, `@book`, `@inproceedings`, etc.) are the target shape an external tool (Zotero, BibLaTeX) can use after manual editing or extension of the script.

## RIS Export

RIS format imports into Zotero, Mendeley, EndNote, and other managers.

**File structure**: Save as `.ris` with `TY` at start and `ER` at end of each entry.

**Export script**:
```bash
python3 scripts/citation_export.py export \
  --file evidence.csv \
  --format ris \
  --out citations.ris
```

**Generated output example**:
```
TY  - JOUR
AU  - Smith, John A.
AU  - Doe, Jane
TI  - Full Paper Title Here
JO  - Journal Name
VL  - 12
IS  - 3
SP  - 45
EP  - 67
PY  - 2024
DO  - 10.1234/example.doi
ER  -

TY  - BOOK
AU  - Smith, John A.
TI  - Book Title
PB  - Publisher Name
PY  - 2023
ER  -
```

## Inline Citation Formats

Generate in-text citations per style requirements:

| Style | In-text Format | Example |
|-------|---------------|---------|
| **APA 7** | `(Author, Year)` | `(Smith, 2024)` |
| **IEEE** | `[N]` | `[1]` |
| **Chicago** | `Author (Year)` | `Smith (2024)` |
| **Vancouver** | `(N)` | `(1)` |

**Formatted reference list generation**:

The bundled `scripts/citation_export.py` supports `--format bibtex` and `--format ris`. To produce APA/IEEE/Chicago/Vancouver/Harvard/Nature/Science/ACM/AMA formatted output, use the bundled `scripts/citation_render.py` wrapper around `pandoc --citeproc` + CSL.

```bash
# Export BibTeX from the evidence ledger first
python3 scripts/citation_export.py export \
  --file evidence.csv \
  --format bibtex \
  --out citations.bib

# Render directly into the target style (downloads the CSL file the
# first time, then caches it under ~/.cache/d-research-skill/csl/).
python3 scripts/citation_render.py render \
  --bib citations.bib \
  --style apa \
  --format markdown \
  --out references_formatted.md
```

Available style aliases (short name → official CSL): `apa`, `apa7`,
`mla`, `mla9`, `ieee`, `chicago-author-date`, `chicago-note`,
`vancouver`, `harvard-cite-them-right`, `nature`, `science`, `acm-sig-proceedings`,
`ama`, `elsevier-harvard`, `acs`, `aiaa`. List all aliases at runtime:

```bash
python3 scripts/citation_render.py list-styles
```

If the agent is offline or downloads are disabled, the script will
refuse to fetch a CSL file unless `--no-download` is omitted; in fully
offline mode the script can still emit the BibTeX-as-prose default
format (see `--style default`).

For a fully manual pandoc invocation (pre-existing CSL file on disk):

```bash
pandoc references.md \
  --citeproc --bibliography citations.bib --csl apa.csl \
  -o references_formatted.md
```

## DOI Enrichment

Query CrossRef API to complete missing metadata:

```bash
curl "https://api.crossref.org/works/10.1234/example.doi"
```

**Response fields to extract**:
- `message.title[0]` → title
- `message.author[]` → authors (family, given, ORCID)
- `message.published.date-parts[0]` → year
- `message.container-title[0]` → journal
- `message.volume` → volume
- `message.issue` → issue
- `message.page` → pages
- `message.abstract` → abstract

**Enrichment from CrossRef**:

The bundled `scripts/citation_export.py` exposes an `enrich` subcommand that queries CrossRef for a single DOI (stdlib only, no `requests` dependency):

```bash
python3 scripts/citation_export.py enrich --doi 10.1234/example.doi
```

It prints a JSON object with title, authors, year, journal, volume, issue, pages, and DOI extracted from the CrossRef `message` payload. Use it inline or wrap it in a loop to enrich every row in your evidence ledger before exporting:

```bash
# Pseudocode: enrich each DOI then re-export
for doi in $(cut -d, -f<doi_col> evidence.csv | tail -n +2 | sort -u); do
  python3 scripts/citation_export.py enrich --doi "$doi" \
    > "enriched/$(echo "$doi" | tr '/' '_').json"
done
```

## Workflow

Follow this sequence for citation management:

0. **Resolve** (if you have an identifier): Use `scripts/citation_resolver.py` to canonicalize DOI/PMID/arXiv/ISBN into structured metadata before any manual search. This is the fastest path to complete bibliographic data.
   ```bash
   python3 scripts/citation_resolver.py doi 10.1038/nature12373
   python3 scripts/citation_resolver.py pmid 35027834
   python3 scripts/citation_resolver.py arxiv 1706.03762
   python3 scripts/citation_resolver.py isbn 978-0134685991
   ```

1. **Collect**: Gather references into the evidence-ledger CSV (`templates/evidence-ledger.csv`)
   - Scrape from web searches, academic databases, paper PDFs
   - Append one row per claim with available metadata immediately

2. **Enrich**: Run the CrossRef enrichment subcommand for each DOI
   ```bash
   python3 scripts/citation_export.py enrich --doi 10.1234/example.doi
   ```

3. **Deduplicate**: Remove duplicate entries
   ```python
   seen_dois = set()
   unique_refs = []
   for ref in references:
       doi = ref.get("doi", "").lower()
       if doi and doi in seen_dois:
           continue
       # Check title similarity for entries without DOI
       unique_refs.append(ref)
       if doi:
           seen_dois.add(doi)
   ```

4. **Export**: Generate the format the downstream tool needs
   ```bash
   python3 scripts/citation_export.py export \
     --file evidence.csv --format bibtex --out citations.bib
   ```

5. **Generate formatted list (optional)**: convert BibTeX to APA/MLA/IEEE/etc. with the bundled renderer (or `pandoc` directly if you prefer)
   ```bash
   python3 scripts/citation_render.py render \
     --bib citations.bib --style apa \
     --format markdown --out references_formatted.md
   ```

## Quality Checks

Before finalizing any citation export, verify:

| Check | Requirement | Fix Action |
|-------|-------------|------------|
| **DOI/URL presence** | Every citation has DOI or URL | Add via DOI lookup or user confirmation |
| **Author consistency** | Names formatted identically across all refs | Normalize to "Family, Given" format |
| **Year complete** | All entries have year field | Lookup via CrossRef or mark as "(n.d.)" |
| **No duplicates** | Check by DOI, then title similarity | Merge or remove duplicates |
| **BibTeX keys unique** | No duplicate keys in .bib file | Append suffix (_2, _3) if needed |
| **DOI format valid** | DOIs match `10.xxxx/xxxxx` pattern | Verify or search for correct DOI |
| **Journal title** | Abbreviated or full name consistent | Use CrossRef canonical form |

**Validation**: there is no separate `citation_validate.py` script. Use the existing evidence-ledger validator, which checks the evidence-ledger CSV that `citation_export.py` consumes (required headers, non-empty atomic claims, present source URLs, well-formed confidence values, etc.):

```bash
python3 scripts/evidence_ledger.py validate --file evidence.csv
```

If you need extra checks specific to bibliographic quality (DOI shape, duplicate DOI detection, missing authors/year), implement them as a small wrapper around the evidence-ledger validator. Reference template:

```python
# Example wrapper — not bundled in scripts/
import csv, re, sys

DOI_RE = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE)

def validate_citations(path: str) -> list[str]:
    errors: list[str] = []
    seen_dois: set[str] = set()
    with open(path, newline="", encoding="utf-8") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):  # 2 = first data row
            url = (row.get("source_url") or "").strip()
            title = (row.get("source_title") or "").strip()
            date = (row.get("date_published") or "").strip()
            if not url:
                errors.append(f"Row {i}: missing source_url")
            if not title:
                errors.append(f"Row {i}: missing source_title")
            if not date:
                errors.append(f"Row {i}: missing date_published")
            doi_match = DOI_RE.search(url)
            if doi_match:
                doi = doi_match.group(0).lower()
                if doi in seen_dois:
                    errors.append(f"Row {i}: duplicate DOI {doi}")
                seen_dois.add(doi)
    return errors

if __name__ == "__main__":
    for err in validate_citations(sys.argv[1]):
        print(err)
```
