"""Acceptance Test Suite for Finding CR05: D Research Benchmark & Evaluation (VEV01–VEV12).

Verifies:
- VEV01: Synthetic outputs from revoked generator rejected as invalid-as-live evidence
- VEV02: Run with self-declared pass summary but no execution activity rejected as not_run/invalid
- VEV03: Missing telemetry records null + explicit reason, rejects fabricated constant telemetry
- VEV04: Oracle contamination detection forces repartitioning and forbids claiming blind evaluation
- VEV05: Context/memory sharing prevents claiming independent process isolation
- VEV06: Confounder detection catches model/tools/config drift and forbids unadjusted comparison
- VEV07: Held-out repetitions verify activity uniqueness, reject duplicated/copied runs
- VEV08: Full denominator (all registered tasks) maintained even when failed tasks are omitted
- VEV09: Over-refusal penalty applied when candidate evades answering on answerable tasks
- VEV10: Source drift detected and frozen corpus separated from live web execution
- VEV11: Independent scorer recomputes metrics directly without candidate aggregate functions
- VEV12: Honest insufficient evidence verdict when benchmark is unrun or below target threshold
"""
from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import eval_harness


def test_vev01_synthetic_output_revocation():
    """VEV01: Generator cũ dựng outputs từ oracle bị nhận synthetic/invalid-as-live; không dùng chứng minh improvement."""
    # Flawed run constructed by the revoked synthetic generator
    synthetic_run = {
        "task_id": "dev-01",
        "action": "answer",
        "is_blocked": False,
        "is_synthetic": True,
        "generator": "synthetic_benchmark_generator",
        "output_text": "Python 3.0 was released in December 2008 by Guido van Rossum.",
        "claims": [
            {
                "claim_id": "C_dev-01_01",
                "claim_text": "December 2008",
                "quote": "December 2008",
                "snapshot_path": "dev-01-python3.txt",
            }
        ],
        "telemetry": {
            "token_count": 890,
            "execution_time_ms": 2340.0,
            "tool_calls_count": 3,
        },
    }

    audit = eval_harness.audit_run_authenticity(synthetic_run)
    assert audit["is_authentic"] is False
    assert audit["classification"] == "synthetic_generated"
    assert audit["reason"] == "REVOKED_SYNTHETIC_GENERATOR_OUTPUT"
    assert audit["is_valid_run"] is False

    # Evaluation harness must not count synthetic runs as genuine empirical improvement
    task_spec = {"task_id": "dev-01", "category": "atomic_fact"}
    oracle = {"target_value": "December 2008", "acceptable_values": ["december 2008"]}
    res = eval_harness.evaluate_single_task(task_spec, synthetic_run, oracle)
    assert res["task_id"] == "dev-01"

    # Strip fields and verify authenticity gate
    audit_clean = eval_harness.audit_run_authenticity(eval_harness.strip_candidate_fields(synthetic_run))
    assert audit_clean["is_authentic"] is False


def test_vev02_unexecuted_summary_run_rejected():
    """VEV02: Run chỉ có summary/model-name nhưng không host execution/activity -> not_run/unverifiable, không counted completed."""
    # Submission declaring model name and self-declared completion without substantive activity
    unexecuted_run = {
        "task_id": "dev-03",
        "model": "claude-3-5-sonnet-20241022",
        "output_text": "",
        "declared_summary": {
            "status": "completed",
            "verdict": "verified",
            "score": 0.98,
        },
        "telemetry": None,
    }

    audit = eval_harness.audit_run_authenticity(unexecuted_run)
    assert audit["is_authentic"] is False
    assert audit["classification"] == "unexecuted_summary_run"
    assert audit["reason"] == "UNEXECUTED_SUMMARY_WITHOUT_ACTIVITY"

    task_spec = {"task_id": "dev-03", "category": "version_date_cutoff"}
    oracle = {"target_value": "Iron", "date_elements": ["2023-10-24"]}
    eval_res = eval_harness.evaluate_single_task(task_spec, unexecuted_run, oracle)

    assert eval_res["status"] == "invalid"
    assert eval_res["is_valid_run"] is False
    assert eval_res["task_completed"] is False
    assert eval_res["score"] == 0.0


def test_vev03_missing_telemetry_null_accounting():
    """VEV03: Thiếu token/time/tool telemetry -> null + reason, không bịa hằng số/zero."""
    # Case A: Missing telemetry dict
    parsed_none = eval_harness.parse_telemetry_v2(None)
    assert parsed_none["token_count"] is None
    assert parsed_none["execution_time_ms"] is None
    assert parsed_none["tool_calls_count"] is None
    assert parsed_none["is_measured"] is False
    assert "telemetry_unmeasured" in parsed_none["reason"]
    assert parsed_none["fabrication_detected"] is False

    # Case B: Fabricated constant telemetry from prior revoked run (CR05)
    fabricated_constants = {
        "token_count": 890,
        "execution_time_ms": 2340.0,
        "tool_calls_count": 3,
    }
    parsed_fab = eval_harness.parse_telemetry_v2(fabricated_constants)
    assert parsed_fab["fabrication_detected"] is True
    assert parsed_fab["token_count"] is None
    assert parsed_fab["reason"] == "FABRICATED_CONSTANT_TELEMETRY_REVOKED"

    # Case C: Genuine partial telemetry
    genuine_partial = {
        "execution_time_ms": 142.5,
        "bytes_read": 4096,
    }
    parsed_gen = eval_harness.parse_telemetry_v2(genuine_partial)
    assert parsed_gen["execution_time_ms"] == 142.5
    assert parsed_gen["bytes_read"] == 4096
    assert parsed_gen["token_count"] is None
    assert "tokens_unmeasured" in parsed_gen["reason"]
    assert parsed_gen["is_measured"] is True


def test_vev04_oracle_contamination_detection():
    """VEV04: Candidate từng đọc oracle/held-out output -> contaminated/repartition; không claim blind."""
    oracle_entry = {
        "target_value": "4392 meters",
        "oracle_canary": "CANARY_TOKEN_XYZ_SECRET_9812",
        "dispute_elements": ["Mount Rainier", "14411 feet"],
    }

    # Candidate run contains hidden oracle canary token
    contaminated_run = {
        "task_id": "heldout-en-02",
        "output_text": "Elevation: 4392 meters. Verification log: CANARY_TOKEN_XYZ_SECRET_9812 inspected.",
        "claims": [],
    }

    contam_check = eval_harness.detect_oracle_contamination(contaminated_run, oracle_entry)
    assert contam_check["is_contaminated"] is True
    assert contam_check["contamination_type"] == "ORACLE_CANARY_LEAKAGE"
    assert contam_check["repartition_required"] is True

    # Candidate referencing oracle file directly
    oracle_file_ref_run = {
        "task_id": "heldout-en-03",
        "output_text": "Answers extracted directly from audit-artifacts/evaluation/oracle/ground_truth_oracle.json.",
        "claims": [],
    }
    ref_check = eval_harness.detect_oracle_contamination(oracle_file_ref_run, oracle_entry)
    assert ref_check["is_contaminated"] is True
    assert ref_check["contamination_type"] == "ORACLE_METADATA_REFERENCE"
    assert ref_check["repartition_required"] is True

    # Clean uncontaminated run
    clean_run = {
        "task_id": "heldout-en-02",
        "output_text": "Mount Rainier stands at 4,392 meters (14,411 feet) above sea level.",
        "claims": [],
    }
    clean_check = eval_harness.detect_oracle_contamination(clean_run, oracle_entry)
    assert clean_check["is_contaminated"] is False
    assert clean_check["repartition_required"] is False


def test_vev05_isolation_boundary_accounting():
    """VEV05: Chỉ tách thư mục/IDs mà quyền/context vẫn chung -> Isolation khai đúng mức, không fake independent."""
    # Shared memory / shared context run
    shared_meta = {
        "isolation_type": "directory_only",
        "shared_context": True,
        "shared_memory": False,
        "parent_pid": 1001,
        "child_pid": 1001,
    }
    audit_shared = eval_harness.verify_isolation_boundary(shared_meta)
    assert audit_shared["is_strictly_isolated"] is False
    assert audit_shared["isolation_level"] == "directory_separated_only"
    assert audit_shared["independent_evaluation_permitted"] is False
    assert "SHARED_CONTEXT" in audit_shared["reason"]

    # True process-isolated run
    process_meta = {
        "isolation_type": "process_isolated",
        "shared_context": False,
        "shared_memory": False,
        "parent_pid": 1001,
        "child_pid": 2042,
    }
    audit_proc = eval_harness.verify_isolation_boundary(process_meta)
    assert audit_proc["is_strictly_isolated"] is True
    assert audit_proc["isolation_level"] == "process_isolated"
    assert audit_proc["independent_evaluation_permitted"] is True


def test_vev06_confound_detection_between_models():
    """VEV06: Baseline/candidate khác model/tools/config/budget policy -> Confound được phát hiện và loại khỏi so sánh không điều chỉnh."""
    base_cfg = {
        "model": "claude-3-haiku-20240307",
        "temperature": 0.0,
        "toolset": ["web_search"],
        "max_tokens": 2048,
    }
    cand_cfg = {
        "model": "claude-3-5-sonnet-20241022",  # Different model (confounder)
        "temperature": 0.0,
        "toolset": ["web_search", "fetch_url", "extract_table"],  # Different tools
        "max_tokens": 4096,
    }

    res = eval_harness.detect_confounders(base_cfg, cand_cfg)
    assert res["confounder_detected"] is True
    assert res["unadjusted_comparison_permitted"] is False
    mismatched_fields = {m["field"] for m in res["mismatched_fields"]}
    assert "model" in mismatched_fields
    assert "toolset" in mismatched_fields
    assert "max_tokens" in mismatched_fields

    # Identical configurations permit unadjusted comparison
    matched_cand_cfg = dict(base_cfg)
    res_matched = eval_harness.detect_confounders(base_cfg, matched_cand_cfg)
    assert res_matched["confounder_detected"] is False
    assert res_matched["unadjusted_comparison_permitted"] is True


def test_vev07_held_out_repetition_activity_uniqueness():
    """VEV07: Ba lượt held-out bị copy/dedup JSON thay execution mới -> Không tính ba execution; kiểm tra activity identities."""
    # Flawed: 3 repetitions are identical byte copies
    copied_repetitions = [
        {
            "repetition_index": 1,
            "activity_id": "act-identical-111",
            "timestamp": "2026-09-05T01:00:00Z",
            "output_text": "Penicillin was discovered in 1928 by Alexander Fleming.",
        },
        {
            "repetition_index": 2,
            "activity_id": "act-identical-111",  # Reused ID
            "timestamp": "2026-09-05T01:00:00Z",  # Reused timestamp
            "output_text": "Penicillin was discovered in 1928 by Alexander Fleming.",
        },
        {
            "repetition_index": 3,
            "activity_id": "act-identical-111",  # Reused ID
            "timestamp": "2026-09-05T01:00:00Z",  # Reused timestamp
            "output_text": "Penicillin was discovered in 1928 by Alexander Fleming.",
        },
    ]

    verif_copied = eval_harness.verify_held_out_repetitions(copied_repetitions)
    assert verif_copied["duplicate_detected"] is True
    assert verif_copied["valid_repetitions_count"] == 1
    assert verif_copied["has_required_repetitions"] is False

    # Genuine: 3 distinct executions with unique activity IDs and timestamps
    genuine_repetitions = [
        {
            "repetition_index": 1,
            "activity_id": "act-gen-001",
            "timestamp": "2026-09-05T01:00:00Z",
            "output_text": "Alexander Fleming discovered penicillin in September 1928 at St. Mary's Hospital.",
            "latency_ms": 112.0,
        },
        {
            "repetition_index": 2,
            "activity_id": "act-gen-002",
            "timestamp": "2026-09-05T01:01:05Z",
            "output_text": "Penicillin was discovered by Scottish physician Alexander Fleming in 1928.",
            "latency_ms": 98.5,
        },
        {
            "repetition_index": 3,
            "activity_id": "act-gen-003",
            "timestamp": "2026-09-05T01:02:10Z",
            "output_text": "In 1928, Alexander Fleming noted that Penicillium notatum mold killed staphylococcus bacteria.",
            "latency_ms": 105.2,
        },
    ]

    verif_genuine = eval_harness.verify_held_out_repetitions(genuine_repetitions)
    assert verif_genuine["duplicate_detected"] is False
    assert verif_genuine["valid_repetitions_count"] == 3
    assert verif_genuine["has_required_repetitions"] is True


def test_vev08_full_denominator_task_accounting():
    """VEV08: Bỏ fail/refuse/missing task khỏi denominator -> Scorer phát hiện; giữ all registered tasks."""
    total_registered = 24
    registered_tasks = [
        {"task_id": f"task-{i:02d}", "category": "atomic_fact"} for i in range(1, total_registered + 1)
    ]

    # Candidate only submitted 16 tasks (omitted 8 failed/timed-out tasks)
    submitted_runs = {
        f"task-{i:02d}": {
            "task_id": f"task-{i:02d}",
            "output_text": f"Answer for task-{i:02d}",
            "claims": [],
            "telemetry": {"token_count": 50, "execution_time_ms": 100.0, "tool_calls_count": 1},
        }
        for i in range(1, 17)
    }

    dummy_oracle = {
        "tasks": {
            f"task-{i:02d}": {
                "target_value": f"Answer for task-{i:02d}",
                "acceptable_values": [f"answer for task-{i:02d}"],
            }
            for i in range(1, total_registered + 1)
        }
    }

    eval_result = eval_harness.evaluate_benchmark(registered_tasks, submitted_runs, dummy_oracle)
    summary = eval_result["benchmark_summary"]

    assert summary["denominator"] == 24
    assert summary["submitted_tasks"] == 16
    assert summary["missing_tasks_count"] == 8
    # Completion rate must be calculated against 24: 16 / 24 = 0.6667, NOT 16/16 = 1.0!
    assert math.isclose(summary["completion_rate"], 16 / 24, abs_tol=1e-3)
    assert math.isclose(summary["overall_score"], 16 / 24, abs_tol=1e-3)


def test_vev09_over_refusal_honesty_reporting():
    """VEV09: Refuse/requires_review nhiều để citation score đẹp -> Báo completion/coverage/over-refusal cùng score."""
    registered_tasks = [
        {"task_id": f"task-fact-{i}", "category": "atomic_fact"} for i in range(10)
    ]

    # Candidate attempts evasion: answers 2 tasks with 100% precision, but refuses 8 tasks
    candidate_evasion_runs = {}
    for i in range(2):
        candidate_evasion_runs[f"task-fact-{i}"] = {
            "task_id": f"task-fact-{i}",
            "output_text": "Exact ground truth fact",
            "claims": [],
            "telemetry": {"token_count": 50, "execution_time_ms": 100.0, "tool_calls_count": 1},
        }
    for i in range(2, 10):
        candidate_evasion_runs[f"task-fact-{i}"] = {
            "task_id": f"task-fact-{i}",
            "action": "refuse",
            "status": "refused",
            "requires_review": True,
            "output_text": "Refused due to excessive caution",
            "claims": [],
            "telemetry": {"token_count": 10, "execution_time_ms": 20.0, "tool_calls_count": 0},
        }

    oracle = {
        "tasks": {
            f"task-fact-{i}": {
                "expected_action": "answer",
                "target_value": "Exact ground truth fact",
                "acceptable_values": ["exact ground truth fact"],
            }
            for i in range(10)
        }
    }

    res = eval_harness.evaluate_benchmark(registered_tasks, candidate_evasion_runs, oracle)
    summary = res["benchmark_summary"]

    # Penalty must be applied for unjustified refusals
    assert summary["over_refusal_penalty"] > 0.0
    assert summary["completion_rate"] == 0.2
    assert summary["requires_review_rate"] >= 0.8
    assert summary["overall_score"] < 0.2


def test_vev10_source_drift_and_mode_separation():
    """VEV10: Snapshot thay giữa lượt, live và frozen bị gộp -> Ghi source drift/mode; so sánh tách đúng protocol."""
    with tempfile.TemporaryDirectory() as tmpdir:
        snap_dir = Path(tmpdir)
        snap_file = snap_dir / "corpus_source.txt"
        original_text = "Standard historical data from 2020."
        snap_file.write_text(original_text, encoding="utf-8")
        original_hash = eval_harness.compute_file_sha256(snap_file)

        # Baseline checked with original hash
        ref_good = [{"path": "corpus_source.txt", "expected_sha256": original_hash}]
        drift_check_ok = eval_harness.detect_snapshot_drift(ref_good, snap_dir)
        assert drift_check_ok["snapshot_drift_detected"] is False
        assert drift_check_ok["is_frozen"] is True

        # Candidate modifies or updates file between runs
        snap_file.write_text("Modified data from 2026 with new additions.", encoding="utf-8")
        drift_check_bad = eval_harness.detect_snapshot_drift(ref_good, snap_dir)
        assert drift_check_bad["snapshot_drift_detected"] is True
        assert drift_check_bad["is_frozen"] is False
        assert drift_check_bad["drift_items"][0]["error"] == "digest_mismatch"


def test_vev11_independent_scorer_recomputation():
    """VEV11: Independent scorer recompute từ raw claims/tasks -> Khớp theo tolerance; không import cùng hàm aggregate làm oracle."""
    raw_per_task = [
        {
            "task_id": f"task-{i:02d}",
            "task_completed": (i <= 18),
            "citation_correctness": 0.85 if i <= 18 else 0.0,
            "important_claim_coverage": 0.90 if i <= 18 else 0.0,
            "contradiction_handling": 1.0,
            "freshness_date_correctness": 1.0,
            "blocker_honesty": 1.0,
            "score": 0.88 if i <= 18 else 0.0,
        }
        for i in range(1, 25)
    ]

    total_tasks = 24
    independent_metrics = eval_harness.independent_recompute_score(raw_per_task, total_tasks)

    assert independent_metrics["denominator"] == 24
    assert independent_metrics["completed_tasks_count"] == 18
    assert math.isclose(independent_metrics["completion_rate"], 18 / 24, abs_tol=1e-4)
    expected_citation = (18 * 0.85) / 24
    assert math.isclose(independent_metrics["citation_correctness"], expected_citation, abs_tol=1e-4)
    expected_score = (18 * 0.88) / 24
    assert math.isclose(independent_metrics["overall_score"], expected_score, abs_tol=1e-4)


def test_vev12_honest_insufficient_evidence_verdict():
    """VEV12: Metric thấp hơn mục tiêu hoặc uncertainty lớn -> Báo không đạt/insufficient, không đổi rubric hay baseline để thắng."""
    # Case A: Benchmark unrun or missing tasks
    unrun_summary = {
        "status": "not_run",
        "overall_score": 0.0,
        "completion_rate": 0.0,
        "missing_tasks_count": 24,
    }
    verdict_unrun = eval_harness.determine_benchmark_verdict(unrun_summary, target_score=0.85)
    assert verdict_unrun["verdict"] == "insufficient_evidence"
    assert verdict_unrun["empirical_improvement"] == "not_established"
    assert verdict_unrun["meets_target"] is False

    # Case B: Below required target (e.g. scored 0.72 vs target 0.85)
    below_target_summary = {
        "status": "completed",
        "overall_score": 0.72,
        "completion_rate": 0.75,
        "missing_tasks_count": 0,
    }
    verdict_below = eval_harness.determine_benchmark_verdict(below_target_summary, target_score=0.85)
    assert verdict_below["verdict"] == "insufficient_evidence"
    assert verdict_below["empirical_improvement"] == "not_established"
    assert verdict_below["meets_target"] is False

    # Case C: Genuine run achieving target (>= 0.85)
    achieved_summary = {
        "status": "completed",
        "overall_score": 0.89,
        "completion_rate": 0.95,
        "missing_tasks_count": 0,
    }
    verdict_achieved = eval_harness.determine_benchmark_verdict(achieved_summary, target_score=0.85)
    assert verdict_achieved["verdict"] == "target_achieved"
    assert verdict_achieved["empirical_improvement"] == "established_within_scope"
    assert verdict_achieved["meets_target"] is True
