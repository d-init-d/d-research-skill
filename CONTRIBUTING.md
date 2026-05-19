# Contributing to d-research-skill

This repo is an **agent skill package**: instruction (`SKILL.md`),
references, adapters, helper scripts, templates, and examples. The
intended consumer is an LLM agent or a human researcher using a
markdown-aware agent runtime.

Most contributions will fall into one of five categories. This guide
explains the conventions for each.

## Repository layout

```
SKILL.md                  Entry point + decision tree for agents
AGENTS.md                 Minimal procedure for non-Claude agents
README.md                 Human-readable overview
references/               Long-form reference modules (1 topic each)
adapters/                 Tool-specific procedures (Playwright, fetch, GraphQL, …)
examples/                 Worked walkthroughs
templates/                Drop-in starter files (CSVs, BibTeX, JSON)
scripts/                  Helper scripts (.mjs, .py) — offline self-tests
docs/                     Internal planning / release notes (not user-facing)
.github/workflows/        CI (link check, lint, self-tests)
```

## General rules

1. **Read-only, lawful access.** Every contribution must respect the
   safety boundary defined in
   `references/safety-and-access-policy.md`. No bypass of login,
   paywall, captcha, rate limit, or `robots.txt`.
2. **Offline first.** Scripts must have an offline `self-test`
   subcommand and must not require network for their core operation.
   Optional network features (e.g. CSL download) must be gated by an
   explicit flag and degrade cleanly.
3. **No external runtime dependencies** for the bundled scripts
   beyond what is documented in `package.json` (Playwright) and
   Python stdlib. `citation_render.py` shells out to `pandoc` and
   degrades gracefully when it is missing.
4. **Citations have URLs and dates.** Anywhere the skill produces a
   claim, the underlying evidence ledger must have a `source_url`
   and a `date_accessed`.
5. **Lint and self-test before opening a PR.** Run
   `npm run self-test` (covers Node + Python self-tests +
   internal-ref check + decision-tree audit) and, if you touched a
   Python file, `ruff check scripts/`. Optionally install
   pre-commit (`pip install pre-commit && pre-commit install`)
   so these checks run automatically on every `git commit`.
6. **Never commit roadmap docs.** PLAN-`*`.md files in the repo root
   are local roadmap notes; the pre-commit `no-plan-files` hook
   refuses them. Use a `docs/` page for material that belongs in
   git.

## v3.0 commands at a glance

```bash
# Full self-test chain (Node + Python + bench harness)
npm run self-test

# Python lint
ruff check scripts/

# Bench validation
python scripts/run_dogfood.py validate --file examples/evals/frontier-bench.json
python scripts/run_dogfood.py classes  --file examples/evals/frontier-bench.json
python scripts/bench_harness_check.py check-all --strict
python scripts/bench_harness_check.py orphans \
    --bench    examples/evals/frontier-bench.json \
    --fixtures examples/evals/fixtures/frontier-empty-scores.json

# Documentation graph health
python scripts/check_internal_refs.py
python scripts/check_internal_refs.py --decision-tree

# Evidence ledger lifecycle
python scripts/evidence_ledger.py validate --file evidence-ledger.csv
python scripts/evidence_ledger.py sign     --file evidence-ledger.csv
python scripts/evidence_ledger.py verify   --file evidence-ledger.csv
python scripts/evidence_ledger.py prov-export --file evidence-ledger.csv --out prov.jsonld

# Capture local run metadata (never uploaded)
python scripts/run_metadata.py record --out runs.jsonl --command "npm run self-test"
```


## Adding a reference (`references/<topic>.md`)

A reference file is a self-contained explanation of one topic. It
should:

- Start with a one-paragraph "what this is for" header.
- Use `references/<other>.md` and `templates/<file>` paths verbatim
  for cross-references (no `[link text](path)` form for these — the
  internal-ref checker validates backticked path references).
- End with a `## See also` section listing related references,
  templates, and examples.
- Be linked from `SKILL.md` at the decision point where an agent would
  need it (otherwise the file is an "orphan" and the audit will flag
  it). For example, a new reference at `references/safety-and-access-policy.md`
  is linked from the "Safety boundary" section of `SKILL.md`.

Length guideline: 50–250 lines. Split bigger topics into two refs.

## Adding an adapter (`adapters/<tool>.md`)

An adapter file describes how to use one tool while respecting the
skill's safety boundary. It should:

- State the tool's role in the priority list (default, fallback,
  specialised).
- Document its setup (e.g. `npx playwright install chromium`).
- Document its idiomatic usage with examples.
- State explicitly what the adapter **does not** do (no stealth
  plugins, no captcha bypass, etc.).

## Adding an example (`examples/<scenario>.md`)

A worked example walks through one realistic task end-to-end with
sample inputs, sample outputs, and sample log lines. Length guideline:
50–250 lines. Keep example URLs realistic (use `example.com` for
placeholders so the lychee external check does not block).

## Adding a script (`scripts/<name>.{py,mjs}`)

Scripts must:

- Live in `scripts/`, with a `#!/usr/bin/env python3` or
  `#!/usr/bin/env node` shebang and `chmod +x` set.
- Use **argparse** (Python) or a hand-rolled flag parser (Node) — no
  external CLI framework.
- Have one subcommand per operation (e.g. `extract`, `validate`,
  `self-test`).
- Implement a `self-test` (or `--self-test`) subcommand that runs
  fully offline and exits 0 on success, non-zero otherwise.
- Print clear error messages with full file paths and context.
- Be added to `package.json`'s `self-test` chain.
- Be linked from a reference doc explaining when to use it.

## Adding a template (`templates/<name>.<ext>`)

A template must include:

- A header row / structural example (header line for CSV, top-level
  keys for JSON, one entry for BibTeX).
- At least 1–2 realistic sample rows / entries. The CSV samples must
  pass the corresponding validator (`scripts/data_clean.py validate`,
  `scripts/evidence_ledger.py validate`); the `research-plan.json`
  template must pass `scripts/research_plan.py check`.
- A reference doc explaining the field semantics.

## CI

Three workflows run on every PR:

- **internal-refs** — `scripts/check_internal_refs.py` validates
  backticked in-repo path references (e.g. `references/safety-and-access-policy.md`
  and the like). The checker walks every markdown file and confirms
  the referenced file exists on disk.
- **lychee** — `lychee --offline` on all markdown for standard
  `[text](url)` link syntax.
- **lint-and-self-test** — `ruff check scripts/`, `node --check`
  on every `.mjs`, and `npm run self-test`.

A fourth workflow (`lychee-external`) runs weekly and on
`workflow_dispatch`; it is non-blocking.

## What is not in scope

The skill explicitly does not, and will not, support:

- Bypass of captcha, login walls, paywalls, rate limits, anti-bot, or
  `robots.txt`.
- Stealth-plugin defaults, browser-fingerprint spoofing, IP rotation
  for evasion.
- Access to paywalled academic databases (Scopus, Web of Science,
  IEEE Xplore, ACM Digital Library, JSTOR, …) without legitimate
  user-supplied credentials.

PRs that add any of the above will not be merged.

## Release notes

Internal release notes live in `docs/`. They are not consumed by
agents and are not linked from `SKILL.md`. Old planning docs should be
moved to `docs/.archive/` once their content is realised.

## License

By contributing, you agree that your contributions are licensed under
the same license as the repository (`CC-BY-NC-4.0`; see `LICENSE`).
Commercial relicensing of third-party contributions may require the
contributor's separate written permission.
