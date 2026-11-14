# D Research v3.7.0

## v3.7.0 Release Notes

## Flexible browser-first execution. Exhaustive federated recall. Bilingual dual-track rigor.

**D Research 3.7.0** is a major capability upgrade focused on maximizing research completeness, bridging host-native IDE/agent browsers into the cryptographically verifiable DRS-1.1 evidence pipeline, equalizing first-round parallelism across documentary and social/community tracks, and hardening bilingual English/Vietnamese cross-branch reconciliation.

This official stable release is promoted from the signed `v3.7.0-rc.1` candidate tag under the repository owner's scoped promotion contract (`release-evidence/v3.7.0/`), preserving deterministic `full` and `runtime` distribution profiles, immutable Git source archival, and GitHub build provenance attestation.

---

### What's New in v3.7.0

#### 1. Flexible 3-Tier Browser-First Routing & DRS-1.1 Host-Browser Evidence Bridge
Agents running inside modern IDE or desktop runtimes often already have access to an integrated browser (IDE browser subagent, Chrome DevTools MCP, CUA driver, or an active CDP debugging session). Previously, non-Playwright browser captures lacked a first-class ingestion path into the DRS-1.1 activity and capture ledgers.

- **Flexible Tier-1 Adapter Priority (`SKILL.md`, `adapters/generic-browser.md`, `references/tool-adapter-policy.md`):** Prioritizes whichever live interactive browser works cleanly in the environment—either Tier 1A (Host/Integrated Browser) or Tier 1B (Local Playwright standalone/`cdp`/`auto`)—before falling back to Tier 2 (`adapters/fetch-only.md`) and Tier 3 (`adapters/web-search-only.md`).
- **Host-Integrated Browser Evidence CLI (`scripts/execution_evidence.py`):** Added `record_browser_evidence()`, `summarize_browser_provenance()`, and CLI subcommands `record` / `verify` (with `--workspace`, `--url`, `--final-url`, `--branch`, `--question-id`, `--engine`, `--mode`, `--action-type`, `--text-file`, `--raw-text-out`, `--screenshot`, `--dom-locator`, `--observed-state-ref`, `--activity-log`, `--capture-records`, `--update-coverage`) so captures from `host-subagent`, `chrome-devtools-mcp`, `cua-driver`, and `cdp-session` receive SHA-256 content hashes and DRS-1.1 provenance validation identical to Playwright runs.
- **Unified Playwright DRS-1.1 Telemetry (`scripts/lib/browser_connector.mjs`, `scripts/playwright_extract.mjs`, `scripts/playwright_crawl.mjs`, `scripts/browser_interaction.mjs`):** Added `appendDrsBrowserEvidence()` and native `--activity-log`, `--capture-records`, `--raw-text-out`, `--branch`, `--question-id`, and `--source-id` options across extraction, crawl, and interaction scripts.

#### 2. Completeness-First Federated Search (`scripts/web_search.mjs`)
- **Multi-Provider `--federated` Sweep:** Queries across all configured search providers in the chain rather than stopping after the first non-empty engine response, canonicalizes URLs with `canonicalizeResultUrl()` to deduplicate overlapping hits, and annotates each result with `source_engine`.
- **Empty-Result Fallback Continuation:** Exhausted providers returning `no_results` cleanly continue to subsequent fallback providers in non-federated mode instead of prematurely terminating discovery.

#### 3. Capture-Driven Iterative Term Harvesting (`scripts/harvest_terms.py`)
- **Direct Capture Corpus Mining:** Added `harvest_from_captures()` and `--from-captures` / `--workspace` flags to extract cross-source recurring acronyms, hyphenated technical compounds, and bilingual EN/VI bigrams directly from DRS-1.1 `capture-records` raw text files (`_extract_capture_terms()`), closing the loop between initial captures and second-round search expansion.

#### 4. Equalized Round-1 Dual-Track Authority & Partial-Stop Gap Preservation (`scripts/research_controller.py`, `scripts/research_plan.py`)
- **Anti-Starvation Round-1 Equilibrium:** Equalized default authority priority (`3.0`) for both `documentary` and `social` branches in `ResearchController` so community, practitioner, and social evidence tracks are never crowded out during Round-1 frontier scheduling.
- **Honest Diminishing-Returns Termination:** When `no_progress_limit_reached` triggers with open pending or blocked frontier gaps, `ResearchController` preserves unresolved `coverage_gaps` and transitions branch state to `partial` rather than marking incomplete coverage as `completed`.
- **First-Class Dual-Track CLI Scaffolding (`scripts/research_plan.py`):** Added `init --dual-track --question ... --route ... --execution-mode ... --budget-profile ...` (which initializes balanced dual-track plans alongside `research-coverage.json`) and `add-task --branch --sub-question-id`.

#### 5. Bilingual (EN/VI) Cross-Branch Reconciliation (`scripts/reconciliation.py`)
- **Expanded Bilingual Lexicon & Taxonomy:** Enriched `CrossBranchReconciler` with bilingual English/Vietnamese `SCOPE_KEYWORDS` (`web_browser`, `cli_api`, `enterprise`, `methodology`, `version_diff`, `config_diff`, `os_diff`), `CORRECTION_KEYWORDS`, `TEMPORAL_SUPERSESSION_KEYWORDS`, `EMPIRICAL_MARKERS`, and `SPECULATION_MARKERS`.
- **Timestamp & Evidence-Tier Adjudication:** Added `_parse_ts()` timestamp comparison and `temporal_evolution` resolution when newer changelogs or authoritative updates supersede older claims, plus clearer separation between empirical benchmarks/audits and unverified speculation.

---

### Upgrade Guidance

- **Standard installation:** Download `d-research-3.7.0-runtime.tar.gz` for lightweight runtime deployment (or consume directly via **Aleph Skill v2.6.0** where it is byte-locked under `components/d-research/`).
- **Development & validation:** Download `d-research-3.7.0-full.tar.gz` or `d-research-skill-v3.7.0.tar.gz` (immutable tagged Git source archive).
- **Backward compatibility:** Existing 14/19/22/23/37-column CSV evidence ledgers, schema 2.0 research plans, and all 28 research routes remain fully supported without breaking migrations. No mandatory Python dependencies were added.

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

gh attestation verify d-research-skill-v3.7.0.tar.gz \
  --repo d-init-d/d-research-skill \
  --signer-workflow d-init-d/d-research-skill/.github/workflows/release-attest.yml
```

From the extracted `full` or source directory, verify local helpers with:

```sh
npm ci --ignore-scripts --no-audit --no-fund
npm run self-test
D_RESEARCH_SKIP_BROWSER_SMOKE=1 npm run acceptance
```

**Full changelog:** [v3.6.0...v3.7.0](https://github.com/d-init-d/d-research-skill/compare/v3.6.0...v3.7.0)
