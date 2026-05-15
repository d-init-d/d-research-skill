# Generic Browser Adapter

Use this when a browser tool is available but it is not Playwright.

## Required capabilities

Use any available browser actions equivalent to:
- open URL
- wait for page load
- read visible text
- inspect links
- click visible controls
- extract tables
- capture screenshot
- download public files

## Mapping

Map the agent's browser tool to these abstract actions:

| Abstract action | Tool-specific action |
|---|---|
| open_page(url) | browser goto/open |
| read_visible_text() | text extraction/read page |
| list_links() | DOM/link extraction |
| click_visible(selector_or_label) | click action |
| screenshot(path) | screenshot action |
| download_public_file(url) | download/fetch |

## Same safety policy

Apply the same rules as Playwright:
- no bypassing login, paywalls, captcha, rate limits, or access controls
- no stealth by default
- report blockers
