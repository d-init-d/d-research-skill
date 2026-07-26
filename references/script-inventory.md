# Script inventory

## Bundled helper scripts

The `scripts/` directory contains helper scripts for agents running in a local Node environment.

Use them when Playwright is installed and the task benefits from repeatable extraction:

- `scripts/playwright_probe.mjs`: classify a page, detect blockers, list links/files/tables, optionally screenshot, and fail closed on response, aggregate-network, request-count, or rendered-output limits
- `scripts/playwright_extract.mjs`: extract visible text, tables, links, metadata, and files into bounded JSON or Markdown under the shared browser limits
- `scripts/playwright_crawl.mjs`: bounded same-domain crawl with RFC 9309 percent-octet-aware robots matching, page manifests, and truthful structured incomplete output for page/domain/depth/network/output ceilings
- `scripts/evidence_ledger.py`: initialize and validate canonical 37-column investigative ledgers, preserve exact 14/19/22/23-column compatibility, and **HMAC-sign / verify** every active field
- `scripts/investigation_policy.py`: initialize/check tiered `R0`-`R4` scopes, bind time-bounded authorization attestations to canonical scope hashes, and classify social/non-official source disposition
- `scripts/api_fetch.mjs`: paginated API fetch with rate limiting, retry, and multiple output formats
- `scripts/data_clean.py`: data cleaning, deduplication, validation, statistics, and merging
- `scripts/citation_export.py`: backward-compatible BibTeX/RIS citation export, optional JSON-sidecar `@article`/`@book`/`@inproceedings` metadata overlay, and DOI enrichment via Crossref with DataCite fallback
- `scripts/resource_limits.py`: conservative HTTP/file/Excel/PDF/OCR/subprocess/table/Wayback/social caps; structured incomplete blockers on violation
- `scripts/check_contract.py`: dynamic version/config/path/count/CLI checks, strict post-RC metadata/path validation, and version-scoped release-waiver verification
- `scripts/package_manifest_check.mjs`: fail-closed npm tarball validation in Git worktrees and extracted source archives; rejects untracked/local/sensitive artifacts, missing tracked runtime files, and path-fingerprint drift
- `scripts/release_verify.py`: offline validation of exact-SHA GitHub Actions success and the default-policy GitHub tag/reviewer API responses; scoped waivers are authorized only by `check_contract.py`
- `scripts/_ssrf_helpers.py`: shared Python public-host / SSRF guards, DNS-pinned streaming HTTPS transport, and bounded same-origin-only private redirect policy for social, translation, and embedding callers
- `scripts/package_metadata.py`: canonical package-version and User-Agent resolver used by Python network helpers; standalone copies fall back to an explicit `unknown` version instead of a stale release number
- `scripts/content_sanitize.py`: production HTML/visible-text extraction, secret redaction, hostile-source processing, safe download names (used by multi_extract + quality eval)
- `scripts/lib/ssrf_guards.mjs`: shared public-host / SSRF guards + **connection-bound** `fetchPublicHttp` (Node; used by `api_fetch.mjs`)
- `scripts/lib/browser_ssrf.mjs`: context-level browser SSRF/read-only guard with Node-pinned GET/HEAD fulfillment, page-originated mutation-method blocking, aggregate/request budgets, service-worker blocking, and WebSocket fail-closed behavior; used by playwright probe/extract/crawl
- `scripts/lib/credentials.mjs`: credential classification and redaction for Node HTTP clients
- `scripts/lib/browser_limits.mjs`: shared Playwright response/output caps, structured exit-3 blockers, and limit parsing used by probe/extract/crawl
- `scripts/lib/package_metadata.mjs`: canonical package-version and User-Agent resolver shared by browser and Node network helpers
- `scripts/browser_smoke.mjs`: real Chromium launch + local fixture smoke (probe/extract/crawl/robots/TLS/local-only/browser SSRF adversarial/service-worker blocking)
- `scripts/adversarial_acceptance.py`: mandatory adversarial acceptance matrix; CI sets `D_RESEARCH_SKIP_BROWSER_SMOKE=1` and runs one explicit browser smoke per OS
- `scripts/citation_render.py`: render BibTeX into APA / MLA / IEEE / Chicago / Vancouver / Harvard / Nature / Science / ACM / AMA styles via pandoc + path-contained official CSL slug caching
- `scripts/extract_tables.py`: extract HTML `<table>` elements into CSV (handles `colspan`/`rowspan`, stdlib only)
- `scripts/score_source.py`: apply the `references/source-quality-rubric.md` rubric to an evidence ledger and emit per-row scores + bands
- `scripts/research_plan.py`: init / configure-execution / set-execution / bind-policy / render / approve / revoke / check / status / parallelizable / mark / block / add-task / gate — drives the long-horizon context-safe protocol and blocks investigative dispatch on policy drift
- `scripts/wikidata.py`: search / entity / disambiguate / sparql / self-test — Wikidata entity lookup, disambiguation, and SPARQL queries (see `adapters/wikidata.md`)
- `scripts/social_snapshot.py`: snapshot / verify / to-ledger / self-test — public social capture with transport-tier integrity, platform-neutral speaker/relationship/origin classification, lineage, and safe lead-by-default 37-column ledger output
- `scripts/pdf_extract.py`: text / meta / tables / to-ledger / self-test — PDF text, metadata, and table extraction via pdftotext / pdfinfo / pdfplumber with soft-fail when binaries are missing (see `references/pdf-extraction.md`)
- `scripts/wayback.py`: lookup / nearest / save / diff [--summarize --top-n N] / self-test — Wayback Machine snapshot lookup, archival, and diff summarization (see `references/wayback-archive.md` and `references/monitoring-change-detection.md`)
- `scripts/citation_resolver.py`: doi / pmid / arxiv / isbn / oa / to-ledger / to-bibtex / batch / self-test — academic identifier resolution via free public APIs (CrossRef, Datacite, NCBI, arXiv, Open Library, Unpaywall); see `adapters/citation-resolver.md`
- `scripts/report_render.py`: init / render / to-pdf / to-docx / to-html / list-styles / lint / self-test — final report generator with workspace containment, inert metadata, HTTP(S)-only source rendering, and investigative main/lead/blocked/contradiction partition enforcement
- `scripts/ocr.py`: text / pdf / to-ledger / langs / self-test — OCR via tesseract (optional system binary, soft-fail if missing); see `references/ocr.md`
- `scripts/translate.py`: text / detect / instances / self-test / production-self-test — translation adapter with optional deterministic langdetect, stdlib trigram fallback, and LibreTranslate/DeepL/Google/Argos backends; the production self-test exercises the real optional package offline; see `adapters/translation.md`
- `scripts/embed_corpus.py`: index / query / query-ledger / dedupe / self-test / production-self-test — retrieval over text corpora using cosine similarity; auto prefers the optional local sentence-transformers backend and otherwise uses built-in deterministic local hashing, while stub/remote/CLI backends require explicit selection; the production self-test uses a generated local model without downloads; see `references/semantic-retrieval.md`
- `scripts/citation_graph.py`: cited-by / references / expand / to-frontier / coauthors / self-test — citation graph traversal via OpenAlex for snowball sampling and network analysis; see `references/citation-graph.md`
- `scripts/multi_extract.py`: text / meta / tables / structured / mbox-search / to-ledger / self-test — unified extraction from DOCX, EPUB, XLSX, mbox, and HTML structured data; see `references/multi-format-extraction.md`
- `scripts/dedup_near.py`: fingerprint / scan / ledger / self-test — near-duplicate detection via SimHash + Hamming distance; see `references/deduplication.md`
- `scripts/http_cache.py`: get-key / stats / purge / self-test — shared HTTP cache with atomic fail-closed publication and strict purge verification (opt-in via `D_RESEARCH_HTTP_CACHE_PATH`); see `references/http-cache.md`
- `scripts/lib/http_cache.mjs`: Node ESM helper used by `api_fetch.mjs` for the same shared cache layout
- `scripts/bench_harness_check.py`: check / check-all / orphans / self-test — bench/fixture/harness consistency check. **NOT an agent benchmark** — only catches bench data regressions
- `scripts/quality_eval.py`: validate / list / integrity / hostile / fuzz / mutation / perf-compare / degraded / promotion-report / promotion-anti-spoof / self-test / triple — held-out research-quality suite, fail-closed enforcement of every promotion threshold, exact candidate/CI binding, integrity-covered evaluation and deterministic-run artifacts, citation/date integrity, and production-path hostile checks via `content_sanitize`. See `examples/evals/quality-suite.json` and `docs/eval.md`
- `scripts/web_search.mjs`: multi-engine web search with fallback chain (DuckDuckGo → SearXNG → Brave → Google CSE) and bounded credential-isolating manual redirects; see `adapters/web-search-only.md`
- `scripts/check_internal_refs.py`: validate backticked in-repo path references (CI guard)
- `scripts/run_python.mjs`: portable Node-to-Python wrapper that runs every bundled Python helper through one entry point (runtime-internal; used by all `npm run` Python scripts)
- `scripts/lib/config.mjs`: shared standard-library config loader — cwd-scoped `research.config.json` discovery, explicit `--config`, typed reads, and secret redaction; used by `api_fetch.mjs` (runtime-internal; see `references/config-reference.md`)
- `scripts/run_metadata.py`: record / self-test — append local run-metadata JSONL with optional `--redact-secrets`, `--command-hash`, and `--omit-hostname` privacy modes (strictly local, never uploaded)
- `scripts/harvest_terms.py`: harvest / self-test — harvest domain terms/jargon from collected text to seed register-aware search (runtime-internal)
- `scripts/run_dogfood.py`: self-test / validate / baseline / list / classes / render / score / compare — offline dogfood evaluation harness over bundled bench fixtures (developer-test; **not** an agent benchmark)
- `scripts/generate_test_pdf.py`: generate deterministic PDF fixtures for `pdf_extract` / `ocr` tests (developer-test)
- `scripts/check_node_syntax.py`: CI guard that `node --check`s every bundled `.mjs` (release-only)
- `scripts/check_no_plan_files.py`: CI guard that rejects stray planning/working files from the package (release-only)
- `scripts/check_doc_examples.py`: compile Python and syntax-check JavaScript fenced examples, plus UTF-8/mojibake screening (release-only)
- `scripts/build_release_artifacts.py`: deterministic-for-identical-input `full`/`runtime` artifact builder and trusted-profile verifier with bounded decompression, per-file/tree SHA-256 manifests, package-command closure, and forged-contract regression tests (release-only)
- `scripts/runtime_self_test.mjs`: dependency-light extracted-runtime verification that rejects hostile/release/CI payloads and dangling commands or references (runtime-internal)

The scripts are optional. If dependencies are unavailable, follow the workflow manually using the agent's browser or web tools.

## Verification entry points

- `npm run self-test:node`: offline Node helper self-tests; CI runs this on Node 18/20/22.
- `npm run package:check`: dry-run the npm tarball and require a tracked-only, secret-free, complete runtime manifest.
- `npm run self-test:python`: offline Python helper and contract checks through the portable Node-to-Python wrapper (includes `quality_eval.py self-test`).
- `npm run eval:quality`: held-out quality suite offline self-test (validate + integrity + hostile + fuzz + mutation + degraded + perf).
- `npm run self-test`: complete offline Node + Python helper suite.
- `npm run self-test:source`: full source suite plus the frozen v3.3.0 capability-superset gate.
- `npm run self-test:runtime`: extracted runtime-profile syntax and functional checks without release/eval payloads.
- `npm run artifact:self-test`: deterministic build-twice, extraction, manifest, route-closure, and profile verification.
- `npm run acceptance`: adversarial acceptance matrix; its normal local run includes the browser case.
- `npm run browser:smoke`: one real Chromium run against local fixtures.

CI runs the full offline suite on Ubuntu and Windows, then the adversarial matrix
without its embedded browser case, then exactly one explicit browser smoke. The
exact Playwright package version in `package.json` locks the corresponding
Chromium revision installed by Playwright.


See also: SKILL.md (core workflow), adapters/, references/config-reference.md.
