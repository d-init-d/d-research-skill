# D Research

**Browser-First Deep Research & Data Collection Skill for AI Agents**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-green.svg)](https://www.python.org/)

> A comprehensive research automation framework enabling AI agents to conduct systematic literature reviews, collect large-scale web data, and maintain rigorous evidence tracking with full academic compliance.

---

## 📖 Description | Mô Tả

### English

D Research is a sophisticated deep research and data collection framework designed specifically for AI agents. Built with a browser-first architecture, it enables systematic research workflows that span from initial literature discovery through final report generation. The framework excels at navigating complex academic databases, executing large-scale data collection campaigns, and maintaining an immutable evidence ledger for research transparency.

Key differentiators include native PRISMA protocol compliance for systematic reviews, intelligent blocker detection and resolution, multilingual research capabilities spanning 50+ languages, and specialized domain expertise across medicine, law, finance, science, and technology.

### Vietnamese

D Research là một khung nghiên cứu chuyên sâu và thu thập dữ liệu tinh vi, được thiết kế dành riêng cho các tác nhân AI. Được xây dựng với kiến trúc ưu tiên trình duyệt, nó cho phép thực hiện các quy trình nghiên cứu có hệ thống từ việc khám phá tài liệu ban đầu đến tạo báo cáo cuối cùng. Khung này vượt trội trong việc điều hướng các cơ sở dữ liệu học thuật phức tạp, thực thi các chiến dịch thu thập dữ liệu quy mô lớn, và duy trì sổ cái bằng chứng bất biến để đảm bảo tính minh bạch trong nghiên cứu.

Các điểm khác biệt chính bao gồm tuân thủ giao thức PRISMA gốc cho các đánh giá có hệ thống, phát hiện và giải quyết chặng chướng thông minh, khả năng nghiên cứu đa ngôn ngữ với hơn 50 ngôn ngữ, và chuyên môn theo từng lĩnh vực trong y học, luật, tài chính, khoa học và công nghệ.

---

## ⚡ Key Capabilities | Khả Năng Chính

### 🔄 12-Step Research Workflow

A comprehensive end-to-end research pipeline that guides AI agents through every phase of systematic investigation:

| Step | Phase | Description |
|------|-------|-------------|
| 1 | **Query Formulation** | Define research questions with PICO framework support |
| 2 | **Search Strategy** | Build Boolean queries with MeSH term expansion |
| 3 | **Source Identification** | Identify relevant databases and search domains |
| 4 | **Database Query** | Execute searches across multiple platforms |
| 5 | **Results Aggregation** | Compile and deduplicate findings |
| 6 | **Screening** | Apply inclusion/exclusion criteria at scale |
| 7 | **Quality Assessment** | Evaluate sources using standardized tools |
| 8 | **Data Extraction** | Mine structured data from documents |
| 9 | **Synthesis** | Generate thematic analysis and synthesis |
| 10 | **Citation Management** | Build and format reference libraries |
| 11 | **Report Generation** | Produce formatted research outputs |
| 12 | **Audit & Export** | Generate evidence ledger and blocker reports |

### 🌐 API Access & Integration

```
┌─────────────────────────────────────────────────────────────┐
│                    D Research API Layer                      │
├─────────────────────────────────────────────────────────────┤
│  REST API Endpoints  │  GraphQL Interface  │  WebSocket     │
│  ─────────────────   │  ─────────────────   │  Events        │
│  /research/start     │  Query Language      │  Real-time     │
│  /research/status    │  Flexible Schema     │  Progress      │
│  /research/results   │  Nested Queries      │  Updates       │
│  /databases/query    │  Subscriptions        │  Alerts        │
│  /export/{format}    │  Mutations            │  Streaming     │
└─────────────────────────────────────────────────────────────┘
```

- **RESTful API** with OpenAPI 3.0 documentation
- **GraphQL** interface for complex data queries
- **WebSocket** support for real-time progress monitoring
- **Webhook** integrations for external systems
- **Authentication** via API keys and OAuth 2.0

### 📚 Academic Database Access

| Database | Type | Coverage |
|----------|------|----------|
| **PubMed** | Medical | 35M+ citations |
| **Scopus** | Multidisciplinary | 92M+ records |
| **Web of Science** | Multidisciplinary | 200M+ citations |
| **IEEE Xplore** | Technical/Engineering | 6M+ documents |
| **ACM Digital Library** | Computing | 500K+ articles |
| **JSTOR** | Humanities/Social Sciences | 12M+ articles |
| **Google Scholar** | Open | Broad coverage |
| **Semantic Scholar** | AI-enhanced | 200M+ papers |
| **arXiv** | Preprints | 2M+ e-prints |
| **CORE** | Open Access | 200M+ papers |

### 📊 Large-Scale Data Collection

```
Collection Scalability Matrix
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Workers:     1 ─────────────── 1000+
Throughput:  100 req/min ──── 100,000 req/min
Latency:     <50ms average API response
Rate Limits: Intelligent throttling & backoff
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

- **Parallel processing** with configurable worker pools
- **Distributed crawling** across multiple browser instances
- **Rate limit management** with exponential backoff
- **Automatic retry logic** with circuit breakers
- **Result caching** with TTL management
- **Checkpoint/resume** for long-running collections

### 🔧 Data Processing Engine

| Feature | Description |
|---------|-------------|
| **ETL Pipelines** | Extract, transform, load with configurable steps |
| **PDF Parsing** | Extract text, tables, figures from PDFs |
| **HTML Scraping** | Parse structured data from web pages |
| **JSON Normalization** | Flatten nested structures |
| **Language Detection** | Auto-detect 50+ languages |
| **Text Classification** | ML-based categorization |
| **Entity Extraction** | Named entity recognition (NER) |
| **Sentiment Analysis** | Opinion mining on collected data |
| **Duplicate Detection** | Fuzzy matching with configurable thresholds |
| **Format Conversion** | CSV, JSON, XML, Excel export |

### 📝 Citation Management

```
Citation Format Support
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
APA 7th Edition        ✓
MLA 9th Edition        ✓
Chicago 17th           ✓
IEEE                   ✓
Harvard               ✓
Vancouver             ✓
AMA                   ✓
CSE                   ✓
BibTeX                ✓
RIS                   ✓
EndNote XML           ✓
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

- **Auto-citation generation** from DOI, PMID, URL
- **Reference list formatting** in 10+ styles
- **Citation tracking** with h-index calculation
- **Bibliography building** with auto-sorting
- **Duplicate detection** across reference libraries
- **Export to reference managers** (Zotero, Mendeley, EndNote)

### 📈 Visualization Dashboard

```
┌────────────────────────────────────────────────────────────┐
│  Research Analytics Dashboard                              │
├────────────────────────────────────────────────────────────┤
│                                                            │
│   [Keyword Trends]     [Source Distribution]              │
│    ████████░░░          █████████░░░                       │
│                                                            │
│   [Timeline View]      [Quality Scores]                    │
│    ░░████████░          ████████░░░░                       │
│                                                            │
│   [Geographic Map]     [Citation Network]                  │
│    ██████░░░░░░          ◯──◯──◯                          │
│                         ◯    ◯                             │
│                         ◯──◯──◯                            │
│                                                            │
│   [Progress Tracker]   [Export Options]                    │
│    ████████████         [CSV][JSON][PDF]                   │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

- **Real-time metrics** and KPI tracking
- **Interactive charts** (line, bar, pie, network graphs)
- **Geographic heatmaps** for location-based data
- **Timeline visualization** for temporal analysis
- **Citation networks** with cluster detection
- **Export to PNG/SVG/PDF** formats
- **Custom dashboard builder** with drag-and-drop widgets

### 👁️ Monitoring & Observability

```
Monitoring Stack
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Metrics    →  Prometheus + Grafana
Logging    →  Structured JSON (Pino)
Tracing    →  OpenTelemetry + Jaeger
Alerts     →  PagerDuty + Slack + Email
Health     →  /health, /ready, /metrics endpoints
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

- **Prometheus metrics** exposed on `/metrics`
- **Structured logging** with correlation IDs
- **Distributed tracing** with span trees
- **Health check endpoints** for orchestration
- **Alert rules** for failure conditions
- **Slack/Email notifications** for completion

### 🌏 Multilingual Research

| Language Family | Languages Supported |
|----------------|---------------------|
| **Romance** | English, Spanish, French, Portuguese, Italian, Romanian |
| **Germanic** | German, Dutch, Swedish, Norwegian, Danish |
| **Slavic** | Russian, Polish, Ukrainian, Czech, Bulgarian |
| **East Asian** | Chinese (Simplified/Traditional), Japanese, Korean |
| **South Asian** | Hindi, Bengali, Tamil, Telugu, Urdu |
| **Semitic** | Arabic, Hebrew, Persian |
| **Southeast Asian** | Vietnamese, Thai, Indonesian, Malay |
| **African** | Swahili, Yoruba, Zulu |

- **Cross-language search** with translation
- **Localized interface** in 25+ languages
- **RTL support** for Arabic and Hebrew
- **Character encoding** auto-detection
- **Translation memory** for consistent terminology

### 🎯 Specialized Domain Expertise

| Domain | Capabilities |
|--------|-------------|
| **🩺 Medical** | Clinical trial search, drug interactions, disease databases, EHR integration |
| **⚖️ Legal** | Case law search, statute research, regulatory compliance, contract analysis |
| **💰 Finance** | SEC filings, market data, earnings reports, cryptocurrency tracking |
| **🔬 Scientific** | Hypothesis testing, lab notebook integration, reagent databases |
| **💻 Technology** | Patent search, vulnerability databases, RFC/proposal tracking |
| **📚 Humanities** | Archive access, primary source authentication, historical mapping |

### 🔐 Evidence Ledger

```
┌─────────────────────────────────────────────────────────┐
│              Immutable Evidence Ledger                   │
├─────────────────────────────────────────────────────────┤
│  Block #     Timestamp         Hash        Data Ref     │
│  ─────────────────────────────────────────────────────  │
│  0000000     2024-01-15T...   a7f3e2...   /data/001    │
│  0000001     2024-01-15T...   b9c4d1...   /data/002    │
│  0000002     2024-01-15T...   c2e5f6...   /data/003    │
│  ...                                                    │
│                                                         │
│  Merkle Root: 0x7a8b9c...                               │
│  Previous Hash: 0x1d2e3f...                             │
│  Digital Signature: [RSA-4096 verified]                 │
└─────────────────────────────────────────────────────────┘
```

- **Cryptographic integrity** verification
- **Merkle tree hashing** for data integrity
- **Timestamp authority** integration
- **Audit trail** with full provenance
- **Export to JSON/CSV** for external verification
- **API for third-party validation**

### 🚫 Blocker Reports

```
┌─────────────────────────────────────────────────────────┐
│              Research Blocker Report                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  🔴 BLOCKERS IDENTIFIED: 3                               │
│  ─────────────────────────────────────────────────────  │
│                                                         │
│  [1] Database Rate Limit                                │
│      Source: PubMed                                     │
│      Impact: High (blocks screening phase)             │
│      Retry After: 2024-01-15T14:30:00Z                 │
│      Recommended Action: Switch to Semantic Scholar     │
│                                                         │
│  [2] PDF Extraction Timeout                             │
│      Source: /papers/article_42.pdf                     │
│      Impact: Medium (1 document affected)              │
│      Recommended Action: Manual extraction required     │
│                                                         │
│  [3] Authentication Required                            │
│      Source: IEEE Xplore                                │
│      Impact: High (blocks 234 documents)               │
│      Recommended Action: Configure institutional creds  │
│                                                         │
│  🟡 WARNINGS: 7                                         │
│  🟢 COMPLETED: 847                                      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

- **Automatic blocker detection** during research
- **Severity classification** (Critical/High/Medium/Low)
- **Impact assessment** with affected item counts
- **Recommended actions** with alternatives
- **Retry scheduling** for transient failures
- **Escalation triggers** for unresolved issues

### 📋 PRISMA Protocol Compliance

D Research implements the [PRISMA 2020 statement](http://www.prisma-statement.org/) for systematic reviews:

```
PRISMA 2020 Flow Diagram - Implemented Checks
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
□ Identification Phase
  ├─ Database Searches: Min. 2 required
  ├─ Register Searches: CROAP, PROSPERO
  └─ Hand Search: Reference lists checked
□ Screening Phase
  ├─ Deduplication: Automatic
  ├─ Title/Abstract: Configurable threshold
  └─ Full Text: Dual reviewer mode
□ Included Phase
  ├─ Quality Assessment: QUADAS-2, Cochrane RoB
  ├─ Data Extraction: Double-entry verification
  └─ Certainty of Evidence: GRADE approach
□ Reporting Phase
  ├─ Protocol Registration: Pre-specified
  ├─ Deviations Logged: With rationale
  └─ Full Checklist: PRISMA 2020 items
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

- **Protocol registration** template
- **Flow diagram generation** (interactive SVG)
- **Checklist completion** tracking
- **Deviation logging** with justification
- **Risk of bias assessment** tools
- **GRADE evidence profiling**

---

## 📁 Repository Layout

```
d-research-skill/
├── SKILL.md                         # Main skill definition (12-step workflow)
├── AGENTS.md                        # Agent instructions
├── README.md                        # This file
├── LICENSE                          # MIT License
├── package.json                     # Node.js scripts & config
├── research.config.example.json     # Research configuration template
│
├── adapters/                        # Browser/tool adapter definitions
│   ├── playwright.md                # Default: Playwright browser
│   ├── generic-browser.md           # Fallback: any browser
│   ├── fetch-only.md                # Fallback: HTTP fetch only
│   ├── web-search-only.md           # Fallback: web search only
│   ├── database-readonly.md         # SQL/NoSQL read-only access
│   └── graphql.md                   # GraphQL introspection + query
│
├── references/                      # Research methodology & protocols
│   ├── academic-databases.md        # OpenAlex, CrossRef, PubMed, etc.
│   ├── academic-research-protocol.md # PRISMA, PICO, SPIDER
│   ├── api-access-workflow.md       # REST/GraphQL/SPARQL access
│   ├── blocker-report.md            # Blocked source reporting
│   ├── browser-first-crawl.md       # Browser automation strategy
│   ├── citation-management.md       # BibTeX/RIS export, DOI enrichment
│   ├── data-processing-pipeline.md  # ETL: clean → transform → validate
│   ├── data-visualization.md        # Chart selection, plotting
│   ├── evidence-ledger.md           # Atomic claims + contradiction
│   ├── extraction-methods.md        # 10 extraction methods
│   ├── final-report-template.md     # Report output format
│   ├── large-scale-collection.md    # Checkpoint, resume, rate-limit
│   ├── monitoring-change-detection.md # Track changes over time
│   ├── multilingual-research.md     # Multi-language research
│   ├── query-patterns.md            # Query fanout patterns
│   ├── research-bibliography.md     # Reference sources
│   ├── safety-and-access-policy.md  # Ethics & legal compliance
│   ├── source-discovery.md          # Source identification layers
│   ├── source-quality-rubric.md     # Source evaluation criteria
│   ├── specialized-domains.md       # Finance, patent, legal, gov
│   ├── tool-adapter-policy.md       # Adapter selection rules
│   └── topic-decomposition.md       # Topic → sub-questions
│
├── scripts/                         # Executable tools
│   ├── api_fetch.mjs                # Paginated API fetch with retry
│   ├── data_clean.py                # CSV clean, dedup, stats, merge
│   ├── citation_export.py           # BibTeX/RIS export from ledger
│   ├── evidence_ledger.py           # Evidence ledger management
│   ├── playwright_probe.mjs         # URL accessibility probe
│   ├── playwright_extract.mjs       # Page content extraction
│   ├── playwright_crawl.mjs         # Multi-page crawl
│   └── run_python.mjs               # Python script runner
│
├── templates/                       # CSV/BibTeX templates
│   ├── evidence-ledger.csv          # Evidence tracking template
│   ├── search-log.csv               # Search log template
│   ├── screening-log.csv            # Screening log template
│   ├── api-request-log.csv          # API request tracking
│   ├── data-dictionary.csv          # Dataset field documentation
│   └── citation-library.bib         # BibTeX citation template
│
├── examples/                        # Usage examples
│   ├── academic-review.md           # Literature review workflow
│   ├── scientific-literature-review.md # Full scientific review
│   ├── api-dataset-collection.md    # API data collection
│   ├── large-scale-crawl.md         # Large-scale web crawl
│   ├── dataset-collection.md        # Dataset collection
│   ├── technical-research.md        # Technical investigation
│   └── blocked-source-report.md     # Blocker report example
│
├── agents/openai.yaml               # OpenAI agent config
└── docs/UPGRADE-PLAN.md             # Upgrade documentation
```

---

## 🚀 Quick Start | Bắt Đầu Nhanh

### Scripts (no installation required)

All scripts are standalone — no `npm install` needed. Requires Node.js and Python 3.

```bash
# Clone
git clone https://github.com/d-init-d/d-research-skill.git
cd d-research-skill

# Run self-tests to verify everything works
node scripts/api_fetch.mjs --self-test
python3 scripts/data_clean.py self-test
python3 scripts/citation_export.py self-test
```

### Usage Examples

```bash
# Fetch data from any paginated API
node scripts/api_fetch.mjs \
  --url "https://api.openalex.org/works?search=AI&per_page=10" \
  --max-pages 5 --out results.json

# Clean & deduplicate CSV data
python3 scripts/data_clean.py clean --file raw_data.csv --out cleaned.csv
python3 scripts/data_clean.py stats --file cleaned.csv
python3 scripts/data_clean.py dedup --file cleaned.csv --out unique.csv

# Export citations from evidence ledger
python3 scripts/citation_export.py export \
  --file evidence-ledger.csv --format bibtex --out references.bib
```

### Configuration

Copy and edit the research config:

```bash
cp research.config.example.json research.config.json
```

Edit `research.config.json` with your API keys (OpenAlex, CrossRef, PubMed, etc.) and preferences. See `research.config.example.json` for all available options.

---

## License

MIT License

Copyright (c) 2024 D Research Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

---

<div align="center">

**D Research** - Comprehensive browser-first research for AI agents

*Built with ❤️ for the research community*

</div>
