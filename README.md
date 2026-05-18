# D Research

**Browser-First Deep Research & Public Data Collection Skill for AI Agents**

[![License: CC BY-NC 4.0](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-nc/4.0/)

Vietnamese docs: [README.vi.md](README.vi.md)

> A markdown-based skill that teaches AI agents (Claude, Devin, GPT-class agents) how to run rigorous, source-backed deep research and lawful public web/data collection. Read-only by default. Never bypasses login, paywalls, captchas, rate limits, or robots restrictions.

---

## What this repository actually is

This is **a skill package**, not a runnable Python application or service.

Concretely, the repo contains:

- `SKILL.md` — the entry point that an agent reads to learn the workflow.
- `README.vi.md` — a short Vietnamese overview and setup guide.
- `AGENTS.md` — short root-level instructions for agentic frameworks that look for it.
- `references/` — 34 deep-dive guides (evidence ledger, query patterns, browser-first crawl, academic databases, API workflow, data pipeline, citation management, PRISMA 2020 systematic-review protocol, synthesis-pattern decision tree, data-extraction toolbox, reproducibility checklist, source-quality rubric, multilingual research, **research-plan protocol for long-horizon tasks**, **frontier search for gap-driven follow-up**, **fact-verification fast path for atomic-fact lookups**, **person-aggregation with an explicit privacy boundary**, **anti-bot fallback chain for blocked public sources**, **PDF extraction**, **Wayback Machine archive access**, **social-media archival with two-tier platform architecture**, …).
- `adapters/` — 7 tool-adapter docs (Playwright default, generic browser, fetch-only, web-search-only, Wikidata, database read-only, GraphQL).
- `examples/` — 9 worked examples spanning academic review, dataset collection, large-scale crawl, technical research, a full PRISMA 2020 systematic review, and a long-horizon context-safe research plan.
- `templates/` — CSV/BibTeX/JSON drop-in starters: evidence ledger, screening log, search log, data dictionary, API request log, citation library, **PRISMA flow diagram**, **Frictionless Data Package**, **research-plan schema**, **frontier ledger**, **coverage map**.
- `scripts/` — 18 small, self-contained helper scripts (5 Node scripts + 13 Python utilities; `run_python.mjs` is only a wrapper). Each ships with an offline `--self-test`. CI runs all of them on every PR.
- `examples/evals/dogfood-bench.json`, `examples/evals/frontier-bench.json`, and `docs/eval.md` — the offline two-tier eval suite: a 12-task regression guard plus a 32-task frontier probe (bench 2.1, 16 classes). See `scripts/run_dogfood.py` and `npm run eval:self-test`.
- `research.config.example.json` — defaults for browser, crawl, API, citation, monitoring, processing, and large-scale config.
- `.agents/skills/testing-scripts/SKILL.md` — sub-skill that an agent uses to verify the scripts after edits.

There is **no Python package**, **no API server**, **no Docker image**, **no `requirements.txt`**, **no notebooks**, and **no service running on `/metrics`** or `/research/start`. If you read older documentation that implied any of those, treat it as out-of-date.

---

## Vietnamese summary

For Vietnamese users, see [README.vi.md](README.vi.md). The default README stays in English for broad compatibility with agent and IDE marketplaces.

---

## Core capabilities (what the skill actually teaches)

1. **Core deep research workflow** — restate goal → decompose topic → source map → query fanout → browser-first probe → extract → expand → evidence ledger → contradiction pass → blocker report → synthesize. See `SKILL.md`.
2. **Browser-first crawl** with Playwright defaults: probe access state, extract visible text/tables/links/files, classify pages, capture evidence/blocker screenshots. See `adapters/playwright.md` and `references/browser-first-crawl.md`.
3. **Public API workflow** for REST / GraphQL / SPARQL endpoints, with pagination patterns, rate-limit handling, and retry/backoff guidance. See `references/api-access-workflow.md` and `adapters/graphql.md`.
4. **Academic database access** via free APIs (OpenAlex, CrossRef, PubMed E-utilities, Semantic Scholar, arXiv, CORE). See `references/academic-databases.md`.
5. **Read-only database access** for SQL/NoSQL when the user provides credentials. See `adapters/database-readonly.md`.
6. **Evidence ledger** — atomic claims with source, type, date, access method, evidence, contradiction status, confidence. **Tamper-evident via HMAC-SHA256** (`scripts/evidence_ledger.py sign / verify`). See `references/evidence-ledger.md` and `templates/evidence-ledger.csv`.
7. **Citation management** — BibTeX/RIS export from an evidence-ledger CSV plus **multi-style rendering** (APA, MLA, IEEE, Chicago, Vancouver, Harvard, Nature, Science, ACM, AMA, …) via `scripts/citation_render.py` (pandoc + CSL). See `references/citation-management.md`.
8. **Data processing pipeline** — audit, clean, dedup, validate, merge. See `references/data-processing-pipeline.md`.
9. **Data extraction toolbox** — recipe-style playbooks for HTML tables (with `scripts/extract_tables.py`), JSON-LD, embedded JSON, dataLayer, sitemaps, RSS, OAI-PMH, REST/GraphQL, PDFs, web archives. See `references/data-extraction-toolbox.md`.
10. **PRISMA 2020 systematic reviews** — full protocol, flow diagram template (`templates/prisma-flow.json`), synthesis-pattern decision tree, worked example (`examples/systematic-review-prisma.md`). See `references/systematic-review-protocol.md` and `references/synthesis-patterns.md`.
11. **Source quality rubric** — 5-axis deterministic scoring (type, authority, recency, methodology, independence) applied automatically by `scripts/score_source.py`. See `references/source-quality-rubric.md`.
12. **Reproducibility checklist** — every deliverable can be audited against `references/reproducibility-checklist.md` before declaring "done".
13. **Context-safe long-horizon protocol** — for tasks bigger than one model context window: create one workspace directory, write `research-plan.json`, annotate subagent slots/context budgets, render `PLAN.md` for review, require approval before dispatch, gate execution/synthesis, and write findings to disk immediately to avoid context loss. See `references/research-plan-protocol.md` and `examples/long-horizon-research-plan.md`.
14. **Frontier search for gap-driven follow-up** — when the first pass leaves evidence gaps, obscure facts, or contested claims, build a small best-first priority queue over candidate queries / URLs / files / APIs / citations / repos / aliases / archives, score each node against the unresolved sub-question, and stop on evidence saturation. Not a literal pathfinding algorithm; no A* / Dijkstra. Maintains a `frontier-ledger.csv` and `coverage-map.json` alongside the evidence ledger. Never bypasses access controls. See `references/frontier-search.md`, `templates/frontier-ledger.csv`, and `templates/coverage-map.json`.
15. **Fact-verification fast path** — for one-entity / one-attribute / deterministic-primary-source questions (commit SHA, package version, API limit, license clause). Skips decompose, source map, query fanout, and crawl. Hits the primary source once, quotes verbatim, files one ledger row with a one-shot independent re-check, and reports. Bails to the broad workflow on any anomaly. See `references/fact-verification.md`.
16. **Person aggregation with a privacy boundary** — a dedicated branch for cross-source public-role lookups about a named person (maintainer, author, speaker, journalist, public figure). Anchors on one canonical source (GitHub profile, ORCID, package author, faculty page, verified byline), aggregates verified public-role claims, and **enforces an explicit privacy boundary**: home address, family, private accounts, personal contact, photos, medical / financial / legal / orientation / whereabouts, pseudonym-to-real-name re-identification, and explicitly-private items are out of scope regardless of whether they appear on the open web. Refuses on minors, private individuals, and harassment / stalking / doxxing framings. Saturates at 25 ledger rows or three sources adding no new verified claims. See `references/person-aggregation.md`.
17. **Offline eval harness** — a two-tier ground-truth suite (`examples/evals/dogfood-bench.json` for regression and `examples/evals/frontier-bench.json` for frontier probes) plus a stdlib-only harness (`scripts/run_dogfood.py`) that validates benches in CI, scores agent-produced ledgers, and compares baseline vs. candidate score artifacts. Designed as a regression detector and upgrade signal, not a leaderboard. See `docs/eval.md`.
18. **Anti-bot fallback chain** — when a relevant public tier-1 source is blocked by Cloudflare, JavaScript challenge, captcha, 403, 429, or repeated browser/fetch failure, try exactly one lawful fallback chain: canonical API/static form, public web archive, cache/snippet if available, fetch-only/no-JS retrieval, then blocker report. Failed attempts are recorded as low-confidence process rows, not positive evidence. See `references/anti-bot-fallback.md`.
19. **Large-scale collection** — checkpointing, adaptive rate limiting, error budgets for >100-record runs. See `references/large-scale-collection.md`.
20. **Multilingual research, change monitoring, and specialized-domain sources** (financial / patent / legal / government / geospatial). See the matching files in `references/`.
21. **Blocker reports** — when a source is unreachable (login, paywall, captcha, rate limit, robots disallow), the skill produces a structured report telling the user exactly what to retrieve manually. See `references/blocker-report.md`.
22. **Social-media archival** — capture public social-media posts from 12 platforms (Reddit, HN, Mastodon, Bluesky, Lemmy, X, Facebook, Instagram, TikTok, YouTube, Threads, LinkedIn) plus a generic fallback. Tier A platforms use direct public API fetch with SHA-256 content hashing for high verifiability; Tier B platforms use archive-only via Wayback Machine. Every capture carries a mandatory verifiability label and plain-language note. See `references/social-media-archival.md` and `scripts/social_snapshot.py`.

---

## Feature matrix

| Area | What users get | Main files / commands |
|---|---|---|
| Agent workflow | A complete browser-first research workflow for evidence-backed answers | `SKILL.md`, `AGENTS.md` |
| Browser extraction | Playwright probing, extraction, bounded crawl, blocker screenshots | `adapters/playwright.md`, `scripts/playwright_*.mjs` |
| API and databases | REST/GraphQL/SPARQL/API pagination plus read-only database guidance | `references/api-access-workflow.md`, `adapters/graphql.md`, `adapters/database-readonly.md` |
| Academic research | OpenAlex/CrossRef/PubMed/Semantic Scholar/arXiv/CORE guidance | `references/academic-databases.md` |
| Evidence ledger | Claim-level evidence CSV with HMAC signing/verification | `templates/evidence-ledger.csv`, `scripts/evidence_ledger.py` |
| Citations | BibTeX/RIS export and APA/MLA/IEEE/Chicago/Vancouver/etc. rendering | `scripts/citation_export.py`, `scripts/citation_render.py` |
| Data processing | Clean, deduplicate, validate, merge, summarize CSV data | `scripts/data_clean.py` |
| Data extraction | HTML tables, JSON-LD, embedded JSON, sitemaps, RSS, OAI-PMH, PDFs | `references/data-extraction-toolbox.md`, `scripts/extract_tables.py` |
| PRISMA reviews | PRISMA 2020 systematic-review protocol and flow template | `references/systematic-review-protocol.md`, `templates/prisma-flow.json` |
| Source scoring | Deterministic authority/recency/methodology/independence scoring | `scripts/score_source.py` |
| Long-horizon workspaces | One reproducible folder per research run with plan, ledger, notes, report | `scripts/research_plan.py init` |
| Approval gate | Human-readable `PLAN.md` must be approved before execution | `plan:render`, `plan:approve`, `plan:gate` |
| Subagent planning | Portable execution contract: slots, max parallel, context budgets, task assignment | `plan:configure-execution`, `plan:set-execution` |
| Context safety | Split work before context overflow; checkpoint findings to files immediately | `references/research-plan-protocol.md` |
| Anti-bot fallback | Lawful fallback chain for blocked public tier-1 sources before blocker reports | `references/anti-bot-fallback.md`, `references/blocker-report.md` |
| Compatibility | Works as a markdown skill; runtime-specific models/API keys stay in the CLI/IDE | `research.config.example.json` |

---

## Safety boundary

The skill is intentionally **read-only and respects access controls**. Allowed and disallowed actions are spelled out in full in `SKILL.md` ("Safety boundary" section) and `references/safety-and-access-policy.md`.

Not allowed:
- bypass login or authentication
- bypass paywalls or subscription checks
- solve or evade captchas
- evade rate limits or anti-bot systems
- use stealth plugins by default
- use stolen cookies, leaked tokens, or credentials not explicitly provided by the user
- access private, personal, or sensitive data without authorization
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
│   └── graphql.md                        # GraphQL endpoints
│
├── references/                           # 34 deep-dive guides
│   ├── academic-databases.md
│   ├── academic-research-protocol.md
│   ├── anti-bot-fallback.md              # new — lawful fallback chain for blocked public sources
│   ├── api-access-workflow.md
│   ├── blocker-report.md
│   ├── browser-first-crawl.md
│   ├── citation-management.md
│   ├── data-extraction-toolbox.md        # new — extraction recipes
│   ├── data-processing-pipeline.md
│   ├── data-visualization.md
│   ├── evidence-ledger.md
│   ├── extraction-methods.md
│   ├── fact-verification.md              # new — atomic-fact fast path
│   ├── final-report-template.md
│   ├── frontier-search.md                # new — gap-driven follow-up controller
│   ├── large-scale-collection.md
│   ├── monitoring-change-detection.md
│   ├── multilingual-research.md
│   ├── pdf-extraction.md                 # new — PDF extraction reference
│   ├── person-aggregation.md              # new — public-role aggregation w/ privacy boundary
│   ├── query-patterns.md
│   ├── reproducibility-checklist.md      # new — pre-release audit
│   ├── research-bibliography.md
│   ├── research-plan-protocol.md         # new — context-safe long-horizon protocol
│   ├── safety-and-access-policy.md
│   ├── source-discovery.md
│   ├── source-quality-rubric.md
│   ├── specialized-domains.md
│   ├── synthesis-patterns.md             # new — review-type decision tree
│   ├── systematic-review-protocol.md     # new — PRISMA 2020
│   ├── tool-adapter-policy.md
│   ├── topic-decomposition.md
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
│   │   ├── frontier-bench.json           # 20-task frontier eval set
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
│   ├── frontier-ledger.csv               # new — frontier-search trace
│   ├── prisma-flow.json                  # new — PRISMA 2020 flow diagram
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
│   ├── data_clean.py                     # clean/dedup/validate/merge/stats
│   ├── citation_export.py                # BibTeX/RIS export + CrossRef enrich
│   ├── citation_render.py                # new — APA/MLA/IEEE/… via pandoc+CSL
│   ├── extract_tables.py                 # new — HTML tables → CSV
│   ├── score_source.py                   # new — rubric-based source scoring
│   ├── research_plan.py                  # new — workspace, approval, context budget, and plan manager
│   ├── run_dogfood.py                    # new — offline eval-bench harness
│   ├── pdf_extract.py                    # new — PDF text/meta/table extraction
│   ├── wayback.py                        # new — Wayback Machine nearest/diff
│   ├── wikidata.py                       # new — Wikidata search/entity/disambiguate/SPARQL
│   ├── social_snapshot.py                # new — social-media post capture/verify/to-ledger
│   ├── check_internal_refs.py            # CI guard for path-style references
│   └── run_python.mjs                    # tiny wrapper to invoke Python
│
├── agents/
│   └── openai.yaml                       # display metadata for hosts
│
├── docs/
│   ├── UPGRADE-PLAN.md                   # internal upgrade plan (VN)
│   └── eval.md                           # new — eval-harness usage guide
│
├── .github/
│   └── workflows/
│       ├── link-check.yml                # internal-refs + lychee on every PR
│       └── lint-and-self-test.yml        # ruff + node --check + all self-tests
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
Install the D Research skill from https://github.com/d-init-d/d-research-skill.git into this project so you can use it for deep research. Prefer vendoring it at .agents/skills/d-research, keep it read-only by default, copy research.config.example.json to research.config.json only if I want project-specific settings, and run the optional self-tests if Node/Python are available.
```

#### Option B: Manual setup

1. Add the skill to your project:

```bash
mkdir -p .agents/skills
git clone https://github.com/d-init-d/d-research-skill.git .agents/skills/d-research
```

2. Point your agent/IDE at the skill entry point:

```text
.agents/skills/d-research/SKILL.md
```

3. Optional: create a project config you can edit:

```bash
cp .agents/skills/d-research/research.config.example.json research.config.json
```

4. Optional: install helper-script dependencies:

```bash
cd .agents/skills/d-research
npm install
npx playwright install
npm run self-test
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

Most agentic frameworks ingest skills by reading `SKILL.md` (and any sub-skill `.agents/skills/*/SKILL.md`). Two common setups:

**Drop-in for an existing project**

```bash
# Clone the skill alongside your project
git clone https://github.com/d-init-d/d-research-skill.git
# Point your agent at d-research-skill/SKILL.md
```

**Vendor it into your project's `.agents/skills/`**

```bash
# From your project root
mkdir -p .agents/skills
git clone https://github.com/d-init-d/d-research-skill.git .agents/skills/d-research
# Most agents will auto-discover the new SKILL.md
```

The agent then reads `SKILL.md` and follows the workflow. No installation, no environment variables, no API keys are required to use the skill itself — only specific scripts (below) need a runtime.

### Running the optional scripts

The helper scripts in `scripts/` are independent. Only install what you actually want to run.

```bash
# For the Playwright scripts (probe / extract / crawl)
npm install                  # installs playwright (declared in package.json)
npx playwright install        # downloads browser binaries

# For the Python scripts (data_clean / citation_export / evidence_ledger / research_plan / etc.)
# Stdlib only — no pip install needed.
python3 --version             # 3.9+ recommended
```

Run the bundled offline self-tests to confirm everything is wired correctly:

```bash
npm run self-test
# or individually:
node scripts/playwright_probe.mjs --self-test
node scripts/playwright_extract.mjs --self-test
node scripts/playwright_crawl.mjs --self-test
node scripts/api_fetch.mjs --self-test
node scripts/web_search.mjs --self-test
python3 scripts/evidence_ledger.py self-test
python3 scripts/data_clean.py self-test
python3 scripts/citation_export.py self-test
python3 scripts/citation_render.py self-test
python3 scripts/extract_tables.py self-test
python3 scripts/score_source.py self-test
python3 scripts/research_plan.py self-test
python3 scripts/run_dogfood.py self-test
python3 scripts/pdf_extract.py self-test
python3 scripts/wayback.py self-test
python3 scripts/wikidata.py self-test
python3 scripts/social_snapshot.py self-test
python3 scripts/check_internal_refs.py
```

All eighteen commands exit `0` and print pass markers (e.g. `ALL TESTS PASSED`, `All self-tests passed!`, `✓ PASS`).

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
npm run eval:score-all -- --bench examples/evals/dogfood-bench.json --ledgers-dir runs/candidate/tier1-ledgers --out runs/candidate/tier1-scores.json
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
npm run refs:check                            # internal-refs CI guard, locally
```

For the multi-style citation rendering, install `pandoc ≥ 2.11` so `--citeproc` is available.

See each script's `--help` for the full argument list.

### Long-horizon workspace flow

For audit-grade or multi-context research, the output is one workspace
directory containing the plan, human-readable review, evidence ledger,
notes, sections, final report, and reproducibility checklist:

```bash
python3 scripts/research_plan.py init --slug topic
cd research-topic-2026-05-16
python3 ../scripts/research_plan.py configure-execution --file research-plan.json
python3 ../scripts/research_plan.py render --file research-plan.json
python3 ../scripts/research_plan.py gate --file research-plan.json --gate plan_ready
python3 ../scripts/research_plan.py approve --file research-plan.json --by "Reviewer"
python3 ../scripts/research_plan.py gate --file research-plan.json --gate execute_ready
```

On Windows, use `python` instead of `python3` if `python3` is not on
PATH, or use the matching `npm run plan:*` commands.

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
| `research.requireEvidenceLedger` | `true` | Require claim-level evidence ledger for important claims. |
| `research.requireContradictionPass` | `true` | Require a contradiction search/pass before synthesis. |
| `research.preferPrimarySources` | `true` | Prefer official/primary sources over summaries. |
| `research.minSourcesForStrongClaim` | `2` | Minimum supporting sources for high-confidence claims. |
| `research.searchLogRequired` | `true` | Keep a search/query log for reproducibility. |
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
| `access.allowCaptchaSolving` | `false` | Captcha solving is disabled by default. |
| `access.allowStealthEvasion` | `false` | Stealth/anti-bot evasion is disabled by default. |
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

The optional scripts need Node.js 18+ (for `api_fetch.mjs` and the Playwright scripts) and Python 3.9+ (for the Python utilities). Playwright is the only npm dependency.

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
