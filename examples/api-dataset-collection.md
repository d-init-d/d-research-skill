```markdown
# Example: Collecting AI Research Papers Dataset

## User Request
"Collect a dataset of AI research papers from 2024-2026 using OpenAlex API, including title, authors, DOI, citation count, and abstract."

## Agent Behavior

### Step 1: Define Unit of Observation
- **Unit**: One research paper (single work/publication)
- **Granularity**: Each row = one publication record

### Step 2: Define Fields and Output Format
| Field | Type | Source | Notes |
|-------|------|--------|-------|
| title | string | title | |
| authors | string[] | authorships.display_name | Flatten to semicolon-separated |
| doi | string | doi | |
| citation_count | integer | cited_by_count | |
| abstract | string | abstract_inverted_index | Reconstitute to plain text |

### Step 3: Call OpenAlex /works Endpoint
```
GET https://api.openalex.org/works?
  filter=from_publication_date:2024-01-01,to_publication_date:2026-12-31,concepts.id:C29428257
  &select=title,authorships,doi,cited_by_count,abstract_inverted_index
  &per_page=200
```

### Step 4: Paginate with Cursor
- Extract `meta.next_cursor` from each response
- Loop until cursor is null or rate limit hit
- Store 2,847 papers across 15 pages

### Step 5: Process and Clean
- Decode `abstract_inverted_index` to full text
- Flatten `authorships` array to semicolon-separated string
- Validate DOI format; skip 23 malformed records
- Remove duplicates by DOI: 12 removed

### Step 6: Export Outputs
- `ai_papers_2024_2026.csv` — 2,812 rows
- `data_dictionary.md` — field definitions and provenance
- `evidence_ledger.json` — API calls, timestamps, row counts

### Step 7: Report
- **Coverage**: Papers with OpenAlex concept "artificial intelligence" published 2024-2026
- **Limitations**: Excludes non-indexed repositories, preprints without DOIs; ~85% recall
- **Output**: 2,812 papers saved to `/datasets/`
```
