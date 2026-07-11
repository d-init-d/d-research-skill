# Script inventory

## Bundled helper scripts

The `scripts/` directory contains helper scripts for agents running in a local Node environment.

Use them when Playwright is installed and the task benefits from repeatable extraction:

- `scripts/playwright_probe.mjs`: classify a page, detect blockers, list links/files/tables, optionally screenshot, and fail closed on an oversized main response
- `scripts/playwright_extract.mjs`: extract visible text, tables, links, metadata, and files into JSON or Markdown with the shared response cap
- `scripts/playwright_crawl.mjs`: bounded same-domain crawl with robots awareness, page manifests, and structured incomplete output on response-limit failures
- `scripts/evidence_ledger.py`: initialize, validate, and **HMAC-sign / verify** CSV evidence ledgers
- `scripts/api_fetch.mjs`: paginated API fetch with rate limiting, retry, and multiple output formats
- `scripts/data_clean.py`: data cleaning, deduplication, validation, statistics, and merging
- `scripts/citation_export.py`: BibTeX/RIS citation export and DOI enrichment via Crossref with DataCite fallback
- `scripts/resource_limits.py`: conservative HTTP/file/Excel/PDF/OCR/subprocess/table/Wayback/social caps; structured incomplete blockers on violation
- `scripts/check_contract.py`: dynamic version/config/path/count/CLI contract checks for release readiness
- `scripts/_ssrf_helpers.py`: shared public-host / SSRF guard helpers (Python; DNS-pinned open for social)
- `scripts/lib/ssrf_guards.mjs`: shared public-host / SSRF guard helpers (Node; used by `api_fetch.mjs` on URL + redirect hops)
- `scripts/lib/credentials.mjs`: credential classification and redaction for Node HTTP clients
- `scripts/lib/browser_limits.mjs`: shared Playwright main-document response cap, structured exit-3 blocker, and limit parsing used by probe/extract/crawl
- `scripts/browser_smoke.mjs`: real Chromium launch + local fixture smoke (probe/extract/crawl/robots/TLS/local-only)
- `scripts/adversarial_acceptance.py`: mandatory 27-case adversarial acceptance matrix; CI sets `D_RESEARCH_SKIP_BROWSER_SMOKE=1` and runs one explicit browser smoke per OS
- `scripts/citation_render.py`: render BibTeX into APA / MLA / IEEE / Chicago / Vancouver / Harvard / Nature / Science / ACM / AMA styles via pandoc + CSL
- `scripts/extract_tables.py`: extract HTML `<table>` elements into CSV (handles `colspan`/`rowspan`, stdlib only)
- `scripts/score_source.py`: apply the `references/source-quality-rubric.md` rubric to an evidence ledger and emit per-row scores + bands
- `scripts/research_plan.py`: init / configure-execution / set-execution / render / approve / revoke / check / status / parallelizable / mark / block / add-task / gate — drives the long-horizon context-safe protocol in `references/research-plan-protocol.md`
- `scripts/wikidata.py`: search / entity / disambiguate / sparql / self-test — Wikidata entity lookup, disambiguation, and SPARQL queries (see `adapters/wikidata.md`)
- `scripts/social_snapshot.py`: snapshot / verify / to-ledger / self-test — public social-media post capture with two-tier architecture, content hashing, and evidence-ledger integration (see `references/social-media-archival.md`)
- `scripts/pdf_extract.py`: text / meta / tables / to-ledger / self-test — PDF text, metadata, and table extraction via pdftotext / pdfinfo / pdfplumber with soft-fail when binaries are missing (see `references/pdf-extraction.md`)
- `scripts/wayback.py`: lookup / nearest / save / diff [--summarize --top-n N] / self-test — Wayback Machine snapshot lookup, archival, and diff summarization (see `references/wayback-archive.md` and `references/monitoring-change-detection.md`)
- `scripts/citation_resolver.py`: doi / pmid / arxiv / isbn / oa / to-ledger / to-bibtex / batch / self-test — academic identifier resolution via free public APIs (CrossRef, Datacite, NCBI, arXiv, Open Library, Unpaywall); see `adapters/citation-resolver.md`
- `scripts/report_render.py`: init / render / to-pdf / to-docx / to-html / list-styles / lint / self-test — final report generator from research workspace (plan + ledger + screening log); see `references/report-generation.md`
- `scripts/ocr.py`: text / pdf / to-ledger / langs / self-test — OCR via tesseract (optional system binary, soft-fail if missing); see `references/ocr.md`
- `scripts/translate.py`: text / detect / instances / self-test — translation adapter with stdlib trigram language detection and LibreTranslate/DeepL/Google/Argos backends; see `adapters/translation.md`
- `scripts/embed_corpus.py`: index / query / query-ledger / dedupe / self-test — semantic retrieval over text corpora using cosine similarity with stub/sentence-transformers/cohere/llama-cli backends; see `references/semantic-retrieval.md`
- `scripts/citation_graph.py`: cited-by / references / expand / to-frontier / coauthors / self-test — citation graph traversal via OpenAlex for snowball sampling and network analysis; see `references/citation-graph.md`
- `scripts/multi_extract.py`: text / meta / tables / structured / mbox-search / to-ledger / self-test — unified extraction from DOCX, EPUB, XLSX, mbox, and HTML structured data; see `references/multi-format-extraction.md`
- `scripts/dedup_near.py`: fingerprint / scan / ledger / self-test — near-duplicate detection via SimHash + Hamming distance; see `references/deduplication.md`
- `scripts/http_cache.py`: get-key / stats / purge / self-test — shared HTTP cache (opt-in via `D_RESEARCH_HTTP_CACHE_PATH`); see `references/http-cache.md`
- `scripts/lib/http_cache.mjs`: Node ESM helper used by `api_fetch.mjs` for the same shared cache layout
- `scripts/bench_harness_check.py`: check / check-all / orphans / self-test — bench/fixture/harness consistency check. **NOT an agent benchmark** — only catches bench data regressions
- `scripts/quality_eval.py`: validate / list / integrity / hostile / fuzz / mutation / perf-compare / degraded / promotion-report / self-test / triple — held-out research-quality suite (schema 1.0, ≥30 cases), evidence-integrity checks, hostile-source acceptance, seeded property tests, mutation probes, performance budgets, degraded-mode checks. See `examples/evals/quality-suite.json` and `docs/eval.md`
- `scripts/web_search.mjs`: multi-engine web search with fallback chain (DuckDuckGo → SearXNG → Brave → Google CSE); see `adapters/web-search-only.md`
- `scripts/check_internal_refs.py`: validate backticked in-repo path references (CI guard)

The scripts are optional. If dependencies are unavailable, follow the workflow manually using the agent's browser or web tools.

## Verification entry points

- `npm run self-test:node`: offline Node helper self-tests; CI runs this on Node 18/20/22.
- `npm run self-test:python`: offline Python helper and contract checks through the portable Node-to-Python wrapper (includes `quality_eval.py self-test`).
- `npm run eval:quality`: held-out quality suite offline self-test (validate + integrity + hostile + fuzz + mutation + degraded + perf).
- `npm run self-test`: complete offline Node + Python helper suite.
- `npm run acceptance`: adversarial acceptance matrix; its normal local run includes the browser case.
- `npm run browser:smoke`: one real Chromium run against local fixtures.

CI runs the full offline suite on Ubuntu and Windows, then the adversarial matrix
without its embedded browser case, then exactly one explicit browser smoke. The
exact Playwright package version in `package.json` locks the corresponding
Chromium revision installed by Playwright.


See also: SKILL.md (core workflow), adapters/, references/config-reference.md.
