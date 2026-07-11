# Network helper SSRF inventory (v3.2.0-rc.1)

Status of public-address validation for outbound HTTP(S) helpers. Arbitrary
user-controlled URL fetchers must validate destinations and revalidate
redirects. Fixed official endpoints may omit DNS pin when TLS is verified,
redirects are constrained, and a written rationale exists.

| Helper | User-controlled URL/host? | Redirects | Credentials | Protection | Resolution |
|--------|---------------------------|-----------|-------------|------------|------------|
| `scripts/_ssrf_helpers.py` + `social_snapshot.py` | Yes (post/API URL) | Denied | No | DNS pin + public IP + streaming body cap | **Protected** (F-06) |
| `scripts/api_fetch.mjs` | Yes (`--url`, Link next, redirects) | Manual, revalidated | Optional | `lib/ssrf_guards.mjs` on initial URL + every hop; credential cross-origin hard-fail | **Protected** (L-01) |
| `scripts/lib/ssrf_guards.mjs` | N/A (library) | N/A | N/A | Public IP / blocked host / DNS check | **Protected** |
| `scripts/wayback.py` | User URL as **query** only; HTTP connects to `web.archive.org` / SPN fixed hosts | urllib default limited by fixed host | No | Fixed official hosts; TLS default; body bounded | **Accepted-risk (fixed endpoint)** |
| `scripts/citation_resolver.py` | DOI/PMID/arXiv/ISBN → fixed APIs (Crossref, DataCite, PubMed, arXiv, Unpaywall) | Limited | No | Fixed hosts; TLS; timeouts; body bounds | **Accepted-risk (fixed endpoint)** |
| `scripts/citation_export.py` / `citation_render.py` / `citation_graph.py` | Same class as resolver | Limited | No | Fixed academic APIs | **Accepted-risk (fixed endpoint)** |
| `scripts/wikidata.py` | Fixed Wikidata / SPARQL endpoints | Limited | No | Fixed hosts; TLS; timeouts | **Accepted-risk (fixed endpoint)** |
| `scripts/translate.py` | Fixed provider endpoints or user-supplied key against known API base | Limited | API key | Fixed API bases; TLS | **Accepted-risk (fixed endpoint)** |
| `scripts/embed_corpus.py` | Embedding API base from config / known host | Limited | Optional | Fixed-style endpoint; TLS | **Accepted-risk (fixed endpoint)** |
| `scripts/web_search.mjs` | Query text; host from configured search endpoint | Limited | Optional | Configured endpoint, not arbitrary URL open | **Accepted-risk (fixed/configured endpoint)** |
| `scripts/playwright_crawl.mjs` / browser adapters | Yes (seed URLs) | Browser navigation | Session optional | Robots, TLS verify default, timeouts; **not** DNS-pinned fetch | **Accepted-risk (browser automation)** — agent must not seed internal targets; remaining assumption: operator-controlled seeds in research workflow, not untrusted open redirect chains without review |
| `scripts/http_cache.py` / `lib/http_cache.mjs` | N/A (disk cache) | N/A | N/A | No network | N/A |

## Accepted-risk details (fixed / browser)

### Fixed official academic & archive endpoints

- **Helpers:** wayback, citation_*, wikidata, translate, embed_corpus, web_search.
- **Reason:** Destination host is not taken from an arbitrary user URL; user input is an identifier or query parameter on a first-party/official base URL.
- **Remaining attack assumption:** Compromise or malicious response content from the official provider; not classic SSRF to link-local metadata via user URL.
- **Protections:** TLS verification on, timeouts, response body caps where applicable, secret redaction, no credential forwarding on cross-origin pagination (api_fetch pattern where relevant).
- **Tests:** Offline self-tests with mocked hosts; contract checks for HTTPS base URLs where enforced.

### Browser automation seeds

- **Helpers:** playwright_crawl / browser smoke paths.
- **Reason:** Purpose is intentional navigation of public research seeds under robots and TLS policy; full DNS pin is not expressible as a single `urlopen` pin.
- **Remaining attack assumption:** Malicious seed list pointing at internal hosts if an agent ignores intake policy.
- **Protections:** safety policy docs, robots respect, TLS verify default, no captcha/stealth bypass, timeouts.
- **Tests:** `browser_smoke.mjs` local fixture; acceptance cases for robots redirect.

## Not accepted-risk

- Any helper that opens an **arbitrary user-supplied URL** as the TCP destination without public-address validation (social + api_fetch are required to stay protected).
