# D Research v3.4.0-rc.1

## v3.4.0-rc.1 Release Notes

D Research v3.4.0-rc.1 is a **monotonic capability-expansion** release
candidate. Its governing rule is that the candidate's public surface is a strict
superset of v3.3.0: every command, option, route, reference, script, template,
ledger schema, and default that existed before still exists and behaves the
same unless a caller explicitly opts into new behavior. The candidate only adds
capability, widens compatibility, or fixes defects.

This build uses prerelease metadata (`Development Status :: 4 - Beta`). Under the
repository's own promotion model, a candidate carries an `-rc.N` version so it is
exempt from the stable release-evidence gate while feature work proceeds; stable
`v3.4.0` is produced later by promotion.

## Monotonic guarantees

Every phase in this candidate is verified against a frozen capability baseline:

```
python release-evidence/v3.4.0/baseline/capability_baseline.py \
  check --baseline release-evidence/v3.4.0/baseline/capability-baseline.json
```

The check fails if any npm script, route id, reference, script, or template is
removed, if a ledger header size (14/19/22/23/37) or record type
(claim/lead/process/blocker) is dropped, if the HMAC signature or CSV
canonicalization identifier changes, or if a recorded default (such as
`api_fetch.maxPages = 10`) changes without a caller opt-in.

## What is new so far

- **Capability baseline + superset checker** — a stdlib tool that freezes and
  enforces the monotonic invariant across the whole upgrade.
- **Downstream interop contract** — `evidence_ledger.py contract --json` (npm
  `ledger:contract`) emits the ledger schema numbers, record types, signature
  and canonicalization identifiers, route ids, entrypoints, and artifact
  profiles from live code. The committed snapshot `templates/interop-contract.json`
  is generated from the same constants and validated for drift by
  `check_contract.py`, giving downstream consumers (e.g. Aleph) a stable,
  machine-checkable compatibility surface.

Additional capability phases (config-driven pagination, additive HTTP methods,
Wayback and run-metadata options, reference routing, and dual artifact profiles)
land in subsequent candidate commits, each gated by the same superset check.
