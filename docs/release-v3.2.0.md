# D Research v3.2.0

## v3.2.0 Release Notes

D Research v3.2.0 is the production-ready release of the schema-2.0 research
workflow. It combines browser-first lawful collection, evidence-ledger and
report gates, deterministic source scoring, citation management, structured
resource limits, and cross-platform release automation in one auditable skill.

This file is included in the final RC so the npm package path manifest remains
frozen during promotion. The stable commit will update only the final release
status and verification references permitted by the post-RC contract.

## Highlights

- Schema-2.0 plans separate research and synthesis tasks, bind approvals to
  immutable intent, lock portable output trees, and expose explicit
  `plan_ready`, `execute_ready`, `synthesize_ready`, and `release_ready` gates.
- Evidence ledgers support claim/process/blocker records, real HMAC integrity,
  source scoring, claim coverage, generated evidence/reference sections, and
  reproducibility assertions with stable IDs.
- Network helpers enforce credential isolation, same-origin pagination,
  browser and direct-HTTP SSRF defenses, robots policy, TLS verification,
  atomic cache writes, redaction, timeouts, and bounded resources.
- Browser probe, extraction, and crawl routes block page-originated mutation
  methods and enforce request, response, aggregate, and output budgets.
- Citation and report tooling fail closed on malformed paths, signatures,
  generated metadata, unsupported claims, duplicate keys, and hostile input.
- Evaluation tooling validates bench/run/artifact provenance, rejects malformed
  nested data without crashing, and preserves honest blocked/incomplete states.
- CI covers supported Python and Node versions on Ubuntu and Windows, real
  Chromium fixtures, package-boundary checks, archive replay, checksums, and
  provenance attestation.

## Compatibility

- Python 3.10 or newer.
- Node.js 18 or newer.
- Playwright 1.61.1 is locked for browser automation.
- Existing v3.1.1 workspaces migrate through
  [`upgrade-v3.1.1-to-v3.2.0.md`](upgrade-v3.1.1-to-v3.2.0.md).

## Release assurance

The v3.2.0 release decision uses the version-scoped maintainer policy frozen in
v3.2.0-rc.3. The policy records rather than conceals the waived live dogfood,
independent-review, and GitHub tag-verification requirements. Stable promotion
still requires the exhaustive hash-bound local suite, annotated tags, exact-SHA
CI, RC ancestry, semantic metadata freeze, archive replay, SHA-256 validation,
and GitHub provenance attestation.

See [`release-v3.2.0-rc.3.md`](release-v3.2.0-rc.3.md) for the complete policy,
test commands, residual-risk statement, and promotion sequence.
