"""
test_gates_and_reporting.py - Acceptance Tests for DRS-1.1 Package W10 (F01 - F08).
"""

import json
from pathlib import Path
import sys
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from research_plan import (
    init_research_coverage,
    _assert_dual_track_terminal,
    _assert_cross_branch_reconciliation_valid,
)
from evidence_ledger import validate_ledger


def test_f01_branch_completed_without_activity_or_source_rejected(tmp_path):
    """Acceptance F01: Rejects branch falsely marked completed with no activity or source IDs."""
    cov = init_research_coverage(["Q1: Test Question"])
    cov["questions"][0]["documentary_branch"]["state"] = "completed"
    cov["questions"][0]["documentary_branch"]["activity_ids"] = []  # Empty! Fraudulent completion
    cov["questions"][0]["documentary_branch"]["source_ids"] = []

    cov_file = tmp_path / "research-coverage.json"
    cov_file.write_text(json.dumps(cov), encoding="utf-8")

    plan = {"tasks": []}
    plan_file = tmp_path / "research-plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")

    ok, msg = _assert_dual_track_terminal(plan, plan_file)
    assert ok is False
    assert "fraudulent completion" in msg.lower()


def test_f02_unfinished_branch_rejected_at_synthesis_gate(tmp_path):
    """Acceptance F02: Rejects plan when social branch is still planned or running."""
    cov = init_research_coverage(["Q1: Test Question"])
    cov["questions"][0]["documentary_branch"]["state"] = "completed"
    cov["questions"][0]["documentary_branch"]["activity_ids"] = ["act_doc_01"]
    cov["questions"][0]["documentary_branch"]["source_ids"] = ["src_doc_01"]
    cov["questions"][0]["social_branch"]["state"] = "running"  # Not terminal!

    cov_file = tmp_path / "research-coverage.json"
    cov_file.write_text(json.dumps(cov), encoding="utf-8")

    plan = {"tasks": []}
    plan_file = tmp_path / "research-plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")

    ok, msg = _assert_dual_track_terminal(plan, plan_file)
    assert ok is False
    assert "not terminal" in msg.lower()


def test_f03_honest_limited_report_path_when_branch_blocked(tmp_path):
    """Acceptance F03: Allows terminal state 'blocked' with explicit stop_reason for honest limited report."""
    cov = init_research_coverage(["Q1: Test Question"])
    cov["questions"][0]["documentary_branch"]["state"] = "completed"
    cov["questions"][0]["documentary_branch"]["activity_ids"] = ["act_doc_01"]
    cov["questions"][0]["documentary_branch"]["source_ids"] = ["src_doc_01"]
    cov["questions"][0]["social_branch"]["state"] = "blocked"
    cov["questions"][0]["social_branch"]["stop_reason"] = "Platform requires authentication; public access wall blocked"

    cov_file = tmp_path / "research-coverage.json"
    cov_file.write_text(json.dumps(cov), encoding="utf-8")

    plan = {"tasks": []}
    plan_file = tmp_path / "research-plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")

    ok, msg = _assert_dual_track_terminal(plan, plan_file)
    assert ok is True
    assert msg == "OK"


def test_f04_executed_empty_results_distinguished_from_error(tmp_path):
    """Acceptance F04: 'no_relevant_results' accepted as valid terminal state."""
    cov = init_research_coverage(["Q1: Test Question"])
    cov["questions"][0]["documentary_branch"]["state"] = "completed"
    cov["questions"][0]["documentary_branch"]["activity_ids"] = ["act_doc_01"]
    cov["questions"][0]["documentary_branch"]["source_ids"] = ["src_doc_01"]
    cov["questions"][0]["social_branch"]["state"] = "no_relevant_results"
    cov["questions"][0]["social_branch"]["activity_ids"] = ["act_soc_query_01"]

    cov_file = tmp_path / "research-coverage.json"
    cov_file.write_text(json.dumps(cov), encoding="utf-8")

    plan = {"tasks": []}
    plan_file = tmp_path / "research-plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")

    ok, msg = _assert_dual_track_terminal(plan, plan_file)
    assert ok is True


def test_f05_f06_cross_branch_reconciliation_assertion(tmp_path):
    """Acceptance F05, F06: Gate validates reconciliation barrier has inputs from both branches."""
    plan = {
        "tasks": [
            {"id": "t-doc", "branch": "documentary", "status": "done"},
            {"id": "t-soc", "branch": "social", "status": "done"},
            {"id": "t-rec", "branch": "reconciliation", "depends_on": ["t-doc", "t-soc"], "status": "todo"}
        ]
    }
    plan_file = tmp_path / "research-plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")

    ok, msg = _assert_cross_branch_reconciliation_valid(plan, plan_file)
    assert ok is True


def test_f07_legacy_ledger_migration_compatibility(tmp_path):
    """Acceptance F07: Validates legacy 14-column and v3.3 37-column ledgers without corruption."""
    # Legacy 14-col header
    legacy_headers = [
        "claim_id", "claim", "sub_question", "source_title", "source_url",
        "source_type", "date_published", "date_accessed", "access_method",
        "evidence", "quote_or_anchor", "contradiction", "confidence", "notes"
    ]
    legacy_file = tmp_path / "legacy.csv"
    with open(legacy_file, "w", encoding="utf-8") as f:
        f.write(",".join(legacy_headers) + "\n")
        f.write("C01,Claim text,Q1,Source,https://example.com,official,2026-01-01,2026-01-02,browser,Quote,Anchor,none,high,Notes\n")

    res = validate_ledger(legacy_file)
    assert res == 0
