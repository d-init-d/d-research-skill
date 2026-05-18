# Report Generation

This reference covers the final report generation step of the research workflow. After evidence collection, ledger signing, and synthesis, the agent produces a structured Markdown report with citations, evidence tables, and PRISMA flow summaries.

## When to Use

- After completing a long-horizon research plan
- When the user requests a formatted deliverable from collected evidence
- As the final step before declaring research "done"
- When producing academic-grade output with proper citations

## Script

`scripts/report_render.py` handles report generation with these subcommands:

| Subcommand | Purpose |
|---|---|
| `init --workspace <dir>` | Create `report.draft.md` skeleton from plan + template |
| `render --workspace <dir>` | Produce final `report.md` from workspace artifacts |
| `to-pdf --in report.md --out report.pdf` | Export to PDF via pandoc |
| `to-docx --in report.md --out report.docx` | Export to DOCX via pandoc |
| `to-html --in report.md --out report.html` | Export to HTML via pandoc |
| `list-styles` | List available CSL citation styles |
| `lint --workspace <dir>` | Check for missing/unused claims and broken refs |

## Workspace Requirements

The `render` command expects a workspace directory containing:

- `research-plan.json` — plan with title and task list (sections derive from tasks)
- `evidence-ledger.csv` — claims with sources, confidence, and evidence
- `screening-log.csv` (optional) — PRISMA screening decisions

## Signature Verification Behavior

The `render` command enforces ledger integrity:

1. **Always** validates the evidence-ledger CSV schema
2. If a `.hmac` signature sidecar exists, **verifies** it — hard-fails on mismatch
3. If no signature exists, **warns** and continues by default
4. If `--require-signature` is set and no valid signature exists, **hard-fails**

This ensures tamper-evident research output when signatures are available.

## Report Structure

The generated `report.md` contains:

1. **Title** — from `research-plan.json`
2. **Executive Summary** — placeholder for synthesis
3. **Task Sections** — one per plan task
4. **Evidence Summary** — table of claims from the ledger (capped at 50 rows)
5. **Screening Summary** — PRISMA counts if `screening-log.csv` exists
6. **References** — deduplicated source URLs from the ledger
7. **Caveats and Limitations** — placeholder for documenting gaps

## Lint Checks

`report_render.py lint` reports:

- Claims referenced in the report (`[ref:claim_id]`) but not in the ledger
- Ledger claims not referenced in the report (warnings, not errors)
- Missing workspace files

## Export Formats

PDF, DOCX, and HTML export require `pandoc >= 2.11`. If pandoc is not installed, the commands print a helpful installation message and exit non-zero without crashing.

## Workflow Integration

```bash
# 1. Initialize report skeleton
python scripts/report_render.py init --workspace ./research-topic-2026-05-18

# 2. (Agent fills in findings in report.draft.md or sections/)

# 3. Render final report
python scripts/report_render.py render --workspace ./research-topic-2026-05-18

# 4. Lint check
python scripts/report_render.py lint --workspace ./research-topic-2026-05-18

# 5. Export (optional)
python scripts/report_render.py to-pdf --in ./research-topic-2026-05-18/report.md --out report.pdf
```

## See Also

- `templates/report-template.md` — the Markdown template used by `init`
- `references/research-plan-protocol.md` — the long-horizon protocol that ends with report render
- `references/synthesis-patterns.md` — synthesis strategies before report generation
- `references/citation-management.md` — citation export and rendering pipeline
- `references/reproducibility-checklist.md` — pre-delivery audit
