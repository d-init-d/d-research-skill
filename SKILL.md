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

### If the user asks for a broad research answer

Use the full deep research workflow. Produce a source-backed synthesis with evidence, confidence, caveats, and next steps.

### If the user asks to collect a dataset

Use the crawl and extraction workflow. Produce structured data, a data dictionary, extraction method, coverage notes, and blocked-source report.

### If the user asks for academic research, literature review, thesis, or project work

Use the academic workflow. Define research questions, search strings, inclusion and exclusion criteria, screening log, evidence table, synthesis, and citations.

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

Combine the academic workflow with `references/academic-databases.md` and `references/citation-management.md`. Export citations in BibTeX or RIS format.

### If the user wants data cleaned or analyzed

Use `references/data-processing-pipeline.md` after extraction. Run cleaning, validation, and analysis stages.

### If the user wants visualizations or charts

Use `references/data-visualization.md`. Generate matplotlib/plotly charts as part of the report.

### If the user wants to monitor changes over time

Use `references/monitoring-change-detection.md`. Take baseline snapshots, detect changes, report diffs.

### If the user needs research across multiple languages

Use `references/multilingual-research.md`. Translate queries per language, search local-language sources, extract in original language, and cross-validate findings across languages.

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
- `scripts/evidence_ledger.py`: initialize and validate CSV evidence ledgers
- `scripts/api_fetch.mjs`: paginated API fetch with rate limiting, retry, and multiple output formats
- `scripts/data_clean.py`: data cleaning, deduplication, validation, statistics, and merging
- `scripts/citation_export.py`: BibTeX/RIS citation export and DOI enrichment via CrossRef

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
