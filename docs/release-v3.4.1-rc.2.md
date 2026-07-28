# D Research v3.4.1-rc.2

## v3.4.1-rc.2 Release Notes

D Research v3.4.1-rc.2 is the frozen patch candidate for v3.4.1. It preserves
the executable behavior validated in RC1 and adds the final stable release-note
path to the candidate package boundary before promotion.

This lifecycle correction matters for reproducibility: the stable release can
now refine its release narrative without introducing a package path that was
absent from the exact candidate. Commands, options, routes, schemas, defaults,
network behavior, dependencies, and artifact profiles are unchanged from RC1.

## Included product correction

- Public entry documents consistently state that D Research is read-only by
  default while explicit, user-authorized archival and API mutation operations
  remain available through dedicated commands or `--intent archive|mutation`.
- Contract checks reject stale absolute read-only assertions and future wording
  that hides the existing mutation surface.
- The social snapshot self-test remains hermetic on filtered DNS while retaining
  production SSRF resolution for private-host and malformed-URL cases.

## Compatibility

| Surface | v3.4.1-rc.2 contract |
|---|---|
| Python | 3.10 or newer |
| Node.js | 18 or newer |
| Playwright | 1.61.1, unchanged |
| API GET/query behavior | Preserved, including default max pages `10` |
| API mutation | Existing explicit POST/PUT/PATCH/DELETE surface preserved |
| Evidence ledgers | Exact 14/19/22/23/37-column formats remain supported |
| Record types | `claim`, `lead`, `process`, and `blocker` remain supported |
| Artifact profiles | Capability-complete `full` plus additive `runtime` |
| Mandatory Python dependencies | None added |

## Promotion contract

Stable promotion is restricted to version/classifier metadata, public release
documentation, the generated interop package version, and version-scoped
evidence. Executable and policy code, dependency graphs, package paths, routes,
and artifact contracts are frozen at this candidate.

The candidate must pass exact-SHA CI across the supported Python and Node
matrices, Windows and Ubuntu integration, real Chromium smoke tests, optional
backends, source/runtime self-tests, deterministic artifact builds, acceptance
34/34, source archive replay, independent reproduction, and provenance
attestation.
