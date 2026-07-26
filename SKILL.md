---
name: d-research
description: >-
  Browser-first deep research and lawful public-data collection for AI agents.
  Use for web research, source discovery, public-data scraping, literature or
  market/technical research, due diligence, policy/standards analysis, cultural
  research, atomic fact verification, single-URL inspection, public social-post
  archival, cross-platform social research, scoped person OSINT, self-exposure
  audits, investigative OSINT, semantic corpus retrieval, evidence ledgers,
  execution gates, and blocker reports. Read-only; never bypasses
  logins, paywalls, captchas, robots restrictions, or rate limits.
---

# D Research

## Mission

Maximize reachable public evidence under available tools and open-web constraints.
Default browser automation: Playwright.

Use for deep web research, public data collection, source discovery, academic
and literature review, market/technical research, due diligence, policy and
standards analysis, creative/cultural research, dynamic-page evidence, and
blocker reports.

Investigative capability uses tiers `R0` through `R4`: public research, deep
investigation, scoped person OSINT, verified self-exposure audit, and authorized
security research. Higher tiers add scope and evidence tools; none weakens the
`RX` prohibited floor in `references/investigative-research.md`.

Never use this skill to bypass access controls, login walls, paywalls, captchas,
rate limits, robots restrictions, or explicit access restrictions.

## Safety invariants (never allowed)

- Bypass login, authentication, paywalls, or subscription checks.
- Solve or evade captchas. Config `access.allowCaptchaSolving` must be `false`;
  `true` fails validation. Captcha solving is never allowed.
- Stealth plugins or anti-detection. Config `access.allowStealthEvasion` must be
  `false`; `true` fails validation. Stealth evasion is never allowed.
- Evade rate limits or anti-bot systems.
- Stolen cookies, leaked tokens, or credentials not provided by the user.
- Secret validation or raw breach-dump acquisition, retention, or redistribution.
- Minors targeting, stalking, doxxing, harassment, real-time whereabouts,
  unauthorized pseudonym re-identification, malware, exploitation, or exfiltration.
- Private/personal/sensitive data without a validated scope and authorization.
- Ignore robots when acting as a crawler (`--no-respect-robots` hard-fails).
- External mutation is never implicit: `social_snapshot.py snapshot` archives
  only with `--submit-archive`, and `wayback.py save` is an explicit command.

Lawful authenticated access with user-provided credentials is distinct from
bypass/evasion and remains read-only by default.

Full policy: `references/safety-and-access-policy.md`.

## Tool priority by phase

1. **Discovery:** user context → web search.
2. **Probe:** Playwright/browser → fetch → web-search-only fallback.
3. **Extraction:** public file/API/static DOM → browser-rendered content.

Anti-bot blocked tier-1 public sources: run the bounded chain in
`references/anti-bot-fallback.md` once (API/static → archive → cache/snippet →
fetch-only → blocker). Never use it to bypass controls.

Adapter policy: `references/tool-adapter-policy.md`.

## Data access layers

1. Web pages and files (browser/fetch)
2. Public APIs (REST/GraphQL/SPARQL) — `references/api-access-workflow.md`
3. Academic databases — `references/academic-databases.md`
4. Wikidata — `adapters/wikidata.md`
5. Read-only databases when user provides access — `adapters/database-readonly.md`
6. Specialized domains — `references/specialized-domains.md`
7. Authorized breach-intelligence or user-supplied incident data — only through
   `references/self-exposure-audit.md` and `references/leaked-data-handling.md`

## Intake and routing

**Step 0:** Classify with `references/research-intake.md` before opening sources.
Assign shape labels, depth (fast/standard/completeness-first), safety posture,
output artifact, authority basins, required ledgers/gates. Ask the user only when
ambiguity changes safety, legality, scope, or deliverable.

**Long-horizon outer loop:** When more than 5 sub-questions, more than 50 sources,
multi-context runtime, or audit-grade output, use research plan schema 2.0
(`references/research-plan-protocol.md`):

1. `node scripts/run_python.mjs scripts/research_plan.py init --slug <slug>
   [--title "..."]` (generic draft)
2. Fill tasks with `phase: research|synthesis`, sub-questions, outputs under
   `research-output/`
3. `configure-execution` → `render` → `gate --gate plan_ready` → `approve` →
   `gate --gate execute_ready`
4. Dispatch only after `execute_ready`/`dispatch_ready` passes; write findings to
   declared outputs immediately
5. `gate --gate synthesize_ready` (research phase only; real HMAC via
   `D_RESEARCH_LEDGER_KEY`; completed checklist)
6. Compose report from `report.draft.md` / section inputs
7. `gate --gate release_ready` (synthesis complete; exact report path; 100 percent
   claim coverage; stopping criteria)

For `R1`-`R4` routes, create and validate `investigation-scope.json`. When the
scope claims `reviewed_public_interest`, `self_verified`, or `authorized`, use
`investigation_policy.py bind-authorization` so reviewer, method, expiry, and
the exact scope hash are recorded; a user-declared purpose is not proof. Then
run `research_plan.py bind-policy --route <route> --scope
investigation-scope.json`. The plan gate checks the exact scope bytes and
requires every research and synthesis task to carry that policy input. Any scope change
invalidates the authorization hash and requires authorization binding, plan
binding, rendering, and approval again.

Migrate v1 plans: `scripts/research_plan.py migrate`. Always report workspace path.

**Before final synthesis:** Apply `references/execution-gates.md` unless a
fast-path branch says otherwise. Do not claim completeness unless gates pass.

### Route table

| Route | Reference |
|---|---|
| Atomic fact | `references/fact-verification.md` |
| Social post archive | `references/social-media-archival.md` |
| Cross-platform social research | `references/social-source-research.md` |
| Scoped person OSINT | `references/person-aggregation.md` |
| Investigative OSINT / threat intelligence | `references/investigative-research.md` |
| Verified self-exposure audit | `references/self-exposure-audit.md` |
| Leak reporting / authorized corpus | `references/leaked-data-handling.md` |
| Semantic corpus query | `references/semantic-retrieval.md` |
| Broad multi-source research | `references/workflow-routes.md` |
| Due diligence / red flags | intake `due_diligence_or_investigation` |
| Policy / standards / RFC | intake `policy_or_standards_analysis` |
| Creative / cultural | intake `creative_or_cultural_research` |
| Technical research | `references/source-discovery.md`, `references/workflow-routes.md` |
| Market / competitor | `references/source-discovery.md`, `references/source-quality-rubric.md` |
| Legal / government / financial | `references/specialized-domains.md` |
| Medical / safety | `references/specialized-domains.md`, `references/source-quality-rubric.md` |
| Dataset collection | `references/data-extraction-toolbox.md`, `references/data-processing-pipeline.md` |
| Academic / literature | `references/academic-research-protocol.md`, `references/citation-management.md` |
| Systematic / PRISMA | `references/systematic-review-protocol.md` |
| Single URL | `references/browser-first-crawl.md`, `references/anti-bot-fallback.md` |
| API collection | `references/api-access-workflow.md` |
| Large-scale (100+) | `references/large-scale-collection.md` |
| Monitoring / change detection | `references/monitoring-change-detection.md` |
| Visualization / rendered report | `references/data-visualization.md`, `references/report-generation.md` |
| Multilingual / Vietnamese | `references/multilingual-research.md`, `references/vietnamese-source-discovery.md` |
| Thin recall / jargon | `references/register-and-jargon-expansion.md` |
| Evidence gaps | `references/frontier-search.md` |

Narrative branch detail: `references/workflow-routes.md`.
Machine-readable routes: `templates/route-manifest.json`.

## Core deep research workflow

1. Restate goal, entities, timeframe, geography, language, output, source constraints.
2. Decompose (`references/topic-decomposition.md`): sub-questions, facets, aliases,
   source classes, stopping criteria.
3. Source map (`references/source-discovery.md`): official, primary, papers, APIs,
   datasets, archives.
4. Query fanout (`references/query-patterns.md`): broad, exact, official, primary,
   filetype, site, dataset, recent, contradiction; register variants when needed.
5. Probe with browser-first access; classify access state; never force blocked pages.
6. Extract least-invasively: public files → public APIs → static markup → rendered text.
7. Expand via links/sitemaps/APIs within crawl limits; respect robots.
8. Maintain the 37-column evidence ledger (`references/evidence-ledger.md`);
   classify social and non-official items by speaker, relationship, origin,
   lineage, discovery disposition, and reporting disposition; sign with
   `scripts/evidence_ledger.py sign` for long-horizon plans and audit-grade work.
9. Contradiction pass; score sources (`references/source-quality-rubric.md`).
10. Blocker reports (`references/blocker-report.md`) for unreachable tier-1 sources.
11. Synthesize only after gates; use `references/final-report-template.md`.

Default crawl limits: depth 2, 30 pages/domain, 100 total, 1000 ms delay, robots true.

## Adapters and fallbacks

Default adapter: `adapters/playwright.md`. Alternatives:
`adapters/generic-browser.md`, `adapters/fetch-only.md`,
`adapters/web-search-only.md`, `adapters/graphql.md`,
`adapters/citation-resolver.md`, `adapters/translation.md`.

If Playwright is unavailable, use the configured browser adapter. If no browser
exists, use fetch. If fetch is unavailable, use web search and mark limitations.

Blocked relevant public tier-1 sources: one pass of
`references/anti-bot-fallback.md` then `references/blocker-report.md`. Record
failed attempts as low-confidence process ledger rows.

## Crawl and expansion defaults

When acting as a crawler:

- max depth: 2
- max pages per domain: 30
- max total pages: 100
- delay between page loads: 1000 ms
- respect robots: always true (policy hard-fail if disabled)
- follow external links: false unless needed for source discovery
- TLS verification on by default; `--ignore-tls-errors` is opt-in and must be
  recorded as a limitation

## Plan gates summary (schema 2.0)

| Gate | Meaning |
|---|---|
| plan_ready | Complete filled plan, rendered PLAN.md, not started |
| execute_ready / dispatch_ready | Approved and ready to run |
| synthesize_ready | Research phase terminal; ledger valid+HMAC; checklist complete |
| release_ready | Synthesis done; exact report+citations; full claim coverage |

Canonical assertion sets live in `templates/route-manifest.json` and are enforced
by `scripts/research_plan.py`. Standard gates cannot be emptied.

## Evidence and output contract

Every important claim needs source, type, dates, access method, evidence,
contradiction status, and confidence. Separate facts, inferences, speculation,
and unknowns.

Ledger rows may set `record_type`: `claim` (default), `lead`, `process`, or
`blocker`. Leads never count as authored claims and never enter main findings.
Release requires full narrative coverage of `claim` rows via `[ref:claim_id]` in
authored text only (not generated Evidence Summary or References blocks).

For investigative outputs, keep `Main findings`, `Non-official / unverified
leads`, `Blocked / prohibited sources`, and `Contradictions / unknowns`
separate. A platform is never inherently official: classify each social item by
who spoke, their relationship to the claim, content origin, integrity, and
independent lineage.

For broad and non-trivial routes, the final answer includes: direct answer, key
findings, evidence summary, data collected, sources reached/blocked,
contradictions/caveats, confidence, and next steps. Narrow fast paths follow
their branch-specific output contract instead of manufacturing unused sections.

Never present results as complete unless the relevant execution gates passed.

Render/lint: `scripts/report_render.py`. Claim coverage:
`report_render.py lint --workspace <dir> [--report <exact-path>] --strict`.

## High-stakes and privacy boundaries

Hard-stop before broad research when intake indicates `RX`, access-control
bypass, minors, stalking/doxxing/harassment, stolen secrets, or unauthorized
intrusion. Do not infer permission from a user's job title.

Scoped person OSINT (`references/person-aggregation.md`) may expand aliases,
relationships, timelines, contradictions, and public-professional frontier
nodes without a fixed row cap. Stop on saturation, scope/risk budgets, or an
`RX` boundary. Discovery does not imply retention or reporting: personal
contact, residence, government IDs, finances, medical data, family/minors, and
precise whereabouts are discarded or redacted.

Social transport tiers in `references/social-media-archival.md` describe capture
and verifiability only. Evidentiary authority is item-level and platform-neutral
under `references/social-source-research.md`.

Self-exposure work is `R3`, requires verified ownership/authorization and a
named-recipient output, and reports exposure metadata plus remediation—never
secrets or unrelated victims. Raw-leak references are metadata-only `lead`
rows with no dump URL, excerpt, hash, or main-finding disposition.

## Signing and reproducibility

For every long-horizon plan workspace, and for audit-grade work on any route:

1. Maintain `evidence-ledger.csv` (37-column canonical; exact legacy
   14/19/22/23 headers remain readable, signable, and verifiable).
2. Sign with `scripts/evidence_ledger.py sign --file evidence-ledger.csv --key-env D_RESEARCH_LEDGER_KEY`.
3. Complete `reproducibility-checklist.md` (no unchecked boxes; N/A as checked with reason).
4. Render: `scripts/report_render.py render --workspace <dir>`.
5. Lint exact report: `scripts/report_render.py lint --workspace <dir> --report <path> --strict`.
6. Gate release: `scripts/research_plan.py gate --gate release_ready`.

Tampered ledgers with stale HMAC sidecars must fail every release gate.

## Optional helpers

Scripts under `scripts/` are optional. Key entry points:

- Browser: `playwright_probe.mjs`, `playwright_extract.mjs`, `playwright_crawl.mjs`
- Plan/report: `research_plan.py`, `report_render.py`, `evidence_ledger.py`
- Investigation policy: `investigation_policy.py`
- Network: `api_fetch.mjs`, `web_search.mjs`, `http_cache.py`
- Academic: `citation_export.py`, `citation_render.py`, `citation_resolver.py`
- Social/archive: `social_snapshot.py`, `wayback.py`
- Quality: `score_source.py`, `run_dogfood.py`, `check_contract.py`

Full inventory: `references/script-inventory.md`.

## Configuration

Obey project `research.config.json` or `research.config.example.json` defaults.
Access is read-only. Captcha solving and stealth evasion are never allowed.
Field reference: `references/config-reference.md`.

## Compatibility notes

- Research plan v1 loads with a one-shot deprecation warning until v4; run migrate.
- Ledgers with 14, 19, 22, or 23 columns remain valid; missing `record_type` is
  `claim`. New ledgers use 37 columns.
- CLI alias `--paginate` remains with one deprecation warning; prefer `--pagination`.
- Root `report.md` is deprecated; prefer declared outputs under `research-output/`.

## Further reading

- Methodology: `references/research-bibliography.md`
- Routes: `references/workflow-routes.md`
- Scripts: `references/script-inventory.md`
- Config: `references/config-reference.md`
- Contributors: `CONTRIBUTING.md`
