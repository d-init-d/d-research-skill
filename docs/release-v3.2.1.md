## Highlights

D Research v3.2.1 makes research workflows easier to deploy, more reliable across
languages, and better suited to publication-quality output.

- **More relevant local search** — Use a production-capable semantic backend when
  available, with a fast deterministic fallback that works without additional services.
- **Cleaner bibliographies** — Export richer BibTeX records for articles, books, and
  conference papers while preserving safe fallback behavior for incomplete metadata.
- **More reliable multilingual research** — Improve language detection while keeping
  processing fully local.
- **Seamless upgrade** — Keep existing research plans, evidence ledgers, routes, and
  installation paths. No migration or new mandatory dependency is required.

## What’s improved

### Semantic retrieval

- The default `auto` mode uses an installed `sentence-transformers` model when available.
- Environments without the optional model backend automatically use deterministic
  `local-hashing`; the test stub is selected only through explicit configuration.
- Model loading and encoding failures now return controlled, actionable diagnostics.
- Stricter index validation rejects malformed vectors, duplicate keys, non-finite values,
  invalid entries, and blank queries before retrieval.

### Citation export

- Validated metadata sidecars support conservative `@article`, `@book`, and
  `@inproceedings` BibTeX entries.
- Structured personal names and literal corporate authors or editors retain their
  intended identity in BibTeX and CSL output.
- Conflicting DOI identities and ambiguous metadata fail closed instead of producing a
  misleading citation.
- Incomplete rich metadata continues to fall back safely to `@misc`.

### Language detection

- Add deterministic local `langdetect` through the optional `language-detection` extra.
- Keep the built-in trigram detector as an offline, dependency-free fallback.
- Preserve explicit backend selection for repeatable workflows and test fixtures.

## Upgrade

No workspace migration is required.

Update an existing Git checkout:

```bash
git fetch --tags
git checkout v3.2.1
```

Install D Research as a new agent skill:

```bash
git clone --branch v3.2.1 --depth 1 \
  https://github.com/d-init-d/d-research-skill.git \
  .agents/skills/d-research
```

Install the production-quality optional backends only when needed:

```bash
python -m pip install -e ".[embeddings,language-detection]"
```

## Compatibility

| Component | Support |
|---|---|
| Python | 3.10 or newer |
| Node.js | 18 or newer |
| Browser runtime | Playwright 1.61.1 (locked) |
| Existing workspaces | No migration required |
| Core runtime dependencies | No new mandatory dependency |

## Quality and security

- Candidate exact-SHA CI passed across Python 3.10–3.12 and Node.js 18/20/22.
- All 27 adversarial acceptance scenarios passed.
- All 14 real-browser Chromium smoke groups passed on local fixtures.
- Real optional-backend tests passed on Python 3.10 and 3.12 without model downloads.
- Package validation passed with the frozen 199-path boundary.
- Dependency audit reported 0 vulnerabilities.
- The stable release contains no executable, dependency, workflow, route, or package-path
  drift from the tested `v3.2.1-rc.2` candidate.
- The annotated `v3.2.1` tag is SSH-signed and verified by GitHub.

## Downloads

GitHub provides the standard **Source code (zip)** and **Source code (tar.gz)** archives
generated from the signed `v3.2.1` tag.

<details>
<summary>Technical release assurance</summary>

The stable tag is bound to commit
`dc07d4902361ddf15ff0dd093faa0784b2fd47ab` and tag object
`4f797f0cb0f75539edfc9bc9332ca4dd041e881c`. The executable candidate is
`520915764a97d717aaf4682e02b8aae5dc511d2f` (`v3.2.1-rc.2`).

Live dogfood retained 128 canonical baseline/candidate bundles under one Grok Build
`0.2.101` / `grok-4.5` configuration. Every task completed or produced its expected
policy refusal; no task failed or remained not-run. Tier 1 and Tier 2 both produced a
`SAME` promotion verdict.

At the maintainer's direction, publication proceeded without waiting for an independent
GitHub review or `reviewer-signoff.json`. No independent reviewer sign-off, custom release
archive/checksum, or green stable-promotion provenance attestation is claimed. This
assurance limitation does not alter the shipped executable tree, which remains identical
to the tested release candidate.

Audit trail: [release PR #14](https://github.com/d-init-d/d-research-skill/pull/14) ·
[tag workflow](https://github.com/d-init-d/d-research-skill/actions/runs/29506701529) ·
[raw evaluation evidence](https://github.com/d-init-d/d-research-skill/tree/v3.2.1/release-evidence/v3.2.1)

</details>

**Full changelog:** [v3.2.0...v3.2.1](https://github.com/d-init-d/d-research-skill/compare/v3.2.0...v3.2.1) ·
[Detailed candidate notes](https://github.com/d-init-d/d-research-skill/blob/v3.2.1/docs/release-v3.2.1-rc.2.md)
