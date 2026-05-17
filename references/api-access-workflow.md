# API Access Workflow for AI Research Agents

This guide provides a structured approach to accessing REST APIs for research data collection, ensuring efficient, reliable, and safe API interactions.

---

## When to Use

Use REST API access when:

- Structured data retrieval is required from external services
- Data updates occur frequently and real-time access is needed
- Research requires data from multiple sources programmatically
- Batch data collection is more efficient than manual scraping
- The target service provides official API support

**Prefer alternatives** when APIs are rate-limited too severely, data is static and easily downloadable, or terms of service prohibit automated access.

If an otherwise public API or canonical API-form source returns 403, 429, anti-bot HTML, captcha, or a JavaScript challenge, run `references/anti-bot-fallback.md` once before producing a blocker report. Do not use the fallback chain for authenticated or paid APIs unless the user has explicitly provided authorization.

---

## API Discovery

Before making requests, identify and document the API:

1. **Locate documentation**: Check `/docs`, `/api/docs`, or developer portals
2. **Identify base URL**: Note version prefixes (e.g., `/v1/`, `/v2/`)
3. **Review available endpoints**: Map required data to specific endpoints
4. **Check rate limits**: Note daily/hourly/request limits
5. **Verify authentication requirements**: Know what credentials are needed

```
Common patterns:
- https://api.service.com/v1/resource
- https://service.com/api/v2/endpoint
- https://api.service.com/rest/v1/resource
```

---

## Authentication Patterns

### API Keys

Simple token-based authentication, typically passed in headers:

```
Authorization: Bearer YOUR_API_KEY
X-API-Key: YOUR_API_KEY
```

### OAuth 2.0

For user-authorized access:

```
1. Obtain client_id and client_secret
2. Request authorization URL
3. Exchange code for access_token
4. Include token in requests: Authorization: Bearer {token}
5. Refresh token when expired
```

### Basic Authentication

For simple cases with username/password:

```
Authorization: Basic base64(username:password)
```

**Always store credentials securely** — never hardcode in scripts. Use environment variables or secure vaults.

---

## Request Workflow

### Standard Request Sequence

```
1. Build request URL with required parameters
2. Attach authentication headers
3. Set appropriate Content-Type headers
4. Execute HTTP request (GET for retrieval, POST for creation)
5. Capture response status code
6. Parse response body
7. Handle errors appropriately
8. Implement backoff on failures
```

### Request Construction Example

```python
import requests

def make_api_request(endpoint, params, headers, max_retries=3):
    """Standardized API request with retry logic."""
    
    for attempt in range(max_retries):
        response = requests.get(
            endpoint,
            params=params,
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 429:
            wait_time = int(response.headers.get('Retry-After', 60))
            time.sleep(wait_time)
        elif 400 <= response.status_code < 500:
            raise ValueError(f"Client error {response.status_code}: {response.text}")
        elif response.status_code >= 500:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise ConnectionError(f"Server error after {max_retries} attempts")
    
    return None
```

---

## Pagination Patterns

APIs limit single response size. Handle pagination to collect complete datasets.

### Offset-Based

Use `offset` and `limit` parameters:

```
GET /v1/data?limit=100&offset=0   # First 100 items
GET /v1/data?limit=100&offset=100  # Next 100 items
```

```python
def paginate_offset(base_url, params, headers):
    results = []
    offset = 0
    limit = params.get('limit', 100)
    
    while True:
        response = make_api_request(
            f"{base_url}?limit={limit}&offset={offset}",
            {}, headers
        )
        results.extend(response['items'])
        
        if len(response['items']) < limit:
            break
        offset += limit
    
    return results
```

### Cursor-Based

Use opaque cursor tokens for stable pagination:

```
GET /v1/data?limit=100&cursor=eyJpZCI6MTAwfQ==
GET /v1/data?limit=100&cursor=eyJpZCI6MjAwfQ==
```

```python
def paginate_cursor(base_url, params, headers):
    results = []
    cursor = None
    
    while True:
        query_params = {**params, 'cursor': cursor} if cursor else params
        response = make_api_request(base_url, query_params, headers)
        results.extend(response['data'])
        
        cursor = response.get('next_cursor')
        if not cursor:
            break
    
    return results
```

### Page-Based

Traditional page numbers (often 1-indexed):

```
GET /v1/data?page=1&per_page=100
GET /v1/data?page=2&per_page=100
```

### Link Header (RFC 5988)

Parse `Link` header for navigation URLs:

```python
def paginate_link_header(response):
    results = []
    link_header = response.headers.get('Link', '')
    
    while True:
        results.extend(response.json())
        
        links = {}
        for part in link_header.split(','):
            part = part.strip()
            if '<' in part and '>' in part:
                url, rel = part.split(';')
                url = url.strip('<> ')
                rel = rel.strip().replace('rel=', '').strip('"')
                links[rel] = url
        
        if 'next' not in links:
            break
        
        response = requests.get(links['next'], headers=headers)
        link_header = response.headers.get('Link', '')
    
    return results
```

---

## Rate Limit Handling

Respect API limits to avoid service disruption and bans.

### Detection Strategies

```python
def check_rate_limits(response):
    """Extract rate limit info from response headers."""
    
    return {
        'limit': int(response.headers.get('X-RateLimit-Limit', 0)),
        'remaining': int(response.headers.get('X-RateLimit-Remaining', 0)),
        'reset': int(response.headers.get('X-RateLimit-Reset', 0)),
        'retry_after': response.headers.get('Retry-After')
    }
```

### Implementation Guidelines

1. **Monitor remaining requests**: Track `X-RateLimit-Remaining` headers
2. **Respect `Retry-After`**: Wait specified seconds before retrying
3. **Implement exponential backoff**: `wait = min(base * 2^attempt, max_wait)`
4. **Add jitter**: Random variation prevents synchronized requests
5. **Queue requests**: Space out requests to stay under limits

```python
import random
import time

def throttled_request(url, headers, calls_per_minute=60):
    """Ensure request rate stays within limits."""
    
    delay = 60 / calls_per_minute
    time.sleep(delay + random.uniform(0, 0.5))
    
    return requests.get(url, headers=headers)
```

---

## Response Processing

### Standard Processing Steps

```python
import json

def process_response(response):
    """Standard response processing pipeline."""
    
    # 1. Check status code
    if not response.ok:
        raise APIError(f"HTTP {response.status_code}: {response.text}")
    
    # 2. Parse content type
    content_type = response.headers.get('Content-Type', '')
    
    if 'application/json' in content_type:
        return response.json()
    elif 'text/csv' in content_type:
        return parse_csv(response.text)
    else:
        return response.content
```

### Data Extraction Patterns

```python
def extract_field(data, path):
    """Navigate nested JSON structures safely."""
    
    for key in path.split('.'):
        if isinstance(data, dict):
            data = data.get(key, {})
        elif isinstance(data, list) and key.isdigit():
            data = data[int(key)] if int(key) < len(data) else {}
        else:
            return None
    return data if data else None
```

---

## Safety Rules

### Do

- Store credentials in environment variables or secure vaults
- Implement comprehensive error handling
- Log all API interactions for debugging
- Respect rate limits and implement backoff
- Use HTTPS exclusively for all requests
- Validate all response data before processing
- Cache responses when permissible

### Do Not

- Hardcode API keys or secrets in source code
- Share credentials across different services
- Ignore rate limit headers or 429 responses
- Make requests without timeout limits
- Process unvalidated external data directly
- Exceed stated rate limits
- Access APIs that prohibit automated use

### Security Checklist

```
□ Credentials stored securely (env vars or vault)
□ All connections use HTTPS
□ Timeouts set on all requests
□ Rate limits respected
□ Input validation on all response data
□ Errors logged without exposing sensitive data
□ No sensitive data in logs or error messages
```

---

## Quick Reference

| Pattern | When to Use |
|---------|-------------|
| Offset pagination | Small, stable datasets |
| Cursor pagination | Large, frequently updated data |
| Link header | APIs following HATEOAS |
| API key auth | Simple, server-to-server calls |
| OAuth 2.0 | User-delegated access |

**Remember**: Always read the specific API documentation first. This workflow provides general guidance, but individual APIs may have unique requirements or limitations.
 window |
| `X-RateLimit-Reset` | Unix timestamp when limit resets |
| `X-RateLimit-Window` | Time window in seconds |
| `Retry-After` | Seconds to wait before retry (on 429) |
| `RateLimit-Limit` | Alternative header format |

```python
def parse_rate_limit(response):
    """Extract rate limit info from response headers."""
    return {
        "limit": response.headers.get("X-RateLimit-Limit"),
        "remaining": response.headers.get("X-RateLimit-Remaining"),
        "reset": response.headers.get("X-RateLimit-Reset"),
        "retry_after": response.headers.get("Retry-After")
    }
```

### Adaptive Delay Strategy

```python
def adaptive_delay(base_delay=1.0, max_delay=60, remaining=None):
    """
    Calculate delay based on remaining requests.
    - If remaining < 10: increase delay
    - If remaining > 50: safe to decrease slightly
    - Never exceed max_delay
    """
    if remaining is not None and remaining < 10:
        return min(base_delay * 1.5, max_delay)
    elif remaining is not None and remaining > 50:
        return max(base_delay * 0.8, 0.5)
    return base_delay
```

### Exponential Backoff

```python
def exponential_backoff(attempt, base_delay=1, max_delay=32):
    """
    Exponential backoff: 1s → 2s → 4s → 8s → 16s → 32s
    Stop after 6 attempts (1 minute total wait)
    """
    delay = min(base_delay * (2 ** attempt), max_delay)
    return delay

def fetch_with_backoff(url, headers, max_attempts=6):
    """Fetch with exponential backoff on rate limit errors."""
    for attempt in range(max_attempts):
        response = requests.get(url, headers=headers)
        
        if response.status_code == 429:
            wait_time = int(response.headers.get("Retry-After", 
                              2 ** attempt))
            print(f"Rate limited. Waiting {wait_time}s...")
            time.sleep(wait_time)
        elif response.status_code >= 500:
            wait_time = exponential_backoff(attempt)
            print(f"Server error. Retrying in {wait_time}s...")
            time.sleep(wait_time)
        else:
            return response
    
    raise Exception(f"Failed after {max_attempts} attempts")
```

### Rate Limit Event Logging

```python
rate_limit_log = []

def log_rate_limit_event(event_type, details):
    """Record rate limit events for analysis."""
    event = {
        "timestamp": time.time(),
        "event_type": event_type,  # "limit_reached", "backoff", "reset"
        "details": details
    }
    rate_limit_log.append(event)
```

---

## Response Processing

### Validate Response Schema

```python
REQUIRED_FIELDS = ["id", "name", "created_at"]

def validate_record(record, required_fields=REQUIRED_FIELDS):
    """Validate record has required fields."""
    missing = [f for f in required_fields if f not in record]
    if missing:
        return False, f"Missing fields: {missing}"
    return True, "Valid"

def validate_response(data, expected_type=list):
    """Validate overall response structure."""
    if not isinstance(data, dict):
        return False, f"Expected dict, got {type(data)}"
    
    if "data" in data and not isinstance(data["data"], expected_type):
        return False, f"Expected data.{expected_type}, got {type(data['data'])}"
    
    return True, "Valid"
```

### Flatten Nested JSON

```python
def flatten_record(record, parent_key='', sep='_'):
    """Flatten nested dictionaries for CSV export."""
    items = []
    for k, v in record.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_record(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            items.append((new_key, json.dumps(v)))
        else:
            items.append((new_key, v))
    return dict(items)
```

### Map to Evidence Ledger

```python
def map_to_evidence(record, source, record_id=None):
    """Map API record to evidence ledger format."""
    evidence = {
        "source": source,
        "source_url": record.get("url", ""),
        "accessed_at": time.time(),
        "record_id": record_id or record.get("id"),
        "evidence_type": "api_response",
        "data": record
    }
    return evidence
```

### Extract Pagination Metadata

```python
def extract_pagination_meta(response):
    """Extract pagination metadata for logging."""
    headers = response.headers
    meta = {
        "total": headers.get("X-Total-Count"),
        "page_size": headers.get("X-Page-Size"),
        "current_page": headers.get("X-Page"),
        "total_pages": headers.get("X-Total-Pages"),
        "rate_limit_remaining": headers.get("X-RateLimit-Remaining")
    }
    return {k: v for k, v in meta.items() if v is not None}
```

---

## Common API Patterns

### REST APIs

Standard REST collection pattern:

```python
def collect_rest_data(base_url, endpoint, headers, params):
    """Collect data from REST API with full workflow."""
    all_data = []
    url = f"{base_url}/{endpoint}"
    
    while True:
        response = fetch_with_logging(url, headers=headers, params=params)
        
        # Auto-detect data location
        records = response.get("data") or response.get("results") or \
                  response.get("records") or response.get("items") or \
                  (response if isinstance(response, list) else [])
        
        all_data.extend(records)
        
        # Detect and handle pagination
        params, next_token = detect_pagination(response, params)
        if not next_token:
            break
    
    return all_data
```

### GraphQL APIs

See detailed GraphQL guidance in `adapters/graphql.md`.

Quick reference:

```python
def graphql_query(endpoint, query, variables=None, headers=None):
    """Execute GraphQL query."""
    payload = {"query": query}
    if variables:
        payload["variables"] = variables
    
    response = requests.post(endpoint, json=payload, headers=headers)
    data = response.json()
    
    if "errors" in data:
        raise Exception(f"GraphQL error: {data['errors']}")
    
    return data.get("data", {})
```

### SPARQL Endpoints

#### Endpoint Discovery

Common SPARQL endpoint patterns:

| Organization | Endpoint Pattern |
|--------------|------------------|
| Wikidata | `https://query.wikidata.org/sparql` |
| DBpedia | `https://dbpedia.org/sparql` |
| EU Open Data | `https://data.europa.eu/sparql` |
| US Census | `https://api.census.gov/data/2021/sparql` |

#### SPARQL Query Execution

```python
def query_sparql(endpoint, sparql_query, format="json"):
    """
    Execute SPARQL query against endpoint.
    
    Args:
        endpoint: SPARQL endpoint URL
        sparql_query: SPARQL query string
        format: Response format (json, xml, csv, ttl)
    """
    response = requests.post(endpoint, data={
        "query": sparql_query,
        "format": format
    }, timeout=60)
    response.raise_for_status()
    return response.json()
```

#### SELECT Query with Pagination

```python
def sparql_select(endpoint, query, limit=10000, offset=0):
    """Execute SPARQL SELECT with LIMIT/OFFSET pagination."""
    paginated_query = f"""
        {query}
        LIMIT {limit}
        OFFSET {offset}
    """
    results = query_sparql(endpoint, paginated_query)
    return results.get("results", {}).get("bindings", [])
```

#### CONSTRUCT Query

```python
def sparql_construct(endpoint, construct_query):
    """Execute SPARQL CONSTRUCT for RDF graph."""
    response = requests.post(endpoint, data={
        "query": construct_query,
        "format": "json"
    })
    
    # Parse RDF/JSON-LD response
    data = response.json()
    return data.get("@graph", [])
```

#### SPARQL Best Practices

```python
SPARQL_EXAMPLE = """
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX wd: <http://www.wikidata.org/entity/>

SELECT ?item ?itemLabel ?country ?countryLabel
WHERE {
    ?item wdt:P31 wd:Q5.  # Human
    ?item wdt:P27 ?country.
    SERVICE wikifi:label {
        bd:serviceParam wikifi:language "en".
    }
}
LIMIT 1000
"""

def collect_sparql_data(endpoint, base_query, max_records=50000):
    """Collect large SPARQL result sets with pagination."""
    all_results = []
    offset = 0
    limit = 10000  # Most endpoints max at 10000
    
    while offset < max_records:
        results = sparql_select(endpoint, base_query, limit=limit, offset=offset)
        all_results.extend(results)
        
        if len(results) < limit:
            break
        offset += limit
        time.sleep(0.5)  # Be respectful to public endpoints
    
    return all_results
```

---

## Output

### Required Outputs for Data Collection

| Output | Format | Contents |
|--------|--------|----------|
| Raw JSON | `.json` | Full API responses with metadata |
| Processed Data | `.csv` or `.json` | Flattened, deduplicated records |
| Request Log | `.jsonl` | All requests with timestamps, status codes |
| Rate Limit Report | `.json` | Summary of rate limit events |
| Blocker Report | `.md` | Any access issues encountered |

### Output Example Structure

```
outputs/
├── api_collection_2024-01-15/
│   ├── raw/
│   │   ├── page_001.json
│   │   ├── page_002.json
│   │   └── ...
│   ├── processed/
│   │   ├── records.csv
│   │   └── evidence_ledger.json
│   ├── request_log.jsonl
│   ├── rate_limit_report.json
│   └── blocker_report.md
```

---

## Safety

### Access Guidelines

1. **GET Only**: Only use GET requests for data collection. POST/PUT/DELETE can modify data.

2. **No Brute-Force Keys**: Never attempt to discover API keys through repeated guessing.

3. **Respect Rate Limits**: Implement delays and backoff. Violating rate limits can result in IP bans.

4. **Authorization Only**: Only access private endpoints with explicit authorization. Document credentials securely.

5. **Audit Trail**: Log every request including URL, parameters, timestamp, and response status.

### Red Flags to Avoid

- Endpoints requiring password or credentials you must discover
- APIs explicitly marked as internal/private
- Requests that would modify, delete, or create data
- Endpoints with no documented terms of service (risk of legal issues)

### Prohibited Actions

- Circumventing authentication to access private data
- Ignoring rate limits causing denial of service
- Scraping data against stated terms of service
- Attempting SQL injection or other injection attacks
- Using harvested credentials on other services

### Security Checklist

```python
SAFETY_CHECKLIST = {
    "uses_get_only": True,
    "has_rate_limiting": True,
    "has_error_handling": True,
    "logs_all_requests": True,
    "uses_exponential_backoff": True,
    "respects_robots_txt": True,
    "documented_credentials": False,  # Should be False unless needed
    "no_brute_force": True
}

def safety_check(passed):
    """Verify all safety checks passed before proceeding."""
    failures = [k for k, v in passed.items() if not v]
    if failures:
        raise ValueError(f"Safety check failed: {failures}")
```

---

## Quick Reference

### Common HTTP Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Process response |
| 400 | Bad Request | Fix parameters |
| 401 | Unauthorized | Add authentication |
| 403 | Forbidden | Do not proceed |
| 404 | Not Found | Check endpoint |
| 429 | Rate Limited | Wait and retry |
| 500 | Server Error | Retry with backoff |

### Key Files Referenced

- `adapters/graphql.md` - Detailed GraphQL patterns
- `references/anti-bot-fallback.md` - Bounded fallback chain for blocked public API/static sources
- `references/data-processing-pipeline.md` - Data cleaning, validation, and transformation
- `templates/api-request-log.csv` - Header for the per-request log this workflow refers to
- `references/large-scale-collection.md` - Checkpointing and adaptive rate limiting for >100 records
