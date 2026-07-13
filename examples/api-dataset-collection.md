---
example_status: illustrative
---

# Example: collecting an OpenAlex paper dataset

This example demonstrates the artifact contract and control flow. It does not
claim that a live collection was run, and it deliberately contains no invented
row counts or coverage percentage.

## Request

Collect public OpenAlex works about artificial intelligence published from
2024 through the actual run date. Return title, authors, DOI, citation count,
publication date, type, and abstract when present.

## Intake and unit of observation

- Shape: `dataset_collection` + `academic_research`
- Unit: one OpenAlex work per row
- Identity key: `openalex_id`; DOI is a secondary deduplication key
- Freshness boundary: record the real run timestamp; never query future dates
- Access: public API, read-only, rate-limit headers respected
- Completion claim: prohibited unless pagination and coverage gates pass

## Output schema

The data file is UTF-8 CSV with this exact header:

```csv
openalex_id,title,authors,doi,cited_by_count,publication_date,work_type,abstract,source_url,date_accessed
```

Supporting artifacts use the committed templates:

- `templates/data-dictionary.csv`
- `templates/data-package.json`
- `templates/api-request-log.csv`
- `templates/evidence-ledger.csv` (23-column canonical ledger)

The data dictionary declares the source field, type, cleaning rule, and
missingness computed from the final CSV. `missingness_pct` is calculated from
actual rows; it is never estimated in prose.

## Collection sequence

1. Probe the API and record status/rate-limit headers.
2. Build request parameters with a publication-date upper bound equal to the
   run date.
3. Fetch with cursor pagination and a conservative page/body cap.
4. Write every request to `api-request-log.csv`, including cursor and status.
5. Checkpoint the last committed cursor before requesting the next page.
6. Normalize authors to a semicolon-separated display string.
7. Reconstruct an abstract only when the source provides an inverted index.
8. Normalize DOI values, but retain works without a DOI under `openalex_id`.
9. Deduplicate first by `openalex_id`, then flag DOI collisions for review.
10. Validate row types, URL schemes, date bounds, and package metadata.

Example command shape:

```bash
node scripts/api_fetch.mjs \
  --url "https://api.openalex.org/works" \
  --params '{"search":"artificial intelligence","filter":"from_publication_date:2024-01-01","per-page":100}' \
  --pagination cursor \
  --cursor-key meta.next_cursor \
  --max-pages 10 \
  --out research-output/raw/openalex.json
```

The initial `--max-pages` value is a bounded pilot, not a completeness target.
Raise it only after checking rate limits, response size, and the collection
scope. If a page fails, the command must return incomplete metadata unless the
caller explicitly accepts partial output.

## Evidence and reporting

Dataset rows are data, not automatically evidence claims. Important statements
about scope, counts, exclusions, or field quality receive claim rows in
`evidence-ledger.csv`; operational failures use `record_type=process` or
`record_type=blocker`.

The final report derives, rather than hand-types:

- total rows from parsed CSV records;
- unique OpenAlex IDs and DOI collision counts;
- page/request counts from `api-request-log.csv`;
- date minimum/maximum from validated values;
- field missingness from `data-dictionary.csv`; and
- coverage gaps from stopped cursors, failed requests, and excluded records.

Acceptable wording is “collected N validated rows within the declared API/query
boundary.” Do not say “all AI papers” or assign a recall percentage without an
independent coverage study.

## Verification

```bash
python scripts/data_clean.py validate \
  --file research-output/data/ai-papers.csv \
  --schema research-output/data/ai-papers.schema.json
python scripts/evidence_ledger.py validate \
  --file evidence-ledger.csv
```

Finish with the reproducibility and execution gates in
`references/reproducibility-checklist.md` and `references/execution-gates.md`.
