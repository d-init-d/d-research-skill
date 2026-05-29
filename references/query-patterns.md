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

9. alternate terms and register ladder
   - synonyms
   - abbreviations
   - translations
   - old product names
   - standards identifiers
   - register variants: canonical/clinical/legal/technical ↔ lay ↔ community jargon ↔ emergent slang
   - run the ladder both ways — formal → vernacular to open recall, vernacular → formal to anchor community terms back to a primary source
   - when a query under-recalls because the evidence basin speaks a different register, see `references/register-and-jargon-expansion.md` (harvest terms from fresh results only; keep only terms recurring across ≥2 independent community sources; vocabulary is discovery, never evidence)

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
### Web search query patterns

- Advanced operators: `site:{domain} {topic}`, `filetype:{extension} {topic}`, `intitle:{phrase}`, `inurl:{keyword}`
- Boolean combinations: `{term1} AND {term2}`, `{term1} OR {term2}`, `{term} -exclude`
- Exact phrases: `"{exact phrase}"`, `"{phrase}" {related_term}`
- Date filtering: `after:{date}`, `before:{date}`, `daterange:{start}..{end}`
- Related content: `related:{domain}`, `link:{url}`
- Cache/versioning: `cache:{url}`, `versions:{term}`

### Documentation and knowledge base queries

- Manual lookup: `"{tool_name}" documentation`, `"{tool_name}" user guide`, `"{tool_name}" tutorial`
- Stack Exchange: `site:stackoverflow.com {error_message}`, `site:serverfault.com {issue}`
- GitHub: `site:github.com {topic} issues`, `site:github.com {repo} README`
- Wikipedia/Encyclopedia: `{concept} wikipedia`, `intitle:wikipedia {topic}`
- RFC/specs: `RFC {number}`, `site:datatracker.ietf.org {protocol}`, `site:tools.ietf.org {rfc}`
- Cheat sheets: `"{topic}" cheatsheet`, `"{tool}" quick reference`, `"{topic}" one-page guide`
