# Owner Release Direction: D Research v3.7.0

- **Repository:** `d-init-d/d-research-skill`
- **Maintainer / Owner:** `d-init-d`
- **Candidate Tag:** `v3.7.0-rc.1` (`4ba2a88ac506e4335fdbf67146919719aea4e337`)
- **Candidate Commit:** `5bd62850c0b3ecee7d963c0d214b3add7aa7af0d`
- **Target Stable Release:** `v3.7.0`
- **Authorized At:** `2026-11-14T15:30:47Z`

## Decision

Promote the signed `v3.7.0-rc.1` candidate snapshot to `v3.7.0` stable under `approved_with_waivers`.
All deterministic checks, Chromium browser smoke & acceptance suites, 162 pytest tests, Ruff lint checks,
contract/provenance validations, and exact-commit CI matrix checks completed with zero failures.

## Disclosed Waivers

- `independent_reviewer`: Solo repository owner release (`d-init-d`) with signed commits, signed annotated tags, and automated CI attestation.
- `live_dogfood`: Deferred external live held-out agent dogfood run under owner authorization; full deterministic suite, host-browser capture verification, and real Chromium acceptance passed.
