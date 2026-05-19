# Shared HTTP Cache

A content-addressed HTTP cache shared across Python and Node scripts. Reduces repeated requests during development and respects API rate limits.

## When to Use

- Iterating on a script during development (avoid hitting public APIs repeatedly)
- Reproducible offline replay of previous research runs
- Batch operations where the same URL is fetched multiple times
- Politeness: cached responses don't count toward rate limits

## Configuration

Cache is **opt-in** via environment variable:

```bash
export D_RESEARCH_HTTP_CACHE_PATH=~/.cache/d-research-skill
```

When this variable is unset, all scripts behave as before — no caching, no disk writes. Cache is never enabled by default.

## Cache Layout

```
<cache-dir>/
  entries/
    <sha256(method + url + request_key + body_key)>.json   # metadata
    <sha256(method + url + request_key + body_key)>.body   # response body
```

Both Python (`scripts/http_cache.py`) and Node (`scripts/lib/http_cache.mjs`) use this exact layout and cache key recipe, so cache entries are interchangeable across runtimes.

## Cache Key

The cache key is `SHA256(method + "\n" + url + "\n" + request_key + "\n" + body_key)`, where:

- **method** — uppercased HTTP method (e.g., `GET`).
- **url** — the **final URL** including all query parameters. `scripts/api_fetch.mjs` applies `--params` to the URL **before** any cache lookup so a parameter change always misses the cache.
- **request_key** — a canonical, sorted, lowercased subset of request headers that affect the response. Only these names are included:

  ```
  authorization
  cookie
  x-api-key
  api-key
  accept
  accept-language
  ```

  Any other request header (User-Agent, Content-Type, etc.) does **not** affect the cache key.
- **body_key** — optional body material for POST or other body-bearing requests.

This means:

- A request with `Authorization: Bearer A` and a request with `Authorization: Bearer B` to the same URL produce **different** cache entries.
- A request with no `Authorization` header to the same URL produces a **third** entry.
- A no-auth lookup will **never** replay a Bearer-A response.

## CLI

```bash
# Show cache statistics
python scripts/http_cache.py stats

# Compute cache key for a URL (no headers)
python scripts/http_cache.py get-key --method GET --url https://example.com/api

# Compute cache key with auth-affecting headers
python scripts/http_cache.py get-key \
  --method GET --url https://example.com/api \
  --header "Authorization: Bearer abc"

# Purge expired entries (default: > 7 days old)
python scripts/http_cache.py purge

# Purge all entries
python scripts/http_cache.py purge --all

# Purge entries older than 1 day
python scripts/http_cache.py purge --max-age 86400
```

## Default TTL

Entries expire after **7 days** by default. Override per-call with `max_age` (Python) / `maxAge` (Node).

## Privacy and Safety

- Cache stores response bodies on disk in plaintext — do not point cache at sensitive locations.
- Request headers (`Authorization`, `Cookie`, `X-API-Key`, `API-Key`) are **hashed into the cache key but never stored on disk**. Cache metadata only contains response headers.
- Cache **never bypasses authentication or access controls** — it only stores responses the script was already allowed to fetch.
- Set `D_RESEARCH_HTTP_CACHE_PATH` to a path inside `.gitignore` — never commit cache content.
- Cache failures are non-fatal: scripts proceed with a live request when the cache cannot be read or written.

## Integration

Scripts that respect the cache when `D_RESEARCH_HTTP_CACHE_PATH` is set:

- `scripts/api_fetch.mjs` — Node API pagination (GET responses)
- `scripts/wayback.py` — Wayback Machine CDX, Availability, snapshot fetches
- `scripts/wikidata.py` — Wikidata `wbsearchentities` and `wbgetentities` (GET only; SPARQL POSTs are not cached)
- `scripts/citation_resolver.py` — CrossRef, Datacite, NCBI, arXiv, Open Library, Unpaywall lookups
- `scripts/citation_graph.py` — OpenAlex work, citation, and reference fetches

All Python integrations cache GET responses only and skip caching when the upstream returns a non-2xx status. Cache failures are silently ignored so they never break a research run.

Other scripts can opt in by importing the helper:

```python
# Python
import http_cache
request_headers = {"User-Agent": "my-tool/1.0", "Authorization": "Bearer abc"}
if http_cache.get_cache_path():
    cached = http_cache.get("GET", url, request_headers=request_headers)
    if cached:
        return cached["body"]
    # ... fetch ...
    http_cache.put("GET", url, status, response_headers, body,
                   request_headers=request_headers)
```

```javascript
// Node
import { getCachePath, getCached, putCache } from './lib/http_cache.mjs';
if (getCachePath()) {
  const requestHeaders = { Authorization: 'Bearer abc' };
  const hit = getCached('GET', url, { requestHeaders });
  if (hit) return hit.body;
  // ... fetch ...
  putCache('GET', url, status, responseHeaders, body, { requestHeaders });
}
```

## Self-tests

Each script's `self-test` subcommand isolates `D_RESEARCH_HTTP_CACHE_PATH` so a stale local cache cannot mask the mocked HTTP layer.

```bash
python scripts/http_cache.py self-test
node scripts/lib/http_cache.mjs --self-test
node scripts/api_fetch.mjs --self-test
python scripts/wayback.py self-test
python scripts/wikidata.py self-test
python scripts/citation_resolver.py self-test
python scripts/citation_graph.py self-test
```

## See Also

- `references/large-scale-collection.md` — when politeness/rate limiting matters
- `references/safety-and-access-policy.md` — what cache must never do
- `scripts/http_cache.py` / `scripts/lib/http_cache.mjs` — implementations
