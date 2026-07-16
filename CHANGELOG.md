# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [3.2.1] - 2026-07-16

Stable production release promoting the exact v3.2.1-rc.2 candidate without
executable-code, dependency, workflow, route, or package-path drift.

### Added

- Production-capable offline semantic retrieval that prefers an installed
  `sentence-transformers` backend and otherwise uses deterministic
  `local-hashing`; the stub backend is now test-only and explicit.
- Validated citation metadata for conservative `@article`, `@book`, and
  `@inproceedings` BibTeX exports, including structured personal names and
  literal corporate authors/editors, with safe `@misc` fallback.
- Deterministic local `langdetect` and stdlib trigram language-detection
  backends without a new mandatory dependency or remote request.

### Changed

- CI now exercises the real optional semantic and language backends offline
  across the supported Python matrix.
- Stable promotion derives scores from canonical schema-2.1 raw task bundles,
  binds them through schema-1.2 promotion evidence, and requires independent
  review of live-run origin, raw artifacts, and score recomputation.

### Release assurance

- The promoted candidate commit is
  `520915764a97d717aaf4682e02b8aae5dc511d2f`; Git tag object
  `fd309e47c9681a391621bf7b842893d5a2d15ab0` binds the GitHub-verified
  annotated `v3.2.1-rc.2` tag to that exact tree.
- Candidate exact-SHA CI, source archive/checksum replay, independent archive
  reproduction, and GitHub build-provenance attestation passed before stable
  preparation.
- Live dogfood produced 128 canonical baseline/candidate bundles under one
  Grok Build runtime, model, tool configuration, and evaluator binding. All
  four score files have zero failed and zero not-run tasks; both tiers are
  unchanged, and neither tier contains a contract-defined regression or safety
  regression; per-task metric movement remains preserved in the score
  artifacts.
- At the maintainer's explicit direction, publication proceeded without an
  independent GitHub review or `reviewer-signoff.json`. No such sign-off or
  green stable-promotion attestation is claimed; this is a maintainer-published
  release rather than a contract-compliant `live_evidence` promotion.

## [3.2.1-rc.2] - 2026-07-16

Release-assurance correction for the v3.2.1 candidate. Skill behavior,
dependencies, routes, and evidence-ledger schemas are unchanged from rc.1.

### Fixed

- Fixed the default-branch provenance workflow to read the `workflow_run`
  webhook from GitHub Actions' guaranteed `GITHUB_EVENT_PATH` environment
  variable. The prior expression-derived alias could be empty in a live run,
  preventing artifact selection before independent checksum, signed-tag,
  archive-reproduction, and provenance checks.
- Added a dynamic contract assertion and mutation self-test that reject the
  expression-derived alias and require both webhook validation stages to use
  `GITHUB_EVENT_PATH` directly.

### Changed

- Rebound release metadata and the frozen live-evidence promotion contract to
  `v3.2.1-rc.2`; stable v3.2.1 must dogfood and promote this exact candidate.

## [3.2.1-rc.1] - 2026-07-15

Production-hardening release candidate that upgrades three optional helper
paths from fallback- or test-oriented defaults to production-capable behavior
while retaining dependency-free fallbacks. The canonical evidence-ledger
schema and read-only research contract are unchanged.

### Added

- Added optional JSON citation-metadata sidecars to export conservative
  `@article`, `@book`, and `@inproceedings` BibTeX entries while preserving the
  canonical evidence-ledger schema and the legacy `@misc` fallback.
- Added explicit corporate-author and corporate-editor support through
  `{"literal": "Organization Name"}` metadata, preserving organizations as
  single BibTeX and CSL names.
- Added deterministic, local `langdetect` support through the optional
  `language-detection` extra, with explicit backend selection and a stdlib
  trigram fallback.
- Added CI integration tests that exercise the real `sentence-transformers`
  and `langdetect` packages offline, using a generated local embedding model
  so the test never downloads model weights.
- Added schema-1.2 stable-promotion evidence that binds each Tier-1/Tier-2
  score artifact to its complete canonical raw-run bundle and records an
  independent review scope covering live-run origin, raw artifacts, and score
  recomputation.

### Changed

- Semantic indexing and direct ledger queries now default to an `auto` backend
  that selects local `sentence-transformers` when installed and otherwise uses
  a deterministic built-in word/character hashing backend. Auto never selects
  a remote backend or the test-only stub, and existing dependency-free
  invocations continue to work. Install `.[embeddings]` for trained semantic
  similarity; explicitly pass `--backend stub` only for test fixtures.
- Upgraded the SHA-pinned release actions to
  `actions/upload-artifact@v7.0.1` and
  `actions/attest-build-provenance@v4.1.1` for future release tags.
- Upgraded the development and CI Ruff pin from `0.15.13` to `0.15.21`.

### Fixed

- The contract check now rejects drift between the Ruff version declared in
  `pyproject.toml` and the version installed by CI.
- The release archive workflow now resolves the dogfood baseline tag from the
  frozen route manifest instead of hard-coding the v3.1.1 release line.
- The release archive workflow now proves that the frozen baseline commit is
  an ancestor of the dogfooded candidate before evaluating either RC or stable
  release evidence.
- The historical annotated `v3.2.0` baseline tag is now pinned to its exact tag
  object SHA. Its legacy unsigned status is recorded explicitly instead of
  being treated as GitHub-verified.
- Stable promotion now re-verifies successful full CI for both the exact
  dogfooded candidate SHA and the metadata-only stable SHA.
- Pull-request CI now explicitly checks out and asserts the PR head SHA instead
  of testing GitHub's synthetic merge ref while labeling the run as candidate CI.
- Tag validation/build runs with read-only permissions; privileged provenance
  attestation moved to a default-branch `workflow_run` that re-verifies the
  signed tag, metadata, checksum, and reproduced archive without executing tag code.
- Stable promotion now rejects self-declared scores: it validates the exact
  canonical task-directory set, hashes raw prompt/output/ledger artifacts,
  binds canonical rendered prompts and the 23-column ledger header, freezes
  per-tier thresholds, and recomputes score artifacts from the raw runs.
- Stable evidence now rejects failed or not-run executions, requires a factual
  pass beyond refusal probes in every tier, pins the evaluator harness to the
  candidate commit, rejects duplicate timestamp instants even when RFC 3339
  offsets differ, and enforces
  `run.finished_at <= score.created_at <= promotion.generated_at`.
- Sentence-transformers model load and encode failures now return a controlled,
  actionable backend error instead of escaping as a Python traceback.
- Semantic indexes and backend responses now reject duplicate/non-finite JSON,
  wrong vector counts, ragged or non-numeric embeddings, invalid entry fields,
  and blank queries with controlled diagnostics; empty local-hashing documents
  produce zero vectors instead of false duplicate matches.
- Citation metadata now rejects duplicate/non-finite JSON values and conflicting
  explicit DOI versus DOI-resolver URL identities. The `accessed` alias is
  normalized to `date_accessed`, with conflicting aliases rejected.
- Crossref and DataCite enrichment now preserves structured personal names,
  editors, and organizational contributors instead of flattening corporate
  identities into ambiguous strings.
- Stable-evidence path derivation now resolves both sides before computing
  repository-relative paths, preventing Windows 8.3 temporary-directory aliases
  from crashing contract validation.
- The Windows Python launcher now prefers the active PATH interpreter before the
  global `py` launcher, so virtual environments and CI matrix versions are honored.

## [3.2.0] - 2026-07-13

Production-ready release of the schema-2.0 D Research workflow. The stable tree
promotes the fully tested v3.2.0-rc.3 candidate without executable-code,
dependency, workflow, or package-path drift.

### Release assurance

- All 23 required local checks passed on candidate commit
  `2974893c77415686b6bcd1d05b6b1f6738a4f320`, including Python 3.10/3.12,
  Node self-tests, 27/27 adversarial acceptance checks, real Chromium smoke,
  quality triple 3/3, promotion anti-spoof 46/46, actionlint, package checks,
  dependency audit, and no-`.git` archive replay.
- Exact-SHA CI passed across Python 3.10-3.12, Node 18/20/22, Ubuntu, and
  Windows, with real Chromium integration on both operating systems.
- Annotated candidate tag `v3.2.0-rc.3` is bound by tag-object SHA
  `16248f808d134a1498f358a96583c0cae6645a39`; its source archive, checksum,
  extracted-tree replay, and provenance attestation passed before promotion.
- The version-scoped maintainer decision records four explicit external-
  assurance waivers rather than fabricating evidence. Annotated tags, candidate
  ancestry, exact-SHA CI, semantic metadata freeze, archive/checksum, and
  provenance remain non-waivable.

### Included

- Immutable research-plan approvals, portable output-tree concurrency locks,
  canonical reproducibility assertions, signed-ledger and claim-coverage gates.
- Fail-closed report/citation paths, total evaluation validators, hostile-input
  regressions, and artifact-bound promotion checks.
- Browser-first read-only collection with robots/TLS/credential/SSRF defenses
  and deterministic request, response, aggregate, and output resource limits.
- Reproducible package boundary, cross-platform CI, annotated-tag release
  workflow, SHA-256 source artifacts, archive replay, and build provenance.

## [3.2.0-rc.3] - 2026-07-13

Final production-hardening candidate. This candidate closes the approval,
workspace-concurrency, report-signature, evaluator-input, browser resource, and
release-policy gaps found during the final adversarial review of rc.2.

### Added

- **Immutable plan approval:** approvals bind a domain-separated SHA-256 digest
  of research intent; legacy or changed intent fails closed until re-approved.
- **Canonical reproducibility checklist:** versioned `DRC-001` through
  `DRC-037` assertions prevent arbitrary checked text from satisfying the
  release gate and require reasons for every `N/A` item.
- **Portable output locking:** task outputs reject absolute, traversal, ADS,
  device-name, case-alias, and ancestor/descendant collisions across hosts.
- **Browser-wide budgets:** request count, aggregate response bytes, and final
  output bytes are enforced across probe, extract, crawl, navigation, and
  subresources; browser-initiated mutation methods are blocked.
- **Scoped maintainer release decision:** v3.2.0 records an exact, reviewable
  waiver set for unavailable live dogfood, independent review, and
  GitHub-verified tag signatures. It requires hash-bound local verification and
  cannot waive annotated tags, exact-SHA CI, RC ancestry, archive/checksum, or
  provenance gates.

### Fixed

- **Report signature preflight:** `--require-signature` now verifies the ledger,
  sidecar, key, and HMAC before reading or creating any report output, then
  verifies again after ledger validation.
- **Generated-report injection:** generated plan/ledger metadata is redacted,
  control-normalized, escaped, URL-filtered, and bounded without altering the
  authored narrative.
- **Citation style containment:** remote CSL identifiers and cache paths are
  portable and containment-checked; local styles require explicit `.csl` paths.
- **Evaluator totality:** malformed suites, manifests, score files, task IDs,
  artifact paths, non-finite weights, and nested type confusion now return
  structured validation errors instead of tracebacks.
- **Post-RC allowlist traversal:** path normalization no longer strips leading
  traversal characters; backslash, drive, UNC, ADS, empty segment, and Windows
  device-name forms fail closed on every host.

### Verified

- Expanded research-plan, report, evaluation, browser, release-contract, and
  hostile-input self-tests, including real local Chromium integration.
- Release checks cover Python 3.10/3.12 locally, the locked Node toolchain,
  archive replay without `.git`, npm package-boundary verification, dependency
  audit, and exact-SHA CI before tag promotion.

## [3.2.0-rc.2] - 2026-07-13

Second production-hardening candidate. This candidate closes the independently
reproduced crawler, promotion-gate, package/archive, workflow-contract, and
installed-skill readiness gaps found after rc.1 preparation.

### Added

- **Quality eval suite:** held-out research-quality suite
  (`examples/evals/quality-suite.json`, schema 1.0) and
  `scripts/quality_eval.py` (validate, integrity, hostile, fuzz, mutation,
  degraded, artifact-verified `promotion-report`, `promotion-anti-spoof`,
  triple self-test). Does **not** auto-claim PROMOTION_READY without validated
  raw run manifests, integrity hashes, exact candidate SHA, CI evidence, and
  genuine dogfood/forward artifacts.
- **`scripts/content_sanitize.py`:** production visible-text extraction, secret
  redaction, hostile-source processing, and path containment (used by
  `multi_extract` and quality hostile checks).
- **`scripts/lib/browser_ssrf.mjs`:** fail-closed browser destination checks for
  navigation and subresources.
- **Machine-bound route taxonomy:** every intake shape label maps exactly once
  through `templates/route-manifest.json`; the contract rejects missing,
  duplicate, or unknown mappings and semantic drift in protocol/metadata docs.
- **Progressive disclosure:** every routed reference of 100 lines or more has an
  early H2 contents map; the contract enforces navigation on future additions.

### Fixed

- **F-01:** Promotion report is fail-closed and artifact-verified; CLI flags
  (`--infra-green`, `--triple-ok`, `--held-out-live-ok`) never grant
  `PROMOTION_READY_CANDIDATE`. Empty `agent-*` files/dirs, hash/SHA mismatch,
  and null metrics block promotion.
- **F-02:** Citation support no longer treats single token-overlap as entailment;
  negation/contradiction pairs fail closed (`requires_review` / `unsupported` /
  `contradicts`).
- **F-03:** Year extraction captures full years (`(?:19|20)\d{2}`), not century
  prefixes `19`/`20`.
- **F-04:** Hostile checks call production `content_sanitize` (and multi_extract
  HTML text path), not evaluator-local helpers as the sole SUT.
- **F-05 / direct HTTP SSRF:** `api_fetch.mjs` uses connection-bound
  `fetchPublicHttp` (validate DNS → connect to validated IP → peer re-check;
  URL-derived Host + DNS SNI). Rebinding / mixed DNS / peer mismatch covered in
  `ssrf_guards.mjs` self-test.
- **Browser SSRF:** arbitrary browser URLs are fail-closed by default (not
  accepted-risk). Local fixture loopback only via
  the hidden `--allow-loopback-fixture` test hook (browser_smoke / acceptance
  hermetic); production browser guards do not read a loopback environment flag.
- **F-06 (portability):** Ruff clean; seed parser accepts decimal/`0x` hex with
  structured errors; ASCII status tokens (`green->red->green`) for CP1252-safe
  Windows consoles.
- **F-06 (prior transport):** Social/pinned HTTPS transport streams response
  bodies with size-aware `read(n)`; cache generation body lifecycle +
  `body_file` containment remain as in rc.1 hard-fixes.
- **F-07 lineage:** Clean branch `grok/v3.2.0-stable-clean` is rooted at
  `661230a` and does **not** contain synthetic dogfood commits `8f61a7e` /
  `a7d28a0` in ancestry.
- **Package boundary:** npm packaging now uses an explicit runtime allowlist;
  `npm run package:check` rejects untracked files, local MCP/browser artifacts,
  release evidence, credential-like files, Python caches, and omitted tracked
  runtime files before a tarball can pass CI.
- **Promotion fail-closed:** every promotion evaluation now requires the full
  seven-rate vector; held-out and dogfood runs require their kind-specific
  metrics. Sparse scorecards, missing evaluations, malformed findings, and
  unresolved Critical/High/Medium findings block promotion.
- **Robots and crawl truthfulness:** RFC 9309 percent-encoded unreserved octets
  cannot bypass path rules, and configured page/domain/depth ceilings produce
  explicit incomplete summaries instead of `complete=true`.
- **Credential redirects:** Brave, translation, and embedding helpers follow
  redirects manually, retain credentials only on the original origin, reject
  downgrade/cross-origin leakage before the destination request, and cap hops.
- **Long-horizon contract:** all primary instructions now require
  `execute_ready`/`dispatch_ready` before work, distinguish research from
  synthesis terminal tasks, and enforce exact release outputs/claim coverage.
- **Cache publish semantics:** Python cache writes no longer report a successful
  key when atomic publication fails.
- **Deterministic cross-runtime SSRF IPv6 policy:** Node and Python share an
  explicit policy rather than runtime-dependent address tables. IPv4-mapped
  destinations use the embedded IPv4 policy; IPv6 fails closed outside
  `2000::/3`; translation prefixes and non-public GUA ranges (`2001::/23`,
  `2001:db8::/32`, `2002::/16`, `3fff::/20`) are blocked. Hermetic matrices
  cover compressed, expanded, mapped, malformed, and public control forms on
  supported runtimes.
- **Node HTTPS SNI and peer verification:** IP literals omit SNI while DNS
  names preserve it; IPv6 `Host` headers retain brackets and non-default ports.
  Connected peers are canonicalized across IPv4, mapped IPv4, and equivalent
  IPv6 spellings, then checked against the DNS-validated set. Tests emit the
  production `socket` event and execute the real peer gate instead of injecting
  expected error text. Missing or malformed peers fail closed.
- **URL-derived Host binding (Host rebinding blocker):** Node `fetchPublicHttp`
  and Python `_pinned_https_open` strip every caller-provided case-insensitive
  `Host` key and always set exactly one RFC-correct `Host` from the validated
  current URL hop (IPv6 bracketed; non-default ports retained). Hostile
  `Host`/`HOST` values cannot select an internal virtual host after a public
  connect. Hermetic tests cover DNS, IPv4, IPv6±port, and multi-casing overrides.
- **Explicit port fidelity (Python):** port `0` is no longer collapsed to the
  default HTTPS port during pinned connect or redirect-origin comparison; the
  transport and URL-derived `Host` now use the same explicit authority.
- **Python preflight and seam cleanup:** malformed/out-of-range URL ports fail
  before DNS, and rejected/wrong-arity injected transports close returned
  response/connection resources instead of leaking test sockets.
- **Shared production peer validation (Python test seam):** `_assert_connected_peer`
  is the single fail-closed gate on both production connect and
  `_TEST_PINNED_TRANSPORT`. The injectable transport must return
  `(response, connection, peer_ip)`; wrong arity, missing, malformed, private,
  or mismatched peers reject. Canonical IPv6 and IPv4-mapped equivalence is
  covered through the production assertion path.
- **Node delayed-connect coverage:** self-tests exercise
  `socket.connecting === true` then the `connect` event so production
  `assertConnectedPeer` runs on both immediate and delayed connect branches.
- **Strict connected-peer syntax:** peer and DNS-set membership no longer
  repairs whitespace, bracketed authorities, or IPv6 scope identifiers before
  comparison. Malformed/scoped values fail closed; valid public IPv4, IPv6,
  and IPv4-mapped equivalence remains supported.
- **Abnormal HTTP status crash hardening:** nonstandard upstream statuses
  (e.g. `600`) that throw inside Fetch `Response` construction now reject the
  `fetchPublicHttp` promise, destroy/drain the message safely, and never escape
  as an uncaught exception. Null-body 204/205/304 responses explicitly drain
  their underlying message before resolution so sockets do not remain busy,
  abort remains effective, and observable protocol-violating bodies still obey
  byte caps. Because Node deliberately hides bytes after HEAD/204/304, all
  HEAD/204/205/304 connections are retired instead of returned to the pool.
  `HEAD`/`304` representation `Content-Length` metadata no longer triggers a
  false body-cap rejection. Normal status behavior is retained.
- **Abort listener lifecycle:** connection-bound fetches remove per-request
  abort listeners on rejection, null-body completion, body end/error/close,
  cancellation, and resource-limit termination, preventing retained request
  and socket closures when a signal is reused.

### Security

- Node public-destination parsing now rejects IPv4-compatible private IPv6,
  dummy/site-local/SRv6/reserved space, invalid zero-width `::` compression,
  and non-canonical dotted tails with leading-zero octets. DNS pinning, peer
  membership, TLS identity, URL-derived Host binding, and redirect gates remain
  fail-closed.
- Inventory `docs/ssrf-helper-inventory.md` updated: browser arbitrary seeds are
  **Protected (fail-closed)**, not accepted-risk. Translation, embedding, and
  search redirects now have explicit credential isolation; remaining fixed
  archive/academic endpoints retain a documented accepted-risk rationale.
- **L-02:** GitHub Actions pin comments aligned to exact release tags that contain
  the immutable 40-character SHAs (`checkout@v7.0.0`, `setup-python@v6.3.0`,
  `setup-node@v6.4.0`, `upload-artifact@v4.6.2`, `lychee-action@v2.9.0`,
  `attest-build-provenance@v2.4.0`).
- npm package dry-runs are tracked-only and fail closed on local, sensitive, or
  evidence artifacts; explicit package exclusions keep generated Python bytecode
  out even when npm's `files` allowlist overrides broad ignore globs.
- Direct `npm pack` invokes the package gate automatically. A committed path
  fingerprint lets the signed source archive run the same package/self-test
  contract without `.git`, while Git worktrees retain tracked-only validation.
- Manual release dispatch now has `contents: read` only; OIDC and attestation
  permissions exist solely on signed tag-push archive jobs. Python 3.10–3.12 CI
  now runs `content_sanitize.py` and `quality_eval.py` in every unit-matrix row.
- The workspace testing sub-skill metadata now matches its directory name, and
  its release checklist covers package/archive boundaries and generated caches.
- The installation contract now documents and validates Grok Build's personal
  `~/.grok/skills/d-research` discovery path.

## [3.2.0-rc.1] - 2026-07-10

Production-hardening **release candidate** (not Production/Stable). Implements
remaining High/Medium plan items from the post-`570d30b` audit while preserving
v3 compatibility via aliases and deprecation warnings (removed only in v4).

**External / remaining blockers (truthful):**

- Live Tier-1/Tier-2 dogfood vs v3.1.1 under identical runtime/model config is
  not claimed complete in this package; run it before promoting to stable.
- Optional system binaries (pandoc, poppler, tesseract) remain soft runtime
  dependencies; required Ubuntu and Windows integration jobs install them so
  binary-dependent helper paths do not silently skip in release CI.
- Network-dependent live API checks (Crossref/DataCite/OpenAlex) are mocked in
  offline self-tests; live resolution is best-effort.

### Added

- Research plan **schema 2.0**: `schema_version`, `tasks[].phase`
  (`research` | `synthesis`), generic draft `init`, and
  `research_plan.py migrate`.
- Gate semantics: `synthesize_ready` checks research-phase tasks only;
  `release_ready` requires synthesis outputs, real HMAC verify via
  `D_RESEARCH_LEDGER_KEY`, complete reproducibility checklist, and 100% claim
  coverage.
- Evidence ledger optional `record_type` (`claim` | `process` | `blocker`);
  report lint requires `[ref:claim_id]` for every claim row.
- Report renderer preserves `report.draft.md` / section narrative; generated
  Evidence Summary and References use explicit markers only.
- `api_fetch.mjs`: AbortSignal timeouts, `--allow-partial`, metadata sidecars,
  `--cursor-key`, same-origin Link next (with `--allow-next-origin`), credential
  isolation, secret redaction.
- Social snapshot schema **1.1**: expanded verification statuses; Tier B is
  Wayback **lookup-only** by default (`--submit-archive` opt-in).
- Source scoring v2 separates five deterministic axes (`type`, `authority`,
  `freshness`, `traceability`, `independence`) from exactly three mandatory
  human gates (`relevance`, `method_transparency`, `access_quality`), and emits
  `base_total`, `adjusted_total`, `review_status`, and
  `final_reviewed_confidence` (unresolved gates never report final high).
- Eval bench/score schema 2.0 with strict multipart assertions, canonical
  source identities, per-task `run-result.json` validation (task, ledger,
  runtime/config hash, skill commit, timestamps), honest status counts, and a
  deprecated flat-ledger compatibility path that never auto-passes refusals.
- Eval comparison rejects `not_run` by default (`--allow-incomplete` is
  exploratory only), verifies identical runtime/model/tool fingerprints, and
  forces `WEAKER` for any Tier-1 or Tier-2 safety regression regardless of
  newly passing factual tasks.
- Score artifacts include a canonical SHA-256 fingerprint of the complete
  bench; comparison hard-fails when baseline and candidate used different
  questions, assertions, source identities, or bench metadata.
- `scripts/resource_limits.py` + enforcement hooks (HTTP/file/Excel/PDF/OCR/
  subprocess/table/Wayback/social); violations return structured incomplete
  blockers (exit 3), never silent truncate-as-complete. Every helper exposes
  per-invocation CLI overrides in addition to validated `D_RESEARCH_*` limits.
- `scripts/browser_smoke.mjs` real local-fixture Chromium smoke;
  `adversarial_acceptance.py` 27-case CI matrix. CI disables the matrix's
  embedded browser case and launches Chromium exactly once per operating system.
- `scripts/check_contract.py` for dynamic version/config/path/count/CLI contract
  checks, including release-note and changelog-link drift.
- CI: Python self-tests on 3.10/3.11/3.12, Node self-tests on 18/20/22, full
  integration on Ubuntu + Windows, immutable Action SHAs, and Dependabot.
- Release workflow requires a matching semantic version, an annotated tag with
  a GitHub-verified signature, then creates a source archive, SHA256 manifest,
  and provenance attestation. Stable promotion additionally requires hashed,
  committed Tier-1/Tier-2 score artifacts, reviewer sign-off, and exact binding
  to both the dogfooded RC-tag commit and the `v3.1.1` baseline-tag commit.
  Stable promotion rejects code changes after that RC; only version/release
  metadata and the versioned evidence directory may differ. Manual dispatch is
  validation-only.
- Citation: Crossref to DataCite DOI fallback; BibTeX escape + year-only
  normalization; parser round-trip self-tests.

### Changed

- `init` creates a generic empty draft (no OAI-PMH example content). The former
  example lives at `examples/fixtures/research-plan-oai-pmh-example.json`.
- TLS verification is on by default for browser helpers; `--ignore-tls-errors`
  is opt-in and recorded as a limitation.
- Wayback/arXiv public endpoints use HTTPS.
- `--no-respect-robots` is accepted only to explain a policy hard-fail.
- Robots handling: 404/410 = no rules; 401/403 = disallow; 429/5xx = stop domain.
- Every top-level example now declares `example_status` as `illustrative` or
  `fixture`; the contract checker rejects missing/unknown status and requires a
  committed fixture path for any future `verified` example.
- Replaced fabricated result counts in the API dataset, systematic-review, and
  large-crawl examples with replayable canonical CSV schemas, artifact-derived
  arithmetic, and explicit no-completeness language; contract checks protect
  their required headers and reject the former unverified claim patterns.
- Contract checks now cap individual reference guides at 1,000 lines and
  require `See also` navigation from guides of 300 lines or more.
- README repository-tree entries are now resolved against the real tree by CI;
  the former upgrade-plan tree entry was corrected to its archived path.
- Added a tested v3.1.1-to-v3.2.0 upgrade guide and committed legacy workspace
  fixture. Migration regression now proves byte-exact backup, lossless task/
  blocker/output/execution preservation, phase inference, approval revocation,
  stale-plan removal, re-render, re-approval, and `execute_ready`.
- Package version `3.2.0-rc.1` / `3.2.0rc1`; `engines.node >= 18`;
  Playwright and its Chromium revision are locked through exact version `1.61.1`.

### Fixed

- Citation export: unique keys, single RIS `TY`, BibTeX escape, year-only `year`.
- Freshness scoring never treats `date_accessed` as publication date.
- Report render no longer overwrites synthesized narrative with placeholders.
- Report paths derived from a plan cannot read or write outside the resolved
  workspace, including lint targets and synthesis inputs.
- Browser crawl checks robots policy before following redirect destinations;
  bounded local acceptance fixtures prove denied destinations receive zero
  requests and cross-origin credentials never leak.
- API response caps and body-read deadlines now cover streaming bodies, with
  redacted structured sidecars for incomplete output.
- Playwright probe/extract/crawl enforce the same bounded response policy;
  resource-limit exits are structured and crawl results remain explicitly
  incomplete. Unknown API CLI arguments are never echoed or retained verbatim.
- Research-plan release checks reject blocked synthesis, empty output
  directories, unreasoned `N/A` checklist items, and citation placeholders;
  compatibility tests cover v1 plans and `.bib`/`.ris` synthesis artifacts.
- Social verification rejects tier/platform conflicts, malformed RFC3339
  timestamps, inconsistent archive-submission states, and non-canonical archive
  hosts before content retrieval.
- Remaining network helpers (Wikidata/SPARQL, citation graph/resolution/export,
  CSL retrieval, remote embeddings/translation, and web search) now use a
  shared conservative timeout/body cap; resource overruns fail closed with
  exit 3, and search/translation error paths redact credential query values.

### Compatibility

- v1 research plans load via compatibility adapter with a deprecation warning
  until v4.
- Ledger 14/19/22-column headers still validate; missing `record_type` defaults
  to `claim`.
- `--paginate` remains a deprecated alias of `--pagination`.
- No new runtime dependencies beyond Playwright + Python stdlib.

## [3.1.1] - 2026-06-01

v3.1.1 is a skill-metadata compatibility patch. It keeps the full D Research
workflow unchanged while making the `SKILL.md` YAML frontmatter safer for
strict parsers that can misread colon-bearing plain scalar descriptions.

### Changed

- `SKILL.md` now expresses the long `description` field as a folded block scalar
  (`>-`) instead of a single plain scalar line. The trigger text and skill body
  are unchanged.
- `README.md` and `README.vi.md` now mention the metadata-hardening patch in the
  v3.x release sequence.
- Package metadata now reports version `3.1.1` in `pyproject.toml`,
  `package.json`, and `package-lock.json`.

### Compatibility

- No workflow behavior changes.
- No trigger text changes.
- No new dependencies.
- No evidence-ledger schema changes.
- No script CLI changes.
- Existing v3.1.0 workspaces, ledgers, reports, eval fixtures, and release tags
  remain valid.

## [3.1.0] - 2026-05-30

v3.1.0 is a release-consistency and documentation-polish release. It keeps the
register/jargon workflow shipped in v3.0.5 and v3.0.6 unchanged while tightening
the public release surface for a ready-to-ship product package.

### Changed

- Standardized release-note artifacts around a concise title followed by a
  `vX.Y.Z Release Notes` subtitle. `docs/release-v3.0.5.md` and
  `docs/release-v3.0.6.md` were updated to match the public release-note style.
- `docs/eval.md` now describes frontier bench 2.2 as 52 tasks across 26 classes,
  matching `examples/evals/frontier-bench.json`, the empty-score fixtures, and
  the self-test output.
- `README.md` and `README.vi.md` now include the v3.0.5, v3.0.6, and v3.1.0
  release sequence so users can understand the register/jargon upgrade path from
  method, to tool and bench, to release polish.
- Package metadata now reports version `3.1.0` in `pyproject.toml`,
  `package.json`, and `package-lock.json`.

### Fixed

- Removed a duplicate `references/register-and-jargon-expansion.md` See also row
  from `references/frontier-search.md`.

### Compatibility

- No runtime behavior changes.
- No new dependencies.
- No evidence-ledger schema changes.
- No script CLI changes.
- Existing v3.0.x workspaces, ledgers, reports, release tags, and eval fixtures
  remain valid.

## [3.0.6] - 2026-05-29

v3.0.6 completes the register/jargon recall work started in v3.0.5 by turning
the cross-source recurrence rule into a runnable tool and adding bench coverage
so the capability is protected against regression. It is purely additive: no
existing behavior, schema, or CLI changes.

### Added

- **`scripts/harvest_terms.py`** — a deterministic, stdlib-only helper that
  implements the "keep only terms recurring across ≥2 independent community
  sources" rule from `references/register-and-jargon-expansion.md`. It reads
  tagged `source<delimiter>term` occurrences, counts distinct sources per
  candidate term, and labels each `confirmed` or `candidate`. It never invents
  vocabulary. Includes a `harvest` subcommand, a `--threshold` flag (default
  `>=2`), JSON/text output, and an offline `self-test`. Wired into the
  `npm run self-test` chain and exposed as `npm run terms:harvest`.
- **`register-jargon-recall` frontier eval class** in
  `examples/evals/frontier-bench.json` with two ground-truth tasks (FB-051,
  FB-052) that probe the bidirectional register ladder and the
  discovery-layer-not-evidence boundary, plus the matching empty-score fixture
  entries in `examples/evals/fixtures/frontier-empty-scores.json`. Frontier
  bench bumps from `2.1` (50 tasks / 25 classes) to `2.2` (52 tasks / 26
  classes) under the additive bench-version policy.
- **Release note artifact** at `docs/release-v3.0.6.md`.

### Changed

- `references/register-and-jargon-expansion.md` now links the new
  `scripts/harvest_terms.py` helper from the filtering rules and See also.
- `scripts/run_dogfood.py` registers `register-jargon-recall` in
  `FRONTIER_CLASSES` so the ≥2-tasks-per-class rule governs it.
- `README.md`, `README.vi.md`, `docs/eval.md`, `docs/eval-upgrade-prompt.md`,
  and `.agents/skills/testing-scripts/SKILL.md` updated for the new bench counts
  (52 tasks / 26 classes / bench 2.2) and the added helper script.
- Package metadata now reports version `3.0.6` in `pyproject.toml`,
  `package.json`, and `package-lock.json`.

### Fixed

- Removed three stale `placeholder for task 2.x` comments in
  `scripts/pdf_extract.py` (the `tables`, `to-ledger`, and `self-test`
  subcommands they annotated were already fully implemented).

### Compatibility

- No new runtime dependencies.
- No evidence-ledger schema changes.
- No script CLI changes to existing scripts.
- Frontier bench `2.2` is additive; `2.1` score artifacts remain comparable on
  the shared task subset.
- Existing v3.0.x workspaces, ledgers, reports, and eval fixtures remain valid.

## [3.0.5] - 2026-05-29

v3.0.5 is a recall-strengthening release. It adds a register- and
jargon-aware discovery layer so an agent can match the vocabulary of the people
who actually hold the evidence — clinical vs. lay, legal vs. street, standards
vs. shop-floor, academic vs. community jargon, emergent slang — without
maintaining any frozen word list. The skill stores a *process for harvesting and
verifying register-matched vocabulary at runtime*, not a dictionary, so it stays
zero-maintenance as slang changes. The new layer is an additive, opt-in
companion: it composes with multilingual, broad, due-diligence, and
creative/cultural research instead of replacing native-language search.

### Added

- **Register & jargon expansion companion** in
  `references/register-and-jargon-expansion.md`: a bidirectional register ladder
  (formal → vernacular to open recall, vernacular → formal to anchor every
  community term to a primary source), a discover → filter → expand → verify
  loop, harvesting and filtering rules, query-expansion patterns, a
  reproducibility log contract, and a guardrail table covering the five main
  failure modes (memory-invented slang, typo/noise/brigading inflation, treating
  community sources as truth, getting stuck in the community basin, and
  English-pivot breaking native-speaker recall).
- **`register_jargon_recall` intake label** in `references/research-intake.md`,
  added as a recall companion (like `multilingual_local` / `vietnamese_local`)
  that activates only when the evidence basin demonstrably uses vernacular,
  subculture, or domain jargon.
- **`templates/register-vocab-log.csv`** — an audit-grade vocabulary log
  (`term`, `language`, `register_level`, `source_basin`, `first_seen_url`,
  `supporting_source_urls`, `independent_source_count`, `status`,
  `rejection_reason`, `used_in_queries`, `resulting_claim_ids`, `notes`) so a
  reviewer can replay which vocabulary was trusted, why, and which claims it
  produced.
- **Release note artifact** at `docs/release-v3.0.5.md`.

### Changed

- `SKILL.md` adds a new decision-tree branch for thin recall / vernacular
  evidence basins and lists register/jargon variants in the Step 4 query fanout.
- `AGENTS.md` core workflow now decomposes register/jargon variants (step 2),
  fans out register variants both ways (step 4), and can enqueue confirmed
  register variants as `alias`-type frontier nodes (step 11a).
- `references/query-patterns.md` (section 9), `references/topic-decomposition.md`
  (section 3), `references/frontier-search.md` (integration + see also), and
  `references/multilingual-research.md` (cross-link companion) now reference the
  register ladder.
- `README.md` and `README.vi.md` document the new companion (capability #26,
  feature matrix, repository layout, template list, and the guide count 44 → 45).
- Package metadata now reports version `3.0.5` in `pyproject.toml`,
  `package.json`, and `package-lock.json`.

### Security

- The new layer explicitly reinforces no-bypass and no-harm behavior: harvested
  vocabulary is a discovery layer only and never evidence; every claim still
  passes `references/source-quality-rubric.md` and the contradiction pass;
  person-related slang inherits the `references/person-aggregation.md` privacy
  boundary; and slurs, harassment vocabulary, and brigading terms are explicitly
  excluded from recall.

### Compatibility

- No new runtime dependencies.
- No evidence-ledger schema changes.
- No script CLI changes.
- Existing v3.0, v3.0.1, v3.0.2, and v3.0.3 workspaces, ledgers, reports, and
  eval fixtures remain valid.

## [3.0.3] - 2026-05-28

v3.0.3 is a classification-strengthening release for teams that prioritize
correct routing, evidence coverage, and auditability over speed. It expands
Step 0 research intake with first-class due diligence, policy/standards, and
creative/cultural research shapes while preserving the open multi-label design:
the new labels compose with market, technical, academic, dataset, multilingual,
high-stakes, and long-horizon workflows instead of replacing them.

### Added

- **Completeness-first research depth** in `references/research-intake.md` for
  audit-grade, risk-heavy, red-flag, due-diligence, and "speed is not important"
  requests. The mode requires source mapping, search logs, evidence ledgers for
  key claims, independent recall expansion, contradiction search, no
  single-basin completion claims, execution gates, and explicit gap/blocker
  notes.
- **`due_diligence_or_investigation` intake label** for company, project,
  vendor, package, claim, provenance, credibility, and red-flag checks, with
  dedicated source basins and red-flag classes.
- **`policy_or_standards_analysis` intake label** for standards, RFCs, policies,
  governance docs, compliance rules, and versioned normative texts, with
  clause-level verification requirements.
- **`creative_or_cultural_research` intake label** for creative works, media,
  culture, trend, reception, archive, and public-discourse research, with a
  domain-specific authority model.
- **Depth-control configuration defaults** under `research.intake` in
  `research.config.example.json`.
- **Release note artifact** at `docs/release-v3.0.3.md`.

### Changed

- `SKILL.md` and `AGENTS.md` now require agents to capture research depth,
  authority model/source basins, and red-flag or contradiction focus during
  intake.
- `README.md` and `README.vi.md` now present v3.0.3 as a production-ready
  classification upgrade and document completeness-first configuration.
- Package metadata now reports version `3.0.3` in `pyproject.toml`,
  `package.json`, and `package-lock.json`.

### Compatibility

- No new runtime dependencies.
- No evidence-ledger schema changes.
- No script CLI changes.
- Existing v3.0, v3.0.1, and v3.0.2 workspaces, ledgers, reports, and eval
  fixtures remain valid.

## [3.0.2] - 2026-05-28

v3.0.2 adds a Step 0 research-intake layer so agents classify the request
before opening sources or choosing a workflow branch. The change is designed to
prevent early route drift: person-related tasks hit privacy boundaries first,
scientific reviews enter academic/systematic workflows, data tasks produce
schemas and coverage notes, and high-stakes or multilingual tasks get the right
source posture from the start.

### Added

- **Research intake controller** in `references/research-intake.md` with a
  multi-label classification card, hard-stop safety layer, shape-label matrix,
  routing priority, output-artifact selection, ambiguity policy, and common
  failure modes.
- **Step 0 routing in `SKILL.md` and `AGENTS.md`** before any branch selection
  or source access.
- **Intake configuration defaults** under `research.intake` in
  `research.config.example.json`.
- **Release note artifact** at `docs/release-v3.0.2.md`.

### Changed

- `SKILL.md` now requires agents to classify research shape, safety posture,
  expected artifact, freshness/geography/language scope, required references,
  and execution gates before source discovery.
- `README.md` and `README.vi.md` now describe the lifecycle as eight pillars
  with `intake` as pillar 0.
- Package metadata now reports version `3.0.2` in `pyproject.toml`,
  `package.json`, and `package-lock.json`.

### Compatibility

- No new runtime dependencies.
- No evidence-ledger schema changes.
- No script CLI changes.
- Existing v3.0 and v3.0.1 workspaces, ledgers, reports, and eval fixtures
  remain valid.

## [3.0.1] - 2026-05-28

v3.0.1 is a focused workflow-hardening release. It promotes the strongest
agent-orchestration patterns from the MiniMax expert backup into the portable
core skill without making D Research narrower, runtime-specific, or
Vietnamese/social-source-first by default.

### Added

- **Portable execution gates** in `references/execution-gates.md`: source map,
  coverage/recall, identity/date/inference, evidence verification, and
  synthesis-readiness gates for non-trivial research tasks.
- **Subagent-optional worker contract** for Source Mapper, Recall Auditor,
  Public Source Hunter, Data Extractor, Evidence Verifier, and Report
  Synthesizer roles. Hosts with subagents can parallelize the checks; hosts
  without subagents can run the same checklists manually.
- **Vietnamese source discovery companion** in
  `references/vietnamese-source-discovery.md`: opt-in guidance for
  diacritic/no-diacritic aliases, Vietnam-local source basins, public social
  source discipline, and date/identity checks.
- **Execution-gate configuration defaults** in
  `research.config.example.json` under `research.executionGates`.
- **Release note artifact** at `docs/release-v3.0.1.md` for downstream
  maintainers preparing GitHub releases or marketplace listings.

### Changed

- `SKILL.md` now routes non-trivial branches through the execution gates before
  synthesis, while preserving fast paths for atomic facts, public social-post
  capture, and safety refusals.
- `AGENTS.md` mirrors the new gate flow and clarifies that subagents are
  accelerators, not required dependencies.
- `README.md` and `README.vi.md` now describe v3.0.1 as a portable
  pre-synthesis quality layer rather than a domain-specific expansion.
- Package metadata now reports version `3.0.1` in `pyproject.toml`,
  `package.json`, and `package-lock.json`.

### Security

- The new gates explicitly reinforce no-bypass behavior: failed coverage,
  recall, or verification gates require better lawful search, lower confidence,
  a blocker report, or a partial-result label, never login/paywall/captcha/rate
  limit evasion.
- Vietnamese/public-source discovery inherits the person-aggregation privacy
  boundary and treats public social/community sources as leads unless identity
  and context are independently supported.

### Compatibility

- No new runtime dependencies.
- No evidence-ledger schema changes.
- No script CLI changes.
- Existing v3.0 workspaces, ledgers, eval fixtures, and reports remain valid.

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

[Unreleased]: https://github.com/d-init-d/d-research-skill/compare/v3.2.1...HEAD
[3.2.1]: https://github.com/d-init-d/d-research-skill/releases/tag/v3.2.1
[3.2.1-rc.2]: https://github.com/d-init-d/d-research-skill/releases/tag/v3.2.1-rc.2
[3.2.1-rc.1]: https://github.com/d-init-d/d-research-skill/releases/tag/v3.2.1-rc.1
[3.2.0]: https://github.com/d-init-d/d-research-skill/releases/tag/v3.2.0
[3.2.0-rc.3]: https://github.com/d-init-d/d-research-skill/releases/tag/v3.2.0-rc.3
[3.2.0-rc.2]: https://github.com/d-init-d/d-research-skill/releases/tag/v3.2.0-rc.2
[3.2.0-rc.1]: https://github.com/d-init-d/d-research-skill/releases/tag/v3.2.0-rc.1
[3.1.1]: https://github.com/d-init-d/d-research-skill/releases/tag/v3.1.1
[3.1.0]: https://github.com/d-init-d/d-research-skill/releases/tag/v3.1.0
[3.0.6]: https://github.com/d-init-d/d-research-skill/releases/tag/v3.0.6
[3.0.5]: https://github.com/d-init-d/d-research-skill/releases/tag/v3.0.5
[3.0.3]: https://github.com/d-init-d/d-research-skill/releases/tag/v3.0.3
[3.0.2]: https://github.com/d-init-d/d-research-skill/releases/tag/v3.0.2
[3.0.1]: https://github.com/d-init-d/d-research-skill/releases/tag/v3.0.1
[3.0.0]: https://github.com/d-init-d/d-research-skill/releases/tag/v3.0.0
[2.1.0]: https://github.com/d-init-d/d-research-skill/releases/tag/v2.1.0
[2.0.0]: https://github.com/d-init-d/d-research-skill/releases/tag/v2.0.0
