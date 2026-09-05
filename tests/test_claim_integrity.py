import os
import sys
import tempfile
import hashlib
from pathlib import Path

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
