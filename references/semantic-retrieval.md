# Semantic Retrieval

Use semantic retrieval when keyword search is insufficient — when you need to find documents or evidence-ledger rows that are conceptually similar to a query, even if they don't share exact terms.

## Contents

- [When to Use](#when-to-use)
- [Script](#script)
- [Similarity Metric](#similarity-metric)
- [Backends](#backends)
- [Privacy](#privacy)
- [Index Schema](#index-schema-jsonl)
- [Usage Examples](#usage-examples)
- [Integration with Other Workflows](#integration-with-other-workflows)
- [See Also](#see-also)

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
| `local-hashing` | Always available | Local (deterministic feature hashing) | Medium for lexical overlap; not a trained semantic model |
| `stub` | Always available | Local (deterministic hash) | Low (testing only) |
| `sentence-transformers` | `python -m pip install -e ".[embeddings]"` | Local inference | High |
| `cohere` | `COHERE_API_KEY` + `--allow-remote` | Remote (data sent to Cohere) | High |
| `llama-cli` | `llama-embedding` binary on PATH | Local | High |

`index` and `query-ledger` default to `--backend auto`. Auto selects `sentence-transformers` when installed and otherwise falls back to the deterministic built-in `local-hashing` backend. It never selects a remote backend or the test stub. Install `.[embeddings]` for trained semantic similarity; the dependency-free fallback preserves command compatibility and is best for lexical overlap and spelling variants. The `stub` backend must be requested explicitly and is only suitable for deterministic tests.

## Privacy

- `local-hashing` is dependency-free, deterministic, local, and performs no model download
- `sentence-transformers` inference and `llama-cli` run locally — no corpus text is sent to a provider
- A named sentence-transformers model may download weights on first use; pre-cache it or pass a local model path for offline runs
- `cohere` sends text to Cohere's API — requires explicit opt-in via `--allow-remote` or `D_RESEARCH_ALLOW_REMOTE_EMBEDDINGS=1`
- Do not embed sensitive evidence-ledger content with remote backends without user consent

## Index Schema (JSONL)

The first line is a metadata header:

```json
{"_meta": true, "schema_version": "1.0", "backend": "sentence-transformers", "model": "all-MiniLM-L6-v2", "embedding_dim": 384}
```

Subsequent lines are document entries:

```json
{"id": 0, "path": "doc1.txt", "text_preview": "First 200 chars...", "embedding": [0.1, -0.2, ...]}
```

The `query` command reads the index metadata and uses the **same concrete backend and model** to embed the query. `auto` is never stored in an index. Legacy headerless indexes still resolve to `stub` for compatibility. Dimension mismatches exit non-zero.

JSONL parsing rejects duplicate keys and non-finite numbers. Explicit metadata
headers require schema `1.0`; every backend batch and stored vector must have
the exact count and dimension, finite numeric non-boolean values, and a
rectangular shape. Blank queries fail before embedding. Empty documents receive
a zero `local-hashing` vector, so they cannot become false duplicates.

For Cohere, the index uses `input_type: "search_document"` and queries use `input_type: "search_query"` per Cohere's API recommendations.

## Usage Examples

```bash
# Install the optional local production backend
python -m pip install -e ".[embeddings]"

# Build an index (auto prefers sentence-transformers, then local-hashing)
python scripts/embed_corpus.py index --in ./corpus/ --out index.jsonl

# Force the dependency-free deterministic lexical backend
python scripts/embed_corpus.py index --in ./corpus/ --out index.jsonl --backend local-hashing

# Build index with stub embedder (testing)
python scripts/embed_corpus.py index --in ./corpus/ --out index.jsonl --backend stub

# Select sentence-transformers explicitly or choose a model/path
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
