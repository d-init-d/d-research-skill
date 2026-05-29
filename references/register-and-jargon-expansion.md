# Register and Jargon Expansion

Use this companion when recall is thin or the evidence basin speaks in a
different **register** than the query: clinical vs. lay, legal vs. street,
standards vs. shop-floor, academic vs. community jargon, or emergent slang.
The leverage is to match the vocabulary of the people who actually hold the
evidence, not to reach for the terms the model was trained on. This file stores
a *process for harvesting and verifying register-matched vocabulary at runtime*,
not a frozen word list. There is nothing to maintain here when slang changes —
the update lives on the live web.

## Safety and scope

Read this before any example below; the guardrails are the hard part.

- Stay read-only and follow `references/safety-and-access-policy.md`. Register
  expansion never bypasses login, paywall, captcha, rate limit, or `robots.txt`.
- Harvested vocabulary is a **discovery layer only — never evidence.** Every
  claim still anchors a real source and still passes
  `references/source-quality-rubric.md` plus the contradiction pass. Community
  jargon is a lead, not a fact.
- For named people, apply the privacy boundary in
  `references/person-aggregation.md` first. Slang that re-identifies a private
  individual, a minor, or a pseudonym is out of scope regardless of where it
  appears.
- Community and subculture sources are maps of how a topic is discussed, not
  authorities about private people or contested facts.
- Do not amplify slurs, harassment vocabulary, or brigading terms as "recall".
  A term that exists only to attack a person or group is not a research lead.

## Register ladder (four rungs, both directions)

Most topics are written about at several registers at once. Walk the ladder in
**both directions** so neither end is missing:

1. **Canonical / clinical / legal / technical** — the term in standards, filings,
   textbooks, official docs, ICD/CPT codes, statute language, scientific names.
2. **Lay / mainstream** — how generalist news and educated non-specialists say it.
3. **Community / domain jargon** — how practitioners, patients, hobbyists,
   trades, or fandoms say it among themselves; abbreviations and in-group terms.
4. **Emergent / vernacular slang** — fast-moving informal terms, memes, coinages,
   region- or platform-specific variants.

Two directions matter equally:

- **formal -> vernacular** opens recall: it surfaces community sources a clinical
  query would never reach.
- **vernacular -> formal** anchors evidence: every community term must be mapped
  back up the ladder to a primary or canonical source before it supports a claim.

A run that only descends ends up trapped in the community basin with no primary
anchor. A run that only ascends never finds the long-tail evidence.

## Discover -> filter -> expand -> verify loop

```
1. Seed from the formal/canonical term and the lay term for each sub-question.
2. DISCOVER: run fresh searches; read how real sources name the concept.
   Extract candidate register/jargon terms from the RESULTS, not from memory.
3. FILTER: keep only terms that recur across >=2 independent community sources.
   Drop typos, noise, one-off coinages, and brigading terms. Unconfirmed
   single-source terms stay flagged as `candidate`, never promoted to a query
   driver on their own.
4. EXPAND: re-run the fanout with confirmed terms, in both ladder directions.
5. VERIFY: map every community term back to a canonical/primary source. A term
   that cannot be anchored upward stays a discovery aid, not evidence.
6. Repeat until new searches stop yielding new confirmed terms (saturation),
   then hand off to the normal evidence ledger and contradiction pass.
```

This is a thin loop on top of the standard workflow, not a replacement for it.

## Harvesting rules

- Harvest vocabulary from **fresh search results, page text, and result
  snippets** captured this run.
- Do **not** dump slang or jargon from model memory. Model-recalled slang is
  stale, hallucination-prone, and detached from any source basin.
- Record where each term was first seen so it can be re-checked and so the
  ladder mapping is auditable.
- Prefer terms that the source itself frames as the in-group name ("we call
  this…", glossaries, pinned community wikis, tag taxonomies).

## Filtering rules

- Keep a term only when it recurs across **at least two independent community
  sources** (different authors, sites, or threads — mirrors and reposts do not
  count as independent).
- Reject obvious typos, autocorrect artifacts, throwaway coinages, and terms
  that appear only inside a single brigading or pile-on thread.
- A term seen once is a `candidate`: you may probe it, but do not let it drive a
  wide fanout or appear in output as established vocabulary until confirmed.
- When a term is rejected, record why; the rejection is itself useful audit data.

To make the cross-source recurrence rule deterministic, feed your tagged
`source<TAB>term` occurrences to `scripts/harvest_terms.py` (subcommand
`harvest`, default threshold `>=2`). It counts distinct sources per candidate
term and labels each `confirmed` or `candidate`; it never invents vocabulary.

## Query expansion patterns

Reuse the fanout syntax from `references/query-patterns.md`, adding both ladder
directions. Patterns, not a required checklist:

```text
"<canonical term>" OR "<lay term>" OR "<community term>"
"<community jargon>" "<canonical term>"        # vernacular -> formal anchor
"<canonical term>" forum OR community OR thread # formal -> vernacular recall
"<abbreviation>" "<expanded official name>"
site:<community-domain> "<emergent slang>"
"<slang>" meaning OR definition OR glossary
"<standards identifier>" "<shop-floor name>"
```

Keep the original-language term first for multilingual work (see below); do not
let an English slang pivot overwrite the native register.

## Logging and reproducibility

For ordinary work, record discovered terms in the `notes` column of
`templates/search-log.csv`.

For audit-grade work, use the dedicated `templates/register-vocab-log.csv`. It
captures one row per harvested term — `term`, `language`, `register_level`,
`source_basin`, `first_seen_url`, `supporting_source_urls`,
`independent_source_count`, `status` (`candidate` / `confirmed` / `rejected`),
`rejection_reason`, `used_in_queries`, `resulting_claim_ids`, and `notes` — so a
reviewer can replay exactly which vocabulary was trusted, why, and which claims
it produced. This keeps the discovery layer separable from, and traceable to,
the evidence ledger.

## Failure modes and guardrails

| # | Trap | Blocking rule |
|---|---|---|
| 1 | Model invents slang from memory | Harvest from fresh results only; this file forbids memory-recalled vocabulary. |
| 2 | Typos / noise / brigading terms inflate the fanout | Keep only terms recurring across >=2 independent community sources; single terms stay `candidate`. |
| 3 | Treating community sources as truth | Vocabulary is discovery only; every claim still passes `references/source-quality-rubric.md` and the contradiction pass. |
| 4 | Getting stuck in the community basin | Register ladder is bidirectional; a vernacular->formal anchoring step to a primary source is mandatory. |
| 5 | English-pivot breaks native-speaker recall | Keep `references/multilingual-research.md` intact; register is an additive layer; extract original-language terms first. |

## Integration

- `references/query-patterns.md` — the fanout this layer extends with ladder
  directions.
- `references/topic-decomposition.md` — record register/jargon variants beside
  entity aliases during decomposition.
- `references/frontier-search.md` — feed confirmed register variants in as
  `alias`-type frontier nodes when a gap persists; do not invent a new node type.
- `references/multilingual-research.md` — register sits on top of the
  native-language workflow, never instead of it.
- `references/evidence-ledger.md` — the discovery vocabulary stays out of the
  ledger; only anchored claims enter it.

## See also

- `references/query-patterns.md` — core query fanout.
- `references/topic-decomposition.md` — entity and alias expansion.
- `references/frontier-search.md` — gap-driven follow-up controller.
- `references/multilingual-research.md` — cross-language recall workflow.
- `references/vietnamese-source-discovery.md` — diacritic/no-diacritic register, a narrow companion case.
- `references/source-quality-rubric.md` — scoring that keeps discovery out of evidence.
- `references/person-aggregation.md` — privacy boundary for person-related slang.
- `references/safety-and-access-policy.md` — non-negotiable access boundaries.
- `templates/search-log.csv` — lightweight term logging.
- `templates/register-vocab-log.csv` — audit-grade register vocabulary log.
- `scripts/harvest_terms.py` — deterministic cross-source recurrence filter for candidate terms.
