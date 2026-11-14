# Tool Adapter Policy

Use this file to remain portable across agents while defaulting to Playwright.

## Default assumptions

Minimum capability:
- web search

Preferred capability:
- Playwright browser automation

Optional capabilities:
- fetch or read_url
- local filesystem
- PDF/document parser
- local search index
- self-hosted search
- MCP tools
- database read-only tools
- API fetch with pagination and rate limiting
- GraphQL introspection and query
- Database read-only access (SQL, NoSQL)
- Academic database API clients
- Data processing (cleaning, validation, statistics)
- Citation export (BibTeX, RIS)
- Data visualization (matplotlib, plotly)

## Adapter selection

Follow flexible 3-tier Browser-First priority:

1. **Tier 1A (Host / Integrated Browser):** If the host runtime exposes an integrated browser (`browser` subagent, Chrome DevTools MCP, CUA driver, or CDP session), use `adapters/generic-browser.md` (or `--browser-mode cdp|auto`) and log captures with `scripts/execution_evidence.py record`.
2. **Tier 1B (Local Playwright):** If Playwright/Chromium is available locally (standalone or `--browser-mode auto`), use `adapters/playwright.md`.
3. **Tier 2 (URL Fetch):** If URL fetch is available but no interactive browser is available/required, use `adapters/fetch-only.md`.
4. **Tier 3 (Web Search):** If only web search exists (or to discover seeds before browsing), use `adapters/web-search-only.md` (`scripts/web_search.mjs --federated`).
5. If a GraphQL endpoint is discovered, use `adapters/graphql.md`.
6. If user provides database credentials, use `adapters/database-readonly.md`.
7. For academic database APIs, use `references/academic-databases.md`.
8. For REST API endpoints, use `references/api-access-workflow.md`.

## Do not hardcode vendor tools

When writing instructions or reports, describe capability by function:
- web search
- browser open
- fetch URL
- extract text
- screenshot
- download file
- crawl links

Avoid assuming a specific hosted service.

## Tool fallback language

If the ideal tool is missing, state:

- intended method
- available fallback
- limitation caused by fallback
- what manual action would remove the limitation

## Script capabilities

Optional bundled scripts extend the agent's capabilities:
- `scripts/execution_evidence.py`: record/verify DRS-1.1 host or Playwright browser evidence
- `scripts/playwright_probe.mjs`: page classification and blocker detection
- `scripts/playwright_extract.mjs`: DOM text, table, link extraction (`--browser-mode`, `--activity-log`, `--capture-records`)
- `scripts/playwright_crawl.mjs`: bounded same-domain crawl (`--activity-log`, `--capture-records`)
- `scripts/browser_interaction.mjs`: interactive search/expand/paginate/reply automation
- `scripts/web_search.mjs`: fallback/federated multi-provider search (`--federated`)
- `scripts/evidence_ledger.py`: CSV evidence ledger management
- `scripts/api_fetch.mjs`: paginated API fetch with rate limiting
- `scripts/data_clean.py`: data cleaning, deduplication, validation, statistics
- `scripts/citation_export.py`: BibTeX/RIS export, DOI enrichment

All scripts are optional. The workflow can be followed manually when scripts are unavailable.
