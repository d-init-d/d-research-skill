# Network helper SSRF inventory (v3.2.0-rc.1 clean)

Status of public-address validation for outbound HTTP(S) helpers. Arbitrary
user-controlled URL fetchers must validate destinations, bind the TCP
connection to a validated public peer, and revalidate redirects. Fixed official
endpoints may omit DNS pin when TLS is verified, redirects are constrained, and
a written rationale exists.

| Helper | User-controlled URL/host? | Redirects | Credentials | Protection | Resolution |
|--------|---------------------------|-----------|-------------|------------|------------|
| `scripts/_ssrf_helpers.py` + `social_snapshot.py` | Yes (post/API URL) | Denied | No | DNS pin + public IP + streaming body cap + peer re-check | **Protected** |
| `scripts/api_fetch.mjs` | Yes (`--url`, Link next, redirects) | Manual, revalidated | Optional | `fetchPublicHttp` connection-bound to validated IP; Host/SNI preserved; credential cross-origin hard-fail; response cap enforced while streaming | **Protected** |
| `scripts/lib/ssrf_guards.mjs` | N/A (library) | N/A | N/A | Public IP / blocked host / DNS check + `fetchPublicHttp` pinned connect + peer mismatch and streaming-cap tests | **Protected** |
| `scripts/lib/browser_ssrf.mjs` + `playwright_*.mjs` | Yes (seed / nav / subresource URLs) | Browser follows fulfilled redirects; every hop is re-routed | Session optional | Context route, service workers blocked, HTTP(S) fulfilled through connection-bound `fetchPublicHttp`; WebSocket fail-closed; loopback only through explicit fixture test injection | **Protected (connection-bound / fail-closed)** - not accepted-risk |
| `scripts/wayback.py` | User URL as query only; HTTP connects to `web.archive.org` / SPN fixed hosts | urllib default limited by fixed host | No | Fixed official hosts; TLS default; body bounded | **Accepted-risk (fixed endpoint)** |
| `scripts/citation_resolver.py` | DOI/PMID/arXiv/ISBN to fixed APIs (Crossref, DataCite, PubMed, arXiv, Unpaywall) | Limited | No | Fixed hosts; TLS; timeouts; body bounds | **Accepted-risk (fixed endpoint)** |
| `scripts/citation_export.py` / `citation_render.py` / `citation_graph.py` | Same class as resolver | Limited | No | Fixed academic APIs | **Accepted-risk (fixed endpoint)** |
| `scripts/wikidata.py` | Fixed Wikidata / SPARQL endpoints | Limited | No | Fixed hosts; TLS; timeouts | **Accepted-risk (fixed endpoint)** |
| `scripts/translate.py` | Fixed provider endpoints or user-supplied key against known API base | Limited | API key | Fixed API bases; TLS | **Accepted-risk (fixed endpoint)** |
| `scripts/embed_corpus.py` | Embedding API base from config / known host | Limited | Optional | Fixed-style endpoint; TLS | **Accepted-risk (fixed endpoint)** |
| `scripts/web_search.mjs` | Query text; host from configured search endpoint | Limited | Optional | Configured endpoint, not arbitrary URL open | **Accepted-risk (fixed/configured endpoint)** |
| `scripts/http_cache.py` / `lib/http_cache.mjs` | N/A (disk cache) | N/A | N/A | No network | N/A |

## Direct HTTP (api_fetch) - connection-bound design

1. Parse and normalize URL (no userinfo; HTTPS default).
2. Resolve A/AAAA (injectable in tests).
3. Reject if any address is loopback/private/link-local/multicast/unspecified/reserved/IPv4-mapped private/metadata.
4. Connect TCP to a validated public IP only.
5. Preserve original hostname for Host header, SNI, and certificate verification.
6. Re-check connected peer is public and in the validated set (blocks rebinding / peer mismatch).
7. Re-run the full gate on every redirect hop before following.
8. Do not forward credentials cross-origin.
9. Stream the response body and abort on the configured byte cap before buffering.

Tests: `node scripts/lib/ssrf_guards.mjs --self-test` (rebinding, mixed DNS, peer mismatch, streaming cap); `api_fetch.mjs --self-test`.

## Browser arbitrary URL - fail-closed (not accepted-risk)

- **Helpers:** `browser_ssrf.mjs` used by `playwright_probe.mjs`, `playwright_extract.mjs`, `playwright_crawl.mjs`.
- **Policy:** Private destinations are denied with structured blockers; private nav/subresource/fetch/popup/WebSocket attempts are zero-request denials.
- **Connection binding:** Allowed HTTP(S) browser requests are fulfilled through `fetchPublicHttp`, which validates DNS, connects to the validated peer, preserves Host/SNI, and re-checks the connected peer before streaming the response back to Playwright.
- **Route scope:** Guards are installed on the browser context, not only the page, and contexts use `serviceWorkers: 'block'` so service-worker interception cannot bypass routing. WebSockets are closed instead of proxied because Playwright's WebSocket server bridge does not provide D Research's pinned-peer guarantee.
- **Fixture loopback:** Browser helpers accept loopback only through the hidden `--allow-loopback-fixture` test hook used by `browser_smoke.mjs`; `D_RESEARCH_SSRF_ALLOW_LOOPBACK` is not read by `browser_ssrf.mjs`.
- **Tests:** `node scripts/lib/browser_ssrf.mjs --self-test`; `npm run browser:smoke` covers subresource/fetch/popup/WebSocket zero-request behavior, service-worker blocking, TLS default failure/opt-in, and resource-limit blockers.

## Accepted-risk details (fixed endpoints only)

### Fixed official academic and archive endpoints

- **Helpers:** wayback, citation_*, wikidata, translate, embed_corpus, web_search.
- **Reason:** Destination host is not taken from an arbitrary user URL; user input is an identifier or query parameter on a first-party/official base URL.
- **Remaining attack assumption:** Compromise or malicious response content from the official provider; not classic SSRF to link-local metadata via user URL.
- **Protections:** TLS verification on, timeouts, response body caps where applicable, secret redaction, no credential forwarding on cross-origin pagination (api_fetch pattern where relevant).

## Not accepted-risk

- Any helper that opens an arbitrary user-supplied URL as the TCP destination without public-address validation and connection binding (social + api_fetch + browser seeds).
- Browser arbitrary seeds are no longer documented as accepted-risk.
