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


def test_vdr10_compound_multi_assertion_sentence():
    """VDR10: Compound sentences in EN and VI with multiple assertions and a trailing citation.

    All sub-clauses must be audited; token overlap is not accepted as an oracle.
    """
    # English compound sentence
    text_en = "System A achieved 99% reliability and System B processed 10M transactions [ref:C001]."
    row_en = [
        {
            "claim_id": "C001",
            "claim": "System A achieved 99% reliability.",
            "evidence": "System A achieved 99% reliability.",
            "source_url": "https://example.com/sys-a",
        }
    ]
    is_compound, clauses = report_render.decompose_compound_claim(text_en, row_en)
    assert is_compound is True
    assert len(clauses) == 2
    uncovered = [c for c in clauses if not c.get("sub_claim_id")]
    assert len(uncovered) == 1

    # Vietnamese compound sentence
    text_vi = "Hệ thống A đạt 99% độ tin cậy và Hệ thống B xử lý 10 triệu giao dịch [ref:C001]."
    row_vi = [
        {
            "claim_id": "C001",
            "claim": "Hệ thống A đạt 99% độ tin cậy.",
            "evidence": "Hệ thống A đạt 99% độ tin cậy.",
            "source_url": "https://example.com/sys-a",
        }
    ]
    is_compound_vi, clauses_vi = report_render.decompose_compound_claim(text_vi, row_vi)
    assert is_compound_vi is True
    assert len(clauses_vi) == 2
    uncovered_vi = [c for c in clauses_vi if not c.get("sub_claim_id")]
    assert len(uncovered_vi) == 1


def test_vdr14_report_edit_invalidates_sidecar():
    """VDR14: Report markdown modified after review invalidates sidecar via report_digest mismatch."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        rep = ws / "report.md"
        rep.write_text("# Report\n\nVerified initial text. [ref:C001]\n", encoding="utf-8")
        h = f"sha256:{report_render.hashlib.sha256(rep.read_bytes()).hexdigest()}"

        sidecar = {
            "schema_version": "1.0.0",
            "report_path": "report.md",
            "report_digest": h,
            "algorithm": "d-research-report-claims/v1",
            "created_at": "2026-09-05T00:00:00Z",
            "generator": {"name": "test", "version": "1.0.0", "commit": "abc"},
            "spans": [],
            "review_decision": {
                "status": "verified",
                "uncovered_factual_spans_count": 0,
                "unsupported_claims_count": 0,
                "reasons": [],
                "reviewed_at": "2026-09-05T00:00:00Z",
                "assurance_tier": "standard_verified",
            },
        }
        (ws / "report-claims.json").write_text(json.dumps(sidecar), encoding="utf-8")

        # Mutate report text
        rep.write_text("# Report\n\nModified text post-review. [ref:C001]\n", encoding="utf-8")
        errors = report_render.validate_report_claims_sidecar(ws, rep, rep.read_text(encoding="utf-8"))
        assert any("STALE_SIDECAR" in e for e in errors)


def test_vdr15_uncovered_factual_span_detection():
    """VDR15: Uncited factual assertions in narrative, bullets, or factual headings are detected."""
    content = (
        "# Summary\n\n"
        "## Revenue surged by 45% in 2025\n\n"
        "The project launched in June 2024. [ref:C001]\n\n"
        "- The system reached 50,000 requests per second.\n"
    )
    rows = [
        {
            "claim_id": "C001",
            "claim": "The project launched in June 2024.",
            "evidence": "The project launched in June 2024.",
            "source_url": "https://example.com/launch",
        }
    ]
    spans, errors = report_render.parse_report_spans(content, None, rows, strict=True)
    uncovered = [e for e in errors if "UNCOVERED_FACTUAL_SPAN" in e]
    assert len(uncovered) >= 2


def test_vdr16_table_caption_footnote_assertions():
    """VDR16: Factual table cells, captions, and footnotes are parsed and bound as discrete spans."""
    content = (
        "# Report\n\n"
        "Table 1: Cluster performance benchmarks [ref:C001]\n\n"
        "| Node | Latency |\n"
        "| --- | --- |\n"
        "| Node-1 | 5ms [ref:C002] |\n\n"
        "[^1]: All benchmarks conducted on hardware cluster A [ref:C003].\n"
    )
    rows = [
        {"claim_id": "C001", "claim": "benchmarks", "evidence": "benchmarks", "source_url": "https://example.com"},
        {"claim_id": "C002", "claim": "5ms", "evidence": "5ms", "source_url": "https://example.com"},
        {"claim_id": "C003", "claim": "cluster A", "evidence": "cluster A", "source_url": "https://example.com"},
    ]
    spans, _ = report_render.parse_report_spans(content, None, rows, strict=False)
    types = {s["location_type"] for s in spans}
    assert "table_caption" in types
    assert "table_cell" in types
    assert "footnote" in types


def test_vdr17_citation_in_comment_or_code_block():
    """VDR17: Citations inside comments or code blocks do not satisfy narrative coverage requirements."""
    content = (
        "# Report\n\n"
        "Quantum computing achieved practical fault tolerance in 2026.\n\n"
        "<!-- Hidden comment: [ref:C001] -->\n\n"
        "```python\n# [ref:C001]\n```\n"
    )
    rows = [
        {"claim_id": "C001", "claim": "Quantum computing achieved practical fault tolerance in 2026.", "evidence": "Data", "source_url": "https://example.com"}
    ]
    spans, errors = report_render.parse_report_spans(content, None, rows, strict=True)
    assert any("UNCOVERED_FACTUAL_SPAN" in e for e in errors)


def test_vdr18_generated_block_factual_assertion():
    """VDR18: Factual assertions inside generated blocks undergo full verification; false assertions fail."""
    content = (
        "# Report\n\n"
        "<!-- BEGIN GENERATED: evidence-summary -->\n"
        "The system version is 9.9.9. [ref:C001]\n"
        "<!-- END GENERATED: evidence-summary -->\n"
    )
    rows = [
        {
            "claim_id": "C001",
            "claim": "The system version is 9.9.9.",
            "evidence": "The system version is 3.4.1.",
            "source_url": "https://example.com/v",
        }
    ]
    spans, errors = report_render.parse_report_spans(content, None, rows, strict=True)
    assert any("CITATION_MISUSE" in e for e in errors)
    bindings = [b for s in spans for b in s.get("evidence_bindings", [])]
    assert any(b["support_status"] in {"contradicts", "insufficient"} for b in bindings)


def test_vdr19_valid_generated_block_and_code_spans():
    """VDR19: Valid generated table summaries and instructional code spans are not over-blocked."""
    content = (
        "# Report\n\n"
        "<!-- BEGIN GENERATED: evidence-summary -->\n"
        "| Claim | Source | Status |\n"
        "| --- | --- | --- |\n"
        "| Latency is 10ms [ref:C001] | https://example.com | Verified |\n"
        "<!-- END GENERATED: evidence-summary -->\n\n"
        "To verify installation, run the following command:\n\n"
        "```bash\ncurl https://example.com/install.sh\n```\n"
    )
    rows = [
        {
            "claim_id": "C001",
            "claim": "Latency is 10ms",
            "evidence": "Measured latency is 10ms",
            "quote_or_anchor": "10ms",
            "source_url": "https://example.com",
        }
    ]
    spans, errors = report_render.parse_report_spans(content, None, rows, strict=False)
    code_spans = [s for s in spans if s.get("location_type") == "code_block"]
    assert len(code_spans) >= 1
    assert all(s.get("statement_type") in {"instructional", "non_factual"} for s in code_spans)
