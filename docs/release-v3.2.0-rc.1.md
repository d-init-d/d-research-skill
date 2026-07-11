# D Research v3.2.0-rc.1

## v3.2.0-rc.1 Release Notes

Production-hardening **release candidate** (Development Status: Beta — not
Production/Stable) implementing remaining High/Medium plan items:

- Research-plan schema 2.0 + gate semantics
- Report/ledger claim coverage
- API/robots/credential isolation
- Social snapshot 1.1 (Wayback lookup-only by default)
- Scoring v2: `automated_band` / `review_status` / `final_reviewed_confidence`
- Eval schema 2.0: canonical per-task run manifests, multipart assertions,
  source recall, assertion accuracy, safety result, and honest run-status counts
- Citation Crossref to DataCite fallback, BibTeX escape, year normalization
- Resource limits (HTTP/Excel/PDF/OCR/subprocess/table/Wayback/social)
  with environment and per-command CLI overrides; violations fail closed with
  structured incomplete metadata
- Workspace-contained report paths plus redirect-aware robots and
  cross-origin credential isolation acceptance tests
- CI: Python self-tests on 3.10–3.12, Node self-tests on 18/20/22, full Ubuntu
  and Windows integration, and one local-fixture Chromium smoke per OS
- Supply chain: exact Playwright `1.61.1` + locked Chromium revision, immutable
  Action SHAs, npm/Actions Dependabot, and signed-tag release validation
- Release artifacts: source archive + verified SHA256 manifest + provenance;
  manual workflow dispatch validates only and cannot attest an untagged build
- Stable-only promotion evidence: committed Tier-1/Tier-2 baseline/candidate
  scores with SHA256 bindings, one identical runtime signature, reviewer
  sign-off, and exact commit binding to the dogfooded RC tag and `v3.1.1` tag
- Safety language: captcha/stealth are **never allowed**
- Tested v3.1.1 workspace migration guide and committed upgrade fixture

## Remaining external blockers (truthful)

1. **Live dogfood** Tier 1 + Tier 2 vs v3.1.1 under identical runtime/model/tool
   configuration is **not** completed in this package artifact. Do not claim
   stable readiness until `not_run=0` and score artifacts are recorded.
2. Optional system binaries (pandoc / poppler / tesseract) remain soft runtime
   dependencies; the required Ubuntu and Windows integration jobs install them
   so their live helper paths cannot silently skip in release CI.
3. Live third-party API resolution (Crossref/DataCite/OpenAlex) is mocked offline;
   production use is best-effort rate-limited HTTP.

## What this RC does **not** claim

- Does **not** claim every historical High/Medium finding is closed in the field
  without live dogfood evidence.
- Does **not** tag or publish a stable `v3.2.0`.
- Does **not** enable captcha solving or stealth evasion under any config.

## Release gate

An RC or stable archive is produced only for a `vX.Y.Z` or `vX.Y.Z-rc.N` tag
that exactly matches `package.json` and `pyproject.toml`. The tag must be an
annotated tag whose signature GitHub reports as verified. The repository
contract checker also requires matching changelog headings/links, release-note
paths, version classifiers, repository counts, core paths, and canonical CLI
flags before archive or attestation steps can run. For a stable tag, it also
resolves both tag commits and rejects promotion evidence produced from any
different candidate or baseline commit. It also verifies that the RC commit is
an ancestor of stable and rejects post-RC changes outside release metadata and
the versioned evidence directory.

### Stable promotion runbook

1. Commit the RC candidate. Run Tier 1 and Tier 2 once at the `v3.1.1` tag and
   once at that exact candidate commit, using one identical agent/model/tool
   configuration. Every task must have a schema-2.0 `run-result.json` and
   `not_run` must be zero.
2. Generate these four score files with `scripts/run_dogfood.py score-all` and
   place them under `release-evidence/v3.2.0/`: Tier-1 baseline, Tier-1
   candidate, Tier-2 baseline, and Tier-2 candidate. Do not edit score output
   by hand.
3. Run `scripts/run_dogfood.py compare` for both tiers. Tier 1 must not be
   `WEAKER`; Tier 2 must have no safety regression and must not reduce the
   passed-task count.
4. Create `release-evidence/v3.2.0/promotion.json` with this contract:

```json
{
  "schema_version": "1.0",
  "release_version": "3.2.0",
  "baseline_version": "3.1.1",
  "candidate_version": "3.2.0-rc.1",
  "baseline_skill_commit": "40-character lowercase commit SHA for v3.1.1",
  "candidate_skill_commit": "40-character lowercase candidate commit SHA",
  "generated_at": "timezone-aware RFC3339 timestamp",
  "tiers": {
    "tier1": {
      "baseline_scores": {"path": "repo-relative path", "sha256": "sha256:64-lowercase-hex"},
      "candidate_scores": {"path": "repo-relative path", "sha256": "sha256:64-lowercase-hex"}
    },
    "tier2": {
      "baseline_scores": {"path": "repo-relative path", "sha256": "sha256:64-lowercase-hex"},
      "candidate_scores": {"path": "repo-relative path", "sha256": "sha256:64-lowercase-hex"}
    }
  },
  "reviewer_signoff_path": "release-evidence/v3.2.0/reviewer-signoff.json"
}
```

5. After an independent reviewer checks the comparisons, create the sign-off.
   Its `promotion_manifest_sha256` must be the SHA256 of the final, unchanged
   `promotion.json`:

```json
{
  "schema_version": "1.0",
  "release_version": "3.2.0",
  "decision": "approved",
  "reviewer": {"name": "reviewer name", "role": "reviewer role"},
  "reviewed_at": "timezone-aware RFC3339 timestamp after generated_at",
  "promotion_manifest_sha256": "sha256:64-lowercase-hex"
}
```

6. Commit the evidence and stable metadata, then run the contract against the
   same commits that the release workflow will resolve:

```bash
python scripts/check_contract.py \
  --release-tag v3.2.0 \
  --candidate-commit "$(git rev-parse 'refs/tags/v3.2.0-rc.1^{commit}')" \
  --baseline-commit "$(git rev-parse 'refs/tags/v3.1.1^{commit}')"
```

The score hashes, score-level `skill_commit` values, promotion commits,
reviewer hash, and the baseline/RC tag commits must all agree. Any mismatch
fails closed. If dogfood discovers a code defect, publish and dogfood a new RC;
do not patch code only in the stable promotion commit.

Create the RC tag locally with a configured signing key:

```bash
git tag -s v3.2.0-rc.1 -m "D Research v3.2.0-rc.1"
git push origin v3.2.0-rc.1
```

Do not use a lightweight tag. A tag whose signature GitHub cannot verify is
rejected before any release artifact is built.

See `CHANGELOG.md` for Added / Changed / Fixed / Compatibility.
