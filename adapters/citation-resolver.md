# Citation Resolver Adapter

Resolves academic identifiers (DOI, PMID, arXiv ID, ISBN) to structured metadata via free public APIs. No API keys required for basic resolution.

## When to Use

- User pastes a DOI, PMID, arXiv ID, or ISBN and needs full metadata
- Enriching evidence-ledger rows with publication details before citation export
- Verifying a claimed publication exists and extracting canonical metadata
- Finding open-access versions of paywalled papers (Unpaywall)
- Building BibTeX entries from identifiers for academic output

## Supported Resolvers

| Identifier | API | Endpoint | Auth |
|---|---|---|---|
| DOI | CrossRef | `https://api.crossref.org/works/<doi>` | None (polite UA) |
| DOI | Datacite | `https://api.datacite.org/dois/<doi>` | None |
| DOI | Unpaywall | `https://api.unpaywall.org/v2/<doi>?email=<email>` | Email param |
| PMID | NCBI E-utilities | `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi` | None |
| arXiv ID | arXiv API | `http://export.arxiv.org/api/query?id_list=<id>` | None |
| ISBN | Open Library | `https://openlibrary.org/api/books?bibkeys=ISBN:<isbn>` | None |

## Usage

```bash
# Resolve a DOI (auto-selects CrossRef)
python scripts/citation_resolver.py doi 10.1038/nature12373

# Force Datacite for dataset DOIs
python scripts/citation_resolver.py doi 10.5281/zenodo.1234567 --source datacite

# Resolve PubMed ID
python scripts/citation_resolver.py pmid 35027834

# Resolve arXiv paper
python scripts/citation_resolver.py arxiv 1706.03762

# Resolve ISBN
python scripts/citation_resolver.py isbn 978-0134685991

# Check open-access availability
python scripts/citation_resolver.py oa 10.1038/nature12373

# Emit evidence-ledger row
python scripts/citation_resolver.py to-ledger 10.1038/nature12373 --url https://doi.org/10.1038/nature12373 --out-row row.csv

# Emit BibTeX
python scripts/citation_resolver.py to-bibtex 10.1038/nature12373

# Bulk resolve
python scripts/citation_resolver.py batch --in ids.txt --out resolved.json
```

## Integration with Other Scripts

The resolver is the canonical "Step 0" before any citation workflow:

1. **Resolve** → `citation_resolver.py doi|pmid|arxiv|isbn`
2. **Enrich** → `citation_export.py enrich --doi <doi>` (uses CrossRef directly)
3. **Export** → `citation_export.py export --format bibtex`
4. **Render** → `citation_render.py render --style apa`

For fact-verification tasks involving academic claims, the resolver provides a one-shot canonical lookup that short-circuits the full research loop.

## Rate Limits

All APIs are polite-pool. The script includes:
- 1 request/second spacing in batch mode
- Exponential backoff on HTTP 429
- Polite User-Agent header with contact email

## Limitations

- CrossRef coverage: ~130M DOIs (journals, conferences, books)
- Datacite coverage: datasets, software, preprints registered with Datacite
- PubMed: biomedical literature only
- arXiv: physics, math, CS, quantitative biology, statistics
- Open Library: books with ISBNs in their catalog
- Unpaywall: only reports OA status, does not bypass paywalls
