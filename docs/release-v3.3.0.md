# D Research v3.3.0

## v3.3.0 Release Notes

D Research v3.3.0 is the stable production release of the investigative-policy
expansion frozen in `v3.3.0-rc.1`. It enables deeper, multi-source public
research through scope-bound planning, item-level source provenance,
lead/evidence separation, and authorized self-exposure workflows. It does not
grant authority to bypass access controls, acquire stolen secrets, or turn
public fragments into harmful dossiers.

> **Promotion record:** This document is a release-note template committed
> before the RC is tagged. The final stable record must replace the pending
> fields in the technical assurance section with verified tag, CI, dogfood,
> review, archive, checksum, and provenance evidence. Until then, this file
> must not be read as a stable-release claim.

## Highlights

- **Scoped investigative research** — R0–R4 capability tiers make purpose,
  subject class, authorization, source admissibility, minimization, retention,
  risk budgets, and stopping criteria explicit.
- **Cross-platform social research** — Reddit, X, Facebook, Instagram,
  Hacker News, and other sources are assessed item by item. Platform identity
  never substitutes for speaker relationship, origin, integrity, or
  corroboration.
- **Lead-to-evidence separation** — non-official or unverified material may
  guide lawful discovery, but remains in a separately labeled lead section
  until the claim meets the required corroboration standard.
- **Leak-aware reporting** — public reporting, authorized provider corpora,
  user-supplied material, raw-leak metadata, and stolen secrets receive
  distinct dispositions. Raw dumps and secrets are never acquired, tested, or
  redistributed.
- **Verified self-exposure audit** — owned identifiers and domains can be
  checked through an authorized provider, with minimum disclosure,
  authorization binding, short retention, and remediation-focused output.

## What’s improved

### Investigation policy as code

`investigation_policy.py` and `investigation-scope.json` validate scope,
authorization attestations, source classes, output partitions, and bounded
resources without making a network request. Research and synthesis tasks bind
the exact policy bytes and authorization scope hash before dispatch.

### Evidence ledger and reporting

The canonical ledger now has 37 typed columns for source access, subject and
purpose, policy tier, social speaker and lineage, sensitivity, discovery and
reporting disposition, redaction, retention, and authorization. Exact legacy
14-, 19-, 22-, and 23-column ledgers remain readable and signable. Strict report
lint keeps main findings, non-official leads, blocked/prohibited sources, and
contradictions/unknowns in separate partitions.

### Safer social promotion

Social snapshots are lead-by-default. Main-findings promotion requires a
verified original statement, intact direct/API or sufficiently populated
archive evidence, and the explicit statement-made classification; a social
post does not automatically prove every underlying factual claim.

## Upgrade

No workspace migration is required for ordinary research plans or existing
ledgers. New investigative work should initialize and validate a scope:

```bash
npm run policy:init -- --mode R1 --out investigation-scope.json
npm run policy:check -- --file investigation-scope.json
npm run plan:bind-policy -- --file research-plan.json \
  --route investigative_osint --scope investigation-scope.json
```

Use `policy:bind` only when ownership, authorization, or public-interest review
has been independently established. A user-declared purpose is not proof of
authority.

## Compatibility

| Component | Support |
|---|---|
| Python | 3.10 or newer |
| Node.js | 18 or newer |
| Browser runtime | Playwright 1.61.1 (locked) |
| Existing research plans | Schema 2.0 remains supported |
| Existing evidence ledgers | 14/19/22/23-column formats remain supported |
| New evidence ledgers | 37-column v3.3 policy-aware format |
| Core runtime dependencies | No new mandatory dependency |

## Security boundaries

The release remains read-only by default. It never bypasses login, paywalls,
CAPTCHA, rate limits, robots, or other access controls. It hard-stops minors,
stalking, harassment, doxxing, precise real-time whereabouts, unauthorized
pseudonym re-identification, intrusion, malware, exfiltration, raw leak-dump
acquisition, and credential/token/session/private-key handling.

Public availability alone does not establish lawful custody, reliability, or
permission to redistribute. Sensitive personal details are minimized, redacted,
or excluded from reporting according to the validated scope.

## Quality and verification

The final stable record must list the exact results of the locked installation,
Node/Python self-tests, adversarial acceptance, real Chromium smoke, package
boundary and dry-pack checks, static checks, dependency audit, supported CI
matrix, extracted source-archive replay, and provenance verification. Pending
stable-promotion evidence is intentionally not summarized as a pass here.

## Downloads

Once promotion is complete, GitHub will provide the standard **Source code
(zip)** and **Source code (tar.gz)** archives for the annotated `v3.3.0` tag.

<details>
<summary>Technical release assurance</summary>

The final record will bind:

- stable commit and annotated tag-object SHA;
- exact `v3.3.0-rc.1` candidate commit and tag-object SHA;
- exact-SHA CI results for candidate and stable commits;
- 128 canonical live baseline/candidate bundles under one runtime/model/tool
  configuration, with recomputed Tier 1/Tier 2 scores and verdicts;
- SHA-256-bound promotion evidence and an independent trusted GitHub review;
- source archive, checksum, extracted-tree replay, independent reproduction,
  and build-provenance attestation.

No value in this list is populated until the corresponding artifact exists and
is verified by the release workflow.

</details>

**Full changelog:** [v3.2.1...v3.3.0](https://github.com/d-init-d/d-research-skill/compare/v3.2.1...v3.3.0) ·
[Detailed candidate notes](release-v3.3.0-rc.1.md)
