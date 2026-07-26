# D Research v3.3.0

## v3.3.0 Release Notes

D Research v3.3.0 is the stable production release of the investigative-policy
expansion introduced by `v3.3.0-rc.1`. It enables deeper multi-source public
research through scope-bound planning, item-level source provenance,
lead/evidence separation, cross-platform social analysis, and authorized
self-exposure workflows.

The release widens lawful discovery and analysis, not access authority. It does
not permit bypassing access controls, acquiring stolen secrets, or turning
public fragments into harmful dossiers.

## Highlights

- **Scoped investigative research** — `R0`-`R4` capability tiers make purpose,
  subject class, authorization, source admissibility, minimization, retention,
  risk budgets, and stopping criteria explicit.
- **Cross-platform social research** — Reddit, X, Facebook, Instagram, Hacker
  News, and other sources are assessed item by item. Platform identity never
  substitutes for speaker relationship, content origin, integrity, or
  corroboration.
- **Lead-to-evidence separation** — non-official or unverified material may
  guide lawful discovery, but remains in a separately labeled lead section
  until the claim meets its required corroboration standard.
- **Leak-aware reporting** — public reporting, authorized-provider corpora,
  user-supplied material, raw-leak metadata, and stolen secrets receive
  distinct dispositions. Raw dumps and secrets are never acquired, tested, or
  redistributed.
- **Verified self-exposure audit** — owned identifiers and domains can be
  checked through authorized providers, with minimum disclosure, short
  retention, authorization binding, and remediation-focused output.

## What's improved

### Investigation policy as code

`scripts/investigation_policy.py` and
`templates/investigation-scope.json` validate scope, authorization
attestations, source classes, output partitions, and bounded resources without
making a network request. Research and synthesis tasks bind the exact policy
bytes and authorization scope hash before dispatch.

### Evidence ledger and reporting

The canonical ledger now has 37 typed columns for source access, subject and
purpose, policy tier, social speaker and lineage, sensitivity, discovery and
reporting disposition, redaction, retention, and authorization. Exact legacy
14-, 19-, 22-, and 23-column ledgers remain readable and signable.

Strict report lint keeps evidence-backed main findings, non-official or
unverified leads, blocked/prohibited sources, and contradictions/unknowns in
separate partitions. Lead records cannot be silently cited as main findings.

### Safer social promotion

Social snapshots are lead-by-default. Main-findings promotion requires a
verified original statement, intact direct/API evidence or a sufficiently
populated archive record, and the explicit `statement_made` classification. A
social post does not automatically prove every underlying factual claim.

## Upgrade

No workspace migration is required for ordinary schema-2.0 research plans or
existing ledgers. New investigative work should initialize and validate a
scope:

```bash
npm run policy:init -- --mode R1 --out investigation-scope.json
npm run policy:check -- --file investigation-scope.json
npm run plan:bind-policy -- --file research-plan.json \
  --route investigative_osint --scope investigation-scope.json
```

Use `policy:bind` only after ownership, authorization, or public-interest
review has been independently established. A user-declared purpose is not
proof of authority.

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
permission to redistribute. Sensitive personal details are minimized,
redacted, or excluded according to the validated scope.

## Quality and verification

The exact candidate commit is
`4be4890d5842426240c39b8b8e4725bfec511424`; its SSH-signed,
GitHub-verified annotated `v3.3.0-rc.1` tag object is
`5abb7d852239635d8c8da626aa00844c5e260998`.

Candidate verification completed successfully:

- 34/34 adversarial acceptance scenarios;
- all 14 real-browser Chromium smoke groups;
- the frozen 207-path package boundary and dry-pack inspection;
- Python 3.10-3.12 and Node.js 18/20/22 CI on Ubuntu and Windows;
- dependency audit with zero reported vulnerabilities;
- source archive checksum and replay without `.git` metadata;
- independent archive reproduction and GitHub build provenance.

The RC source archive SHA-256 is
`5002b1c640a8005bb68e768905e88dbb85db7c95f2dee67119ec899670185a4a`.
Stable publication additionally requires successful exact-SHA CI for the
stable commit, a GitHub-verified stable tag, candidate ancestry, archive and
checksum verification, extracted-tree replay, independent reproduction, and
provenance attestation.

## Release assurance and residual risk

At the repository owner's explicit direction, v3.3.0 proceeds directly from
`v3.3.0-rc.1` without a second release candidate. Because RC1 froze the default
`live_evidence` contract, the stable tree records a post-candidate release
policy amendment limited to `scripts/check_contract.py` and
`templates/route-manifest.json`. This release is therefore not described as a
metadata-only promotion.

The version-scoped maintainer decision waives exactly two external assurances:

- uncontaminated live Tier-1/Tier-2 baseline/candidate dogfood;
- an independent GitHub reviewer bound to the exact stable commit.

Neither item is represented as completed evidence. GitHub-verified annotated
candidate and stable tags, candidate ancestry and tag-object binding, exact
SHA-256 bindings for both policy-amendment files, exact-release-SHA CI, source
archive, SHA-256 manifest, extracted-tree replay, independent archive
reproduction, and provenance attestation remain non-waivable.

## Downloads

GitHub provides the standard **Source code (zip)** and **Source code (tar.gz)**
archives for the annotated `v3.3.0` tag. The release workflow also produces a
versioned source archive, SHA-256 checksum, and artifact metadata record.

**Full changelog:** [v3.2.1...v3.3.0](https://github.com/d-init-d/d-research-skill/compare/v3.2.1...v3.3.0) ·
[Detailed candidate notes](release-v3.3.0-rc.1.md)
