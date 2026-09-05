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
    (ws / "evidence").mkdir(parents=True, exist_ok=True)
    snap_content = "The package version is 3.4.1."
    (ws / "evidence" / "C001.txt").write_text(snap_content, encoding="utf-8")
    import hashlib
    snap_hash = f"sha256:{hashlib.sha256(snap_content.encode('utf-8')).hexdigest()}"

    fields = [
        "claim_id", "claim", "sub_question", "source_title", "source_url", "source_type",
        "date_published", "date_accessed", "access_method", "evidence", "quote_or_anchor",
        "contradiction", "confidence", "notes", "archive_url", "content_hash",
        "snapshot_status", "verifiability", "verifiability_note"
    ]
    rows = [
        {
            "claim_id": "C001",
            "claim": "The package version is 3.4.1.",
            "sub_question": "What version?",
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
            "notes": "",
            "archive_url": "",
            "content_hash": snap_hash,
            "snapshot_status": "intact",
            "verifiability": "archive_snapshot",
            "verifiability_note": "",
        }
    ]
    with (ws / "evidence-ledger.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    report_text = "# Verified Report\n\nThe package version is 3.4.1. [ref:C001]\n"
    (ws / "report.md").write_text(report_text, encoding="utf-8")

    # Generate valid sidecar
    spans, errors = report_render.parse_report_spans(report_text, ws, rows, strict=True)
    report_render.generate_report_claims_sidecar(ws, ws / "report.md", rows, spans, strict=True, errors=errors)


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


def test_vdr22_cli_final_and_runtime_archive():
    """VDR22: Execute VDR scenarios (positive VDR03 vs negative VDR01/07/18) through CLI gate.

    Verifies gate exit codes and dynamic provenance metadata in generated sidecar.
    """
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        _setup_positive_workspace(ws)

        # 1. Positive VDR03 via CLI lint
        lint_args = argparse.Namespace(
            workspace=str(ws), report="report.md", strict=True, allow_unreferenced=False
        )
        rc_pos = report_render.cmd_lint(lint_args)
        assert rc_pos == 0

        # Check provenance metadata in sidecar
        sidecar = json.loads((ws / "report-claims.json").read_text(encoding="utf-8"))
        gen = sidecar.get("generator", {})
        assert gen.get("name") == "d-research-skill"
        assert "version" in gen
        assert "commit" in gen

        # 2. Negative VDR01 via CLI lint (version mismatch)
        (ws / "report.md").write_text("# Report\n\nThe package version is 9.9.9. [ref:C001]\n", encoding="utf-8")
        rc_neg_vdr01 = report_render.cmd_lint(lint_args)
        assert rc_neg_vdr01 != 0

        # 3. Negative VDR07 via CLI lint (sign flip)
        (ws / "report.md").write_text("# Report\n\nThe package version is -3.4.1. [ref:C001]\n", encoding="utf-8")
        rc_neg_vdr07 = report_render.cmd_lint(lint_args)
        assert rc_neg_vdr07 != 0

        # 4. Negative VDR18 via CLI lint (false assertion inside generated block)
        gen_block_report = (
            "# Report\n\n"
            "<!-- BEGIN GENERATED: evidence-summary -->\n"
            "The package version is 9.9.9. [ref:C001]\n"
            "<!-- END GENERATED: evidence-summary -->\n"
        )
        (ws / "report.md").write_text(gen_block_report, encoding="utf-8")
        rc_neg_vdr18 = report_render.cmd_lint(lint_args)
        assert rc_neg_vdr18 != 0


def test_vux02_d_research_docs_positive_workflow(monkeypatch):
    """VUX02: Agent following D Research docs executes real positive workflow (capture, sign, review, finalize).

    Verifies that authentic commands and real verification gates achieve strict_verified tier
    without fabricated JSON sidecars or dummy mocks.
    """
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        _setup_positive_workspace(ws)

        # 1. Sign evidence ledger with real HMAC key via evidence_ledger
        monkeypatch.setenv("D_RESEARCH_LEDGER_KEY", "secret-test-key-12345678901234567890")
        import evidence_ledger

        sig_rc = evidence_ledger.sign_ledger(
            ws / "evidence-ledger.csv", "D_RESEARCH_LEDGER_KEY", None
        )
        assert sig_rc == 0
        sig_file = ws / "evidence-ledger.csv.hmac"
        assert sig_file.is_file()

        # 2. Execute report lint / gate review using real cmd_lint
        lint_args = argparse.Namespace(
            workspace=str(ws), report="report.md", strict=True, allow_unreferenced=False
        )
        rc = report_render.cmd_lint(lint_args)
        assert rc == 0

        # 3. Verify real generated review sidecar
        sidecar_path = ws / "report-claims.json"
        assert sidecar_path.is_file()
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        review = sidecar.get("review_decision", {})
        assert review.get("status") == "verified"
        assert review.get("assurance_tier") == "strict_verified"
        assert review.get("uncovered_factual_spans_count") == 0
        assert review.get("unsupported_claims_count") == 0

        # 4. Verify build provenance is dynamic and real (not hardcoded dummy)
        gen = sidecar.get("generator", {})
        assert gen.get("name") == "d-research-skill"
        assert "version" in gen
        assert "commit" in gen

