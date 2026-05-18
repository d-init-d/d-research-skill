# Data Extraction Toolbox

Concrete extraction recipes for the structured data shapes you actually
encounter on the public web. Each recipe lists:

- **Signature** — how to recognise the shape from a page or response.
- **Extractor** — the least-invasive stable method.
- **Don't** — common over-engineering or bypass attempts to avoid.

For general extraction strategy and decision rules, see
`references/extraction-methods.md`. For the safety boundary on what
counts as legitimate extraction, see
`references/safety-and-access-policy.md`.

## Recipe 1 — HTML `<table>` elements

**Signature**: visible `<table>` tags in DOM, with `<thead>` / `<tbody>`
/ `<tr>` / `<td>` / `<th>` structure.

**Extractor**: `scripts/extract_tables.py`.

```
scripts/extract_tables.py extract --in page.html --out-dir out/
```

Output is one CSV per `<table>`, with `colspan` and `rowspan`
duplicated into the right cells.

For pages where the table is rendered by JavaScript, first dump the DOM
via `scripts/playwright_extract.mjs`, then feed the result into
`extract_tables.py`.

**Don't**: paste the table into an LLM and ask it to "transcribe" — the
deterministic parser is faster, cheaper, and won't hallucinate cells.

## Recipe 2 — JSON-LD in `<script type="application/ld+json">`

**Signature**: `<script type="application/ld+json">{ ... }</script>` in
the page source.

**Extractor**: a tiny shell pipeline.

```
curl -sSfL "$URL" \
  | python3 -c "import json,re,sys,html
text = sys.stdin.read()
for m in re.finditer(r'<script type=\"application/ld\\+json\">(.*?)</script>', text, re.S):
    try:
        obj = json.loads(html.unescape(m.group(1).strip()))
        print(json.dumps(obj, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f'WARN: {e}', file=sys.stderr)"
```

Or pipe through `scripts/playwright_extract.mjs --selector
'script[type=\"application/ld+json\"]'` for pages that ship JSON-LD
only after JS execution.

**Don't**: try to scrape the rendered DOM when the same data is
sitting structured in JSON-LD already. JSON-LD is the canonical source.

## Recipe 3 — Embedded JSON in page-level `<script>` (`__NEXT_DATA__`, `__NUXT__`, dataLayer, …)

**Signature**: SPA frameworks ship initial state as a JSON blob inside
an inline `<script>`. Common keys:

- `__NEXT_DATA__` (Next.js)
- `__NUXT__` (Nuxt)
- `window.__INITIAL_STATE__` (custom)
- `dataLayer = [{ ... }]` (Google Tag Manager)

**Extractor**: regex out the JSON literal, then parse.

```
curl -sSfL "$URL" \
  | python3 -c "import json,re,sys
text = sys.stdin.read()
m = re.search(r'<script id=\"__NEXT_DATA__\" type=\"application/json\">(.*?)</script>', text, re.S)
if m:
    print(m.group(1))"
```

For the harder cases (`window.__INITIAL_STATE__ = { ... };`), prefer
`scripts/playwright_extract.mjs --selector head` and pull the value via
`page.evaluate(() => window.__INITIAL_STATE__)`.

**Don't**: scrape the rendered HTML for fields you can read directly
from the initial-state JSON — you lose precision and pick up render
artefacts.

## Recipe 4 — REST APIs (public, documented)

**Signature**: the site provides an OpenAPI / Swagger doc, or a public
data portal links to `https://api.<domain>/...`.

**Extractor**: `scripts/api_fetch.mjs`.

```
node scripts/api_fetch.mjs \
  --url 'https://api.openalex.org/works?search=playwright&per-page=50' \
  --out data/openalex.jsonl \
  --paginate cursor --cursor-key 'meta.next_cursor' --max-pages 20
```

Log every request to `templates/api-request-log.csv`. Respect
`Retry-After`, `X-RateLimit-Remaining`, and the API's published rate
limits.

**Don't**: hammer the API with concurrent requests to "finish faster".
You will get rate-limited and you may be banned. The skill defaults
explicitly to polite pacing.

## Recipe 5 — GraphQL endpoints (public, documented)

**Signature**: the site exposes a public GraphQL endpoint (often at
`/graphql`) with a schema you can introspect.

**Extractor**: `adapters/graphql.md` walks through the workflow.

**Don't**: use GraphQL introspection on endpoints that have
`__schema { types { name } }` disabled — that is the operator's signal
that the schema is not for public use. Move on.

## Recipe 6 — Sitemaps

**Signature**: `https://<host>/sitemap.xml` or a `Sitemap:` header in
`robots.txt`.

**Extractor**:

```
curl -sSfL "$URL/sitemap.xml" \
  | python3 -c "import sys, xml.etree.ElementTree as ET
ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
root = ET.parse(sys.stdin).getroot()
for url in root.findall('s:url', ns):
    loc = url.findtext('s:loc', namespaces=ns)
    lm = url.findtext('s:lastmod', namespaces=ns) or ''
    print(f'{loc}\t{lm}')"
```

Sitemaps tell you exactly which URLs the operator wants discovered.
Always prefer them over random link-following.

## Recipe 7 — RSS / Atom feeds

**Signature**: `<link rel="alternate" type="application/rss+xml" ...>`
or `application/atom+xml` in the page `<head>`, or a well-known path
like `/feed`, `/rss`, `/atom.xml`.

**Extractor**: parse the XML with `xml.etree.ElementTree` (stdlib).
Capture `title`, `link`, `pubDate`/`updated`, and (when present) the
content / summary.

**Don't**: scrape the index page for items when the feed gives you the
exact same items pre-structured.

## Recipe 8 — OAI-PMH (repositories, libraries, archives)

**Signature**: institutional repositories advertise
`https://<host>/oai/request?verb=Identify` or similar.

**Extractor**:

```
curl -sSfL "$BASE?verb=ListRecords&metadataPrefix=oai_dc"
```

Then pipe through an XML parser. OAI-PMH is **designed** for harvesting
and includes a resumption-token pagination scheme.

**Don't**: crawl the repository's HTML pages when OAI-PMH is offered —
that's the polite path.

## Recipe 9 — PDFs

**Signature**: links ending in `.pdf` or `Content-Type:
application/pdf`.

**Extractor**: `scripts/pdf_extract.py`.

```bash
# Extract plain text from a PDF
python3 scripts/pdf_extract.py text --in document.pdf --out document.txt

# Extract metadata (title, author, page count, creation date)
python3 scripts/pdf_extract.py meta --in document.pdf

# Extract tables to CSV (one CSV per table found)
python3 scripts/pdf_extract.py tables --in document.pdf --out-dir out/
```

For pages where the PDF link is behind JavaScript rendering, first
download the file via `scripts/playwright_extract.mjs`, then feed the
result into `pdf_extract.py`.

When you extract text from a PDF, record the **page number** in the
evidence ledger `quote_or_anchor` field (e.g. "p. 12, paragraph 3") so
the quote can be located again.

**Don't**: paste PDF text into an LLM and ask it to "parse" — the
deterministic extractor is faster, cheaper, and won't hallucinate
structure.

## Recipe 10 — Web archives (Wayback Machine, archive.today)

**Signature**: the original page is dead, but a snapshot exists at
`https://web.archive.org/web/<TIMESTAMP>/<URL>` or
`https://archive.today/<id>`.

**Extractor**: treat the archived snapshot like a normal page. Record
the **archive URL** and **archive timestamp** in the evidence ledger
(both `source_url` and `notes`) so the snapshot remains pinned even if
the live URL changes.

## Common processing after extraction

- **Clean / normalise**: `scripts/data_clean.py clean` strips
  whitespace, normalises empty strings, dedupes within a single CSV.
- **Validate**: `scripts/data_clean.py validate` enforces a schema
  defined in a sidecar JSON spec.
- **Merge**: `scripts/data_clean.py merge` joins multiple CSVs on a
  shared key.
- **Score sources**: `scripts/score_source.py score` applies the
  rubric.
- **Sign the ledger**: `scripts/evidence_ledger.py sign` emits a
  tamper-evident HMAC sidecar.

## Lawful access reminder

Every recipe above assumes the target is **publicly accessible** to
ordinary users. None of these recipes bypass:

- Login walls / authentication
- Captchas / anti-bot
- Paywalls
- Rate limits / `Retry-After`
- `robots.txt` `Disallow` rules on paths you would otherwise crawl

If you hit any of the above, stop and produce a blocker report (see
`references/blocker-report.md`). Do not switch to stealth plugins,
fake user agents, IP rotation, or session-token forging.

## Scanned documents and images (OCR)

When a source is an image file or a scanned PDF where `pdftotext` returns empty text, use `scripts/ocr.py`:

```bash
# Image to text
python scripts/ocr.py text --in scan.png --lang eng

# Scanned PDF (multi-page)
python scripts/ocr.py pdf --in scanned.pdf --out text.txt

# Emit evidence-ledger row from OCR
python scripts/ocr.py to-ledger --in scan.png --url https://example.com/doc --out-row row.csv
```

Requires `tesseract-ocr` system package (optional; soft-fails if missing). See `references/ocr.md`.

## See also

- `references/extraction-methods.md` — extraction strategy
- `references/safety-and-access-policy.md` — what counts as lawful
- `references/api-access-workflow.md` — API workflow details
- `references/large-scale-collection.md` — checkpointing / pacing
- `references/blocker-report.md` — when blocked
- `adapters/playwright.md`, `adapters/graphql.md`, `adapters/fetch-only.md`
