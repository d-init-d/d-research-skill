# D Research Agent Instructions

Use the D Research workflow whenever the user asks for deep research, data scraping, source discovery, academic research, literature review, market research, technical investigation, or multi-source evidence synthesis.

Default browser automation: Playwright.

Core workflow:
1. Restate the research goal.
2. Decompose the topic into sub-questions, facets, entities, aliases, and source classes.
3. Build a source map before extraction.
4. Generate query fanout: broad, exact, official, primary, filetype, site-specific, dataset/API, recent, and contradiction queries.
5. Use browser-first probing for promising URLs.
6. Access public APIs and academic databases when available (OpenAlex, CrossRef, PubMed, Semantic Scholar, arXiv).
7. Extract accessible public data using the least invasive stable method.
8. Expand via links, sitemaps, files, public APIs, citations, and snowballing.
9. Process and clean extracted data when building datasets (see `references/data-processing-pipeline.md`).
10. Maintain an evidence ledger for important claims.
11. Search for contradictions before final synthesis.
12. Export citations in BibTeX/RIS format for academic work (see `references/citation-management.md`).
13. If a source is blocked, produce a blocker report instead of trying to bypass access controls.

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
