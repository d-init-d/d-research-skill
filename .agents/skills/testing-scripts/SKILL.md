---
name: testing-d-research-scripts
description: Verify the d-research-skill helper scripts (Node + Python). Use after editing any file under `scripts/`, after regenerating a script, or before publishing a new version of the skill.
---

# Testing D Research Skill Scripts

## When to use this sub-skill

Run these checks whenever you have:

- edited a file under `scripts/`
- regenerated or replaced a helper script
- bumped a dependency in `package.json`
- prepared a release of `d-research-skill`

The same checks run automatically in CI on every pull request (see "CI" below), so local runs are mainly to fail fast before pushing.

## Prerequisites

- Node.js 18+ (for `*.mjs` scripts and `npm run`)
- Python 3.9+ (for `*.py` scripts; stdlib only — no `pip install` needed)
- `pandoc >= 2.11` (only for the `citation_render.py` self-test; the script degrades cleanly when pandoc is missing)
- Optional: `npx playwright install` — only needed for real-world browser runs, not for any self-test

No external API keys are required. Every self-test runs offline.

## Quick validation: one command

From the repo root:

```bash
npm run self-test
```

This is the same chain CI runs. It executes every script's offline self-test in sequence and exits non-zero on the first failure. Pass criteria: exit code `0` and the final command (`check_internal_refs.py`) prints `OK: all backticked internal refs resolve.`

## Quick validation: individual scripts

If you want to isolate a failure, run scripts one at a time. There are **20 helper scripts** with self-tests (5 Node + 15 Python). `run_python.mjs` is a thin wrapper and has no self-test of its own.

### Node scripts (5)

```bash
node scripts/playwright_probe.mjs   --self-test   # → "playwright_probe self-test ok"
node scripts/playwright_extract.mjs --self-test   # → "playwright_extract self-test ok"
node scripts/playwright_crawl.mjs   --self-test   # → "playwright_crawl self-test ok"
node scripts/api_fetch.mjs          --self-test   # → 4× "✓ PASS" (parseArgs, Link header, cursor, offset)
node scripts/web_search.mjs         --self-test   # → "web_search self-test ok"
```

### Python scripts (15)

```bash
python3 scripts/evidence_ledger.py     self-test   # → "evidence_ledger self-test ok" (incl. tamper detection)
python3 scripts/data_clean.py          self-test   # → "ALL TESTS PASSED" (5 subtests: clean/stats/dedup/validate/merge)
python3 scripts/citation_export.py     self-test   # → "All self-tests passed!" (6 subtests)
python3 scripts/citation_render.py     self-test   # → "All self-tests passed!" (incl. pandoc integration)
python3 scripts/extract_tables.py      self-test   # → "All self-tests passed!" (5 subtests)
python3 scripts/score_source.py        self-test   # → "All self-tests passed!" (4 subtests)
python3 scripts/research_plan.py       self-test   # → "OK: research_plan self-test passed (NN sub-tests)."
python3 scripts/run_dogfood.py         self-test   # → "OK: eval benches valid; dogfood-bench.json: 12 tasks, frontier-bench.json: 34 tasks."
python3 scripts/pdf_extract.py         self-test   # → "pdf_extract self-test ok"
python3 scripts/wayback.py             self-test   # → "wayback self-test ok"
python3 scripts/wikidata.py            self-test   # → "wikidata self-test ok"
python3 scripts/social_snapshot.py     self-test   # → "social_snapshot self-test ok"
python3 scripts/citation_resolver.py   self-test   # → "citation_resolver self-test ok"
python3 scripts/bench_harness_check.py self-test   # → "bench_harness_check self-test ok"
python3 scripts/check_internal_refs.py             # → "OK: all backticked internal refs resolve."
```

On Windows, use `python` if `python3` is not on PATH.

### Pass criteria (universal)

- Exit code `0` for every command
- Output contains a positive marker: `ok`, `PASS`, `ALL TESTS PASSED`, `All self-tests passed!`, or `OK: …`
- No Python tracebacks, no `FAIL`, no unhandled-promise warnings from Node

The `evidence_ledger.py` self-test intentionally exercises the tamper-detection path; a `TAMPER DETECTED` line in the middle of its output is expected and is followed by the success marker.

## Real-world smoke tests (optional)

These hit live public APIs. Use them to verify network paths after a script change, not as gates for CI.

### `api_fetch.mjs` — OpenAlex

```bash
node scripts/api_fetch.mjs \
  --url "https://api.openalex.org/works?search=machine+learning&per_page=5" \
  --max-pages 1 \
  --out openalex.json
```

Expected: `openalex.json` is a JSON array; each item has `id`, `title`, and (usually) `doi`.

### `data_clean.py` — CSV dedup

```bash
python3 scripts/data_clean.py clean --file input.csv --out cleaned.csv
```

Expected: duplicates collapsed, whitespace normalized, ISO 8601 dates.

### `citation_export.py` — BibTeX export

```bash
python3 scripts/citation_export.py export \
  --file evidence.csv --format bibtex --out refs.bib
```

Expected: `refs.bib` contains `@misc{` (or `@article{`) entries with `title = {…}` and `url = {…}` fields.

For the full list of npm shortcuts (`npm run probe`, `npm run plan:render`, `npm run citation:render`, …) see the "npm scripts" section of `README.md`.

## CI

Two GitHub Actions workflows replicate these checks on every pull request:

- `.github/workflows/lint-and-self-test.yml`
  - `ruff check scripts/` — Python lint
  - `node --check` on every `scripts/*.mjs` — JS syntax
  - `npm run self-test` — every offline self-test (with pandoc installed for `citation_render`)
- `.github/workflows/link-check.yml`
  - `scripts/check_internal_refs.py` — backticked in-repo path references
  - `lychee --offline` on all markdown — standard `[text](url)` link integrity
  - A weekly `lychee-external` job (non-blocking) validates external URLs

If any of the 20 self-tests fail locally, the same failure will block the PR. Fix locally before pushing.

## Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| `ImportError` or `ModuleNotFoundError` | Generated script missing a stdlib import | Add the import; re-run `python3 -c "import py_compile; py_compile.compile('scripts/<name>.py', doraise=True)"` |
| `ERR_UNKNOWN_FILE_EXTENSION ".py"` | Tried to invoke `.py` with `node` directly | Use `python3` (or `node scripts/run_python.mjs scripts/<name>.py …`) |
| Pandoc-related FAIL in `citation_render` | Pandoc not installed or `< 2.11` | Install pandoc; the self-test will skip the pandoc-dependent subtest if pandoc is genuinely missing |
| `playwright_*` self-test hangs | Real browser launch attempted | Self-tests must not require a browser; check the script wasn't edited to drop the offline branch |
| `check_internal_refs.py` reports a missing path | A markdown file backticks an in-repo path (e.g. a reference, adapter, template, or script) that no longer exists | Update the reference, restore the file, or remove the link |
| Eval bench schema error | New task missing required keys or frontier/refusal rule violation | Compare against an existing task; required keys are listed in `docs/eval.md` |

## Adding a new script

When you add a new helper to `scripts/`:

1. Implement an offline `self-test` (Python) or `--self-test` (Node) subcommand. CI runs offline, so any network dependency must degrade cleanly.
2. Append the new self-test to the chained `self-test` script in `package.json` so it runs in CI.
3. Add the script to `SKILL.md`'s "Optional bundled scripts" list and link it from a reference doc.
4. Update the script-count notes in `README.md` if the total changes.
5. Re-run `npm run self-test` locally before opening a PR.

See `CONTRIBUTING.md` for the full conventions (argparse, shebangs, error formatting, etc.).

## See also

- `SKILL.md` — main entry point of d-research-skill (decision tree)
- `package.json` — full list of `npm run` shortcuts and the chained `self-test` definition
- `CONTRIBUTING.md` — conventions for adding references, adapters, examples, scripts, and templates
- `docs/eval.md` — eval-harness usage guide for `run_dogfood.py`
- `.github/workflows/` — the two CI workflows that mirror these checks
