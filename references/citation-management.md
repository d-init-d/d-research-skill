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

**Export script**:
```bash
python scripts/citation_export.py --format bibtex --input references.json --output citations.bib
```

## RIS Export

RIS format imports into Zotero, Mendeley, EndNote, and other managers.

**File structure**: Save as `.ris` with `TY` at start and `ER` at end of each entry.

**Export script**:
```bash
python scripts/citation_export.py --format ris --input references.json --output citations.ris
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
```bash
python scripts/citation_export.py --format apa7 --input references.json --output references.md
```

Output produces properly formatted bibliography entries in requested style.

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

**Enrichment script**:
```python
# scripts/citation_enrich.py
import requests

def enrich_doi(doi: str) -> dict:
    url = f"https://api.crossref.org/works/{doi}"
    headers = {"User-Agent": "ResearchAgent/1.0 (mailto:agent@example.com)"}
    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code == 200:
        data = response.json()["message"]
        return {
            "title": data.get("title", [""])[0],
            "authors": [{"family": a.get("family", ""), 
                        "given": a.get("given", ""),
                        "orcid": a.get("ORCID", "")} 
                       for a in data.get("author", [])],
            "year": data.get("published", {}).get("date-parts", [[0]])[0][0],
            "journal": data.get("container-title", [""])[0],
            "volume": data.get("volume", ""),
            "issue": data.get("issue", ""),
            "pages": data.get("page", ""),
            "doi": doi
        }
    return None
```

## Workflow

Follow this sequence for citation management:

1. **Collect**: Gather references into `evidence/references.json` ledger
   - Scrape from web searches, academic databases, paper PDFs
   - Store each citation with available metadata immediately

2. **Enrich**: Query CrossRef API for each DOI
   ```python
   for ref in references:
       if ref.get("doi") and not ref.get("authors"):
           enriched = enrich_doi(ref["doi"])
           ref.update(enriched)
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

4. **Export**: Generate format needed by user
   ```bash
   python scripts/citation_export.py --format bibtex --input references.json
   ```

5. **Generate formatted list**: Create in-text citation and bibliography
   ```bash
   python scripts/citation_export.py --format apa7 --input references.json --output refs.md
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

**Validation script**:
```python
# scripts/citation_validate.py
def validate_citations(refs: list) -> list:
    errors = []
    dois = set()
    keys = set()
    for i, ref in enumerate(refs):
        if not ref.get("doi") and not ref.get("url"):
            errors.append(f"Entry {i}: Missing DOI and URL")
        if ref.get("doi"):
            if ref["doi"].lower() in dois:
                errors.append(f"Entry {i}: Duplicate DOI {ref['doi']}")
            dois.add(ref["doi"].lower())
        if not ref.get("authors"):
            errors.append(f"Entry {i}: No authors listed")
        if not ref.get("year"):
            errors.append(f"Entry {i}: Missing year")
    return errors
```

Run validation before any export:
```bash
python scripts/citation_validate.py --input references.json
```
