# D Research Skill — Upgrade Plan Chi Tiết

## Mục tiêu

Nâng bộ skill từ **7/10 → 9/10**, đáp ứng đầy đủ cho:
- **Dev**: cào data quy mô lớn, truy cập mọi loại API, database, xử lý data pipeline
- **Nhà khoa học**: nghiên cứu học thuật với academic databases, citation management, analysis, báo cáo hoàn chỉnh

## Tổng quan thay đổi

| Loại | File | Hành động |
|---|---|---|
| reference | `references/api-access-workflow.md` | **TẠO MỚI** |
| reference | `references/academic-databases.md` | **TẠO MỚI** |
| reference | `references/data-processing-pipeline.md` | **TẠO MỚI** |
| reference | `references/citation-management.md` | **TẠO MỚI** |
| reference | `references/large-scale-collection.md` | **TẠO MỚI** |
| reference | `references/data-visualization.md` | **TẠO MỚI** |
| reference | `references/monitoring-change-detection.md` | **TẠO MỚI** |
| reference | `references/multilingual-research.md` | **TẠO MỚI** |
| reference | `references/specialized-domains.md` | **TẠO MỚI** |
| adapter | `adapters/database-readonly.md` | **TẠO MỚI** |
| adapter | `adapters/graphql.md` | **TẠO MỚI** |
| template | `templates/api-request-log.csv` | **TẠO MỚI** |
| template | `templates/data-dictionary.csv` | **TẠO MỚI** |
| template | `templates/citation-library.bib` | **TẠO MỚI** |
| example | `examples/api-dataset-collection.md` | **TẠO MỚI** |
| example | `examples/large-scale-crawl.md` | **TẠO MỚI** |
| example | `examples/scientific-literature-review.md` | **TẠO MỚI** |
| script | `scripts/api_fetch.mjs` | **TẠO MỚI** |
| script | `scripts/data_clean.py` | **TẠO MỚI** |
| script | `scripts/citation_export.py` | **TẠO MỚI** |
| core | `SKILL.md` | **CẬP NHẬT** — thêm steps mới + references |
| core | `AGENTS.md` | **CẬP NHẬT** — thêm capabilities mới |
| core | `README.md` | **CẬP NHẬT** — thêm new capabilities |
| config | `research.config.example.json` | **CẬP NHẬT** — thêm config fields mới |
| config | `package.json` | **CẬP NHẬT** — thêm scripts mới |
| reference | `references/tool-adapter-policy.md` | **CẬP NHẬT** — thêm adapters mới |
| reference | `references/extraction-methods.md` | **CẬP NHẬT** — thêm API + DB extraction |
| reference | `references/source-discovery.md` | **CẬP NHẬT** — thêm API/DB discovery |
| reference | `references/query-patterns.md` | **CẬP NHẬT** — thêm API query patterns |
| reference | `references/final-report-template.md` | **CẬP NHẬT** — thêm LaTeX, visualization |
| reference | `references/academic-research-protocol.md` | **CẬP NHẬT** — thêm DB workflow, citation |
| reference | `references/research-bibliography.md` | **CẬP NHẬT** — thêm references mới |

---

## PHASE 1: Mở rộng tầng truy cập dữ liệu (Priority cao nhất)

### 1.1 TẠO `references/api-access-workflow.md` (~150 dòng)

**Mục đích**: Workflow hoàn chỉnh để agent gọi public/authorized APIs

**Nội dung chi tiết**:
```
# API Access Workflow

## Khi nào dùng
- User cung cấp API key/endpoint
- Phát hiện public API từ docs hoặc network requests
- Cần structured data mà HTML extraction không hiệu quả

## API Discovery
- Kiểm tra /api, /api/v1, /api/docs, /swagger, /openapi.json
- Tìm API documentation links từ page
- Inspect network requests (XHR/Fetch) khi browse page
- Tìm developer portal qua search

## Authentication patterns
- No auth (public API)
- API key via header (Authorization: Bearer, X-API-Key)
- API key via query parameter
- OAuth2 client credentials (khi user cung cấp)
- Session-based (khi user authorize)

## Request workflow
1. Discover API endpoint + docs
2. Test with smallest possible request
3. Check rate limits từ response headers (X-RateLimit-*)
4. Implement pagination (offset, cursor, page-based, link-header)
5. Handle errors (retry on 429/500/503, stop on 401/403)
6. Validate response schema
7. Log mỗi request vào api-request-log

## Pagination patterns
- Offset-based: ?offset=0&limit=100
- Page-based: ?page=1&per_page=100
- Cursor-based: ?cursor=<next_cursor>
- Link header: parse rel="next"
- Token-based: ?pageToken=<token>
- Auto-detect pattern từ response

## Rate limit handling
- Parse X-RateLimit-Remaining, X-RateLimit-Reset, Retry-After
- Adaptive delay: nếu remaining < 10%, tăng delay
- Exponential backoff trên 429: 1s → 2s → 4s → 8s → stop
- Log rate limit events

## Response processing
- Validate JSON schema
- Extract pagination metadata
- Flatten nested objects khi cần
- Map to evidence ledger format
- Handle partial/incomplete responses

## Common API patterns
### REST
- GET collection: /api/items?filter=value&page=1
- GET detail: /api/items/{id}
- Bulk endpoints: /api/items/batch

### GraphQL
- Xem adapters/graphql.md

### SPARQL
- Endpoint discovery: /.well-known/void, /sparql
- SELECT queries cho tabular data
- CONSTRUCT queries cho graph data
- LIMIT + OFFSET pagination

## Output
- Raw JSON responses (archived)
- Processed CSV/JSON dataset
- API request log
- Rate limit report
- Blocker report nếu API bị restricted

## Safety
- Chỉ GET/read-only requests trừ khi user authorize write
- Không brute-force API keys
- Respect rate limits
- Không access private endpoints không có authorization
- Log tất cả requests để audit
```

### 1.2 TẠO `references/academic-databases.md` (~180 dòng)

**Mục đích**: Hướng dẫn truy cập các nguồn academic phổ biến nhất

**Nội dung chi tiết**:
```
# Academic Database Access

## Khi nào dùng
- Literature review, systematic review
- Research paper discovery
- Citation analysis
- Dataset discovery cho academic projects

## Free/Open APIs (không cần API key)

### OpenAlex (khuyến nghị đầu tiên)
- Base: https://api.openalex.org
- Docs: https://docs.openalex.org
- Works: GET /works?search={query}&filter=publication_year:2020-2026
- Authors: GET /authors?search={name}
- Concepts: GET /concepts?search={topic}
- Institutions: GET /institutions?search={name}
- Pagination: cursor-based (?cursor=*)
- Rate: 10 req/s (polite pool với email: ?mailto=user@example.com)
- Output: JSON, mỗi work có DOI, title, abstract, citations, references
- Dùng cho: discovery, citation network, metadata enrichment

### CrossRef
- Base: https://api.crossref.org
- Works: GET /works?query={query}&rows=100&offset=0
- DOI lookup: GET /works/{doi}
- Rate: polite pool với User-Agent header chứa email
- Output: JSON với full metadata, references, funding info
- Dùng cho: DOI resolution, reference list enrichment, metadata

### Semantic Scholar
- Base: https://api.semanticscholar.org/graph/v1
- Paper search: GET /paper/search?query={query}&limit=100
- Paper detail: GET /paper/{paper_id}?fields=title,abstract,citations,references
- Author: GET /author/{id}
- Rate: 100 req/5min (free), higher với API key
- Dùng cho: citation graph, influence analysis, related papers

### PubMed / MEDLINE (E-utilities)
- Base: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
- Search: esearch.fcgi?db=pubmed&term={query}&retmax=100
- Fetch: efetch.fcgi?db=pubmed&id={pmid_list}&rettype=xml
- Rate: 3 req/s (free), 10 req/s với API key
- Dùng cho: biomedical, life sciences, clinical research

### arXiv
- Base: http://export.arxiv.org/api/query
- Search: ?search_query=all:{query}&start=0&max_results=100
- Output: Atom XML
- Rate: respect crawl-delay
- Dùng cho: physics, CS, math, quantitative biology/finance

### CORE (open access aggregator)
- Base: https://api.core.ac.uk/v3
- Search: GET /search/works?q={query}&limit=100
- API key: free registration
- Dùng cho: full-text open access papers

### DOAJ (Directory of Open Access Journals)
- Base: https://doaj.org/api
- Search: GET /search/articles/{query}?page=1&pageSize=100
- Dùng cho: open access journal discovery

## APIs cần API key (user phải cung cấp)

### Scopus / Elsevier
- Cần: Elsevier API key (free cho academic)
- Base: https://api.elsevier.com
- Search: GET /content/search/scopus?query={query}

### IEEE Xplore
- Cần: IEEE API key
- Base: https://ieeexploreapi.ieee.org/api/v1/search/articles
- Query: ?querytext={query}&max_records=200

### Web of Science
- Cần: Clarivate API key
- Base: https://api.clarivate.com/apis/wos-starter/v1

### Google Scholar
- Không có official API
- Dùng: SerpAPI (cần key) hoặc browser-based extraction
- Rate limit nghiêm ngặt, dễ bị block
- Khuyến nghị: dùng OpenAlex/Semantic Scholar thay thế

## Workflow
1. Xác định databases phù hợp với discipline
2. Bắt đầu với free APIs (OpenAlex → CrossRef → Semantic Scholar)
3. Chuyển sang paid APIs khi user cung cấp key
4. Cross-reference kết quả giữa databases
5. Enrich metadata: DOI → full record từ CrossRef
6. Build citation network từ references
7. Log queries vào search-log

## Citation network analysis
- Forward citations: ai cite paper này?
- Backward citations: paper này cite ai?
- Co-citation: papers nào hay được cite cùng nhau?
- Bibliographic coupling: papers nào cite cùng nguồn?
- Dùng OpenAlex cited_by_count + referenced_works

## Output
- Paper list (CSV/JSON)
- Citation network (edge list)
- Evidence table
- Search log (reproducible)
- Blocker report cho restricted databases
```

### 1.3 TẠO `adapters/database-readonly.md` (~80 dòng)

**Mục đích**: Adapter cho read-only database access

**Nội dung**:
```
# Database Read-Only Adapter

## Khi nào dùng
- User cung cấp database connection string
- Cần query structured data từ SQL/NoSQL databases
- Data portal cung cấp query interface

## Supported patterns
### SQL databases (PostgreSQL, MySQL, SQLite)
- Connection: user-provided connection string
- Query: SELECT only, no INSERT/UPDATE/DELETE
- Pagination: LIMIT + OFFSET
- Schema discovery: INFORMATION_SCHEMA queries
- Export: CSV, JSON

### NoSQL (MongoDB, Elasticsearch)
- Connection: user-provided URI
- Query: read-only find/search operations
- Pagination: skip/limit hoặc scroll
- Schema inference từ sample documents

### Data portals with query interfaces
- Socrata (SODA API): nhiều government open data portals
- CKAN: data.gov, nhiều national data portals
- Google BigQuery (public datasets): cần user auth

## Safety
- CHỈREAD-ONLY — không bao giờ mutate data
- Validate connection string trước khi connect
- Không log credentials
- Timeout cho mỗi query
- Limit result size

## Workflow
1. User cung cấp connection info
2. Test connection
3. Discover schema / collections
4. Build query từ research question
5. Execute với LIMIT
6. Export results
7. Log queries vào search-log

## Output
- Query results (CSV/JSON)
- Schema documentation
- Query log
- Connection status report
```

### 1.4 TẠO `adapters/graphql.md` (~70 dòng)

**Mục đích**: GraphQL API adapter

**Nội dung**:
```
# GraphQL Adapter

## Khi nào dùng
- API endpoint là GraphQL
- Cần query nested/relational data
- Phát hiện /graphql endpoint từ page inspection

## Discovery
- Kiểm tra /graphql, /api/graphql, /gql
- Introspection query: { __schema { types { name fields { name type { name } } } } }
- Đọc docs nếu có GraphQL Playground/Explorer

## Query workflow
1. Introspect schema (nếu enabled)
2. Identify relevant types và fields
3. Build query với chỉ fields cần thiết
4. Test với small LIMIT/first
5. Implement cursor-based pagination
6. Handle errors và rate limits

## Pagination patterns
- Relay-style: { items(first: 100, after: "cursor") { edges { node { ... } } pageInfo { hasNextPage endCursor } } }
- Offset-style: { items(limit: 100, offset: 0) { ... } }

## Safety
- Read-only queries only (query, không mutation)
- Respect rate limits
- Không introspect nếu disabled
- Log tất cả queries

## Output
- Flattened JSON/CSV
- Schema documentation
- Query log
```

---

## PHASE 2: Data Processing & Analysis Pipeline

### 2.1 TẠO `references/data-processing-pipeline.md` (~160 dòng)

**Mục đích**: Pipeline hoàn chỉnh từ raw data → clean → analyze → output

**Nội dung**:
```
# Data Processing Pipeline

## Khi nào dùng
- Sau khi extract data từ web, API, hoặc database
- Khi data cần cleaning trước khi phân tích
- Khi cần merge data từ nhiều sources
- Khi cần statistical summary hoặc analysis

## Pipeline stages

### Stage 1: Raw Data Audit
- Row count, column count
- Data types per column
- Missing values (count, percentage)
- Duplicate detection
- Sample inspection (first 10, random 10)
- Character encoding check

### Stage 2: Cleaning
- Remove exact duplicates
- Normalize whitespace, encoding
- Standardize date formats (ISO 8601)
- Standardize number formats
- Handle missing values (document strategy: drop, fill, flag)
- Fix obvious typos in categorical fields
- Trim and normalize text fields
- Validate URLs, emails, identifiers

### Stage 3: Transformation
- Type casting (string → number, date, boolean)
- Derive new fields (year from date, domain from URL, etc.)
- Merge/join datasets by key
- Reshape (pivot, unpivot, flatten nested)
- Categorize/bin continuous variables
- Normalize/standardize numerical values
- Geocode addresses (khi cần)

### Stage 4: Validation
- Schema validation (expected types, ranges)
- Cross-source consistency check
- Outlier detection (IQR, z-score)
- Referential integrity (foreign keys)
- Business rule validation
- Sample spot-check against source

### Stage 5: Analysis (khi được yêu cầu)
- Descriptive statistics (mean, median, std, quartiles)
- Frequency tables cho categorical data
- Correlation matrix
- Time series trends
- Group comparisons
- Text analysis (word frequency, n-grams)

### Stage 6: Output
- Clean dataset (CSV, JSON, Parquet)
- Data dictionary
- Cleaning log (what was changed, why)
- Quality report
- Analysis summary
- Visualization (xem data-visualization.md)

## Data dictionary template
| Field | Original name | Type | Description | Example | Source | Cleaning notes | Missingness |
|---|---|---|---|---|---|---|---|

## Quality report template
- Total rows raw → clean
- Duplicates removed
- Missing values handled
- Outliers flagged
- Transformations applied
- Validation passed/failed
- Known data quality issues

## Tools
- Python: pandas, numpy (agent generates code)
- Shell: csvkit, jq, miller
- Script: scripts/data_clean.py (basic cleaning)
```

### 2.2 TẠO `references/data-visualization.md` (~120 dòng)

**Mục đích**: Hướng dẫn agent tạo charts và visual reports

**Nội dung**:
```
# Data Visualization

## Khi nào dùng
- Research report cần charts
- Dataset summary cần visual overview
- Comparison hoặc trend analysis
- User yêu cầu dashboard hoặc visual output

## Chart type selection
| Data pattern | Chart type | Tool |
|---|---|---|
| Distribution | Histogram, box plot | matplotlib/plotly |
| Comparison | Bar chart, grouped bar | matplotlib/plotly |
| Trend over time | Line chart, area chart | matplotlib/plotly |
| Composition | Pie chart, stacked bar | matplotlib/plotly |
| Relationship | Scatter plot, heatmap | matplotlib/plotly |
| Ranking | Horizontal bar, lollipop | matplotlib/plotly |
| Geographic | Choropleth, point map | plotly/folium |
| Network | Node-link graph | networkx + matplotlib |
| Text | Word cloud, frequency bar | wordcloud |

## Static charts (matplotlib)
- Dùng cho: PDF reports, academic papers, simple exports
- Output: PNG, SVG, PDF
- Agent generates Python code inline

## Interactive charts (plotly)
- Dùng cho: HTML reports, dashboards, exploration
- Output: HTML file, embedded in report
- Agent generates Python code inline

## Report embedding
- Markdown: ![chart](path/to/chart.png)
- HTML report: <img> hoặc plotly embed
- LaTeX: \includegraphics

## Dashboard template (HTML)
- Single-page HTML với embedded charts
- Summary stats ở trên
- Charts ở giữa
- Data table ở dưới
- Source attribution và timestamp

## Guidelines
- Always label axes, title, and source
- Use colorblind-friendly palettes
- Keep it simple — ít chart nhưng đúng insight
- Include data source and date range
- Prefer vector (SVG) cho publications
```

### 2.3 TẠO `references/citation-management.md` (~100 dòng)

**Mục đích**: Citation export và management cho academic users

**Nội dung**:
```
# Citation Management

## Khi nào dùng
- Academic writing, thesis, paper
- Literature review
- User cần reference list theo format chuẩn

## Citation data model
Mỗi citation cần:
- type (article, book, conference, report, web, dataset, software)
- title
- authors (family, given)
- year
- journal/conference/publisher
- volume, issue, pages
- DOI
- URL
- accessed date
- abstract (optional)

## BibTeX export
- File: .bib
- Entry types: @article, @inproceedings, @book, @techreport, @misc, @online, @dataset
- Key format: AuthorYear_ShortTitle
- Script: scripts/citation_export.py --format bibtex

## RIS export
- File: .ris
- For Zotero, Mendeley, EndNote import
- Script: scripts/citation_export.py --format ris

## Inline citation formats
- APA 7: (Author, Year)
- IEEE: [1]
- Chicago: Author (Year)
- Vancouver: (1)
- Agent generates formatted reference list

## DOI → metadata enrichment
- CrossRef API: GET https://api.crossref.org/works/{doi}
- Trả về full metadata: authors, journal, dates, references
- Dùng để verify và complete citation data

## Workflow
1. Collect citations trong evidence ledger (source_url, source_title, date_published)
2. Enrich: DOI → CrossRef → full metadata
3. Deduplicate by DOI hoặc title similarity
4. Export theo format user yêu cầu
5. Generate formatted reference list

## Quality checks
- Mỗi citation có DOI hoặc URL
- Author names consistent
- Dates complete
- No duplicate entries
- Citation keys unique (BibTeX)

## Template
Xem templates/citation-library.bib
```

---

## PHASE 3: Large-Scale & Advanced Collection

### 3.1 TẠO `references/large-scale-collection.md` (~130 dòng)

**Nội dung chính**:
```
# Large-Scale Data Collection

## Khi nào dùng
- Dataset > 100 pages/records
- Multi-domain collection
- Collection cần nhiều giờ
- Cần resume sau interruption

## Principles
- Incremental > full re-crawl
- Checkpoint > hope for the best
- Adaptive delay > fixed delay
- Quality sample > incomplete exhaustive

## Checkpointing
- Lưu state sau mỗi N pages/records: visited URLs, queue, partial data
- Checkpoint file: research-output/checkpoint.json
- Resume: đọc checkpoint, skip visited, continue queue
- Agent nên checkpoint mỗi 50 records hoặc 5 phút

## Adaptive rate limiting
- Start: configured delay (1000ms)
- Nếu response time tăng > 2x: tăng delay 50%
- Nếu 429: exponential backoff (2s → 4s → 8s → 16s → stop)
- Nếu stable 100 requests: giảm delay 10% (không dưới min)
- Log rate limit events

## Batch processing
- Chia collection thành batches (ví dụ: 100 records/batch)
- Process + validate mỗi batch
- Merge batches cuối cùng
- Cho phép parallel batches trên different domains

## Multi-domain strategy
- Separate queues per domain
- Separate rate limits per domain
- Round-robin giữa domains
- Domain-specific config overrides

## Error recovery
- Retry transient errors (5xx, timeout) tối đa 3 lần
- Skip permanent errors (404, 403) → log vào blocked
- Continue collection sau individual page failures
- Alert user khi error rate > 20%

## Coverage tracking
- Expected total (nếu biết)
- Collected so far
- Blocked/failed
- Remaining estimate
- Coverage percentage
- Freshness (oldest record date)

## Output
- Complete dataset (CSV/JSON)
- Checkpoint file (cho resume)
- Collection log
- Coverage report
- Blocker summary
```

### 3.2 TẠO `references/monitoring-change-detection.md` (~90 dòng)

**Nội dung chính**:
```
# Monitoring and Change Detection

## Khi nào dùng
- Theo dõi giá, stock, product availability
- Monitor news/announcements
- Detect content changes trên pages
- Track dataset updates

## Monitoring workflow
1. Baseline snapshot: extract + hash content
2. Schedule re-check (user defines interval)
3. Compare: diff content, detect changes
4. Alert: report significant changes
5. Archive: store history

## Change detection methods
- Full text hash comparison
- Structured field comparison
- DOM element comparison (selector-based)
- File checksum comparison
- API response diff
- RSS/Atom feed monitoring

## Diff output
- What changed (field, value before → after)
- When detected
- Source URL
- Confidence change is real (not layout/ad change)

## Use cases
- Price monitoring (e-commerce, APIs)
- Regulatory change tracking
- Competitor feature tracking
- Job posting monitoring
- Academic paper retraction/update tracking
```

### 3.3 TẠO `references/multilingual-research.md` (~80 dòng)

**Nội dung chính**:
```
# Multilingual Research

## Khi nào dùng
- Chủ đề có sources quan trọng bằng nhiều ngôn ngữ
- User research market/policy ở nhiều quốc gia
- Academic papers bằng non-English languages

## Workflow
1. Identify relevant languages cho topic
2. Generate queries bằng mỗi language
3. Search trên local search engines (Baidu, Yandex, Naver, etc.)
4. Extract content bằng original language
5. Translate key findings (dùng agent translation capability)
6. Cross-validate findings across languages
7. Report language coverage

## Search engines by language
- English: Google, Bing
- Chinese: Baidu, Sogou
- Russian: Yandex
- Korean: Naver
- Japanese: Yahoo Japan
- Vietnamese: Cốc Cốc, Google.com.vn
- Multilingual: Google Scholar (language filter)

## Translation strategy
- Extract first, translate key sections
- Preserve original text alongside translation
- Note translation confidence
- Keep proper nouns untranslated
- Verify technical terms

## Academic multilingual
- Many databases support language filters
- OpenAlex: filter by language
- Local repositories: HAL (French), CNKI (Chinese), CiNii (Japanese)
```

### 3.4 TẠO `references/specialized-domains.md` (~140 dòng)

**Nội dung chính**:
```
# Specialized Domain Research

## Financial & Market Data
### Free sources
- Yahoo Finance API (unofficial, qua yfinance Python)
- Alpha Vantage (free API key, 5 req/min)
- FRED (Federal Reserve Economic Data): https://api.stlouisfed.org
- World Bank Open Data: https://api.worldbank.org/v2
- IMF Data: https://datahelp.imf.org
- SEC EDGAR filings: https://efts.sec.gov/LATEST/search-index?q={query}

### Workflow
- Company research: EDGAR filings + financial APIs + news
- Market analysis: time series data + indicator APIs
- Macro research: World Bank + FRED + IMF

## Patent & IP
- Google Patents: https://patents.google.com (browser extraction)
- USPTO PatentsView API: https://api.patentsview.org
- EPO Open Patent Services: https://ops.epo.org
- WIPO: https://patentscope.wipo.int

## Legal & Regulatory
- Government gazette/official journal per country
- EUR-Lex (EU law): https://eur-lex.europa.eu
- US Congress: https://api.congress.gov
- Court databases vary by jurisdiction

## Government & Statistics
- data.gov (US): CKAN API
- data.gov.uk (UK): CKAN API
- Eurostat: https://ec.europa.eu/eurostat/api
- UN Data: https://data.un.org
- National statistics agencies per country

## Social Media & News (public data only)
- Reddit: reddit.com/r/{subreddit}.json, Pushshift (limited)
- Hacker News: https://hn.algolia.com/api
- News APIs: NewsAPI, GDELT, Wayback Machine
- Twitter/X: very limited without paid API

## Geospatial
- OpenStreetMap / Overpass API
- Natural Earth Data
- GADM boundaries
- National geoportals
```

---

## PHASE 4: Script mới

### 4.1 TẠO `scripts/api_fetch.mjs` (~200 dòng)

**Mục đích**: Reusable API fetch với pagination, rate-limit, retry

**Capabilities**:
- `--url` base API URL
- `--method` GET (default)
- `--headers` JSON string cho headers (API keys)
- `--params` JSON string cho query params
- `--pagination` auto|offset|cursor|page|link-header
- `--max-pages` limit
- `--delay` between requests
- `--out` output file
- `--format` json|csv|jsonl
- Rate limit detection từ headers
- Exponential backoff trên 429
- Self-test mode

### 4.2 TẠO `scripts/data_clean.py` (~150 dòng)

**Mục đích**: Basic data cleaning pipeline

**Capabilities**:
- `clean --file input.csv --out clean.csv` — basic cleaning
- `stats --file data.csv` — descriptive statistics
- `dedup --file data.csv --key field_name --out deduped.csv`
- `validate --file data.csv --schema schema.json`
- `merge --files a.csv b.csv --key id --out merged.csv`
- `self-test`

### 4.3 TẠO `scripts/citation_export.py` (~120 dòng)

**Mục đích**: Export evidence ledger → BibTeX/RIS

**Capabilities**:
- `export --file evidence.csv --format bibtex --out references.bib`
- `export --file evidence.csv --format ris --out references.ris`
- `enrich --doi 10.1234/example` — fetch metadata từ CrossRef
- `self-test`

---

## PHASE 5: Cập nhật files hiện tại

### 5.1 CẬP NHẬT `SKILL.md`

**Thay đổi**:
1. Thêm section "## Data access layers" sau "## Tool priority" — mô tả 6 tầng: Web → File → API → Database → Academic DB → Specialized
2. Thêm step 6.5 vào workflow: "Process and clean extracted data" — tham chiếu `references/data-processing-pipeline.md`
3. Thêm step 11.5: "Export citations" — tham chiếu `references/citation-management.md`
4. Mở rộng "## Optional bundled scripts" — thêm 3 scripts mới
5. Mở rộng "## Configuration" — thêm config fields: api.*, database.*, citation.*, monitoring.*
6. Thêm "## Workflow decision tree" entries cho: API dataset, large-scale crawl, financial research, monitoring

### 5.2 CẬP NHẬT `AGENTS.md`

**Thay đổi**:
- Thêm các capabilities mới vào core workflow list:
  - "Use public APIs and academic databases when available"
  - "Process and clean extracted data"
  - "Export citations in BibTeX/RIS format"
  - "Support large-scale collection with checkpointing"
- Thêm adapter list: database-readonly, graphql

### 5.3 CẬP NHẬT `README.md`

**Thay đổi**:
- Thêm new capabilities vào "Key capabilities" section
- Thêm new scripts vào "Script examples"
- Update "Repository layout" với new files
- Mirror English + Vietnamese sections

### 5.4 CẬP NHẬT `research.config.example.json`

**Thêm fields**:
```json
{
  "api": {
    "defaultDelayMs": 500,
    "maxRetries": 3,
    "backoffMultiplier": 2,
    "respectRateLimitHeaders": true
  },
  "database": {
    "queryTimeoutMs": 30000,
    "maxResultRows": 10000,
    "readOnly": true
  },
  "citation": {
    "defaultFormat": "bibtex",
    "enrichFromCrossRef": true,
    "autoGenerateKeys": true
  },
  "monitoring": {
    "enabled": false,
    "defaultIntervalMinutes": 60,
    "hashMethod": "sha256"
  },
  "processing": {
    "autoClean": false,
    "detectOutliers": true,
    "deduplicateByDefault": true
  }
}
```

### 5.5 CẬP NHẬT existing references

**`references/extraction-methods.md`**:
- Thêm "### 8. API extraction" — tham chiếu api-access-workflow.md
- Thêm "### 9. Database extraction" — tham chiếu adapters/database-readonly.md
- Thêm "### 10. Academic database extraction" — tham chiếu academic-databases.md

**`references/source-discovery.md`**:
- Thêm "### API layer" — REST, GraphQL, SPARQL discovery
- Thêm "### Database layer" — public data portals với query interface
- Thêm "### Specialized domain layer" — tham chiếu specialized-domains.md

**`references/query-patterns.md`**:
- Thêm "## API query patterns" — endpoint construction
- Thêm "## Academic database query patterns" — OpenAlex, CrossRef, PubMed cụ thể

**`references/final-report-template.md`**:
- Thêm "## Report with visualization" template
- Thêm "## LaTeX report template"
- Thêm "## Citation list format"

**`references/academic-research-protocol.md`**:
- Thêm "## Database search workflow" — academic DB APIs
- Thêm "## Citation export" section

**`references/tool-adapter-policy.md`**:
- Thêm database-readonly và graphql vào adapter list
- Thêm API fetch vào optional capabilities

**`references/research-bibliography.md`**:
- Thêm references cho: OpenAlex, CrossRef, PRISMA-S, data processing standards

### 5.6 CẬP NHẬT `package.json`

**Thêm scripts**:
```json
{
  "api:fetch": "node scripts/api_fetch.mjs",
  "data:clean": "node scripts/run_python.mjs scripts/data_clean.py clean",
  "data:stats": "node scripts/run_python.mjs scripts/data_clean.py stats",
  "data:dedup": "node scripts/run_python.mjs scripts/data_clean.py dedup",
  "citation:export": "node scripts/run_python.mjs scripts/citation_export.py export",
  "citation:enrich": "node scripts/run_python.mjs scripts/citation_export.py enrich"
}
```

---

## PHASE 6: Templates & Examples mới

### Templates
- `templates/api-request-log.csv`: request_id, timestamp, url, method, status, response_time_ms, rate_limit_remaining, notes
- `templates/data-dictionary.csv`: field, original_name, type, description, example, source, cleaning_notes, missingness_pct
- `templates/citation-library.bib`: sample BibTeX entries

### Examples
- `examples/api-dataset-collection.md`: thu thập dataset qua OpenAlex API
- `examples/large-scale-crawl.md`: crawl 500+ pages với checkpointing
- `examples/scientific-literature-review.md`: systematic review với academic DB APIs + citation export

---

## Thứ tự triển khai

| Phase | Công việc | Files | Ước lượng |
|---|---|---|---|
| **1** | Tầng truy cập dữ liệu | 4 files mới | Cao nhất |
| **2** | Data processing + visualization + citation | 3 files mới | Cao |
| **3** | Large-scale + monitoring + multilingual + specialized | 4 files mới | Trung bình |
| **4** | Scripts mới | 3 scripts | Trung bình |
| **5** | Cập nhật files hiện tại | ~10 files sửa | Quan trọng |
| **6** | Templates + Examples | 6 files mới | Thấp |

**Tổng: ~20 files mới + ~10 files cập nhật**

---

## Sau upgrade: expected score

| Khả năng | Trước | Sau |
|---|---|---|
| Web research + crawl | 9/10 | 9/10 |
| API access | 3/10 | 9/10 |
| Database access | 0/10 | 7/10 |
| Academic databases | 2/10 | 9/10 |
| Data processing | 1/10 | 8/10 |
| Citation management | 0/10 | 8/10 |
| Visualization | 0/10 | 7/10 |
| Large-scale collection | 4/10 | 8/10 |
| Monitoring | 0/10 | 7/10 |
| Multilingual | 3/10 | 7/10 |
| Specialized domains | 2/10 | 8/10 |
| **Overall** | **7/10** | **9/10** |
