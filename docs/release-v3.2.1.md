# D Research v3.2.1

## v3.2.1 Release Notes

D Research v3.2.1 is the stable production release of the optional semantic-
retrieval, bibliographic-export, and language-detection upgrades frozen in
v3.2.1-rc.2. The stable tree promotes that exact candidate without executable-
code, dependency, workflow, route, or package-path drift.

## Maintainer-directed publication

The maintainer explicitly directed publication after the completed technical
test and live-dogfood runs without waiting for the independent-review gate.
No reviewer approval or `reviewer-signoff.json` is claimed or manufactured.
As a result, this GitHub Release is a maintainer-published build rather than a
contract-compliant `live_evidence` promotion. The dogfood artifacts remain
included for audit, but independent review was not treated as a publication
blocker.

## Highlights

- Semantic retrieval now defaults to an offline `auto` path that prefers an
  installed `sentence-transformers` backend and otherwise uses deterministic
  `local-hashing`. The stub backend remains available only through explicit
  test configuration.
- Validated JSON metadata sidecars enable conservative `@article`, `@book`,
  and `@inproceedings` BibTeX exports while preserving safe `@misc` fallback.
  Structured personal names and literal corporate authors/editors retain their
  intended identity.
- Deterministic local `langdetect` and stdlib trigram backends improve language
  detection without adding a mandatory dependency or making a remote request.
- CI exercises the real optional semantic and language backends offline across
  the supported Python matrix, including a generated local embedding model
  that requires no downloaded weights.
- Stable promotion recomputes every score from canonical schema-2.1 raw task
  bundles instead of trusting submitted summaries. Prompts, outputs, ledgers,
  runtime/model/tool bindings, commit bindings, and thresholds stay auditable.

## Compatibility and upgrade notes

Python 3.10 or newer and Node.js 18 or newer remain supported. Existing
research-plan workspaces, evidence ledgers, routes, and install paths require
no migration. Semantic retrieval remains dependency-free through
`local-hashing`; install `.[embeddings]` for trained semantic similarity.
Deterministic legacy fixtures must explicitly select `--backend stub`.

## Candidate provenance

The promoted candidate commit is
`520915764a97d717aaf4682e02b8aae5dc511d2f`. Git tag object
`fd309e47c9681a391621bf7b842893d5a2d15ab0` binds the GitHub-verified,
SSH-signed annotated `v3.2.1-rc.2` tag to that exact tree.

Before stable preparation, candidate exact-SHA CI, source-archive/checksum
replay, independent archive reproduction, and GitHub build-provenance
attestation passed. The RC archive SHA-256 is
`3e8b29c6662a790e81310bb177776c0d7225612567bde19aa31d7850991245bd`.

## Live dogfood results

Promotion evidence contains exactly 128 canonical run bundles: 12 Tier-1 and
52 Tier-2 tasks for both the v3.2.0 baseline and the v3.2.1-rc.2 candidate.
Every bundle binds its rendered prompt, raw output, evidence ledger, runtime,
model, tool configuration, skill commit, evaluator-harness commit, and
timestamps.

| Gate | v3.2.0 baseline | v3.2.1-rc.2 candidate | Verdict |
|---|---:|---:|---|
| Tier-1 strict passes | 2 / 12 | 2 / 12 | **SAME** |
| Tier-1 mean recall | 0.65 | 0.65 | unchanged |
| Tier-1 mean accuracy | 0.64 | 0.64 | +0.00 (rounded) |
| Tier-2 strict passes | 6 / 52 | 6 / 52 | **SAME** |
| Tier-2 mean recall | 0.61 | 0.62 | +0.02 |
| Tier-2 mean accuracy | 0.71 | 0.75 | +0.04 |

Both tiers have zero failed runs, zero not-run tasks, zero contract-defined
regressions, and zero safety regressions. Under the frozen comparison policy,
Tier-1 metric drops count as regressions only when they exceed 0.20; Tier-2
regressions are pass or safety transitions. Per-task metric movement remains
visible in the score artifacts: DF-010 has a 0.20 Tier-1 accuracy drop, and
FB-017, FB-039, FB-042, FB-048, and FB-049 have negative Tier-2 metric deltas;
none crosses its tier's frozen regression rule. Tier 1 records one partial
improvement, and Tier 2 records ten partial improvements. “Strict passes” means
a task met every applicable scoring threshold; all 128 baseline/candidate runs
completed or produced the expected policy refusal and remain auditable.

All runs used Grok Build `0.2.101` with `grok-4.5` and one tool-configuration
hash,
`sha256:45b1ed81cc973de656f5d1ce090fd157817111a86b6bcb6733a8ba00f779e300`.
Targeted reruns used the identical prompt, model, runtime, evaluator, and frozen
thresholds; no benchmark, policy, or scoring rule changed. The SHA-256 of the
schema-1.2 promotion manifest is
`sha256:5f77a1de7a741bedc193b973a4d6bd2de64a0e55cd09bae6044c6b2c270cb611`.

## Stable release assurance

The metadata-only stable commit carries the canonical Tier-1 and Tier-2 live
dogfood bundles, recomputed schema-2.1 scores, and schema-1.2 promotion
evidence. The release contract requires one identical runtime, model, tool
configuration, and evaluator binding across baseline and candidate runs; zero
failed or not-run tasks; frozen regression thresholds; and an independent
review of live-run origin, raw artifacts, and score recomputation.

The tag-triggered archive workflow remains read-only. Under the normal
contract, GitHub provenance is issued only after the default-branch verifier
revalidates the signed tag, artifact metadata, checksum, reproduced archive,
exact-SHA CI, and repository-bound review. This maintainer-directed publication
claims only the signed stable tag, the tests reported above, and the included
raw evidence; it does not claim an independent reviewer sign-off or a green
stable-promotion attestation.

See [`release-v3.2.1-rc.2.md`](release-v3.2.1-rc.2.md) for the complete frozen
candidate scope and promotion contract.
