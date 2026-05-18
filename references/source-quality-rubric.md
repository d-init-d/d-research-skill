# Source Quality Rubric

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

Score 0 to 5:

- authority: source is official or primary
- relevance: directly answers the question
- freshness: current enough for the claim
- method transparency: explains data and method
- reproducibility: can be checked by another person
- independence: not simply copying another source
- access quality: full content accessible, not just snippet

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
