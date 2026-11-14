# Generic Browser Adapter (Host / Integrated / Non-Playwright)

Use this when the runtime environment provides an integrated or native browser
(for example: built-in browser subagent, Chrome DevTools MCP, CUA driver, or an
active CDP debugging session) OR another non-Playwright browser tool.

Tier 1 Browser-First accepts either this adapter OR `adapters/playwright.md`
interchangeably—prefer whichever live interactive browser is available and
authenticated cleanly in the host environment.

## Required capabilities

Use any available browser actions equivalent to:
- open URL and inspect final URL after redirects
- wait for page load / dynamic DOM stability
- read visible text and HTML/DOM regions
- inspect links, pagination controls, and downloadable files
- click/expand visible controls (accordions, reply threads, tabs, search inputs)
- capture screenshot
- download public files

## Mapping

Map the host or agent browser tool to these abstract actions:

| Abstract action | Host / Agent tool examples |
|---|---|
| open_page(url) | `browser` subagent / Chrome DevTools `navigate_page` / CUA `browser_navigate` |
| read_visible_text() | DOM evaluation / accessibility snapshot / text extraction |
| list_links() | DOM link extraction (`a[href]`) |
| click_visible(selector_or_label) | `click` / `browser_click` / `fill` + `Enter` |
| screenshot(path) | `take_screenshot` / visual capture |
| download_public_file(url) | browser download / public `curl` after discovery |
| record_evidence(...) | `scripts/execution_evidence.py record` (required for host browsers) |

## Recording DRS-1.1 execution evidence

After capturing content in a host/integrated browser, write the visible text to a
file in the research workspace and record a SHA-256-verified DRS-1.1 capture:

```bash
python3 scripts/execution_evidence.py record \
  --workspace research-output \
  --url "https://example.org/source" \
  --branch documentary \
  --question-id Q1 \
  --engine host-subagent \
  --mode host_integrated \
  --action-type extract \
  --text-file research-output/captures/source.txt
```

Supported `--engine` identifiers: `host-subagent`, `chrome-devtools-mcp`,
`cua-driver`, `cdp-session`. Or attach Playwright scripts directly to an
existing Chromium DevTools session via `--browser-mode auto --cdp-endpoint <url>`.

## Same safety policy

Apply the same rules as Playwright:
- no bypassing login, paywalls, captcha, rate limits, or access controls
- captcha solving and stealth/anti-detection are never allowed
- report blockers
