# Example — PRISMA 2020 systematic review

A worked example walking through a small systematic review using this
skill end-to-end. The topic and counts are illustrative; reuse the
structure, not the numbers.

**Research question** — How effective are headless-browser automation
tools (Playwright, Puppeteer, Selenium) at retrieving structured data
from public academic-database web interfaces, compared with using the
databases' documented APIs?

**Mode** — Systematic review with narrative synthesis (PRISMA 2020).

## Step 1 — Protocol

Wrote `research/protocol.md`:

- **PICO**:
  - Population: public academic databases with both a documented API
    and a public web interface (e.g. OpenAlex, CrossRef, PubMed, arXiv).
  - Intervention: headless-browser automation (Playwright, Puppeteer,
    Selenium) used to retrieve structured records from the web UI.
  - Comparator: the database's documented HTTP/REST/GraphQL API.
  - Outcomes: completeness (records retrieved / records expected),
    correctness (field-level accuracy on a sampled gold standard),
    throughput (records / hour), failure modes (rate limits, captchas,
    schema drift).
- **Eligibility**: peer-reviewed or arXiv preprint, 2018-2026, English,
  empirical evaluation on ≥1 academic database.
- **Information sources**: OpenAlex, CrossRef, Semantic Scholar, arXiv,
  Europe PMC, OSF registries, citation chaining.
- **Screening**: dual screener with conflict resolution.
- **Quality**: custom rubric (`references/source-quality-rubric.md`)
  augmented with `scripts/score_source.py`.
- **Synthesis**: narrative, grouped by outcome.
- **Reporting**: PRISMA 2020 + `references/final-report-template.md`.

## Step 2 — Search

Logged every query in `templates/search-log.csv`. Sample rows:

```csv
date,tool,query,filters,results_reviewed,kept,notes
2026-02-01,OpenAlex,"(headless-browser OR Playwright OR Puppeteer OR Selenium) AND (academic database OR scholarly OR bibliographic) AND (scraping OR crawling OR extraction)",2018-2026,412,84,broad concept-block query
2026-02-01,CrossRef,"headless browser bibliographic scraping",2018-2026,178,29,REST API with cursor pagination
2026-02-01,Semantic Scholar,"headless browser academic database scraping evaluation",2018-2026,96,18,
2026-02-01,arXiv,"abstract:(headless browser scholarly scraping)",2018-2026,41,11,
```

Tools used for the searches:

- `scripts/api_fetch.mjs` for OpenAlex and CrossRef (REST APIs).
- `scripts/playwright_extract.mjs` for Semantic Scholar (no easy public
  API for full-text search at the depth required).
- arXiv via its public API.

All API requests logged in `templates/api-request-log.csv` with
timestamps and rate-limit headers.

## Step 3 — Identification → screening

Deduplicated by DOI then title-similarity:

```
node scripts/run_python.mjs scripts/data_clean.py dedup \
  --in raw-records.csv --out deduped-records.csv --on doi,title
```

Result: 773 identified → 187 duplicates → 586 screened.

PRISMA flow numbers captured in `prisma-flow.json` (using
`templates/prisma-flow.json` as the schema):

```json
{
  "identification": {"total_identified": 773, "duplicates_removed": 187},
  "screening": {
    "records_screened": 586,
    "records_excluded_title_abstract": 502,
    "reports_sought_for_retrieval": 84,
    "reports_not_retrieved": 6,
    "reports_assessed_for_eligibility": 78,
    "reports_excluded_full_text": {
      "wrong_population": 14,
      "wrong_intervention": 9,
      "wrong_outcome": 7,
      "wrong_study_design": 12,
      "duplicate_or_overlap": 3,
      "could_not_obtain_full_text": 2
    }
  },
  "included": {
    "studies_included_in_review": 31,
    "studies_included_in_narrative_synthesis": 31
  }
}
```

## Step 4 — Extraction

For each of 31 included studies, added one row to
`templates/evidence-ledger.csv`. Example row (truncated):

```csv
claim_id,claim,sub_question,source_title,source_url,source_type,date_published,date_accessed,access_method,evidence,quote_or_anchor,contradiction,confidence,notes
C012,"Playwright achieved 98.3% field-level accuracy on OpenAlex web-UI scraping vs the documented API on a 500-record gold standard","correctness","Smith et al. 2024","https://doi.org/10.1145/example.123","paper",2024-08-12,2026-02-15,fetch,"Table 3 reports per-field accuracy across name, title, year, DOI, abstract. Mean 98.3%, lowest field 'abstract' at 94.1%.","Table 3, p. 8","none","high",""
```

## Step 5 — Quality assessment

Ran the rubric:

```
node scripts/run_python.mjs scripts/score_source.py score \
  --file evidence-ledger.csv \
  --out evidence-ledger.scored.csv
```

Sample summary:

| band | count |
|------|-------|
| high | 14 |
| medium | 13 |
| low | 4 |

The four "low" rows are non-peer-reviewed engineering blog posts. Kept
in the synthesis because they describe real production failure modes
the peer-reviewed corpus did not cover, but flagged with `confidence:
low` and discussed as such.

## Step 6 — Synthesis (narrative, per sub-question)

Wrote `report.md` with one section per outcome:

- **Completeness** — across 11 studies, headless automation retrieved
  93-99% of records returned by the documented API on the same query
  (median 97%). Gaps came from JS-rendered results that required extra
  scroll/click logic. [claim_ids: C002, C004, C007, …]
- **Correctness** — across 9 studies on field-level accuracy, mean
  98.1% (range 94-99.6%). Lowest accuracy on free-text fields
  (abstracts, descriptions). [claim_ids: C012, C015, …]
- **Throughput** — 50–500 records/hour for headless automation vs
  5,000–50,000 records/hour for the API. The API is 10–100× faster
  where it covers the user's need. [claim_ids: C021, C023, …]
- **Failure modes** — three recurring categories: schema drift (3
  studies), captcha walls (5 studies), rate-limit enforcement (8
  studies). [claim_ids: C027, C028, C029, …]

## Step 7 — Citation export

```
node scripts/run_python.mjs scripts/citation_export.py export \
  --file evidence-ledger.csv --out references.bib --format bibtex

node scripts/run_python.mjs scripts/citation_render.py render \
  --bib references.bib --style ieee --format markdown \
  --out references.formatted.md
```

## Step 8 — Tamper-evidence

```
export D_RESEARCH_LEDGER_KEY="$(cat ~/.config/d-research-skill/ledger.key)"
node scripts/run_python.mjs scripts/evidence_ledger.py sign \
  --file evidence-ledger.csv

node scripts/run_python.mjs scripts/evidence_ledger.py verify \
  --file evidence-ledger.csv
```

The `.hmac` sidecar is committed alongside the ledger. A reviewer can
re-run `verify` to confirm the ledger has not been edited since
signing.

## Step 9 — Limitations recorded in the report

- Single-language search (English) excluded relevant Chinese-language
  literature on bibliographic crawling.
- No access to Scopus or Web of Science; coverage of older literature
  is partial.
- Throughput comparisons are approximate; benchmarks across studies
  were not standardised.
- Three included studies are non-peer-reviewed engineering blog posts,
  scored `confidence: low`.

## Step 10 — Reproducibility checklist

Ran through `references/reproducibility-checklist.md` and confirmed all
items pass. Deliverables:

```
research/
├── protocol.md
├── report.md
├── prisma-flow.json
├── search-log.csv
├── api-request-log.csv
├── screening-log.csv
├── evidence-ledger.csv
├── evidence-ledger.csv.hmac
├── evidence-ledger.scored.csv
├── references.bib
└── references.formatted.md
```

## See also

- `references/systematic-review-protocol.md`
- `references/synthesis-patterns.md`
- `references/reproducibility-checklist.md`
- `references/source-quality-rubric.md`
- `references/citation-management.md`
- `templates/prisma-flow.json`
- `examples/scientific-literature-review.md`
