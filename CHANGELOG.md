# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

Nothing yet.

## [3.0.0] - 2026-05-19

This release finalises the v3.0 production-grade core. It is the cumulative
result of nine focused PRs (#1–#9) plus this release-polish PR (#10). All
self-tests run offline; no PR introduced a runtime network dependency.

### Added

- **Two-tier offline eval harness with frontier bench 2.1**
  (`examples/evals/dogfood-bench.json`, `examples/evals/frontier-bench.json`).
  Tier 1 is a 12-task regression guard; Tier 2 is a 50-task / 25-class
  frontier probe covering hard atomic facts, subtle contradictions, hidden
  refusal triggers, long-horizon planning, API drift, systematic review,
  large-scale collection, monitoring, multilingual research, anti-bot
  fallback, PDF extraction, Wayback archive, Wikidata disambiguation,
  social-media Tier A and Tier B, social refusal, citation resolution,
  report generation, OCR extraction, translation, semantic retrieval,
  citation-graph traversal, multi-format extraction, dedup-and-cache, and
  provenance/compliance.
- **Wayback Machine integration**: `scripts/wayback.py` with `lookup`,
  `nearest`, `save`, and `diff --summarize` (top-N hunks).
- **Citation resolver**: `scripts/citation_resolver.py` for DOI / PMID /
  arXiv / ISBN canonical metadata via free public APIs (CrossRef,
  Datacite, NCBI, arXiv, Open Library, Unpaywall) with a `to-ledger` and
  `to-bibtex` short-circuit. See `adapters/citation-resolver.md`.
- **Report generator**: `scripts/report_render.py` with `init`, `render`,
  `to-pdf`, `to-docx`, `to-html`, `lint`, and `list-styles`.
  Pandoc/wkhtmltopdf/weasyprint are optional and the script soft-fails
  when they are missing.
- **OCR + translation**: `scripts/ocr.py` (tesseract optional) and
  `scripts/translate.py` (LibreTranslate / DeepL / Google / Argos with an
  explicit `--allow-remote` privacy gate; default backend stays local /
  stub).
- **Semantic retrieval**: `scripts/embed_corpus.py` with stub /
  sentence-transformers / Cohere / `llama-cli` backends and a same-
  backend query path. Index metadata records backend, model, and
  embedding dimension so a query that mismatches hard-fails.
- **Citation-graph traversal**: `scripts/citation_graph.py` over the
  OpenAlex public API (`cited-by`, `references`, `expand`, `to-frontier`,
  `coauthors`) with a global cap and frontier-ledger emitter that matches
  the exact 13-column `templates/frontier-ledger.csv` schema.
- **Multi-format extraction**: `scripts/multi_extract.py` for DOCX,
  EPUB, XLSX (stdlib `zipfile` + XML, including inlineStr cells and
  sparse columns), `mbox`, and HTML structured data (JSON-LD,
  microdata, RDFa).
- **Near-duplicate detection**: `scripts/dedup_near.py` using a 64-bit
  SimHash plus Hamming distance over normalised token shingles, with
  `fingerprint`, `scan`, and `ledger` subcommands.
- **Shared HTTP cache** (opt-in via `D_RESEARCH_HTTP_CACHE_PATH`):
  `scripts/http_cache.py` and `scripts/lib/http_cache.mjs`. The cache key
  hashes auth-affecting request headers (Authorization, Cookie,
  X-API-Key, API-Key, Accept, Accept-Language) so a Bearer-A response is
  never replayed for a Bearer-B or no-auth request. Integrated into
  `scripts/api_fetch.mjs`, `scripts/wayback.py`, `scripts/wikidata.py`,
  `scripts/citation_resolver.py`, and `scripts/citation_graph.py`.
- **Evidence-ledger v3.0 schema** (additive): three optional columns
  appended to the existing v2.1 social schema:
  - `license_spdx` (SPDX-style token, `NOASSERTION`, or `LicenseRef-…`),
  - `robots_status` (`allowed`, `disallowed`, `unknown`, `not_checked`,
    `not_applicable`, or empty),
  - `prov_activity_id` (stable `prov:<script>:<hash>` or UUID-like
    identifier).
  All three are validated, included in HMAC canonical bytes, and emitted
  by `social_snapshot.py`, `pdf_extract.py`, `multi_extract.py`,
  `ocr.py`, and `citation_resolver.py`.
- **PROV-O export**: `evidence_ledger.py prov-export` writes a JSON-LD
  graph with `prov:Entity`, `prov:Activity`, `prov:wasGeneratedBy`, and
  `prov:used` links. Accepts 14, 19, or 22-column ledgers; the activity
  graph is populated only when `prov_activity_id` is non-empty.
- **Bench-harness consistency check**: `scripts/bench_harness_check.py`
  with a CI job that fails when scoring drifts away from the frozen
  empty-score fixtures.
- **Run metadata capture**: `scripts/run_metadata.py` records local
  JSONL metadata (git SHA, timestamp, hostname, Python / Node version,
  optional command label). Strictly local; never uploaded.
- **Refusal i18n templates**: `references/i18n/refusal.en.json` and
  `references/i18n/refusal.vi.json` cover minor / third-party-mirror /
  harassment / private-individual refusals. `social_snapshot.py`
  recognises `--locale en|vi`; default remains `en`.
- **Pre-commit config**: `.pre-commit-config.yaml` runs `ruff` on
  `scripts/`, `node --check` on every `.mjs`, and the internal-refs
  check.
- **Decision-tree completeness check**:
  `scripts/check_internal_refs.py --decision-tree` verifies that every
  reference doc is reachable from the `SKILL.md` decision tree or the
  workflow checklists.

### Changed

- `evidence_ledger.py init` now writes the 22-column header by default
  (still backward compatible with 14 and 19-column inputs).
- `social_snapshot.py to-ledger`, `pdf_extract.py to-ledger`,
  `multi_extract.py to-ledger`, `ocr.py to-ledger`, and
  `citation_resolver.py to-ledger` emit 22-column rows with sensible
  provenance defaults (no false `robots_status: allowed` claims).
- `references/evidence-ledger.md` documents the v3.0 schema, the
  backward-compat matrix, the robots semantics ("never claim allowed
  unless checked"), and the PROV-O export contract.
- `templates/evidence-ledger.csv` upgraded to 22 columns with realistic
  example values.
- `scripts/check_internal_refs.py` skips PLAN-* roadmap files (they
  intentionally reference scripts that may not exist yet).
- README.md reorganised around the actual research lifecycle pillars
  (discover → fetch → extract → analyze → synthesize → report → audit).
- README.vi.md mirrors the v3.0 capability summary in Vietnamese.
- CONTRIBUTING.md updated with v3.0 commands, pre-commit guidance, and
  PLAN-file exclusion rules.
- `package.json` bumped to `1.0.0` and ships an updated self-test chain
  that includes `dedup_near`, `http_cache`, and `run_metadata`.

### Fixed

- HTTP cache no longer reuses a Bearer-A response for an unauthenticated
  request (cache key now hashes the canonical request-header subset).
- `api_fetch.mjs` applies `--params` to the URL **before** any cache
  lookup so a parameter change always misses the cache.
- Cache integration in Python fetchers isolates
  `D_RESEARCH_HTTP_CACHE_PATH` inside `self-test`, so a stale local
  cache cannot mask the mocked HTTP layer.
- `multi_extract.py` XLSX parser now supports `inlineStr` cells and
  preserves sparse column positions (`A1`, `C1` → `["A","","C"]`).
- `multi_extract.py` HTML structured extractor now emits
  `json_ld`, `microdata`, **and** `rdfa` keys (was JSON-LD only).
- `multi_extract.py` metadata path no longer relies on `/dev/null`
  pandoc behaviour; uses stdlib ZIP/XML for DOCX/XLSX/EPUB.
- `citation_resolver.py to_ledger_row` now emits the full 19/22-column
  evidence-ledger schema, not a truncated row.
- `citation_graph.py` snowball expansion enforces the global node cap
  before recursing into the second hop in `expand`.
- `report_render.py` `_verify_signature` calls `verify_ledger` via
  `contextlib.redirect_stdout` so signed-ledger validation no longer
  pollutes the report output.

### Security

- **Auth/cookie isolation in HTTP cache.** Authorization, Cookie,
  X-API-Key, API-Key, Accept, and Accept-Language headers are hashed
  into the cache key. Request headers are **never** persisted in cache
  metadata (only the response headers are).
- **Privacy boundary in social capture.** `social_snapshot.py` refuses
  minors, private individuals, harassment / stalking / doxxing framings,
  third-party mirror URLs, and login-bypass attempts before any HTTP
  call. Refusal text is now i18n-aware via `--locale`.
- **HMAC tamper detection extended to v3.0 columns.** Tampering with
  `license_spdx`, `robots_status`, or `prov_activity_id` in a signed
  22-column ledger is now caught by `evidence_ledger.py verify`.

### Deferred to v3.1

- Audio/video extraction beyond OCR (whisper / ffmpeg pipeline).
- Local task-runner / job-queue script.
- Auto-discovered evidence-ledger plug-ins.

### Tag commands (run after merge)

These commands are documented for the maintainer; they are intentionally
**not** executed by this PR. Running them creates three tags: a retroactive
release tag for v2.1, a frozen bench tag for the v2.1 frontier suite, and
the v3.0 release tag itself.

```bash
# Retro-tag v2.1.0 on the historical commit that shipped 2.1.
git tag -a v2.1.0 5574a9e -m "v2.1.0 research reach and social archival"

# Freeze the current frontier bench (50 tasks / 25 classes, bench_version 2.1)
# on HEAD. Independent of the release tag so downstream agent runs can pin
# to the exact bench they were scored against.
git tag -a bench/v2.1 -m "bench v2.1 frontier suite"

# Release tag for v3.0.0 on HEAD.
git tag -a v3.0.0 -m "v3.0.0 production-grade research skill"

# Push all three together.
git push origin v2.1.0 bench/v2.1 v3.0.0
```

## [2.1.0] - 2025-12 (historical)

- Social-media archival (Tier A direct API + Tier B Wayback) with
  19-column evidence-ledger schema (added `archive_url`,
  `content_hash`, `snapshot_status`, `verifiability`,
  `verifiability_note`).
- Long-horizon research-plan workspaces (`scripts/research_plan.py`)
  with explicit `plan_ready` gate.
- Frontier search controller with `templates/frontier-ledger.csv` and
  `templates/coverage-map.json`.

## [2.0.0] - 2025-09 (historical)

- Initial public skill with browser-first probing, 14-column
  evidence-ledger schema, anti-bot fallback chain, citation export,
  systematic-review protocol, and PRISMA flow template.

[Unreleased]: https://github.com/d-init-d/d-research-skill/compare/v3.0.0...HEAD
[3.0.0]: https://github.com/d-init-d/d-research-skill/releases/tag/v3.0.0
[2.1.0]: https://github.com/d-init-d/d-research-skill/releases/tag/v2.1.0
[2.0.0]: https://github.com/d-init-d/d-research-skill/releases/tag/v2.0.0
