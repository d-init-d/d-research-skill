# Owner Release Direction: D Research v3.9.0

- **Repository:** `d-init-d/d-research-skill`
- **Maintainer / Owner:** `d-init-d`
- **Candidate Tag:** `v3.9.0-rc.1` (`3553d2260a945562842fed13629d87a620ea4f19`)
- **Candidate Commit:** `fae50cdff142d47cb47e9fb4f4dea9d23305011a`
- **Target Stable Release:** `v3.9.0`
- **Authorized At:** `2026-11-26T13:09:30Z`

## Decision

Promote the signed `v3.9.0-rc.1` candidate snapshot to `v3.9.0` stable under `approved_with_waivers`.
All deterministic self-tests, pytest suites, Ruff lint checks, artifact profile builds, capability superset checks,
and exact-commit CI matrix runs (Ubuntu & Windows including Chromium smoke, run `45825280500`) completed with zero failures.

## Disclosed Waivers

- `independent_reviewer`: Solo repository owner release (`d-init-d`) with signed commits, signed annotated tags, and automated CI attestation.
- `live_dogfood`: Deferred external live held-out agent dogfood run under owner authorization; full deterministic suite, host-browser capture verification, and live CI Chromium integration passed.
