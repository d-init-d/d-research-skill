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


## Provenance / compliance columns (v3.0, optional)

Three additional optional columns appended after the social-media block. They are **purely additive** — existing ledgers (14-column legacy or 19-column v2.1) continue to validate, sign, and verify without change. Use them only when you can populate the value with real, checked information.

| Field | Allowed values | Semantics |
|---|---|---|
| `license_spdx` | empty, `NOASSERTION`, an SPDX-style token (`MIT`, `Apache-2.0`, `CC-BY-4.0`, `CC-BY-NC-4.0`, ...), or `LicenseRef-<token>` | Declared license of the captured source. Use `NOASSERTION` when the source is publicly accessible but no license is declared (the SPDX-conformant placeholder). Leave empty when license discovery has not been attempted. |
| `robots_status` | empty, `allowed`, `disallowed`, `unknown`, `not_checked`, `not_applicable` | Result of consulting the source host's `robots.txt` for the User-Agent that fetched the evidence. **Never set this to `allowed` unless robots.txt was actually checked**; default to `unknown` or `not_checked` when in doubt. Use `not_applicable` for canonical-metadata APIs (CrossRef, OpenAlex, NCBI), local files, and direct social-media APIs whose access is governed by ToS rather than robots. |
| `prov_activity_id` | empty or a stable identifier (recommended `prov:<script>:<hash>` or a UUID) | Identifier of the PROV-O `Activity` that generated this row. Lets `evidence_ledger.py prov-export` link claims to extraction events. Identifiers do not need to be globally unique across files; they only need to be stable inside one ledger. |

Validation rules:
- `license_spdx` must be empty, `NOASSERTION`, `LicenseRef-<token>`, or match `^[A-Za-z0-9.\-+]{1,64}$`.
- `robots_status` must be empty or one of the values above.
- `prov_activity_id` must be empty or a non-whitespace token of length 1-128.

### Backward compatibility matrix

| Schema | Columns | Status |
|---|---|---|
| Legacy | 14 | Read-only support: validates, signs, verifies. Skips social/provenance checks. |
| v2.1 social | 19 | Validates, signs, verifies. Provenance columns are not present. |
| v3.0 provenance | 22 | Validates, signs, verifies. All five social columns plus three provenance columns are included in the canonical bytes hashed by HMAC-SHA256, so tampering with any of them is detected. |

`evidence_ledger.py init` writes the 22-column header so new ledgers default to v3.0. `validate`, `sign`, and `verify` accept all three header sets.

### PROV-O export

```bash
python scripts/evidence_ledger.py prov-export \
  --file evidence-ledger.csv \
  --out prov.jsonld
```

The exporter emits a JSON-LD document with this shape:

```json
{
  "@context": {
    "prov": "http://www.w3.org/ns/prov#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "dcterms": "http://purl.org/dc/terms/",
    "dres": "https://github.com/d-init-d/d-research-skill/ns#"
  },
  "@graph": [
    {"@id": "claim:C001", "@type": "prov:Entity",
     "rdfs:label": "...", "prov:wasGeneratedBy": {"@id": "prov:wayback:abcd1234"}},
    {"@id": "https://example.com/source", "@type": "prov:Entity",
     "dres:robotsStatus": "allowed"},
    {"@id": "prov:wayback:abcd1234", "@type": "prov:Activity",
     "rdfs:label": "wayback_snapshot", "prov:used": [{"@id": "https://example.com/source"}]}
  ]
}
```

Rows without a `prov_activity_id` still appear as `prov:Entity` nodes; they just do not participate in the activity graph. Legacy and v2.1 ledgers without provenance columns export a graph with only entity nodes (no activities).
