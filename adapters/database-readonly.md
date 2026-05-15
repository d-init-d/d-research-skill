# Database Read-Only Adapter

## When to Use

- User provides connection string or URI
- Need structured data from relational or document databases
- Research data portal with query interface (Socrata, CKAN, etc.)
- Exporting datasets for analysis without mutation

---

## Supported Patterns

### SQL Databases (PostgreSQL, MySQL, SQLite)

- Connection via user-provided connection string
- **SELECT only** — no INSERT, UPDATE, or DELETE
- Pagination via `LIMIT` and `OFFSET`
- Schema discovery via `INFORMATION_SCHEMA`
- Export results as CSV or JSON

### NoSQL Databases (MongoDB, Elasticsearch)

- User-provided URI or connection string
- Read-only `find()` or search operations
- Pagination via `skip/limit` or scroll API
- Schema inference from sample documents (10-50 records)

### Data Portals with Query Interfaces

| Portal Type | API | Notes |
|-------------|-----|-------|
| Socrata SODA | `https://data.city.gov/resource/` | Government open data, free tier |
| CKAN | `https://data.gov/api/3/action/` | data.gov portals, requires API key |
| BigQuery | Google Cloud API | Public datasets, user needs auth |

---

## Safety Rules

| Rule | Implementation |
|------|----------------|
| **READ-ONLY ONLY** | Reject any write operations with clear error |
| Validate before connect | Test credentials with 10s timeout |
| Never log credentials | Mask passwords in all logs |
| Timeout per query | 30s default, configurable |
| Limit result size | Max 10,000 rows per query |

---

## Workflow

1. **Receive connection** — user provides connection string
2. **Test connection** — verify with 10s timeout, report status
3. **Discover schema** — query metadata tables or sample docs
4. **Build query** — translate research question to SQL/filter
5. **Execute** — run with LIMIT, pagination for large results
6. **Export** — format as CSV or JSON
7. **Log query** — append to `search-log.md`

---

## Output

| File | Content |
|------|---------|
| `query-results.csv` or `.json` | Raw data from database |
| `schema-documentation.md` | Discovered tables/collections/fields |
| `query-log.md` | Query history with timestamps |
| `connection-report.md` | Connection status and capabilities |

---

## Error Handling

- **Connection failed**: Return status, suggest fixes
- **Permission denied**: Inform user of required privileges
- **Query timeout**: Offer pagination or filter suggestions
- **Result too large**: Suggest LIMIT or date range filters
