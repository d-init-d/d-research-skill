# Query Patterns

Use this file to generate broad and targeted searches.

## Core fanout

For every sub-question, generate these query types:

1. broad
   - `{topic} overview`
   - `{topic} explained`

2. exact phrase
   - `"{specific phrase}"`
   - `"{entity}" "{field}"`

3. official source
   - `{entity} official`
   - `{product} official docs {feature}`
   - `site:{official_domain} {topic}`

4. primary source
   - `{topic} specification`
   - `{topic} standard`
   - `{topic} RFC`
   - `{topic} changelog`
   - `{topic} release notes`
   - `{topic} GitHub`
   - `{company} annual report`
   - `{company} filing`

5. data and API
   - `{topic} dataset`
   - `{topic} public data`
   - `{topic} csv`
   - `{topic} api`
   - `{topic} download`
   - `{topic} filetype:csv`
   - `{topic} filetype:json`
   - `{topic} filetype:xlsx`

6. document search
   - `{topic} filetype:pdf`
   - `{topic} report pdf`
   - `{topic} whitepaper`

7. recent
   - `{topic} 2026`
   - `{topic} latest`
   - `{topic} updated`
   - `{topic} release notes 2026`

8. contradiction
   - `{claim} false`
   - `{topic} criticism`
   - `{topic} limitations`
   - `{topic} controversy`
   - `{topic} not working`
   - `{topic} outdated`

9. alternate terms
   - synonyms
   - abbreviations
   - translations
   - old product names
   - standards identifiers

10. site search
   - `site:{domain} {topic}`
   - `site:{domain} filetype:pdf {topic}`
   - `site:{domain} intitle:{keyword}`

## Iterative query expansion

After reviewing initial results:
- extract new entities, aliases, product names, versions, dates, and authors
- search those terms directly
- use promising snippets as exact phrases
- search cited sources and backlinks
- search for the same concept in another language when useful

## Pearl growing and snowballing

When a high-quality source is found:
- backward snowball: inspect references and outbound links
- forward snowball: search who cited, quoted, forked, discussed, or mirrored it
- lateral snowball: search related authors, organizations, projects, terms, and datasets

## Search log template

```markdown
| Sub-question | Query | Tool | Date | Top sources found | Notes |
|---|---|---|---|---|---|
```
