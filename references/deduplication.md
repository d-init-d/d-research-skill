# Near-Duplicate Detection

Use `scripts/dedup_near.py` to find near-duplicate text in CSVs and evidence ledgers via SimHash + Hamming distance.

## When to Use

- Large-scale collection where the same content was scraped from multiple URLs
- Evidence ledger cleanup before synthesis (collapse repeat claims)
- Detecting paraphrased duplicates that exact-match dedup misses
- Identifying mirror sites and syndicated articles

## Algorithm

The script implements 64-bit **SimHash** over normalized 3-token shingles:

1. **Normalize**: lowercase, strip punctuation, collapse whitespace
2. **Shingle**: split into overlapping 3-token windows
3. **Hash**: SHA-256 each shingle, take low 64 bits
4. **Combine**: bit-vote across all shingle hashes to produce a single 64-bit fingerprint
5. **Compare**: Hamming distance between two fingerprints

Smaller distance = more similar. Default threshold: **3** (conservative).

## Usage

```bash
# Single text fingerprint
python scripts/dedup_near.py fingerprint --text "Some text to fingerprint"

# Scan CSV by text column
python scripts/dedup_near.py scan --in rows.csv --text-column claim --out duplicates.csv

# Scan evidence ledger (uses claim + evidence fields)
python scripts/dedup_near.py ledger --in evidence-ledger.csv --out duplicates.csv

# Adjust threshold
python scripts/dedup_near.py scan --in rows.csv --text-column claim --threshold 5 --out dups.csv
```

## Threshold Guidance

| Threshold | Behavior |
|---|---|
| 0 | Exact normalized match only |
| 1-3 | Near duplicates (default 3) — very small edits |
| 4-7 | Moderate similarity — paraphrases |
| 8+ | Loose similarity — risk of false positives |

## False Positives Review

SimHash can flag false positives, especially in short text. Review duplicate pairs before deletion:

1. Sort `duplicates.csv` by `distance` ascending
2. Manually verify pairs with distance >= 3
3. Mark confirmed duplicates in the ledger and resolve via merge or deletion
4. Keep the original claim_id; mark the duplicate's status as `superseded_by:<original_id>` in notes

## Integration with Evidence Ledger

After `dedup_near.py ledger`, use the output to consolidate:
- Keep the row with stronger evidence / earlier date
- Merge unique source URLs from duplicates into the kept row's notes
- Mark duplicates with `notes` field: `duplicate of <claim_id>, superseded`

## See Also

- `references/large-scale-collection.md` — when dedup is needed
- `references/data-processing-pipeline.md` — data cleaning workflow
- `scripts/data_clean.py dedup` — exact-match dedup (faster, stricter)
- `scripts/embed_corpus.py dedupe` — semantic dedup via embeddings
