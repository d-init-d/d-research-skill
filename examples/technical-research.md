# Example — technical research

User asks: *"Research the best open-source browser-automation stack
for scraping dynamic websites."*

This is a **technical survey**: comparing tools across criteria,
producing a recommendation with evidence. Mode comes from
`references/academic-research-protocol.md`.

## Workflow

### 1. Decompose

Per `references/topic-decomposition.md`:

- Tool capabilities: JS rendering, network interception, parallelism,
  language support.
- Reliability: anti-bot avoidance *without* bypass, schema-drift
  resilience.
- Ethics: respect for `robots.txt`, rate limits, terms of service.
- Reproducibility: pinned versions, deterministic locators,
  checkpointing.
- Cost / footprint: memory, CPU, container size.

### 2. Identify candidates

- **Playwright** (Node, Python, .NET, Java)
- **Puppeteer** (Node)
- **Selenium WebDriver** (multi-lang)
- **Crawlee** (Node; built on Playwright/Puppeteer)
- **Scrapy + scrapy-playwright** (Python)
- **HTTPX / requests + lxml** (fetch-only fallback)

### 3. Source map

For each candidate:

- Official docs (priority 1).
- Official GitHub repo (issues, recent commit cadence,
  `cited_by_count`-style metric).
- Maintainers' technical blog posts (priority 2; mark
  `source_type=secondary`).
- Independent benchmarks (priority 2 if peer-reviewed, priority 3 if
  vendor-published).
- Practitioner blog posts (Cloudflare, Datadome, archive.org) for
  failure-mode evidence (priority 3, `confidence=low/medium`).

### 4. Extract claims

For each criterion, extract one ledger row per source:

```csv
claim_id,claim,sub_question,source_title,source_url,source_type,...
T001,"Playwright supports parallel browser contexts within a single process","parallelism","Playwright docs: Browser Contexts","https://playwright.dev/docs/browser-contexts","official","2024-12-01","2026-05-15","fetch","Multiple contexts share a browser instance but have isolated cookies/storage","Page section 'Browser Contexts', paragraph 1","none","high",""
```

### 5. Compare

Build a comparison matrix in `report.md` (one column per tool, one row
per criterion). For each cell, cite the supporting `claim_id`.

| Criterion | Playwright | Puppeteer | Selenium | Crawlee | Scrapy + sp |
|-----------|------------|-----------|----------|---------|-------------|
| JS rendering | yes [T001] | yes [T010] | yes [T020] | yes [T030] | yes [T040] |
| Network intercept | yes [T002] | yes [T011] | partial [T021] | yes [T031] | yes [T041] |
| Multi-lang | 4 langs [T003] | Node only | many | Node only | Python only |
| ... | | | | | |

### 6. Search for contradictions

Per step 11 of the workflow: actively search for sources that disagree
with the converging recommendation. Document them in
`source-quality-rubric.md`'s "Independence" axis.

### 7. Recommend

The recommendation lives in `report.md`'s synthesis section and must:

- State the recommended stack (e.g. "Playwright (Node) with
  scrapy-playwright as a Python fallback").
- Cite the strongest 3–5 `claim_id`s that support it.
- Name the trade-offs (cost / footprint / lock-in).
- List the conditions under which the recommendation would change
  (e.g. "if multi-language is required across Java, switch to
  Selenium").

### 8. Reproducibility

- Pin each tool's version in the report.
- Sign the ledger (`scripts/evidence_ledger.py sign`).
- Note the access policy explicitly: read-only, no stealth plugins,
  respect `robots.txt`.

## Deliverables

- `report.md` (using `references/final-report-template.md`)
- `evidence-ledger.csv` (+ `.hmac`)
- `references.bib`, optionally `references.formatted.md`
- `tool-versions.txt` (output of `--version` for each tool)

## See also

- `references/academic-research-protocol.md`
- `references/data-extraction-toolbox.md`
- `references/source-quality-rubric.md`
- `references/safety-and-access-policy.md`
- `adapters/playwright.md`
- `examples/large-scale-crawl.md`
