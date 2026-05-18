# Monitoring and Change Detection

Change detection enables agents to track modifications across web sources, APIs, and datasets over time. This reference covers the complete workflow and methods for building reliable monitoring systems.

## When to Use Change Detection

- **Price tracking** — Monitor e-commerce product prices, API rate limits, or subscription costs for changes
- **News and announcements** — Track press releases, blog posts, or media coverage for updates
- **Regulatory changes** — Watch government portals, legal databases, or policy pages for new rules
- **Dataset updates** — Detect version changes in published datasets, model weights, or benchmark results
- **Competitor feature tracking** — Monitor rival product pages, changelogs, or pricing for strategic insights
- **Job posting monitoring** — Track career pages for new listings or removed positions
- **Academic paper updates** — Watch for paper revisions, retractions, or citation count changes
- **Infrastructure cost changes** — Monitor cloud provider pricing pages for cost-impacting updates

## Monitoring Workflow

**Step 1: Baseline snapshot**  
Extract current content and compute a hash for future comparison. Store the raw content and metadata (timestamp, URL, extracted fields).

**Step 2: Schedule re-checks**  
The agent defines a checking interval based on the monitoring priority. Use `repeat` blocks with `wait_for` durations. Higher-priority targets (e.g., regulatory sites) warrant shorter intervals.

**Step 3: Compare and detect changes**  
Fetch current content and compare against the baseline. Compute diffs at the appropriate granularity (full page, specific elements, structured fields).

**Step 4: Alert and report**  
If changes are detected, generate a structured alert with before/after values, significance assessment, and source details. Route alerts via the channel specified by the user (Slack, email, console output).

**Step 5: Archive and update baseline**  
Store the detected change in a history log. Update the baseline to the current state to continue tracking subsequent changes.

## Change Detection Methods

| Method | Use Case | How It Works |
|--------|----------|--------------|
| **Full text hash** | Simple page monitoring | SHA-256 hash of entire page; fast equality check, no detail on what changed |
| **Structured field comparison** | API responses, JSON feeds | Extract specific fields and compare values directly with type awareness |
| **DOM element comparison** | Dynamic web pages | Use CSS selectors or XPath to target specific elements; compare `innerText`, `href`, `src` attributes |
| **File checksum comparison** | Dataset files, PDFs | MD5/SHA-256 of downloaded files; detect binary or structural changes |
| **API response diff** | REST/GraphQL endpoints | Compare JSON payloads field-by-field; handle nested structures |
| **RSS/Atom feed monitoring** | Blogs, news sites | Track `<item>` entries by GUID; detect new posts, updated timestamps |
| **Sitemap comparison** | Site structure changes | Parse XML sitemaps; track added/removed URLs and change frequencies |

For web pages, prefer targeted element extraction over full-page hashing to avoid noise from ads, timestamps, or dynamic content that changes on every load.

## Diff Output Format

When changes are detected, report them in this structure:

```
## Change Detected: [Source Name]

**Detected:** [ISO timestamp]
**Source URL:** [full URL]
**Change Type:** [field_added | field_removed | value_changed | structure_changed]

| Field | Before | After |
|-------|--------|-------|
| [field_name] | [previous value] | [current value] |

**Confidence:** [high | medium | low]
  - High: Direct value comparison (structured data, APIs)
  - Medium: DOM element text changed
  - Low: Layout/formatting only (CSS, whitespace, attribute order)

**Action Required:** [yes | no]
  - Mark "yes" if the change matches user-defined criteria (price threshold, keyword, etc.)
```

## Use Cases

**Price monitoring (e-commerce/APIs)**
```
1. Identify target product or API pricing page
2. Extract price field, currency, unit (per-call, per-seat, etc.)
3. Store baseline with timestamp
4. Compare on schedule; alert on any deviation
5. Track price history over time
```

**Regulatory change tracking**
```
1. Identify authoritative source (government portal, official journal)
2. Target specific sections or document types
3. Extract version numbers, effective dates, amendment text
4. Alert on new entries or modified sections
5. Link to full legal text for review
```

**Competitor feature tracking**
```
1. Monitor competitor changelog, release notes, or product pages
2. Extract feature names, descriptions, release dates
3. Track additions and removals over time
4. Compare feature sets across competitors
```

**Job posting monitoring**
```
1. Target ATS (Applicant Tracking System) pages or company career URLs
2. Track job listings by ID or title hash
3. Detect new postings, removed listings, or description updates
4. Report posting duration trends
```

**Academic paper retraction/update tracking**
```
1. Monitor arXiv, PubMed, or journal RSS feeds for specific papers
2. Track version numbers (v1 → v2) and update timestamps
3. Detect retraction notices by monitoring paper status endpoints
4. Alert on citation count changes or author revisions
```

**Dataset version tracking**
```
1. Monitor source URLs (HuggingFace, Kaggle, GitHub releases)
2. Compare dataset metadata: version tags, file counts, checksum totals
3. Detect schema changes (added/removed columns)
4. Alert when new versions are published or access permissions change
```

## Key Practices

- **Store all baselines and snapshots** in a persistent history file or database for auditability
- **Set minimum check intervals** to respect source load; 15–60 minutes for high priority, 4–24 hours for lower priority
- **Handle anti-scraping measures** with retry logic and user-agent rotation
- **Track false positives** — layout changes, ad rotation, and CDN updates can trigger noise; refine selectors to target stable content
- **Combine methods** when needed — hash the page for fast checks, then use DOM comparison for detailed alerting

For structured sources (APIs, feeds), prefer field-level comparison. For unstructured sources (web pages), use targeted DOM extraction to reduce noise from dynamic page elements.

## Compare via Wayback snapshots

When you need to compare how a public page looked at two different points in time, use `scripts/wayback.py diff`:

```bash
python scripts/wayback.py diff --url <url> --t1 YYYYMMDD --t2 YYYYMMDD
```

This fetches the two nearest Wayback Machine snapshots for the given URL at timestamps `t1` and `t2`, then produces a unified text diff of the archived page content. Useful for detecting silent edits to policy pages, pricing tables, or documentation that the site operator did not announce publicly.

### Structured diff summary

For programmatic consumption, add `--summarize` to get a JSON object with line-level change counts and the top-N largest hunks:

```bash
python scripts/wayback.py diff --url <url> --t1 YYYYMMDD --t2 YYYYMMDD --summarize --top-n 3
```

Output:

```json
{
  "hash_t1": "abc123...",
  "hash_t2": "def456...",
  "identical": false,
  "diff_summary": {
    "added_lines": 42,
    "removed_lines": 17,
    "top_hunks": [
      {"context": "@@ -10,5 +10,8 @@", "added": "new pricing tier...", "removed": "old pricing..."}
    ]
  }
}
```

Use this when you need to quantify how much a page changed (e.g., "pricing page gained 42 lines") or when feeding change data into a downstream monitoring pipeline. The `--top-n` flag controls how many hunks are included (default: 5).
