# Network helper SSRF inventory (v3.2.0-rc.3 clean)

Status of public-address validation for outbound HTTP(S) helpers. Arbitrary
user-controlled URL fetchers must validate destinations, bind the TCP
connection to a validated public peer, and revalidate redirects. Fixed official
endpoints may omit DNS pin when TLS is verified, redirects are constrained, and
a written rationale exists.

| Helper | User-controlled URL/host? | Redirects | Credentials | Protection | Resolution |
|--------|---------------------------|-----------|-------------|------------|------------|
| `scripts/_ssrf_helpers.py` + Python callers | Yes for social-post/API URLs; fixed provider URLs elsewhere | Manual, bounded, every hop revalidated | Optional | DNS pin + public IP + shared `_assert_connected_peer`; URL-derived Host (caller Host stripped; IPv6 bracketed); HTTPS downgrade blocked; credential/body-bearing cross-origin redirects rejected before the destination request | **Protected** |
| `scripts/api_fetch.mjs` | Yes (`--url`, Link next, redirects) | Manual, revalidated | Optional | `fetchPublicHttp` connection-bound to validated IP; URL-derived Host (not caller Host) + SNI rules; credential cross-origin hard-fail; response cap enforced while streaming; abnormal status construction fails closed | **Protected** |
| `scripts/lib/ssrf_guards.mjs` | N/A (library) | N/A | N/A | Deterministic public-IP policy shared with Python: IPv4-mapped → embedded IPv4; IPv6 fail-closed outside `2000::/3`; block translation prefixes and GUA special-use (`2001::/23`, `2001:db8::/32`, `2002::/16`, `3fff::/20`); `fetchPublicHttp` pinned connect; Host always from validated URL; SNI only for DNS names; canonical peer membership via `assertConnectedPeer` (immediate + delayed connect); abnormal status → rejected promise; streaming-cap tests | **Protected** |
| `scripts/lib/browser_ssrf.mjs` + `playwright_*.mjs` | Yes (seed / nav / subresource URLs) | Browser follows fulfilled redirects; every hop is re-routed | Session optional | Context route, service workers blocked, HTTP(S) fulfilled through connection-bound `fetchPublicHttp`; WebSocket fail-closed; loopback only through explicit fixture test injection | **Protected (connection-bound / fail-closed)** - not accepted-risk |
| `scripts/wayback.py` | User URL as query only; HTTP connects to `web.archive.org` / SPN fixed hosts | urllib default limited by fixed host | No | Fixed official hosts; TLS default; body bounded | **Accepted-risk (fixed endpoint)** |
| `scripts/citation_resolver.py` | DOI/PMID/arXiv/ISBN to fixed APIs (Crossref, DataCite, PubMed, arXiv, Unpaywall) | Limited | No | Fixed hosts; TLS; timeouts; body bounds | **Accepted-risk (fixed endpoint)** |
| `scripts/citation_export.py` / `citation_render.py` / `citation_graph.py` | Same class as resolver | Limited | No | Fixed academic APIs | **Accepted-risk (fixed endpoint)** |
| `scripts/wikidata.py` | Fixed Wikidata / SPARQL endpoints | Limited | No | Fixed hosts; TLS; timeouts | **Accepted-risk (fixed endpoint)** |
| `scripts/translate.py` | Fixed provider endpoints | Manual, max 5 hops | API key/body | Shared Python pinned transport; same-origin-only private material; cross-origin private redirect and HTTPS downgrade hard-fail | **Protected** |
| `scripts/embed_corpus.py` | Fixed Cohere endpoint | Manual, max 5 hops | API key/body | Shared Python pinned transport; same-origin-only private material; cross-origin private redirect and HTTPS downgrade hard-fail | **Protected** |
| `scripts/web_search.mjs` | Query text; fixed/configured search endpoint | Manual, max 5 hops | Optional | Credentialed cross-origin redirect and HTTPS downgrade hard-fail; public cross-origin headers filtered | **Protected redirect policy; fixed/configured endpoint** |
| `scripts/http_cache.py` / `lib/http_cache.mjs` | N/A (disk cache) | N/A | N/A | No network | N/A |

## Direct HTTP (api_fetch) - connection-bound design

1. Parse and normalize URL (no userinfo; HTTPS default).
2. Resolve A/AAAA (injectable in tests).
3. Reject if any address is loopback/private/link-local/multicast/unspecified/reserved/IPv4-mapped private/metadata.
4. Connect TCP to a validated public IP only (unbracketed).
5. **Strip every caller `Host`/`host`/`HOST` key** and set exactly one HTTP
   `Host` from the validated current URL (RFC-correct brackets/port for IPv6;
   non-default ports retained). Callers cannot rebind virtual hosts after a
   public connect. For TLS: use the original DNS hostname as SNI; **omit SNI
   for IP literals** (WHATWG bracketed IPv6 hostnames are not valid SNI on Node
   18/20/22). Certificate verification stays bound to the connect host IP when
   SNI is omitted.
6. Re-check connected peer via `assertConnectedPeer`: public and in the
   canonicalized validated set (compressed/expanded IPv6 and IPv4-mapped
   equivalence; fail closed on missing, whitespace-padded, bracketed, scoped,
   or otherwise malformed peers). Covers immediate
   connect and delayed `socket.connecting` → `connect`.
7. Re-run the full gate on every redirect hop before following (Host rebound
   from the hop URL).
8. Do not forward credentials cross-origin.
9. Stream the response body and abort on the configured byte cap before buffering.
10. Response/callback construction failures (including nonstandard statuses such
    as 600 that `Response` rejects) settle as promise rejection after safe
    destroy/drain — never as an uncaught exception.
11. Null-body 204/205/304 responses explicitly drain the underlying message so
    the connection is not stranded in the busy agent pool. All HEAD/204/205/304
    connections are retired: Node does not expose post-header bytes for
    HEAD/204/304, while observable 205 bytes are drained and capped first.
    `HEAD`/`304` representation `Content-Length` metadata is not miscounted as
    received body bytes.
12. Abort listeners are released on every terminal response/rejection path;
    abort after headers still cancels an active body stream.

### IPv6 public-destination policy (Node + Python)

Shared deterministic tables (not CPython `ipaddress.is_global`, which drifts
across 3.10–3.12). Registry reference: IANA IPv6 Special-Purpose Address
Registry, last updated **2025-10-09**.

1. **IPv4-mapped** `::ffff:0:0/96` → classify the embedded IPv4 first
   (compressed, hextet, and expanded forms).
2. **Fail closed** for any IPv6 address outside global-unicast envelope
   `2000::/3` (loopback, ULA, link-local, multicast, SRv6 `5f00::/16`, dummy
   `100:0:0:1::/64`, discard `100::/64`, deprecated site-local `fec0::/10`,
   IPv4-compatible `::a.b.c.d`, unallocated space such as `4000::` / `8000::`).
3. **Translation always blocked** even when IANA marks a prefix globally
   reachable, because encoded private IPv4 is an SSRF risk:
   `64:ff9b::/96`, `64:ff9b:1::/48`, `2002::/16` (6to4).
4. **Inside `2000::/3`**, block `2001::/23` (entire IETF Protocol Assignments
   parent), `2001:db8::/32`, `2002::/16`, `3fff::/20`.
5. **Policy choice on `2001::/23` exceptions:** IANA lists more-specific
   globally reachable assignments under the parent (PCP/TURN/DNS-SD anycast,
   AMT, AS112-v6, ORCHIDv2, DETs). The skill deliberately does not allowlist
   them: fail-closed treatment of the parent avoids CPython 3.10–3.12 table
   drift and is conservative for public web research. Normal public unicast
   (e.g. Google/Cloudflare DNS, `2000::/3` outside the blocked nets) remains
   allowed.

Tests: `node scripts/lib/ssrf_guards.mjs --self-test` (HTTPS SNI + URL-derived
Host capture for DNS/IPv4/IPv6 literals, hostile Host override stripping,
immediate and delayed connect peer validation with canonical IPv6/IPv4-mapped
membership, abnormal status 600 rejection without crash, raw-TCP
HEAD/204/304 hidden-byte connection retirement, malformed `::`
fail-closed, rebinding, mixed DNS, streaming cap, full IPv6 matrix);
`python scripts/_ssrf_helpers.py` (URL-derived Host with bracketed IPv6,
shared `_assert_connected_peer` via production and test seam, wrong-arity /
private / mismatched peers, response limits); `api_fetch.mjs --self-test`.

## Python provider requests - connection-bound redirect design

- **Helper:** `public_urlopen_with_redirects` in `scripts/_ssrf_helpers.py`, used by translation and Cohere embedding calls.
- **Per-hop policy:** production hops allow HTTPS only, resolve and reject non-public destinations, connect to a validated address, set URL-derived Host (caller Host stripped; IPv6 bracketed), preserve SNI for DNS names, and require the connected peer via shared `_assert_connected_peer` (including IPv4-mapped IPv6 normalization) to belong to the DNS-validated set before TLS. The `_TEST_PINNED_TRANSPORT` seam must supply `peer_ip` and cannot bypass that assertion.
- **Redirect policy:** at most five hops; URL userinfo, unsupported schemes, and HTTPS-to-HTTP downgrade are rejected. Request bodies, credential-like query parameters, and non-public headers may remain only on the same origin. A cross-origin public GET/HEAD may continue with an allowlisted header subset.
- **Tests:** `python scripts/_ssrf_helpers.py`, `python scripts/translate.py self-test`, and `python scripts/embed_corpus.py self-test` cover same-origin credential retention, zero-request cross-origin denial, public redirects, and loop bounds.

## Browser arbitrary URL - fail-closed (not accepted-risk)

- **Helpers:** `browser_ssrf.mjs` used by `playwright_probe.mjs`, `playwright_extract.mjs`, `playwright_crawl.mjs`.
- **Policy:** Private destinations are denied with structured blockers; private nav/subresource/fetch/popup/WebSocket attempts are zero-request denials.
- **Connection binding:** Allowed HTTP(S) browser requests are fulfilled through `fetchPublicHttp`, which validates DNS, connects to the validated peer, preserves Host/SNI, and re-checks the connected peer before streaming the response back to Playwright.
- **Route scope:** Guards are installed on the browser context, not only the page, and contexts use `serviceWorkers: 'block'` so service-worker interception cannot bypass routing. WebSockets are closed instead of proxied because Playwright's WebSocket server bridge does not provide D Research's pinned-peer guarantee.
- **Fixture loopback:** Browser helpers accept loopback only through the hidden `--allow-loopback-fixture` test hook used by `browser_smoke.mjs`; `D_RESEARCH_SSRF_ALLOW_LOOPBACK` is not read by `browser_ssrf.mjs`.
- **Tests:** `node scripts/lib/browser_ssrf.mjs --self-test`; `npm run browser:smoke` covers subresource/fetch/popup/WebSocket zero-request behavior, service-worker blocking, TLS default failure/opt-in, and resource-limit blockers.

## Accepted-risk details (fixed endpoints only)

### Fixed official academic and archive endpoints

- **Helpers:** wayback, citation_*, and wikidata. Translation, embedding, and web-search helpers now enforce explicit bounded redirect policies as documented above.
- **Reason:** Destination host is not taken from an arbitrary user URL; user input is an identifier or query parameter on a first-party/official base URL.
- **Remaining attack assumption:** Compromise or malicious response content from the official provider; not classic SSRF to link-local metadata via user URL.
- **Protections:** TLS verification on, timeouts, response body caps where applicable, secret redaction, no credential forwarding on cross-origin pagination (api_fetch pattern where relevant).

## Not accepted-risk

- Any helper that opens an arbitrary user-supplied URL as the TCP destination without public-address validation and connection binding (social + api_fetch + browser seeds).
- Browser arbitrary seeds are no longer documented as accepted-risk.
