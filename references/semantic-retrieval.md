# Semantic Retrieval

Use semantic retrieval when keyword search is insufficient — when you need to find documents or evidence-ledger rows that are conceptually similar to a query, even if they don't share exact terms.

## When to Use

- Large corpus (>30 documents) where keyword search returns too many or too few results
- Finding semantically related claims in an evidence ledger before synthesis
- Near-duplicate detection across collected sources
- Identifying conceptually similar papers in a literature review
- Gap analysis: finding which collected evidence is closest to an unresolved sub-question

## Script

`scripts/embed_corpus.py` provides semantic retrieval with these subcommands:

| Subcommand | Purpose |
|---|---|
| `index --in <dir> --out index.jsonl` | Build embedding index from text files |
| `query --index index.jsonl --q "..." --k 10` | Find top-k similar documents |
| `query-ledger --ledger evidence.csv --q "..."` | Query evidence ledger directly |
| `dedupe --index index.jsonl --threshold 0.92` | Find near-duplicate documents |

## Similarity Metric

All queries use **cosine similarity** between embedding vectors, implemented with stdlib `math.fsum` (no numpy dependency).

## Backends

| Backend | Setup | Privacy | Quality |
|---|---|---|---|
| `stub` | Always available | Local (deterministic hash) | Low (testing only) |
| `sentence-transformers` | `pip install sentence-transformers` | Local | High |
| `cohere` | `COHERE_API_KEY` + `--allow-remote` | Remote (data sent to Cohere) | High |
| `llama-cli` | `llama-embedding` binary on PATH | Local | High |

Default: `stub` (for testing). For production use, prefer `sentence-transformers` (local, high quality).

## Privacy

- `sentence-transformers` and `llama-cli` run entirely locally — no data leaves the machine
- `cohere` sends text to Cohere's API — requires explicit opt-in via `--allow-remote` or `D_RESEARCH_ALLOW_REMOTE_EMBEDDINGS=1`
- Do not embed sensitive evidence-ledger content with remote backends without user consent

## Index Schema (JSONL)

The first line is a metadata header:

```json
{"_meta": true, "schema_version": "1.0", "backend": "stub", "model": "", "embedding_dim": 32}
```

Subsequent lines are document entries:

```json
{"id": 0, "path": "doc1.txt", "text_preview": "First 200 chars...", "embedding": [0.1, -0.2, ...]}
```

The `query` command reads the index metadata and uses the **same backend and model** to embed the query. This ensures dimension compatibility. If the query embedding dimension does not match the index `embedding_dim`, the command exits non-zero with a clear error.

For Cohere, the index uses `input_type: "search_document"` and queries use `input_type: "search_query"` per Cohere's API recommendations.

## Usage Examples

```bash
# Build index with stub embedder (testing)
python scripts/embed_corpus.py index --in ./corpus/ --out index.jsonl --backend stub

# Build index with sentence-transformers (production)
python scripts/embed_corpus.py index --in ./corpus/ --out index.jsonl --backend sentence-transformers

# Query the index
python scripts/embed_corpus.py query --index index.jsonl --q "transformer attention mechanism" --k 5

# Query evidence ledger directly
python scripts/embed_corpus.py query-ledger --ledger evidence-ledger.csv --q "climate change impact"

# Find near-duplicates
python scripts/embed_corpus.py dedupe --index index.jsonl --threshold 0.92 --out duplicates.json
```

## Integration with Other Workflows

- **Frontier search**: use semantic neighbors as candidate sources when keyword search exhausts (`references/frontier-search.md`)
- **Synthesis**: retrieve top-k semantically related claims before composing a section (`references/synthesis-patterns.md`)
- **Deduplication**: identify near-duplicate evidence rows before final report

## See Also

- `references/frontier-search.md` — gap-driven follow-up (semantic neighbor as candidate source)
- `references/synthesis-patterns.md` — synthesis strategies
- `references/data-processing-pipeline.md` — data cleaning before indexing
