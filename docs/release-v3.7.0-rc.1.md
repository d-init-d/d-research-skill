# D Research v3.7.0-rc.1

## v3.7.0-rc.1 Release Notes

This signed release-candidate snapshot prepares **D Research 3.7.0** for stable promotion and freezes the future stable release notes and package manifest before promotion.

### Highlights in this candidate

- **3-Tier Browser-First Architecture & DRS-1.1 Host-Browser Evidence Bridge**: Accept host/integrated browsers (`host-subagent`, `chrome-devtools-mcp`, `cua-driver`, `cdp-session`) and standalone/CDP Playwright sessions interchangeably as Tier-1 browser execution, backed by `scripts/execution_evidence.py` (`record` / `verify`, `record_browser_evidence()`, `summarize_browser_provenance()`) and `appendDrsBrowserEvidence()` in `scripts/lib/browser_connector.mjs`.
- **Completeness-First Federated Search**: Added `--federated` multi-provider query execution and `canonicalizeResultUrl()` URL deduplication in `scripts/web_search.mjs`, plus automatic fallback continuation on `no_results` empty responses.
- **Capture-Driven Term Harvesting**: Added `harvest_from_captures()` and `--from-captures` / `--workspace` CLI flags in `scripts/harvest_terms.py` to mine recurring acronyms, hyphenated compounds, and bilingual bigrams directly from DRS-1.1 captures.
- **Equalized Round-1 Dual-Track Authority & Gap Preservation**: Equalized initial `documentary` and `social` branch authority priority (`3.0`) and preserved open `coverage_gaps` (`partial` terminal state) on diminishing-returns stops in `scripts/research_controller.py`; added `--dual-track` initialization and `--branch` / `--sub-question-id` task registration in `scripts/research_plan.py`.
- **Bilingual (EN/VI) Cross-Branch Reconciliation**: Expanded `CrossBranchReconciler` in `scripts/reconciliation.py` with English/Vietnamese correction, temporal supersession (`temporal_evolution`), platform/methodology scope divergence, and empirical-vs-speculative markers.

See [stable release notes](release-v3.7.0.md) for full technical architecture, compatibility, upgrade instructions, and SHA-256 verification commands. This candidate tag is not itself the stable release.
