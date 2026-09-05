import argparse
import csv
import json
import sys
import tempfile
from pathlib import Path

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import report_render
import research_plan


def _setup_positive_workspace(ws: Path):
    fields = [
        "claim_id", "claim", "sub_question", "source_title", "source_url", "source_type",
        "date_published", "date_accessed", "access_method", "evidence", "quote_or_anchor",
        "contradiction", "confidence", "notes"
    ]
    rows = [
        {
            "claim_id": "C001",
            "claim": "The package version is 3.4.1.",
            "source_title": "package.json",
            "source_url": "https://example.com/package.json",
            "source_type": "code",
            "date_published": "2026-07-28",
            "date_accessed": "2026-09-04",
            "access_method": "fetch",
            "evidence": "The package version is 3.4.1.",
            "quote_or_anchor": "The package version is 3.4.1.",
            "contradiction": "none",
            "confidence": "high",
        }
    ]
    with (ws / "evidence-ledger.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    report_text = "# Verified Report\n\nThe package version is 3.4.1. [ref:C001]\n"
    (ws / "report.md").write_text(report_text, encoding="utf-8")

    # Generate valid sidecar
    spans, _ = report_render.parse_report_spans(report_text, ws, rows, strict=True)
    report_render.generate_report_claims_sidecar(ws, ws / "report.md", rows, spans, strict=True)


def test_d23_cli_release_gates_blocking():
    """D23: CLI release gates executed against D01/D12/D13 flaw workspaces exit non-zero."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        fields = [
            "claim_id", "claim", "sub_question", "source_title", "source_url", "source_type",
            "date_published", "date_accessed", "access_method", "evidence", "quote_or_anchor",
            "contradiction", "confidence", "notes"
        ]
        # Flawed row: version mismatch (3.4.1 in evidence vs 9.9.9 in claim)
        rows = [
            {
                "claim_id": "C001",
                "claim": "The package version is 9.9.9.",
                "source_title": "package.json",
                "source_url": "https://example.com/package.json",
                "source_type": "code",
                "date_published": "2026-07-28",
                "date_accessed": "2026-09-04",
                "access_method": "fetch",
                "evidence": "The package version is 3.4.1.",
                "quote_or_anchor": "The package version is 9.9.9.",
                "contradiction": "none",
                "confidence": "high",
            }
        ]
        with (ws / "evidence-ledger.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

        # Flaw A: Citation misuse (D12)
        (ws / "report.md").write_text("# Report\n\nSoftware predicts future with 100% accuracy [ref:C001]\n", encoding="utf-8")
        lint_args = argparse.Namespace(
            workspace=str(ws), report="report.md", strict=True, allow_unreferenced=False
        )
        rc_misuse = report_render.cmd_lint(lint_args)
        assert rc_misuse != 0

        # Flaw B: Uncited factual extra claim (D13)
        (ws / "report.md").write_text(
            "# Report\n\nThe package version is 9.9.9. [ref:C001]\n\nUncited extra factual assertion.\n",
            encoding="utf-8"
        )
        rc_uncited = report_render.cmd_lint(lint_args)
        assert rc_uncited != 0

        # Flaw C: research_plan _claim_coverage_complete gate check
        plan_data = {
            "schema_version": "2.0",
            "title": "Flawed Research",
            "tasks": [
                {"id": "T1", "phase": "synthesis", "outputs": ["report.md"]}
            ]
        }
        plan_file = ws / "research-plan.json"
        plan_file.write_text(json.dumps(plan_data), encoding="utf-8")
        ok, detail = research_plan._claim_coverage_complete(plan_data, plan_file)
        assert ok is False


def test_d24_cli_positive_end_to_end():
    """D24: Fully verified positive report workspace executed via CLI completes with exit code 0."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        _setup_positive_workspace(ws)

        # 1. cmd_lint passes with strict mode
        lint_args = argparse.Namespace(
            workspace=str(ws), report="report.md", strict=True, allow_unreferenced=False
        )
        rc = report_render.cmd_lint(lint_args)
        assert rc == 0

        # 2. Sidecar verified with strict_verified assurance tier
        sidecar_path = ws / "report-claims.json"
        assert sidecar_path.is_file()
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert sidecar["review_decision"]["status"] == "verified"
        assert sidecar["review_decision"]["assurance_tier"] == "strict_verified"
        assert sidecar["review_decision"]["uncovered_factual_spans_count"] == 0
        assert sidecar["review_decision"]["unsupported_claims_count"] == 0
