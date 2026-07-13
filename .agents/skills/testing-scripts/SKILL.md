---
name: testing-scripts
description: Verify the d-research-skill helper scripts (Node + Python). Use after editing files under scripts/, changing dependencies, or preparing a release.
---

# Testing D Research Skill Scripts

Use this sub-skill after changing any helper under `scripts/`, changing
`package.json` or `package-lock.json`, or preparing an RC/stable release.

## Prerequisites

- Node.js 18 or newer
- Python 3.10 or newer
- Locked Node dependencies installed with `npm ci`
- Chromium installed with `npx --no-install playwright install chromium` for
  the real browser smoke
- Pandoc, Poppler, and Tesseract for release-integration coverage of optional
  extraction/rendering paths

The unit and contract suites are offline. The browser smoke uses only local
HTTP/HTTPS fixtures. No external API key is required.

## Required local release checks

Run from the repository root:

```bash
npm ci --ignore-scripts --no-audit --no-fund
npm run self-test
npm run acceptance
npm run browser:smoke
npm run package:check
npm pack --dry-run --json
```

Pass criteria:

- every command exits `0`
- the acceptance summary reports zero `FAIL`
- the browser smoke reports all local security scenarios as passing
- the package path fingerprint matches and no generated/local/evidence artifact
  enters the dry-run tarball
- no Python traceback or unhandled Node rejection appears

`npm run self-test` is split into:

```bash
npm run self-test:node
npm run self-test:python
```

The Python suite includes the repository-reference checks, dynamic contract
checker, eval-bench validation, and resource-limit tests. The Node suite covers
the browser helpers, API fetcher, shared HTTP cache, and web-search helper.
Treat `package.json` as the authoritative list; do not duplicate a stale script
count here. `references/script-inventory.md` documents helper ownership and
routing.

Package validation must also pass after Python bytecode caches exist under
`examples/`; generated `__pycache__`, `.pyc`, `.pyo`, and `.pyd` files must be
excluded from npm output. The extracted source-archive test must run without a
`.git` directory and still pass `npm run self-test` plus `npm pack --dry-run`.

## Static checks

Run these after any cross-cutting change:

```bash
ruff check scripts/
python -m compileall -q scripts examples
python scripts/check_node_syntax.py
python scripts/check_internal_refs.py
python scripts/check_internal_refs.py --decision-tree
python scripts/check_contract.py
python scripts/bench_harness_check.py check-all --strict
git diff --check
```

Run `actionlint` over all files under `.github/workflows/` when the Go toolchain
is available. Run `npm audit --omit=dev --audit-level=moderate` when network
access is available; record an unavailable registry as an external limitation,
not a synthetic pass.

`evidence_ledger.py self-test` intentionally exercises tamper detection before
printing its success marker. That intermediate diagnostic is expected.

## Runtime matrix

The required CI matrix is:

- Python 3.10, 3.11, and 3.12 for lint and Python self-tests
- Node.js 18, 20, and 22 for syntax and Node self-tests
- Ubuntu and Windows integration jobs with Pandoc, Poppler, Tesseract, locked
  Node dependencies, one adversarial acceptance run, and exactly one Chromium
  smoke per operating system

When a change is sensitive to runtime compatibility, reproduce the affected
matrix locally where those runtimes are available. A single local interpreter
does not replace the required CI jobs.

## Security acceptance coverage

`npm run acceptance` must exercise the actual behavior rather than wrapper
existence. It covers at least:

- cross-origin credential and Link-header isolation
- secret redaction and credential-cache policy
- robots handling, including redirect destinations
- TLS verification by default and explicit opt-in limitations
- report workspace path containment and claim-marker linting
- date/freshness scoring gates and citation fallbacks
- structured resource-limit blockers

`npm run browser:smoke` launches real Chromium against loopback-only fixtures.
It verifies probe/extract/crawl behavior, robots status mapping, zero-request
redirect denial, credential isolation, and local self-signed TLS behavior.

## Common failures

| Symptom | Likely cause | Action |
|---|---|---|
| `ModuleNotFoundError` | Missing import or wrong interpreter | Confirm Python 3.10+ and inspect imports before adding dependencies |
| `ERR_UNKNOWN_FILE_EXTENSION .py` | Python helper invoked with Node | Use `python` or `scripts/run_python.mjs` |
| Browser executable missing | Chromium was not installed for the locked Playwright version | Run `npx --no-install playwright install chromium` |
| Resource test exits `3` | A configured cap was exceeded | Confirm the incomplete blocker/sidecar is present; raise the limit only when justified |
| Reference check fails | A documented local path is stale | Correct the route or restore the file |
| Contract check fails | Version, counts, config, CLI, or release docs drifted | Fix the reported source of truth; never hard-code around the check |
| Eval strict check fails | Bench schema or frozen empty-score fixture drifted | Migrate the fixture intentionally and review the scoring delta |

## Adding or changing a helper

1. Keep the implementation compatible with the declared Python/Node runtime.
2. Add an offline `self-test` (Python) or `--self-test` (Node).
3. Add the self-test to the appropriate package script.
4. Add or update focused adversarial coverage for security-sensitive behavior.
5. Update `references/script-inventory.md`, route/config documentation, and
   dynamic contract assertions when the public surface changes.
6. Run every required local release check above.

## CI and release boundary

`.github/workflows/lint-and-self-test.yml` is the authoritative CI definition.
`.github/workflows/release-source-archive.yml` may publish only from a matching
annotated tag under the release policy frozen into the candidate RC. Manual
dispatch is validation-only. The default stable path requires GitHub-verified
tags, independent review, and live dogfood. A release-scoped maintainer override
is valid only when the RC contract names the exact version, waiver set, owner,
non-waivable hard gates, required local checks, and hash-bound evidence before
the candidate tag exists. Such an override never waives annotated tags, RC
ancestry, exact-SHA CI, archive/checksum validation, or provenance attestation.
