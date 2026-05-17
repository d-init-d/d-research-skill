# D Research Agent Instructions

Use the D Research workflow whenever the user asks for deep research, data scraping, source discovery, academic research, literature review, market research, technical investigation, or multi-source evidence synthesis.

Default browser automation: Playwright.

Core workflow:
1. Restate the research goal.
2. Decompose the topic into sub-questions, facets, entities, aliases, and source classes.
2a. For any long-horizon task (>5 sub-questions, >50 sources, multi-context-window runtime, or audit-grade output), initialise one workspace directory from `templates/research-plan.json` and follow `references/research-plan-protocol.md`. Use `scripts/research_plan.py init --slug <topic-slug>` so each run gets its own folder in the current directory by default, or under `researchPlan.workspace.baseDir` when configured. If the configured output folder is inaccessible, fall back to the current directory and tell the user. Use `scripts/research_plan.py configure-execution` after task decomposition so every task records its main/sub-agent assignment, context budget, and sub-agent thread use. Use `scripts/research_plan.py render` to create `PLAN.md`; the plan must show execution slots and per-task thread/budget assignments for user review. If the user changes a task's slot or thread count, use `scripts/research_plan.py set-execution`, render again, then run `gate --gate plan_ready`, get approval with `approve`, list parallel-safe tasks, mark task status, and gate the synthesize step. Dispatch to sub-agents only when `researchPlan.subagents.slots[]` has configured slots. Split tasks before they exceed their `execution.context_budget`; write findings to files immediately to avoid context loss. Use `--allow-unattended` only when no human review is available. Always report the final workspace path in the user-facing answer. See `examples/long-horizon-research-plan.md`.
3. Build a source map before extraction.
4. Generate query fanout: broad, exact, official, primary, filetype, site-specific, dataset/API, recent, and contradiction queries.
5. Use browser-first probing for promising URLs.
6. Access public APIs and academic databases when available (OpenAlex, CrossRef, PubMed, Semantic Scholar, arXiv).
7. Extract accessible public data using the least invasive stable method.
8. Expand via links, sitemaps, files, public APIs, citations, and snowballing.
9. Process and clean extracted data when building datasets (see `references/data-processing-pipeline.md`).
10. Maintain an evidence ledger for important claims.
11. Search for contradictions before final synthesis.
11a. If the first pass leaves evidence gaps, obscure facts, or contested claims, escalate to `references/frontier-search.md`. Maintain `templates/frontier-ledger.csv` and `templates/coverage-map.json` alongside the evidence ledger, score candidate nodes against open gaps, expand the highest-priority node, and stop on evidence saturation. Never use this as a way around access controls.
11b. If the user asks to verify or look up one specific atomic fact (one entity + one attribute, deterministic primary source, one-sentence answer), switch to `references/fact-verification.md` instead of running the full loop. Hit the primary source once, quote verbatim, file one ledger row with a one-shot independent re-check, and report. Bail back to the full workflow on any anomaly (non-2xx, contradicting mirrors, follow-up "why" questions). Do not reach for `references/frontier-search.md` from this branch.
12. Export citations in BibTeX/RIS format for academic work, and render to APA/MLA/IEEE/Chicago/Vancouver/Harvard/Nature with `scripts/citation_render.py` when needed (see `references/citation-management.md`).
13. For PRISMA-grade systematic reviews, follow `references/systematic-review-protocol.md` and populate `templates/prisma-flow.json`.
14. For structured data extraction (HTML tables, JSON-LD, sitemaps, RSS, OAI-PMH, embedded JSON), use the recipes in `references/data-extraction-toolbox.md` and `scripts/extract_tables.py`.
15. For tamper-evidence on the evidence ledger, sign it with `scripts/evidence_ledger.py sign` (HMAC-SHA256). Verify with the same script's `verify` subcommand.
16. Apply the source-quality rubric with `scripts/score_source.py score` to get deterministic per-row scores.
17. Before declaring an output "done", walk through `references/reproducibility-checklist.md`.
18. If a source is blocked, produce a blocker report instead of trying to bypass access controls.

Data access layers (in order):
- Web pages and files (browser/fetch)
- Public APIs: REST, GraphQL, SPARQL (see `references/api-access-workflow.md`)
- Academic databases (see `references/academic-databases.md`)
- Read-only databases when user provides access (see `adapters/database-readonly.md`)
- Specialized domain sources (see `references/specialized-domains.md`)

Available adapters:
- `adapters/playwright.md` (default)
- `adapters/generic-browser.md`
- `adapters/fetch-only.md`
- `adapters/web-search-only.md`
- `adapters/database-readonly.md`
- `adapters/graphql.md`

Safety rules:
- read-only by default
- do not bypass login, paywalls, captchas, rate limits, robots restrictions, or access controls
- do not use stealth plugins by default
- do not access private or personal data without authorization
- stop on repeated 403, 429, captcha, or login walls
- respect API rate limits and log all requests

For large-scale collection (100+ records), use checkpointing and adaptive rate limiting (see `references/large-scale-collection.md`).

If Playwright is unavailable, use the configured browser adapter. If no browser exists, use fetch. If fetch is unavailable, use web search and mark limitations.

Final outputs should include direct answer, key findings, evidence summary, data collected, sources reached, sources blocked, caveats, confidence, and next research steps. For academic outputs, include formatted citations.
