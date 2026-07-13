# D Research v3.2.0-rc.3

## v3.2.0-rc.3 Release Notes

v3.2.0-rc.3 is the final production-hardening candidate for the v3.2.0
release line. It keeps the schema-2.0 research workflow introduced by the
earlier candidates and closes the remaining fail-open, portability,
concurrency, and release-governance findings from the final adversarial audit.

The candidate remains prerelease metadata (`Development Status :: 4 - Beta`).
Stable promotion changes only release metadata and versioned release evidence;
the executable skill, scripts, dependencies, workflow contract, and package
path manifest are frozen at this candidate.

## Security and integrity changes

- Plan approval now binds immutable research intent with a deterministic,
  domain-separated SHA-256 fingerprint. Any intent change revokes execution
  authorization until a new approval is recorded.
- Workspace task outputs use portable repository-relative validation and
  case-insensitive tree locking. Exact aliases and ancestor/descendant overlaps
  cannot run concurrently.
- The reproducibility checklist has a canonical version marker and 37 stable
  assertion IDs. Duplicate, missing, unknown, un-IDed, unchecked, or unexplained
  `N/A` assertions fail the gate.
- Required report signatures are verified before any narrative or output is
  opened, and are reverified after ledger validation. Missing sidecars, missing
  keys, and invalid HMACs fail without creating output.
- Generated report metadata is secret-redacted, control-normalized, escaped,
  URL-filtered, and size-bounded. Authored narrative remains byte-for-byte under
  the user's control.
- CSL cache identifiers, eval fixtures, run artifacts, and release-evidence
  paths reject traversal, absolute, drive, UNC, ADS, device-name, trailing-dot,
  case-alias, and symlink-escape forms.
- Browser helpers enforce read-only page requests plus request-count,
  per-response, aggregate-response, and final-output budgets. Resource limits
  remain structured blockers rather than completeness claims.

## Evaluation hardening

- Research-plan self-tests cover approval drift, checklist spoofing, portable
  paths, and output-tree collision scheduling.
- Dogfood and held-out evaluators validate every nested input before use,
  reject non-finite or malformed weights, and keep invalid inputs on structured
  error paths instead of Python tracebacks.
- Promotion evaluation remains artifact-bound and fail-closed. The local
  maintainer decision for v3.2.0 does not synthesize live dogfood scores or an
  independent review that did not occur.

## Release policy for v3.2.0

The repository owner explicitly authorized promotion based on the complete
local release suite plus exact-SHA CI. The frozen RC contract permits exactly
these four waivers:

1. GitHub-verified signature for the candidate tag.
2. GitHub-verified signature for the stable tag.
3. An independent pull-request reviewer.
4. Live Tier-1/Tier-2 dogfood against v3.1.1.

The override is scoped only to v3.2.0 and must be committed after this RC as a
strict JSON record that binds the candidate commit, annotated tag object, and
SHA-256 of the local verification record. It cannot waive:

- annotated candidate and stable tags;
- the exact candidate tag-object binding;
- candidate ancestry of the stable release;
- successful full CI for the exact tagged commit;
- source-archive construction and replay without `.git`;
- SHA-256 manifest verification; or
- GitHub build-provenance attestation.

This policy is transparent risk acceptance, not a claim that the waived work
was performed. Future release lines default to the full live-evidence path
unless they freeze a new version-scoped decision before their candidate tag.

## Required verification

Run from a clean checkout of the exact candidate commit:

```powershell
npm ci --ignore-scripts --no-audit --no-fund
npm run self-test
npm run acceptance
npm run browser:smoke
npm run package:check
npm pack --dry-run --json
ruff check scripts/
python -m compileall -q scripts examples
python scripts/check_node_syntax.py
python scripts/check_internal_refs.py
python scripts/check_internal_refs.py --decision-tree
python scripts/check_contract.py
python scripts/check_contract.py self-test
python scripts/bench_harness_check.py check-all --strict
python scripts/quality_eval.py triple
python scripts/quality_eval.py promotion-anti-spoof
go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.7
git diff --check
npm audit --omit=dev --audit-level=moderate
```

The Python self-test suite must also pass with Python 3.10 and 3.12. The CI
matrix remains authoritative for Python 3.10-3.12, Node 18/20/22, Ubuntu, and
Windows.

## Promotion procedure

1. Commit and push the complete candidate tree.
2. Require the full CI workflow to pass for that exact commit.
3. Create and push the annotated `v3.2.0-rc.3` tag.
4. Require the release archive workflow, archive replay, checksum, and
   provenance attestation to pass.
5. Commit only stable metadata and versioned `release-evidence/v3.2.0/` files.
6. Validate post-RC paths and semantic metadata against the RC tag.
7. Require full CI for the exact stable commit.
8. Create and push the annotated `v3.2.0` tag, then publish the verified assets
   and professional release notes.
