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

1. If Playwright is available, use `adapters/playwright.md`.
2. If another browser tool is configured, use `adapters/generic-browser.md`.
3. If URL fetch is available but no browser exists, use `adapters/fetch-only.md`.
4. If only web search exists, use `adapters/web-search-only.md`.
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
- `scripts/playwright_probe.mjs`: page classification and blocker detection
- `scripts/playwright_extract.mjs`: DOM text, table, link extraction
- `scripts/playwright_crawl.mjs`: bounded same-domain crawl
- `scripts/evidence_ledger.py`: CSV evidence ledger management
- `scripts/api_fetch.mjs`: paginated API fetch with rate limiting
- `scripts/data_clean.py`: data cleaning, deduplication, validation, statistics
- `scripts/citation_export.py`: BibTeX/RIS export, DOI enrichment

All scripts are optional. The workflow can be followed manually when scripts are unavailable.
