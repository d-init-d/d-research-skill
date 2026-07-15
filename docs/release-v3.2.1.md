# D Research v3.2.1

## v3.2.1 Release Notes

D Research v3.2.1 promotes the production-quality semantic retrieval,
bibliographic export, and language-detection upgrades frozen in
v3.2.1-rc.1. The executable candidate, dependency graph, workflow contract,
and package path manifest must remain unchanged during stable promotion.

## Highlights

- Local `sentence-transformers` is the default semantic retrieval path;
  missing production dependencies fail closed instead of silently selecting a
  test stub.
- Validated JSON sidecars enable conservative `@article`, `@book`, and
  `@inproceedings` exports while preserving safe `@misc` fallback behavior.
- Deterministic local `langdetect` and stdlib trigram backends improve language
  detection without adding a mandatory dependency or remote request.

## Compatibility and upgrade notes

Python 3.10 or newer and Node.js 18 or newer remain supported. Existing
research-plan workspaces and evidence ledgers require no migration. Semantic
retrieval users should install `.[embeddings]`; deterministic test fixtures
must explicitly select `--backend stub`.

## Release assurance

This document is frozen into the candidate package so stable promotion cannot
add a new package path. The metadata-only stable commit may record evidence
available before that commit is reviewed, including the exact candidate
commit, annotated candidate tag-object SHA, and live Tier-1/Tier-2 results.
Evidence that necessarily exists only after the stable commit or tag—exact-SHA
CI for both candidate and stable commits, the independent GitHub review,
archive replay, checksum, and provenance—is verified by the release workflow
and recorded in the published GitHub Release.
Until those gates pass, v3.2.1-rc.1 remains the latest truthful release claim.

See [`release-v3.2.1-rc.1.md`](release-v3.2.1-rc.1.md) for the complete frozen
candidate scope and promotion requirements.
