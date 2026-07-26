# D Research v3.4.0-rc.1

## v3.4.0-rc.1 Release Notes

D Research v3.4.0-rc.1 is a monotonic capability-expansion candidate. Its
public surface is a strict superset of v3.3.0: existing commands, options,
routes, references, scripts, templates, ledger formats, and no-config defaults
remain available. New network mutation behavior is explicit, and the complete
source profile remains available alongside the new clean runtime profile.

This candidate uses `Development Status :: 4 - Beta`. Stable `v3.4.0` may be
promoted only after the candidate tree and its release artifacts pass the
version-scoped release gates.

## Highlights

### Stronger API access without changing legacy GET behavior

- `scripts/api_fetch.mjs` now reads `api.maxPagesPerEndpoint` from
  `research.config.json`; `--max-pages` still has highest precedence and the
  no-config default remains `10`.
- POST, PUT, PATCH, and DELETE are available through explicit `--method` and
  `--intent` arguments, with `--body-json`, `--body-file`, and
  `--content-type` request construction.
- State-changing requests make one network attempt by default. Callers can opt
  into additional attempts with `--max-attempts`; legacy GET/query requests
  keep their existing retry behavior.
- Redirect handling follows HTTP method semantics, strips entity headers when
  a redirect becomes GET, never forwards credentials across origins, and
  requires `--allow-redirect-origin` before replaying a state-changing 307/308
  redirect to another origin.
- Successful 204/205 and empty responses are accepted. JSON objects and
  GraphQL envelopes are preserved instead of being collapsed to an empty
  result.

### Explicit archival and safer metadata

- `wayback.py save` keeps its historical command behavior while adding
  `--submit-archive`, `--dry-run`, and `--json` interfaces. Documentation now
  describes the real behavior instead of requiring a nonexistent flag.
- `run_metadata.py record --redact-secrets` masks common CLI, JSON, header,
  URL-query, bearer, basic-auth, camelCase, and quoted secret forms before
  persistence.
- Wayback and effective-config output redact URL credentials and secret query
  values. Redaction tests cover `clientSecret`, `refreshToken`, authorization
  headers, and credential-bearing URLs.

### Machine-checkable downstream interoperability

- `evidence_ledger.py contract --json` and npm `ledger:contract` expose ledger
  widths `14/19/22/23/37`, record types, HMAC/canonicalization identifiers,
  routes, entry points, and artifact profiles from live code.
- `templates/interop-contract.json` is generated from those constants and
  checked for drift, giving bundled consumers such as Aleph a deterministic
  import contract.
- A frozen v3.3.0 capability baseline checks npm commands, CLI options, routes,
  references, scripts, templates, package paths, ledger schemas, record types,
  and behavioral defaults. CI fails on any removal.

### Clean, deterministic installation artifacts

- `full` (alias `source`) remains the capability-complete developer and auditor
  distribution.
- The additional `runtime` profile is an allowlisted end-user payload. It
  excludes CI, release evidence, hostile evaluation fixtures, and the
  developer-only testing sub-skill while retaining every routed reference and
  runtime helper. Its projected package metadata advertises only commands
  closed inside that artifact.
- For identical source bytes, both profiles are deterministic `tar.gz` archives
  with an embedded manifest,
  sidecar manifest, checksum, per-file SHA-256 values, ordered-path digest, and
  tree digest.
- The builder rejects path traversal, case-insensitive collisions, symlinks,
  credential-like files, missing route closure, and profile contract drift.
  It verifies two independent builds, extraction outside Git, profile-specific
  self-tests, source-archive replay, and that runtime is a byte-exact subset of
  source.
- End-user installation now uses the checksummed runtime release artifact;
  cloning the complete repository is no longer the documented installation
  path.

### Documentation and package integrity

- Every one of the 52 reference guides is routed directly from `SKILL.md`.
- The script inventory covers all shipped scripts, and internal-reference
  checks now inspect fenced commands and bare executable paths.
- Fenced Python and JavaScript examples are syntax-checked in CI, alongside a
  mojibake screen.
- Optional visualization dependencies are declared under the
  `visualization` extra; core runtime paths remain dependency-free.

## Compatibility

| Surface | v3.4.0-rc.1 contract |
|---|---|
| Python | 3.10 or newer |
| Node.js | 18 or newer |
| Playwright | 1.61.1, unchanged |
| Existing API GET usage | Preserved, including default max pages `10` |
| Evidence ledgers | Exact 14/19/22/23/37-column formats remain supported |
| Record types | `claim`, `lead`, `process`, and `blocker` remain supported |
| Install profiles | Existing complete `full` surface plus additive `runtime` |
| Mandatory Python dependencies | None added |

## Verification contract

The candidate must pass:

```bash
npm run self-test
npm run self-test:source
npm run self-test:runtime
npm run artifact:self-test
npm run acceptance
npm run refs:check
npm run refs:check:decision-tree
npm run docs:check
npm run package:check
npm run capability:check
python scripts/check_contract.py
```

Stable promotion additionally binds the annotated candidate tag, exact
candidate and stable CI SHAs, candidate ancestry, deterministic archives,
checksums, extracted-artifact replay, and provenance attestation. Missing live
dogfood or independent-review evidence, if explicitly accepted by the
repository owner, is recorded as a narrow waiver and is never represented as
completed evidence.

## What this candidate does not do

- It removes no v3.3.0 capability and changes no no-config default.
- It does not make external mutation implicit.
- It does not weaken existing access-control, privacy, credential, or
  investigative-scope floors.
- It does not claim stable-release or remote-CI evidence before those artifacts
  exist.
