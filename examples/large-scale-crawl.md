# Large-Scale Documentation Crawl Example

**Scenario**: User requests complete crawl of documentation site `docs.example.com`

**Objective**: Extract all pages with content, links, and code examples, delivering a comprehensive dataset.

---

**Step 1: Probe Seed URL & Check robots.txt**

Agent sends HTTP HEAD to `https://docs.example.com`, verifies HTTP 200, and fetches `robots.txt` to parse allowed paths and crawl-delay directives.

```
→ GET https://docs.example.com/robots.txt
← 200 OK (disallow: /internal/, delay: 1)
```

**Step 2: Discover Sitemap**

Agent requests `https://docs.example.com/sitemap.xml` to enumerate documented URLs. Discovers 847 URLs across 12 sections (guides, API, tutorials, reference).

**Step 3: Configure Crawl Parameters**

Agent adjusts default config for large-scale operation:

```yaml
max_pages: 500
max_depth: 3
user_agent: "DocCrawler/1.0 (+mailto:agent@example.com)"
respect_robots: true
```

**Step 4: Enable Checkpointing**

Sets checkpoint interval to 50 pages with persistent state: `checkpoint_interval: 50`.

**Step 5: Implement Adaptive Delay**

Enables polite crawling with dynamic delay (2-5 seconds based on server response time).

**Step 6: Extract Content Per Page**

For each page, agent extracts: title, body text, headings (H1-H3), code blocks (with language tags), internal links, external links, and metadata (last modified, author if available).

**Step 7: Generate Manifest & Coverage Report**

Outputs `manifest.jsonl` tracking URLs, HTTP status, content type, and extraction timestamp. Creates `coverage_report.md` summarizing: 487 successful, 13 blocked by robots.txt.

**Step 8: Report Blocked Pages**

Lists 13 URLs excluded by robots.txt: `/internal/private/*`, `/admin/*`, plus 3 rate-limited pages (HTTP 429). Suggests manual review for any critical blocked content.

**Step 9: Deliver Dataset**

Final output includes: `pages/`, `manifest.jsonl`, `links.csv`, `coverage_report.md`, and `data_dictionary.md` describing schema fields (url, status, content_type, word_count, code_blocks[], links_internal[], links_external[]).

---

**Output Summary**: 487 pages extracted, 0.98 GB total, average extraction rate: 12 pages/minute.
