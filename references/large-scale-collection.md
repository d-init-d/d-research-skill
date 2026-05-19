# Large-Scale Data Collection

Reference guide for collecting >100 pages or records efficiently, reliably, and at scale.

## When to Use

Large-scale collection is appropriate when you need to:

- Scrape 100+ pages or records from a single source or multiple sources
- Gather comprehensive datasets for analysis (e.g., product catalogs, job listings, academic papers)
- Build datasets that will be updated periodically
- Extract data across multiple domains with different rate limits and requirements

If you only need <50 items and they can be fetched in minutes, use targeted fetching instead.

## Principles

### Incremental Over Full Re-crawl

Always prefer incremental collection over re-scraping everything. Only collect what you need:

- Use checkpoints to resume from where you left off
- Collect new records only if comparing timestamps or IDs
- Re-scrape only changed/updated records rather than starting over

### Checkpoint Over Hope

Never rely on completing a large collection in one run. Save state frequently:

- Persist progress after every batch
- Track visited URLs, queue state, and partial data
- Resume automatically without data loss

### Adaptive Delay Over Fixed

Rate limits must respond to server behavior:

- Start conservative, then adjust based on response quality
- Slow down when servers show stress (slow responses, 429s)
- Speed up only when behavior confirms stability
- Never use a static delay for unknown servers

### Quality Sample Over Incomplete Exhaustive

A complete but slightly smaller dataset beats a partial full dataset:

- Skip truly blocked pages rather than failing entirely
- Prioritize successful fetches over retries
- Capture what works rather than hammering what doesn't

## Checkpointing

Checkpointing prevents data loss and enables reliable resumption.

### Checkpoint Structure

Save checkpoint to `research-output/checkpoint.json`:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "records_collected": 847,
  "visited": ["url1", "url2", ...],
  "queue": ["next_url1", "next_url2", ...],
  "partial_data": [...],
  "stats": {
    "success": 820,
    "failed": 27,
    "blocked": 15
  }
}
```

### When to Checkpoint

- Every 50 records collected
- At minimum, every 5 minutes during collection
- Before any pause or delay
- After processing each batch

### Resume Process

1. Read `research-output/checkpoint.json`
2. Load visited URLs set
3. Restore remaining queue
4. Skip any URLs already in visited set
5. Continue from queue position

### Checkpoint Validation

On resume, validate checkpoint integrity:

- Verify JSON is valid and parseable
- Confirm visited list is deduplicated
- Validate queue URLs are still accessible (check for redirects)

## Adaptive Rate Limiting

For repeated runs during development, enable the shared HTTP cache to avoid hitting public APIs repeatedly:

```bash
export D_RESEARCH_HTTP_CACHE_PATH=~/.cache/d-research-skill
```

Cached responses don't count toward rate limits. See `references/http-cache.md`. After a large collection, run near-duplicate detection to consolidate the evidence ledger:

```bash
python scripts/dedup_near.py ledger --in evidence-ledger.csv --out duplicates.csv
```

See `references/deduplication.md` for the SimHash workflow.

Rate limits must adapt to server behavior and response quality.

### Initial Delay

Start at the configured base delay (default: 1000ms). This gives servers time to respond without overwhelming them.

### Response-Based Adjustment

Monitor response times and adjust accordingly:

| Condition | Action |
|-----------|--------|
| Response time > 2x base delay | Increase delay by 50% |
| Response time stable for 100 requests | Decrease delay by 10% |
| Hit minimum floor (100ms) | Stop decreasing |
| Response time degrades | Increase delay again |

### Error Handling

On HTTP 429 (rate limited):

```
Attempt 1: wait 2s, retry
Attempt 2: wait 4s, retry
Attempt 3: wait 8s, retry
Attempt 4: wait 16s, retry
Attempt 5: stop, log as blocked, continue
```

On 5xx errors (server errors):

- Wait 2s, retry up to 3 times
- If persistent, reduce rate and continue
- If still failing, mark as blocked and move on

### Event Logging

Log all rate limit events:

```
[10:30:15] Rate limit event: increased delay to 1500ms (response 2100ms)
[10:32:45] Rate limit event: 429 received, waiting 4s
[10:45:00] Rate limit event: decreased delay to 900ms (stable for 100)
```

## Batch Processing

Break large collections into manageable batches to prevent memory issues and enable progress tracking.

### Batch Size

- Optimal batch size: ~100 records per batch
- Process batch completely before starting next
- Validate each batch before proceeding

### Batch Workflow

```
BATCH 1:
  - Collect 100 records
  - Validate format and completeness
  - Save to partial-output/batch1.json
  - Checkpoint

BATCH 2:
  - Load checkpoint, resume queue
  - Collect next 100 records
  - Validate
  - Merge with batch1

... continue until complete

FINAL:
  - Merge all batch files
  - Deduplicate
  - Generate final dataset
```

### Parallel Batches

For multiple independent domains, process batches in parallel:

- Each domain has its own queue and rate limit
- Process domain A batch 1, domain B batch 1 simultaneously
- Never parallelize within same domain (causes rate limit issues)

## Multi-Domain Strategy

When collecting from multiple domains, manage them independently.

### Domain Separation

- Maintain separate queue for each domain
- Track separate rate limits per domain
- Store domain-specific errors separately

### Round-Robin Processing

Cycle between domains to avoid hammering one server:

```
Domain A: request → Domain B: request → Domain C: request
Domain A: request → Domain B: request → Domain C: request
```

This prevents any single domain from receiving burst traffic.

### Domain Configuration

Allow domain-specific overrides:

```yaml
domains:
  - pattern: "*.gov"
    delay: 2000ms
    max_retries: 5
  - pattern: "api.example.com"
    delay: 500ms
    max_retries: 2
  - pattern: "*"
    delay: 1000ms
    max_retries: 3
```

### Respect Robots.txt

Before multi-domain collection:

- Check robots.txt for each domain
- Respect crawl-delay directives
- Skip disallowed paths entirely

## Error Recovery

Robust error handling keeps collection progressing.

### Retry Strategy

| Error Type | Retry Count | Delay | Action |
|------------|-------------|-------|--------|
| 5xx Server Error | 3 max | 2s, 4s, 8s | Continue if fails |
| Connection Timeout | 3 max | 2s, 4s, 8s | Continue if fails |
| 429 Rate Limited | 4 max | 2s, 4s, 8s, 16s | Stop after 4 |
| 404 Not Found | 0 | - | Log, skip |
| 403 Forbidden | 0 | - | Log as blocked, skip |
| 401 Unauthorized | 0 | - | Log, skip |

### Skipping Strategy

Never let individual failures halt entire collection:

- Log failed URLs with error type and timestamp
- Continue to next URL in queue
- Attempt failed URLs again in final pass if time permits

### Alert Threshold

Trigger alert when error rate exceeds 20%:

```
ALERT: Collection error rate at 23% (47 failed / 200 total)
Last successful: 3 minutes ago
Most common errors: 403 (31), 500 (12), timeout (4)
```

Alert user immediately so they can assess and adjust strategy.

## Coverage Tracking

Track collection progress and coverage throughout the process.

### Coverage Metrics

Maintain real-time metrics:

```
Expected Total: 5,000 (if known from sitemap/search)
Collected So Far: 2,847
  - Successful: 2,712
  - Blocked: 89
  - Failed: 46
Remaining Estimate: ~2,150
Coverage: 56.9%
```

### Freshness Tracking

Track how recent the collected data is:

```
Freshest record: 2024-01-15T10:28:00Z (2 minutes ago)
Oldest record: 2024-01-10T08:15:00Z (5 days ago)
Median age: 18 hours
```

### Blocked URL Summary

Track why URLs are blocked for analysis:

```
Blocked URLs Summary:
  - 403 Forbidden: 45 (site blocks scraping)
  - 404 Not Found: 28 (removed/deleted)
  - Captcha/Challenge: 12
  - Requires Auth: 4
  - Total: 89 blocked (3.3% of attempted)
```

## Output

At completion, generate comprehensive output files.

### Files Generated

1. **Complete Dataset** (`research-output/collected-data.json`)
   - All successfully collected records
   - Deduplicated and validated
   - JSON or CSV format based on data type

2. **Checkpoint File** (`research-output/checkpoint.json`)
   - Final state for future incremental updates
   - Current queue for continuation if incomplete

3. **Collection Log** (`research-output/collection.log`)
   - Timestamped events
   - Rate limit changes
   - Errors and retries
   - Progress milestones

4. **Coverage Report** (`research-output/coverage-report.md`)
   - Summary statistics
   - Coverage percentage
   - Blocked URL analysis
   - Data freshness metrics

5. **Blocker Summary** (`research-output/blocked-urls.json`)
   - List of all blocked/failed URLs
   - Categorized by failure type
   - Timestamps for each failure

### Final Report Structure

```
Large-Scale Collection Complete
===============================
Duration: 2h 34m
Total Collected: 4,712 of 5,000 (94.2%)
Errors: 156 (3.3%)
Blocked: 132 (2.8%)
Data Freshness: 1-5 days old

Output Files:
- collected-data.json (4.3 MB)
- checkpoint.json (82 KB)
- collection.log (1.2 MB)
- coverage-report.md
- blocked-urls.json

Recommendation: 5,868 URLs remaining.
Run again in 24h to capture updates.
```

### Incremental Update Reminder

Always include guidance for future updates:

```
To update this dataset:
1. Run same collection command
2. System will load checkpoint.json
3. Only new/modified records will be collected
4. Final merge will include updates
```
