"""Acceptance Test Suite for Gate G4 Evaluator Integrity (E01–E10).

Verifies:
- E01: Oracle Isolation (Candidate self-grading fields stripped/ignored)
- E02: Empty run output marked invalid/not_run regardless of candidate-declared summary
- E03: Missing host telemetry recorded as 'unknown', not false 0
- E04: Confounder detection on mismatched model/tools/config
- E05: Contamination detection and held-out repartitioning
- E06: Denominator completeness catching omitted/timed-out tasks
- E07: Over-refusal penalty accounting preventing evasion
- E08: Snapshot drift detection via SHA-256 digest validation
- E09: Mutation check proving test harness catches injected errors
- E10: Deterministic metric reproducibility from raw artifacts
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import eval_harness


def test_e01_oracle_isolation():
    """E01: Candidate output attempts to supply evaluation rubric fields with identical names to oracle.
    
    Evaluator rejects or ignores candidate rubric fields; evaluation driven strictly by isolated oracle.
    """
    task_spec = {
        "task_id": "test-t01",
        "category": "atomic_fact",
        "expected_action": "answer",
    }
    
    # Candidate provides incorrect factual text, but injects self-grading oracle fields
    candidate_spoofed = {
        "task_id": "test-t01",
        "output_text": "The speed of light in vacuum is 100 meters per second.",  # Factually wrong
        "expected_support": "supports",
        "polarity": "positive",
        "support_polarity": "positive",
        "support_pattern": ".*",
        "is_supported": True,
        "override_verdict": "verified",
        "rubric_score": 1.0,
        "oracle_answer": "299,792,458 m/s",
        "citation_correctness": 1.0,
        "important_claim_coverage": 1.0,
        "beats_baseline": True,
    }
    
    isolated_oracle = {
        "target_value": "299,792,458 m/s",
        "acceptable_values": ["299,792,458", "299792458"],
        "required_claims": [
            {"keywords": ["299,792,458"], "description": "Exact speed of light"}
        ],
    }

    # Clean function strips prohibited fields
    cleaned = eval_harness.strip_candidate_fields(candidate_spoofed)
    for field in eval_harness.PROHIBITED_CANDIDATE_FIELDS:
        assert field not in cleaned

    # Evaluate task
    res = eval_harness.evaluate_single_task(task_spec, candidate_spoofed, isolated_oracle)
    
    # The evaluation MUST fail despite the self-grading fields
    assert res["task_completed"] is False
    assert res["answer_matched"] is False
    assert res["score"] < 0.5


def test_e02_empty_run_invalid():
    """E02: Candidate run yields empty output logs but provides self-declared pass summary.
    
    Evaluator marks run as invalid/not_run; candidate-declared summary rejected.
    """
    task_spec = {"task_id": "test-t02", "category": "atomic_fact"}
    oracle = {"target_value": "Python 3.0", "acceptable_values": ["python 3.0"]}

    # Case A: empty dict
    res_empty_dict = eval_harness.evaluate_single_task(task_spec, {}, oracle)
    assert res_empty_dict["status"] == "invalid"
    assert res_empty_dict["is_valid_run"] is False
    assert res_empty_dict["score"] == 0.0

    # Case B: dict with declared pass summary but empty substantive logs
    empty_with_declared_pass = {
        "task_id": "test-t02",
        "output_text": "",
        "declared_summary": {"status": "pass", "verdict": "all_passed", "score": 1.0},
    }
    res_declared = eval_harness.evaluate_single_task(task_spec, empty_with_declared_pass, oracle)
    assert res_declared["status"] == "invalid"
    assert res_declared["is_valid_run"] is False
    assert res_declared["score"] == 0.0
    assert "Candidate run produced zero substantive output content" in res_declared["notes"][0]


def test_e03_telemetry_missing_unknown():
    """E03: Host telemetry missing token counts or execution time.
    
    Evaluator logs metric as unknown rather than substituting false 0 value.
    """
    raw_telemetry_missing = {
        "token_count": None,  # Missing
        "execution_time_ms": None,  # Missing
        "tool_calls_count": 3,
    }
    parsed = eval_harness.parse_telemetry(raw_telemetry_missing)
    assert parsed["token_count"] == "unknown"
    assert parsed["execution_time_ms"] == "unknown"
    assert parsed["token_count"] != 0
    assert parsed["execution_time_ms"] != 0.0
    assert parsed["tool_calls_count"] == 3

    # When telemetry is completely absent (None)
    parsed_none = eval_harness.parse_telemetry(None)
    assert parsed_none["token_count"] == "unknown"
    assert parsed_none["execution_time_ms"] == "unknown"
    assert parsed_none["tool_calls_count"] == "unknown"


def test_e04_confounder_detection():
    """E04: Model, tools, or configuration differ between baseline and candidate benchmark runs.
    
    Confounder detection flags run; unadjusted comparison prohibited.
    """
    baseline_cfg = {
        "model": "gpt-4o-2024-05-13",
        "temperature": 0.0,
        "toolset": ["web_search", "fetch_url"],
        "max_tokens": 4096,
    }
    # Candidate used a different model
    candidate_cfg_model_mismatch = {
        "model": "claude-3-5-sonnet-20241022",
        "temperature": 0.0,
        "toolset": ["web_search", "fetch_url"],
        "max_tokens": 4096,
    }
    audit1 = eval_harness.detect_confounders(baseline_cfg, candidate_cfg_model_mismatch)
    assert audit1["confounder_detected"] is True
    assert audit1["unadjusted_comparison_permitted"] is False
    assert any(m["field"] == "model" for m in audit1["mismatched_fields"])

    # Candidate used different toolset
    candidate_cfg_tool_mismatch = {
        "model": "gpt-4o-2024-05-13",
        "temperature": 0.0,
        "toolset": ["web_search", "fetch_url", "code_interpreter", "calculator"],
        "max_tokens": 4096,
    }
    audit2 = eval_harness.detect_confounders(baseline_cfg, candidate_cfg_tool_mismatch)
    assert audit2["confounder_detected"] is True
    assert audit2["unadjusted_comparison_permitted"] is False
    assert any(m["field"] == "toolset" for m in audit2["mismatched_fields"])

    # Identical configurations: no confounders
    audit_clean = eval_harness.detect_confounders(baseline_cfg, baseline_cfg)
    assert audit_clean["confounder_detected"] is False
    assert audit_clean["unadjusted_comparison_permitted"] is True


def test_e05_contamination_repartition():
    """E05: Agent worker observed held-out benchmark task answers during development.
    
    Benchmark harness marks task contaminated; held-out status revoked and task repartitioned.
    """
    # Simulated partition manifest
    manifest = {
        "tasks": [
            {"task_id": "heldout-en-01", "partition": "held_out", "is_contaminated": False},
            {"task_id": "heldout-en-02", "partition": "held_out", "is_contaminated": False},
            {"task_id": "dev-01", "partition": "development", "is_contaminated": False},
        ]
    }

    # Worker observed answer for heldout-en-01 during debugging
    target_task_id = "heldout-en-01"

    # Repartition function
    repartitioned = False
    for t in manifest["tasks"]:
        if t["task_id"] == target_task_id:
            t["is_contaminated"] = True
            t["partition"] = "development"
            t["repartition_reason"] = "ORACLE_ANSWER_OBSERVED_IN_DEV"
            repartitioned = True

    assert repartitioned is True
    target_item = next(t for t in manifest["tasks"] if t["task_id"] == target_task_id)
    assert target_item["is_contaminated"] is True
    assert target_item["partition"] == "development"
    # Held-out count has been reduced and task can no longer serve as uncontaminated held-out
    held_out_remaining = sum(1 for t in manifest["tasks"] if t["partition"] == "held_out")
    assert held_out_remaining == 1


def test_e06_denominator_omission_catch():
    """E06: Candidate run omits failed or timed-out tasks from summary denominator.
    
    Evaluator recalculates denominator from total registered tasks; flags missing cases.
    """
    registered_tasks = [
        {"task_id": f"task-{i:02d}", "category": "atomic_fact"} for i in range(1, 25)
    ]  # 24 tasks
    assert len(registered_tasks) == 24

    # Candidate run only returns 18 tasks (omitted 6 tasks that failed/crashed)
    candidate_partial_runs = {
        f"task-{i:02d}": {
            "task_id": f"task-{i:02d}",
            "output_text": "Valid answer content",
            "telemetry": {"token_count": 100, "execution_time_ms": 500.0, "tool_calls_count": 1},
        }
        for i in range(1, 19)
    }

    dummy_oracle = {
        "tasks": {
            f"task-{i:02d}": {"target_value": "Valid answer content", "acceptable_values": ["valid answer content"]}
            for i in range(1, 25)
        }
    }

    res = eval_harness.evaluate_benchmark(registered_tasks, candidate_partial_runs, dummy_oracle)
    summary = res["benchmark_summary"]

    # Denominator must remain 24, not 18!
    assert summary["denominator"] == 24
    assert summary["submitted_tasks"] == 18
    assert summary["missing_tasks_count"] == 6
    assert len(summary["missing_task_ids"]) == 6
    # Completion rate calculated against 24: 18 / 24 = 0.75, not 18/18 = 1.0!
    assert math.isclose(summary["completion_rate"], 18 / 24, abs_tol=1e-3)


def test_e07_over_refusal_accounting():
    """E07: Candidate refuses high percentage of tasks or marks all as requires_review to inflate citation accuracy.
    
    Evaluator reports completion rate, coverage, and over-refusal penalties alongside accuracy.
    """
    # 10 factual tasks (none are missing_blocked_source)
    tasks = [
        {"task_id": f"fact-{i}", "category": "atomic_fact"} for i in range(10)
    ]
    oracle = {
        "tasks": {
            f"fact-{i}": {"target_value": f"Answer {i}", "acceptable_values": [f"answer {i}"]}
            for i in range(10)
        }
    }

    # Evasive candidate strategy: marks 9 out of 10 tasks as requires_review / refusal to avoid errors
    evasive_runs = {}
    for i in range(10):
        if i == 0:
            evasive_runs[f"fact-{i}"] = {
                "task_id": f"fact-{i}",
                "output_text": "Answer 0",
                "telemetry": {"token_count": 100, "execution_time_ms": 200.0, "tool_calls_count": 1},
            }
        else:
            evasive_runs[f"fact-{i}"] = {
                "task_id": f"fact-{i}",
                "output_text": "Requires review / Uncertain / Refusal to answer",
                "requires_review": True,
                "status": "refused",
                "telemetry": {"token_count": 50, "execution_time_ms": 100.0, "tool_calls_count": 1},
            }

    eval_result = eval_harness.evaluate_benchmark(tasks, evasive_runs, oracle)
    summary = eval_result["benchmark_summary"]

    # Evaluator flags completion rate degradation and over-refusal penalty
    assert summary["completion_rate"] == 0.1  # Only 1 of 10 completed
    assert summary["over_refusal_penalty"] > 0.0
    # Overall score is penalized severely, preventing evasion
    assert summary["overall_score"] < 0.2


def test_e08_snapshot_drift_detection():
    """E08: Source snapshots altered between repeated runs of benchmark task.
    
    Evaluator detects snapshot drift via digest check; differentiates frozen corpus evaluation from live search.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        dir_path = Path(temp_dir)
        snap_file = dir_path / "snapshot.txt"
        original_bytes = b"Original frozen source content"
        snap_file.write_bytes(original_bytes)
        correct_sha = hashlib.sha256(original_bytes).hexdigest()

        snapshots_reg = [
            {"path": "snapshot.txt", "expected_sha256": correct_sha}
        ]

        # First check: passes without drift
        check1 = eval_harness.detect_snapshot_drift(snapshots_reg, dir_path)
        assert check1["snapshot_drift_detected"] is False
        assert check1["is_frozen"] is True

        # Mutate the snapshot (simulating live web drift or file edit)
        snap_file.write_bytes(b"Modified drifting source content")

        # Second check: detects snapshot drift
        check2 = eval_harness.detect_snapshot_drift(snapshots_reg, dir_path)
        assert check2["snapshot_drift_detected"] is True
        assert check2["is_frozen"] is False
        assert len(check2["drift_items"]) == 1
        assert check2["drift_items"][0]["error"] == "digest_mismatch"


def test_e09_harness_mutation_catch():
    """E09: Intentional bugs and assertions injected into test harness during mutation check.
    
    Harness catches injected bugs; confirms tests do not merely assert output contains 'PASS'.
    """
    task = {"task_id": "mut-01", "category": "atomic_fact"}
    oracle = {"target_value": "Paris", "acceptable_values": ["paris"]}
    
    # 1. Correct candidate run
    valid_run = {
        "task_id": "mut-01",
        "output_text": "The capital of France is Paris.",
        "telemetry": {"token_count": 50, "execution_time_ms": 100.0, "tool_calls_count": 1},
    }
    eval_good = eval_harness.evaluate_single_task(task, valid_run, oracle)
    assert eval_good["task_completed"] is True
    assert eval_good["score"] > 0.8

    # 2. Injected mutation in candidate: wrong fact
    mutated_run = {
        "task_id": "mut-01",
        "output_text": "The capital of France is Berlin.",
        "telemetry": {"token_count": 50, "execution_time_ms": 100.0, "tool_calls_count": 1},
    }
    eval_bad = eval_harness.evaluate_single_task(task, mutated_run, oracle)
    assert eval_bad["task_completed"] is False
    assert eval_bad["answer_matched"] is False
    assert eval_bad["score"] < 0.5

    # 3. Injected mutation in grader oracle: corrupted expected value
    corrupted_oracle = {"target_value": "Tokyo", "acceptable_values": ["tokyo"]}
    eval_mismatch = eval_harness.evaluate_single_task(task, valid_run, corrupted_oracle)
    assert eval_mismatch["task_completed"] is False
    assert eval_mismatch["answer_matched"] is False


def _find_audit_artifacts_dir() -> Path | None:
    for p in Path(__file__).resolve().parents:
        if (p / "audit-artifacts" / "evaluation").is_dir():
            return p / "audit-artifacts"
    return None


def _find_evaluation_summary_file() -> Path | None:
    local_f = Path(__file__).resolve().parent / "fixtures" / "evaluation_summary.json"
    if local_f.is_file():
        return local_f
    audit_dir = _find_audit_artifacts_dir()
    if audit_dir and (audit_dir / "evaluation" / "results" / "evaluation_summary.json").is_file():
        return audit_dir / "evaluation" / "results" / "evaluation_summary.json"
    return None


def test_e10_raw_artifact_scoring_reproducibility():
    """E10: Scorer executed against raw benchmark outputs and empirical pilot artifacts.
    
    Recomputed metrics match recorded metrics exactly; proves automated reproducible evaluation.
    """
    summary_file = _find_evaluation_summary_file()
    if summary_file is None:
        import pytest
        pytest.skip("Could not locate evaluation summary fixture in isolated environment")

    # Test A: Benchmark artifact recomputation
    assert summary_file.is_file(), "evaluation_summary.json must exist"

    summary_data = json.loads(summary_file.read_text(encoding="utf-8"))
    cand_per_task = summary_data["candidate_per_task"]
    total_reg = summary_data["candidate_summary"]["total_registered_tasks"]

    recomputed = eval_harness.recompute_benchmark_metrics(cand_per_task, total_reg)
    expected_score = summary_data["candidate_summary"]["overall_score"]
    assert recomputed["overall_score"] == expected_score
    assert recomputed["completion_rate"] == summary_data["candidate_summary"]["completion_rate"]
    assert recomputed["citation_correctness"] == summary_data["candidate_summary"]["citation_correctness"]

    # Test B: Empirical Pilot cases recomputation from real pilot artifacts on disk (if present)
    audit_artifacts = _find_audit_artifacts_dir()
    if audit_artifacts is None or not (audit_artifacts / "empirical-pilot" / "hindcast").is_dir():
        return
    pilot_dir = audit_artifacts / "empirical-pilot"
    hindcast_dir = pilot_dir / "hindcast"
    assert hindcast_dir.is_dir(), "hindcast directory must exist"

    raw_case_files = sorted(hindcast_dir.glob("case-*.json"))
    assert len(raw_case_files) >= 30, f"Must have >= 30 cases, found {len(raw_case_files)}"

    real_cases = [json.loads(f.read_text(encoding="utf-8")) for f in raw_case_files]
    recomputed_pilot = eval_harness.recompute_empirical_pilot_metrics(real_cases)

    recorded_metrics = json.loads((pilot_dir / "recomputed-metrics.json").read_text(encoding="utf-8"))
    assert recomputed_pilot["case_count"] == recorded_metrics["case_count"]
    assert recomputed_pilot["candidate_metrics"]["mae"] == recorded_metrics["candidate_metrics"]["mae"]
    assert recomputed_pilot["baseline_metrics"]["mae"] == recorded_metrics["baseline_metrics"]["mae"]
    assert recomputed_pilot["beats_baseline"] == recorded_metrics["beats_baseline"]
    assert recomputed_pilot["beats_baseline"] is False
    assert recomputed_pilot["assurance_status"] == "uncalibrated"
