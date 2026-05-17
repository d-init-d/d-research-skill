---
name: d-research
description: Browser-first deep research and lawful public-data collection for AI agents. Triggers: web research, source discovery, scraping public data, literature reviews, market or technical research, evidence ledgers, blocker reports. Read-only; never bypasses logins, paywalls, captchas, or rate limits.
---

# D Research

## Mission

Use this skill to maximize reachable evidence under available tools, permissions, and open-web constraints.

Default browser automation tool: Playwright.

Use this skill for:
- deep web research
- public web data collection
- source discovery
- academic and literature review
- market, competitor, product, and technical research
- collecting evidence for reports, essays, theses, and projects
- researching dynamic websites that require browser interaction
- reporting blocked sources so the user can retrieve data manually

Do not use this skill to bypass access controls, login walls, paywalls, captchas, rate limits, or explicit access restrictions.

## Core model

Run every research task as a layered investigation:

1. define the question
2. decompose the topic
3. map likely sources
4. generate query fanout
5. discover candidate URLs
6. probe sources with browser-first access
7. extract accessible data
8. expand through links, sitemaps, files, and public APIs
9. verify claims with an evidence ledger
10. search for contradictions
11. report unreachable or blocked data with manual instructions
12. synthesize the final answer

## Tool priority

Use the best available tool stack in this order:

1. user-provided context, URLs, files, and constraints
2. web search
3. URL fetch or HTTP read, when available
4. Playwright browser automation
5. public files: PDF, CSV, JSON, XML, XLSX, DOCX, TXT
6. public API or public network responses exposed by the page
7. local files or repo search, when the user provides a workspace
8. configured browser adapter, if not Playwright
9. web-search-only fallback, if no browser or fetch tool exists

If a tool is unavailable, continue with the next-best method and record the limitation.

For the full decision rules on choosing between adapters (e.g. when to demote Playwright to fetch-only, when web search alone is acceptable), see `references/tool-adapter-policy.md`.

## Data access layers

Access data in order of preference:

1. **Web layer** — public pages, dynamic content, file downloads (existing browser/fetch workflow)
2. **File layer** — CSV, JSON, XML, PDF, XLSX, DOCX from public URLs
3. **API layer** — REST, GraphQL, SPARQL endpoints with proper authentication. See `references/api-access-workflow.md`
4. **Database layer** — read-only SQL/NoSQL access when user provides credentials. See `adapters/database-readonly.md`
5. **Academic database layer** — OpenAlex, CrossRef, PubMed, Semantic Scholar, arXiv. See `references/academic-databases.md`
6. **Specialized domain layer** — financial APIs, patent databases, government portals. See `references/specialized-domains.md`

For each layer, follow the safety boundary: read-only, respect rate limits, log all access.

## Safety boundary

Allowed:
- open public pages
- render dynamic pages
- click normal user-visible navigation
- use site search boxes and filters
- paginate through public results
- expand tabs, accordions, and lazy-loaded sections
- download public files
- inspect public network requests initiated by a page
- extract visible text, tables, links, metadata, and files
- produce blocker reports when access fails

Not allowed:
- bypass login or authentication
- bypass paywalls or subscription checks
- solve or evade captchas
- evade rate limits or anti-bot systems
- use stealth plugins by default
- use stolen cookies, leaked tokens, or credentials not explicitly provided by the user
- access private, personal, or sensitive data without authorization
- ignore robots or explicit site restrictions when acting as a crawler

When blocked, do not force access. Produce a blocker report.

The full safety and access policy (legal/ethical framing, what counts as a public source, escalation steps) is in `references/safety-and-access-policy.md`. Read it before doing anything that touches authenticated or rate-limited surfaces.

## Workflow decision tree

**Before picking a branch:** if the task is long-horizon (more than 5 sub-questions, more than 50 sources, multi-context-window runtime, or audit-grade output), apply the **research plan protocol** from `references/research-plan-protocol.md` as an outer loop *around* whichever branch fits the topic. The agent creates one workspace directory with `scripts/research_plan.py init --slug <topic-slug>`, writes `research-plan.json` (from `templates/research-plan.json`), renders `PLAN.md`, gets approval with `scripts/research_plan.py approve`, dispatches parallel-safe tasks (optionally to sub-agents if config allows), gates the synthesize step, and only then composes the final report. See `examples/long-horizon-research-plan.md`. The branches below describe the *content* of the work; the protocol describes the *flow control* that keeps the work surviving across context resets.

### If the user asks to verify or look up one specific atomic fact

Use `references/fact-verification.md`. Applies when the question targets one named entity, one named attribute, has a deterministic primary source (API, registry, canonical text), and a one-sentence-or-quote answer. Skip decompose, source map, query fanout, and crawl. Hit the primary source once, quote the value verbatim, file one ledger row with a one-shot independent re-check, and report. If anything looks off — non-2xx status, contradicting mirrors, the user follows up with "why" — escalate to the broad research workflow below. Never reach for `references/frontier-search.md` from this branch; atomic facts either fetch cleanly or fail loudly.

### If the user asks for a broad research answer

Use the full deep research workflow. Produce a source-backed synthesis with evidence, confidence, caveats, and next steps.

### If the user asks to collect a dataset

Use the crawl and extraction workflow. Produce structured data, a data dictionary, extraction method, coverage notes, and blocked-source report.

### If the user asks for academic research, literature review, thesis, or project work

Use the academic workflow. Define research questions, search strings, inclusion and exclusion criteria, screening log, evidence table, synthesis, and citations.

### If the user asks for a systematic review, scoping review, rapid review, or PRISMA-grade output

Use `references/systematic-review-protocol.md` (PRISMA 2020). Pick the right review type with `references/synthesis-patterns.md`. Populate `templates/prisma-flow.json` for the flow diagram and `templates/screening-log.csv` for screening decisions. See `examples/systematic-review-prisma.md` for an end-to-end walkthrough.

### If the user gives a specific URL

Probe the URL first with the browser. Classify access status, extract available data, discover linked files/endpoints/pages, and report blockers.

### If only web search exists

Run search-based research. Prefer official and primary sources. Mark sources that were found but not directly opened.

### If the user asks to collect data from an API

Use `references/api-access-workflow.md`. Discover endpoints, authenticate if user provides keys, paginate, handle rate limits, export structured data.

### If the user asks for large-scale collection (100+ pages/records)

Use `references/large-scale-collection.md`. Enable checkpointing, adaptive rate limiting, batch processing.

### If the user asks for financial, patent, legal, or government data

Use `references/specialized-domains.md`. Route to appropriate free APIs and data portals.

### If the user asks for a literature review with citations

Combine the academic workflow with `references/academic-databases.md` and `references/citation-management.md`. Export citations in BibTeX or RIS with `scripts/citation_export.py`, then render APA / MLA / IEEE / Chicago / Vancouver / Harvard / Nature with `scripts/citation_render.py` (pandoc + CSL).

### If the user wants data cleaned or analyzed

Use `references/data-processing-pipeline.md` after extraction. Run cleaning, validation, and analysis stages.

### If the user asks to extract structured data from web pages (tables, JSON-LD, embedded JSON, sitemaps, RSS, OAI-PMH)

Use `references/data-extraction-toolbox.md` for recipe-style playbooks. Use `scripts/extract_tables.py` for HTML `<table>` → CSV, `scripts/api_fetch.mjs` for REST/GraphQL, and `templates/data-package.json` to publish the result as a Frictionless Data Package.

### If the user needs tamper-evident research output, a signed evidence ledger, or a reproducibility audit

Sign the ledger with `scripts/evidence_ledger.py sign --file evidence-ledger.csv --key-env D_RESEARCH_LEDGER_KEY`; the verifier is `evidence_ledger.py verify`. Then walk through `references/reproducibility-checklist.md` before declaring done.

### If the task is long-horizon, multi-source, or risks blowing context

Use the **research plan protocol** in `references/research-plan-protocol.md`. The agent MUST start by creating a single workspace directory with `scripts/research_plan.py init --slug <topic-slug>`, writing `research-plan.json` (from `templates/research-plan.json`), validating it with `scripts/research_plan.py check`, refreshing execution annotations with `scripts/research_plan.py configure-execution`, rendering `PLAN.md`, running `gate --gate plan_ready`, and getting approval with `scripts/research_plan.py approve` before dispatch. `init` reads `research.config.json` when present; by default it creates a fresh run folder in the current working directory, or under `researchPlan.workspace.baseDir` if configured. If that configured folder is inaccessible, it falls back to the current directory and warns. Unattended runs fail by default unless the agent explicitly records `--allow-unattended`. After approval, dispatch parallel-safe tasks via `scripts/research_plan.py parallelizable` only when `researchPlan.subagents.slots[]` contains configured slots (`agent`, `contextLength`, and `maxParallel` are not null). If the user changes task assignment, slot, or thread count during review, use `scripts/research_plan.py set-execution --id <task> --agent <main|subagent> [--slot <slot>] [--parallel-threads <n>]`, then render and approve again. If no sub-agent is configured, run tasks with the main agent and split the plan according to the main agent's context length. Context overflow is a hard failure: each task must fit its `execution.context_budget`; if not, split the task, write partial findings to files immediately, re-run `configure-execution`, render, and re-approve. Mark task status as work progresses, gate the synthesize step with `scripts/research_plan.py gate --gate synthesize_ready`, and only then compose the final report. Always include the final workspace path in the user-facing answer. See `examples/long-horizon-research-plan.md` for the end-to-end walkthrough. This is the right default for any task with >5 sub-questions, >50 sources, or estimated runtime that does not fit in one context window.

### If the user wants visualizations or charts

Use `references/data-visualization.md`. Generate matplotlib/plotly charts as part of the report.

### If the user wants to monitor changes over time

Use `references/monitoring-change-detection.md`. Take baseline snapshots, detect changes, report diffs.

### If the user needs research across multiple languages

Use `references/multilingual-research.md`. Translate queries per language, search local-language sources, extract in original language, and cross-validate findings across languages.

### If the first pass leaves evidence gaps, obscure / long-tail facts, or contested claims

Escalate to `references/frontier-search.md`. Build a small best-first frontier over candidate queries, URLs, files, APIs, citations, repos, aliases, and archives; score each node against the unresolved sub-question; expand the highest-priority node; and stop on evidence saturation rather than node count. Maintain `templates/frontier-ledger.csv` and `templates/coverage-map.json` alongside `templates/evidence-ledger.csv`. Never use this as a way to bypass access controls — blocked nodes still go to `references/blocker-report.md`.

## Standard deep research workflow

### 1. Restate the task

Capture:
- research goal
- entities, products, technologies, organizations, places, or people
- timeframe and freshness requirement
- geography and language constraints
- desired output format
- acceptable source types
- forbidden source types
- whether the task is research, dataset collection, academic review, or mixed

When the request is broad, proceed with reasonable assumptions and state them.

### 2. Decompose the topic

Use `references/topic-decomposition.md`.

Create:
- root question
- sub-questions
- facets
- entities
- synonyms and aliases
- likely source classes
- unknowns
- research risks
- stopping criteria

### 3. Build a source map

Use `references/source-discovery.md`.

Look for:
- official sites and docs
- source repositories
- issue trackers and discussions
- changelogs and releases
- public datasets
- public APIs
- standards, RFCs, and specifications
- academic papers
- government filings
- PDFs and reports
- tables, dashboards, and data portals
- news, blogs, forums, and community sources
- archives and caches, when allowed

### 4. Generate query fanout

Use `references/query-patterns.md`.

For every important sub-question, generate:
- broad query
- exact phrase query
- official source query
- primary source query
- filetype query
- site-specific query
- dataset/API query
- recent query
- contradiction query
- alternate-language query when useful

Do not conclude "not found" until broad, exact, official, primary, filetype, and contradiction searches have been attempted or are clearly irrelevant.

### 5. Probe sources with browser-first access

Use Playwright by default. See `adapters/playwright.md` and `references/browser-first-crawl.md`.

For each promising URL:
- open the page
- wait for page stability
- record final URL, title, status if available, and access state
- extract visible text, headings, links, files, tables, metadata, dates, and page controls
- capture screenshots when evidence or blockers need visual proof
- classify the page as accessible, partial, dynamic, blocked, login-required, paywalled, captcha, rate-limited, robots-restricted, broken, or manual-needed

### 6. Extract data

Use the least invasive reliable method:

1. public downloadable files
2. public API or structured endpoint linked/exposed by the page
3. static HTML tables and semantic markup
4. visible page text
5. browser-rendered content after normal interaction
6. screenshots only when text extraction is unreliable

Always record the extraction method.

For the detailed playbooks per content type (HTML tables, JSON-LD, PDFs, embedded JSON in `<script>` tags, datalayer objects, GraphQL responses, etc.), see `references/extraction-methods.md`.

### 7. Crawl and expand

For accessible sources:
- use sitemaps and robots discovery when acting as a crawler
- follow relevant internal links
- follow citation and reference links
- follow pagination and filters that expose public data
- deduplicate URLs
- limit crawl depth and page count
- stop when evidence saturation is reached

Default crawl limits unless overridden:
- max depth: 2
- max pages per domain: 30
- max total pages: 100
- delay between page loads: 1000 ms
- respect robots: true
- follow external links: false unless needed for source discovery

### 8. Maintain evidence ledger

Use `references/evidence-ledger.md`.

For tamper-evidence, sign the ledger with `scripts/evidence_ledger.py sign` (HMAC-SHA256 over the canonicalised CSV bytes). The verifier (`scripts/evidence_ledger.py verify`) detects any edits made after signing.

Every important claim must have:
- claim
- source
- source type
- date
- access method
- extracted evidence
- contradiction status
- confidence

Separate facts, inferences, speculation, and unknowns.

### 9. Run contradiction pass

Before final output:
- search for contrary evidence
- compare source dates and versions
- identify stale or deprecated pages
- check whether secondary sources cite primary sources
- downgrade confidence when evidence is weak or conflicting
- state unresolved contradictions clearly

Score every source on the rubric in `references/source-quality-rubric.md` (primary vs. secondary, authority, recency, methodology, independence). Use the rubric scores to set the `confidence` column in the evidence ledger and to break ties between contradicting sources.

### 10. Report blockers

Use `references/blocker-report.md`.

If a likely useful source cannot be extracted, report:
- URL
- why it matters
- access status
- what was attempted
- what blocked access
- visible evidence of blocker
- likely manual path
- exact data the user should export, copy, screenshot, or download
- alternative sources found

### 11. Synthesize

Before composing the final answer, scan the evidence ledger and (if maintained) `templates/coverage-map.json` for unresolved gaps. If a key sub-question still has `missing` entries or only low-confidence non-primary sources, escalate one pass with `references/frontier-search.md` instead of synthesising over thin evidence.

Use `references/final-report-template.md`.

Default final answer:
1. direct answer
2. key findings
3. evidence summary
4. data collected
5. sources reached
6. sources blocked
7. contradictions and caveats
8. confidence
9. next research steps

For academic outputs, use the academic report format in `references/academic-research-protocol.md`.

## Optional bundled scripts

The `scripts/` directory contains helper scripts for agents running in a local Node environment.

Use them when Playwright is installed and the task benefits from repeatable extraction:

- `scripts/playwright_probe.mjs`: classify a page, detect blockers, list links/files/tables, optionally screenshot
- `scripts/playwright_extract.mjs`: extract visible text, tables, links, metadata, and files into JSON or Markdown
- `scripts/playwright_crawl.mjs`: bounded same-domain crawl with basic robots awareness and page manifests
- `scripts/evidence_ledger.py`: initialize, validate, and **HMAC-sign / verify** CSV evidence ledgers
- `scripts/api_fetch.mjs`: paginated API fetch with rate limiting, retry, and multiple output formats
- `scripts/data_clean.py`: data cleaning, deduplication, validation, statistics, and merging
- `scripts/citation_export.py`: BibTeX/RIS citation export and DOI enrichment via CrossRef
- `scripts/citation_render.py`: render BibTeX into APA / MLA / IEEE / Chicago / Vancouver / Harvard / Nature / Science / ACM / AMA styles via pandoc + CSL
- `scripts/extract_tables.py`: extract HTML `<table>` elements into CSV (handles `colspan`/`rowspan`, stdlib only)
- `scripts/score_source.py`: apply the `references/source-quality-rubric.md` rubric to an evidence ledger and emit per-row scores + bands
- `scripts/research_plan.py`: init / configure-execution / set-execution / render / approve / revoke / check / status / parallelizable / mark / block / add-task / gate — drives the long-horizon context-safe protocol in `references/research-plan-protocol.md`
- `scripts/check_internal_refs.py`: validate backticked in-repo path references (CI guard)

The scripts are optional. If dependencies are unavailable, follow the workflow manually using the agent's browser or web tools.

## Configuration

If a project has `research.config.json`, obey it. Otherwise use `research.config.example.json` defaults.

Important config fields:
- browser.default
- browser.timeoutMs
- crawl.maxDepth
- crawl.maxPagesPerDomain
- crawl.maxTotalPages
- crawl.delayMs
- crawl.respectRobots
- research.requireEvidenceLedger
- research.requireContradictionPass
- researchPlan.context.mainContextLength
- researchPlan.context.taskBudgetRatio
- researchPlan.context.writeFindingsImmediately
- researchPlan.subagents.slots[].id
- researchPlan.subagents.slots[].agent
- researchPlan.subagents.slots[].contextLength
- researchPlan.subagents.slots[].maxParallel
- researchPlan.workspace.baseDir
- researchPlan.workspace.nameTemplate
- researchPlan.workspace.fallbackToCwdOnError
- researchPlan.finalResponse.reportWorkspacePath
- access.allowLoginWithUserPermission
- access.allowPaywalledSources
- access.allowCaptchaSolving
- access.allowStealthEvasion
- api.defaultDelayMs
- api.maxRetries
- api.respectRateLimitHeaders
- database.queryTimeoutMs
- database.maxResultRows
- database.readOnly
- citation.defaultFormat
- citation.enrichFromCrossRef
- monitoring.enabled
- monitoring.defaultIntervalMinutes
- processing.autoClean
- processing.detectOutliers
- largeScale.checkpointEveryN
- largeScale.adaptiveRateLimit

Default access policy is conservative and read-only.

For long-horizon research, `researchPlan.finalResponse.reportWorkspacePath` defaults to `true`; always tell the user the workspace path where the plan, ledger, notes, sections, report, and checklist were written.

## Output standards

Never present scraped data as complete unless coverage was verified.

Always include:
- what was searched
- what was accessed
- what was extracted
- what was blocked
- what remains unknown
- confidence level

Use concise outputs for simple tasks. Use full evidence-ledger reports for high-stakes, academic, or dataset-building tasks.

## Further reading

The research methodology and source taxonomy behind this skill are written up in `references/research-bibliography.md`. Read it when adapting the skill to a new domain or when explaining the methodology to a stakeholder.

For contributors extending the skill (new references, adapters, examples, scripts, or templates), see `CONTRIBUTING.md`.
