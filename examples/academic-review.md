# Example — academic review

User asks: *"Help me write a literature review on web scraping methods
for dynamic websites."*

This example shows a **scoping review** workflow — broader than a full
systematic review, but still reproducible. For the more rigorous
PRISMA 2020 flow, see
`examples/systematic-review-prisma.md`.

## Workflow

### 1. Frame the research question

Decompose with `references/topic-decomposition.md`:

- Primary: *"What methods exist for scraping dynamic (JS-rendered) web
  pages, and how do they compare on completeness, robustness, and
  ethical access?"*
- Sub-questions:
  - Which client-side rendering strategies need browser automation?
  - When is fetch + DOM parsing sufficient?
  - How do researchers handle rate limiting, captchas, and bot
    detection without bypassing them?
  - What reproducibility practices exist?

### 2. Build the search strings

See `references/query-patterns.md`. Sample fanout:

```
("dynamic web pages" OR "client-side rendering" OR JavaScript-rendered)
AND (scraping OR crawling OR extraction)
AND (Playwright OR Puppeteer OR Selenium OR headless OR "JavaScript engine")
```

Log every query in `templates/search-log.csv` (date, tool, exact query,
filters, results reviewed, kept).

### 3. Search

- **OpenAlex** for cross-discipline coverage
  (`scripts/api_fetch.mjs --url 'https://api.openalex.org/works?search=...'`).
- **arXiv** for CS preprints.
- **ACM DL** / **IEEE Xplore** only with institutional access.
- **Engineering blogs** (Cloudflare, Datadome, Playwright team) for
  practitioner perspective — flag as `confidence: low/medium`.

### 4. Screen with inclusion / exclusion criteria

Record decisions in `templates/screening-log.csv`. Typical criteria:

- Include: 2019–present, English, empirical or systematic.
- Exclude: vendor marketing material, single-blog opinion without
  evidence, papers not addressing dynamic rendering at all.

### 5. Snowball

For each kept paper, take its top references and forward citations
(via OpenAlex `referenced_works` and `cited_by_count` endpoints).

### 6. Build the evidence ledger

One row per claim in `templates/evidence-ledger.csv`. Anchor every
quote with a page/section reference. Run `scripts/score_source.py
score` to get a rubric pre-score and override manually as needed.

### 7. Synthesise

Group by sub-question (see `references/synthesis-patterns.md` for
narrative-synthesis structure). For each sub-question:

- Body of evidence (count, year range)
- Findings with `claim_id` cites
- Convergence vs. divergence
- Quality of the body of evidence
- Gaps

### 8. Export

```
node scripts/run_python.mjs scripts/citation_export.py export \
  --file evidence-ledger.csv --out references.bib --format bibtex

node scripts/run_python.mjs scripts/citation_render.py render \
  --bib references.bib --style apa --format markdown \
  --out references.formatted.md
```

### 9. Reproducibility

Tick through `references/reproducibility-checklist.md`. Sign the
ledger:

```
node scripts/run_python.mjs scripts/evidence_ledger.py sign \
  --file evidence-ledger.csv --key-env D_RESEARCH_LEDGER_KEY
```

## Deliverables

- `report.md` — using `references/final-report-template.md`
- `evidence-ledger.csv` (+ `.hmac`)
- `search-log.csv`, `screening-log.csv`
- `references.bib`, `references.formatted.md`

## See also

- `references/academic-research-protocol.md`
- `references/synthesis-patterns.md`
- `examples/systematic-review-prisma.md`
- `examples/scientific-literature-review.md`
