# D Research v3.4.2

## v3.4.2 Release Notes

## Evidence you can inspect. Reports you can verify.

D Research 3.4.2 strengthens the connection between a research report and the
source material behind it. This release brings stricter claim verification,
more careful English and Vietnamese source interpretation, and reproducible
full and runtime packages to existing research workflows.

### Highlights

- **Source-bound reporting.** Report claims are checked against the actual
  source snapshot bytes. A matching quote alone no longer establishes support
  when the surrounding source contradicts the claim.
- **More precise English and Vietnamese grounding.** Questions, explicit
  negation, common contractions, quoted passages spanning multiple sentences,
  and corrections to a claim receive separate treatment. Uncertain semantic
  matches return `requires_review` rather than an unsupported success.
- **Stronger report integrity.** Generated blocks, numerical signs, authored
  claims, and evidence references are validated together. Strict command-line
  checks return a failure when their verification contract is not satisfied.
- **Portable verification.** Local fixtures reduce unnecessary network
  dependencies in offline tests; UTF-8 command output is more reliable on
  Windows. Source and runtime archives retain explicit manifests and checksums.
- **Auditable evaluation.** Benchmark tooling records runner identity and
  evidence provenance, with regression coverage for fabricated or incomplete
  results. A configured benchmark is distinguished from a completed run.

### Upgrade guidance

Use `d-research-3.4.2-runtime.tar.gz` for a normal skill installation, or
`d-research-3.4.2-full.tar.gz` for development and audit tooling. Verify the
download against `SHA256SUMS` before replacing your installed copy. Preserve
your research workspaces and configuration outside the skill directory.

Existing research routes, ledger formats, and command names remain available.
Reports that previously passed on ambiguous, questioned, or contradicted
source text may now require review or fail strict validation. Revalidate
active reports and regenerate version-bound receipts when needed; do not
hand-edit evidence hashes to make an old receipt pass.

### Compatibility

| Component | Support |
|---|---|
| Python | 3.10 or newer |
| Node.js | 18 or newer |
| Browser integration | Playwright 1.61.1; browser installation remains separate |
| Evidence ledgers | Existing 14/19/22/23/37-column contracts |
| Distribution | Full/source and runtime profiles |
| Mandatory Python dependencies | No new dependency |

### Validation and assurance

Release verification covers automated regressions, adversarial acceptance,
real Chromium smoke tests, capability compatibility, package extraction,
reproducible builds, and independent Antigravity CLI workflow checks. Signed
tags, CI for the exact release commit, SHA-256 checksums, and source provenance
attestation form the publication checks.

The release is published at the repository owner's direction following the
upgrade review. Independent human pull-request approval and an uncontaminated
live baseline-versus-candidate benchmark are not claimed. Automated and
synthetic checks do not establish coverage across every host or the factual
correctness of every research conclusion. Ambiguous claims still need review.

The existing **CC BY-NC 4.0** license is unchanged.

**Full changelog:** [v3.4.1...v3.4.2](https://github.com/d-init-d/d-research-skill/compare/v3.4.1...v3.4.2)
