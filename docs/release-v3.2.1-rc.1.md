# D Research v3.2.1-rc.1

## v3.2.1-rc.1 Release Notes

D Research v3.2.1-rc.1 upgrades three previously fallback- or test-oriented
helper paths—semantic retrieval, bibliographic export, and language detection—
to production-quality defaults while preserving the canonical evidence-ledger
schema and read-only research contract.

This build remains prerelease metadata (`Development Status :: 4 - Beta`). It
freezes the executable candidate that must complete live dogfood, independent
review, exact-SHA CI, and verified-tag assurance before stable promotion.

## Production-quality upgrades

- **Semantic retrieval:** `index` and direct ledger queries now default to an
  `auto` backend that selects local `sentence-transformers`. If the production
  backend is unavailable, the command fails closed with installation guidance;
  the deterministic stub remains available only through explicit
  `--backend stub` selection for tests and fixtures.
- **Citation export:** optional JSON metadata sidecars add conservative
  `@article`, `@book`, and `@inproceedings` BibTeX output without changing the
  evidence-ledger schema. DOI, URL, and title/year matching are deterministic;
  conflicts fail closed, and incomplete or unsafe metadata falls back to the
  existing `@misc` representation.
- **Language detection:** `translate.py detect` supports deterministic local
  `langdetect` through the `language-detection` extra and an explicit stdlib
  trigram backend. Automatic selection stays offline and does not enable a
  remote translation service.

See [semantic retrieval](../references/semantic-retrieval.md),
[citation management](../references/citation-management.md), and the
[translation adapter](../adapters/translation.md) for the complete contracts.

## Reliability and release tooling

- Release artifacts use SHA-pinned `actions/upload-artifact@v7.0.1` and
  `actions/attest-build-provenance@v4.1.1` actions.
- The development and CI Ruff pin is synchronized at `0.15.21`, and the
  contract check rejects future pin drift.
- The source-archive workflow now derives the dogfood baseline from the frozen
  route manifest, allowing each release line to bind the correct stable tag.
- The v3.2.0 maintainer waiver is not reused. This release line restores the
  default `live_evidence` promotion mode.

## Compatibility and upgrade notes

- Python 3.10 or newer and Node.js 18 or newer remain supported.
- No new mandatory Python dependency is introduced. Install
  `.[embeddings]` for the default semantic backend or
  `.[language-detection]` for `langdetect`.
- Existing semantic commands that omitted `--backend` may now fail when
  `sentence-transformers` is not installed. Use the production extra, or pass
  `--backend stub` only when deterministic test behavior is intentional.
- When `langdetect` is installed, language rankings may differ from the stdlib
  trigram detector; the command's JSON output shape is unchanged.
- Existing evidence ledgers, research-plan workspaces, route names, and
  browser safety invariants require no migration.

## Verification

The candidate passed the complete pre-commit local release suite: locked
dependency installation; Node and Python self-tests; full Python 3.10 and 3.12
self-test runs; 27/27 adversarial acceptance scenarios; all 14 real local
Chromium smoke groups; a 198-file package-boundary check; Ruff and bytecode
compilation; internal-reference, decision-tree, contract, and strict-bench
checks; deterministic quality evaluation 3/3; promotion anti-spoof 46/46;
actionlint; and an npm audit with zero vulnerabilities. Extracted archive
replay without `.git` metadata is repeated on the committed candidate before
tagging. Exact-SHA CI remains authoritative for the supported Python, Node,
Ubuntu, and Windows matrix.

## Stable promotion gate

Stable v3.2.1 requires all of the following against baseline `v3.2.0` and this
exact `v3.2.1-rc.1` candidate:

1. Complete live Tier-1 and Tier-2 baseline/candidate runs under one identical
   runtime, model, tool, and evaluator configuration, with `not_run = 0`.
2. No Tier-1 regression, no Tier-2 safety regression, and no reduction in the
   Tier-2 passed-task count.
3. A GitHub-verified annotated candidate tag bound to its exact tag object,
   plus successful full CI for both the exact candidate SHA and the later
   metadata-only stable SHA.
4. A promotion manifest with SHA-256-bound score artifacts and an independent
   `APPROVED` GitHub pull-request review on the exact stable commit.
5. A metadata-only RC-to-stable transition, verified source archive and
   checksum, extracted-tree replay, and GitHub build-provenance attestation.

Any executable, dependency, workflow, route, or package-path change after the
candidate is dogfooded requires a new RC and a complete rerun.

## What this RC does not claim

- It is not the stable v3.2.1 release.
- It does not claim live dogfood or independent GitHub review before those
  artifacts exist and pass the frozen contract.
- It does not treat the test-only semantic stub or the stdlib trigram detector
  as equivalent to their production backends.
