---
example_status: illustrative
---

# Example: systematic review of time-series transformer research

This is a protocol example, not a completed review. It contains no fabricated
search totals, screening counts, effect estimates, or study conclusions.

## Review question

What transformer-based architectures have been evaluated for time-series
forecasting, under which datasets and metrics, and what evidence supports
comparative performance or efficiency claims?

The search end date is the actual execution date. A review run before the end
of a calendar year must not claim coverage through that future year.

## Protocol

- Shape: `academic_review` + `systematic_review`
- Depth: completeness-first
- Sources: OpenAlex, Crossref, PubMed when relevant, arXiv, and venue/publisher
  pages for canonical metadata
- Required artifacts: PRISMA flow, search log, screening log, evidence ledger,
  citation library, protocol deviations, and final report
- Contradiction focus: dataset split comparability, metric direction, baseline
  tuning, compute budget, and inconsistent efficiency claims

Register the query, eligibility criteria, databases, date/language scope,
deduplication policy, screening process, extraction fields, and synthesis plan
before opening results.

## Canonical logs

Copy the committed headers; do not invent a YAML substitute.

`search-log.csv`:

```csv
sub_question,query,tool,date,results_reviewed,candidate_sources,kept_sources,notes
```

`screening-log.csv`:

```csv
id,title,authors_or_org,year_or_date,url_or_doi,source_type,included,exclusion_reason,relevance_score,quality_score,notes
```

`evidence-ledger.csv` uses the exact 23-column header from
`templates/evidence-ledger.csv`. Study-extraction data belongs in a separate
table, for example:

```csv
study_id,canonical_url,architecture,dataset,task,horizon,split_protocol,metric,metric_value,baseline,compute_reported,notes
```

Never compare metric values across papers until task, horizon, split, scaling,
and metric direction are compatible.

## Search and screening

1. Build database-specific queries from the registered concept blocks.
2. Record exact query text, execution date, and returned/reviewed counts.
3. Resolve DOI/arXiv identifiers to canonical metadata before expansion.
4. Deduplicate with DOI first and normalized title/author/year second.
5. Screen title/abstract, then full text, with a reason for every exclusion.
6. Snowball backward and forward from included studies; label the discovery
   method in the search log.
7. Search explicitly for corrections, retractions, replications, and
   contradictory evaluations.

PRISMA counts are computed from the logs and written to
`templates/prisma-flow.json`. The following equalities must hold:

```text
records_after_duplicates_removed = records_identified - duplicate_records_removed
full_text_reports_assessed = records_screened - records_excluded
studies_included = full_text_reports_assessed - full_text_reports_excluded
```

If the review uses additional-source discovery, record those flows separately
instead of forcing the arithmetic into the database-search branch.

## Evidence and synthesis

Each factual report claim points to one or more ledger claim IDs with
`[ref:claim_id]`. A source row records an exact quote/anchor and enough method
context to distinguish reported results from the reviewer's inference.

Synthesis separates:

- architecture taxonomy;
- evaluation design and dataset coverage;
- comparable performance evidence;
- computational/efficiency evidence;
- contradictions and sensitivity to protocol choices; and
- evidence gaps.

Do not write “consistently outperforms,” “state of the art,” or a complexity
claim from model memory. Those statements require compatible primary studies,
independent verification, and contradiction review.

## Citations and report

Resolve canonical identifiers, export BibTeX/RIS, and parser-round-trip the
library before rendering the selected style. Use
`scripts/citation_resolver.py`, `scripts/citation_export.py`, and
`scripts/citation_render.py`.

The report follows the registered protocol and includes the PRISMA flow,
deviations, quality assessment, evidence tables, synthesis, limitations,
coverage gaps, and confidence. It may claim completion only after the
systematic-review and execution gates pass.

## Verification

```bash
python scripts/evidence_ledger.py validate --file evidence-ledger.csv
python scripts/citation_export.py self-test
python scripts/report_render.py lint --workspace research-workspace --strict
```

See `references/systematic-review-protocol.md`,
`references/academic-research-protocol.md`, and
`references/reproducibility-checklist.md`.
