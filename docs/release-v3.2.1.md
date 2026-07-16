D Research v3.2.1 is a focused production release that upgrades three optional
capabilities—semantic retrieval, bibliographic export, and language detection—while
preserving the read-only research contract and dependency-free core.

> **Upgrade at a glance:** production-capable local semantic search, richer BibTeX
> output, stronger offline language detection, no workspace migration, and no new
> mandatory runtime dependency.

## Highlights

- **Production-capable semantic retrieval** — The default `auto` backend prefers an
  installed `sentence-transformers` model and falls back to deterministic
  `local-hashing`. The stub backend is now explicit and test-only.
- **Richer citation export** — Validated metadata sidecars can emit conservative
  `@article`, `@book`, and `@inproceedings` entries while retaining safe `@misc`
  fallback behavior. Structured personal names and literal corporate contributors
  preserve their intended identity.
- **Better language detection** — Deterministic local `langdetect` and built-in
  trigram backends improve multilingual routing without remote requests.
- **Offline production-backend coverage** — The optional semantic and language
  backends are exercised on Python 3.10 and 3.12 without downloading model weights.

## Compatibility and upgrade

- **Python:** 3.10 or newer
- **Node.js:** 18 or newer
- Existing research plans, evidence ledgers, routes, and install paths require no
  migration.
- Core helpers remain dependency-free. Install optional trained semantic and language
  backends only when needed:

```bash
python -m pip install -e ".[embeddings,language-detection]"
```

For an existing Git checkout:

```bash
git fetch --tags
git checkout v3.2.1
```

## Verification

- Skill validation, Ruff, Python compilation, Node syntax, and all non-promotion
  helper tests passed.
- All 27 adversarial acceptance scenarios passed.
- All 14 real-browser Chromium smoke groups passed.
- Package validation passed with the frozen 199-path package boundary.
- Dependency audit reported 0 vulnerabilities.
- The stable tree contains no executable, dependency, workflow, route, or package-path
  drift from the audited `v3.2.1-rc.2` candidate.

Live dogfood retained 128 canonical baseline/candidate bundles under one Grok Build
`0.2.101` / `grok-4.5` configuration. Every task completed or produced its expected
policy refusal; no task failed or remained not-run.

| Gate | v3.2.0 baseline | v3.2.1-rc.2 candidate | Verdict |
|---|---:|---:|---|
| Tier-1 strict passes | 2 / 12 | 2 / 12 | **SAME** |
| Tier-2 strict passes | 6 / 52 | 6 / 52 | **SAME** |

The complete raw-run and score evidence remains available in
[`release-evidence/v3.2.1`](https://github.com/d-init-d/d-research-skill/tree/v3.2.1/release-evidence/v3.2.1).

## Downloads

GitHub provides the standard **Source code (zip)** and **Source code (tar.gz)**
archives generated from the signed `v3.2.1` tag.

<details>
<summary>Release assurance and maintainer publication note</summary>

The stable tag is an annotated, GitHub-verified SSH-signed tag bound to commit
`dc07d4902361ddf15ff0dd093faa0784b2fd47ab` and tag object
`4f797f0cb0f75539edfc9bc9332ca4dd041e881c`. The promoted executable candidate is
`520915764a97d717aaf4682e02b8aae5dc511d2f` (`v3.2.1-rc.2`).

At the maintainer's explicit direction, publication proceeded without waiting for an
independent GitHub review or `reviewer-signoff.json`. No reviewer sign-off, custom
release archive/checksum, or green stable-promotion provenance attestation is claimed.
The live dogfood and technical verification artifacts are retained for audit, but the
independent-review gate was not treated as a publication blocker.

Audit trail: [release PR #14](https://github.com/d-init-d/d-research-skill/pull/14) ·
[tag workflow](https://github.com/d-init-d/d-research-skill/actions/runs/29506701529)

</details>

**Full changelog:** [v3.2.0...v3.2.1](https://github.com/d-init-d/d-research-skill/compare/v3.2.0...v3.2.1) ·
[Detailed candidate notes](https://github.com/d-init-d/d-research-skill/blob/v3.2.1/docs/release-v3.2.1-rc.2.md)
