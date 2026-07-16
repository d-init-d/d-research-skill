# D Research v3.2.1-rc.2

## v3.2.1-rc.2 Release Notes

D Research v3.2.1-rc.2 supersedes rc.1 with a release-assurance correction
discovered by the first live candidate-tag run. The skill behavior, helper
implementations, dependency graph, evidence-ledger schema, and read-only
research contract remain unchanged from rc.1.

## What changed since rc.1

- The default-branch provenance workflow now reads the workflow-run webhook
  from GitHub Actions' guaranteed `GITHUB_EVENT_PATH` environment variable.
- The previous expression-derived alias could resolve to an empty string in a
  live `workflow_run`, causing independent artifact selection to fail before
  checksum, tag-signature, archive-reproduction, and provenance checks ran.
- The dynamic contract and its mutation self-test now reject that alias and
  require both webhook validation stages to use `GITHUB_EVENT_PATH` directly.
- Candidate metadata, documentation, and the frozen stable-promotion contract
  now bind the release line to `v3.2.1-rc.2`.

The correction does not weaken any gate. The tag-triggered archive workflow
remains read-only, while OIDC and attestation write permissions remain confined
to the default-branch verifier after it independently selects the exact
upstream artifact.

## Candidate scope

The production-capable optional upgrades introduced in rc.1 are retained:

- semantic retrieval defaults to an offline `auto` path that prefers local
  `sentence-transformers` and otherwise uses deterministic `local-hashing`;
- validated metadata sidecars enable conservative `@article`, `@book`, and
  `@inproceedings` export with safe `@misc` fallback;
- language detection supports deterministic local `langdetect` and a stdlib
  trigram backend without adding a mandatory dependency;
- CI exercises the real optional backends offline across the supported runtime
  matrix.

## Compatibility

Python 3.10 or newer and Node.js 18 or newer remain supported. Existing
research-plan workspaces, evidence ledgers, routes, and install paths require no
migration. No mandatory runtime dependency was added.

## Stable promotion gate

Stable v3.2.1 must be promoted from this exact candidate and requires:

1. Complete live Tier-1 and Tier-2 baseline/candidate dogfood under one
   identical runtime, model, tool configuration, and evaluator binding, with no
   failed or not-run tasks and all frozen comparison thresholds satisfied.
2. A GitHub-verified annotated `v3.2.1-rc.2` tag, exact-SHA CI for the candidate
   and metadata-only stable commit, and pinned ancestry from v3.2.0.
3. Schema-1.2 promotion evidence recomputed from canonical schema-2.1 raw run
   bundles and bound to every score artifact by SHA-256.
4. An independent trusted GitHub `APPROVED` review on the exact stable commit,
   plus a reviewer sign-off bound to the promotion-manifest digest.
5. A metadata-only RC-to-stable transition, verified source archive and
   checksum, extracted-tree replay, independently reproduced archive, and
   GitHub build-provenance attestation.

Any executable, dependency, workflow, route, or package-path change after this
candidate is dogfooded requires another release candidate and a complete rerun.

## Verification status

This document freezes the candidate contract; it does not pre-claim dogfood,
review, CI, archive, or provenance results. Those results are reported only
after the exact artifacts and GitHub checks exist.
