# Citation Graph Traversal

Snowball sampling and citation network analysis via OpenAlex API. Use `scripts/citation_graph.py` to traverse forward citations (cited-by), backward citations (references), and coauthor networks.

## When to Use

- Systematic review snowball sampling (forward + backward)
- Identifying seminal papers via citation count
- Mapping research communities through coauthorship
- Converting citation networks into frontier-search candidates
- Finding related work that keyword search misses

## Script

| Subcommand | Purpose |
|---|---|
| `cited-by --doi <doi> --max 200` | Papers that cite this DOI |
| `references --doi <doi> --max 200` | Papers this DOI references |
| `expand --seed seeds.csv --max 500` | Full snowball from seed DOIs |
| `to-frontier --graph graph.json --out frontier.csv` | Convert to frontier-ledger candidates |
| `coauthors --orcid <orcid>` | Coauthor network for a researcher |

## OpenAlex API

All queries use the OpenAlex public API (`https://api.openalex.org`):

- **Works by DOI**: `GET /works/doi:{doi}`
- **Cited-by filter**: `GET /works?filter=cites:{openalex_id}`
- **Author by ORCID**: `GET /authors/orcid:{orcid}`
- **Works by author**: `GET /works?filter=author.id:{author_id}`

Rate limit: ~1 request/second (polite pool with User-Agent + contact email).

## Graph Schema

```json
{
  "schema_version": "1.0",
  "seed_works": [{"openalex_id": "...", "doi": "...", "title": "..."}],
  "nodes": [{"openalex_id": "...", "doi": "...", "title": "...", "year": 2023, "cited_by_count": 42, "authors": ["..."]}],
  "edges": [{"src": "https://openalex.org/W...", "dst": "https://openalex.org/W...", "kind": "cites"}],
  "stats": {"node_count": 50, "edge_count": 120, "cap_hit": false}
}
```

## Caps and Safety

- `--max` is a **global total output cap** on neighbor nodes (excluding the seed). With depth=2, the total output is still capped at --max, not --max per hop.
- `--depth 1|2` controls traversal hops (1 = direct neighbors, 2 = one more hop with per-hop caps)
- `--direction references|cited-by|both` for expand (default: both = full snowball)
- `cap_hit: true` in stats indicates the traversal was truncated
- Rate-limited to ~1 req/sec by default
- No authentication required (OpenAlex is fully open)
- `coauthors` only supports `--depth 1`; other values exit non-zero

## Frontier Conversion

`to-frontier` converts graph nodes into the exact `templates/frontier-ledger.csv` schema:

```
node_id,parent_id,node_type,value,gap_id,expansion_method,priority,status,access_status,blocked_reason,claim_ids,date_visited,notes
```

Fields:
- `node_type` = `citation`
- `value` = DOI URL when available, otherwise OpenAlex ID
- `expansion_method` = `citation_graph`
- `status` = `pending`
- `access_status` = `unknown`

```bash
python scripts/citation_graph.py expand --seed seeds.csv --max 100 --out graph.json
python scripts/citation_graph.py to-frontier --graph graph.json --out frontier-candidates.csv
```

## See Also

- `references/academic-databases.md` — OpenAlex API documentation
- `references/systematic-review-protocol.md` — snowball step in PRISMA reviews
- `references/frontier-search.md` — citation as a frontier node type
- `scripts/citation_resolver.py` — resolve individual DOIs to metadata
