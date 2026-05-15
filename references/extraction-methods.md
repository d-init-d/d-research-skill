# Extraction Methods

Use this file when the user wants structured data or a repeatable extraction workflow.

## Extraction modes

### 1. File-first extraction

Prefer public files when available:
- CSV
- JSON
- XML
- XLSX
- PDF
- DOCX
- TXT

Record file URL, file type, last modified date if available, and extraction method.

### 2. API-first extraction

Prefer documented public APIs. Also record public endpoints discovered from official docs or visible page network requests.

Do not use private endpoints requiring unauthorized tokens, session cookies, or hidden privileges.

### 3. DOM extraction

Use browser-rendered DOM for dynamic pages:
- visible text
- semantic regions
- headings
- tables
- cards/lists
- pagination
- filters
- links
- metadata

### 4. Table extraction

For every table:
- detect headers
- normalize row lengths
- preserve source URL
- preserve extraction timestamp
- infer field types
- report missing columns

### 5. Repeated item extraction

For listings, detect repeated cards or rows:
- identify item container
- extract repeated fields
- collect detail page links
- visit detail pages only when needed
- deduplicate by canonical URL or stable item ID

### 6. PDF/report extraction

When PDFs are public:
- record title, source URL, publication date, and publisher
- extract text
- inspect tables and figures when relevant
- cite page or section when possible
- note OCR uncertainty when text is image-based

### 7. Screenshot-backed extraction

Use screenshots only when:
- data is visible but text extraction fails
- the blocker must be documented
- charts or visual tables require human verification

## Schema inference

For datasets, create:
- field name
- description
- type
- example value
- missingness
- source selector or source field
- normalization rule

## Quality checks

Before returning data:
- deduplicate rows
- check row count against visible page counts when available
- verify a random sample against source pages
- check date/version consistency
- mark partial coverage
- separate raw extracted data from cleaned data

## Dataset output template

```markdown
## Dataset summary

Unit of observation:
Rows collected:
Fields collected:
Source domains:
Coverage:
Known gaps:
Extraction date:

## Data dictionary

| Field | Type | Description | Example | Source |
|---|---|---|---|---|

## Quality notes

## Blocked or partial sources
```
### 8. API extraction

When a public API or authorized API endpoint is available:
- discover API docs (swagger, openapi.json, developer portal)
- test with smallest possible request
- implement proper pagination (offset, cursor, page, link-header)
- respect rate limits (parse X-RateLimit headers, adaptive backoff)
- validate response schema
- flatten nested JSON to tabular format when needed
- log all requests to api-request-log

See references/api-access-workflow.md for full workflow.
See adapters/graphql.md for GraphQL-specific extraction.

### 9. Database extraction

When user provides database access:
- connect with user-provided credentials (NEVER guess or brute-force)
- discover schema (tables, columns, types)
- build SELECT queries from research questions
- always use LIMIT to prevent overwhelming results
- export to CSV/JSON
- document schema in data dictionary
- READ-ONLY operations only

See adapters/database-readonly.md for full workflow.

### 10. Academic database extraction

For literature and research data:
- use free academic APIs first (OpenAlex, CrossRef, Semantic Scholar, PubMed, arXiv)
- paginate through results (cursor-based for OpenAlex, offset for CrossRef)
- enrich metadata via DOI lookup on CrossRef
- build citation networks from referenced_works
- export citations in BibTeX/RIS format
- log all queries to search-log for reproducibility

See references/academic-databases.md for endpoints and query syntax.
See references/citation-management.md for citation export.
