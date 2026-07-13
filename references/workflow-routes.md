# Workflow route table

## Contents

- [Workflow decision tree](#workflow-decision-tree)

## Workflow decision tree

**Step 0: Research intake.** Before choosing any branch or opening sources,
classify the request with `references/research-intake.md`. Assign one or more
shape labels (atomic fact, URL, person/public role, academic review, systematic
review, dataset/extraction, API/database, technical/market, due diligence,
policy/standards, creative/cultural, high-stakes, multilingual/local,
long-horizon, etc.), set research depth (fast, standard, or
completeness-first), set the safety posture, choose the expected output
artifact, and list the references/gates that apply. Use multi-label routing
when tasks overlap. If the classification changes safety,
legality, scope, or deliverable and cannot be resolved conservatively, ask the
user before proceeding; otherwise state the assumption and continue.

**Before picking a branch:** if the task is long-horizon (more than 5 sub-questions, more than 50 sources, multi-context-window runtime, or audit-grade output), apply the **research plan protocol** from `references/research-plan-protocol.md` as an outer loop *around* whichever branch fits the topic. The agent creates one workspace directory with `scripts/research_plan.py init --slug <topic-slug>`, writes `research-plan.json` (from `templates/research-plan.json`), renders `PLAN.md`, passes `plan_ready`, records approval, and passes `execute_ready`/`dispatch_ready` before dispatching any task. After research tasks finish, it passes `synthesize_ready`; after synthesis tasks, exact report/citations, claim coverage, and stopping criteria finish, it passes `release_ready`. See `examples/long-horizon-research-plan.md`. The branches below describe the *content* of the work; the protocol describes the *flow control* that keeps the work surviving across context resets.

**Before final synthesis:** for any non-trivial branch, apply
`references/execution-gates.md` unless a narrower fast path explicitly says to
skip it. If subagents exist, use the gate roles as independent reviewers; if
they do not, perform the same checklists manually. Do not present a result as
complete until source mapping, recall/coverage, evidence verification, blockers,
and confidence have been handled or explicitly marked out of scope.

### If the user asks to verify or look up one specific atomic fact

Use `references/fact-verification.md`. Applies when the question targets one named entity, one named attribute, has a deterministic primary source (API, registry, canonical text), and a one-sentence-or-quote answer. Skip decompose, source map, query fanout, and crawl. Hit the primary source once, quote the value verbatim, file one ledger row with a one-shot independent re-check, and report. If anything looks off — non-2xx status, contradicting mirrors, the user follows up with "why" — escalate to the broad research workflow below. Never reach for `references/frontier-search.md` from this branch; atomic facts either fetch cleanly or fail loudly.

### If the user asks to capture or analyze a public social-media post

Use `references/social-media-archival.md`. Capture public posts from 12 supported platforms (Reddit, Hacker News, Mastodon, Bluesky, Lemmy, X, Facebook, Instagram, TikTok, YouTube, Threads, LinkedIn) plus a generic fallback. The script `scripts/social_snapshot.py` handles snapshot capture, hash-based verification, and evidence-ledger row generation. **Read the privacy boundary section first** — it refuses minors, private individuals, harassment/stalking/doxxing framings, and login-bypass attempts before making any HTTP call. Tier A platforms (Reddit, HN, Mastodon, Bluesky, Lemmy) use direct public API fetch with high verifiability; Tier B platforms (X, Facebook, Instagram, TikTok, YouTube, Threads, LinkedIn) use archive-only via `scripts/wayback.py` with low verifiability.

### If the user asks for public-role information about a specific named person

Use `references/person-aggregation.md`. Applies when the user wants scattered public-role information about one named person (maintainer, author, speaker, journalist, public figure) and there is a canonical anchor (GitHub profile, ORCID, package author field, faculty page, verified byline). The value is in cross-source aggregation and homonym disambiguation, not in any one source. **Apply the privacy boundary in that file before doing anything else** — it is a hard stop, not abstract guidance; home address, family, private accounts, personal contact, photos, medical/financial/legal/orientation/whereabouts, pseudonym-to-real-name re-identification, and explicitly-private items are out of scope regardless of whether they appear on the open web. Refuse on minors, private individuals, and harassment/stalking/doxxing framings. Saturate at 25 ledger rows or three sources adding no new verified claims, and never escalate to `references/frontier-search.md` to chase one more piece of personal info.

### If the user has a large corpus or many ledger rows and asks a semantic question

Use `references/semantic-retrieval.md` when a corpus is large enough that keyword search is brittle (roughly >30 documents or many evidence-ledger rows) and the task asks for conceptually related material, near-duplicates, or "find claims like X". Build or query an index with `scripts/embed_corpus.py`; prefer local backends for private data, and require explicit remote opt-in for Cohere.

### If the user asks for a broad research answer

Use the full deep research workflow. Produce a source-backed synthesis with evidence, confidence, caveats, and next steps.

### If the user asks for due diligence, public investigation, risk review, or red flags

Use `references/research-intake.md` with `due_diligence_or_investigation`.
Default to completeness-first unless the user explicitly asks for a quick scan.
Build a source map, keep a search log, maintain an evidence ledger for verified
claims and red flags, run a contradiction pass, and apply execution gates before
synthesis. Separate verified facts, red flags, unresolved risks, benign
unknowns, confidence, and recommended manual checks. Do not gather private
personal data or phrase allegations beyond what the evidence supports.

### If the user asks for policy, standards, RFC, governance, or compliance analysis

Use `references/research-intake.md` with `policy_or_standards_analysis`.
Prioritize canonical text, version/status, effective dates, errata, issuing-body
guidance, and exact clause evidence. Distinguish normative from informative
language, draft from final or superseded text, and obligations from permissions
or implementation notes. Add `references/specialized-domains.md` only when the
question is legal/government/financial or jurisdiction-specific.

### If the user asks for creative, cultural, media, trend, reception, or archive research

Use `references/research-intake.md` with `creative_or_cultural_research`.
Anchor on primary works, official releases, creator/publisher/studio/label
records, archives, criticism, cultural scholarship, trade press, and public
reception metrics when available. Treat fan/community/social sources as
reception evidence, not as verified factual authority about private people.

### If the user asks to collect a dataset

Use the crawl and extraction workflow. Produce structured data, a data dictionary, extraction method, coverage notes, and blocked-source report.

### If the user asks for academic research, literature review, thesis, or project work

Use the academic workflow. Define research questions, search strings, inclusion and exclusion criteria, screening log, evidence table, synthesis, and citations.

### If the user asks for a systematic review, scoping review, rapid review, or PRISMA-grade output

Use `references/systematic-review-protocol.md` (PRISMA 2020). Pick the right review type with `references/synthesis-patterns.md`. Populate `templates/prisma-flow.json` for the flow diagram and `templates/screening-log.csv` for screening decisions. For citation chasing / snowball sampling, use `scripts/citation_graph.py expand --seed seeds.csv --direction both` to traverse forward and backward citations from included papers. See `examples/systematic-review-prisma.md` for an end-to-end walkthrough.

### If the user gives a specific URL

Probe the URL first with the browser. Classify access status, extract available data, discover linked files/endpoints/pages, and report blockers.

If the URL appears relevant but is blocked by Cloudflare, bot challenge, captcha, 403, 429, or a JavaScript challenge, follow `references/anti-bot-fallback.md` once before declaring it blocked. Record failed fallback attempts as low-confidence process rows in the evidence ledger, then produce `references/blocker-report.md` if no lawful public fallback works.

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

Use the **research plan protocol** in `references/research-plan-protocol.md`. The agent MUST start by creating a single workspace directory with `scripts/research_plan.py init --slug <topic-slug>`, writing `research-plan.json` (from `templates/research-plan.json`), validating it with `scripts/research_plan.py check`, refreshing execution annotations with `scripts/research_plan.py configure-execution`, rendering `PLAN.md`, running `gate --gate plan_ready`, recording approval with `scripts/research_plan.py approve`, and passing `gate --gate execute_ready` before dispatch. `init` reads `research.config.json` when present; by default it creates a fresh run folder in the current working directory, or under `researchPlan.workspace.baseDir` if configured. If that configured folder is inaccessible, it falls back to the current directory and warns. Unattended runs fail by default unless the agent explicitly records `--allow-unattended`. After `execute_ready`, dispatch parallel-safe tasks via `scripts/research_plan.py parallelizable` only when `researchPlan.subagents.slots[]` contains configured slots (`agent`, `contextLength`, and `maxParallel` are not null). If the user changes task assignment, slot, or thread count during review, use `scripts/research_plan.py set-execution --id <task> --agent <main|subagent> [--slot <slot>] [--parallel-threads <n>]`, then render, approve, and pass `execute_ready` again. If no sub-agent is configured, run tasks with the main agent and split the plan according to the main agent's context length. Context overflow is a hard failure: each task must fit its `execution.context_budget`; if not, split the task, write partial findings to files immediately, re-run `configure-execution`, render, re-approve, and re-run `execute_ready`. Mark task status as work progresses, gate the synthesize step with `scripts/research_plan.py gate --gate synthesize_ready` after research-phase tasks only, and gate release after synthesis tasks, exact report/citations, claim coverage, and stopping criteria complete. Always include the final workspace path in the user-facing answer. See `examples/long-horizon-research-plan.md` for the end-to-end walkthrough. This is the right default for any task with >5 sub-questions, >50 sources, or estimated runtime that does not fit in one context window.

### If the user wants visualizations or charts

Use `references/data-visualization.md`. Generate matplotlib/plotly charts as part of the report.

### If the user wants to monitor changes over time

Use `references/monitoring-change-detection.md`. Take baseline snapshots, detect changes, report diffs.

### If the user needs research across multiple languages

Use `references/multilingual-research.md`. Translate queries per language, search local-language sources, extract in original language, and cross-validate findings across languages.

If Vietnamese sources, Vietnam-local institutions, Vietnamese news, or
Vietnamese public/community sources are materially relevant, use
`references/vietnamese-source-discovery.md` as a companion. It adds
diacritic/no-diacritic alias handling, local source basins, and date/identity
discipline without making Vietnamese discovery a global default.

### If recall is thin or the evidence lives in community, vernacular, or jargon-heavy registers

Use `references/register-and-jargon-expansion.md`. Applies when a clinical,
legal, standards, or academic query under-recalls because the people who hold
the evidence use lay terms, community jargon, or emergent slang. Walk the
register ladder in both directions: formal -> vernacular to open recall, and
vernacular -> formal to anchor every community term back to a primary source.
Harvest vocabulary from fresh results only (never from model memory), keep only
terms that recur across two or more independent community sources, and treat the
harvested vocabulary as a discovery layer — never as evidence. Every claim still
passes `references/source-quality-rubric.md` and the contradiction pass. This is
an additive layer on top of `references/multilingual-research.md`, not a
replacement for native-language search.

### If the first pass leaves evidence gaps, obscure / long-tail facts, or contested claims

Escalate to `references/frontier-search.md`. Build a small best-first frontier over candidate queries, URLs, files, APIs, citations, repos, aliases, and archives; score each node against the unresolved sub-question; expand the highest-priority node; and stop on evidence saturation rather than node count. Maintain `templates/frontier-ledger.csv` and `templates/coverage-map.json` alongside `templates/evidence-ledger.csv`. Never use this as a way to bypass access controls — blocked nodes still go to `references/blocker-report.md`.


See also: research-intake.md, execution-gates.md.
