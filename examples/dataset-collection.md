# Example — dataset collection

User asks: *"Collect a dataset of public AI research tools with
website, license, GitHub repo, and use case."*

This is a **structured-data collection** task, not a literature review.
Treat it as building a small Frictionless Data Package
(`templates/data-package.json`).

## Workflow

### 1. Define the unit of observation

One row = one distinct project (not one release, not one repository
fork). Document this in the data dictionary
(`templates/data-dictionary.csv`).

### 2. Define the schema

```
project_id, name, website, github_url, primary_license, github_stars,
last_commit_date, primary_language, use_case, source_url,
date_accessed, notes
```

Save as `data-dictionary.csv`. Choose a deduplication key (here:
`github_url` if present, else canonicalised `website`).

### 3. Identify sources

- **Awesome lists** (read-only, attribution required) — e.g.
  `awesome-ai`, `awesome-machine-learning`.
- **GitHub topics** (`https://api.github.com/search/repositories?q=topic:llm`,
  with a polite User-Agent and respect `X-RateLimit-Remaining`).
- **Hugging Face Hub** (`https://huggingface.co/api/models`).
- **Papers With Code** dataset listings.
- **Vendor websites** for verification (license, claims).

### 4. Extract

Use `references/data-extraction-toolbox.md` recipes:

- For GitHub: REST API → `scripts/api_fetch.mjs --paginate cursor`.
- For Hugging Face: REST API the same way.
- For awesome-lists: `scripts/playwright_extract.mjs --selector
  'article a'` then post-process.
- For vendor pages: case-by-case; many have JSON-LD (`script[type=
  "application/ld+json"]`).

Log every API call in `templates/api-request-log.csv`.

### 5. Normalise and dedupe

```
node scripts/run_python.mjs scripts/data_clean.py clean \
  --in raw.csv --out clean.csv

node scripts/run_python.mjs scripts/data_clean.py dedup \
  --in clean.csv --out unique.csv --on github_url,website
```

For license normalisation, build a mapping table (e.g. `Apache 2` /
`Apache-2.0` / `apache_license_2_0` → `Apache-2.0`) and document it in
the report appendix.

### 6. Score and tag

For each row, score the source's quality with
`scripts/score_source.py score`. Treat rows with `band=low` as
informational, not authoritative — include them in the dataset but flag
in `notes` (e.g. *"crowd-sourced from awesome-list, not vendor-verified"*).

### 7. Validate

```
node scripts/run_python.mjs scripts/data_clean.py validate \
  --in unique.csv --spec data-spec.json
```

Where `data-spec.json` describes column types and constraints (e.g.
`github_url` must match `https://github.com/<owner>/<repo>`).

### 8. Package

Populate `datapackage.json` from `templates/data-package.json`. Include
resources for `unique.csv`, `evidence-ledger.csv`, and the logs.

Sign the ledger:

```
export D_RESEARCH_LEDGER_KEY="$(cat ~/.config/d-research-skill/ledger.key)"
node scripts/run_python.mjs scripts/evidence_ledger.py sign \
  --file evidence-ledger.csv
```

## Blocked sources

If a vendor site uses Cloudflare bot protection or a captcha that
appears for ordinary users, produce a blocker report
(`references/blocker-report.md`) and exclude the row, **do not** switch
to stealth plugins or rotating user agents.

## Deliverables

- `datapackage.json` (Frictionless Data Package descriptor)
- `unique.csv` (the dataset itself)
- `evidence-ledger.csv` (+ `.hmac`)
- `data-dictionary.csv`
- `api-request-log.csv`
- `report.md` summarising scope, coverage gaps, known limitations

## See also

- `references/data-extraction-toolbox.md`
- `references/data-processing-pipeline.md`
- `references/large-scale-collection.md`
- `references/api-access-workflow.md`
- `references/blocker-report.md`
- `templates/data-package.json`
- `examples/api-dataset-collection.md`
- `examples/large-scale-crawl.md`
