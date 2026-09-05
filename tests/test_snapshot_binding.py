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
