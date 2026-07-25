# D Research v3.3.0-rc.1

## v3.3.0-rc.1 Release Notes

D Research v3.3.0-rc.1 is a capability-expansion release candidate for
stronger investigative, social, public-data, and self-exposure research. It
widens lawful discovery and analysis through explicit scope, source
admissibility, risk budgets, contradiction search, and output controls. It
does not widen authority to bypass access controls or collect prohibited
personal or secret data.

This build uses prerelease metadata (`Development Status :: 4 - Beta`) and
freezes the executable candidate that stable v3.3.0 must dogfood and promote.

## Stronger research surface

- **Scoped investigative research:** capability tiers distinguish ordinary
  public research, public-role aggregation, authorized self-audit, defensive
  security work, and prohibited requests. Scope, purpose, source classes,
  retention, redaction, resource budgets, and stopping criteria are explicit.
- **Cross-platform social-source research:** every item is classified by the
  speaker's identity, relationship to the claim, whether it is original or a
  repost, content integrity, and independent corroboration. A platform is not
  treated as uniformly official or unofficial.
- **Lead-to-evidence separation:** non-official or unverified material may open
  a lawful discovery path, but consequential claims require appropriate
  corroboration. Main findings, unverified leads, contradictions, and
  prohibited or blocked sources remain visibly separate.
- **Leaked-data handling:** public reporting, authorized-provider corpora,
  user-provided private material, raw-leak leads, and stolen secrets receive
  distinct discovery, evidence, retention, and reporting treatment.
- **Self-exposure audit:** owned identifiers and domains can be checked through
  an authorized provider or public breach reporting after ownership or
  authorization is established. Outputs minimize disclosure and emphasize
  remediation rather than credential recovery or third-party profiling.

## Deterministic policy helper

`scripts/investigation_policy.py` validates a versioned investigation scope
and classifies proposed source use without making a network request. The
matching `templates/investigation-scope.json` records the research mode,
purpose, subject class, authorization, allowed source/data classes, resource
limits, output sections, redactions, retention, and audience.

The package exposes:

```bash
npm run policy:init -- --mode R1 --out investigation-scope.json
npm run policy:check -- --file investigation-scope.json
npm run policy:bind -- --file investigation-scope.json --status self_verified \
  --method provider_native_verification --reviewed-by account-owner \
  --reviewed-at 2026-07-25T00:00:00Z --expires-at 2026-07-28T00:00:00Z
npm run plan:bind-policy -- --file research-plan.json \
  --route self_exposure_audit --scope investigation-scope.json
python scripts/investigation_policy.py self-test
```

The helper is policy-as-code, not proof of legal authority and not an access
grant. Human review remains responsible for context, identity, and
jurisdiction-specific decisions.

The plan gate binds the exact policy bytes to every research and synthesis
task. `report_render.py lint --strict` enforces the four investigative output
partitions and prevents a lead from being cited in main findings. Social
`to-ledger` emits a policy-aware lead by default; explicit main-findings output
is limited to a verified original statement and does not establish every
underlying factual claim.

## Safety and access invariants

The expanded research surface retains hard stops for:

- minors, stalking, harassment, doxxing, precise whereabouts, and private-
  person dossiers;
- pseudonym re-identification and collection of sensitive personal details;
- passwords, tokens, cookies, sessions, private keys, and other stolen
  secrets;
- login, paywall, captcha, rate-limit, robots, or other access-control bypass;
- bulk acquisition, parsing, redistribution, or operational use of raw leaked
  datasets.

Public availability alone does not establish lawful custody, reliability, or
permission to redistribute.

## Compatibility

- Package metadata is `3.3.0-rc.1`; Python project metadata is PEP 440
  `3.3.0rc1`.
- Python 3.10 or newer and Node.js 18 or newer remain supported.
- Playwright remains locked to `1.61.1`.
- Existing evidence ledgers, schema-2.0 research-plan workspaces, and install
  paths require no migration.
- New ledgers use the 37-column v3.3 investigative-policy header; exact
  legacy 14-, 19-, 22-, and 23-column ledgers remain supported without
  rewriting.

## Verification status

This document records the candidate contract, not completed release evidence.
Before tagging, the exact candidate tree must pass locked installation, Node
and Python self-tests, contract and internal-reference checks, strict eval
validation, adversarial acceptance, real local Chromium smoke tests, package
boundary validation, dry-pack inspection, Ruff, bytecode compilation, and
the supported CI runtime/OS matrix.

The v3.3.0 evidence directory is excluded from Git text conversion so Windows
checkout-time EOL rewriting cannot invalidate SHA-256-bound raw run artifacts.
The evidence itself is created only after the candidate is frozen.

## Stable promotion gate

Stable v3.3.0 must promote this exact `v3.3.0-rc.1` candidate against baseline
`v3.2.1` and requires:

1. Complete live Tier-1 and Tier-2 baseline/candidate runs under one identical
   runtime, model, tool configuration, and evaluator binding, with zero failed
   and zero not-run tasks.
2. No Tier-1 regression, no Tier-2 safety regression, and no reduction in the
   Tier-2 passed-task count.
3. A GitHub-verified annotated candidate tag, successful exact-SHA CI, pinned
   ancestry from v3.2.1, and exact tag-object bindings.
4. Schema-1.2 promotion evidence recomputed from canonical schema-2.1 raw run
   bundles and bound to all score artifacts by SHA-256.
5. Independent reviewer sign-off bound to the promotion-manifest digest and a
   trusted GitHub `APPROVED` review on the exact stable commit.
6. A metadata-only RC-to-stable transition, verified source archive and
   checksum, extracted-tree replay, independent archive reproduction, and
   GitHub build-provenance attestation.

Any executable, dependency, workflow, route, or package-path change after
dogfood requires another release candidate and a complete rerun.

## What this RC does not claim

- It is not the stable v3.3.0 release.
- It does not claim live dogfood, independent review, exact-SHA CI, archive
  reproduction, or provenance results before those artifacts exist.
- It does not authorize access-control bypass, raw-leak acquisition, secret
  handling, or third-party self-exposure lookups.
