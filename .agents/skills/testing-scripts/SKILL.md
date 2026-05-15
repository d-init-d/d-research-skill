---
name: testing-d-research-scripts
description: Test the d-research-skill executable scripts (api_fetch.mjs, data_clean.py, citation_export.py). Use when verifying script changes, after code generation, or when upgrading the research skill.
---

# Testing D Research Skill Scripts

## Prerequisites

- Node.js (for `api_fetch.mjs`)
- Python 3 (for `data_clean.py` and `citation_export.py`)
- No external API keys needed — self-tests are offline, real-world tests use free APIs (OpenAlex)

## Quick Validation (Self-Tests)

All 3 scripts have built-in self-test commands. Run from the repo root:

```bash
# All 3 can run in parallel — they are independent
python3 scripts/data_clean.py self-test
python3 scripts/citation_export.py self-test
node scripts/api_fetch.mjs --self-test
```

### Pass criteria
- Exit code 0 for all three
- `data_clean.py`: Output contains "ALL TESTS PASSED" with 5 subtests (clean, stats, dedup, validate, merge)
- `citation_export.py`: Output contains "All self-tests passed!" with 6 subtests (CSV read, source extraction, BibTeX, RIS, format, citation key)
- `api_fetch.mjs`: Output contains 4x "✓ PASS" (parseArgs, Link header, cursor, offset pagination)
- No Python tracebacks or "✗ FAIL" strings

## Real-World Tests

### api_fetch.mjs — OpenAlex API
```bash
node scripts/api_fetch.mjs \
  --url "https://api.openalex.org/works?search=machine+learning&per_page=5" \
  --max-pages 1 \
  --out /tmp/test_openalex.json
```
Verify: Output JSON is a valid array with items containing `id`, `title`, `doi` fields.

### data_clean.py — CSV dedup
```bash
# Create test CSV with known duplicates
cat > /tmp/test_input.csv << 'EOF'
id,name,email
1,Alice,alice@example.com
2,Bob,bob@example.com
3,Charlie,charlie@example.com
2,Bob,bob@example.com
4,Diana,diana@example.com
1,Alice,alice@example.com
EOF

python3 scripts/data_clean.py clean --file /tmp/test_input.csv --out /tmp/test_cleaned.csv
```
Verify: Output has 4 rows (header + 4 unique), duplicates for Alice and Bob removed.

### citation_export.py — BibTeX export
```bash
cat > /tmp/test_ledger.csv << 'EOF'
claim,source_url,source_title,confidence,date_collected
"ML improves diagnosis","https://pubmed.ncbi.nlm.nih.gov/12345","ML in Healthcare",high,2024-01-15
"DL outperforms traditional","https://arxiv.org/abs/2401.00001","DL Survey",medium,2024-02-20
EOF

python3 scripts/citation_export.py export --file /tmp/test_ledger.csv --format bibtex --out /tmp/test.bib
```
Verify: Output `.bib` file contains `@misc{` entries with `title = {` and `url = {` fields.

## Known Pitfalls (MiniMax Code Generation)

When scripts are generated or regenerated via MiniMax M2.7:

1. **Markdown code fences** — Output might be wrapped in ` ```python ` / ` ``` `. Remove with `sed -i '1d;$d' <file>`.
2. **Thinking text preamble** — MiniMax may prepend reasoning text before actual code. Inspect first ~30 lines and extract only the code portion.
3. **Missing imports** — Generated code may use modules (e.g., `tempfile`) without importing them at the top. Run a syntax check first: `python3 -c "import py_compile; py_compile.compile('<file>', doraise=True)"`.
4. **Wrong self-test assertions** — Test data row counts or expected values may be off. Trace through the test data manually to verify expected values before trusting assertions.

## No CI Configured

This repo has no CI checks. All validation must be done locally via the commands above.
