import hashlib
import sys
import tempfile
from pathlib import Path

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import quality_eval


def test_d04_quote_not_in_snapshot():
    """D04: Claim quote matches text claimed by candidate but substring does not exist in snapshot."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        snap_dir = ws / "evidence"
        snap_dir.mkdir(parents=True)
        snap_file = snap_dir / "C101.txt"
        snap_content = "The server returned HTTP status 200 with standard payload headers."
        snap_file.write_text(snap_content, encoding="utf-8")
        snap_hash = hashlib.sha256(snap_content.encode("utf-8")).hexdigest()

        # Quote claimed by candidate is fabricated / not in snapshot bytes
        fabricated_quote = "The server authorized root administrator access without authentication."
        row = {
            "claim_id": "C101",
            "claim": fabricated_quote,
            "evidence": snap_content,
            "quote_or_anchor": fabricated_quote,
            "source_url": "https://example.com/log.txt",
            "snapshot_path": str(snap_file.resolve()),
            "content_hash": f"sha256:{snap_hash}",
            "confidence": "high",
        }

        res = quality_eval.classify_claim_evidence(row["claim"], snap_content, row, workspace=ws)
        assert res["status"] in {"unsupported", "contradicts", "insufficient"}
        assert res.get("supports_claim") is False
        assert res.get("reason") in {"quote_not_in_snapshot", "quote_not_found", "no_deterministic_support"}


def test_d05_missing_or_tampered_snapshot():
    """D05: Snapshot file missing on disk, or content digest altered."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        snap_dir = ws / "evidence"
        snap_dir.mkdir(parents=True)
        snap_file = snap_dir / "C102.txt"
        snap_content = "Original verified snapshot content."
        snap_file.write_text(snap_content, encoding="utf-8")
        valid_hash = hashlib.sha256(snap_content.encode("utf-8")).hexdigest()

        # Case A: Snapshot file does not exist on disk
        missing_row = {
            "claim_id": "C102",
            "claim": "Original verified snapshot content.",
            "evidence": snap_content,
            "quote_or_anchor": "Original verified snapshot content.",
            "source_url": "https://example.com/source.txt",
            "snapshot_path": str((ws / "evidence" / "nonexistent.txt").resolve()),
            "content_hash": f"sha256:{valid_hash}",
            "confidence": "high",
        }
        res_missing = quality_eval.classify_claim_evidence(
            missing_row["claim"], snap_content, missing_row, workspace=ws
        )
        assert res_missing["status"] == "unsupported"
        assert res_missing.get("reason") == "missing_snapshot_bytes"

        # Case B: Content digest tampered / altered
        tampered_hash = hashlib.sha256(b"Tampered content").hexdigest()
        tampered_row = {
            "claim_id": "C102",
            "claim": "Original verified snapshot content.",
            "evidence": snap_content,
            "quote_or_anchor": "Original verified snapshot content.",
            "source_url": "https://example.com/source.txt",
            "snapshot_path": str(snap_file.resolve()),
            "content_hash": f"sha256:{tampered_hash}",  # Mismatch with disk file
            "confidence": "high",
        }
        res_tampered = quality_eval.classify_claim_evidence(
            tampered_row["claim"], snap_content, tampered_row, workspace=ws
        )
        assert res_tampered["status"] in {"contradicts", "unsupported", "insufficient"}
        assert res_tampered.get("reason") in {"snapshot_digest_mismatch", "digest_mismatch"}


def test_d10_unopened_url_rejection():
    """D10: Candidate ledger supplies valid, reachable URL but snapshot content was never captured."""
    row = {
        "claim_id": "C103",
        "claim": "Valid RFC published in 2024.",
        "evidence": "RFC 9999 specifies network protocol updates.",
        "quote_or_anchor": "RFC 9999 specifies network protocol updates.",
        "source_url": "https://tools.ietf.org/rfc/rfc9999.txt",
        "snapshot_status": "unopened",
        "confidence": "high",
    }
    res = quality_eval.classify_claim_evidence(row["claim"], row["evidence"], row)
    assert res["status"] == "unsupported"
    assert res.get("supports_claim") is False
    assert res.get("reason") in {"unopened_url", "empty_evidence", "missing_snapshot_bytes", "no_deterministic_support"}


def test_vdr02_legacy_ledger_missing_snapshot():
    """VDR02: Report, ledger, and quote agree, but no physical snapshot artifact exists on disk.

    Legacy reading succeeds; grants standard_verified assurance, NOT strict_verified.
    In strict mode, gate fails closed.
    """
    import report_render

    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        row = {
            "claim_id": "C001",
            "claim": "System latency is 12ms.",
            "evidence": "System latency is 12ms.",
            "quote_or_anchor": "System latency is 12ms.",
            "source_url": "https://example.com/status",
            "confidence": "high",
        }
        report_text = "# Performance\n\nSystem latency is 12ms. [ref:C001]\n"
        (ws / "report.md").write_text(report_text, encoding="utf-8")

        # Non-strict mode: legacy readable, standard_verified (not strict_verified)
        spans_nonstrict, err_nonstrict = report_render.parse_report_spans(report_text, ws, [row], strict=False)
        sidecar_nonstrict = report_render.generate_report_claims_sidecar(
            ws, ws / "report.md", [row], spans_nonstrict, strict=False, errors=err_nonstrict
        )
        assert sidecar_nonstrict["review_decision"]["status"] == "verified"
        assert sidecar_nonstrict["review_decision"]["assurance_tier"] == "standard_verified"
        assert sidecar_nonstrict["review_decision"]["assurance_tier"] != "strict_verified"

        # Strict mode: missing snapshot file blocks verification
        spans_strict, err_strict = report_render.parse_report_spans(report_text, ws, [row], strict=True)
        assert any("MISSING_SNAPSHOT" in e for e in err_strict)
        sidecar_strict = report_render.generate_report_claims_sidecar(
            ws, ws / "report.md", [row], spans_strict, strict=True, errors=err_strict
        )
        assert sidecar_strict["review_decision"]["status"] == "rejected"
        assert sidecar_strict["review_decision"]["assurance_tier"] == "degraded"


def test_vdr03_valid_snapshot_byte_binding():
    """VDR03: Valid snapshot file on disk with correct digest and exact quote match.

    Positive verification grants strict_verified in strict gate.
    """
    import report_render

    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        snap_content = "The database cluster maintains 99.999% uptime."
        snap_dir = ws / "evidence"
        snap_dir.mkdir(parents=True)
        snap_file = snap_dir / "C001.txt"
        snap_file.write_text(snap_content, encoding="utf-8")
        h = f"sha256:{hashlib.sha256(snap_content.encode('utf-8')).hexdigest()}"

        row = {
            "claim_id": "C001",
            "claim": "The database cluster maintains 99.999% uptime.",
            "evidence": snap_content,
            "quote_or_anchor": "99.999% uptime",
            "source_url": "https://example.com/db-status",
            "snapshot_path": "evidence/C001.txt",
            "content_hash": h,
            "confidence": "high",
        }
        report_text = "# System Status\n\nThe database cluster maintains 99.999% uptime. [ref:C001]\n"
        (ws / "report.md").write_text(report_text, encoding="utf-8")

        spans, errors = report_render.parse_report_spans(report_text, ws, [row], strict=True)
        assert not errors
        sidecar = report_render.generate_report_claims_sidecar(
            ws, ws / "report.md", [row], spans, strict=True, errors=errors
        )
        assert sidecar["review_decision"]["status"] == "verified"
        assert sidecar["review_decision"]["assurance_tier"] == "strict_verified"
        assert sidecar["review_decision"]["uncovered_factual_spans_count"] == 0
        assert sidecar["review_decision"]["unsupported_claims_count"] == 0


def test_vdr04_snapshot_tamper_or_path_escape():
    """VDR04: Snapshot path escapes workspace (path traversal) or snapshot bytes differ from declared digest.

    Both must result in structured rejection; cannot get verified status.
    """
    import report_render

    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        # Part A: Path Traversal
        traversal_row = {
            "claim_id": "C001",
            "claim": "Configuration details.",
            "evidence": "Config data.",
            "quote_or_anchor": "Config data.",
            "source_url": "https://example.com/config",
            "snapshot_path": "../../etc/shadow",
            "confidence": "high",
        }
        report_text = "# Config\n\nConfiguration details. [ref:C001]\n"
        (ws / "report.md").write_text(report_text, encoding="utf-8")
        spans, errs = report_render.parse_report_spans(report_text, ws, [traversal_row], strict=True)
        assert any("PATH_TRAVERSAL" in e for e in errs)

        sidecar = report_render.generate_report_claims_sidecar(
            ws, ws / "report.md", [traversal_row], spans, strict=True, errors=errs
        )
        assert sidecar["review_decision"]["status"] == "rejected"

        # Part B: Digest Tamper
        (ws / "evidence").mkdir(parents=True, exist_ok=True)
        (ws / "evidence" / "C002.txt").write_text("Actual content on disk", encoding="utf-8")
        fake_hash = f"sha256:{hashlib.sha256(b'Tampered fake content').hexdigest()}"
        tamper_row = {
            "claim_id": "C002",
            "claim": "Actual content on disk.",
            "evidence": "Actual content on disk",
            "quote_or_anchor": "Actual content on disk",
            "source_url": "https://example.com/source",
            "snapshot_path": "evidence/C002.txt",
            "content_hash": fake_hash,
            "confidence": "high",
        }
        report_text2 = "# Data\n\nActual content on disk. [ref:C002]\n"
        (ws / "report2.md").write_text(report_text2, encoding="utf-8")
        spans2, errs2 = report_render.parse_report_spans(report_text2, ws, [tamper_row], strict=True)
        assert any("SNAPSHOT_TAMPER" in e for e in errs2)

        sidecar2 = report_render.generate_report_claims_sidecar(
            ws, ws / "report2.md", [tamper_row], spans2, strict=True, errors=errs2
        )
        assert sidecar2["review_decision"]["status"] == "rejected"


def test_vdr05_wrong_source_binding_rejection():
    """VDR05: Quote exists in Source A, but claim is bound to Source B whose snapshot lacks the quote.

    Evaluator detects cross-source mismatch and rejects binding.
    """
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "evidence").mkdir(parents=True, exist_ok=True)
        (ws / "evidence" / "source_a.txt").write_text("Alpha feature active.", encoding="utf-8")
        (ws / "evidence" / "source_b.txt").write_text("Beta feature pending.", encoding="utf-8")

        # Claim claims Alpha feature, but references source B snapshot
        hash_b = f"sha256:{hashlib.sha256(b'Beta feature pending.').hexdigest()}"
        row = {
            "claim_id": "C005",
            "claim": "Alpha feature active.",
            "evidence": "Alpha feature active.",
            "quote_or_anchor": "Alpha feature active.",
            "source_url": "https://example.com/source_b",
            "snapshot_path": "evidence/source_b.txt",
            "content_hash": hash_b,
            "confidence": "high",
        }
        res = quality_eval.classify_claim_evidence(
            row["claim"], row["evidence"], row, workspace=ws
        )
        assert res["status"] in {"unsupported", "contradicts", "insufficient"}
        assert res.get("supports_claim") is False
        assert res.get("reason") in {"quote_not_in_snapshot", "quote_not_found"}
