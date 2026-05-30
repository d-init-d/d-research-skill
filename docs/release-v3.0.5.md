# Register- and Jargon-Aware Recall

v3.0.5 Release Notes

D Research v3.0.5 strengthens the recall layer of an agentic research run. It
adds a register- and jargon-aware discovery companion so the agent can match the
vocabulary of the people who actually hold the evidence — not the vocabulary the
model happened to be trained on. The result is higher recall on topics where the
authoritative discussion lives in a different register than the query: clinical
vs. lay, legal vs. street, standards vs. shop-floor, academic vs. community
jargon, or fast-moving emergent slang.

Crucially, the skill stores a *process for harvesting and verifying
register-matched vocabulary at runtime*, not a frozen word list. There is
nothing to maintain when slang changes — the update lives on the live web.

## What's New

- A new opt-in companion, `references/register-and-jargon-expansion.md`, built
  guardrails-first around five core principles: the skill stores a process not a
  word list; vocabulary is harvested from fresh results at recall time, never
  recalled from model memory; harvested vocabulary is a discovery layer and
  never evidence; the register ladder is bidirectional; and native-language
  research principles stay intact.
- A bidirectional **register ladder** — formal → vernacular to open recall, and
  vernacular → formal to anchor every community term back to a primary source —
  so a run never gets trapped in the community basin without a primary anchor.
- A `register_jargon_recall` intake label that activates only when the evidence
  basin demonstrably uses vernacular, subculture, or domain jargon.
- An audit-grade `templates/register-vocab-log.csv` that records one row per
  harvested term — including its register level, source basin, independent
  source count, status (`candidate` / `confirmed` / `rejected`), and the claims
  it ultimately produced — so a reviewer can replay exactly which vocabulary was
  trusted and why.
- Wiring across `SKILL.md`, `AGENTS.md`, `references/query-patterns.md`,
  `references/topic-decomposition.md`, `references/frontier-search.md`, and
  `references/multilingual-research.md` so register expansion is reachable from
  the decision tree, the query fanout, topic decomposition, and gap-driven
  follow-up.

## Why It Matters

A clinical, legal, standards, or academic query frequently under-recalls because
the people who hold the long-tail evidence use different words. Patients say
"brain fog", clinicians say "cognitive dysfunction". Practitioners abbreviate;
communities coin terms; slang moves faster than any maintained list. An agent
that searches only in the canonical register quietly misses entire source
basins — and an agent that descends into slang without anchoring back up ends up
citing community chatter as if it were fact.

v3.0.5 addresses both failure modes at the recall layer. The bidirectional
ladder opens recall *and* forces every community term back to a primary source
before it can support a claim. The guardrails make the hard part — not the
"add more slang" part — the center of the design.

## Discovery, Never Evidence

The single most important boundary in this release: harvested vocabulary is a
discovery aid, never evidence. Terms are kept only when they recur across two or
more independent community sources; single-source terms stay flagged as
candidates and never drive a wide fanout on their own. Every resulting claim
still anchors a real source and still passes `references/source-quality-rubric.md`
and the contradiction pass. Person-related slang inherits the
`references/person-aggregation.md` privacy boundary, and slurs, harassment
vocabulary, and brigading terms are explicitly excluded from recall.

## Compatibility

- No new runtime dependencies.
- No evidence-ledger schema changes.
- No script CLI changes.
- Existing v3.0, v3.0.1, v3.0.2, and v3.0.3 workspaces, ledgers, reports, and
  eval fixtures remain valid.

## Upgrade Notes

Pull the new release and continue using the skill normally. The register layer
is opt-in: it activates only when recall is thin or the evidence basin uses lay,
community, or vernacular terms, and otherwise stays out of the way. For
audit-grade runs, copy `templates/register-vocab-log.csv` into your workspace to
keep a replayable record of which vocabulary was trusted and which claims it
produced.
