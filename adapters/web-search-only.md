# Web-Search-Only Adapter

Use this adapter when the agent has no browser or URL fetch tool, or when a quick search-engine query is the fastest path to source discovery. The concrete implementation is `scripts/web_search.mjs` — a zero-dependency Node 18+ script that queries free search engines and returns normalised JSON results.

## When to use

- No browser automation (Playwright, Puppeteer) is available.
- No direct URL fetch tool exists in the agent runtime.
- You need a fast source-discovery pass before committing to a full crawl.
- You want to verify that a URL exists and is indexed before probing it with a heavier tool.

## Script

`scripts/web_search.mjs` — native `fetch` only, no npm dependencies beyond what is in `package.json`.

## Supported engines

### 1. DuckDuckGo (no key required)

Fetches from `https://html.duckduckgo.com/html/?q=<q>` and parses the HTML response. Zero configuration needed.

```bash
node scripts/web_search.mjs --engine duckduckgo --query "site:github.com underthesea"
```

### 2. SearXNG (no key required)

Fetches from a public SearXNG instance JSON endpoint (`/search?q=<q>&format=json`). Privacy-respecting metasearch.

```bash
node scripts/web_search.mjs --engine searxng --query "PRISMA 2020 systematic review"
```

Override the default instance:

```bash
SEARXNG_INSTANCE=https://my-instance.example.com node scripts/web_search.mjs --engine searxng --query "..."
```

### 3. Brave Search (API key required)

Fetches from `https://api.search.brave.com/res/v1/web/search`. Requires `BRAVE_API_KEY` environment variable.

```bash
BRAVE_API_KEY=BSA_xxx node scripts/web_search.mjs --engine brave --query "wikidata SPARQL tutorial"
```

### 4. Google Custom Search Engine (API key required)

Fetches from `https://www.googleapis.com/customsearch/v1`. Requires both `GOOGLE_CSE_KEY` and `GOOGLE_CSE_ID` environment variables.

```bash
GOOGLE_CSE_KEY=AIza... GOOGLE_CSE_ID=abc123 node scripts/web_search.mjs --engine google-cse --query "open data portal CSV"
```

## Fallback chain

When no `--engine` is specified, the script attempts engines in this order:

1. **DuckDuckGo** — always attempted (no key needed)
2. **SearXNG** — always attempted (no key needed)
3. **Brave** — attempted only if `BRAVE_API_KEY` is set
4. **Google CSE** — attempted only if both `GOOGLE_CSE_KEY` and `GOOGLE_CSE_ID` are set

The first engine that returns results wins. Results are **not** merged across engines — every result in the output has the same `source_engine` value.

If all engines fail, the script prints a summary of all failures to stderr and exits non-zero.

```bash
# Uses fallback chain automatically
node scripts/web_search.mjs --query "evidence-based policy evaluation"
```

## Environment variables

| Variable | Required | Used by | Default |
|----------|----------|---------|---------|
| `SEARXNG_INSTANCE` | No | SearXNG engine | `https://searx.be` |
| `BRAVE_API_KEY` | Only for Brave | Brave engine | — |
| `GOOGLE_CSE_KEY` | Only for Google CSE | Google CSE engine | — |
| `GOOGLE_CSE_ID` | Only for Google CSE | Google CSE engine | — |

## Usage examples

### Basic search (fallback chain)

```bash
node scripts/web_search.mjs --query "machine learning fairness survey 2024"
```

### Limit results

```bash
node scripts/web_search.mjs --query "Python packaging PEP 723" --limit 5
```

### Write results to file

```bash
node scripts/web_search.mjs --query "open access journals" --out results.json
```

### npm shortcut

```bash
npm run search:web -- --query "GDPR data portability" --limit 10
```

## Output format

Every result is a JSON object with:

```json
{
  "title": "Page title",
  "url": "https://example.com/page",
  "snippet": "Brief excerpt from the page...",
  "source_engine": "duckduckgo"
}
```

The script outputs a JSON array of these objects to stdout (or to `--out` file).

## Limitations

- In web-search-only mode, the agent cannot verify full page contents. Mark claims as lower confidence when based only on search snippets.
- DuckDuckGo HTML parsing may break if DDG changes their markup.
- SearXNG public instances may be rate-limited or temporarily unavailable.
- Brave and Google CSE have free-tier quotas.

## Required output when using this adapter

Always include in your research output:
- queries attempted
- candidate URLs found
- which engine returned results
- sources that need manual opening for full verification
- confidence limitations due to snippet-only access

## See also

- `references/source-discovery.md` — search engine fallback chain section.
- `references/query-patterns.md` — how to generate effective query fanout.
- `references/tool-adapter-policy.md` — when to use this adapter vs. browser-based tools.
- `adapters/wikidata.md` — for structured entity lookups (complements web search).
- `SKILL.md` — main entry point and decision tree.
