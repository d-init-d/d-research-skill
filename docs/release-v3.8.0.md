# D Research v3.8.0

## v3.8.0 Release Notes

## Open-scholarly federation. Bilingual precision. Ledger-native grounding & lineage.

**D Research 3.8.0** upgrades the research stack from raw web capture into a zero-key federated discovery, bilingual Vietnamese/English terminology mining, automated contradiction reconciliation, lineage-auditing, and paraphrase-grounded evidence engine — ready for standalone agent workflows and byte-locked integration inside **Aleph Skill v2.9.0**.

This official stable release is promoted from the signed `v3.8.0-rc.1` candidate tag under the repository owner's scoped promotion contract (`release-evidence/v3.8.0/`), preserving deterministic `full` and `runtime` distribution profiles, immutable Git source archival, and GitHub build provenance attestation.

---

### What's New in v3.8.0

#### 1. Zero-Key Open-Scholarly & Community Federated Search (`scripts/web_search.mjs`)
- **Four New Built-in Providers (All SSRF-Guarded via `fetchPublicHttp`):**
  - `openalex` — OpenAlex Works API (`/works`) returning peer-reviewed papers, citation/year/host metadata, and DOI/landing URLs with no API key required.
  - `crossref` — Crossref REST Works API (`/works`) for authoritative DOI, publisher, journal, and title resolution.
  - `wikipedia` — Bilingual Wikipedia MediaWiki Search API with automatic English/Vietnamese language detection (`en.wikipedia.org` / `vi.wikipedia.org`) when `--lang auto` or `--query` contains Vietnamese diacritics.
  - `hn-algolia` — Hacker News Algolia Search API (`hn.algolia.com/api/v1/search`) for engineering postmortems and practitioner discussions.
- **Balanced `--federated` Diversity Merging:** Instead of truncating results from later providers, `--federated` interleaves unique canonical URLs across active engines in balanced round-robin turns (`min(limit, results.length)`), raising source diversity while preserving DuckDuckGo + SearXNG fallback order.
- **Direct Engine Selection:** `--engine openalex|crossref|wikipedia|hn-algolia` works independently or as part of fallback/federated sweeps, covered by 65 unit/integration assertions in `--self-test` and transport boundary tests.

#### 2. Multilingual & Vietnamese Term Harvesting (`scripts/harvest_terms.py`)
- **Fixed Short-Syllable Bigram Drops:** Replaced the 3-character-per-token floor on un-hyphenated bigrams with `_is_valid_bigram_token()` + `_CAPTURE_STOPWORDS`, preserving high-signal 1-2 character Vietnamese technical and economic compounds such as `tỷ giá`, `nợ xấu`, `dự trữ`, `y tế`, `ô nhiễm`, and `độ trễ`.
- **Expanded Bilingual Stopwords & Unicode Segmentation:** Broadened Vietnamese and English functional stopwords so multi-round iterative term expansion surfaces genuine domain terminology rather than conjunctions or particles.

#### 3. Ledger-Native Cross-Branch Reconciliation (`scripts/reconciliation.py`)
- **Direct CSV Ledger Pipeline (`reconcile_from_ledger()` & `--ledger <csv>`):** Analyzes 14/19/22/23/37-column evidence ledgers directly from disk, pairing claims sharing normalized entities or sub-questions against bilingual correction, temporal supersession, scope divergence, and empirical-vs-speculation signals (`E03`–`E06`).
- **Backward Compatibility:** Existing fixture-based reconciliation (`--fixtures`) remains intact alongside structured JSON output (`--out`).

#### 4. Automated Domain & Quote Lineage Inference (`scripts/lineage_tracker.py`)
- **Ledger Lineage Analyzer (`analyze_ledger()` & `analyze-ledger` CLI):** Automatically clusters ledger claims by canonical domain, mirror/syndication pairs, and shared quote/evidence n-grams to compute `independent_origin_count` without manual graph construction.
- **Self-Test Verification:** Added standalone `python3 scripts/lineage_tracker.py self-test` contract checks.

#### 5. Paraphrase-Aware Grounding & Ledger Audit (`scripts/source_grounding.py`)
- **Dual-Mode Grounding Engine:** Preserves strict `assess_source_context()` backward compatibility while adding `assess_paraphrase_grounding()` and `audit_ledger_grounding()` to detect:
  - numeric mismatches (`9.4%` vs `4.9%`),
  - negation polarity flips, and
  - token/n-gram paraphrase overlap (`overlapping` / `grounded` / `ungrounded`) against snapshot files or evidence text.
- **First-Class CLI (`check`, `audit-ledger`, `self-test`):** Executable directly or through Aleph's `research:grounding` gateway route.

#### 6. Hybrid BM25 + Semantic Corpus Retrieval (`scripts/embed_corpus.py`)
- **Hybrid Scoring (`--hybrid-alpha`, default `0.35`):** Combines dense cosine similarity with Okapi BM25 lexical scoring plus exact numeric and uppercase acronym boost across both `query` and `query-ledger`, eliminating blind spots on statistics, version numbers, and technical identifiers.

#### 7. Interop & Downstream Gateway Surface (`templates/route-manifest.json`, `templates/interop-contract.json`)
- Added `scripts/browser_interaction.mjs`, `scripts/embed_corpus.py`, `scripts/execution_evidence.py`, `scripts/harvest_terms.py`, `scripts/lineage_tracker.py`, `scripts/reconciliation.py`, `scripts/research_controller.py`, and `scripts/source_grounding.py` to `cli_contracts` and `interop-contract.json` `entrypoints` for direct validated dispatch from **Aleph Skill v2.9.0**.

---

### Upgrade Guidance

- **Standard installation:** Download `d-research-3.8.0-runtime.tar.gz` for lightweight runtime deployment (or consume directly via **Aleph Skill v2.9.0** where it is byte-locked under `components/d-research/`).
- **Development & validation:** Download `d-research-3.8.0-full.tar.gz` or `d-research-skill-v3.8.0.tar.gz` (immutable tagged Git source archive).
- **Backward compatibility:** Existing 14/19/22/23/37-column CSV evidence ledgers, schema 2.0 research plans, and all 28 research routes remain supported with zero breaking schema migrations. Core Python scripts remain stdlib-only.

| Component | Requirement / Support |
|---|---|
| Python | 3.10 or newer (stdlib-only core scripts) |
| Node.js | 18 or newer |
| Browser Automation | Host-integrated browser (Tier 1A) or Playwright `1.61.1` (Tier 1B) |
| Evidence Ledger | 14 / 19 / 22 / 23 / 37-column contracts with HMAC-SHA256 signing |
| License | `CC-BY-NC-4.0` (unchanged) |

---

### Release Assets & Verification

Download the release assets and `SHA256SUMS` into a single directory and verify integrity and GitHub provenance attestation before extraction:

```sh
sha256sum -c SHA256SUMS

gh attestation verify d-research-skill-v3.8.0.tar.gz \
  --repo d-init-d/d-research-skill \
  --signer-workflow d-init-d/d-research-skill/.github/workflows/release-attest.yml
```

From the extracted `full` or source directory, verify local helpers with:

```sh
npm ci --ignore-scripts --no-audit --no-fund
npm run self-test
D_RESEARCH_SKIP_BROWSER_SMOKE=1 npm run acceptance
```

**Full changelog:** [v3.7.0...v3.8.0](https://github.com/d-init-d/d-research-skill/compare/v3.7.0...v3.8.0)
