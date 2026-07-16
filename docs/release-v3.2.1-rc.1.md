# D Research v3.2.1-rc.1

## v3.2.1-rc.1 Release Notes

D Research v3.2.1-rc.1 upgrades three previously fallback- or test-oriented
helper paths—semantic retrieval, bibliographic export, and language detection—
to production-capable optional paths while preserving the canonical
evidence-ledger schema and read-only research contract.

This build remains prerelease metadata (`Development Status :: 4 - Beta`). It
freezes the executable candidate that must complete live dogfood, independent
review, exact-SHA CI, and verified-tag assurance before stable promotion.

## Production-capable optional upgrades

- **Semantic retrieval:** `index` and direct ledger queries now default to an
  `auto` backend that selects local `sentence-transformers` when installed and
  otherwise uses the deterministic built-in `local-hashing` backend. Auto
  never selects a remote backend or the deterministic test stub; the latter
  remains available only through explicit `--backend stub` selection. Strict
  JSON/vector validation rejects ambiguous indexes, malformed backend output,
  and blank queries; blank local-hashing documents use a zero vector.
- **Citation export:** optional JSON metadata sidecars add conservative
  `@article`, `@book`, and `@inproceedings` BibTeX output without changing the
  evidence-ledger schema. DOI, URL, and title/year matching are deterministic;
  duplicate or non-finite JSON values and conflicting DOI identities fail
  closed, while incomplete or unsafe metadata falls back to the existing
  `@misc` representation. Explicit `literal` names preserve corporate authors
  and editors as organizations, including structured Crossref/DataCite
  enrichment, and `accessed` is normalized to
  `date_accessed` without silently accepting conflicting aliases.
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
- The tag workflow has read-only validation/build permissions. OIDC and
  attestation write access exist only in a default-branch `workflow_run`
  workflow that independently verifies the signed tag, artifact metadata,
  checksum, and reproduced archive without executing tagged repository code.
- CI installs the optional `embeddings` and `language-detection` extras in
  dedicated Python 3.10 and 3.12 jobs, exercises the actual `sentence-transformers`
  library with a generated local model, and checks deterministic `langdetect`
  behavior without model downloads or network access.
- The development and CI Ruff pin is synchronized at `0.15.21`, and the
  contract check rejects future pin drift.
- Windows evidence paths normalize both the repository root and resolved
  artifacts before containment checks, including 8.3 temporary-directory aliases.
- The Node-to-Python launcher prefers the active PATH interpreter before the
  global Windows `py` launcher, preserving virtual-environment and CI matrix intent.
- The source-archive workflow now derives the dogfood baseline from the frozen
  route manifest, allowing each release line to bind the correct stable tag.
- The workflow verifies baseline-to-candidate ancestry before accepting any
  release evidence and rechecks successful full CI for both the exact
  dogfooded candidate SHA and the later metadata-only stable SHA.
- Schema-1.2 promotion evidence binds the four baseline/candidate Tier-1/Tier-2
  score artifacts to canonical per-task run bundles. The contract verifies the
  raw prompt, output, and ledger hashes; exact task coverage and canonical
  filenames; rendered prompt bytes; the canonical 23-column ledger header;
  unique run/session identities; UTC-normalized timestamp pairs; exact
  commit/version/runtime bindings; an evaluator harness pinned to the candidate
  commit; frozen thresholds; and a full score recomputation from raw runs.
- Independent sign-off binds the exact promotion-manifest SHA-256 and explicitly
  attests that the reviewer verified live-run origin, reviewed raw artifacts,
  and reviewed score recomputation. Machine validation proves artifact
  consistency; it does not manufacture proof that an agent ran live.
- The v3.2.0 maintainer waiver is not reused. This release line restores the
  default `live_evidence` promotion mode.

## Compatibility and upgrade notes

- Python 3.10 or newer and Node.js 18 or newer remain supported.
- No new mandatory Python dependency is introduced. Install
  `.[embeddings]` for trained semantic similarity or
  `.[language-detection]` for `langdetect`.
- Existing semantic commands that omitted `--backend` continue to run. Without
  `sentence-transformers`, they use deterministic lexical feature hashing;
  install the production extra for model-based similarity, or pass
  `--backend stub` only when test-fixture behavior is intentional.
- When `langdetect` is installed, language rankings may differ from the stdlib
  trigram detector; the command's JSON output shape is unchanged.
- Existing evidence ledgers, research-plan workspaces, route names, and
  browser safety invariants require no migration.

## Verification status

This document records the frozen verification contract, not a claim that the
candidate has already completed it. Before tagging, the final candidate commit
must pass locked dependency installation; Node and Python self-tests, including
Python 3.10 and 3.12; all 27 adversarial acceptance scenarios; all 14 real local
Chromium smoke groups; the package-boundary and dry-pack checks; Ruff and
bytecode compilation; internal-reference, decision-tree, contract, and strict
bench checks; deterministic quality and promotion anti-spoof suites;
actionlint; dependency audit; an extracted archive replay without `.git`
metadata; and the real optional-backend self-tests. Exact-SHA CI remains
authoritative for the supported Python, Node, Ubuntu, and Windows matrix.
Results belong in the tagged prerelease and later stable GitHub Release only
after they exist.

## Stable promotion gate

Stable v3.2.1 requires all of the following against baseline `v3.2.0` and this
exact `v3.2.1-rc.1` candidate:

1. Complete live Tier-1 and Tier-2 baseline/candidate runs under one identical
   runtime, model, tool, and evaluator configuration, with `not_run = 0`,
   `failed = 0`, at least one factual pass per tier, and strict
   run-to-score-to-promotion timestamp ordering.
2. No Tier-1 regression, no Tier-2 safety regression, and no reduction in the
   Tier-2 passed-task count.
3. A GitHub-verified annotated candidate tag bound to its exact tag object,
   plus successful full CI for both the exact candidate SHA and the later
   metadata-only stable SHA. The annotated historical `v3.2.0` baseline tag is
   separately pinned to its exact legacy tag-object SHA and is not falsely
   described as GitHub-verified.
4. A strict schema-1.2 promotion manifest with SHA-256-bound score artifacts,
   canonical raw-run bundles, deterministic score recomputation, and a
   SHA-256-bound independent reviewer sign-off. The reviewer scope must attest
   live-run origin, raw-artifact review, and score-recomputation review.
5. An independent `APPROVED` GitHub pull-request review on the exact stable
   commit from a trusted repository association.
6. A metadata-only RC-to-stable transition, verified source archive and
   checksum, extracted-tree replay, and GitHub build-provenance attestation.

Any executable, dependency, workflow, route, or package-path change after the
candidate is dogfooded requires a new RC and a complete rerun.

## What this RC does not claim

- It is not the stable v3.2.1 release.
- It does not claim live dogfood or independent GitHub review before those
  artifacts exist and pass the frozen contract.
- It does not treat the test-only semantic stub or dependency-free
  `local-hashing` fallback as equivalent to a trained semantic model, nor the
  stdlib trigram detector as equivalent to `langdetect`.
