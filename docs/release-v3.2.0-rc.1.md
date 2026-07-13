# D Research v3.2.0-rc.1

## v3.2.0-rc.1 Release Notes

Production-hardening **release candidate** (Development Status: Beta — not
Production/Stable) implementing remaining High/Medium plan items:

- Research-plan schema 2.0 + gate semantics
- Report/ledger claim coverage
- API/robots/credential isolation
- Social snapshot 1.1 (Wayback lookup-only by default)
- Scoring v2: `automated_band` / `review_status` / `final_reviewed_confidence`
- Eval run-result/score schema 2.1: canonical per-task manifests, hashed raw
  prompt/output/ledger provenance, unique run/session IDs, multipart assertions,
  source recall, assertion accuracy, safety result, and honest run-status counts
- Promotion run-manifest schema 1.1: exact candidate SHA, unique run/session
  IDs, strict finite JSON metrics, hashed consumed artifacts, live-provenance
  declaration, blind-label checks, and candidate-bound deterministic logs
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

## Post-candidate transport/cache hard-fixes (this branch)

Independent verification closed four regressions before dogfood:

- **F-06** bounded social transport (streaming pinned HTTPS; no unbounded
  `resp.read()` before `social_max_bytes`)
- **F-07** generation cache body lifecycle + purge (Python + Node)
- **F-08** `body_file` path containment (no absolute/traversal/symlink escape)
- **F-09** package-boundary containment: explicit npm runtime allowlist plus
  `npm run package:check` prevents untracked local MCP/browser state, release
  evidence, credential-like files, Python caches, or incomplete runtime trees
  from entering a release tarball

Low findings:

- **L-01** SSRF inventory (`docs/ssrf-helper-inventory.md`); `api_fetch.mjs`
  validates public destinations on every hop; fixed endpoints documented
- **L-02** Action pin comments matched to exact tags containing the immutable SHAs

Do **not** dogfood or tag a superseded intermediate SHA after these fixes.

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
   configuration. Every task must have a schema-2.1 `run-result.json`, hashed
   raw prompt/output/ledger artifacts, unique run/session identities, and
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
  "schema_version": "1.1",
  "release_version": "3.2.0",
  "baseline_version": "3.1.1",
  "candidate_version": "3.2.0-rc.1",
  "baseline_skill_commit": "40-character lowercase commit SHA for v3.1.1",
  "candidate_skill_commit": "40-character lowercase candidate commit SHA",
  "candidate_tag": "v3.2.0-rc.1",
  "candidate_tag_object_sha": "40-character annotated RC tag-object SHA",
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

5. Create the sign-off declaration before the final stable commit. Its
   `promotion_manifest_sha256` must be the SHA256 of the final, unchanged
   `promotion.json`. Declare the PR and independent GitHub reviewer that will
   attest the exact final commit:

```json
{
  "schema_version": "1.1",
  "release_version": "3.2.0",
  "decision": "approved",
  "reviewer": {"name": "reviewer name", "role": "reviewer role"},
  "reviewed_at": "timezone-aware RFC3339 timestamp after generated_at",
  "promotion_manifest_sha256": "sha256:64-lowercase-hex",
  "attestation": {
    "type": "github_verified_pull_request_review",
    "repository": "d-init-d/d-research-skill",
    "pull_request_number": 7,
    "reviewer_login": "independent-reviewer-login"
  }
}
```

6. Commit the evidence and stable metadata. The stable commit may differ from
   the dogfooded RC only in the field-level version/classifier transformation,
   release notes, README version text, and versioned release evidence.
   `package.json` scripts/dependencies, the npm lock graph, and pyproject build
   backend/requirements/dependencies remain frozen. Run both post-RC checks:

```bash
git diff --name-only "$(git rev-parse 'refs/tags/v3.2.0-rc.1^{commit}')" HEAD > changed.txt
python scripts/check_contract.py --validate-post-rc-paths changed.txt --release-version 3.2.0
python scripts/check_contract.py \
  --validate-post-rc-metadata "$(git rev-parse 'refs/tags/v3.2.0-rc.1^{commit}')" \
  --release-version 3.2.0
```

7. Push the final commit and require the full `lint-and-self-test.yml` workflow
   to finish successfully on that exact SHA. The PR author cannot approve their
   own promotion. The declared reviewer must submit an `APPROVED` GitHub review
   on the exact final commit, with this line in the review body:

```text
D-Research-Promotion-SHA256: sha256:64-lowercase-hex
```

8. Run the contract against the same refs that the release workflow resolves:

```bash
python scripts/check_contract.py \
  --release-tag v3.2.0 \
  --candidate-commit "$(git rev-parse 'refs/tags/v3.2.0-rc.1^{commit}')" \
  --baseline-commit "$(git rev-parse 'refs/tags/v3.1.1^{commit}')" \
  --candidate-tag-object "$(git rev-parse 'refs/tags/v3.2.0-rc.1^{tag}')"
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

The source-archive workflow verifies both the RC and stable annotated tag
objects through GitHub's authenticated API, then queries Actions for a
successful full-CI run at the exact release SHA and queries the declared PR for
the exact-commit approval. It refuses missing, failing, mismatched, paginated,
or malformed API results before upload or provenance attestation. The remaining
trust boundary is GitHub's authenticated API, repository membership metadata,
and account security; the repository does not treat an HMAC or a reviewer name
string as independent approval.

See `CHANGELOG.md` for Added / Changed / Fixed / Compatibility.
