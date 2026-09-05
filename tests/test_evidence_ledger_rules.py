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


def test_vdr21_ledger_schema_and_lead_separation():
    """VDR21: Ledger schemas 14/19/22/23/37, duplicate IDs, and lead/blocker segregation.

    Parses supported schemas, rejects duplicate IDs, and prevents leads from elevating to verified claims.
    """
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        # 1. Backward compatibility: 14, 19, 22, 23, 37 columns
        for col_set, name in [
            (evidence_ledger.FIELDS_LEGACY, "ledger_14.csv"),
            (evidence_ledger.FIELDS_V2_1, "ledger_19.csv"),
            (evidence_ledger.FIELDS_V3_0, "ledger_22.csv"),
            (evidence_ledger.FIELDS_V3_1, "ledger_23.csv"),
            (evidence_ledger.FIELDS_V3_3, "ledger_37.csv"),
        ]:
            lp = ws / name
            row = {c: "" for c in col_set}
            row["claim_id"] = "C001"
            row["claim"] = f"Test claim for {name}"
            row["source_title"] = "Source"
            row["source_url"] = "https://example.com"
            row["source_type"] = "official"
            row["confidence"] = "high"
            row["contradiction"] = "none"
            if "record_type" in col_set:
                row["record_type"] = "claim"
            if "snapshot_status" in col_set:
                row["snapshot_status"] = "intact"
            if "verifiability" in col_set:
                row["verifiability"] = "archive_snapshot"
            if "source_access_class" in col_set:
                row["source_access_class"] = "standard_public"
                row["subject_class"] = "organization"
                row["purpose_category"] = "general_research"
                row["policy_tier"] = "R1"
                row["data_sensitivity"] = "public"
                row["discovery_disposition"] = "evidence"
                row["reporting_disposition"] = "main_findings"
                row["redaction_class"] = "none"

            with lp.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=col_set)
                w.writeheader()
                w.writerow(row)

            assert evidence_ledger.validate_ledger(lp) == 0
            loaded = report_render._load_ledger(lp)
            assert len(loaded) == 1
            assert loaded[0]["claim_id"] == "C001"

        # 2. Duplicate IDs rejection
        dup_lp = ws / "dup.csv"
        with dup_lp.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=evidence_ledger.FIELDS_LEGACY)
            w.writeheader()
            w.writerow({"claim_id": "C001", "claim": "Claim 1", "source_title": "S1", "source_url": "https://a.com", "confidence": "high", "source_type": "official"})
            w.writerow({"claim_id": "C001", "claim": "Claim 2", "source_title": "S2", "source_url": "https://b.com", "confidence": "high", "source_type": "official"})
        assert evidence_ledger.validate_ledger(dup_lp) != 0

        # 3. Lead separation: lead rows are not counted as reportable factual claims
        lead_row = {c: "" for c in evidence_ledger.FIELDS_V3_3}
        lead_row["claim_id"] = "L001"
        lead_row["record_type"] = "lead"
        lead_row["confidence"] = "low"
        assert not report_render._row_is_reportable_claim(lead_row)
