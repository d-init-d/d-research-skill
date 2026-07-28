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

The stable release promotes candidate commit
`65d11e47068e19bfde3d35b4124d70e33a66fc83`. Its SSH-signed annotated
`v3.4.1-rc.2` tag object is
`2d369d30f7f5fd58b17e5828e3d5507de36986f9`, verified by GitHub.

The exact candidate passed:

- the complete CI matrix on Python 3.10-3.12 and Node.js 18/20/22;
- Windows and Ubuntu integration, real Chromium, and optional backends;
- source/runtime build, extraction, replay, closure, and deterministic artifact
  gates;
- 34/34 adversarial acceptance, dependency audit, contract negative fixtures,
  and the v3.4.0 capability-superset baseline;
- source archive checksum verification, independent reproduction, and GitHub
  provenance attestation.

Stable publication remains fail-closed on exact stable-SHA CI, a signed and
GitHub-verified stable tag, candidate ancestry, source archive replay,
checksums, and provenance. Exactly two external assurances are explicitly
waived and are not represented as completed evidence: independent pull-request
review and uncontaminated live dogfood. These waivers do not apply to any
artifact, signature, CI, ancestry, archive, or provenance gate.

**Full changelog:**
[v3.4.0...v3.4.1](https://github.com/d-init-d/d-research-skill/compare/v3.4.0...v3.4.1)
