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
d-research/
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .env.example
├── docker-compose.yml
├── Dockerfile
│
├── src/
│   └── dresearch/
│       ├── __init__.py
│       ├── __version__.py
│       │
│       ├── core/
│       │   ├── __init__.py
│       │   ├── agent.py              # AI agent interface
│       │   ├── browser.py            # Browser automation
│       │   ├── workflow.py           # 12-step workflow engine
│       │   ├── scheduler.py          # Task scheduling
│       │   └── config.py             # Configuration management
│       │
│       ├── collectors/
│       │   ├── __init__.py
│       │   ├── api_client.py         # API access layer
│       │   ├── database_searcher.py  # Academic DB queries
│       │   ├── web_scraper.py        # Web data collection
│       │   ├── pdf_extractor.py      # PDF content extraction
│       │   └── scale_controller.py   # Large-scale orchestration
│       │
│       ├── processing/
│       │   ├── __init__.py
│       │   ├── etl_pipeline.py       # ETL pipelines
│       │   ├── text_processor.py     # NLP processing
│       │   ├── entity_extractor.py   # NER pipeline
│       │   ├── deduplicator.py       # Duplicate detection
│       │   └── language_detector.py  # Multilingual support
│       │
│       ├── citations/
│       │   ├── __init__.py
│       │   ├── generator.py          # Citation creation
│       │   ├── formatter.py          # Style formatting
│       │   ├── bibliography.py       # Reference management
│       │   └── exporter.py           # Export to managers
│       │
│       ├── evidence/
│       │   ├── __init__.py
│       │   ├── ledger.py             # Blockchain ledger
│       │   ├── hasher.py            # Hash computation
│       │   ├── verifier.py           # Integrity checks
│       │   └── block.py             # Block management
│       │
│       ├── monitoring/
│       │   ├── __init__.py
│       │   ├── metrics.py           # Prometheus metrics
│       │   ├── logger.py            # Structured logging
│       │   ├── tracer.py            # Distributed tracing
│       │   ├── alerts.py            # Alert management
│       │   └── dashboard.py         # Dashboard components
│       │
│       ├── visualization/
│       │   ├── __init__.py
│       │   ├── charts.py            # Chart generation
│       │   ├── network.py          # Network graphs
│       │   ├── timeline.py         # Timeline views
│       │   ├── map.py              # Geographic maps
│       │   └── exporter.py         # Export utilities
│       │
│       ├── prisma/
│

py
│   │   ├── financial.py        # Nguồn tài chính
│   │   ├── patents.py          # Cơ sở dữ liệu sáng chế
│   │   ├── legal.py            # Nguồn pháp lý
│   │   ├── government.py       # Dữ liệu chính phủ
│   │   └── geospatial.py       # GIS/bản đồ
│   ├── multilingual/
│   │   ├── __init__.py
│   │   ├── translator.py       # Dịch vụ dịch
│   │   ├── search.py           # Tìm kiếm xuyên ngôn ngữ
│   │   └── parser.py           # Phân tích đa ngôn ngữ
│   ├── monitoring/
│   │   ├── __init__.py
│   │   ├── tracker.py          # Phát hiện thay đổi
│   │   └── notifier.py         # Hệ thống cảnh báo
│   └── prisma/
│       ├── __init__.py
│       ├── protocol.py         # Giao thức đánh giá
│       ├── search.py           # Tìm kiếm có hệ thống
│       └── screening.py        # Sàng lọc eligibility
│
├── references/
│   ├── __init__.py
│   ├── taxonomy.py             # Phân loại nguồn
│   ├── schemas.py              # Schema dữ liệu
│   └── policies.py             # Chính sách truy cập
│
├── adapters/
│   ├── __init__.py
│   ├── base.py                 # Lớp adapter cơ sở
│   ├── web_scraper.py          # Adapter thu thập web
│   ├── api_client.py           # Adapter API tổng quát
│   └── database.py             # Adapter cơ sở dữ liệu
│
├── scripts/
│   ├── __init__.py
│   ├── setup.py                # Thiết lập môi trường
│   ├── batch_collect.py        # Công cụ thu thập hàng loạt
│   ├── export_data.py          # Tiện ích xuất dữ liệu
│   ├── generate_report.py      # Tạo báo cáo
│   └── monitor_sources.py      # Giám sát nguồn
│
├── templates/
│   ├── __init__.py
│   ├── research_template.md    # Mẫu tài liệu nghiên cứu
│   ├── citation_template.bib    # Mẫu trích dẫn BibTeX
│   ├── prisma_template.md      # Mẫu sơ đồ PRISMA
│   └── blocker_report.md       # Mẫu báo cáo blocker
│
├── examples/
│   ├── __init__.py
│   ├── basic_research.py       # Ví dụ nghiên cứu cơ bản
│   ├── academic_review.py      # Đánh giá tài liệu học thuật
│   ├── financial_analysis.py   # Thu thập dữ liệu tài chính
│   ├── patent_search.py        # Ví dụ tìm kiếm sáng chế
│   ├── multilingual_research.py # Nghiên cứu đa ngôn ngữ
│   └── custom_adapter.py       # Phát triển adapter tùy chỉnh
│
├── docs/
│   ├── README.md               # File này
│   ├── QUICKSTART.md           # Hướng dẫn bắt đầu nhanh
│   ├── API_REFERENCE.md        # Tài liệu API
│   ├── RESEARCH_WORKFLOW.md    # Tài liệu quy trình
│   ├── DOMAIN_GUIDES/
│   │   ├── financial.md
│   │   ├── patents.md
│   │   ├── legal.md
│   │   └── government.md
│   └── PRISMA_GUIDE.md         # Hướng dẫn giao thức PRISMA
│
├── tests/
│   ├── __init__.py
│   ├── test_scraper.py
│   ├── test_api_clients.py
│   ├── test_academic.py
│   ├── test_collector.py
│   ├── test_processor.py
│   └── test_citation.py
│
├── config/
│   ├── __init__.py
│   ├── settings.py             # Quản lý cấu hình
│   ├── api_keys.json           # Lưu trữ API key (gitignored)
│   └── rate_limits.json        # Cấu hình giới hạn tốc độ
│
├── notebooks/
│   ├── data_analysis.ipynb     # Ví dụ phân tích dữ liệu
│   ├── visualization.ipynb     # Ví dụ biểu đồ
│   └── research_demo.ipynb     # Demo quy trình nghiên cứu
│
├── .env.example                # Mẫu biến môi trường
├── .gitignore
├── requirements.txt            # Phụ thuộc Python
├── package.json                # Cấu hình package Node.js
├── setup.py                    # Thiết lập package Python
├── pyproject.toml              # Cấu hình Python hiện đại
├── CLAUDE.md                   # Hướng dẫn Claude AI
├── LICENSE                    # Giấy phép MIT
└── README.md                   # File này
```

---

## Bắt đầu nhanh

### Cài đặt

```bash
# Clone repository
git clone https://github.com/your-org/d-research.git
cd d-research

# Cài đặt phụ thuộc Python
pip install -r requirements.txt

# Cài đặt phụ thuộc Node.js (cho tự động hóa trình duyệt)
npm install

# Sao chép mẫu môi trường
cp .env.example .env
```

### Cấu hình

Chỉnh sửa `.env` với các API key của bạn:

```env
# Academic APIs
OPENALEX_API_KEY=your_openalex_key
CROSSREF_API_KEY=your_crossref_key
PUBMED_API_KEY=your_pubmed_key

# Data APIs
SEMANTIC_SCHOLAR_API_KEY=your_s2_key
ARXIV_API_KEY=your_arxiv_key

# Optional services
TRANSLATION_API_KEY=your_translation_key
```

### Sử dụng cơ bản

```python
from src.main import DResearch

# Khởi tạo phiên nghiên cứu
research = DResearch(
    query="tác động của trí tuệ nhân tạo lên y tế",
    max_sources=50
)

# Thực thi quy trình 12 bước
results = await research.execute()

# Truy cập dữ liệu đã thu thập
documents = results['documents']
evidence = results['evidence']
citations = results['citations']

# Xuất sang BibTeX
research.export_citations('references.bib', format='bibtex')
```

### Nâng cao: Đánh giá tài liệu PRISMA

```python
from src.prisma import PRISMAReview

review = PRISMAReview(
    research_question="Tác động của AI lên chẩn đoán y tế là gì?",
    inclusion_criteria=["peer-reviewed", "2018-2024", "English"],
    exclusion_criteria=["non-empirical", "opinion pieces"]
)

# Thực thi đánh giá có hệ thống
report = await review.execute()

# Tạo sơ đồ PRISMA
review.generate_flowchart('prisma_diagram.png')
```

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
