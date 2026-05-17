# Browser-First Crawl Protocol

Use this file when researching or collecting data from websites.

## Principle

Use the browser to behave like a normal user reading public web pages. Do not evade access controls.

## Page access states

Classify every important URL:

- accessible: content visible and extractable
- partial: some content visible, some blocked or lazy-loaded
- dynamic: requires JavaScript rendering
- interaction-needed: tabs, accordions, filters, pagination, or search box
- login-required: authentication required
- paywalled: subscription or payment required
- captcha: captcha or bot challenge present
- rate-limited: 429 or similar throttling
- forbidden: 401 or 403
- geo-blocked: unavailable due to region or VPN
- robots-restricted: crawler access disallowed
- broken: 404, 5xx, network error, or malformed page
- manual-needed: agent cannot continue; user action required

## Browser probe checklist

For each promising URL, record:

- input URL
- final URL after redirects
- HTTP status if available
- title
- canonical URL
- meta description
- language
- visible text summary
- headings
- key links
- downloadable files
- forms and search boxes
- pagination controls
- tables detected
- JSON-LD or structured data detected
- publication date or update date
- blocker indicators
- screenshot path when captured

If a relevant public URL hits Cloudflare, anti-bot challenge, captcha, 403, 429, geo block, or repeated browser/fetch failure, run `references/anti-bot-fallback.md` once before declaring the source blocked.

## Crawl expansion

Use this priority:

1. links from the user-provided URL
2. canonical docs navigation
3. relevant internal links
4. sitemap URLs
5. RSS or Atom feeds
6. public downloadable files
7. public APIs linked from docs or page content
8. external citations only when needed

## Sitemaps and robots

When crawling a domain:
- request `/robots.txt`
- record disallow rules relevant to the crawler
- look for `Sitemap:` entries
- request sitemap indexes and sitemap files when allowed
- use sitemap URLs for discovery, not as proof of content

## Interaction rules

Allowed interactions:
- click normal links and buttons
- open tabs or accordions
- change filters exposed to normal users
- paginate result lists
- use site search
- sort tables
- download public files

Avoid:
- submitting personal information
- account creation
- payment flows
- captcha solving
- stealth or anti-detection behavior
- high-frequency automated requests

## Extraction priority

Use the most stable source first:

1. public export/download file
2. official public API or documented endpoint
3. structured data embedded in page
4. HTML table
5. main text content
6. browser-rendered DOM after interaction
7. screenshot-backed observation

## Coverage notes

For any crawl or dataset, report:
- seed URLs
- allowed domains
- crawl depth
- pages visited
- pages skipped
- pages blocked
- deduplication rules
- fields extracted
- missing fields
- reasons for missingness

## Politeness defaults

Unless configured otherwise:
- max depth: 2
- max total pages: 100
- max pages per domain: 30
- delay: 1000 ms
- respect robots: true
- stop on repeated 403, 429, captcha, or login walls

Repeated blocking after the bounded chain in `references/anti-bot-fallback.md` means stop and produce `references/blocker-report.md`.
