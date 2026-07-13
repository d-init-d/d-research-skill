# Source Quality Rubric

## Contents

- [Source type ranking](#source-type-ranking)
- [Score dimensions](#score-dimensions)
- [Conflict resolution](#conflict-resolution)
- [Freshness rules](#freshness-rules)
- [Red flags](#red-flags)
- [Social Sources (v2.1)](#social-sources-v21)

Use this file to rank sources and resolve conflicts.

## Source type ranking

1. primary official source
2. public dataset or public API from source owner
3. standard, RFC, law, regulation, filing, or official registry
4. source code, release notes, changelog, issue tracker
5. peer-reviewed paper or authoritative preprint
6. reputable industry analysis or media
7. blog, tutorial, forum, community source
8. unsourced aggregation or AI-generated summary

## Score dimensions

### Automated dimensions (implemented by `scripts/score_source.py`)

Each automated axis is scored 0–5 (except type which uses a fixed map). The
script sums these into `base_total`, optionally adds `social_bonus`, and
reports `adjusted_total` (alias: `total`):

| Dimension | Field | Range | Meaning |
|---|---|---|---|
| source type | `type_score` | 0–5 | primary / official / paper / secondary / community / … |
| authority | `authority` | 0–5 | host is official or primary for the claim |
| freshness | `freshness` | 0–5 | publication date is current enough (never uses `date_accessed` as published) |
| traceability | `traceability` | 0–5 | exact anchor, source URL, reproducible access path, and usable evidence context |
| independence | `independence` | 0–5 | not merely copying another source |

`recency` and `methodology` remain deprecated v3 aliases of `freshness` and
`traceability`, respectively. Method transparency is deliberately a manual
gate; the automated scorer does not pretend to infer it from row length.

**Automated band** (`automated_band`, alias `band`):

- `high` if `adjusted_total >= 20`
- `medium` if `adjusted_total >= 13`
- `low` otherwise

Automated band is **not** final reviewed confidence.

### Manual review gates (not auto-high-confidence)

These gates are scored only by a human reviewer. Unresolved gates must never
be reported as final reviewed high confidence:

| Gate | Field | Meaning |
|---|---|---|
| relevance | `review_gates.relevance` | directly answers the question |
| method transparency | `review_gates.method_transparency` | explains data and method in enough detail |
| access quality | `review_gates.access_quality` | full content accessible, not just snippet |

`scripts/score_source.py score` accepts the same decisions as flat CSV fields:
`review_relevance`, `review_method_transparency`, and `review_access_quality`;
a `review_gates` JSON object is also accepted. The earlier RC field
`review_reproducibility` remains an optional compatibility gate: when supplied,
an explicit failure still blocks reviewed confidence, but its absence never
keeps the three required gates pending. Valid
decisions are `pass` and `fail` (`passed`/`ok`
and `failed`/`reject` are normalized aliases). The script preserves valid
human decisions in its output. Missing or invalid required input keeps the row
at `pending_manual_review`; an explicit failed gate produces `review_failed`;
partial reviews never become `reviewed`.

### Separated confidence fields

| Field | Meaning |
|---|---|
| `automated_band` | Score-derived band only (`high` / `medium` / `low`) |
| `review_status` | `unreviewed` · `pending_manual_review` · `review_failed` · `reviewed`; `reviewed` means all three required gates passed and no supplied compatibility gate failed |
| `final_reviewed_confidence` | Equals `automated_band` **only** when `review_status == reviewed`. Missing or unresolved review caps high at `medium_pending_review`; an explicit failure returns `low_review_failed`. |

Do **not** treat an unresolved review gate row as final reviewed high confidence.

## Conflict resolution

When sources disagree:

1. prefer the source closest to the primary data
2. prefer newer sources for changeable facts
3. prefer source with transparent methods
4. preserve minority evidence if credible
5. mark unresolved conflicts clearly
6. lower confidence instead of hiding disagreement

## Freshness rules

Always check dates for:
- software versions
- prices
- policies
- laws and regulations
- company facts
- security issues
- market data
- product availability
- documentation for actively developed tools

## Red flags

Downgrade sources that:
- lack date or author
- make broad claims without evidence
- have affiliate/commercial bias
- cite no primary source
- are stale relative to the topic
- contain obvious generated text or scraped summaries
- contradict primary sources without explanation

## Social Sources (v2.1)

When an evidence-ledger row contains the `verifiability` column (added in v2.1 for social-media archival), the following scoring modifiers are applied additively on top of the standard five-dimension score:

| Condition | Score Modifier | Rationale |
|---|---|---|
| `verifiability` is `archive_snapshot` | **+2** | The content has been preserved in the Wayback Machine, providing an independent third-party copy that can be re-checked. This significantly increases confidence that the evidence existed at the claimed time. |
| Row has a verified author handle (non-empty `author_handle` in source metadata or `author_handle=` present in `notes`) | **+1** | A verified author attribution strengthens provenance — the claim can be traced to a specific public account. |
| `verifiability` is `unverified` | **-1** | No independent verification path exists for this social evidence. The content may have been fabricated, edited, or taken out of context. Reduces confidence accordingly. |

These modifiers stack with each other and with the base score. For example, an `archive_snapshot` row with a verified author handle receives +3 total social bonus. An `unverified` row with no author handle receives -1.

The social bonus is reported as a separate `social_bonus` column in `score_source.py score` output, and is included in the `total` used for band classification (high/medium/low).
