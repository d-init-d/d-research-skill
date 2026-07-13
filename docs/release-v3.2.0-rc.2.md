# D Research v3.2.0-rc.2

## v3.2.0-rc.2 Release Notes

Status: production-hardening release candidate. This document defines the
candidate that may be tagged after exact-SHA CI and independent review pass. It
does not claim stable promotion or live dogfood completion.

## Candidate scope

This candidate keeps the v3.2 plan/report/ledger/API/social/citation surface and
closes the independently reproduced gaps found after rc.1 preparation:

- RFC 9309 robots matching normalizes percent-encoded unreserved octets.
- Crawl summaries distinguish queue exhaustion from page/domain/depth/resource
  ceilings and never label a bounded partial crawl complete.
- Promotion evaluations are complete per run; sparse metrics cannot be averaged
  away. Findings ledgers fail closed and unresolved Critical/High/Medium rows
  block promotion.
- Credential-bearing search, translation, and embedding requests use bounded
  manual redirects and reject cross-origin leakage before the next request.
- Python HTTPS connects require the normalized peer to belong to the
  DNS-validated address set before TLS.
- Node and Python use one deterministic IPv6 public-destination policy:
  IPv4-mapped addresses use the embedded IPv4 policy, addresses outside
  `2000::/3` fail closed, and translation/non-public GUA ranges are blocked.
  The policy is independent of version-drifting runtime address tables.
- Node `fetchPublicHttp` omits TLS SNI for IP literals, retains DNS SNI, and
  always binds `Host` from the validated URL (caller `Host`/`HOST` stripped on
  every hop; IPv6 brackets and non-default ports retained). Connected peers are
  canonicalized before DNS-set membership. Self-tests exercise immediate and
  delayed (`connecting` then `connect`) production socket peer gates. Malformed
  peer, bracket/scope/whitespace variants, and IPv6 fallback forms fail closed.
  Abnormal upstream statuses that
  cannot construct a Fetch `Response` (e.g. 600) reject the promise without
  process crash; null-body/HEAD responses drain their network message and cap
  observable bytes without rejecting valid `HEAD`/`304` representation lengths.
  Their TCP connections are retired because Node hides post-header bytes for
  parser-defined null-body responses.
- Python `_pinned_https_open` uses the same URL-derived Host rule (bracketed
  IPv6 authority) and a shared `_assert_connected_peer` on both production and
  the injectable test transport (which must supply `peer_ip`). Explicit port
  `0` remains distinct from the default HTTPS port in transport and origin logic.
- Failed atomic Python cache publication returns failure rather than a phantom
  cache key; purge-all also fails on real locked artifacts or enumeration
  errors while ignoring only confirmed Windows directory tombstones.
- Long-horizon instructions require `execute_ready`/`dispatch_ready` before any
  task, gate research and synthesis separately, and require exact release
  report/citations/claim coverage.
- Intake labels and SKILL route rows are bound to the machine-readable manifest.
- Python 3.10–3.12 CI runs all Python helpers, including content sanitation and
  quality evaluation.
- Direct npm packing runs the package boundary automatically; source archives
  verify the same deterministic path manifest without relying on `.git`.
- Generated Python bytecode remains excluded even after `compileall`, and the
  installation matrix covers Grok Build as well as Agent Skills, Codex, Claude
  Code, and OpenCode.
- Manual release validation is read-only; OIDC/attestation permissions are
  limited to signed tag-push release jobs.

## Compatibility

- Python: 3.10, 3.11, 3.12.
- Node.js: 18, 20, 22 (`engines.node >=18`).
- Playwright: exact locked version from `package-lock.json`.
- Research plan: schema 2.0; v1 migration remains available.
- Evidence ledgers: canonical 23 columns; legacy 14/19/22-column inputs remain
  readable under the documented compatibility rules.
- Existing v3 CLI aliases remain deprecated rather than removed.

## Required local candidate checks

Run from the repository root on a clean tracked worktree:

```sh
npm ci --ignore-scripts --no-audit --no-fund
ruff check scripts/
python -m compileall -q scripts examples
python scripts/check_node_syntax.py
python scripts/check_internal_refs.py
python scripts/check_internal_refs.py --decision-tree
python scripts/check_contract.py
python scripts/check_contract.py self-test
python scripts/bench_harness_check.py check-all --strict
npm run self-test
npm run acceptance
npm run browser:smoke
npm run package:check
npm pack --dry-run --json
git diff --check
```

Pass criteria:

- every command exits zero;
- acceptance reports zero failures;
- browser smoke passes all loopback-only scenarios;
- package output matches the committed path fingerprint and contains no local,
  credential, browser-state, evidence, cache, or untracked files;
- `git status --short` contains no unexpected generated files.

## Exact-SHA CI gate

The candidate commit must pass all required jobs from
`.github/workflows/lint-and-self-test.yml` and `.github/workflows/link-check.yml`:

- Python 3.10, 3.11, 3.12 unit matrix;
- Node 18, 20, 22 unit matrix;
- Ubuntu and Windows full integration;
- Chromium smoke on both integration operating systems;
- strict bench consistency and internal/external link policy.

Do not reuse checks from a superseded commit. The commit reviewed, tagged, and
recorded in release evidence must be identical.

## RC tag gate

After local checks, exact-SHA CI, and candidate review pass:

```sh
git tag -s v3.2.0-rc.2 -m "D Research v3.2.0-rc.2"
git push origin v3.2.0-rc.2
```

The release workflow independently requires an annotated, GitHub-verified tag
whose semantic version matches `package.json` and `pyproject.toml`. It builds a
versioned source archive, verifies the extracted no-`.git` tree, emits SHA-256
checksums, and creates provenance attestation. Manual dispatch cannot publish or
attest an archive.

## Stable promotion gate

Stable `v3.2.0` remains blocked until all of the following are committed under
`release-evidence/v3.2.0/` and validate against the exact rc.2 tag commit:

1. Live Tier-1 12-task baseline and candidate score artifacts.
2. Live Tier-2 52-task baseline and candidate score artifacts.
3. Schema-2.1 `run-result.json` plus integrity-bound prompt/output/ledger data
   for every attempted task.
4. Identical runtime, model, tool configuration, evaluator commit, and current
   bench fingerprints for baseline and candidate.
5. Hashed A/B/C forward-test artifacts, including a blind role C without answer,
   candidate, score, or intended-fix leakage.
6. Three deterministic green quality runs with integrity-covered logs.
7. Green exact-candidate CI evidence and a valid findings ledger with no open or
   unresolved Critical/High/Medium item.
8. `promotion.json` and an independent GitHub-verified pull-request review bound
   to the exact release SHA and promotion-document SHA-256.

Local synthetic fixtures and mocked APIs prove harness behavior only; they are
never substitutes for live promotion evidence.

## Stable metadata-only transition

After rc.2 dogfood is frozen, stable promotion may change only the allowlisted
version/release metadata and versioned evidence directory. Validate the diff and
metadata against the tagged candidate:

```sh
git diff --name-only "$(git rev-parse 'refs/tags/v3.2.0-rc.2^{commit}')" HEAD > changed.txt
python scripts/check_contract.py \
  --validate-post-rc-paths changed.txt \
  --release-version 3.2.0
python scripts/check_contract.py \
  --validate-post-rc-metadata "$(git rev-parse 'refs/tags/v3.2.0-rc.2^{commit}')" \
  --release-version 3.2.0
```

Any code, workflow, skill, route, helper, dependency graph, or evaluation-harness
change after dogfood requires a new RC and a complete rerun.

## Truthful release claim

Before the tag and external gates pass, the correct claim is:

> v3.2.0-rc.2 candidate code and offline release gates are ready for exact-SHA
> CI, independent review, and live dogfood. Stable v3.2.0 is not yet claimed.
