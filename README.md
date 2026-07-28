# D Research

**Production-grade research skill for AI agents: search, browser automation, APIs, archives, extraction, evidence ledgers, and reproducible evals.**

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)
[![Release](https://img.shields.io/github/v/release/d-init-d/d-research-skill?sort=semver)](https://github.com/d-init-d/d-research-skill/releases)
[![Self-test](https://github.com/d-init-d/d-research-skill/actions/workflows/lint-and-self-test.yml/badge.svg)](https://github.com/d-init-d/d-research-skill/actions/workflows/lint-and-self-test.yml)
[![Link check](https://github.com/d-init-d/d-research-skill/actions/workflows/link-check.yml/badge.svg)](https://github.com/d-init-d/d-research-skill/actions/workflows/link-check.yml)

Vietnamese docs: [README.vi.md](README.vi.md)

> D Research turns ad hoc agent research into an auditable workflow: plan the question, discover sources, collect public evidence, extract structured data, resolve citations, write a ledger, pass synthesis-readiness gates, and verify the result with offline benchmarks.

Looking for the prebuilt multi-agent version? See
[D Research Ultra](https://github.com/d-init-d/d-research-ultra-skill),
which builds on this core skill and adds a runtime-neutral orchestrator
plus six ready-to-register worker roles.

---

## At a glance

| Area | What D Research provides |
|---|---|
| Primary users | AI agents and agent operators who need source-backed research, public-data collection, literature review, fact verification, or long-horizon investigation workflows. |
| Access model | Read-only by default. Explicit, user-authorized archival or API mutation operations remain available through dedicated commands or `--intent archive\|mutation`. |
| Evidence model | Every meaningful claim should land in an evidence ledger with source, quote/value, access method, confidence, contradictions, provenance, and optional HMAC signature. |
| Outputs | Evidence ledgers, citation files, extracted tables, frontier ledgers, coverage maps, research plans, reports, and reproducibility metadata. |
| Verification | Offline self-tests, internal-reference checks, a 12-task regression bench, and a 52-task frontier bench covering 26 capability classes. |
| Safety posture | Never bypass login, paywalls, captchas, rate limits, robots restrictions, or access controls. Blocked sources become blocker reports, not escalation attempts. |

## When to use it

Use D Research when an agent needs to:

- answer a question with primary or high-quality sources rather than unsupported assertions;
- collect lawful public data and preserve an audit trail;
- compare contradictory sources and record uncertainty;
- work across search engines, browser pages, APIs, PDFs, archives, academic IDs, and local files;
- run systematic reviews, technical research, market/public-data scans, or multi-step long-horizon research;
- run scoped investigative OSINT, cross-platform social research, authorized threat intelligence, or a verified self-exposure audit;
- verify that a skill upgrade did not regress core research behavior.

Do **not** use it to bypass access controls, target minors, stalk/doxx/harass,
retain or test stolen secrets, deanonymize a person without authorization, or
run a live monitoring service without separate operational controls.

## Product scope

This is **a skill package**, not a hosted crawler, SaaS product, Python package, or API service.

An agent reads `SKILL.md` and follows the workflow. The repository ships instructions, adapter policies, reference playbooks, templates, examples, eval benches, and optional helper scripts. Those helper scripts are deliberately small, local, and auditable; they support the workflow but do not replace the agent.

Concretely, the repo contains:

- `SKILL.md` — the entry point that an agent reads to learn the workflow.
- `README.vi.md` — a short Vietnamese overview and setup guide.
- `AGENTS.md` — short root-level instructions for agentic frameworks that look for it.
- `references/` — 52 deep-dive guides, including investigative tiers, scoped person OSINT, cross-platform social classification, verified self-exposure, leak-derived lead handling, research intake, evidence ledgers, academic/systematic review, extraction, execution gates, frontier search, and reproducibility guidance, plus `references/i18n/` refusal templates (en, vi).
- `adapters/` — 9 tool-adapter docs (Playwright default, generic browser, fetch-only, web-search-only, Wikidata, database read-only, GraphQL, citation resolver, translation).
- `examples/` — 9 worked examples spanning academic review, dataset collection, large-scale crawl, technical research, a full PRISMA 2020 systematic review, and a long-horizon context-safe research plan.
- `templates/` — CSV/BibTeX/JSON drop-in starters: the v3.3 evidence ledger with 37 columns, investigation scope, screening/search logs, data dictionary, API request log, citation library, PRISMA flow, Frictionless Data Package, research-plan schema, frontier ledger, coverage map, and register vocab log.
- `scripts/` — 55 small, self-contained files (39 Python + 9 top-level Node + 7 under `scripts/lib/`). Research helpers ship offline `--self-test` (or are invoked by the adversarial/browser smoke suite). Pre-commit/check utilities (`check_node_syntax.py`, `check_no_plan_files.py`, `check_internal_refs.py`, `check_doc_examples.py`, `check_contract.py`, `build_release_artifacts.py`, `package_manifest_check.mjs`, `release_verify.py`, `adversarial_acceptance.py`, `browser_smoke.mjs`, `runtime_self_test.mjs`) run as CI/release gates rather than research CLIs. `run_python.mjs` is a Node→Python wrapper only. Playwright is pinned to an exact npm version; `npm run package:check` rejects untracked, sensitive, or omitted runtime files before packaging.
- `examples/evals/dogfood-bench.json`, `examples/evals/frontier-bench.json`, `examples/evals/quality-suite.json`, and `docs/eval.md` — offline eval: 12-task regression, 52-task frontier (bench 3.0), and a 42-case held-out quality suite (development / held-out / adversarial) with multi-dimension scoring, hostile fixtures, fuzz/mutation gates (`scripts/quality_eval.py`, `npm run eval:quality`).
- `research.config.example.json` — defaults for browser, crawl, API, citation, monitoring, processing, and large-scale config.
- `.agents/skills/testing-scripts/SKILL.md` — sub-skill that an agent uses to verify the scripts after edits.

There is **no Python package**, **no API server**, **no Docker image**, **no `requirements.txt`**, **no notebooks**, and **no service running on `/metrics`** or `/research/start`.

---

## Vietnamese summary

For Vietnamese users, see [README.vi.md](README.vi.md). The default README stays in English for broad compatibility with agent and IDE marketplaces.

---

## Workflow lifecycle (v3.x)

The skill is organised around eight research lifecycle pillars. Each pillar is a small, composable step, and every pillar produces an artifact that the next pillar consumes.

| # | Pillar | What happens | Key files |
|---|---|---|---|
| 0 | **intake** | Classify the research shape, safety posture, output artifact, freshness/language scope, and route before opening sources. | `references/research-intake.md` |
| 1 | **discover** | Restate the goal, decompose, build a source map, generate query fanout. | `references/topic-decomposition.md`, `references/source-discovery.md`, `references/query-patterns.md` |
| 2 | **fetch** | Browser-first probe + lawful fallbacks; opt-in shared HTTP cache; resolve canonical IDs (DOI/PMID/arXiv/ISBN) before broad search. | `adapters/playwright.md`, `references/browser-first-crawl.md`, `references/anti-bot-fallback.md`, `references/http-cache.md`, `scripts/citation_resolver.py` |
| 3 | **extract** | Pull text, tables, structured data (JSON-LD, microdata, RDFa), PDF / DOCX / EPUB / XLSX / mbox, OCR images. | `references/data-extraction-toolbox.md`, `references/multi-format-extraction.md`, `scripts/extract_tables.py`, `scripts/multi_extract.py`, `scripts/pdf_extract.py`, `scripts/ocr.py` |
| 4 | **analyze** | Clean, dedup, score sources, traverse citation graphs, run semantic retrieval, detect contradictions. | `scripts/data_clean.py`, `scripts/dedup_near.py`, `scripts/score_source.py`, `scripts/citation_graph.py`, `scripts/embed_corpus.py` |
| 5 | **synthesize** | Combine evidence into atomic claims; apply synthesis patterns; render citations in the required style. | `references/synthesis-patterns.md`, `references/citation-management.md`, `scripts/citation_render.py`, `scripts/citation_export.py` |
| 6 | **report** | Render a structured report (Markdown / PDF / DOCX / HTML); lint claim coverage. | `references/report-generation.md`, `scripts/report_render.py`, `templates/report-template.md` |
| 7 | **audit** | Sign the evidence ledger (HMAC-SHA256), export PROV-O JSON-LD, check reproducibility, capture run metadata. | `references/evidence-ledger.md`, `scripts/evidence_ledger.py sign / verify / prov-export`, `references/reproducibility-checklist.md`, `scripts/run_metadata.py` |

v3.4.1-rc.2 is the current patch candidate. It corrects the public access-model
contract so it accurately exposes the explicit archival and authorized API
mutation capabilities already present in v3.4.0, and adds a regression gate
against future absolute read-only claims. No command, option, route, schema,
default, or supported operation is removed. See
[`docs/release-v3.4.1-rc.2.md`](docs/release-v3.4.1-rc.2.md).

v3.4.0 is the current stable release. It is a monotonic capability expansion:
existing commands, routes, ledger widths, and recorded no-config defaults
remain valid, while API collection gains opt-in pagination config and explicit
mutation methods, archival and metadata handling gain truthful interfaces and
stronger redaction, downstream consumers gain a machine-readable interop
contract, and installers gain `full` and `runtime` artifacts deterministic for
identical source bytes. See
[`docs/release-v3.4.0.md`](docs/release-v3.4.0.md).

v3.3.0 is the previous stable investigation-policy release. It added executable
`R0`-`R4` scopes, scope-bound plan dispatch, the 37-column policy-aware ledger,
platform-neutral social classification, separate non-official lead output,
leak-aware reporting, and verified self-exposure handling. See
[`docs/release-v3.3.0.md`](docs/release-v3.3.0.md).

v3.2.1 is the previous stable release of three production-capable optional upgrades:
semantic retrieval, rich citation export, and language detection. Semantic
retrieval now prefers
local sentence-transformers and uses deterministic built-in lexical retrieval
when the optional model backend is unavailable; citation export
supports validated article, book, and conference metadata; language detection
can use deterministic local `langdetect`. The stable tree promotes the exact
v3.2.1-rc.2 candidate without executable, dependency, workflow, route, or
package-path drift. See
[`docs/release-v3.2.1.md`](docs/release-v3.2.1.md).

v3.2.0 is the production-ready schema-2.0 release. It includes immutable
approval fingerprints, portable output locking, canonical checklist IDs,
fail-closed report signatures, strict eval manifests, and browser-wide
read-only/resource budgets. Its release record transparently documents the
maintainer-authorized external-assurance waivers while retaining annotated
tags, 23/23 local checks, exact-SHA cross-platform CI, RC ancestry, archive
replay, SHA-256 validation, and provenance. See
[`docs/release-v3.2.0.md`](docs/release-v3.2.0.md).
Existing v3.1.1 workspaces should follow the tested
[`docs/upgrade-v3.1.1-to-v3.2.0.md`](docs/upgrade-v3.1.1-to-v3.2.0.md).

v3.1.1 hardens the skill metadata surface by expressing the `SKILL.md`
description as YAML block scalar syntax. The trigger text is unchanged, but
parsers that are strict about colon-bearing plain scalars can now read the
frontmatter more reliably.

v3.1.0 polishes the public release surface: release notes now use a consistent
product-title plus `vX.Y.Z Release Notes` subtitle pattern, eval documentation
matches the 52-task / 26-class frontier bench, and small duplicate-reference
noise has been removed.

v3.0.6 turns register/jargon recall into an executable, regression-protected
capability with `scripts/harvest_terms.py` and a two-task
`register-jargon-recall` frontier bench class.

v3.0.5 adds the register- and jargon-aware recall companion: a zero-maintenance
process for harvesting live vocabulary from fresh results, walking the register
ladder both ways, and treating discovered terms as leads rather than evidence.

v3.0.3 expands Step 0 into a stronger classification controller. Agents can now
route due diligence / investigation, policy / standards analysis, and creative /
cultural research as first-class research shapes, with completeness-first depth
for audit-grade, risk-heavy, or "speed is not important" work.

v3.0.2 adds a Step 0 research-intake layer before discovery. Agents classify
the request with multi-label routing before they search, so person, scientific,
dataset, URL, high-stakes, multilingual, and long-horizon tasks enter the right
branch from the start.

v3.0.1 adds a portable execution-gate layer between analysis and final
synthesis. The gates harden source mapping, recall, basin coverage,
date/identity discipline, claim verification, and final readiness while keeping
subagents optional and domain-specific discovery opt-in.

For the full release history see [CHANGELOG.md](CHANGELOG.md).

---

## Core capabilities

1. **Research intake and task classification** — Step 0 multi-label routing for fact / URL / person / academic / systematic review / dataset / API / technical / market / due diligence / policy-standards / creative-cultural / high-stakes / multilingual / long-horizon tasks before source access. Includes fast, standard, and completeness-first depth selection. See `references/research-intake.md`.
2. **Core deep research workflow** — restate goal → decompose topic → source map → query fanout → browser-first probe → extract → expand → evidence ledger → contradiction pass → blocker report → synthesize. See `SKILL.md`.
3. **Browser-first crawl** with Playwright defaults: probe access state, extract visible text/tables/links/files, classify pages, capture evidence/blocker screenshots. See `adapters/playwright.md` and `references/browser-first-crawl.md`.
4. **Public API workflow** for REST / GraphQL / SPARQL endpoints, with pagination patterns, rate-limit handling, and retry/backoff guidance. See `references/api-access-workflow.md` and `adapters/graphql.md`.
5. **Academic database access** via free APIs (OpenAlex, CrossRef, PubMed E-utilities, Semantic Scholar, arXiv, CORE). See `references/academic-databases.md`.
6. **Read-only database access** for SQL/NoSQL when the user provides credentials. See `adapters/database-readonly.md`.
7. **Evidence ledger** — 37-column v3.3 schema for claims, leads, source access, subject/purpose/tier, social lineage, sensitivity, reporting/redaction/retention, and authorization scope; exact 14/19/22/23-column ledgers remain supported. **Tamper-evident via HMAC-SHA256** (`scripts/evidence_ledger.py sign / verify`). See `references/evidence-ledger.md` and `templates/evidence-ledger.csv`.
8. **Citation management** — BibTeX/RIS export from an evidence-ledger CSV plus **multi-style rendering** (APA, MLA, IEEE, Chicago, Vancouver, Harvard, Nature, Science, ACM, AMA, …) via `scripts/citation_render.py` (pandoc + CSL). For DOI/PMID/arXiv/ISBN inputs, `scripts/citation_resolver.py` resolves canonical metadata via free public APIs (CrossRef, Datacite, NCBI, arXiv, Open Library, Unpaywall) before export. See `references/citation-management.md` and `adapters/citation-resolver.md`.
9. **Data processing pipeline** — audit, clean, dedup, validate, merge. See `references/data-processing-pipeline.md`.
10. **Data extraction toolbox** — recipe-style playbooks for HTML tables (with `scripts/extract_tables.py`), JSON-LD, embedded JSON, dataLayer, sitemaps, RSS, OAI-PMH, REST/GraphQL, PDFs, web archives. See `references/data-extraction-toolbox.md`.
11. **PRISMA 2020 systematic reviews** — full protocol, flow diagram template (`templates/prisma-flow.json`), synthesis-pattern decision tree, worked example (`examples/systematic-review-prisma.md`). See `references/systematic-review-protocol.md` and `references/synthesis-patterns.md`.
12. **Source quality rubric** — 5-axis deterministic scoring (type, authority, freshness, traceability, independence), separated from the three mandatory human review gates (relevance, method transparency, access quality). See `scripts/score_source.py` and `references/source-quality-rubric.md`.
13. **Reproducibility checklist** — every deliverable can be audited against `references/reproducibility-checklist.md` before declaring "done".
14. **Context-safe long-horizon protocol** — for tasks bigger than one model context window: create one workspace directory, write `research-plan.json`, annotate subagent slots/context budgets, render `PLAN.md` for review, require approval before dispatch, gate execution/synthesis, and write findings to disk immediately to avoid context loss. See `references/research-plan-protocol.md` and `examples/long-horizon-research-plan.md`.
15. **Frontier search for gap-driven follow-up** — when the first pass leaves evidence gaps, obscure facts, or contested claims, build a small best-first priority queue over candidate queries / URLs / files / APIs / citations / repos / aliases / archives, score each node against the unresolved sub-question, and stop on evidence saturation. Not a literal pathfinding algorithm; no A* / Dijkstra. Maintains a `frontier-ledger.csv` and `coverage-map.json` alongside the evidence ledger. Never bypasses access controls. See `references/frontier-search.md`, `templates/frontier-ledger.csv`, and `templates/coverage-map.json`.
16. **Fact-verification fast path** — for one-entity / one-attribute / deterministic-primary-source questions (commit SHA, package version, API limit, license clause). Skips decompose, source map, query fanout, and crawl. Hits the primary source once, quotes verbatim, files one ledger row with a one-shot independent re-check, and reports. Bails to the broad workflow on any anomaly. See `references/fact-verification.md`.
17. **Scoped person OSINT** — `R2` entity/alias resolution, public-professional timelines, relationships, contradiction search, and bounded frontier expansion. It has no fixed evidence-row cap; scope, risk, resource budgets, and saturation control stopping. Private-person work requires authorization or reviewed public interest, while minors, stalking/doxxing/harassment, secrets, sensitive retention, real-time whereabouts, and weaponized dossiers hard-stop. See `references/person-aggregation.md`.
18. **Offline eval harness** — a two-tier ground-truth suite (`examples/evals/dogfood-bench.json` for regression and `examples/evals/frontier-bench.json` for frontier probes) plus a stdlib-only harness (`scripts/run_dogfood.py`) that validates benches in CI, verifies per-task schema-2.1 `run-result.json` files with hashed raw prompt/output/ledger provenance, scores agent-produced ledgers, and compares isolated baseline vs. candidate score artifacts. Designed as a regression detector and upgrade signal, not a leaderboard. See `docs/eval.md`.
19. **Anti-bot fallback chain** — when a relevant public tier-1 source is blocked by Cloudflare, JavaScript challenge, captcha, 403, 429, or repeated browser/fetch failure, try exactly one lawful fallback chain: canonical API/static form, public web archive, cache/snippet if available, fetch-only/no-JS retrieval, then blocker report. Failed attempts are recorded as low-confidence process rows, not positive evidence. See `references/anti-bot-fallback.md`.
20. **Large-scale collection** — checkpointing, adaptive rate limiting, error budgets for >100-record runs. See `references/large-scale-collection.md`.
21. **Multilingual research, change monitoring, and specialized-domain sources** (financial / patent / legal / government / geospatial). See the matching files in `references/`.
22. **Blocker reports** — when a source is unreachable (login, paywall, captcha, rate limit, robots disallow), the skill produces a structured report telling the user exactly what to retrieve manually. See `references/blocker-report.md`.
23. **Social archival and cross-platform research** — capture public posts from 12 platforms plus a generic fallback, then classify every item by speaker identity, relationship, content origin, integrity, lineage, sensitivity, and reporting disposition. Transport tiers describe capture only; they never determine authority. `to-ledger` emits a 37-column lead by default, and only a verified original statement can be explicitly promoted as a statement-made claim. See `references/social-media-archival.md`, `references/social-source-research.md`, and `scripts/social_snapshot.py`.
24. **Portable execution gates** — before non-trivial synthesis, agents run source-map, coverage/recall, identity/date/inference, evidence-verification, and synthesis-readiness gates. Subagents can accelerate the checks, but the main agent can perform them manually in any runtime. See `references/execution-gates.md`.
25. **Vietnamese source discovery companion** — opt-in guidance for Vietnamese and Vietnam-local research: diacritic/no-diacritic aliases, local source basins, public-source privacy discipline, and compact coverage tables. See `references/vietnamese-source-discovery.md`.
26. **Register & jargon expansion companion** — opt-in recall layer for when the evidence basin speaks a different register than the query (clinical vs. lay, legal vs. street, standards vs. shop-floor, academic vs. community jargon, emergent slang). Walks a bidirectional register ladder — formal → vernacular to open recall, vernacular → formal to anchor every community term to a primary source. Harvests vocabulary from fresh results at runtime (never from model memory), keeps only terms recurring across ≥2 independent community sources, and treats the harvested vocabulary as a discovery layer, never as evidence — every claim still passes the source-quality rubric and contradiction pass. Audit-grade runs log vocabulary in `templates/register-vocab-log.csv`. See `references/register-and-jargon-expansion.md`.
27. **Tiered investigative policy** — `investigation_policy.py` validates `R0` public research, `R1` deep investigation, `R2` scoped person OSINT, `R3` verified self-exposure, and `R4` authorized security work under one non-negotiable `RX` floor. `research_plan.py bind-policy` binds exact scope bytes to every task and invalidates dispatch after drift. See `references/investigative-research.md`.
28. **Leak-derived research without secret handling** — public incident reporting is admissible normally; authorized providers and affected-user data are scope-bound; raw leak claims create redacted metadata leads only; stolen secrets are never acquired, retained, tested, or reported. See `references/leaked-data-handling.md` and `references/self-exposure-audit.md`.

---

## Feature matrix

| Area | What users get | Main files / commands |
|---|---|---|
| Research intake | Step 0 multi-label routing, authority-model selection, and fast/standard/completeness-first depth before source access | `references/research-intake.md` |
| Agent workflow | A complete browser-first research workflow for evidence-backed answers | `SKILL.md`, `AGENTS.md` |
| Execution gates | Portable pre-synthesis gates for recall, basin coverage, identity/date discipline, and evidence verification | `references/execution-gates.md` |
| Browser extraction | Playwright probing, extraction, bounded crawl, blocker screenshots | `adapters/playwright.md`, `scripts/playwright_*.mjs` |
| API and databases | REST/GraphQL/SPARQL/API pagination plus read-only database guidance | `references/api-access-workflow.md`, `adapters/graphql.md`, `adapters/database-readonly.md` |
| Academic research | OpenAlex/CrossRef/PubMed/Semantic Scholar/arXiv/CORE guidance | `references/academic-databases.md` |
| Evidence ledger | Claim-level evidence CSV with HMAC signing/verification | `templates/evidence-ledger.csv`, `scripts/evidence_ledger.py` |
| Citations | BibTeX/RIS export, optional rich article/book/conference metadata, and APA/MLA/IEEE/Chicago/Vancouver/etc. rendering | `scripts/citation_export.py`, `scripts/citation_render.py` |
| Data processing | Clean, deduplicate, validate, merge, summarize CSV data | `scripts/data_clean.py` |
| Data extraction | HTML tables, JSON-LD, embedded JSON, sitemaps, RSS, OAI-PMH, PDFs | `references/data-extraction-toolbox.md`, `scripts/extract_tables.py` |
| PRISMA reviews | PRISMA 2020 systematic-review protocol and flow template | `references/systematic-review-protocol.md`, `templates/prisma-flow.json` |
| Source scoring | Deterministic type/authority/freshness/traceability/independence scoring plus explicit human review gates | `scripts/score_source.py` |
| Long-horizon workspaces | One reproducible folder per research run with plan, ledger, notes, report | `scripts/research_plan.py init` |
| Approval gate | Human-readable `PLAN.md` must be approved before execution | `plan:render`, `plan:approve`, `plan:gate` |
| Subagent planning | Portable execution contract: slots, max parallel, context budgets, task assignment | `plan:configure-execution`, `plan:set-execution` |
| Context safety | Split work before context overflow; checkpoint findings to files immediately | `references/research-plan-protocol.md` |
| Anti-bot fallback | Lawful fallback chain for blocked public tier-1 sources before blocker reports | `references/anti-bot-fallback.md`, `references/blocker-report.md` |
| Vietnamese discovery | Opt-in Vietnamese/Vietnam-local source matrix and public-source discipline | `references/vietnamese-source-discovery.md` |
| Register & jargon recall | Opt-in bidirectional register ladder (formal ↔ vernacular) to match the evidence basin's vocabulary; discovery layer only, never evidence | `references/register-and-jargon-expansion.md` |
| Compatibility | Works as a markdown skill; runtime-specific models/API keys stay in the CLI/IDE | `research.config.example.json` |

---

## Safety boundary

The skill is read-only by default and respects access controls. Explicit,
user-authorized archival or API mutation operations remain available through
dedicated commands or `--intent archive|mutation`. Allowed and disallowed
actions are spelled out in full in `SKILL.md` ("Safety boundary" section) and
`references/safety-and-access-policy.md`.

Not allowed:
- bypass login or authentication
- bypass paywalls or subscription checks
- solve or evade captchas
- evade rate limits or anti-bot systems
- use stealth or anti-detection plugins
- acquire raw leak dumps or retain/test stolen cookies, passwords, tokens,
  sessions, MFA material, or private keys
- target minors, stalk/doxx/harass, or access personal/sensitive data outside a
  validated scope and authorization
- ignore robots or explicit site restrictions when acting as a crawler

When blocked, the agent stops and produces a blocker report — it does not force access.

---

## Repository layout

```
.
├── SKILL.md                              # entry point for the agent
├── AGENTS.md                             # short root-level instructions
├── README.md                             # this file
├── README.vi.md                          # Vietnamese overview
├── LICENSE                               # CC BY-NC 4.0
├── research.config.example.json          # default config values
├── package.json                          # npm scripts for the helper scripts
├── package-lock.json
├── .gitignore
│
├── adapters/
│   ├── playwright.md                     # default browser automation
│   ├── generic-browser.md                # any other browser tool
│   ├── fetch-only.md                     # URL fetch without a browser
│   ├── web-search-only.md                # search-only fallback
│   ├── wikidata.md                       # Wikidata entity lookup and SPARQL
│   ├── database-readonly.md              # SQL/NoSQL read-only access
│   ├── graphql.md                        # GraphQL endpoints
│   ├── citation-resolver.md              # new — DOI/PMID/arXiv/ISBN resolution adapter
│   └── translation.md                    # new — machine-translation adapter
│
├── references/                           # 52 deep-dive guides
│   ├── academic-databases.md
│   ├── academic-research-protocol.md
│   ├── anti-bot-fallback.md              # new — lawful fallback chain for blocked public sources
│   ├── api-access-workflow.md
│   ├── blocker-report.md
│   ├── browser-first-crawl.md
│   ├── citation-management.md
│   ├── citation-graph.md                 # new — citation graph traversal via OpenAlex
│   ├── data-extraction-toolbox.md        # new — extraction recipes
│   ├── data-processing-pipeline.md
│   ├── data-visualization.md
│   ├── evidence-ledger.md
│   ├── execution-gates.md                # new — portable pre-synthesis quality gates
│   ├── extraction-methods.md
│   ├── fact-verification.md              # new — atomic-fact fast path
│   ├── final-report-template.md
│   ├── frontier-search.md                # new — gap-driven follow-up controller
│   ├── investigative-research.md         # v3.3 — R0-R4/RX scope and investigation loop
│   ├── leaked-data-handling.md           # v3.3 — leak taxonomy and lead-only handling
│   ├── large-scale-collection.md
│   ├── monitoring-change-detection.md
│   ├── multilingual-research.md
│   ├── ocr.md                            # new — OCR / image-to-text extraction
│   ├── pdf-extraction.md                 # new — PDF extraction reference
│   ├── person-aggregation.md              # v3.3 — scoped person OSINT
│   ├── query-patterns.md
│   ├── register-and-jargon-expansion.md  # new — register/jargon recall companion
│   ├── report-generation.md              # new — final report generation
│   ├── reproducibility-checklist.md      # new — pre-release audit
│   ├── research-bibliography.md
│   ├── research-intake.md                # new — Step 0 task classification
│   ├── research-plan-protocol.md         # new — context-safe long-horizon protocol
│   ├── safety-and-access-policy.md
│   ├── semantic-retrieval.md             # new — embedding-based corpus retrieval
│   ├── self-exposure-audit.md             # v3.3 — verified owned-identifier exposure audit
│   ├── social-source-research.md          # v3.3 — platform-neutral social evidence
│   ├── source-discovery.md
│   ├── source-quality-rubric.md
│   ├── specialized-domains.md
│   ├── synthesis-patterns.md             # new — review-type decision tree
│   ├── systematic-review-protocol.md     # new — PRISMA 2020
│   ├── tool-adapter-policy.md
│   ├── topic-decomposition.md
│   ├── vietnamese-source-discovery.md    # new — opt-in Vietnamese/local source discovery
│   ├── wayback-archive.md                # new — Wayback Machine archive access
│   └── social-media-archival.md          # new — social-media post archival (two-tier)
│
├── examples/                             # worked examples
│   ├── academic-review.md
│   ├── api-dataset-collection.md
│   ├── blocked-source-report.md
│   ├── dataset-collection.md
│   ├── evals/
│   │   ├── dogfood-bench.json            # 12-task regression eval set
│   │   ├── frontier-bench.json           # 52-task frontier eval set (bench 3.0, 26 classes)
│   │   ├── quality-suite.json            # 42-case held-out quality suite (dev/held-out/adversarial)
│   │   ├── quality/                      # schema, fixtures, forward protocol
│   │   └── fixtures/                     # deterministic empty-score fixtures
│   ├── large-scale-crawl.md
│   ├── long-horizon-research-plan.md     # new — plan-protocol walkthrough
│   ├── scientific-literature-review.md
│   ├── systematic-review-prisma.md       # new — full PRISMA walkthrough
│   └── technical-research.md
│
├── templates/                            # CSV / BibTeX / JSON templates
│   ├── api-request-log.csv
│   ├── citation-library.bib
│   ├── coverage-map.json                 # new — evidence-gap map
│   ├── data-dictionary.csv
│   ├── data-package.json                 # new — Frictionless Data Package
│   ├── evidence-ledger.csv
│   ├── investigation-scope.json          # v3.3 — tier, scope, authorization, output controls
│   ├── frontier-ledger.csv               # new — frontier-search trace
│   ├── prisma-flow.json                  # new — PRISMA 2020 flow diagram
│   ├── register-vocab-log.csv            # new — register/jargon vocabulary audit log
│   ├── research-plan.json                # new — research-plan schema
│   ├── screening-log.csv
│   └── search-log.csv
│
├── scripts/                              # optional helper scripts
│   ├── playwright_probe.mjs              # classify a page, detect blockers
│   ├── playwright_extract.mjs            # extract text/tables/links/files
│   ├── playwright_crawl.mjs              # bounded same-domain crawl
│   ├── api_fetch.mjs                     # paginated API fetch w/ rate limit
│   ├── web_search.mjs                    # new — multi-engine web search w/ fallback chain
│   ├── evidence_ledger.py                # init/validate/sign/verify ledger
│   ├── investigation_policy.py           # v3.3 — scope and source-disposition gate
│   ├── data_clean.py                     # clean/dedup/validate/merge/stats
│   ├── citation_export.py                # rich BibTeX/RIS export + CrossRef enrich
│   ├── citation_render.py                # new — APA/MLA/IEEE/… via pandoc+CSL
│   ├── extract_tables.py                 # new — HTML tables → CSV
│   ├── score_source.py                   # new — rubric-based source scoring
│   ├── research_plan.py                  # new — workspace, approval, context budget, and plan manager
│   ├── run_dogfood.py                    # offline eval-bench harness
│   ├── quality_eval.py                   # held-out quality suite + integrity/hostile/fuzz
│   ├── pdf_extract.py                    # new — PDF text/meta/table extraction
│   ├── wayback.py                        # new — Wayback Machine nearest/diff
│   ├── wikidata.py                       # new — Wikidata search/entity/disambiguate/SPARQL
│   ├── social_snapshot.py                # new — social-media post capture/verify/to-ledger
│   ├── citation_resolver.py              # new — DOI/PMID/arXiv/ISBN resolver via free public APIs
│   ├── report_render.py                 # new — final report generator from research workspace
│   ├── bench_harness_check.py            # new — bench/fixture/harness consistency check (NOT an agent benchmark)
│   ├── check_internal_refs.py            # CI guard for path-style references
│   └── run_python.mjs                    # Python >=3.10 launcher; supports D_RESEARCH_PYTHON
│
├── agents/
│   └── openai.yaml                       # display metadata for hosts
│
├── docs/
│   ├── .archive/UPGRADE-PLAN.md          # archived internal upgrade plan (VN)
│   ├── eval.md                           # eval-harness usage guide
│   ├── eval-upgrade-prompt.md            # external-runner dogfood contract
│   ├── upgrade-v3.1.1-to-v3.2.0.md       # tested workspace migration guide
│   ├── release-v3.2.0-rc.1.md            # first RC scope and external gates
│   ├── release-v3.2.0-rc.2.md            # second RC hardening record
│   ├── release-v3.2.0-rc.3.md            # final RC scope and ship gates
│   ├── release-v3.2.0.md                 # stable release notes
│   ├── release-v3.2.1-rc.1.md            # initial production-capable optional helper RC
│   ├── release-v3.2.1-rc.2.md            # attestation-hardened release candidate
│   ├── release-v3.2.1.md                 # stable promotion note (candidate-frozen path)
│   ├── release-v3.3.0-rc.1.md            # frozen investigation-policy candidate
│   ├── release-v3.3.0.md                 # stable investigation-policy release
│   ├── release-v3.4.0-rc.1.md            # frozen monotonic-capability candidate
│   └── release-v3.4.0.md                 # stable monotonic-capability release
│
├── .github/
│   ├── dependabot.yml                    # npm + GitHub Actions updates
│   └── workflows/
│       ├── lint-and-self-test.yml        # version matrices + full integration
│       ├── link-check.yml                # internal and external link integrity
│       └── release-source-archive.yml    # annotated-tag archive/SHA/provenance
│
├── CONTRIBUTING.md                       # how to add references/adapters/examples/scripts
└── .agents/
    └── skills/
        └── testing-scripts/
            └── SKILL.md                  # sub-skill for testing scripts
```

---

## Installation

### For humans

#### Option A: Let an LLM do it

Paste this into any LLM agent or IDE assistant (Claude Code, OpenCode, Cursor, Windsurf, etc.):

```text
Install D Research v3.4.0 from the GitHub Release runtime artifact into
.agents/skills/d-research. Do not clone the repository. Download both the
runtime .tar.gz and its .sha256 file, verify SHA-256 before extraction, keep
the skill read-only by default, and run npm run self-test:runtime when
Node/Python are available.
```

#### Option B: Manual setup

1. Add the skill to your project. The final directory name must be
   `d-research`, matching the skill frontmatter.

   Choose the discovery root for your runtime; in every case the final path
   must end in `d-research/SKILL.md`:

| Runtime | Project-local destination | Personal destination |
|---|---|---|
| Agent Skills portable layout | `.agents/skills/d-research` | `~/.agents/skills/d-research` |
| Codex | `.agents/skills/d-research` | `$CODEX_HOME/skills/d-research` (default: `~/.codex/skills/d-research`) |
| Claude Code | `.claude/skills/d-research` | `~/.claude/skills/d-research` |
| Grok Build | `.agents/skills/d-research` | `~/.grok/skills/d-research` |
| OpenCode | `.opencode/skills/d-research` (also discovers `.agents/skills`) | `~/.config/opencode/skills/d-research` |

   The commands below use the portable project-local destination. Substitute
   another destination from the matrix when installing for one runtime only.

   The runtime artifact is an allowlisted end-user payload. It excludes CI,
   release evidence, hostile eval fixtures, and the developer-only testing
   sub-skill. Its projected package metadata advertises only commands that are
   closed inside the artifact. Bash:

```bash
version=3.4.0
base="https://github.com/d-init-d/d-research-skill/releases/download/v${version}"
mkdir -p .agents/skills
test ! -e .agents/skills/d-research || { echo 'destination already exists' >&2; exit 1; }
curl --fail --location --remote-name "${base}/d-research-${version}-runtime.tar.gz"
curl --fail --location --remote-name "${base}/d-research-${version}-runtime.tar.gz.sha256"
sha256sum --check "d-research-${version}-runtime.tar.gz.sha256"
tar -xzf "d-research-${version}-runtime.tar.gz" -C .agents/skills
test -f .agents/skills/d-research/SKILL.md
```

   PowerShell:

```powershell
$Version = '3.4.0'
$Base = "https://github.com/d-init-d/d-research-skill/releases/download/v$Version"
$Archive = "d-research-$Version-runtime.tar.gz"
New-Item -ItemType Directory -Force .agents/skills | Out-Null
if (Test-Path .agents/skills/d-research) { throw 'destination already exists' }
Invoke-WebRequest "$Base/$Archive" -OutFile $Archive
Invoke-WebRequest "$Base/$Archive.sha256" -OutFile "$Archive.sha256"
$Expected = ((Get-Content "$Archive.sha256" -Raw) -split '\s+')[0].ToLowerInvariant()
$Actual = (Get-FileHash $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Actual -ne $Expected) { throw "SHA-256 mismatch for $Archive" }
tar -xzf $Archive -C .agents/skills
if (-not (Test-Path .agents/skills/d-research/SKILL.md)) { throw 'Skill entry point missing' }
```

   Use `d-research-3.4.0-full.tar.gz` instead when you explicitly need the
   complete contributor/auditor surface, including CI, evaluations, hostile
   fixtures, and release evidence. `full` (alias `source`) remains the
   capability-complete profile; `runtime` is an additional clean install
   profile, not a replacement.

2. Point your agent/IDE at the skill entry point:

```text
.agents/skills/d-research/SKILL.md
```

3. Optional: create a project config you can edit:

```bash
cp .agents/skills/d-research/research.config.example.json research.config.json
```

```powershell
Copy-Item .agents/skills/d-research/research.config.example.json research.config.json
```

4. Optional: install helper-script dependencies:

```bash
cd .agents/skills/d-research
npm ci
npx --no-install playwright install chromium
npm run self-test:runtime
```

5. Use it by asking your agent for research work, for example:

```text
Use the D Research skill to research the current state of open-source browser automation for lawful public data collection. Create a reproducible workspace, show me the plan before execution, and cite sources.
```

### For agent / IDE maintainers

D Research does not store API keys, model routing, or provider credentials. Configure those in your host runtime (OpenCode, Claude Code, Cursor, VS Code extension, custom CLI, etc.). The skill only defines the portable workflow, scripts, plan schema, and subagent execution contract.

---

## Quick start

### As an agent skill

Most agentic frameworks ingest skills by reading `SKILL.md`. Install the
checksummed `runtime` release artifact with the commands above, either beside
your project or under its `.agents/skills/` discovery root. Repository cloning
is not an end-user installation path. Maintainers who need the complete source,
evaluation, and release-verification surface can install the separately
published `source` profile.

The agent then reads `SKILL.md` and follows the workflow. No installation, no environment variables, no API keys are required to use the skill itself — only specific scripts (below) need a runtime.

### Running the optional scripts

The helper scripts in `scripts/` are independent. Only install what you actually want to run.

```bash
# For the Playwright scripts (probe / extract / crawl)
npm ci                               # installs the exact locked Playwright version
npx --no-install playwright install chromium  # downloads the locked Chromium revision

# Core Python helpers (data_clean / citation_export / evidence_ledger / research_plan / etc.)
# use only the standard library — no pip install needed.
python3 --version                    # 3.10+ required

# Optional production-quality semantic and language-detection backends
python3 -m pip install -e ".[embeddings,language-detection]"
```

Run the bundled offline self-test for the profile you installed:

```bash
npm run self-test:runtime  # runtime artifact
npm run self-test:source   # complete source artifact
```

If Python is installed outside `PATH`, set `D_RESEARCH_PYTHON` to the full
Python 3.10+ executable path before invoking an npm command. The launcher probes
configured and platform-default interpreters and skips broken shims.

`npm run self-test` is the canonical offline helper chain. It runs every Node
and Python helper self-test, the bench-harness consistency check, the internal
reference and decision-tree checks, the repository contract checker, and the
resource-limit suite. Pass criteria: exit code `0`. CI then runs the adversarial
matrix with its embedded browser case disabled and launches the real local-only
Chromium smoke exactly once per operating system.

For a local release-style acceptance run, including its browser case:

```bash
npm run acceptance
```

If you want to isolate a failure, the most useful individual checks are:

```bash
# All research helpers ship a self-test subcommand:
node scripts/playwright_probe.mjs   --self-test
node scripts/playwright_extract.mjs --self-test
node scripts/playwright_crawl.mjs   --self-test
node scripts/api_fetch.mjs          --self-test
node scripts/web_search.mjs         --self-test
node scripts/lib/http_cache.mjs     --self-test
python3 scripts/evidence_ledger.py self-test
python3 scripts/data_clean.py      self-test
python3 scripts/citation_export.py self-test
python3 scripts/citation_render.py self-test
python3 scripts/extract_tables.py  self-test
python3 scripts/score_source.py    self-test
python3 scripts/research_plan.py   self-test
python3 scripts/run_dogfood.py     self-test
python3 scripts/pdf_extract.py     self-test
python3 scripts/wayback.py         self-test
python3 scripts/wikidata.py        self-test
python3 scripts/social_snapshot.py self-test
python3 scripts/citation_resolver.py self-test
python3 scripts/report_render.py   self-test
python3 scripts/ocr.py             self-test
python3 scripts/translate.py       self-test
python3 scripts/embed_corpus.py    self-test
python3 scripts/citation_graph.py  self-test
python3 scripts/multi_extract.py   self-test
python3 scripts/dedup_near.py      self-test
python3 scripts/http_cache.py      self-test
python3 scripts/bench_harness_check.py self-test
python3 scripts/run_metadata.py    self-test
python3 scripts/harvest_terms.py   self-test
python3 scripts/resource_limits.py self-test
python3 scripts/check_contract.py

# Documentation graph health (no `--self-test`; these are checks):
python3 scripts/check_internal_refs.py
python3 scripts/check_internal_refs.py --decision-tree

# Pre-commit utility scripts (also checks, not self-tests):
python3 scripts/check_node_syntax.py
python3 scripts/check_no_plan_files.py README.md   # passes (file is allowed)
```

Each research helper exits `0` and prints a pass marker such as `ok`, `ALL TESTS PASSED`, `All self-tests passed!`, or `✓ PASS`. The two pre-commit utility scripts (`check_node_syntax.py`, `check_no_plan_files.py`) and the two `check_internal_refs.py` invocations are checks, not self-tests, and exit `0` when there is nothing to flag.

### npm scripts

`package.json` exposes shortcuts for the most common operations:

```bash
npm run probe -- <url>                        # playwright_probe.mjs
npm run extract -- <url>                      # playwright_extract.mjs
npm run crawl -- <seed-url>                   # playwright_crawl.mjs
npm run api:fetch -- --url <api-url> --out out.json
npm run ledger:init -- --out evidence.csv
npm run ledger:validate -- --file evidence.csv
npm run data:clean -- --file input.csv --out cleaned.csv
npm run data:stats -- --file cleaned.csv
npm run data:dedup -- --file input.csv --out dedup.csv
npm run data:validate -- --file cleaned.csv
npm run data:merge -- --left a.csv --right b.csv --on id --out merged.csv
npm run citation:export -- --file evidence.csv --format bibtex --out refs.bib
npm run citation:enrich -- --doi 10.1234/example
npm run citation:render -- --bib refs.bib --style apa --format markdown --out refs.apa.md
npm run extract:tables -- --in page.html --out-dir out/
npm run score:source -- --file evidence.csv --out scored.csv
npm run ledger:sign -- --file evidence.csv --key-env D_RESEARCH_LEDGER_KEY
npm run ledger:verify -- --file evidence.csv --key-env D_RESEARCH_LEDGER_KEY
npm run eval:score-all -- --bench examples/evals/dogfood-bench.json --runs-dir runs/candidate/tier1 --out runs/candidate/tier1-scores.json
npm run eval:compare -- runs/baseline/tier1-scores.json runs/candidate/tier1-scores.json
npm run plan:init                             # write research-plan.json from template
npm run plan:check                            # validate schema + dep graph
npm run plan:status                           # one-line status per task
npm run plan:parallelizable                   # list task ids ready to dispatch
npm run plan:configure-execution              # refresh context/subagent annotations
npm run plan:set-execution -- --id T2 --agent subagent --slot deep-reader --parallel-threads 2
npm run plan:render                           # write PLAN.md for review
npm run plan:approve -- --by "Reviewer"       # approve before execution
npm run plan:revoke -- --reason "scope changed"
npm run plan:gate -- --gate synthesize_ready  # run a named gate
npm run wikidata:search -- --term "Douglas Adams"
npm run wikidata:entity -- --id Q42
npm run wikidata:sparql -- --query "SELECT ..."
npm run search:web -- --query "open data portal"
npm run social:snapshot -- reddit --url <url> --out snap.json
npm run social:verify -- --file snap.json
npm run cite:resolve:doi -- 10.1038/nature12373
npm run cite:resolve:pmid -- 35027834
npm run cite:resolve:arxiv -- 1706.03762
npm run cite:resolve:isbn -- 978-0134685991
npm run cite:resolve:oa -- 10.1038/nature12373
npm run refs:check                            # internal-refs CI guard, locally
```

For the multi-style citation rendering, install `pandoc ≥ 2.11` so `--citeproc` is available.

See each script's `--help` for the full argument list.

### Long-horizon workspace flow

For audit-grade or multi-context research, the output is one workspace
directory containing the plan, human-readable review, evidence ledger,
notes, sections, final report, and reproducibility checklist:

```bash
node scripts/run_python.mjs scripts/research_plan.py init --slug topic
cd research-topic-2026-05-16
node ../scripts/run_python.mjs ../scripts/research_plan.py configure-execution --file research-plan.json
node ../scripts/run_python.mjs ../scripts/research_plan.py render --file research-plan.json
node ../scripts/run_python.mjs ../scripts/research_plan.py gate --file research-plan.json --gate plan_ready
node ../scripts/run_python.mjs ../scripts/research_plan.py approve --file research-plan.json --by "Reviewer"
node ../scripts/run_python.mjs ../scripts/research_plan.py gate --file research-plan.json --gate execute_ready
```

`run_python.mjs` selects an available Python launcher on Windows, macOS, and
Linux. The matching `npm run plan:*` commands are equivalent.

The `init` command prints the actual `workspace:` path. Agents must
include that path in the final answer so users know where the plan,
ledger, notes, report, and checklist were written.

Execution is blocked until the plan is rendered and approved. If no
human reviewer is reachable, the agent must explicitly pass
`--allow-unattended`, which records `agent-self-approved` in the plan.

---

## Configuration

The skill respects a project-local `research.config.json` when present. Start from `research.config.example.json`:

```bash
cp .agents/skills/d-research/research.config.example.json research.config.json
```

Precedence for plan-related settings is: explicit CLI flags (for example `--workspace`, `--config`, `set-execution`) > `research.config.json` > built-in defaults. Runtime credentials, API keys, model selection, and real subagent invocation are intentionally configured outside this skill in your CLI/IDE.

### Configuration reference

| Key | Default | Purpose |
|---|---:|---|
| `browser.default` | `playwright` | Preferred browser adapter. |
| `browser.headless` | `true` | Run browser automation headlessly when the adapter supports it. |
| `browser.timeoutMs` | `30000` | Default browser operation timeout. |
| `browser.screenshotOnBlocker` | `true` | Capture screenshots for blocker reports. |
| `browser.screenshotOnEvidence` | `false` | Capture screenshots for evidence items when useful. |
| `crawl.maxDepth` | `2` | Maximum crawl depth. |
| `crawl.maxPagesPerDomain` | `30` | Per-domain crawl cap. |
| `crawl.maxTotalPages` | `100` | Total crawl cap. |
| `crawl.delayMs` | `1000` | Delay between crawl requests. |
| `crawl.respectRobots` | `true` | Respect robots/site restrictions. |
| `crawl.followExternalLinks` | `false` | Whether bounded crawls may leave the seed domain. |
| `research.intake.enabled` | `true` | Classify task shape, safety posture, route, and output artifact before source access. |
| `research.intake.emitClassificationCard` | `false` | Include the intake card in user-facing output when useful or audit-grade. |
| `research.intake.multiLabel` | `true` | Allow overlapping labels such as academic review + dataset extraction. |
| `research.intake.askOnSafetyOrOutputAmbiguity` | `true` | Ask only when ambiguity changes safety, legality, scope, or deliverable. |
| `research.intake.defaultToConservativeBranch` | `true` | Prefer the safer/stricter branch when classification is uncertain. |
| `research.intake.defaultDepth` | `standard` | Default research depth when no fast path or completeness-first trigger applies. |
| `research.intake.allowCompletenessFirst` | `true` | Allow deeper routing when accuracy, auditability, risk review, or recall matter more than speed. |
| `research.intake.completenessFirstOnRiskOrAudit` | `true` | Prefer completeness-first for due diligence, red flags, high-stakes, audit-grade, and risk-heavy tasks. |
| `research.intake.completenessFirstTriggers` | See config | Label/user-intent triggers that promote the task from standard depth to completeness-first. |
| `research.requireEvidenceLedger` | `true` | Require claim-level evidence ledger for important claims. |
| `research.requireContradictionPass` | `true` | Require a contradiction search/pass before synthesis. |
| `research.preferPrimarySources` | `true` | Prefer official/primary sources over summaries. |
| `research.minSourcesForStrongClaim` | `2` | Minimum supporting sources for high-confidence claims. |
| `research.searchLogRequired` | `true` | Keep a search/query log for reproducibility. |
| `research.executionGates.enabled` | `true` | Run portable quality gates before non-trivial synthesis. |
| `research.executionGates.lowRecallGuard` | `true` | Trigger an additional recall pass when evidence is thin. |
| `research.executionGates.noSingleBasinStop` | `true` | Avoid claiming broad coverage from one narrow source basin. |
| `research.executionGates.finalVerificationGate` | `true` | Require claim/evidence/readiness checks before final output. |
| `research.executionGates.subagentsOptional` | `true` | Treat subagents as accelerators, not required dependencies. |
| `research.executionGates.minIndependentBasinsForCompleteness` | `3` | Target basin diversity before calling broad work complete. |
| `researchPlan.context.mainContextLength` | `null` | Main agent context length. If set, task budgets derive from it. |
| `researchPlan.context.taskBudgetRatio` | `0.5` | Task budget = context length x ratio. |
| `researchPlan.context.writeFindingsImmediately` | `true` | Write findings to task output files as soon as they are found. |
| `researchPlan.subagents.slots[].id` | `default` | Stable slot id shown in `PLAN.md`. |
| `researchPlan.subagents.slots[].agent` | `null` | Host/runtime subagent label. `null` means the slot is disabled. |
| `researchPlan.subagents.slots[].contextLength` | `null` | Context length for that slot. Required when `agent` is set. |
| `researchPlan.subagents.slots[].maxParallel` | `null` | Maximum parallel threads for that slot. Required when `agent` is set. |
| `researchPlan.workspace.baseDir` | `.` | Parent folder for new research workspaces. |
| `researchPlan.workspace.nameTemplate` | `research-{slug}-{date}` | Workspace naming template. Supports `{slug}`, `{date}`, `{datetime}`. |
| `researchPlan.workspace.fallbackToCwdOnError` | `true` | If `baseDir` is inaccessible, fall back to the current directory and warn. |
| `researchPlan.approval.requireHuman` | `true` | Human review is expected before dispatch. |
| `researchPlan.approval.allowUnattended` | `false` | Whether host policy allows `--allow-unattended`. |
| `researchPlan.finalResponse.reportWorkspacePath` | `true` | Final responses must state the workspace path. |
| `access.allowLoginWithUserPermission` | `false` | Allow login only when the user explicitly authorizes it. |
| `access.allowPaywalledSources` | `false` | Allow paywalled sources only with explicit lawful access. |
| `access.allowCaptchaSolving` | `false` | Captcha solving is **never allowed** (hard policy; config cannot enable it). |
| `access.allowStealthEvasion` | `false` | Stealth/anti-bot evasion is **never allowed** (hard policy; config cannot enable it). |
| `access.defaultMode` | `read-only` | Default data-access posture. |
| `output.defaultReport` | `research-report` | Default report base name for non-plan workflows. |
| `output.includeBlockedSources` | `true` | Include blocked sources in final outputs. |
| `output.includeConfidence` | `true` | Include confidence labels. |
| `output.includeNextSearches` | `true` | Include suggested next searches. |
| `api.defaultDelayMs` | `500` | Delay between API requests. |
| `api.maxRetries` | `3` | API retry count. |
| `api.backoffMultiplier` | `2` | Retry backoff multiplier. |
| `api.respectRateLimitHeaders` | `true` | Respect API rate-limit headers. |
| `api.maxPagesPerEndpoint` | `50` | Pagination cap per API endpoint. |
| `api.timeoutMs` | `30000` | API request timeout. |
| `database.queryTimeoutMs` | `30000` | Read-only database query timeout. |
| `database.maxResultRows` | `10000` | Result-row cap for database reads. |
| `database.readOnly` | `true` | Database access must be read-only. |
| `citation.defaultFormat` | `bibtex` | Default citation export format. |
| `citation.enrichFromCrossRef` | `true` | Use CrossRef enrichment when available. |
| `citation.autoGenerateKeys` | `true` | Generate citation keys automatically. |
| `citation.deduplicateByDOI` | `true` | Deduplicate citations by DOI. |
| `monitoring.enabled` | `false` | Enable change-monitoring workflows. |
| `monitoring.defaultIntervalMinutes` | `60` | Default monitoring interval. |
| `monitoring.hashMethod` | `sha256` | Hash method for change detection. |
| `monitoring.archiveSnapshots` | `true` | Archive snapshots in monitoring workflows. |
| `processing.autoClean` | `false` | Automatically clean extracted tabular data. |
| `processing.detectOutliers` | `true` | Flag outliers in processing workflows. |
| `processing.deduplicateByDefault` | `true` | Deduplicate by default when processing data. |
| `processing.dateFormatISO8601` | `true` | Normalize dates to ISO 8601. |
| `largeScale.checkpointEveryN` | `50` | Record checkpoint after this many items. |
| `largeScale.checkpointEveryMinutes` | `5` | Time-based checkpoint interval. |
| `largeScale.maxErrorRatePercent` | `20` | Abort/review threshold for large-scale collection errors. |
| `largeScale.adaptiveRateLimit` | `true` | Slow down automatically on rate-limit signals. |

### Subagent slots are portable by design

`researchPlan.subagents.slots[]` is an execution planning contract, not a provider API. The skill records which task should use which slot, how much context it may consume, and how many parallel threads it may reserve. Your host runtime decides how to call the real worker:

- OpenCode can map a slot to its configured subagent / Task tool.
- Claude Code or another IDE can map a slot to its own agent mechanism.
- A custom CLI can read `research-plan.json` and dispatch tasks however it wants.
- If no slot is configured, the main agent must split tasks to fit its own context length.

Do not put provider secrets in `research.config.json`; keep API keys, auth, model routing, and account management in the CLI/IDE/runtime that actually executes the work.

---

## Compatibility

The skill is framework-agnostic. It has been written against the conventions of:

- Claude / Anthropic skills (root `SKILL.md` with YAML frontmatter `name` + `description`)
- Devin (root `AGENTS.md` and `.agents/skills/*/SKILL.md` sub-skills)
- Generic agent frameworks that follow either pattern

The optional scripts need Node.js 18+ (for `api_fetch.mjs` and the Playwright scripts) and Python 3.10+ (for the Python utilities; matches `requires-python` in `pyproject.toml`). Playwright is the only npm dependency (pinned to an exact version in `package.json`).

If you want to try this skill through ready-made agent presets, see the
[`d-research-agent-pack`](https://github.com/d-init-d/d-research-agent-pack),
which provides platform-specific agent adapters built on top of this skill.

---

## License

This project is source-available for non-commercial use under the
**Creative Commons Attribution-NonCommercial 4.0 International**
license (`CC-BY-NC-4.0`). See `LICENSE`.

You may use, copy, share, and adapt the material for non-commercial
purposes with attribution. Commercial use is not permitted without
written permission from the copyright holder.

Commercial use includes, but is not limited to, resale, paid
redistribution, SaaS packaging, marketplace distribution, paid agent
bundles, or embedding this skill in a paid product or service.

The copyright holder may offer separate commercial licenses on request.
