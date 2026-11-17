# Owner Release Direction: D Research v3.8.0

- **Repository:** `d-init-d/d-research-skill`
- **Maintainer / Owner:** `d-init-d`
- **Candidate Tag:** `v3.8.0-rc.1` (`469d0c6825b1eac89bf5681bfeccb54954af158e`)
- **Candidate Commit:** `0217bf5550939021a6cb38a351302605cd4336af`
- **Target Stable Release:** `v3.8.0`
- **Authorized At:** `2026-11-17T17:20:57Z`

## Decision

Promote the signed `v3.8.0-rc.1` candidate snapshot to `v3.8.0` stable under `approved_with_waivers`.
All deterministic self-tests, pytest suites, Ruff lint checks, artifact profile builds, capability superset checks,
and exact-commit CI matrix runs (Ubuntu & Windows including Chromium smoke, run `44134764401`) completed with zero failures.

## Disclosed Waivers

- `independent_reviewer`: Solo repository owner release (`d-init-d`) with signed commits, signed annotated tags, and automated CI attestation.
- `live_dogfood`: Deferred external live held-out agent dogfood run under owner authorization; full deterministic suite, host-browser capture verification, and live CI Chromium integration passed.
