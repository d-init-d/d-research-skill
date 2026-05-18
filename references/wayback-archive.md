# Wayback Machine Archive

Use this file when you need to retrieve, compare, or archive web page
snapshots via the Internet Archive's Wayback Machine. The script
`scripts/wayback.py` wraps the CDX API, Availability API, and Save Page
Now endpoint into a single CLI with subcommands suitable for research
archival workflows.

## CDX API reference

The CDX (Capture/Digital Index) API lists all archived snapshots of a
given URL.

**Endpoint:** `http://web.archive.org/cdx/search/cdx`

**Key parameters:**

| Parameter | Description |
|---|---|
| `url` | Target URL to search (required) |
| `output` | Response format — `json` recommended |
| `from` | Start date filter (YYYYMMDD) |
| `to` | End date filter (YYYYMMDD) |
| `limit` | Maximum number of results |

**Usage via script:**

```bash
python scripts/wayback.py lookup \
  --url "https://example.com/page" \
  --from 20200101 \
  --to 20231231 \
  --limit 50
```

**Response format (output=json):** A JSON array of arrays where the
first row is the header (`urlkey`, `timestamp`, `original`, `mimetype`,
`statuscode`, `digest`, `length`) and subsequent rows are snapshot
records.

## Availability API

The Availability API finds the nearest snapshot to a given timestamp.

**Endpoint:** `http://archive.org/wayback/available`

**Parameters:** `url` (required), `timestamp` (YYYYMMDD, required).

**Usage via script:**

```bash
python scripts/wayback.py nearest \
  --url "https://example.com/page" \
  --timestamp 20220601
```

Returns the snapshot URL and its actual timestamp. If no snapshot exists
near the requested date, the script prints an informative message and
exits 0.

## Save Page Now etiquette

The Save Page Now endpoint requests a fresh snapshot of a URL.

**Endpoint:** `https://web.archive.org/save/<URL>`

**Usage via script:**

```bash
python scripts/wayback.py save --url "https://example.com/page"
```

**Rate limiting:** The Internet Archive informally limits Save Page Now
to approximately 15 requests per minute. The script enforces exponential
backoff on HTTP 429 responses (2^attempt seconds, up to 3 retries).

**Best practices:**

- Do not batch-save hundreds of URLs without pausing between requests.
- Use `lookup` or `nearest` first to check if a recent snapshot already
  exists before requesting a new save.
- If you receive repeated 429 responses after retries, stop and wait at
  least 5 minutes before trying again.

## Diff workflow

Compare content between two archived timestamps to detect changes over
time.

```bash
python scripts/wayback.py diff \
  --url "https://example.com/page" \
  --t1 20200101 \
  --t2 20230101
```

The diff subcommand:

1. Queries the Availability API for the nearest snapshot to each
   timestamp.
2. Fetches both snapshot pages.
3. Computes SHA-256 hashes of the content.
4. Reports whether the content is identical or changed.

Use this for monitoring content drift, verifying that a source has not
been altered, or detecting when a page was last updated.

## Integration with anti-bot fallback chain

This script is what Step 2 of `references/anti-bot-fallback.md` calls
when a tier-1 source is blocked. The fallback chain runs:

1. Canonical API or raw/static form (same source)
2. **Public web archive** — use `scripts/wayback.py nearest` to find an
   archived copy
3. Search-engine cache or snippet
4. Fetch-only / no-JS retrieval
5. Blocker report

When the fallback chain reaches Step 2, invoke:

```bash
python scripts/wayback.py nearest \
  --url "<blocked-url>" \
  --timestamp "$(date +%Y%m%d)"
```

If a snapshot is found, record it in the evidence ledger with the
archive URL as `source_url` and the archive timestamp in `notes`. If no
snapshot exists, proceed to Step 3.

## Self-test

Run offline validation with a local mock HTTP server (no network
requests):

```bash
python scripts/wayback.py self-test
```

Exercises lookup, nearest, and diff against mock endpoints. Exits 0 on
success.

## See also

- `references/anti-bot-fallback.md` — bounded fallback chain for blocked sources
- `references/monitoring-change-detection.md` — change detection patterns
- `references/data-extraction-toolbox.md` — full extraction recipe catalog
- `scripts/wayback.py` — the script itself
