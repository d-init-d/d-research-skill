# Web-Search-Only Adapter

Use this when the agent has no browser or URL fetch tool.

## Workflow

1. generate query fanout
2. prefer official and primary sources in search results
3. use snippets only as discovery signals, not as full evidence when a direct source is required
4. record URLs that should be opened manually
5. search for alternative accessible sources
6. produce a source map and manual retrieval plan

## Limitations

In web-search-only mode, the agent cannot verify full page contents unless the search result provides enough information. Mark claims as lower confidence when based only on search snippets.

## Required output

Always include:
- queries attempted
- candidate URLs found
- sources that need manual opening
- confidence limitations
