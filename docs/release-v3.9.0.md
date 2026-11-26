# D Research v3.9.0

## v3.9.0 Release Notes

## High-precision claim grounding. Publisher-domain lineage. Resilient CLI & browser diagnostics.

**D Research 3.9.0** hardens the end-to-end evidentiary pipeline across source grounding, publisher-domain lineage inference, bilingual Vietnamese/English terminology extraction, 37-column ledger/policy interoperability, same-branch conflict reconciliation, and structured browser/HTTP diagnostics — ready for standalone production agent workflows and byte-locked integration inside **Aleph Skill v2.11.0**.

This official stable release is promoted from the signed `v3.9.0-rc.1` candidate tag under the repository owner's scoped promotion contract (`release-evidence/v3.9.0/`), preserving deterministic `full` and `runtime` distribution profiles, immutable Git source archival, and GitHub SLSA build provenance attestation.

---

### What's New in v3.9.0

#### 1. Contraction-Aware, Multi-Sentence & Percent-Normalized Grounding (`scripts/source_grounding.py`)
- **Expanded Contraction Negation Detection:** `_expand_negation_contractions()` normalizes straight and typographic apostrophes (`'` / `’` / `‘`) across 17 English negated verb contractions (`didn't`, `don't`, `doesn't`, `can't`, `cannot`, `couldn't`, `won't`, `wouldn't`, `isn't`, `aren't`, `wasn't`, `weren't`, `hasn't`, `haven't`, `hadn't`, `shouldn't`, `mustn't`) in both `_polarity()` and `_has_negator()`, ensuring polarity-inverted claims (`"didn't raise"` vs `"raised"`, `"cannot approve"` vs `"approves"`) deterministically classify as `contradicted`.
- **Canonical Percentage Equivalence:** `_numeric_tokens()` canonicalizes `%`, `percent`, and Vietnamese `phần trăm` representations (`4.9%`, `4.9 percent`, `4.9 phần trăm` → `4.9%`), eliminating false numeric-mismatch contradictions across mixed prose styles.
- **Multi-Sentence Verbatim Windows & Anchor Isolation:** `assess_source_context()` and `assess_paraphrase_grounding()` evaluate sliding 2–3 sentence windows and full normalized source text before single-sentence numeric fallback so multi-sentence verbatim excerpts return `literal_supported`. `audit_ledger_grounding()` isolates `quote_or_anchor` verification so non-negated attribution framing in `evidence` never downgrades grounded claims.

#### 2. Publisher-Domain Lineage Clustering & Verified Evidence Synthesis (`scripts/lineage_tracker.py`)
- **Canonical Publisher Clustering (`_canonical_publisher_key()`):** `LineageTracker.analyze_ledger()` normalizes `www.` host prefixes and clusters syndicated or multi-article citations from the same non-multi-tenant publisher domain into unified origin clusters while keeping distinct speakers and accounts on multi-tenant social/community platforms separate.
- **Metadata-to-Evidence Synthesis:** Validated ledger rows carrying `sha256:...` content hashes and intact capture state (`intact`, `live_intact`, or `archive_snapshot`) synthesize structured `evidence_records` and pass accurate `independent_origins` and `corroborating_doc_url` inputs into `UnifiedClaimAssessor.assess_claim()`, preserving `supported` / `main_findings` status on verified official and primary documentary claims.

#### 3. Unicode-Consistent Vietnamese & Technical Term Harvesting (`scripts/harvest_terms.py`)
- **Direct `harvest()` Unicode `NFC` Normalization:** Normalizes both source identifiers and candidate terms to `NFC` in direct `harvest()` mode (matching `--from-captures`), preventing precomposed (`NFC`) and decomposed (`NFD`) Vietnamese diacritics (`tỷ giá`) from fragmenting across sources.
- **Expanded Vietnamese Syllable & Acronym Coverage:** Broadens `_VI_SHORT_SYLLABLES` (`ý`, `ổ`, `ủ`, `ở`, `á`, `ê`, `u`, `í`, `ố`, `ế`, `ồ`) to retain compounds such as `ý thức`, `ổ cứng`, and `ủ bệnh`; adds `"mà"` and high-frequency particles to `_CAPTURE_STOPWORDS`; and preserves 2-letter uppercase domain/country acronyms (`AI`, `VN`, `US`, `EU`, `UN`, `IT`, `IP`, `ID`, `OS`, `UI`, `UX`, `ML`, `QA`, `QC`).

#### 4. Cross-Script Integrity & 37-Column Documentary Parity (`scripts/evidence_ledger.py`, `scripts/investigation_policy.py`)
- **Unified Snapshot/Integrity Vocabulary:** Harmonizes `"intact"` and `"live_intact"` across `evidence_ledger.py`, `investigation_policy.py` (`assess-source --integrity`), and `lineage_tracker.py` so multi-stage audit pipelines interoperate without vocabulary friction.
- **Scoped Social Statement Enforcement (`_is_social_row()`):** Restricts 37-column social `notes` syntax enforcement (`claim_kind=statement_made` / `corroborated_by=`) to genuine social/community rows, allowing official, primary, academic, and dataset documentary rows to populate `speaker_identity` cleanly.

#### 5. Intra-Branch Conflict Detection & Ergonomic Reconciliation CLI (`scripts/reconciliation.py`)
- **Same-Branch Discrepancy Detection (`_has_same_branch_conflict_signal()`):** `reconcile_from_ledger()` now evaluates same-branch claim pairs sharing a `sub_question` (for example, two official sources reporting conflicting figures or polarity) even when `contradiction` was initialized to `"none"`.
- **Direct Flag Invocation:** `scripts/reconciliation.py --ledger <csv>` (as well as `--fixtures` and `--documentary`) automatically defaults to the `reconcile` subcommand while maintaining full backward compatibility with explicit `reconciliation.py reconcile ...` calls.

#### 6. Resilient Node Helpers, SSRF Normalization & Missing-Browser UX
- **First-Class `--help` & Default `User-Agent` (`scripts/web_search.mjs`, `scripts/api_fetch.mjs`):** Both Node network entrypoints support `-h` / `--help` (`exit 0`), and `api_fetch.mjs` supplies `packageUserAgent('api-fetch')` whenever callers omit a custom `User-Agent` header (preventing `HTTP 403` rejections on strict public APIs such as Wikimedia REST).
- **Raw Host SSRF Normalization (`scripts/lib/ssrf_guards.mjs`):** Exports `isPrivateIpOrBlockedHost()` with WHATWG `URL` host canonicalization so direct helper calls immediately reject octal and decimal loopback/private encodings (`0177.0.0.1`, `2130706433`).
- **Consistent Playwright CLI & Structured Blocker Output (`scripts/playwright_*.mjs`, `scripts/browser_interaction.mjs`):** Accepts positional `<url>` / `<seed-url>` arguments and `--url` aliases across probe/extract/crawl helpers, and emits structured JSON blocker payloads (`status: "blocked"`, `blockers: ["browser_launch_failure"]`, `limitations: ["missing_browser_capability"]`) plus schema-valid `activity-log.json` entries when a headless Chromium binary is unavailable on the host.

---

### Upgrade Guidance

- **Standard runtime deployment:** Download `d-research-3.9.0-runtime.tar.gz` (`249` runtime files) for standalone agent execution, or install **Aleph Skill v2.11.0** where D Research `3.9.0` is vendored and byte-locked at `aleph-component://d-research`.
- **Development, benchmarks & release verification:** Download `d-research-3.9.0-full.tar.gz` (`849` files) or `d-research-skill-v3.9.0.tar.gz` (immutable tagged Git source archive).
- **Zero-migration backward compatibility:** Existing 14/19/22/23/37-column CSV evidence ledgers, HMAC-SHA256 `.hmac` sidecars, schema `2.0` research plans, and all `28` research routes continue to work without schema changes.

| Component | Requirement / Support |
|---|---|
| Python | 3.10 or newer (stdlib-only core scripts) |
| Node.js | 18 or newer |
| Browser Automation | Host-integrated browser (Tier 1A) or Playwright `1.61.1` (Tier 1B) |
| Evidence Ledger | 14 / 19 / 22 / 23 / 37-column contracts with HMAC-SHA256 signing |
| License | `CC-BY-NC-4.0` (unchanged) |

---

### Release Assets & Verification

Download the release archives and `SHA256SUMS` into a single directory and verify cryptographic checksums and GitHub SLSA provenance attestation before extraction:

```sh
sha256sum -c SHA256SUMS

gh attestation verify d-research-skill-v3.9.0.tar.gz \
  --repo d-init-d/d-research-skill \
  --signer-workflow d-init-d/d-research-skill/.github/workflows/release-attest.yml
```

From the extracted `full` or source directory, verify all local self-tests and adversarial gates:

```sh
npm ci --ignore-scripts --no-audit --no-fund
npm run self-test
D_RESEARCH_SKIP_BROWSER_SMOKE=1 npm run acceptance
```

**Full changelog:** [v3.8.0...v3.9.0](https://github.com/d-init-d/d-research-skill/compare/v3.8.0...v3.9.0)
