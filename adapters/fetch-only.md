# Fetch-Only Adapter

Use this when URL fetch is available but no browser automation is available.

## Best suited for

- static HTML
- public files
- JSON/XML/CSV endpoints
- documentation pages
- sitemaps and robots

## Limitations

Fetch-only mode may fail for:
- JavaScript-rendered pages
- lazy-loaded content
- content behind buttons, tabs, or filters
- pages requiring browser cookies or client-side navigation

## Workflow

1. fetch the URL
2. record status code, final URL, content type, and headers when available
3. extract title, headings, links, tables, and text
4. discover public files and sitemaps
5. if content is missing due to dynamic rendering, mark browser-needed
6. produce blocker or manual-needed report if required

## Output caveat

Clearly mark content as not browser-rendered.
