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

## Adapter selection

1. If Playwright is available, use `adapters/playwright.md`.
2. If another browser tool is configured, use `adapters/generic-browser.md`.
3. If URL fetch is available but no browser exists, use `adapters/fetch-only.md`.
4. If only web search exists, use `adapters/web-search-only.md`.

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
