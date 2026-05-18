# Source Discovery

Use this file to find where relevant data lives before extracting anything.

## Source hierarchy

Prefer sources in this order:

1. primary official source
2. public dataset or public API
3. source code repository, release notes, changelog, issue tracker
4. standard, RFC, specification, legal filing, government document
5. academic paper or systematic review
6. reputable secondary analysis
7. community sources: forums, discussions, Q&A
8. social media or unverifiable summaries

For factual claims, prefer primary sources. Use secondary sources to discover primary sources, not as the final authority when primary sources are available.

## Discovery layers

### Search engine layer

Run query fanout from `query-patterns.md`.

#### Search engine fallback chain

When using `scripts/web_search.mjs` for programmatic search (no browser needed), the script attempts engines in this order:

1. **DuckDuckGo** — no API key required, always attempted first
2. **SearXNG** — no API key required, privacy-respecting metasearch (override instance with `SEARXNG_INSTANCE` env var)
3. **Brave Search** — attempted only if `BRAVE_API_KEY` is set
4. **Google CSE** — attempted only if both `GOOGLE_CSE_KEY` and `GOOGLE_CSE_ID` are set

The first engine that succeeds returns results; no cross-engine merging occurs. Use `npm run search:web -- --query "<q>"` or invoke directly with `node scripts/web_search.mjs --query "<q>"`.

Use this programmatic search when:
- No browser tool is available for interactive search
- You need reproducible, scriptable search queries
- You want to fan out multiple queries without manual browser interaction

Use browser-based search (Playwright / generic browser) when:
- You need to interact with search result pages (pagination, filters)
- You need to verify full page content beyond snippets
- The search engine requires JavaScript rendering

### Domain layer

For each promising domain, inspect:
- homepage
- docs
- search page
- sitemap.xml
- sitemap index
- robots.txt
- RSS or Atom feeds
- public downloads
- API docs
- changelog or releases
- footer links
- terms and data usage pages

### File discovery layer

Search for:
- filetype:pdf
- filetype:csv
- filetype:xlsx
- filetype:json
- filetype:xml
- filetype:docx
- site-specific reports
- public data exports

### Code and developer layer

Search for:
- GitHub/GitLab repositories
- package registry pages
- examples
- issues
- discussions
- commits
- releases
- migration guides

### Academic layer

Search for:
- paper title
- authors
- DOI
- arXiv ID
- conference or journal
- citations and references
- datasets and supplementary material

### Public database layer

Look for:
- government portals
- open data portals
- statistical agencies
- registries
- standards bodies
- company filings
- research datasets

## Source map template

```markdown
## Source map

| Source class | Candidate source | Why it matters | Access method | Priority | Notes |
|---|---|---|---|---|---|
| official docs |  |  | browser/fetch/search | high |  |
| public dataset |  |  | download/api | high |  |
| academic |  |  | search/browser | medium |  |
| secondary |  |  | search/browser | low |  |
```

## Source scoring

Score each source from 0 to 5:

- authority: is it primary or official?
- relevance: does it answer the sub-question?
- freshness: is it recent enough?
- traceability: does it cite data or methods?
- accessibility: can it be opened and extracted?
- stability: is the URL canonical and durable?

Use high-scoring sources first.
### API layer

Search for structured data via APIs:
- REST API endpoints: check /api, /api/v1, /api/docs, /swagger.json, /openapi.json
- GraphQL endpoints: check /graphql, /api/graphql, /gql
- SPARQL endpoints: check /.well-known/void, /sparql
- Developer portals and API documentation pages
- Network requests visible in browser (XHR/Fetch) revealing API patterns
- API aggregators: RapidAPI, ProgrammableWeb, public-apis GitHub repo

Evaluate: authentication requirements, rate limits, data completeness, documentation quality.

### Database and data portal layer

Look for queryable data interfaces:
- Socrata/SODA API portals (many US/EU government datasets)
- CKAN-based portals (data.gov, data.gov.uk, many national portals)
- Google Dataset Search: https://datasetsearch.research.google.com
- Kaggle datasets (public, downloadable)
- data.world, Hugging Face Datasets
- Domain-specific registries and repositories

### Specialized domain layer

Route to domain-specific sources based on research topic:
- Financial: FRED, World Bank, SEC EDGAR, Alpha Vantage (see references/specialized-domains.md)
- Academic: OpenAlex, CrossRef, PubMed, Semantic Scholar (see references/academic-databases.md)
- Patent: USPTO PatentsView, EPO, WIPO
- Legal: EUR-Lex, Congress.gov, national legal databases
- Geospatial: OpenStreetMap Overpass, Natural Earth, GADM
- Social: Reddit JSON API, Hacker News Algolia, GDELT
