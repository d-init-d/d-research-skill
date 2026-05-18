# Evidence Ledger

Use this file for every non-trivial research task.

## Purpose

The evidence ledger prevents unsupported claims, weak synthesis, and source confusion.

## Required fields

| Field | Meaning |
|---|---|
| claim_id | stable ID such as C001 |
| claim | atomic factual claim |
| sub_question | which sub-question the claim answers |
| source_title | title of source |
| source_url | URL or local path |
| source_type | primary, official, dataset, code, pdf, paper, filing, secondary, community, unknown |
| date_published | publication date if available |
| date_accessed | date accessed by agent |
| access_method | search, fetch, playwright, public_file, public_api, screenshot, manual_needed |
| evidence | concise evidence extracted from source |
| quote_or_anchor | short quote, section, selector, page, or screenshot path |
| contradiction | none, possible, direct, unresolved |
| confidence | high, medium, low |
| notes | caveats and extraction notes |

## CSV quoting (RFC 4180)

When the ledger is written as a CSV file, embedded quotes inside a quoted field MUST be **doubled** (`""`), not backslash-escaped (`\"`). Python's `csv.DictReader`, Excel, and `scripts/run_dogfood.py score` all follow RFC 4180 and will split the row at the wrong column otherwise — silently corrupting `source_url`, `evidence`, and downstream recall/accuracy scores.

Bad (`\"` — breaks the parser):
```csv
C002,"API rejected with body {\"error\":\"Pagination error.\"}",https://api.example.org/works?per-page=201,...
```

Good (`""` — RFC 4180 compliant):
```csv
C002,"API rejected with body {""error"":""Pagination error.""}",https://api.example.org/works?per-page=201,...
```

When in doubt, write the ledger through Python's `csv.DictWriter(..., quoting=csv.QUOTE_MINIMAL)` rather than hand-formatting the rows. The harness validates this when scoring — a row that mis-quotes will show up as a recall miss or an accuracy miss, not as a CSV syntax error.

## Failed fallback attempts

For blocked public tier-1 sources, follow `references/anti-bot-fallback.md`. If a fallback attempt fails, record it as a low-confidence process row using the existing schema rather than adding ad-hoc columns. These rows prove search coverage; they are not positive evidence for the final claim. Put `fallback_result=blocked`, `fallback_result=not-found`, or `fallback_result=refused` in `notes`.

## Atomic claims

Keep each claim small.

Bad:
- Tool X is the best scraper and is open-source and works everywhere.

Good:
- Tool X is open-source under license Y.
- Tool X supports browser automation.
- Tool X supports JavaScript-rendered pages.
- Tool X is suitable for this task because the target page requires JavaScript rendering.

## Confidence rules

High confidence:
- supported by primary or official source
- current enough for the task
- no unresolved contradiction
- directly observed or extracted

Medium confidence:
- supported by reputable secondary source
- primary source inaccessible but referenced
- minor date/version uncertainty

Low confidence:
- only snippet available
- source is old or unofficial
- conflicting evidence exists
- extraction was partial

## Evidence table template

```markdown
| ID | Claim | Source | Type | Date | Access | Evidence | Contradiction | Confidence |
|---|---|---|---|---|---|---|---|---|
```

## Final claim audit

Before final answer, check:
- every key claim has evidence
- every source URL is recorded
- freshness-sensitive claims have dates
- blocked sources are not treated as evidence
- contradictions are disclosed
- inference is labeled as inference

## Social archival columns (v2.1)

Five optional columns appended after `notes` to support social-media evidence rows. Existing ledgers without these columns remain valid and continue to pass `evidence_ledger.py validate`.

| Field | Allowed Values | Semantics |
|---|---|---|
| archive_url | Any URL or empty | Wayback Machine or other archive URL for the captured content. Empty for Tier A direct-API captures that have no archive copy. |
| content_hash | SHA-256 hex string or empty | Hash of the canonicalised post text at capture time. Used for tamper detection on re-verification. Empty when text could not be extracted (Tier B). |
| snapshot_status | `intact`, `edited`, `deleted`, `unknown`, or empty | Result of the most recent verification pass. `intact` = content unchanged, `edited` = content differs from original hash, `deleted` = source returned 404, `unknown` = cannot re-verify (Tier B / archive-only). Empty if never verified. |
| verifiability | `direct_api`, `direct_api_deleted`, `archive_snapshot`, `screenshot_only`, `unverified`, or empty | Confidence classification for the evidence capture method. `direct_api` = fetched from a stable public API with content hash. `direct_api_deleted` = was direct_api but post has since been deleted. `archive_snapshot` = captured via Wayback Machine only. `screenshot_only` = only a screenshot exists. `unverified` = no independent verification path available. Empty for non-social rows. |
| verifiability_note | Plain-language sentence or empty | Human-readable explanation of what the verifiability label means for this specific row. Example: "Fetched directly from Reddit JSON API; content hash can be re-verified." |

### HMAC coverage

When `evidence_ledger.py sign` is invoked on a ledger containing these columns, all five are included in the canonical bytes hashed by HMAC-SHA256. Tampering with any social column value will be detected by `evidence_ledger.py verify`.

### Validation rules

- `verifiability` must be one of the allowed values listed above, or empty.
- `snapshot_status` must be one of the allowed values listed above, or empty.
- All other new columns are free-form (no value restriction beyond CSV quoting rules).
