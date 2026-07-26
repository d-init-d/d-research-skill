# D Research v3.4.0

## v3.4.0 Release Notes

D Research v3.4.0 is the stable production release of the monotonic-capability
candidate frozen as `v3.4.0-rc.1`. It expands API collection, archival,
metadata protection, downstream interoperability, reference routing, and
installation packaging while preserving every v3.3.0 command, route, ledger
format, and no-config default.

The executable surface is inherited from the signed release candidate. Stable
promotion changes only lifecycle metadata, documentation, the generated
interop package version, and version-scoped release evidence.

## Highlights

### Broader API collection with preserved GET behavior

- `scripts/api_fetch.mjs` now supports POST, PUT, PATCH, and DELETE through
  explicit `--method` and `--intent` options, plus JSON/file request bodies and
  caller-selected content types.
- Existing GET/query calls retain the same behavior and the same default limit
  of 10 pages. `api.maxPagesPerEndpoint` supplies an optional config default;
  the established `--max-pages` option still wins.
- Mutation requests make one attempt by default, avoiding accidental duplicate
  writes. Additional attempts remain available through explicit opt-in.
- Redirect handling follows 301/302/303/307/308 method semantics, removes
  credentials across origins, and requires explicit authorization before a
  state-changing 307/308 replay crosses origins.
- Valid 204/205 and empty responses are accepted, while JSON objects and
  GraphQL envelopes are preserved.

### Explicit archival controls and stronger secret redaction

- `wayback.py save` keeps its historical behavior and adds
  `--submit-archive`, `--dry-run`, and machine-readable `--json` output.
- `run_metadata.py record --redact-secrets` masks common CLI, JSON, URL-query,
  authorization-header, camelCase, bearer, basic-auth, and quoted-secret forms
  before persistence.
- Effective-config and Wayback output redact URL credentials and sensitive
  query values.

### Stable machine-readable interop for bundled consumers

- `evidence_ledger.py contract --json` and npm `ledger:contract` expose ledger
  widths `14/19/22/23/37`, record types, canonicalization/signature identifiers,
  routes, entry points, and artifact profiles from live code.
- `templates/interop-contract.json` is generated from those constants and
  checked for drift. Bundled consumers such as Aleph can bind to this contract
  instead of inferring compatibility from prose.
- The ledger matrix continues to accept `claim`, `lead`, `process`, and
  `blocker` records; no historical ledger width is removed.

### Clean dual-profile installation artifacts

- `full` remains the capability-complete developer/auditor distribution;
  `source` remains its accepted alias.
- The additive `runtime` profile is an allowlisted end-user payload that
  excludes CI history, release evidence, hostile evaluation fixtures, and the
  developer-only testing sub-skill while retaining its routed references and
  operational helpers.
- Both profiles are deterministic for identical source bytes and ship with an
  embedded manifest, sidecar manifest, archive checksum, per-file hashes,
  ordered-path digest, and tree digest.
- Artifact verification uses the trusted local profile contract, supports
  expected version/SHA binding, applies compressed and extracted size limits,
  and rejects traversal, symlink, junction, reparse-point, case-collision, and
  forged-profile inputs before running artifact code.
- End-user documentation now recommends the checksummed runtime artifact;
  cloning the complete repository is no longer the installation path.

### Discoverability and package integrity

- All 52 reference guides are directly routed from `SKILL.md`.
- The inventory covers all 55 Python/Node script files, including runtime,
  development, and release roles.
- CI validates fenced Python and JavaScript examples, internal executable
  paths, reference decision-tree reachability, package boundaries, and
  mojibake regressions.
- Python and Node network clients derive their User-Agent version from
  `package.json`, eliminating stale embedded release labels.

## Compatibility

| Surface | v3.4.0 contract |
|---|---|
| Python | 3.10 or newer |
| Node.js | 18 or newer |
| Playwright | 1.61.1, unchanged |
| Existing API GET usage | Preserved, including default max pages `10` |
| Evidence ledgers | Exact 14/19/22/23/37-column formats remain supported |
| Record types | `claim`, `lead`, `process`, and `blocker` |
| Install profiles | Capability-complete `full` plus additive `runtime` |
| Mandatory Python dependencies | None added |

## Upgrade guidance

Choose the runtime artifact for a clean end-user installation or the full
artifact for development, evaluation, and audit work. Verify the adjacent
`.sha256` file before extraction, then run the profile-specific self-test. The
complete commands and artifact names are published with the GitHub Release.

Existing config-free calls need no migration. New pagination config and API
mutation options are opt-in; existing CLI flags continue to take precedence.

## Verification and release assurance

The frozen candidate is commit
`d1da48dd4b0053e829255fe1d2dfe26f8c58f408`. Its SSH-signed annotated
`v3.4.0-rc.1` tag object is
`6ca963e04fb116d2aa6f3d69231537b23f10a953`, verified by GitHub.

The exact candidate passed:

- the complete CI matrix on Python 3.10-3.12 and Node.js 18/20/22;
- Windows and Ubuntu integration with real Chromium;
- source/runtime build, extraction, replay, closure, determinism, and forged
  profile tests;
- a 24-check local promotion record, package audit, contract anti-spoof tests,
  and the v3.3.0 capability-superset gate;
- source archive checksum verification, independent archive reproduction, and
  GitHub provenance attestation.

Stable publication remains fail-closed on exact stable-SHA CI, a signed and
GitHub-verified annotated stable tag, candidate ancestry, source archive
replay, checksum validation, independent reproduction, and provenance
attestation. The GitHub Release record links those stable-run receipts and
publishes the final artifact hashes.

Exactly two external assurances are explicitly waived and are not represented
as completed evidence:

- `independent_reviewer`: no independent GitHub pull-request review is claimed;
- `live_dogfood`: no uncontaminated live Tier-1/Tier-2 comparison is claimed.

The repository-owner decision and residual-risk statements are bound in
`release-evidence/v3.4.0/maintainer-override.json`. These waivers do not apply
to signed tags, exact-SHA CI, artifact integrity, archive replay, candidate
ancestry, or provenance.

## Security posture

This release adds no implicit network mutation and weakens no existing access,
credential, privacy, robots, rate-limit, or investigative-scope floor. It adds
capability through explicit interfaces while keeping established read/query
paths and defaults intact.

**Full changelog:** [v3.3.0...v3.4.0](https://github.com/d-init-d/d-research-skill/compare/v3.3.0...v3.4.0) ·
[candidate notes](release-v3.4.0-rc.1.md)
