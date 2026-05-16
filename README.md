# D Research

**Browser-First Deep Research & Public Data Collection Skill for AI Agents**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

> A markdown-based skill that teaches AI agents (Claude, Devin, GPT-class agents) how to run rigorous, source-backed deep research and lawful public web/data collection. Read-only by default. Never bypasses login, paywalls, captchas, rate limits, or robots restrictions.

---

## What this repository actually is

This is **a skill package**, not a runnable Python application or service.

Concretely, the repo contains:

- `SKILL.md` — the entry point that an agent reads to learn the workflow.
- `AGENTS.md` — short root-level instructions for agentic frameworks that look for it.
- `references/` — 27 deep-dive guides (evidence ledger, query patterns, browser-first crawl, academic databases, API workflow, data pipeline, citation management, PRISMA 2020 systematic-review protocol, synthesis-pattern decision tree, data-extraction toolbox, reproducibility checklist, source-quality rubric, multilingual research, **research-plan protocol for long-horizon tasks**, …).
- `adapters/` — 6 tool-adapter docs (Playwright default, generic browser, fetch-only, web-search-only, database read-only, GraphQL).
- `examples/` — 9 worked examples spanning academic review, dataset collection, large-scale crawl, technical research, a full PRISMA 2020 systematic review, and a long-horizon context-safe research plan.
- `templates/` — CSV/BibTeX/JSON drop-in starters: evidence ledger, screening log, search log, data dictionary, API request log, citation library, **PRISMA flow diagram**, **Frictionless Data Package**, **research-plan schema**.
- `scripts/` — 12 small, self-contained helper scripts (3 Playwright Node scripts + 9 Python utilities). Each ships with an offline `--self-test`. CI runs all of them on every PR.
- `research.config.example.json` — defaults for browser, crawl, API, citation, monitoring, processing, and large-scale config.
- `.agents/skills/testing-scripts/SKILL.md` — sub-skill that an agent uses to verify the scripts after edits.

There is **no Python package**, **no API server**, **no Docker image**, **no `requirements.txt`**, **no notebooks**, and **no service running on `/metrics`** or `/research/start`. If you read older documentation that implied any of those, treat it as out-of-date.

---

## Mô tả ngắn (tiếng Việt)

D Research là một **bộ skill dạng markdown** dạy AI agent cách thực hiện nghiên cứu chuyên sâu có chứng cứ, thu thập dữ liệu công khai một cách hợp pháp. Mặc định đọc-only. Không bao giờ né login, paywall, captcha, rate-limit, hay robots restrictions.

Repo là tài liệu + một số script phụ trợ, **không phải Python application**. Để dùng, agent đọc `SKILL.md` và làm theo workflow trong đó; các script trong `scripts/` là optional helper khi agent có Node/Python sẵn.

---

## Core capabilities (what the skill actually teaches)

1. **12-step deep research workflow** — restate goal → decompose topic → source map → query fanout → browser-first probe → extract → expand → evidence ledger → contradiction pass → blocker report → synthesize. See `SKILL.md`.
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
12a. **Context-safe long-horizon protocol** — for tasks bigger than one model context window: create one workspace directory, write `research-plan.json` (from `templates/research-plan.json`), render `PLAN.md`, require approval before dispatch, drive execution with `scripts/research_plan.py`, dispatch parallel-safe tasks to sub-agents, and gate the synthesize step with `gate.synthesize_ready`. See `references/research-plan-protocol.md` and `examples/long-horizon-research-plan.md`.
13. **Large-scale collection** — checkpointing, adaptive rate limiting, error budgets for >100-record runs. See `references/large-scale-collection.md`.
14. **Multilingual research, change monitoring, and specialized-domain sources** (financial / patent / legal / government / geospatial). See the matching files in `references/`.
15. **Blocker reports** — when a source is unreachable (login, paywall, captcha, rate limit, robots disallow), the skill produces a structured report telling the user exactly what to retrieve manually. See `references/blocker-report.md`.

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
├── LICENSE                               # MIT
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
│   ├── database-readonly.md              # SQL/NoSQL read-only access
│   └── graphql.md                        # GraphQL endpoints
│
├── references/                           # 26 deep-dive guides
│   ├── academic-databases.md
│   ├── academic-research-protocol.md
│   ├── api-access-workflow.md
│   ├── blocker-report.md
│   ├── browser-first-crawl.md
│   ├── citation-management.md
│   ├── data-extraction-toolbox.md        # new — extraction recipes
│   ├── data-processing-pipeline.md
│   ├── data-visualization.md
│   ├── evidence-ledger.md
│   ├── extraction-methods.md
│   ├── final-report-template.md
│   ├── large-scale-collection.md
│   ├── monitoring-change-detection.md
│   ├── multilingual-research.md
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
│   └── topic-decomposition.md
│
├── examples/                             # worked examples
│   ├── academic-review.md
│   ├── api-dataset-collection.md
│   ├── blocked-source-report.md
│   ├── dataset-collection.md
│   ├── large-scale-crawl.md
│   ├── long-horizon-research-plan.md     # new — plan-protocol walkthrough
│   ├── scientific-literature-review.md
│   ├── systematic-review-prisma.md       # new — full PRISMA walkthrough
│   └── technical-research.md
│
├── templates/                            # CSV / BibTeX / JSON templates
│   ├── api-request-log.csv
│   ├── citation-library.bib
│   ├── data-dictionary.csv
│   ├── data-package.json                 # new — Frictionless Data Package
│   ├── evidence-ledger.csv
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
│   ├── evidence_ledger.py                # init/validate/sign/verify ledger
│   ├── data_clean.py                     # clean/dedup/validate/merge/stats
│   ├── citation_export.py                # BibTeX/RIS export + CrossRef enrich
│   ├── citation_render.py                # new — APA/MLA/IEEE/… via pandoc+CSL
│   ├── extract_tables.py                 # new — HTML tables → CSV
│   ├── score_source.py                   # new — rubric-based source scoring
│   ├── research_plan.py                  # new — workspace, approval, and plan manager
│   ├── check_internal_refs.py            # CI guard for path-style references
│   └── run_python.mjs                    # tiny wrapper to invoke Python
│
├── agents/
│   └── openai.yaml                       # display metadata for hosts
│
├── docs/
│   └── UPGRADE-PLAN.md                   # internal upgrade plan (VN)
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

The 7 helper scripts in `scripts/` are independent. Only install what you actually want to run.

```bash
# For the Playwright scripts (probe / extract / crawl)
npm install                  # installs playwright (declared in package.json)
npx playwright install        # downloads browser binaries

# For the Python scripts (data_clean / citation_export / evidence_ledger)
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
python3 scripts/evidence_ledger.py self-test
python3 scripts/data_clean.py self-test
python3 scripts/citation_export.py self-test
python3 scripts/citation_render.py self-test
python3 scripts/extract_tables.py self-test
python3 scripts/score_source.py self-test
python3 scripts/research_plan.py self-test
python3 scripts/check_internal_refs.py
```

All twelve exit `0` and print pass markers (e.g. `ALL TESTS PASSED`, `All self-tests passed!`, `✓ PASS`).

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
npm run plan:init                             # write research-plan.json from template
npm run plan:check                            # validate schema + dep graph
npm run plan:status                           # one-line status per task
npm run plan:parallelizable                   # list task ids ready to dispatch
npm run plan:render                           # write PLAN.md for review
npm run plan:approve -- --by "Reviewer"       # approve before execution
npm run plan:revoke -- --reason "scope changed"
npm run plan:gate -- --gate synthesize_ready  # run a named gate
npm run refs:check                            # internal-refs CI guard, locally
```

For the multi-style citation rendering, install `pandoc ≥ 2.11` so `--citeproc` is available.

See each script's `--help` for the full argument list.

### Long-horizon workspace flow

For audit-grade or multi-context research, the output is one workspace
directory containing the plan, human-readable review, evidence ledger,
notes, sections, final report, and reproducibility checklist:

```bash
python3 scripts/research_plan.py init --workspace research-topic-2026-05-16
cd research-topic-2026-05-16
python3 ../scripts/research_plan.py render --file research-plan.json
python3 ../scripts/research_plan.py gate --file research-plan.json --gate plan_ready
python3 ../scripts/research_plan.py approve --file research-plan.json --by "Reviewer"
python3 ../scripts/research_plan.py gate --file research-plan.json --gate execute_ready
```

On Windows, use `python` instead of `python3` if `python3` is not on
PATH, or use the matching `npm run plan:*` commands.

Execution is blocked until the plan is rendered and approved. If no
human reviewer is reachable, the agent must explicitly pass
`--allow-unattended`, which records `agent-self-approved` in the plan.

---

## Configuration

The skill respects a project-local `research.config.json` when present. `research.config.example.json` documents every field with safe defaults. Highlights:

- `browser.default` — `playwright` (override to use another browser adapter)
- `crawl.maxDepth` / `crawl.maxPagesPerDomain` / `crawl.maxTotalPages` / `crawl.delayMs`
- `crawl.respectRobots` — default `true`
- `research.requireEvidenceLedger`, `research.requireContradictionPass` — default `true`
- `access.allowLoginWithUserPermission`, `access.allowPaywalledSources`, `access.allowCaptchaSolving`, `access.allowStealthEvasion` — default **`false`** for all four; only flip these with explicit, lawful user authorization
- `api.defaultDelayMs`, `api.maxRetries`, `api.respectRateLimitHeaders`
- `database.readOnly` — default `true`
- `citation.defaultFormat` — `bibtex`
- `largeScale.checkpointEveryN`, `largeScale.adaptiveRateLimit`

---

## Compatibility

The skill is framework-agnostic. It has been written against the conventions of:

- Claude / Anthropic skills (root `SKILL.md` with YAML frontmatter `name` + `description`)
- Devin (root `AGENTS.md` and `.agents/skills/*/SKILL.md` sub-skills)
- Generic agent frameworks that follow either pattern

The optional scripts need Node.js 18+ (for `api_fetch.mjs` and the Playwright scripts) and Python 3.9+ (for the Python utilities). Playwright is the only npm dependency.

---

## License

MIT — see `LICENSE`.
