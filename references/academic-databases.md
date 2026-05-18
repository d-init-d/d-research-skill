# Academic Literature Database Access

This guide teaches the agent how to access, search, and analyze academic literature using free and open APIs. Academic database research is foundational for literature reviews, systematic reviews, meta-analyses, and research synthesis tasks.

## When to Use

### Literature Review

- Initial exploration of a research topic
- Surveying existing work before proposing new research
- Identifying gaps in current knowledge
- Finding related work for introduction sections

### Paper Discovery

- Finding relevant papers on a specific topic
- Identifying seminal works and key authors
- Discovering papers published within date ranges
- Finding papers by specific authors or institutions

### Citation Analysis

- Tracing how knowledge evolved in a field
- Identifying highly influential papers
- Mapping research communities and collaborations
- Tracking citation patterns and trends

### Dataset Discovery

- Finding papers that introduce or use specific datasets
- Identifying datasets relevant to a research question
- Verifying dataset citations for reproducibility
- Discovering new datasets in a domain

## Free/Open APIs (No Key Required)

These APIs provide free access to academic metadata and abstracts. No registration or API key is needed.

### OpenAlex

**Best for**: Comprehensive paper discovery with citation data

**Base URL**: `https://api.openalex.org`

OpenAlex is a free, open catalog of scholarly papers, authors, institutions, and publishers. It indexes over 240 million papers and provides rich citation data.

**Search Works**:

```
GET https://api.openalex.org/works?search=machine+learning+healthcare
```

**Filter by Year Range**:

```
GET https://api.openalex.org/works?search=transformer+models&filter=publication_year:2020-2026
```

**Filter by Author**:

```
GET https://api.openalex.org/works?search=neural+networks&filter=author.id:A12345678
```

**Filter by Institution**:

```
GET https://api.openalex.org/works?search=climate+change&filter=institutions.id:I12345678
```

**Pagination (Cursor-Based)**:

```
GET https://api.openalex.org/works?search=quantum+computing&cursor=*
```

OpenAlex uses cursor pagination. The response includes `meta.next_cursor`. Pass this as the cursor parameter:

```
GET https://api.openalex.org/works?search=quantum+computing&cursor=CursorValueHere
```

**Rate Limits**:

- 10 requests per second with `mailto` parameter
- Include your email: `https://api.openalex.org/works?search=X&mailto=user@example.com`

**Response Fields**:

```json
{
  "id": "W123456789",
  "doi": "https://doi.org/10.1234/example",
  "title": "Paper Title",
  "display_name": "Paper Title",
  "abstract": "Paper abstract text...",
  "publication_year": 2024,
  "citation_count": 150,
  "cited_by_count": 150,
  "authorships": [
    {
      "author": {
        "id": "A123456",
        "display_name": "Author Name"
      },
      "institutions": [
        {
          "id": "I123456",
          "display_name": "University Name"
        }
      ]
    }
  ],
  "concepts": [
    {
      "id": "C123456",
      "display_name": "Machine Learning",
      "level": 0
    }
  ],
  "referenced_works": ["W111111", "W222222"],
  "related_works": ["W333333", "W444444"]
}
```

**Key Operations**:

- `cited_by_count`: Number of papers citing this work
- `referenced_works`: IDs of papers this work cites
- `related_works`: IDs of semantically similar papers
- `concepts`: Topic classification tags

### CrossRef

**Best for**: Full metadata, references, funding information

**Base URL**: `https://api.crossref.org`

CrossRef provides comprehensive DOI-based metadata including references, funding, and license information.

**Search Works**:

```
GET https://api.crossref.org/works?query=machine+learning+diagnosis
```

**Pagination**:

```
GET https://api.crossref.org/works?query=deep+learning&rows=100&offset=0
```

- `rows`: Number of results (max 100)
- `offset`: Starting position

**Filter by DOI**:

```
GET https://api.crossref.org/works/10.1038/nature12373
```

**Filter by Author**:

```
GET https://api.crossref.org/works?query.author=smith&query=machine+learning
```

**Rate Limits**:

- Uses "polite pool" - include User-Agent with email:
- Header: `User-Agent: YourApp/1.0 (mailto:user@example.com)`

**Response Fields**:

```json
{
  "status": "ok",
  "message-type": "work",
  "message": {
    "DOI": "10.1234/example",
    "title": ["Paper Title"],
    "abstract": "Abstract text...",
    "author": [
      {
        "given": "John",
        "family": "Smith",
        "affiliation": [{"name": "University"}]
      }
    ],
    "published": {
      "date-parts": [[2024, 1, 15]]
    },
    "container-title": ["Journal Name"],
    "volume": "12",
    "issue": "3",
    "page": "123-145",
    "citation-count": 150,
    "references-count": 89,
    "references": [
      {
        "DOI": "10.5678/reference",
        "article-title": "Referenced Paper",
        "author": "Author Name",
        "year": 2020
      }
    ],
    "funder": [
      {
        "name": "National Science Foundation",
        "DOI": "10.13039/501100008982"
      }
    ],
    "license": [
      {
        "URL": "https://creativecommons.org/licenses/by/4.0/",
        "start": {"date-time": "2024-01-01"}
      }
    ]
  }
}
```

**Key Operations**:

- `references`: Full reference list with DOIs when available
- `funder`: Funding agency information
- `license`: Open access licensing details

### Semantic Scholar

**Best for**: Citation graphs, related papers, paper recommendations

**Base URL**: `https://api.semanticscholar.org/graph/v1`

Semantic Scholar provides AI-powered paper discovery with citation network data and paper recommendations.

**Search Papers**:

```
GET https://api.semanticscholar.org/graph/v1/paper/search?query=machine+learning+medical&limit=100
```

**Get Paper Details**:

```
GET https://api.semanticscholar.org/graph/v1/paper/ARXIV:2103.14030?fields=title,authors,abstract,citations,references,year,citationCount,influentialCitationCount
```

**Get Paper by DOI**:

```
GET https://api.semanticscholar.org/graph/v1/paper/DOI:10.1038/nature12373?fields=title,abstract,citationCount
```

**Get Paper Citations**:

```
GET https://api.semanticscholar.org/graph/v1/paper/ARXIV:2103.14030/citations?fields=title,authors,year,citationCount&limit=100
```

**Get Paper References**:

```
GET https://api.semanticscholar.org/graph/v1/paper/ARXIV:2103.14030/references?fields=title,authors,year&limit=100
```

**Get Related Papers**:

```
GET https://api.semanticscholar.org/graph/v1/paper/ARXIV:2103.14030?fields=relatedPapers&limit=50
```

**Rate Limits**:

- 100 requests per 5 minutes (free tier)
- 1000 requests per 5 minutes (with free API key from scholar.org)

**Available Fields**:

- `title`, `abstract`, `year`, `venue`, `citationCount`
- `influentialCitationCount` (highly cited papers)
- `authors` (with author IDs)
- `citations` (papers citing this)
- `references` (papers this cites)
- `relatedPapers` (semantically similar)

### PubMed E-utilities

**Best for**: Biomedical, clinical, and life sciences literature

**Base URL**: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`

PubMed provides access to MEDLINE database covering biomedical literature.

**Search (esearch.fcgi)**:

```
GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=machine+learning+diagnosis&retmax=100&usehistory=n
```

**Key Parameters**:

- `db`: Database name (pubmed, pmc, books, etc.)
- `term`: Search query (supports MeSH terms, boolean operators)
- `retmax`: Maximum results
- `usehistory`: y/n - store results on server for retrieval
- `retmode`: json/xml

**Fetch Details (efetch.fcgi)**:

```
GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=35027834&retmode=xml
```

**Fetch with History**:

```
GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=machine+learning&retmax=100&usehistory=y
```

Then retrieve results:

```
GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=machine+learning&retmax=100&usehistory=y&query_key=1&WebEnv=COEID_12345
```

**Combined Search and Fetch**:

```
GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=machine+learning+diagnosis&retmax=100&retmode=json
```

Then use returned IDs with efetch.

**Link Navigation**:

```
GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi?dbfrom=pubmed&id=35027834&linkname=pubmed_pmc
```

**Rate Limits**:

- 3 requests per second (without API key)
- 10 requests per second (with API key: add `&api_key=YOURKEY`)

Get free API key from: https://www.ncbi.nlm.nih.gov/account/

### arXiv

**Best for**: Physics, computer science, mathematics, quantitative biology

**Base URL**: `http://export.arxiv.org/api/query`

arXiv provides preprints in physics, math, CS, and related fields.

**Search All Fields**:

```
GET http://export.arxiv.org/api/query?search_query=all:machine+learning&start=0&max_results=100
```

**Search by Title**:

```
GET http://export.arxiv.org/api/query?search_query=ti:neural+network&start=0&max_results=100
```

**Search by Author**:

```
GET http://export.arxiv.org/api/query?search_query=au:smith&start=0&max_results=100
```

**Search by Abstract**:

```
GET http://export.arxiv.org/api/query?search_query=abs:transformer+attention&start=0&max_results=100
```

**Search by Category**:

```
GET http://export.arxiv.org/api/query?search_query=cat:cs.LG+AND+all:reinforcement+learning&start=0&max_results=100
```

**Categories**: cs.AI, cs.LG, cs.CL, cs.CV, stat.ML, physics.gen-ph, math.CO, etc.

**Date Range**:

```
GET http://export.arxiv.org/api/query?search_query=all:quantum&start=0&max_results=100&datefrom=2023-01-01&dateto=2024-12-31
```

**Pagination**:

```
GET http://export.arxiv.org/api/query?search_query=all:graph+neural+network&start=100&max_results=100
```

- `start`: Offset for pagination
- `max_results`: Results per query (max 2000, recommended 100-200)

**Output Format**: Atom XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2301.12345v1</id>
    <title>Paper Title</title>
    <summary>Abstract text...</summary>
    <author><name>Author Name</name></author>
    <published>2023-01-15T00:00:00Z</published>
    <category term="cs.LG"/>
    <arxiv:doi xmlns:arxiv="http://arxiv.org/schemas/atom">10.1234/example</arxiv:doi>
    <link href="http://arxiv.org/abs/2301.12345v1" rel="alternate"/>
  </entry>
</feed>
```

**Rate Limits**:

- 1 request per 3 seconds recommended
- Batch requests to reduce load
- Do not exceed 1 request per second

### CORE

**Best for**: Open access full-text papers and datasets

**Base URL**: `https://api.core.ac.uk/v3`

CORE aggregates open access research outputs from repositories worldwide.

**Search Papers** (requires free API key):

Register at: https://core.ac.uk/api-keys

```
GET https://api.core.ac.uk/v3/search/works?q=machine+learning&limit=100&offset=0
```

**Search with Filters**:

```
GET https://api.core.ac.uk/v3/search/works?q=climate+change&limit=100&year=2023&isOpenAccess=true
```

**Get Paper by ID**:

```
GET https://api.core.ac.uk/v3/works/WORK_ID
```

**Get Paper by DOI**:

```
GET https://api.core.ac.uk/v3/works/doi/10.1234/example
```

**Download Full Text** (if available):

```
GET https://api.core.ac.uk/v3/works/WORK_ID/download
```

**Rate Limits**:

- Requires free API key from core.ac.uk
- Varies by plan (1000-10000 requests/day free)

**Response Fields**:

```json
{
  "id": 12345678,
  "title": "Paper Title",
  "abstract": "Abstract text...",
  "authors": [{"name": "Author Name"}],
  "year": 2024,
  "downloadUrl": "https://...",
  "fullText": "Full text if available...",
  "topics": [{"name": "Computer Science"}],
  "repositoryName": "arXiv",
  "isOpenAccess": true
}
```

### DOAJ

**Best for**: Open access journal discovery

**Base URL**: `https://doaj.org/api/v2`

Directory of Open Access Journals - discover OA journals by subject.

**Search Articles**:

```
GET https://doaj.org/api/v2/search/articles/machine+learning?page=1&pageSize=100
```

**Search Journals**:

```
GET https://doaj.org/api/v2/search/journals/climate+change?page=1&pageSize=50
```

**Get Article by DOI**:

```
GET https://doaj.org/api/v2/articles/10.1234/example
```

**Filter by Subject**:

```
GET https://doaj.org/api/v2/search/articles/biology?subject=Physics&pageSize=100
```

**Response Fields**:

```json
{
  "results": [
    {
      "id": "article-id",
      "bibjson": {
        "title": "Article Title",
        "abstract": "Abstract...",
        "author": [{"name": "Author Name"}],
        "year": "2024",
        "journal": {
          "title": "Journal Name",
          "publisher": "Publisher Name"
        }
      },
      "doi": "10.1234/example",
      "license": [{"title": "CC BY 4.0"}]
    }
  ],
  "total": 12345
}
```

**Rate Limits**:

- Reasonable use expected
- Include User-Agent identifying your application

## APIs Needing Keys

These databases require paid subscriptions or approved API keys:

### Scopus/Elsevier

- Requires institutional subscription or paid API key
- Cost: Significant licensing fees
- **Recommendation**: Use OpenAlex and CrossRef for most use cases

### IEEE Xplore

- Requires institutional subscription or paid API
- Coverage: Electrical engineering, CS, electronics
- **Recommendation**: Use OpenAlex and Semantic Scholar for discovery

### Web of Science (Clarivate)

- Requires paid institutional access
- Coverage: Multidisciplinary, citation indexing
- **Recommendation**: Use OpenAlex for citation analysis (provides similar data)

### Google Scholar

- **No official API** available
- Third-party scrapers exist but violate Terms of Service
- Risk: IP blocking, legal issues
- **Recommendation**: Use OpenAlex, CrossRef, and Semantic Scholar instead

**Strategy for Restricted Databases**:

1. Use free APIs (OpenAlex, CrossRef, Semantic Scholar) as primary sources
2. These cover 80-90% of academic literature
3. If specific papers missing, try institutional library access
4. Contact authors directly for preprints if needed
5. Check arXiv, PubMed Central, and other OA repositories

## Workflow

### Step 1: Identify Relevant Databases for Discipline

> **Step 0 — Canonicalize the identifier.** If you already have a DOI, PMID, arXiv ID, or ISBN, resolve it first with `scripts/citation_resolver.py` before searching databases. This gives you canonical metadata in one request and short-circuits the full search loop. See `adapters/citation-resolver.md`.

| Discipline | Primary DBs |
|------------|-------------|
| General/All | OpenAlex, CrossRef, Semantic Scholar |
| Biomedical | PubMed, Semantic Scholar, OpenAlex |
| Physics/Math/CS | arXiv, OpenAlex, CrossRef |
| Engineering | IEEE Xplore*, Scopus*, OpenAlex |
| Social Sciences | OpenAlex, CrossRef, Semantic Scholar |
| Humanities | OpenAlex, CrossRef |

*indicates subscription required

### Step 2: Start with Free APIs

```
1. Begin with OpenAlex for broad search
   - Get initial paper set with citations
   
2. Use CrossRef for metadata enrichment
   - Get references, funding info
   
3. Use Semantic Scholar for:
   - Citation graphs
   - Related papers
   - Influential citation counts
```

### Step 3: Cross-Reference Results

```python
# Pseudocode for cross-referencing
paper_ids = openalex.search(topic="machine learning healthcare")
for paper_id in paper_ids:
    paper = openalex.get_paper(paper_id)
    
    # Get DOI for CrossRef lookup
    if paper.doi:
        crossref_data = crossref.get_paper(paper.doi)
        references = crossref_data.references
    
    # Get citations from Semantic Scholar
    citations = semanticscholar.get_citations(paper_id)
    related = semanticscholar.get_related(paper_id)
```

### Step 4: Enrich with CrossRef

For each paper found:

1. Look up DOI in CrossRef
2. Extract: references, funders, licenses, publication details
3. Store full reference list for backward citation analysis

### Step 5: Build Citation Network

```
Data structure for citation network:
- nodes: papers (id, title, year, authors)
- edges: citations (source_id, target_id, type)

Types of edges:
- cites: paper A cites paper B
- cited_by: paper B cited by paper A
- related_to: papers share topics/authors
```

### Step 6: Log All Searches

```python
search_log = {
    "timestamp": "2024-01-15T10:30:00Z",
    "database": "openalex",
    "query": "machine learning healthcare",
    "parameters": {
        "filter": "publication_year:2020-2026",
        "per_page": 100
    },
    "results_count": 1000,
    "cursor": "CursorValue"
}
```

## Citation Network Analysis

### Automated graph traversal

Use `scripts/citation_graph.py` for programmatic citation network building:

```bash
# Forward citations (who cites this paper?)
python scripts/citation_graph.py cited-by --doi 10.1038/nature12373 --depth 1 --max 100 --out cited-by.json

# Backward citations (what does this paper cite?)
python scripts/citation_graph.py references --doi 10.1038/nature12373 --depth 1 --max 100 --out refs.json

# Full snowball (both directions)
python scripts/citation_graph.py expand --seed seeds.csv --direction both --max 500 --out graph.json

# Coauthor network
python scripts/citation_graph.py coauthors --orcid 0000-0001-2345-6789 --out coauthors.json
```

See `references/citation-graph.md` for full documentation.

### Forward Citations (What Cites This?)

Papers published after your target paper that cite it.

**OpenAlex**:

```
GET https://api.openalex.org/works?filter=cites:W123456789
```

**Semantic Scholar**:

```
GET https://api.semanticscholar.org/graph/v1/paper/{id}/citations?fields=title,year,citationCount
```

**Interpretation**:

- Shows impact and influence
- Identifies subsequent work building on your paper
- Tracks how knowledge evolved

### Backward Citations (What Does This Paper Cite?)

Papers referenced within your target paper.

**CrossRef**:

```
GET https://api.crossref.org/works/10.1234/example
# Response includes references array
```

**OpenAlex**:

```
# referenced_works field in paper response
GET https://api.openalex.org/works/W123456789
# Look at referenced_works array
```

**Interpretation**:

- Shows foundational work
- Identifies key prior research
- Reveals intellectual lineage

### Co-citation

When two papers are cited together by a third paper.

**Analysis Method**:

1. Collect all papers citing your target
2. Extract references from each citing paper
3. Count pairs of papers that appear together
4. Higher co-citation count = stronger relationship

**Example**:

```
Paper A cites: [X, Y, Z, Target]
Paper B cites: [X, Y, Target]
Paper C cites: [X, Target]

Co-citation counts:
- X & Target: 3 (high co-citation)
- Y & Target: 2 (moderate)
- Z & Target: 1 (low)
```

### Bibliographic Coupling

When two papers cite the same references.

**Analysis Method**:

1. Extract references for each paper in your set
2. Count shared references between pairs
3. Higher shared reference count = stronger coupling

**Example**:

```
Paper A references: [X, Y, Z, W]
Paper B references: [X, Y, P, Q]
Paper C references: [Z, W, P, Q]

Coupling counts:
- A & B: 2 shared (X, Y)
- C & D: 2 shared (P, Q)
- A & C: 2 shared (Z, W)
```

**Use Cases**:

- Identify research clusters
- Find related work from same time period
- Map research communities

## Output

### Paper List (CSV/JSON)

```json
{
  "papers": [
    {
      "id": "W123456789",
      "doi": "10.1234/example",
      "title": "Paper Title",
      "authors": ["Author 1", "Author 2"],
      "year": 2024,
      "venue": "Journal Name",
      "abstract": "Abstract...",
      "citation_count": 150,
      "url": "https://...",
      "open_access": true,
      "topics": ["AI", "Healthcare"]
    }
  ]
}
```

```csv
id,title,authors,year,venue,citation_count,doi,open_access
W123456789,Paper Title,"Author 1; Author 2",2024,Journal Name,150,10.1234/example,true
```

### Citation Network Edge List

```csv
source,target,type,year
W111111,W123456789,cites,2024
W222222,W123456789,cites,2023
W123456789,W333333,cites,2024
```

### Evidence Table

```json
{
  "query": "machine learning healthcare",
  "databases_searched": ["OpenAlex", "CrossRef", "Semantic Scholar", "PubMed"],
  "date_range": "2020-2026",
  "total_papers_found": 5000,
  "papers_reviewed": 500,
  "papers_included": 100,
  "exclusion_reasons": {
    "not_relevant": 4500,
    "wrong_date_range": 200,
    "no_access": 100,
    "duplicate": 200
  },
  "included_papers": [...]
}
```

### Search Log

```json
{
  "searches": [
    {
      "database": "openalex",
      "timestamp": "2024-01-15T10:30:00Z",
      "query": "machine learning healthcare",
      "parameters": {
        "filter": "publication_year:2020-2026",
        "per_page": 100,
        "cursor": "*"
      },
      "results": 10000,
      "pagination_needed": true,
      "total_requests": 100
    },
    {
      "database": "crossref",
      "timestamp": "2024-01-15T10:45:00Z",
      "query": "deep learning diagnosis",
      "parameters": {"rows": 100, "offset": 0},
      "results": 5000,
      "requests_made": 50
    }
  ]
}
```

### Blocker Report

```json
{
  "blockers": [
    {
      "database": "Scopus",
      "status": "blocked",
      "reason": "Requires institutional subscription",
      "workaround": "Using OpenAlex and Semantic Scholar instead",
      "coverage_gap": "Some biomedical literature may be underrepresented"
    },
    {
      "database": "Web of Science",
      "status": "blocked",
      "reason": "Paid access required",
      "workaround": "OpenAlex provides similar citation data",
      "coverage_gap": "None significant for citation analysis"
    },
    {
      "database": "IEEE Xplore",
      "status": "blocked",
      "reason": "API requires subscription",
      "workaround": "Using arXiv and OpenAlex for engineering papers",
      "coverage_gap": "Some recent conference papers may be missing"
    }
  ],
  "total_coverage": "Estimated 85-90% of relevant literature accessible",
  "recommendations": [
    "Use institutional library access for specific missing papers",
    "Contact authors directly for preprints",
    "Check institutional repositories for OA versions"
  ]
}
```
