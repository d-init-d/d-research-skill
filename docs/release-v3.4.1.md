# D Research v3.4.1

## v3.4.1 Release Notes

D Research v3.4.1 is a focused production patch that makes the product's public
access-model contract accurately describe its existing capability surface. The
default posture remains read-only; explicit, user-authorized archival and API
mutation operations remain available through dedicated commands or
`--intent archive|mutation`.

No migration is required. Existing commands, flags, routes, ledger formats,
record types, configuration, defaults, and artifacts remain compatible.

## Highlights

### Truthful capability discovery

- `SKILL.md`, `AGENTS.md`, `README.md`, and `README.vi.md` now expose one
  consistent access model.
- The documentation no longer contradicts the existing Wayback and
  POST/PUT/PATCH/DELETE interfaces.
- A machine-enforced contract prevents absolute read-only wording from hiding
  explicitly authorized operations in future releases.

### More reliable offline verification

- The social snapshot self-test no longer depends on public DNS resolving
  normally when all HTTP responses are mocked.
- Known fixture hosts use a bounded test-only resolver seam; every private,
  loopback, metadata, mapped-IPv6, and malformed target still exercises the
  production SSRF resolver and must fail closed.

## Compatibility

| Surface | v3.4.1 support |
|---|---|
| Python | 3.10 or newer |
| Node.js | 18 or newer |
| Playwright | 1.61.1, unchanged |
| Existing API GET/query usage | CLI contract and defaults preserved |
| Authorized API mutation | Existing POST/PUT/PATCH/DELETE surface preserved |
| Evidence ledgers | 14/19/22/23/37-column formats |
| Record types | `claim`, `lead`, `process`, `blocker` |
| Artifact profiles | `full` (`source` alias) and `runtime` |
| Mandatory Python dependencies | None added |

## Upgrade guidance

Replace the installed v3.4.0 runtime or full artifact with the corresponding
v3.4.1 artifact and run its profile-specific self-test. Existing config-free
and configured workflows require no schema or command migration.

## Release assurance

The stable release promotes the exact signed v3.4.1 candidate without changing
executable code, dependencies, package paths, routes, or artifact contracts.
Exact-SHA CI, source archive replay, independent reproduction, checksums,
deterministic dual-profile artifacts, and GitHub provenance remain
non-waivable release requirements.

**Full changelog:**
[v3.4.0...v3.4.1](https://github.com/d-init-d/d-research-skill/compare/v3.4.0...v3.4.1)
