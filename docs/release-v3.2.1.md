# D Research v3.2.1

## v3.2.1 Release Notes

D Research v3.2.1 promotes the production-capable optional semantic-retrieval,
bibliographic-export, and language-detection upgrades frozen in v3.2.1-rc.1.
The executable candidate, dependency graph, workflow contract, and package
path manifest must remain unchanged during stable promotion.

## Highlights

- Semantic retrieval auto-selects local `sentence-transformers` when installed,
  otherwise using a deterministic built-in `local-hashing` path rather than a
  test stub or remote service.
- Validated JSON sidecars enable conservative `@article`, `@book`, and
  `@inproceedings` exports while preserving safe `@misc` fallback behavior.
  Strict JSON and identity validation rejects ambiguous metadata, while
  explicit literal names correctly preserve corporate authors and editors.
- Deterministic local `langdetect` and stdlib trigram backends improve language
  detection without adding a mandatory dependency or remote request.
- Dedicated CI coverage installs and exercises the real `sentence-transformers`
  and `langdetect` packages offline, without downloading model weights.
- Stable promotion is derived from canonical raw task bundles rather than
  trusting submitted score summaries: prompts, outputs, ledgers, commit/runtime
  bindings, thresholds, and recomputed scores all remain auditable.

## Compatibility and upgrade notes

Python 3.10 or newer and Node.js 18 or newer remain supported. Existing
research-plan workspaces and evidence ledgers require no migration. Semantic
retrieval remains available without optional dependencies through lexical
`local-hashing`; install `.[embeddings]` for trained semantic similarity.
Deterministic legacy test fixtures must explicitly select `--backend stub`.

## Release assurance

This document is frozen into the candidate package so stable promotion cannot
add a new package path. The metadata-only stable commit may record evidence
available before that commit is reviewed, including the exact candidate
commit, annotated candidate tag-object SHA, and live Tier-1/Tier-2 results.
Evidence that necessarily exists only after the stable commit or tag—exact-SHA
CI for both candidate and stable commits, the independent GitHub review,
archive replay, checksum, and provenance—is verified by the release workflow
and recorded in the published GitHub Release.

The tag-triggered workflow is read-only. Provenance is issued only by the
default-branch `release-source-attestation` workflow after it independently
revalidates the signed tag, artifact metadata, checksum, and reproduced archive
without executing code from the tagged tree.

The stable workflow pins the annotated legacy baseline tag object, proves
baseline-to-candidate ancestry, and validates schema-1.2 promotion evidence.
Every submitted score must have no failed/not-run tasks, include factual passes,
obey run-to-score-to-promotion time ordering, reject duplicate instants even
when RFC 3339 offsets differ, pin its evaluator harness to the candidate commit,
and match a deterministic recomputation over the canonical raw run bundle. The
independent sign-off
must bind the exact promotion-manifest SHA-256 while attesting review of live
run origin, raw artifacts, and recomputation. These controls verify the
evidence chain; they do not substitute for the required live runs or reviewer.
Until those gates pass, v3.2.1-rc.1 remains the latest truthful release claim.

See [`release-v3.2.1-rc.1.md`](release-v3.2.1-rc.1.md) for the complete frozen
candidate scope and promotion requirements.
