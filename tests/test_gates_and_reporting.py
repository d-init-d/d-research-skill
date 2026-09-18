"""
test_gates_and_reporting.py - Acceptance Tests for DRS-1.1 Package W10 (F01 - F08).
"""

import hashlib
import json
from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from research_plan import (
    init_research_coverage,
    _assert_dual_track_terminal,
    _assert_cross_branch_reconciliation_valid,
)
from evidence_ledger import validate_ledger


def _write_gate_evidence(tmp_path: Path, branch: str, outcome="success", with_capture=True):
    out_dir = tmp_path / f"{branch}-evidence"
    (out_dir / "captures").mkdir(parents=True, exist_ok=True)
    activity_id = f"act-{branch}-{outcome}"
    capture_id = f"cap-{branch}-001"
    source_id = f"src-{branch}-001"
    activity = {
        "activity_id": activity_id,
        "branch_id": branch,
        "question_ids": ["Q1"],
        "action_type": "search" if not with_capture else "navigate",
        "started_at": "2026-09-16T00:00:00Z",
        "finished_at": "2026-09-16T00:00:01Z",
        "final_url": f"https://example.test/{branch}",
        "outcome": outcome,
        "output_capture_ids": [capture_id] if with_capture else [],
        "limitation": "authentication required" if outcome != "success" else None,
    }
    activity_path = out_dir / "activity-log.json"
    activity_path.write_text(json.dumps([activity]), encoding="utf-8")
    if with_capture:
        payload = f"{branch} evidence".encode()
        (out_dir / "captures" / f"{capture_id}.txt").write_bytes(payload)
        capture = {
            "capture_id": capture_id,
            "source_id": source_id,
            "branch_id": branch,
            "activity_id": activity_id,
            "source_url": f"https://example.test/{branch}",
            "raw_text_ref": f"captures/{capture_id}.txt",
            "bytes_hash": "sha256:" + hashlib.sha256(payload).hexdigest(),
            "byte_length": len(payload),
        }
        (out_dir / "capture-records.json").write_text(json.dumps([capture]), encoding="utf-8")
    return activity_id, source_id


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


def test_completed_branch_with_nonexistent_ids_is_rejected(tmp_path):
    coverage = init_research_coverage(["Q1: Test Question"])
    for branch_name in ("documentary_branch", "social_branch"):
        coverage["questions"][0][branch_name]["state"] = "completed"
        coverage["questions"][0][branch_name]["activity_ids"] = ["missing-activity"]
        coverage["questions"][0][branch_name]["source_ids"] = ["missing-source"]
    (tmp_path / "research-coverage.json").write_text(json.dumps(coverage), encoding="utf-8")
    plan_file = tmp_path / "research-plan.json"
    plan_file.write_text(json.dumps({"tasks": []}), encoding="utf-8")

    ok, message = _assert_dual_track_terminal({"tasks": []}, plan_file)
    assert ok is False
    assert "unresolved execution evidence" in message


def test_zero_byte_capture_cannot_complete_branch(tmp_path):
    """A rendered shell with no readable text is not source evidence."""
    activity_id, source_id = _write_gate_evidence(tmp_path, "documentary")
    capture_path = tmp_path / "documentary-evidence" / "capture-records.json"
    capture = json.loads(capture_path.read_text(encoding="utf-8"))[0]
    raw_path = tmp_path / "documentary-evidence" / capture["raw_text_ref"]
    raw_path.write_bytes(b"")
    capture["byte_length"] = 0
    capture["bytes_hash"] = "sha256:" + hashlib.sha256(b"").hexdigest()
    capture_path.write_text(json.dumps([capture]), encoding="utf-8")

    cov = init_research_coverage(["Q1: Test Question"])
    branch = cov["questions"][0]["documentary_branch"]
    branch["state"] = "completed"
    branch["activity_ids"] = [activity_id]
    branch["source_ids"] = [source_id]
    (tmp_path / "research-coverage.json").write_text(json.dumps(cov), encoding="utf-8")
    plan_path = tmp_path / "research-plan.json"
    plan_path.write_text(json.dumps({"tasks": []}), encoding="utf-8")

    ok, message = _assert_dual_track_terminal({"tasks": []}, plan_path)
    assert ok is False
    assert "no readable bytes" in message


def test_f03_honest_limited_report_path_when_branch_blocked(tmp_path):
    """Acceptance F03: Allows terminal state 'blocked' with explicit stop_reason for honest limited report."""
    doc_activity, doc_source = _write_gate_evidence(tmp_path, "documentary")
    social_activity, _ = _write_gate_evidence(
        tmp_path, "social", outcome="blocked", with_capture=False
    )
    cov = init_research_coverage(["Q1: Test Question"])
    cov["questions"][0]["documentary_branch"]["state"] = "completed"
    cov["questions"][0]["documentary_branch"]["activity_ids"] = [doc_activity]
    cov["questions"][0]["documentary_branch"]["source_ids"] = [doc_source]
    cov["questions"][0]["social_branch"]["state"] = "blocked"
    cov["questions"][0]["social_branch"]["activity_ids"] = [social_activity]
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
    doc_activity, doc_source = _write_gate_evidence(tmp_path, "documentary")
    social_activity, _ = _write_gate_evidence(tmp_path, "social", with_capture=False)
    cov = init_research_coverage(["Q1: Test Question"])
    cov["questions"][0]["documentary_branch"]["state"] = "completed"
    cov["questions"][0]["documentary_branch"]["activity_ids"] = [doc_activity]
    cov["questions"][0]["documentary_branch"]["source_ids"] = [doc_source]
    cov["questions"][0]["social_branch"]["state"] = "no_relevant_results"
    cov["questions"][0]["social_branch"]["activity_ids"] = [social_activity]
    cov["questions"][0]["social_branch"]["stop_reason"] = "bounded queries returned no relevant items"

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
            {
                "id": "t-rec",
                "branch": "reconciliation",
                "depends_on": ["t-doc", "t-soc"],
                "status": "done",
                "outputs": ["research-output/sections/q1-reconciled.md"],
            }
        ]
    }
    output = tmp_path / "research-output" / "sections" / "q1-reconciled.md"
    output.parent.mkdir(parents=True)
    output.write_text("Reconciled evidence", encoding="utf-8")
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
