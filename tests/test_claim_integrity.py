import hashlib
from pathlib import Path
import sys
import tempfile

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import quality_eval


def test_d01_version_mismatch():
    """D01: Evidence records version 3.4.1 while claim states version 9.9.9 (repro F01)."""
    claim = "The package version is 9.9.9."
    evidence = "The package version is 3.4.1."
    row = {
        "claim_id": "C1",
        "claim": claim,
        "evidence": evidence,
        "quote_or_anchor": claim,
        "source_url": "https://example.com/package.json",
        "date_published": "2026-07-28",
        "date_accessed": "2026-09-04",
        "confidence": "high",
    }
    classification = quality_eval.classify_claim_evidence(claim, evidence, row)
    assert classification["status"] in {"contradicts", "refutes", "insufficient"}
    assert classification["status"] != "supports"
    assert classification.get("supports_claim") is False

    analysis = quality_eval.analyze_artifact({
        "report_claims": [{"claim_id": "C1", "text": claim, "important": True}],
        "ledger_rows": [row],
        "sources": [{"url": row["source_url"]}],
    })
    assert analysis["citation_correctness"] != 1.0
    assert not analysis["ok"]
    assert "citation_does_not_support_claim" in analysis["critical_failures"]


def test_d02_valid_quote_supports():
    """D02: Genuine matching quote verified in snapshot and contextual claim semantics fully consistent."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        snap_dir = ws / "evidence"
        snap_dir.mkdir(parents=True)
        snap_file = snap_dir / "C100.txt"
        snap_content = "Project Apollo confirmed successful deployment of subsystem v2.4 in production."
        snap_file.write_text(snap_content, encoding="utf-8")
        snap_hash = hashlib.sha256(snap_content.encode("utf-8")).hexdigest()

        quote = "successful deployment of subsystem v2.4 in production"
        claim = quote
        evidence = snap_content
        row = {
            "claim_id": "C100",
            "claim": claim,
            "evidence": evidence,
            "quote_or_anchor": quote,
            "source_url": "https://example.com/apollo-report",
            "snapshot_path": str(snap_file.resolve()),
            "content_hash": f"sha256:{snap_hash}",
            "date_published": "2026-01-01",
            "date_accessed": "2026-06-01",
            "confidence": "high",
        }

        classification = quality_eval.classify_claim_evidence(claim, evidence, row=row, workspace=ws)
        assert classification["status"] == "supports"
        assert classification.get("supports_claim") is True

        analysis = quality_eval.analyze_artifact({
            "report_claims": [{"claim_id": "C100", "text": claim, "important": True}],
            "ledger_rows": [row],
            "sources": [{"url": row["source_url"]}],
        })
        assert analysis["ok"] is True
        assert analysis["citation_correctness"] == 1.0
        assert len(analysis["critical_failures"]) == 0


def test_d06_locator_vs_quote_semantics():
    """D06: quote_or_anchor is a CSS selector, page number, or image path from legacy ledger."""
    selectors = [
        "div.main-content > p:nth-child(3)",
        "#section-results table tr:first-child",
        "p. 142",
        "page 12-15",
        "figures/chart_2026.png",
    ]
    for locator in selectors:
        claim = "System throughput scaled to 10000 req/sec."
        row = {
            "claim_id": "C200",
            "claim": claim,
            "evidence": "Observed high system load and scalability.",
            "quote_or_anchor": locator,
            "source_url": "https://example.com/benchmark.pdf",
            "confidence": "high",
        }
        res = quality_eval.classify_claim_evidence(claim, row["evidence"], row)
        # Locators must degrade assurance or require review, not claim literal quote match
        assert res["status"] != "supports"
        assert res.get("status") in {"requires_review", "unsupported", "insufficient"}
        assert res.get("reason") in {
            "locator_anchor_not_literal_quote",
            "locator_anchor_requires_review",
            "quote_not_found",
            "no_deterministic_support",
            "insufficient_evidence",
        }


def test_d08_hypothetical_context():
    """D08: Quote appears in source within a refutation, hypothesis, or conditional clause."""
    hypothetical_evidence = (
        "If quantum computers break RSA-2048 next month, all current encryption keys will be compromised. "
        "However, this scenario remains purely hypothetical and unproven."
    )
    claim = "All current RSA-2048 encryption keys are compromised."
    row = {
        "claim_id": "C300",
        "claim": claim,
        "evidence": hypothetical_evidence,
        "quote_or_anchor": "all current encryption keys will be compromised",
        "source_url": "https://example.com/quantum-security",
        "confidence": "high",
    }
    res = quality_eval.classify_claim_evidence(claim, hypothetical_evidence, row)
    assert res["status"] in {"contradicts", "refutes", "insufficient", "requires_review"}
    assert res.get("supports_claim") is False


def test_vdr01_report_repeats_mismatched_ledger():
    """VDR01: Report repeats ledger claim 9.9.9 while evidence is 3.4.1.

    Strict/final gate is not verified; emits specific citation misuse / mismatch error.
    """
    import report_render

    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        row = {
            "claim_id": "C001",
            "claim": "The package version is 9.9.9.",
            "evidence": "The package version is 3.4.1.",
            "quote_or_anchor": "The package version is 3.4.1.",
            "source_url": "https://example.com/package.json",
            "confidence": "high",
        }
        report_text = "# Report\n\nThe package version is 9.9.9. [ref:C001]\n"
        (ws / "report.md").write_text(report_text, encoding="utf-8")

        spans, errors = report_render.parse_report_spans(report_text, ws, [row], strict=True)
        assert any("CITATION_MISUSE" in e for e in errors)
        assert any(
            b["support_status"] in {"contradicts", "insufficient", "refutes"}
            for s in spans
            for b in s.get("evidence_bindings", [])
        )

        sidecar = report_render.generate_report_claims_sidecar(
            ws, ws / "report.md", [row], spans, strict=True, errors=errors
        )
        assert sidecar["review_decision"]["status"] == "rejected"
        assert sidecar["review_decision"]["assurance_tier"] == "degraded"
        assert sidecar["review_decision"]["unsupported_claims_count"] > 0


def test_vdr06_locator_selector_not_literal_quote():
    """VDR06: quote_or_anchor is a selector/page/screenshot legacy anchor instead of literal quote.

    Evaluator must not treat locators as verbatim quote matches.
    """
    import report_render

    locators = [
        "page 42",
        "p. 15",
        "line 120",
        "xpath://div[@id='content']",
        "css:.main-title",
        "selector: #results",
        "figures/chart.png",
    ]
    for loc in locators:
        row = {
            "claim_id": "C200",
            "claim": "Throughput reached 10000 req/sec.",
            "evidence": "Throughput was observed to scale up.",
            "quote_or_anchor": loc,
            "source_url": "https://example.com/report.pdf",
            "confidence": "high",
        }
        status, reason, method = report_render._statement_supported_by_row(
            "Throughput reached 10000 req/sec. [ref:C200]", row, None
        )
        assert method != "exact_quote_offset"
        assert status != "supports"

        res = quality_eval.classify_claim_evidence(
            "Throughput reached 10000 req/sec.", row["evidence"], row
        )
        assert res["status"] != "supports"


def test_vdr09_short_quote_long_claim_assertion():
    """VDR09: Short quote + longer claim adding new ungrounded assertions is not proven by quote alone."""
    import report_render

    row = {
        "claim_id": "C301",
        "claim": "The service is active with 500 million enterprise users in 2026.",
        "evidence": "The service is active and running.",
        "quote_or_anchor": "active",
        "source_url": "https://example.com/status",
        "confidence": "high",
    }
    res = quality_eval.classify_claim_evidence(
        row["claim"], row["evidence"], row
    )
    assert res["status"] != "supports"

    status, reason, method = report_render._statement_supported_by_row(
        row["claim"], row, None
    )
    assert status != "supports"


def test_vdr11_quote_in_refutation_context():
    """VDR11: Quote appears within refutation or hypothetical context; not promoted to established fact."""
    evidence = (
        "Claims that the vaccine contains microchips were thoroughly disproven and refuted by medical consensus."
    )
    claim = "The vaccine contains microchips."
    row = {
        "claim_id": "C401",
        "claim": claim,
        "evidence": evidence,
        "quote_or_anchor": "vaccine contains microchips",
        "source_url": "https://example.com/health-review",
        "confidence": "high",
    }
    res = quality_eval.classify_claim_evidence(claim, evidence, row)
    assert res["status"] in {"contradicts", "refutes", "insufficient", "requires_review"}
    assert res.get("supports_claim") is False


def test_vdr21_snapshot_context_refutation_rejection():
    """VDR21 (RV3-01): Quote exists in source snapshot but context explicitly refutes it.

    Strict lint and sidecar must reject with CITATION_MISUSE / degraded assurance.
    """
    import report_render

    statement = "The server is secure."
    source = "The following assertion is FALSE: The server is secure. In fact, the server is not secure."
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "evidence").mkdir()
        (ws / "evidence/C001.txt").write_text(source, encoding="utf-8")
        row = {
            "claim_id": "C001",
            "claim": statement,
            "evidence": statement,
            "quote_or_anchor": statement,
            "source_url": "https://example.com/advisory",
            "snapshot_path": "evidence/C001.txt",
            "content_hash": f"sha256:{hashlib.sha256(source.encode()).hexdigest()}",
            "confidence": "high",
        }
        report = f"# Report\n\n{statement} [ref:C001]\n"
        (ws / "report.md").write_text(report, encoding="utf-8")

        status, reason, method = report_render._statement_supported_by_row(statement, row, ws)
        assert status == "contradicts"
        assert reason == "source_context_refutes_claim"

        spans, errors = report_render.parse_report_spans(report, ws, [row], strict=True)
        assert any("CITATION_MISUSE" in e for e in errors)
        sidecar = report_render.generate_report_claims_sidecar(
            ws, ws / "report.md", [row], spans, strict=True, errors=errors
        )
        assert sidecar["review_decision"]["status"] == "rejected"
        assert sidecar["review_decision"]["assurance_tier"] == "degraded"


def test_vdr22_vietnamese_refutation_rejection():
    """VDR22 (RV3-01 VI): Vietnamese source context explicitly refuting claim."""
    import report_render

    statement = "Hệ thống bảo mật tuyệt đối."
    source = "Khẳng định sau đây là hoàn toàn sai: Hệ thống bảo mật tuyệt đối. Thực tế là hệ thống có lỗ hổng."
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "evidence").mkdir()
        (ws / "evidence/C002.txt").write_text(source, encoding="utf-8")
        row = {
            "claim_id": "C002",
            "claim": statement,
            "evidence": statement,
            "quote_or_anchor": statement,
            "source_url": "https://example.com/vi-advisory",
            "snapshot_path": "evidence/C002.txt",
            "content_hash": f"sha256:{hashlib.sha256(source.encode('utf-8')).hexdigest()}",
            "confidence": "high",
        }
        status, reason, method = report_render._statement_supported_by_row(statement, row, ws)
        assert status == "contradicts"
        assert reason == "source_context_refutes_claim"

