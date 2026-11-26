"""Regression suite for D Research v3.9.0-rc.1 upgrades (stdlib unittest)."""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import evidence_ledger  # noqa: E402
import harvest_terms  # noqa: E402
import investigation_policy  # noqa: E402
import lineage_tracker  # noqa: E402
import reconciliation  # noqa: E402
import source_grounding  # noqa: E402


class TestV390UpgradeRegressions(unittest.TestCase):
    def test_source_grounding_contractions_percent_and_multisub(self) -> None:
        r_didn = source_grounding.assess_paraphrase_grounding(
            "The central bank didn’t raise interest rates in September 2026.",
            "The central bank raised interest rates in September 2026.",
        )
        self.assertEqual(r_didn["status"], "contradicted")

        r_cannot = source_grounding.assess_paraphrase_grounding(
            "The regulator cannot approve unverified disclosures under current rules.",
            "The regulator approves unverified disclosures under current rules.",
        )
        self.assertEqual(r_cannot["status"], "contradicted")

        r_pct = source_grounding.assess_paraphrase_grounding(
            "Vietnam CPI rose 4.9 percent in 2026.",
            "Vietnam CPI rose 4.9% in 2026",
        )
        self.assertEqual(r_pct["status"], "paraphrase_supported")
        self.assertTrue(r_pct["numeric_match"])

        r_pct_vi = source_grounding.assess_paraphrase_grounding(
            "Lạm phát tăng 4.9 phần trăm trong năm 2026.",
            "Lạm phát tăng 4.9% năm 2026",
        )
        self.assertEqual(r_pct_vi["status"], "paraphrase_supported")

        multi_src = "Vietnam exported 10% more wafers in Q1. Semiconductor FDI reached 1.6 billion USD in 2026."
        multi_claim = "Vietnam exported 10% more wafers in Q1. Semiconductor FDI reached 1.6 billion USD in 2026."
        r_multi = source_grounding.assess_paraphrase_grounding(multi_src, multi_claim)
        self.assertEqual(r_multi["status"], "literal_supported")

        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "ledger.csv"
            with ledger.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(
                    fh,
                    fieldnames=["claim_id", "claim", "quote_or_anchor", "evidence", "record_type", "source_url"],
                )
                writer.writeheader()
                writer.writerow({
                    "claim_id": "C1",
                    "claim": "Vietnam semiconductor FDI reached 1.6 billion USD in 2025.",
                    "quote_or_anchor": "semiconductor FDI reached 1.6 billion USD in 2025",
                    "evidence": "MPI Official Report states Vietnam semiconductor FDI reached 1.6 billion USD in 2025.",
                    "record_type": "claim",
                    "source_url": "https://mpi.gov.vn/report-2025",
                })
            audit = source_grounding.audit_ledger_grounding(ledger)
            self.assertEqual(audit["findings"][0]["status"], "paraphrase_supported")

    def test_lineage_domain_clustering_and_official_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "ledger.csv"
            with ledger.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=evidence_ledger.FIELDS_V3_3)
                writer.writeheader()
                base = {k: "" for k in evidence_ledger.FIELDS_V3_3}
                r1 = dict(base, **{
                    "claim_id": "C01",
                    "claim": "MPI reported 1.6B semiconductor FDI.",
                    "sub_question": "Q1",
                    "source_title": "MPI Release A",
                    "source_url": "https://www.mpi.gov.vn/releases/a",
                    "source_type": "official",
                    "date_published": "2026-01-10",
                    "snapshot_status": "intact",
                    "verifiability": "direct_api",
                    "content_hash": "sha256:" + "a" * 64,
                    "record_type": "claim",
                    "source_access_class": "standard_public",
                    "subject_class": "organization",
                    "purpose_category": "general_research",
                    "policy_tier": "R0",
                    "speaker_identity": "official",
                    "speaker_relationship": "subject",
                    "content_origin": "original",
                    "data_sensitivity": "public",
                    "discovery_disposition": "evidence",
                    "reporting_disposition": "main_findings",
                    "redaction_class": "none",
                })
                r2 = dict(base, **{
                    "claim_id": "C02",
                    "claim": "Second unrelated MPI page note.",
                    "sub_question": "Q2",
                    "source_title": "MPI Release B",
                    "source_url": "https://mpi.gov.vn/releases/b",
                    "source_type": "official",
                    "date_published": "2026-01-11",
                    "snapshot_status": "live_intact",
                    "verifiability": "direct_api",
                    "content_hash": "sha256:" + "b" * 64,
                    "record_type": "claim",
                    "source_access_class": "standard_public",
                    "subject_class": "organization",
                    "purpose_category": "general_research",
                    "policy_tier": "R0",
                    "data_sensitivity": "public",
                    "discovery_disposition": "evidence",
                    "reporting_disposition": "main_findings",
                    "redaction_class": "none",
                })
                r3 = dict(base, **{
                    "claim_id": "L01",
                    "claim": "Social user A comment.",
                    "sub_question": "Q1",
                    "source_title": "Alice on X",
                    "source_url": "https://x.com/alice/status/1",
                    "source_type": "community",
                    "date_published": "2026-01-12",
                    "snapshot_status": "unknown",
                    "verifiability": "unverified",
                    "record_type": "lead",
                    "source_access_class": "standard_public",
                    "subject_class": "organization",
                    "purpose_category": "general_research",
                    "policy_tier": "R0",
                    "speaker_identity": "pseudonymous",
                    "speaker_relationship": "secondhand",
                    "content_origin": "original",
                    "data_sensitivity": "public",
                    "discovery_disposition": "lead_only",
                    "reporting_disposition": "non_official_unverified_leads",
                    "redaction_class": "none",
                })
                r4 = dict(base, **{
                    "claim_id": "L02",
                    "claim": "Social user B different post.",
                    "sub_question": "Q1",
                    "source_title": "Bob on X",
                    "source_url": "https://x.com/bob/status/2",
                    "source_type": "community",
                    "date_published": "2026-01-13",
                    "snapshot_status": "unknown",
                    "verifiability": "unverified",
                    "record_type": "lead",
                    "source_access_class": "standard_public",
                    "subject_class": "organization",
                    "purpose_category": "general_research",
                    "policy_tier": "R0",
                    "speaker_identity": "pseudonymous",
                    "speaker_relationship": "firsthand",
                    "content_origin": "original",
                    "data_sensitivity": "public",
                    "discovery_disposition": "lead_only",
                    "reporting_disposition": "non_official_unverified_leads",
                    "redaction_class": "none",
                })
                writer.writerows([r1, r2, r3, r4])

            self.assertEqual(evidence_ledger.validate_ledger(ledger), 0)
            tracker = lineage_tracker.LineageTracker()
            res = tracker.analyze_ledger(ledger)
            summary = res["lineage_summary"]
            # mpi.gov.vn clustered together (1 origin), while x.com/alice and x.com/bob stay separate (2 origins)
            self.assertEqual(summary["total_independent_origins"], 3)
            self.assertEqual(summary["origins"]["ORIGIN-C01"], ["C01", "C02"])
            by_id = {a["claim_id"]: a for a in res["assessments"]}
            self.assertEqual(by_id["C01"]["verification_state"], "supported")
            self.assertEqual(by_id["C01"]["reporting_disposition"], "main_findings")
            self.assertGreaterEqual(by_id["C01"]["independent_origin_count"], 1)
            self.assertEqual(by_id["L01"]["reporting_disposition"], "non_official_unverified_leads")
            self.assertEqual(by_id["L02"]["reporting_disposition"], "firsthand_unverified")

    def test_harvest_terms_nfc_short_syllables_and_acronyms(self) -> None:
        direct = (
            f"src1\t{unicodedata.normalize('NFC', 'tỷ giá')}\n"
            f"src2\t{unicodedata.normalize('NFD', 'tỷ giá')}\n"
        )
        res = harvest_terms.harvest(direct, threshold=2)
        self.assertEqual(res["confirmed"], ["tỷ giá"])

        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            (ws / "c1.txt").write_text(
                "AI tại VN giúp nâng ý thức, tối ưu ổ cứng và tránh ủ bệnh mà tăng năng suất.",
                encoding="utf-8",
            )
            (ws / "c2.txt").write_text(
                "Chiến lược AI ở VN cải thiện ý thức, sản xuất ổ cứng, ngừa ủ bệnh mà tăng trưởng tốt.",
                encoding="utf-8",
            )
            cap = ws / "caps.json"
            cap.write_text(
                json.dumps([
                    {"capture_id": "1", "source_id": "s1", "raw_text_ref": "c1.txt"},
                    {"capture_id": "2", "source_id": "s2", "raw_text_ref": "c2.txt"},
                ]),
                encoding="utf-8",
            )
            cap_res = harvest_terms.harvest_from_captures(cap, workspace_dir=ws, threshold=2)
            conf = {t.lower() for t in cap_res["confirmed"]}
            for expected in ("ý thức", "ổ cứng", "ủ bệnh", "ai", "vn"):
                self.assertIn(expected, conf)
            self.assertNotIn("mà tăng", conf)

    def test_integrity_normalization_and_same_branch_reconciliation(self) -> None:
        parser = investigation_policy.build_parser()
        args = parser.parse_args([
            "assess-source",
            "--source-access-class", "standard_public",
            "--speaker-identity", "official",
            "--speaker-relationship", "subject",
            "--origin", "original",
            "--integrity", "intact",
            "--data-sensitivity", "public",
            "--claim-impact", "material",
            "--claim-kind", "statement_made",
        ])
        out = investigation_policy.assess_source(args)
        self.assertEqual(out["reporting_disposition"], "main_findings")

        with tempfile.TemporaryDirectory() as td:
            ledger = Path(td) / "same_branch.csv"
            with ledger.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=evidence_ledger.FIELDS_LEGACY)
                writer.writeheader()
                writer.writerows([
                    {
                        "claim_id": "A1", "claim": "Policy rate is 5%", "sub_question": "Q1",
                        "source_url": "https://a.gov", "source_type": "official",
                        "contradiction": "none", "confidence": "high",
                    },
                    {
                        "claim_id": "A2", "claim": "Policy rate is 7%", "sub_question": "Q1",
                        "source_url": "https://b.gov", "source_type": "official",
                        "contradiction": "none", "confidence": "high",
                    },
                    {
                        "claim_id": "A3", "claim": "Ports handled 12M TEUs in 2025", "sub_question": "Q1",
                        "source_url": "https://c.gov", "source_type": "official",
                        "contradiction": "none", "confidence": "high",
                    },
                ])
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS_DIR / "reconciliation.py"), "--ledger", str(ledger)],
                capture_output=True,
                text=True,
                check=True,
            )
            rep = json.loads(proc.stdout)
            self.assertEqual(rep["total_discrepancies"], 1)
            self.assertEqual(rep["pairs"][0]["initial_claim_id"], "A1")
            self.assertEqual(rep["pairs"][0]["competing_claim_id"], "A2")

    def test_node_cli_help_ssrf_and_missing_browser_ux(self) -> None:
        for script in ("web_search.mjs", "api_fetch.mjs"):
            proc = subprocess.run(
                ["node", str(SCRIPTS_DIR / script), "--help"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("Usage:", proc.stdout)

        ssrf_check = subprocess.run(
            [
                "node", "-e",
                "import('./scripts/lib/ssrf_guards.mjs').then(m => {"
                " if (!m.isPrivateIpOrBlockedHost('0177.0.0.1') || !m.isPrivateIpOrBlockedHost('2130706433')) process.exit(1);"
                "});",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(ssrf_check.returncode, 0, ssrf_check.stderr)

        # Verify positional URL parsing works and never throws 'Unknown argument'
        for script in ("playwright_probe.mjs", "playwright_extract.mjs", "playwright_crawl.mjs"):
            proc = subprocess.run(
                ["node", str(SCRIPTS_DIR / script), "https://example.com"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotIn("Unknown argument", proc.stderr)
            if proc.stdout.strip().startswith("{"):
                parsed = json.loads(proc.stdout)
                if "blockers" in parsed and "browser_launch_failure" in parsed["blockers"]:
                    self.assertIn("missing_browser_capability", parsed.get("limitations", []))


if __name__ == "__main__":
    unittest.main()
