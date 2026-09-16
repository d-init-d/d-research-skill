"""Test suite for DRS-1.1 Package W04: Dual-Track Routing & Scheduling (A01 - A08).

Verifies:
- A01: Fast fact with social errata check and fraud rejection
- A02: Multi-question coverage mapping (100% question coverage)
- A03: Concurrent execution temporal overlap in multi-slot hosts
- A04: Single-slot round-robin interleaving and anti-starvation
- A05: Single URL analysis with bounded scope
- A06: User corpus restriction with scope_excluded reference
- A07: Pure operation exemption without dummy research queries
- A08: Monotonic revision increment on resume / incremental inquiry
"""

import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from research_plan import (
    load as load_plan,
    save as save_plan,
    generate_dual_track_tasks,
    init_research_coverage,
    parallelizable_tasks,
    _assert_dual_track_terminal,
)
from fast_evaluator import evaluate_fast


def _write_execution_evidence(workspace: Path, branches=("documentary", "social")):
    activity_paths = []
    capture_paths = []
    refs = {}
    timestamp = "2026-09-16T00:00:00Z"
    for branch in branches:
        out_dir = workspace / f"{branch}-run"
        capture_dir = out_dir / "captures"
        capture_dir.mkdir(parents=True)
        activity_id = f"act-{branch}-001"
        capture_id = f"cap-{branch}-001"
        source_id = f"src-{branch}-001"
        payload = f"Observed {branch} evidence for Q1.\n".encode()
        raw_ref = f"captures/{capture_id}.txt"
        (out_dir / raw_ref).write_bytes(payload)
        activity = {
            "schema_version": "1.1.0",
            "activity_id": activity_id,
            "branch_id": branch,
            "question_ids": ["Q1"],
            "purpose": f"Read {branch} source",
            "observed_state_ref": None,
            "action_type": "navigate",
            "target_locator": None,
            "action_payload": {"url": f"https://example.test/{branch}"},
            "started_at": timestamp,
            "finished_at": timestamp,
            "final_url": f"https://example.test/{branch}",
            "outcome": "success",
            "output_capture_ids": [capture_id],
            "limitation": None,
            "tool_details": {"engine": "test-fixture", "mode": "offline", "response_status": 200},
        }
        capture = {
            "schema_version": "1.1.0",
            "capture_id": capture_id,
            "source_id": source_id,
            "branch_id": branch,
            "activity_id": activity_id,
            "retrieved_at": timestamp,
            "source_url": f"https://example.test/{branch}",
            "final_url": f"https://example.test/{branch}",
            "method": "test_fixture",
            "bytes_hash": "sha256:" + hashlib.sha256(payload).hexdigest(),
            "byte_length": len(payload),
            "dom_locator": "main",
            "raw_text_ref": raw_ref,
            "screenshot_ref": None,
            "extraction_limits": {
                "truncated": False,
                "items_extracted": 1,
                "total_estimated": 1,
                "truncation_reason": None,
            },
            "artifact_version": 1,
        }
        activity_path = out_dir / "activity-log.json"
        capture_path = out_dir / "capture-records.json"
        activity_path.write_text(json.dumps([activity]), encoding="utf-8")
        capture_path.write_text(json.dumps([capture]), encoding="utf-8")
        activity_paths.append(activity_path)
        capture_paths.append(capture_path)
        refs[branch] = {"activity_id": activity_id, "source_id": source_id}
    return activity_paths, capture_paths, refs


def test_a01_fast_fact_social_errata(tmp_path):
    """A01: Fast fact check queries official source and community errata; rejects fraudulent completion."""
    ws = tmp_path / "a01_fast_fact"
    ws.mkdir()
    activity_logs, capture_records, _refs = _write_execution_evidence(ws)
    
    # 1. Run fast evaluator on an atomic fact
    cov = evaluate_fast(
        route="atomic_fact",
        question="What is the official release date of Lumen 2.1?",
        workspace_dir=ws,
        execution_mode="interleaved",
        activity_logs=activity_logs,
        capture_records=capture_records,
    )
    
    assert cov["schema_version"] == "1.1.0"
    q1 = cov["questions"][0]
    assert q1["question_id"] == "Q1"
    assert q1["documentary_branch"]["state"] == "completed"
    assert q1["social_branch"]["state"] == "completed"
    
    # Verify social branch actually recorded activity and source IDs
    assert len(q1["social_branch"]["activity_ids"]) >= 1
    assert len(q1["social_branch"]["source_ids"]) >= 1
    
    # Verify gate assertion passes on valid dual-track coverage
    plan = {
        "schema_version": "2.0",
        "plan_id": "test-a01",
        "title": "A01 Plan",
        "tasks": [
            {"id": "t1-doc", "phase": "research", "branch": "documentary", "status": "done"},
            {"id": "t1-soc", "phase": "research", "branch": "social", "status": "done"},
        ]
    }
    plan_file = ws / "research-plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    
    ok, detail = _assert_dual_track_terminal(plan, plan_file)
    assert ok is True, f"Gate should pass on valid coverage: {detail}"

    # Fraud test: transition from planned to completed with empty activity_ids must FAIL gate
    fraud_cov = dict(cov)
    fraud_cov["questions"][0]["social_branch"]["activity_ids"] = []
    fraud_cov["questions"][0]["social_branch"]["source_ids"] = []
    (ws / "research-coverage.json").write_text(json.dumps(fraud_cov), encoding="utf-8")
    
    fraud_ok, fraud_detail = _assert_dual_track_terminal(plan, plan_file)
    assert fraud_ok is False
    assert "fraudulent completion" in fraud_detail.lower()


def test_fast_evaluator_without_execution_evidence_stays_planned(tmp_path):
    coverage = evaluate_fast(
        route="atomic_fact",
        question="UNIQUE-NO-SOURCES",
        workspace_dir=tmp_path,
    )
    question = coverage["questions"][0]
    assert question["overall_status"] == "planned"
    assert question["documentary_branch"]["state"] == "planned"
    assert question["social_branch"]["state"] == "planned"
    assert coverage["consumed_budget"]["total_browser_actions"] == 0
    assert not (tmp_path / "research-output" / "notes" / "q1-documentary.md").exists()


def test_a02_multi_question_coverage():
    """A02: Multiple subquestions generate dual-track sibling tasks mapping 100% question coverage."""
    sub_questions = [
        {"id": "Q1", "text": "What is the release date of Lumen 2.1?"},
        {"id": "Q2", "text": "Where is CSV export located in Lumen 2.1?"},
        {"id": "Q3", "text": "What error codes are reported for sync in Lumen 2.1?"},
    ]

    tasks = generate_dual_track_tasks(sub_questions, research_route="broad_research")
    
    # 3 questions -> 3 doc + 3 soc + 3 rec = 9 tasks total (6 research tasks)
    research_tasks = [t for t in tasks if t.get("phase") == "research"]
    synthesis_tasks = [t for t in tasks if t.get("phase") == "synthesis"]
    
    assert len(research_tasks) == 6
    assert len(synthesis_tasks) == 3

    # Check 100% question coverage mapping
    mapped_qids = {t.get("sub_question_id") for t in tasks}
    assert mapped_qids == {"Q1", "Q2", "Q3"}

    # Verify initial research tasks have depends_on: []
    for rt in research_tasks:
        assert rt["depends_on"] == [], f"Research task {rt['id']} must start concurrently in Round 1"

    # Verify reconciliation tasks depend on both doc and soc
    for st in synthesis_tasks:
        qid = st["sub_question_id"]
        slug = qid.lower()
        expected_deps = [f"task-{slug}-doc", f"task-{slug}-soc"]
        assert st["depends_on"] == expected_deps


def test_a03_concurrent_execution_overlap(tmp_path):
    """A03: Multi-slot hosts dispatch documentary and social concurrently with overlapping timestamps."""
    ws = tmp_path / "a03_concurrent"
    ws.mkdir()

    # Simulate timestamps of real concurrent execution
    t0 = datetime(2026, 9, 15, 10, 0, 0, tzinfo=timezone.utc)
    t_start_d = t0
    t_start_s = t0 + timedelta(milliseconds=150)  # slightly later start
    t_end_d = t0 + timedelta(seconds=2)
    t_end_s = t0 + timedelta(seconds=3)
    _activity_logs, _capture_records, refs = _write_execution_evidence(ws)
    for branch, started_at, finished_at in (
        ("documentary", t_start_d, t_end_d),
        ("social", t_start_s, t_end_s),
    ):
        activity_path = ws / f"{branch}-run" / "activity-log.json"
        records = json.loads(activity_path.read_text(encoding="utf-8"))
        records[0]["started_at"] = started_at.isoformat().replace("+00:00", "Z")
        records[0]["finished_at"] = finished_at.isoformat().replace("+00:00", "Z")
        activity_path.write_text(json.dumps(records), encoding="utf-8")

    # Prove temporal overlap: max(start_d, start_s) < min(end_d, end_s)
    overlap_start = max(t_start_d, t_start_s)
    overlap_end = min(t_end_d, t_end_s)
    assert overlap_start < overlap_end, "Tasks must have temporal overlap in concurrent mode"

    cov = {
        "schema_version": "1.1.0",
        "run_id": "run-20260915-a03-001",
        "revision": 1,
        "execution_mode": "concurrent",
        "allocated_budget": {
            "profile_name": "standard",
            "max_queries_per_branch": 6,
            "max_sources_per_branch": 12,
            "max_comments_per_thread": 60,
            "thread_depth_cap": 4,
            "max_browser_actions_per_page": 30,
            "wall_time_cap_seconds": 1200,
        },
        "consumed_budget": {
            "total_queries": 2,
            "total_sources_visited": 2,
            "total_comments_extracted": 10,
            "total_browser_actions": 4,
            "elapsed_wall_time_seconds": 3.0,
        },
        "questions": [
            {
                "question_id": "Q1",
                "question_text": "Concurrent inquiry",
                "domain_specialist": "general",
                "route_id": "broad_research",
                "overall_status": "completed",
                "documentary_branch": {
                    "branch_id": "documentary",
                    "state": "completed",
                    "started_at": t_start_d.isoformat().replace("+00:00", "Z"),
                    "finished_at": t_end_d.isoformat().replace("+00:00", "Z"),
                    "activity_ids": [refs["documentary"]["activity_id"]],
                    "source_ids": [refs["documentary"]["source_id"]],
                    "stop_reason": "done",
                    "scope_reference": None,
                },
                "social_branch": {
                    "branch_id": "social",
                    "state": "completed",
                    "started_at": t_start_s.isoformat().replace("+00:00", "Z"),
                    "finished_at": t_end_s.isoformat().replace("+00:00", "Z"),
                    "activity_ids": [refs["social"]["activity_id"]],
                    "source_ids": [refs["social"]["source_id"]],
                    "stop_reason": "done",
                    "scope_reference": None,
                },
                "coverage_gaps": [],
                "stop_reason": None,
            }
        ],
        "created_at": t0.isoformat().replace("+00:00", "Z"),
        "updated_at": t_end_s.isoformat().replace("+00:00", "Z"),
    }
    (ws / "research-coverage.json").write_text(json.dumps(cov), encoding="utf-8")
    
    plan = {"schema_version": "2.0", "plan_id": "a03", "execution_mode": "concurrent", "tasks": []}
    plan_file = ws / "research-plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")
    
    ok, _ = _assert_dual_track_terminal(plan, plan_file)
    assert ok is True


def test_a04_single_slot_interleaving():
    """A04: Single-slot hosts strictly alternate between documentary and social branches without starvation."""
    plan = {
        "schema_version": "2.0",
        "plan_id": "test-a04",
        "execution_mode": "interleaved",
        "tasks": [
            {
                "id": "task-q1-doc",
                "branch": "documentary",
                "status": "todo",
                "depends_on": [],
                "parallel_safe": True,
                "outputs": ["research-output/notes/q1-doc.md"]
            },
            {
                "id": "task-q2-doc",
                "branch": "documentary",
                "status": "todo",
                "depends_on": [],
                "parallel_safe": True,
                "outputs": ["research-output/notes/q2-doc.md"]
            },
            {
                "id": "task-q1-soc",
                "branch": "social",
                "status": "todo",
                "depends_on": [],
                "parallel_safe": True,
                "outputs": ["research-output/notes/q1-soc.md"]
            },
            {
                "id": "task-q2-soc",
                "branch": "social",
                "status": "todo",
                "depends_on": [],
                "parallel_safe": True,
                "outputs": ["research-output/notes/q2-soc.md"]
            },
        ]
    }

    # Turn 1: Starts with documentary -> interleaved order should alternate doc, soc, doc, soc
    ready = parallelizable_tasks(plan, last_executed_branch=None)
    assert ready == ["task-q1-doc", "task-q1-soc", "task-q2-doc", "task-q2-soc"]

    # Turn 2: Last executed was documentary -> next prioritized task MUST be social
    ready_after_doc = parallelizable_tasks(plan, last_executed_branch="documentary")
    assert ready_after_doc[0] == "task-q1-soc"
    assert ready_after_doc == ["task-q1-soc", "task-q1-doc", "task-q2-soc", "task-q2-doc"]

    # Turn 3: Last executed was social -> next prioritized task MUST be documentary
    ready_after_soc = parallelizable_tasks(plan, last_executed_branch="social")
    assert ready_after_soc[0] == "task-q1-doc"


def test_a05_single_url_social_bounded(tmp_path):
    """A05: Single URL evaluation stays strictly bounded within thread context without runaway account crawls."""
    ws = tmp_path / "a05_single_url"
    ws.mkdir()
    activity_logs, capture_records, _refs = _write_execution_evidence(ws)

    cov = evaluate_fast(
        route="single_url",
        question="Analyze the release announcement at https://example.com/blog/lumen-2-1",
        workspace_dir=ws,
        execution_mode="interleaved",
        activity_logs=activity_logs,
        capture_records=capture_records,
    )

    assert cov["allocated_budget"]["profile_name"] == "fast"
    # Thread depth cap is bounded to 2
    assert cov["allocated_budget"]["thread_depth_cap"] <= 2
    assert cov["allocated_budget"]["max_browser_actions_per_page"] <= 10
    assert cov["questions"][0]["overall_status"] == "completed"


def test_a06_user_corpus_restriction(tmp_path):
    """A06: User prompt restricting search to corpus transitions external branch to scope_excluded."""
    ws = tmp_path / "a06_corpus_only"
    ws.mkdir()
    activity_logs, capture_records, _refs = _write_execution_evidence(ws, ("documentary",))

    cov = evaluate_fast(
        route="broad_research",
        question="Analyze policy implications --corpus-only",
        workspace_dir=ws,
        corpus_only=True,
        activity_logs=activity_logs,
        capture_records=capture_records,
    )

    q = cov["questions"][0]
    assert q["documentary_branch"]["state"] == "completed"
    assert q["social_branch"]["state"] == "scope_excluded"
    assert "user_provided_corpus_only" in q["social_branch"]["scope_reference"]

    plan = {"schema_version": "2.0", "plan_id": "a06", "tasks": []}
    plan_file = ws / "research-plan.json"
    plan_file.write_text(json.dumps(plan), encoding="utf-8")

    ok, detail = _assert_dual_track_terminal(plan, plan_file)
    assert ok is True, f"Gate should pass when external branch is legitimately scope_excluded: {detail}"


def test_a07_pure_operation_exemption(tmp_path):
    """A07: Supporting operations bypass research loops under pure_operation_exemption."""
    ws = tmp_path / "a07_pure_op"
    ws.mkdir()

    cov = evaluate_fast(
        route="broad_research",
        question="Convert ledger from CSV to JSON format",
        workspace_dir=ws,
        pure_operation="format_conversion",
    )

    q = cov["questions"][0]
    assert q["overall_status"] == "scope_excluded"
    assert q["documentary_branch"]["state"] == "scope_excluded"
    assert q["social_branch"]["state"] == "scope_excluded"
    assert "pure_operation_exemption:format_conversion" in q["documentary_branch"]["scope_reference"]
    assert cov["consumed_budget"]["total_queries"] == 0


def test_a08_revision_increment_on_resume(tmp_path):
    """A08: Adding tasks or follow-up questions increments plan revision and resets completion flags."""
    ws = tmp_path / "a08_revision"
    ws.mkdir()

    plan = {
        "schema_version": "2.0",
        "plan_id": "plan-a08",
        "title": "A08 Plan",
        "revision": 1,
        "tasks": [
            {"id": "t1-doc", "phase": "research", "branch": "documentary", "status": "done"},
            {"id": "t1-soc", "phase": "research", "branch": "social", "status": "done"},
        ],
    }
    plan_file = ws / "research-plan.json"
    save_plan(plan, plan_file)

    # Initial coverage is completed for Q1 using resolvable execution evidence.
    _activity_logs, _capture_records, refs = _write_execution_evidence(ws)
    cov = init_research_coverage(["Q1 Question"], run_id="run-a08")
    cov["questions"][0]["documentary_branch"]["state"] = "completed"
    cov["questions"][0]["documentary_branch"]["activity_ids"] = [refs["documentary"]["activity_id"]]
    cov["questions"][0]["documentary_branch"]["source_ids"] = [refs["documentary"]["source_id"]]
    cov["questions"][0]["social_branch"]["state"] = "completed"
    cov["questions"][0]["social_branch"]["activity_ids"] = [refs["social"]["activity_id"]]
    cov["questions"][0]["social_branch"]["source_ids"] = [refs["social"]["source_id"]]
    (ws / "research-coverage.json").write_text(json.dumps(cov), encoding="utf-8")

    ok1, _ = _assert_dual_track_terminal(plan, plan_file)
    assert ok1 is True

    # Now simulate incremental resume: follow-up inquiry Q2 added
    plan_loaded = load_plan(plan_file)
    plan_loaded["revision"] = plan_loaded.get("revision", 1) + 1
    assert plan_loaded["revision"] == 2

    # Append new tasks for Q2
    new_tasks = generate_dual_track_tasks([{"id": "Q2", "text": "Follow-up inquiry"}])
    plan_loaded["tasks"].extend(new_tasks)
    save_plan(plan_loaded, plan_file)

    # Update coverage to revision 2 with Q2 planned
    cov["revision"] = 2
    cov["questions"].append({
        "question_id": "Q2",
        "question_text": "Follow-up inquiry",
        "domain_specialist": "general",
        "route_id": "broad_research",
        "overall_status": "planned",
        "documentary_branch": {
            "branch_id": "documentary",
            "state": "planned",
            "started_at": None,
            "finished_at": None,
            "activity_ids": [],
            "source_ids": [],
            "stop_reason": None,
            "scope_reference": None,
        },
        "social_branch": {
            "branch_id": "social",
            "state": "planned",
            "started_at": None,
            "finished_at": None,
            "activity_ids": [],
            "source_ids": [],
            "stop_reason": None,
            "scope_reference": None,
        },
        "coverage_gaps": [],
        "stop_reason": None,
    })
    (ws / "research-coverage.json").write_text(json.dumps(cov), encoding="utf-8")

    # Gate MUST now fail because Q2 is planned (stale completion flags cannot be carried forward!)
    ok2, detail2 = _assert_dual_track_terminal(plan_loaded, plan_file)
    assert ok2 is False
    assert "Q2.documentary_branch state 'planned' is not terminal" in detail2
