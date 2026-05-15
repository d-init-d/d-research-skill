# Playwright Adapter

Use Playwright as the default browser automation layer.

## Use Playwright for

- opening pages found through search
- rendering JavaScript-heavy pages
- clicking visible navigation, tabs, accordions, filters, and pagination
- reading visible text
- extracting links, tables, files, headings, and metadata
- capturing screenshots for evidence or blockers
- observing public network requests initiated by the page
- downloading public files

## Do not use Playwright for

- bypassing login
- bypassing paywalls
- solving or evading captchas
- bypassing rate limits
- stealth or anti-detection behavior by default
- forging identity
- using credentials without explicit user permission
- accessing private or personal data without authorization

## Recommended browser probe

For every important page:

1. open URL
2. wait for DOM content loaded
3. wait briefly for network/page stability
4. record final URL, title, status, and language
5. extract visible text sample
6. extract headings
7. extract links
8. detect downloadable files
9. detect tables
10. detect forms, search boxes, filters, and pagination
11. detect blockers
12. screenshot when useful

## Wait strategy

Prefer robust waits:
- wait for DOM content loaded
- wait for target selectors when known
- wait for network idle only when useful
- avoid arbitrary long sleeps
- stop on repeated failures

## Interaction strategy

Interact only with user-visible controls:
- search fields
- filters
- next page links
- show more buttons
- tabs
- accordions

Record the interaction path when it affects the extracted data.

## Network observation

Allowed:
- note public JSON, CSV, or API responses initiated by normal page loading
- prefer documented public APIs when available

Not allowed:
- use private endpoints that require unauthorized tokens
- replay state-changing requests
- exfiltrate cookies, tokens, or secrets

## Script usage

Optional scripts:

```bash
npm install
npx playwright install chromium
node scripts/playwright_probe.mjs --url https://example.com --out research-output/probe.json --screenshot research-output/probe.png
node scripts/playwright_extract.mjs --url https://example.com --format json --out research-output/extract.json
node scripts/playwright_crawl.mjs --seed https://example.com --outDir research-output/crawl --maxDepth 2 --maxPages 30
```
