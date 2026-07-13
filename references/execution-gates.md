# Execution Gates

## Contents

- [When to Apply](#when-to-apply)
- [Operating Principles](#operating-principles)
- [Gate 1: Source Map Gate](#gate-1-source-map-gate)
- [Gate 2: Coverage and Recall Gate](#gate-2-coverage-and-recall-gate)
- [Gate 3: Identity, Date, and Inference Gate](#gate-3-identity-date-and-inference-gate)
- [Gate 4: Evidence Verification Gate](#gate-4-evidence-verification-gate)
- [Gate 5: Synthesis Readiness Gate](#gate-5-synthesis-readiness-gate)
- [Optional Worker Roles](#optional-worker-roles)

Use these gates as a portable quality controller before synthesis. They capture
the strongest parts of orchestrated agent workflows without requiring MiniMax,
OpenAI, Claude, a specific subagent runtime, or any single research domain.

The gates reduce false completeness. They do not promise exhaustive Internet
coverage, and they never relax the safety boundary in
`references/safety-and-access-policy.md`.

## When to Apply

Apply the gates to any non-trivial research task, source-discovery task,
dataset collection task, public URL analysis, market or technical research,
academic review, public-role person aggregation, or answer that makes multiple
factual claims.

Keep the gates lightweight or skip them when a narrower branch already fits:

- Atomic fact lookups covered by `references/fact-verification.md`.
- Public social-media post capture covered by `references/social-media-archival.md`.
- Refusal or safety-boundary decisions where no source access is allowed.
- Very small single-source summaries where the user explicitly asks for speed
  and the answer is clearly marked as limited to that source.

## Operating Principles

- **Domain-neutral by default.** Gates should improve research across technical,
  academic, legal, financial, government, market, product, and local-language
  work. Do not force social/person workflows onto unrelated tasks.
- **Subagents are optional.** If the host runtime offers subagents, use them as
  independent reviewers. If not, the main agent performs the same checklists.
- **The main agent owns the merge.** Never blindly trust worker summaries.
  Deduplicate mirrors, reconcile conflicts, and preserve useful leads that a
  synthesizer might otherwise drop.
- **No access escalation.** A gate failure is a reason to search better,
  downgrade confidence, or report blockers, not a reason to bypass login walls,
  paywalls, captchas, rate limits, robots restrictions, or access controls.
- **Completeness is scoped.** Report reachable-evidence coverage and remaining
  gaps. Never claim total web coverage.

## Gate 1: Source Map Gate

Pass this gate when the run has a source map with:

- the task interpretation and major assumptions;
- entities, aliases, synonyms, versions, dates, locations, and source classes;
- candidate URLs or source classes for each major sub-question;
- access status when known: accessible, partial, blocked, login-required,
  paywalled, captcha, rate-limited, robots-restricted, broken, or unknown;
- the likely evidence each candidate can provide;
- the query or path that found each candidate;
- source-quality expectations: primary, official, original, secondary,
  mirror/reprint, community, social, archive, or unknown.

If the gate fails, build or repair the source map before extracting data.

## Gate 2: Coverage and Recall Gate

Use this gate when the answer would otherwise rely on thin discovery.

Triggers:

- fewer than three independent credible sources were found for a broad or
  multi-claim answer;
- fewer than three relevant source basins were checked;
- all useful evidence comes from one source basin;
- the answer depends on snippets, mirrors, reposts, or secondary summaries;
- the topic is obscure, old, local-language, historical, or long-tail;
- the first pass exposed names, aliases, versions, article titles, distinctive
  phrases, datasets, files, APIs, citations, or related entities that were not
  searched directly;
- the user asks for "deep research", "find all", "verify carefully",
  "collect sources", "maximum recall", or similar completeness language.

A source basin is a narrow evidence cluster, for example:

- official website or documentation;
- public data portal, API, registry, or filing;
- academic database or cited paper set;
- source code repository, release notes, issues, or discussions;
- government or standards source;
- one news outlet or media group;
- one community/forum/Q&A platform;
- one social or public-profile platform;
- archive, mirror, reprint, or aggregator;
- one time period, language variant, name variant, or geography.

Pass this gate when the run has either:

- checked the relevant basins for the task;
- found independent support across multiple basins;
- escalated once to `references/frontier-search.md` for documented gaps; or
- explicitly marked remaining basins as blocked, unavailable, irrelevant, or
  out of scope.

If the gate fails, run a recall pass:

1. Extract anchors from current evidence: exact names, aliases, titles, unique
   phrases, dates, versions, organizations, authors, domains, IDs, files,
   endpoints, citations, locations, and related entities.
2. Generate a different query plan from the first pass.
3. Try targeted follow-up queries across exact phrase, site-specific,
   file/API/dataset, official/primary, archive/mirror, contradiction, local
   language, and related-entity variants.
4. For audit-grade or user-requested maximum recall work, try at least ten
   targeted follow-up queries or document why fewer are sufficient.
5. If no new source appears, include the follow-up queries in the search trail
   and mark the answer as partial where appropriate.

Do not finalize a non-trivial answer from a single basin while claiming broad
coverage. Either continue discovery or state the limitation plainly.

## Gate 3: Identity, Date, and Inference Gate

Use this gate whenever claims involve people, organizations, products, versions,
schools, roles, dates, locations, historical events, social/public sources, or
same-name ambiguity.

Pass this gate when:

- each date, year, age, role, release, version, affiliation, or status claim is
  directly supported by source text or clearly marked as inference;
- same-name entities have been disambiguated with positive evidence, not only
  search ranking or partial name matches;
- article publication dates are not converted into event dates, school years,
  product release dates, or birth years unless a source states that explicitly;
- generational labels, grade/class labels, and approximate descriptors are
  reported as written rather than converted into exact facts;
- social, forum, or community leads are labeled as confirmed, likely, possible,
  uncertain/same-name risk, or likely different when identity matters;
- stale pages, mirrors, reprints, and duplicate reports are not counted as
  independent confirmation.

If the gate fails, downgrade confidence, split verified facts from inference,
or continue verification before synthesis.

## Gate 4: Evidence Verification Gate

Break the draft answer into atomic claims. For each important claim, verify:

- exact source URL or explicit unavailable/blocked marker;
- source title or stable label;
- source type and source basin;
- access method and extraction method;
- date/version/snapshot when relevant;
- evidence quote, value, selector, row, API field, or other anchor;
- contradiction status;
- confidence and caveat.

Prefer primary, official, original, recent, and directly accessible sources.
Use secondary sources to find primary sources, not as final authority when a
primary source is available.

If a claim cannot be tied to evidence, remove it, mark it as inference, or
downgrade confidence.

## Gate 5: Synthesis Readiness Gate

Before final output, confirm:

- source map exists or the task is explicitly small enough not to need one;
- search trail lists important queries and source paths tried;
- URLs opened or extracted are recorded separately from sources found only by
  search snippets;
- evidence ledger or evidence summary covers important claims;
- contradictions, stale sources, mirrors, duplicates, and confidence downgrades
  are visible;
- blockers and partial sources are reported with manual retrieval instructions
  when useful;
- coverage gaps are named;
- output does not overclaim completeness;
- final answer separates verified facts, inference, uncertainty, and unavailable
  data.

If any item fails, either continue the workflow or label the result as partial.

## Optional Worker Roles

When the host supports subagents or parallel workers, these roles are useful.
They are optional implementation details, not required dependencies.

| Role | Use when | Required output |
|---|---|---|
| Source Mapper | Starting non-trivial source discovery. | Source basins, exact queries, candidate URLs, access states, why each source matters, gaps. |
| Recall Auditor | Recall is thin, long-tail, old, local-language, contested, or single-basin. | Independent follow-up query plan, new candidates, duplicates/mirrors, blocked leads, remaining recall gaps. |
| Public Source Hunter | Public social/community sources are relevant and privacy-safe. | Public URLs, access states, identity labels, privacy caveats, blockers, next queries. |
| Data Extractor | Sources contain tables, files, APIs, embedded data, PDFs, or reusable datasets. | Structured output, schema/data dictionary, extraction method, coverage, quality checks. |
| Evidence Verifier | Factual claims, dates, identities, roles, versions, or contradictions matter. | Claim-level verification table with confidence and caveats. |
| Report Synthesizer | Multiple worker outputs need a final user-facing report. | Direct answer, evidence summary, blockers, contradictions, confidence, next steps. |

The main agent remains accountable for merging worker outputs, resolving
conflicts, and enforcing privacy and safety boundaries.
