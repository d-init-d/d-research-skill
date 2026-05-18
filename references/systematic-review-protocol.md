# Systematic Review Protocol (PRISMA 2020)

Use this protocol when the user asks for a **systematic review**,
**scoping review**, or **rapid review** that should be reproducible and
publishable. The protocol is mapped to the PRISMA 2020 checklist
(<https://www.prisma-statement.org/prisma-2020-statement>); each step
below references the PRISMA item it covers.

For lighter literature surveys, see `references/academic-research-protocol.md`.
For choosing between review types, see `references/synthesis-patterns.md`.

## When to use this protocol

Pick a systematic review when **all** of these are true:

- The research question is narrow enough to enumerate eligible studies
  (PICO/PICOS-shaped).
- Reproducibility matters (e.g. for a publication, thesis, or
  policy-grade report).
- The user can budget time for a transparent screening pass with
  documented inclusion/exclusion decisions.

If any of those is false, use a scoping or rapid review instead.

## Step 1 — Protocol (PRISMA item 1, 2, 24a)

Write the protocol **before** searching. Include:

- Research question framed in PICO / PICOS / PEO format (depending on
  domain — see `references/academic-research-protocol.md`).
- Eligibility criteria (population, intervention, comparator, outcome,
  study type, language, date range).
- Information sources you will search (databases + grey literature +
  registries).
- Search strategy template (one strategy per source).
- Screening procedure (single vs dual screener, conflict resolution).
- Data items to extract.
- Quality assessment instrument (e.g. CASP, ROBINS, Cochrane RoB).
- Synthesis approach (narrative / meta-analysis / mixed).
- Reporting standard (this document defaults to PRISMA 2020).

Save the protocol as `research/protocol.md` in the work directory.

## Step 2 — Information sources (PRISMA item 6)

Default minimum set (all free / open):

- **OpenAlex** for cross-discipline coverage
  (`references/academic-databases.md`).
- **CrossRef** for DOI-resolution and reference enrichment.
- **PubMed / Europe PMC** for biomedical work.
- **arXiv / bioRxiv / medRxiv / SSRN** for preprints.
- **Semantic Scholar** for citation-context queries.

Optional with user-supplied legitimate access:

- Scopus / Web of Science / IEEE Xplore / ACM DL / JSTOR — only with
  institutional credentials the user can lawfully provide.

**Do not** crawl paywalled databases without legitimate access. If the
user does not have access, document the limitation in the report rather
than working around it.

## Step 3 — Search strategy (PRISMA items 7, 24b)

For each database, write the **exact** query string that will be run.
Persist these in `templates/search-log.csv` (one row per query) so the
review is reproducible.

Search strategy must include:

- Concept blocks joined by `AND`; synonyms within each block joined by
  `OR`.
- MeSH / Emtree / database-specific controlled vocabulary terms where
  applicable.
- Date filter matching the protocol's eligibility window.
- Language filter (note: do not filter out languages you can read —
  see `references/multilingual-research.md`).

Run each search and capture, per query:

- Date executed
- Total hits
- Number exported / kept

## Step 4 — Identification of records (PRISMA item 16)

Export records into a single working file. Deduplicate by:

1. DOI exact match.
2. Title-similarity match (Levenshtein distance < 5).
3. Author + year + journal match.

Use `scripts/data_clean.py dedup --on doi,title` to collapse duplicates.
Record the PRISMA flow numbers in `templates/prisma-flow.json` (see
template field documentation below).

### Step 4b — Citation chasing / snowball sampling

After initial identification, expand the candidate set via citation graph traversal:

```bash
# Create seeds.csv from included DOIs
python scripts/citation_graph.py expand --seed seeds.csv --direction both --max 500 --out citation-graph.json

# Convert to frontier candidates for further screening
python scripts/citation_graph.py to-frontier --graph citation-graph.json --out frontier-candidates.csv
```

Screen the new candidates through the same eligibility criteria (Step 5). This catches papers missed by keyword search. See `references/citation-graph.md`.

## Step 5 — Screening (PRISMA items 8, 17, 24c)

Screen records against eligibility criteria in two passes:

1. **Title + abstract** screen against the inclusion/exclusion criteria.
2. **Full-text** screen for survivors.

For each record, log to `templates/screening-log.csv` with:

- `included` (true/false)
- `exclusion_reason` (one of the protocol's pre-registered reasons)
- `relevance_score` 1–5
- `quality_score` 1–5

If two screeners are used, also log:

- `screener_1_decision`, `screener_2_decision`, `resolved_decision`
- `disagreement_reason` (when present)

## Step 6 — Data extraction (PRISMA items 9, 18)

For each included study, extract one row in the evidence ledger
(`templates/evidence-ledger.csv`). Required fields are listed in
`references/evidence-ledger.md`.

When the claim is empirical, also extract:

- Sample size
- Population characteristics
- Intervention / exposure
- Comparator (if any)
- Outcome measure
- Effect size + confidence interval (if reported)

## Step 7 — Risk of bias assessment (PRISMA items 11, 19–21)

Apply an appropriate risk-of-bias instrument depending on study design:

- RCTs → Cochrane RoB 2
- Non-randomised intervention studies → ROBINS-I
- Observational studies → ROBINS-E or Newcastle–Ottawa
- Qualitative studies → CASP qualitative checklist

Record per-domain judgements in the evidence ledger `notes` field, and
feed the overall judgement into the `confidence` column (low / medium /
high).

For a structural baseline, run `scripts/score_source.py score --file
templates/evidence-ledger.csv` to get a rubric-based pre-score. Override
manually based on the formal RoB judgement.

## Step 8 — Synthesis (PRISMA items 13, 20–23)

Pick one synthesis approach:

- **Narrative synthesis** — for heterogeneous studies, qualitative
  evidence, or scoping reviews. Group by sub-question / theme and
  describe the body of evidence in prose. See
  `references/synthesis-patterns.md` for the structure.
- **Meta-analysis** — for homogeneous quantitative outcomes with
  comparable effect measures. Use a dedicated tool (e.g. R `meta`,
  Stata `meta`, RevMan) — this skill does not perform meta-analysis
  arithmetic.
- **Mixed-methods synthesis** — combine narrative and meta-analytic
  results in clearly separated sections.

## Step 9 — Reporting (PRISMA items 13–27)

Produce these artifacts:

- `report.md` — the review itself, using the structure in
  `references/final-report-template.md`.
- `prisma-flow.json` — the populated PRISMA 2020 flow diagram counts
  (see `templates/prisma-flow.json` for the schema).
- `references.bib` — the included studies as a BibTeX file
  (`scripts/citation_export.py export`).
- `references.formatted.md` — citations rendered in the journal's
  required style with `scripts/citation_render.py render --style
  <alias>`.
- `evidence-ledger.csv[.hmac]` — the evidence ledger plus its
  tamper-evidence sidecar (`scripts/evidence_ledger.py sign`).

## Step 10 — Reproducibility checklist

Before declaring done, verify against
`references/reproducibility-checklist.md`. Every claim in the report
must be traceable to a ledger row, and every ledger row to a source
URL and access date.

## See also

- `references/academic-research-protocol.md` — general academic workflow
- `references/synthesis-patterns.md` — choosing review type
- `references/evidence-ledger.md` — ledger schema and conventions
- `references/source-quality-rubric.md` — quality scoring rubric
- `references/citation-management.md` — citation export and rendering
- `references/reproducibility-checklist.md` — reproducibility audit
- `templates/prisma-flow.json` — PRISMA flow diagram data schema
- `examples/systematic-review-prisma.md` — worked example
