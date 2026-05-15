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
