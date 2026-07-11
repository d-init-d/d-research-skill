---
example_status: illustrative
---

# Example: bounded large-scale documentation crawl

The user asks for a “complete crawl.” The agent translates that into a declared,
auditable boundary. This example uses `docs.example.com` as a non-live fixture
domain and makes no claim that pages were fetched.

## Intake and completion boundary

- Shape: `dataset_collection` + `large_scale_collection`
- Unit: one canonical public documentation URL
- Allowed origins: the seed origin only unless explicitly approved
- Discovery basins: seed links, declared sitemaps, and public API/static files
- Safety: read-only, robots respected, no login/captcha/rate-limit bypass
- Completion: all discovered in-scope URLs reached a terminal recorded state,
  and the coverage/recall gate found no unresolved discovery basin

If those conditions do not hold, report bounded or partial coverage instead of
“complete.”

## Pilot configuration

```json
{
  "seed": "https://docs.example.com/",
  "allowed_origins": ["https://docs.example.com"],
  "max_depth": 3,
  "max_pages_per_domain": 100,
  "max_total_pages": 100,
  "delay_ms": 1000,
  "respect_robots": true,
  "checkpoint_every_n": 25
}
```

These are pilot caps, not evidence about site size. The crawler user-agent is
the canonical `DResearchBot` value used by the browser helpers. Disabling
robots is a policy hard failure.

## Crawl sequence

1. Probe the seed and fetch `/robots.txt` with the crawler user-agent.
2. Apply status semantics: 404/410 means no rules; 401/403 disallows; 429/5xx
   or network failure stops the domain as unknown/rate-limited.
3. Discover sitemap URLs and seed links without requesting denied targets.
4. Canonicalize and deduplicate URLs before queue insertion.
5. Crawl with adaptive delay, per-request timeout, and body/page caps.
6. Check robots before every redirect destination; denied destinations must
   receive zero page requests.
7. Write a checkpoint atomically before advancing the committed frontier.
8. Record blocked, failed, skipped, duplicate, and successful URLs as terminal
   states; never silently omit them.

Example pilot command:

```bash
node scripts/playwright_crawl.mjs \
  --seed "https://docs.example.com/" \
  --maxDepth 3 \
  --maxPages 100 \
  --delayMs 1000 \
  --outDir research-output/crawl
```

## Canonical outputs

`url-manifest.csv`:

```csv
url,canonical_url,discovered_from,discovery_method,depth,http_status,robots_status,access_status,content_type,content_hash,date_accessed,terminal_state,blocker_reason
```

`links.csv`:

```csv
source_url,target_url,target_origin,link_type,in_scope,reason
```

Also produce:

- `checkpoint.json` with queue/frontier position and committed counters;
- `api-request-log.csv` using `templates/api-request-log.csv`;
- `data-dictionary.csv` using `templates/data-dictionary.csv`;
- `evidence-ledger.csv` using `templates/evidence-ledger.csv` (canonical
  23-column header); and
- `coverage-report.md` generated from the manifest.

Page content can be stored under `pages/` using a stable hash-based filename;
the manifest is the authoritative URL-to-file mapping.

## Coverage arithmetic

Derive all counts from `url-manifest.csv`:

```text
discovered_unique = count(distinct canonical_url)
terminal_total = success + blocked + failed + skipped
coverage_ratio = terminal_total / discovered_unique
```

The equality `terminal_total = discovered_unique` proves only that every known
URL has a recorded terminal state. It does not prove the discovery process
found every page. Sitemap/seed/frontier saturation and explicit gaps remain
part of the coverage gate.

## Blockers and release wording

Robots denials, 403/429/captcha/login walls, repeated server failures, and
resource caps are blocker/process rows. Do not recommend manual bypass. The
final summary reports source basins reached, terminal-state counts, denied
paths, failed requests, cap-triggered stops, and unresolved discovery gaps.

Acceptable wording: “The crawl recorded terminal states for every URL
discovered within the declared seed/sitemap/link boundary.”

## Verification

```bash
node scripts/playwright_crawl.mjs --self-test
python scripts/resource_limits.py self-test
python scripts/evidence_ledger.py validate --file evidence-ledger.csv
```

See `references/large-scale-collection.md`,
`references/browser-first-crawl.md`, and `references/execution-gates.md`.
