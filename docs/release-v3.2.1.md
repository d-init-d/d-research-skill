D Research v3.2.1 is a focused, drop-in production upgrade for semantic retrieval,
bibliographic export, and language detection. It ships the implementation frozen in
`v3.2.1-rc.2` without executable, dependency, workflow, route, or package-path drift.

> **Ready to ship:** stronger local semantic search, richer BibTeX output, better
> multilingual routing, no workspace migration, and no new mandatory runtime
> dependency.

## Highlights

- **Production-capable semantic retrieval** — Automatically use a local
  `sentence-transformers` model when available, with deterministic built-in retrieval
  as the dependency-free fallback.
- **Richer citation export** — Produce validated `@article`, `@book`, and
  `@inproceedings` entries while preserving the safe `@misc` fallback.
- **Better multilingual routing** — Add deterministic local `langdetect` and trigram
  backends without introducing a remote request path.
- **Safe, compatible upgrade** — Preserve existing research plans, evidence ledgers,
  routes, install paths, and the read-only research contract.
- **Reproducible delivery** — Retain a frozen package boundary, signed release tag,
  complete raw evaluation artifacts, and cross-platform technical verification.

## What’s new in v3.2.1

### Semantic retrieval

- `auto` now prefers an installed `sentence-transformers` backend and otherwise selects
  deterministic `local-hashing`.
- The deterministic stub remains available only through explicit `--backend stub`
  selection for fixtures and tests.
- Model loading and encoding failures return controlled, actionable diagnostics instead
  of escaping as Python tracebacks.
- Semantic indexes reject duplicate keys, non-finite values, malformed vectors, invalid
  entries, and blank queries before retrieval.

### Citations and bibliographies

- Validated JSON metadata sidecars support conservative `@article`, `@book`, and
  `@inproceedings` exports.
- Structured personal names and literal corporate authors or editors retain their
  intended identity in BibTeX and CSL output.
- Conflicting DOI identities, duplicate JSON keys, non-finite values, and ambiguous
  metadata fail closed.
- Incomplete rich metadata continues to fall back safely to `@misc`.

### Language detection

- Add deterministic local `langdetect` for installations that opt into the
  `language-detection` extra.
- Keep the built-in trigram detector as an offline, dependency-free fallback.
- Preserve explicit backend selection for reproducible workflows and fixtures.

### Release engineering

- Exercise the real optional semantic and language backends offline on Python 3.10 and
  3.12 without downloading model weights.
- Preserve the frozen 199-path package boundary and locked Playwright dependency.
- Promote the exact `v3.2.1-rc.2` executable tree; stable changes are limited to release
  metadata, documentation, and audit evidence.

## Compatibility and upgrade

- **Python:** 3.10 or newer
- **Node.js:** 18 or newer
- **Browser runtime:** Playwright 1.61.1 (locked)
- Existing research workspaces and evidence ledgers require no migration.
- Core helpers remain dependency-free.

For an existing Git checkout:

```bash
git fetch --tags
git checkout v3.2.1
```

For a fresh agent-skill install:

```bash
git clone --branch v3.2.1 --depth 1 \
  https://github.com/d-init-d/d-research-skill.git \
  .agents/skills/d-research
```

Install the production-quality optional backends only when needed:

```bash
python -m pip install -e ".[embeddings,language-detection]"
```

## Verification

- Candidate exact-SHA CI passed across Python 3.10–3.12 and Node.js 18/20/22.
- All 27 adversarial acceptance scenarios passed.
- All 14 real-browser Chromium smoke groups passed on local fixtures.
- Real optional-backend tests passed on Python 3.10 and 3.12 without model downloads.
- Package validation passed with the frozen 199-path boundary.
- Dependency audit reported 0 vulnerabilities.
- The annotated `v3.2.1` tag is SSH-signed and verified by GitHub.

## Downloads

GitHub provides the standard **Source code (zip)** and **Source code (tar.gz)**
archives generated from the signed `v3.2.1` tag.

<details>
<summary>Release assurance and residual risk</summary>

The stable tag is bound to commit
`dc07d4902361ddf15ff0dd093faa0784b2fd47ab` and tag object
`4f797f0cb0f75539edfc9bc9332ca4dd041e881c`. The executable candidate is
`520915764a97d717aaf4682e02b8aae5dc511d2f` (`v3.2.1-rc.2`).

Live dogfood retained 128 canonical baseline/candidate bundles under one Grok Build
`0.2.101` / `grok-4.5` configuration. All tasks completed or produced their expected
policy refusal; no task failed or remained not-run. Tier 1 and Tier 2 both produced a
`SAME` promotion verdict.

At the maintainer's explicit direction, publication proceeded without waiting for an
independent GitHub review or `reviewer-signoff.json`. Consequently, no independent
reviewer sign-off, custom release archive/checksum, or green stable-promotion provenance
attestation is claimed. This assurance limitation does not alter the shipped executable
tree, which remains identical to the tested release candidate.

Audit trail: [release PR #14](https://github.com/d-init-d/d-research-skill/pull/14) ·
[tag workflow](https://github.com/d-init-d/d-research-skill/actions/runs/29506701529) ·
[raw evaluation evidence](https://github.com/d-init-d/d-research-skill/tree/v3.2.1/release-evidence/v3.2.1)

</details>

**Full changelog:** [v3.2.0...v3.2.1](https://github.com/d-init-d/d-research-skill/compare/v3.2.0...v3.2.1) ·
[Detailed candidate notes](https://github.com/d-init-d/d-research-skill/blob/v3.2.1/docs/release-v3.2.1-rc.2.md)
