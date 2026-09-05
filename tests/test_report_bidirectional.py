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


def _create_minimal_workspace(ws: Path, rows: list[dict[str, str]]) -> Path:
    fields = [
        "claim_id", "claim", "sub_question", "source_title", "source_url", "source_type",
        "date_published", "date_accessed", "access_method", "evidence", "quote_or_anchor",
        "contradiction", "confidence", "notes"
    ]
    ledger_path = ws / "evidence-ledger.csv"
    with ledger_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return ledger_path


def test_d12_citation_misuse_lint():
    """D12: Valid citation ref attached to contrary narrative assertion exits non-zero (repro F02)."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        row = {
            "claim_id": "C001",
            "claim": "The package version is 3.4.1.",
            "source_title": "package.json",
            "source_url": "https://example.com/package.json",
            "source_type": "code",
            "date_published": "2026-07-28",
            "date_accessed": "2026-09-04",
            "access_method": "fetch",
            "evidence": "The package.json version field is 3.4.1.",
            "contradiction": "none",
            "confidence": "high",
        }
        _create_minimal_workspace(ws, [row])
        # Assertion contrary to row C001
        report_text = "# Report\n\nThis software predicts all future events with 100 percent accuracy. [ref:C001]\n"
        (ws / "report.md").write_text(report_text, encoding="utf-8")

        args = argparse.Namespace(
            workspace=str(ws), report="report.md", strict=True, allow_unreferenced=False
        )
        rc = report_render.cmd_lint(args)
        assert rc != 0


def test_d13_uncited_extra_claim_lint():
    """D13: Report narrative contains uncited factual claim appended at end of document (repro F02)."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        row = {
            "claim_id": "C001",
            "claim": "The package version is 3.4.1.",
            "source_title": "package.json",
            "source_url": "https://example.com/package.json",
            "source_type": "code",
            "date_published": "2026-07-28",
            "date_accessed": "2026-09-04",
            "access_method": "fetch",
            "evidence": "The package.json version field is 3.4.1.",
            "contradiction": "none",
            "confidence": "high",
        }
        _create_minimal_workspace(ws, [row])
        report_text = (
            "# Report\n\n"
            "The package version is 3.4.1. [ref:C001]\n\n"
            "This software predicts all future events with 100 percent accuracy.\n"
        )
        (ws / "report.md").write_text(report_text, encoding="utf-8")

        args = argparse.Namespace(
            workspace=str(ws), report="report.md", strict=True, allow_unreferenced=False
        )
        rc = report_render.cmd_lint(args)
        assert rc != 0


def test_d14_comment_code_citation_evasion():
    """D14: Citations placed exclusively inside HTML comments or code fences do not count for narrative."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        row = {
            "claim_id": "C001",
            "claim": "Deployment succeeded on target servers.",
            "source_title": "Deploy Log",
            "source_url": "https://example.com/deploy",
            "source_type": "log",
            "date_published": "2026-01-01",
            "date_accessed": "2026-06-01",
            "access_method": "fetch",
            "evidence": "Deployment succeeded on target servers.",
            "contradiction": "none",
            "confidence": "high",
        }
        _create_minimal_workspace(ws, [row])
        report_text = (
            "# Report\n\n"
            "Deployment succeeded on target servers.\n\n"
            "<!-- Hidden citation evasion: [ref:C001] -->\n\n"
            "```bash\necho [ref:C001]\n```\n"
        )
        (ws / "report.md").write_text(report_text, encoding="utf-8")

        args = argparse.Namespace(
            workspace=str(ws), report="report.md", strict=True, allow_unreferenced=False
        )
        rc = report_render.cmd_lint(args)
        assert rc != 0


def test_d15_table_and_caption_spans():
    """D15: Factual assertions in table cells, captions, and footnotes are audited as discrete spans."""
    content = (
        "# Benchmark Report\n\n"
        "Table 1: System latency measurements across clusters [ref:C001]\n\n"
        "| Cluster | P99 Latency | Status |\n"
        "| --- | --- | --- |\n"
        "| US-East | 12ms [ref:C001] | Verified |\n\n"
        "[^1]: Latency was measured under peak 50k RPS load.\n"
    )
    rows = [
        {
            "claim_id": "C001",
            "claim": "Latency measurements across clusters",
            "evidence": "US-East P99 latency measured at 12ms",
            "quote_or_anchor": "12ms",
            "source_url": "https://example.com/latency",
        }
    ]
    spans, errors = report_render.parse_report_spans(content, None, rows, strict=False)
    types = {s["location_type"] for s in spans}
    assert "table_caption" in types
    assert "table_cell" in types
    assert "footnote" in types


def test_d16_compound_claim_decomposition():
    """D16: Compound sentence containing one true claim and one unverified claim is decomposed."""
    text = "Company X was founded in 2010 and reached 100M ARR in 2020 [ref:C001]."
    cited_rows = [
        {
            "claim_id": "C001",
            "claim": "Company X was founded in 2010",
            "evidence": "Company X was founded in 2010 in California.",
            "source_url": "https://example.com/about",
        }
    ]
    is_compound, sub_clauses = report_render.decompose_compound_claim(text, cited_rows)
    assert is_compound is True
    assert len(sub_clauses) >= 2
    unverified = [sc for sc in sub_clauses if not sc.get("sub_claim_id")]
    assert len(unverified) >= 1


def test_d17_sidecar_span_misclassification():
    """D17: Sidecar report-claims.json omits factual spans or misclassifies factual statements."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        report_path = ws / "report.md"
        report_text = "# Report\n\nSubstantive factual finding verified here. [ref:C001]\n"
        report_path.write_text(report_text, encoding="utf-8")

        # Create tampered sidecar omitting the factual span or labeling it non_factual
        tampered_sidecar = {
            "schema_version": "1.0.0",
            "report_path": "report.md",
            "report_digest": f"sha256:{report_render.hashlib.sha256(report_text.encode('utf-8')).hexdigest()}",
            "algorithm": "d-research-report-claims/v1",
            "created_at": "2026-09-05T00:00:00Z",
            "generator": {"name": "test", "version": "1.0.0", "commit": "abc"},
            "metadata": {"workspace_root": str(ws), "ledger_path": "evidence-ledger.csv", "total_report_characters": len(report_text), "total_report_lines": 3},
            "spans": [
                {
                    "span_id": "span:1",
                    "start_offset": 10,
                    "end_offset": 60,
                    "line_number": 3,
                    "text": "Substantive factual finding verified here. [ref:C001]",
                    "location_type": "narrative_paragraph",
                    "statement_type": "non_factual",  # Misclassification!
                    "claim_ids": [],
                    "evidence_bindings": [],
                }
            ],
            "review_decision": {
                "status": "verified",
                "uncovered_factual_spans_count": 0,
                "unsupported_claims_count": 0,
                "requires_review_count": 0,
                "reasons": [],
                "reviewed_at": "2026-09-05T00:00:00Z",
                "assurance_tier": "standard_verified",
            },
        }
        (ws / "report-claims.json").write_text(json.dumps(tampered_sidecar), encoding="utf-8")
        errors = report_render.validate_report_claims_sidecar(ws, report_path, report_text)
        assert any("SIDECAR_INTEGRITY_FAILURE" in e for e in errors)


def test_d18_stale_sidecar_rejection():
    """D18: Report markdown modified after sidecar generation alters report_digest; rejected as stale."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        report_path = ws / "report.md"
        report_text = "# Report\n\nInitial certified text. [ref:C001]\n"
        report_path.write_text(report_text, encoding="utf-8")

        sidecar = {
            "schema_version": "1.0.0",
            "report_path": "report.md",
            "report_digest": f"sha256:{report_render.hashlib.sha256(report_text.encode('utf-8')).hexdigest()}",
            "algorithm": "d-research-report-claims/v1",
            "created_at": "2026-09-05T00:00:00Z",
            "generator": {"name": "test", "version": "1.0.0", "commit": "abc"},
            "metadata": {"workspace_root": str(ws), "ledger_path": "evidence-ledger.csv", "total_report_characters": len(report_text), "total_report_lines": 3},
            "spans": [],
            "review_decision": {
                "status": "verified",
                "uncovered_factual_spans_count": 0,
                "unsupported_claims_count": 0,
                "requires_review_count": 0,
                "reasons": [],
                "reviewed_at": "2026-09-05T00:00:00Z",
                "assurance_tier": "standard_verified",
            },
        }
        (ws / "report-claims.json").write_text(json.dumps(sidecar), encoding="utf-8")

        # Now mutate report.md without regenerating sidecar
        report_path.write_text("# Report\n\nInitial certified text MUTATED. [ref:C001]\n", encoding="utf-8")
        errors = report_render.validate_report_claims_sidecar(ws, report_path, report_path.read_text(encoding="utf-8"))
        assert any("STALE_SIDECAR" in e for e in errors)


def test_d19_inference_statement_admissibility():
    """D19: Inferences/hypotheses labeled statement_type=inference are admitted as analytical commentary."""
    content = (
        "# Analysis Report\n\n"
        "Inference: Market adoption will likely accelerate if subsidies continue.\n\n"
        "Hypothesis: Secondary failure occurred due to voltage drop.\n"
    )
    spans, errors = report_render.parse_report_spans(content, None, [], strict=False)
    inference_spans = [s for s in spans if s.get("statement_type") == "inference"]
    assert len(inference_spans) == 2
    # Inferences do not require factual claim bindings and do not generate UNCOVERED_FACTUAL_SPAN
    assert not any("UNCOVERED_FACTUAL_SPAN" in e for e in errors)
