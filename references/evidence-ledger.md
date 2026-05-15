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
| source_type | primary, official, dataset, code, paper, filing, secondary, community, unknown |
| date_published | publication date if available |
| date_accessed | date accessed by agent |
| access_method | search, fetch, playwright, public_file, public_api, screenshot, manual_needed |
| evidence | concise evidence extracted from source |
| quote_or_anchor | short quote, section, selector, page, or screenshot path |
| contradiction | none, possible, direct, unresolved |
| confidence | high, medium, low |
| notes | caveats and extraction notes |

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
