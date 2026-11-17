# D Research v3.8.0-rc.1

## v3.8.0-rc.1 Release Notes

This signed release-candidate snapshot prepares **D Research 3.8.0** for stable promotion and freezes the future stable release notes and package manifest before promotion.

### Highlights in this candidate

- **Open-Scholarly & Community Federated Search (`scripts/web_search.mjs`)**: Added SSRF-guarded zero-key `openalex`, `crossref`, bilingual `wikipedia` (`EN`/`VI`), and `hn-algolia` providers to the search transport layer, plus balanced round-robin `--federated` diversity merging so scholarly, reference, and practitioner voices remain balanced without API keys.
- **Multilingual & Vietnamese Term Harvesting (`scripts/harvest_terms.py`)**: Fixed 1-2 character syllable dropping (`tỷ giá`, `nợ xấu`, `dự trữ`, `y tế`, `ô nhiễm`, `độ trễ`) via `_is_valid_bigram_token`, expanded `_CAPTURE_STOPWORDS`, and Unicode word-boundary tokenization.
- **Ledger-Native Cross-Branch Reconciliation (`scripts/reconciliation.py`)**: Added `reconcile_from_ledger()` and `--ledger <csv>` CLI execution so live 14/19/22/23/37-column CSV evidence ledgers flow directly into `E03`-`E06` contradiction resolution without manual fixture conversion.
- **Automated Domain & Quote Lineage Inference (`scripts/lineage_tracker.py`)**: Added `analyze_ledger()` and `analyze-ledger` CLI workflow to infer independent-origin families, shared domains, mirrors, and syndicated quotes directly from CSV ledgers.
- **Paraphrase-Aware Source Grounding & CLI (`scripts/source_grounding.py`)**: Preserved deterministic `assess_source_context()` while adding `assess_paraphrase_grounding()`, `audit_ledger_grounding()`, and `check` / `audit-ledger` CLI subcommands with numeric-conflict and negation-mismatch detection.
- **Hybrid BM25 + Semantic Corpus Retrieval (`scripts/embed_corpus.py`)**: Added BM25 lexical scoring combined with dense cosine similarity and numeric/acronym exact-match boosting (`--hybrid-alpha`, default `0.35`) for `query` and `query-ledger`.
- **Expanded Interop Entrypoints (`templates/route-manifest.json`, `templates/interop-contract.json`)**: Registered all upgraded workflow helpers in `cli_contracts` and `entrypoints` so downstream runtimes (**Aleph Skill v2.9.0**) can dispatch them with full path-safety checks.

See [stable release notes](release-v3.8.0.md) for full technical architecture, compatibility, upgrade instructions, and SHA-256 verification commands. This candidate tag is not itself the stable release.
