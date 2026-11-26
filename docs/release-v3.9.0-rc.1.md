# D Research v3.9.0-rc.1

## v3.9.0-rc.1 Release Notes

This release-candidate snapshot prepares **D Research 3.9.0** for evaluation and downstream bundling in **Aleph Skill v2.11.0**.

### Highlights in this candidate

- **Source Grounding Hardening (`scripts/source_grounding.py`)**: Expanded English contraction negations (`didn't`, `cannot`, `isn't`, `won't`, etc., plus curly `’`) across both `_has_negator()` and `_polarity()`, canonicalized `%` / `percent` / `phần trăm` numeric matching, fixed multi-sentence verbatim support across consecutive sentence windows, and hardened `audit_ledger_grounding()` for `quote_or_anchor` + attribution prose.
- **Publisher-Domain Lineage & Metadata Evidence (`scripts/lineage_tracker.py`)**: Added canonical publisher-domain clustering (normalizing `www.` while keeping multi-tenant social/forum speakers separate) and synthesized verified `evidence_records` from hash-bound intact ledger rows so official/primary rows assess cleanly as `supported` / `main_findings`.
- **Vietnamese & Multilingual Harvesting (`scripts/harvest_terms.py`)**: Added `NFC` normalization in direct `harvest()`, expanded `_VI_SHORT_SYLLABLES` (`ý`, `ổ`, `ủ`, `ở`, `á`, `ê`, `u`, `í`, `ố`, `ế`, `ồ`), added `"mà"` to `_CAPTURE_STOPWORDS`, and enabled 2-letter uppercase acronyms (`AI`, `VN`, `US`, `EU`, etc.).
- **Ledger & Policy Interop (`scripts/evidence_ledger.py`, `scripts/investigation_policy.py`)**: Accepted `"intact"` <-> `"live_intact"` across integrity validation and scoped 37-column social `notes` syntax checks to social/community rows.
- **Same-Branch Reconciliation & CLI (`scripts/reconciliation.py`)**: Enabled same-branch contradiction detection within shared `sub_question` buckets and defaulted `reconciliation.py --ledger ...` cleanly to `reconcile`.
- **Node CLI & Missing-Browser UX**: Added `--help`/`-h` to `web_search.mjs` and `api_fetch.mjs`, defaulted `User-Agent` to `packageUserAgent('api-fetch')`, normalized raw hostnames in `isPrivateIpOrBlockedHost()`, added positional/alias URL handling to Playwright helpers, and emitted structured `browser_launch_failure` JSON blockers (plus `activity-log.json` persistence in `browser_interaction.mjs`).

See [target stable release notes](release-v3.9.0.md) for full compatibility and verification guidance. This candidate tag is not itself the stable release.
