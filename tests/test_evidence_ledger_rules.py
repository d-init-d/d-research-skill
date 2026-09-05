import csv
import sys
import tempfile
from pathlib import Path

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import evidence_ledger
import report_render


def test_d20_lead_and_blocker_segregation():
    """D20: Lead and blocker rows are segregated; cannot be promoted to main findings."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        ledger_path = ws / "evidence-ledger.csv"
        fields = evidence_ledger.FIELDS  # Full 37-column policy header
        rows = [
            {
                "claim_id": "C100",
                "claim": "Verified factual finding",
                "source_title": "Official Announcement",
                "source_url": "https://example.com/official",
                "source_type": "official",
                "access_method": "fetch",
                "evidence": "verified",
                "contradiction": "none",
                "confidence": "high",
                "record_type": "claim",
                "source_access_class": "standard_public",
                "subject_class": "organization",
                "purpose_category": "general_research",
                "policy_tier": "R1",
                "data_sensitivity": "public",
                "discovery_disposition": "evidence",
                "reporting_disposition": "main_findings",
                "redaction_class": "none",
            },
            {
                "claim_id": "L100",
                "claim": "Unverified social media lead",
                "source_title": "Forum Post",
                "source_url": "https://example.com/forum",
                "source_type": "community",
                "access_method": "fetch",
                "evidence": "lead only",
                "contradiction": "none",
                "confidence": "low",
                "record_type": "lead",
                "source_access_class": "standard_public",
                "subject_class": "organization",
                "purpose_category": "general_research",
                "policy_tier": "R1",
                "speaker_identity": "pseudonymous",
                "speaker_relationship": "commentary",
                "content_origin": "original",
                "lineage_id": "lineage:forum-1",
                "data_sensitivity": "public",
                "discovery_disposition": "lead_only",
                "reporting_disposition": "non_official_unverified_leads",
                "redaction_class": "none",
            },
        ]
        with ledger_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

        # Report incorrectly promoting lead L100 into Main findings
        bad_report = (
            "# Investigative report\n\n"
            "## Main findings\n\n"
            "Verified factual finding. [ref:C100]\n"
            "Unverified social media lead promoted as fact. [ref:L100]\n\n"
            "## Non-official / unverified leads\n\nNone.\n\n"
            "## Blocked / prohibited sources\n\nNone.\n\n"
            "## Contradictions and unknowns\n\nNone.\n"
        )
        (ws / "report.md").write_text(bad_report, encoding="utf-8")
        import argparse

        args = argparse.Namespace(
            workspace=str(ws), report="report.md", strict=True, allow_unreferenced=False
        )
        rc = report_render.cmd_lint(args)
        assert rc != 0


def test_d22_csv_rfc4180_unicode_integrity():
    """D22: Ledger CSV handles Unicode, RFC 4180 quotes, multiline fields, and detects duplicate IDs."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        ledger_path = ws / "evidence-ledger.csv"
        # 14-column minimal header
        cols = [
            "claim_id", "claim", "sub_question", "source_title", "source_url",
            "source_type", "date_published", "date_accessed", "access_method",
            "evidence", "quote_or_anchor", "contradiction", "confidence", "notes"
        ]

        # Multiline, escaped quotes, and Unicode text
        unicode_evidence = 'Dữ liệu xác thực có dấu tiếng Việt và ký tự đặc biệt: "Được phê duyệt" 100%.\nLine 2 tiếp tục.'
        rows = [
            {
                "claim_id": "C001",
                "claim": "Báo cáo tiếng Việt đã được phê duyệt.",
                "sub_question": "sq1",
                "source_title": "Bộ Thông tin",
                "source_url": "https://example.gov.vn",
                "source_type": "official",
                "date_published": "2026-01-01",
                "date_accessed": "2026-06-01",
                "access_method": "fetch",
                "evidence": unicode_evidence,
                "quote_or_anchor": "Được phê duyệt",
                "contradiction": "none",
                "confidence": "high",
                "notes": "Ghi chú nhiều dòng:\nDòng 1\nDòng 2",
            }
        ]

        with ledger_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            writer.writeheader()
            writer.writerows(rows)

        # Validate ledger preserves RFC 4180 multiline and Unicode integrity
        assert evidence_ledger.validate_ledger(ledger_path) == 0
        loaded = report_render._load_ledger(ledger_path)
        assert len(loaded) == 1
        assert "tiếng Việt" in loaded[0]["claim"]
        assert "Line 2" in loaded[0]["evidence"]

        # Duplicate claim_id detection
        dup_rows = list(rows) + [dict(rows[0])]
        dup_path = ws / "dup-ledger.csv"
        with dup_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            writer.writeheader()
            writer.writerows(dup_rows)
        assert evidence_ledger.validate_ledger(dup_path) != 0
