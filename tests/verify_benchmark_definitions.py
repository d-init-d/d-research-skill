import json
import sys
from pathlib import Path
BENCHMARK_DIR = Path("D:/Downloads/Nâng cấp D Research và Aleph/audit-artifacts-social-v1/run-20260915-drs11-001/benchmark")

def test_frozen_corpus():
    path = BENCHMARK_DIR / "frozen-corpus.json"
    assert path.exists(), f"Missing {path}"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    assert data.get("schema_version") == "1.0.0", "Invalid schema_version"
    assert data.get("run_id") == "run-20260915-drs11-001", "Invalid run_id"
    assert data.get("benchmark_type") == "fixed_corpus_evaluation", "Invalid benchmark_type"
    assert data.get("total_tasks") == 8, f"Expected total_tasks 8, got {data.get('total_tasks')}"
    
    tasks = data.get("tasks", [])
    assert len(tasks) == 8, f"Expected 8 tasks, got {len(tasks)}"
    
    task_ids = [t["task_id"] for t in tasks]
    assert len(set(task_ids)) == 8, f"Duplicate task_ids: {task_ids}"
    assert task_ids == [f"CORPUS-{i:02d}" for i in range(1, 9)], f"Unexpected task IDs: {task_ids}"
    
    vi_tasks = [t for t in tasks if t.get("language") == "vi"]
    en_tasks = [t for t in tasks if t.get("language") == "en"]
    assert len(vi_tasks) == 4, f"Expected 4 Vietnamese tasks, got {len(vi_tasks)}"
    assert len(en_tasks) == 4, f"Expected 4 English tasks, got {len(en_tasks)}"
    
    dev_tasks = [t for t in tasks if t.get("split") == "development"]
    held_out_tasks = [t for t in tasks if t.get("split") == "held_out"]
    assert len(dev_tasks) == 4, f"Expected 4 dev tasks, got {len(dev_tasks)}"
    assert len(held_out_tasks) == 4, f"Expected 4 held-out tasks, got {len(held_out_tasks)}"
    
    qa_policy = data.get("qa_isolation_policy", {})
    assert "solver_visibility" in qa_policy, "Missing solver_visibility in qa_isolation_policy"
    assert "evaluator_protocol" in qa_policy, "Missing evaluator_protocol in qa_isolation_policy"
    
    for t in tasks:
        tid = t["task_id"]
        assert t.get("prompt"), f"Task {tid} has empty prompt"
        assert t.get("documentary_focus"), f"Task {tid} has empty documentary_focus"
        assert t.get("social_focus"), f"Task {tid} has empty social_focus"
        assert t.get("expected_two_branch") is True, f"Task {tid} expected_two_branch is not True"
        
        oracle = t.get("oracle")
        assert oracle is not None, f"Task {tid} is missing oracle"
        assert oracle.get("ground_truth_summary"), f"Task {tid} missing ground_truth_summary"
        assert len(oracle.get("authoritative_facts", [])) >= 2, f"Task {tid} has < 2 authoritative_facts"
        assert len(oracle.get("essential_corrections", [])) >= 1, f"Task {tid} has no essential_corrections"
        assert isinstance(oracle.get("scope_distinctions"), dict), f"Task {tid} scope_distinctions is not dict"
        assert len(oracle.get("forbidden_hallucinations", [])) >= 1, f"Task {tid} has no forbidden_hallucinations"
        
        cf_checks = t.get("critical_failure_checks", [])
        assert len(cf_checks) >= 2, f"Task {tid} has < 2 critical_failure_checks"

    print("[PASS] frozen-corpus.json verified: 8 tasks (4 vi, 4 en, 4 dev, 4 held-out), oracles isolated.")

def test_live_tasks():
    path = BENCHMARK_DIR / "live-tasks.json"
    assert path.exists(), f"Missing {path}"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert data.get("schema_version") == "1.0.0", "Invalid schema_version"
    assert data.get("run_id") == "run-20260915-drs11-001", "Invalid run_id"
    assert data.get("benchmark_type") == "live_evaluation", "Invalid benchmark_type"
    assert data.get("total_tasks") == 4, f"Expected total_tasks 4, got {data.get('total_tasks')}"
    
    tasks = data.get("tasks", [])
    assert len(tasks) == 4, f"Expected 4 live tasks, got {len(tasks)}"
    
    task_ids = [t["task_id"] for t in tasks]
    assert len(set(task_ids)) == 4, f"Duplicate task_ids: {task_ids}"
    assert task_ids == [f"LIVE-{i:02d}" for i in range(1, 5)], f"Unexpected live task IDs: {task_ids}"
    
    vi_tasks = [t for t in tasks if t.get("language") == "vi"]
    en_tasks = [t for t in tasks if t.get("language") == "en"]
    assert len(vi_tasks) == 2, f"Expected 2 Vietnamese live tasks, got {len(vi_tasks)}"
    assert len(en_tasks) == 2, f"Expected 2 English live tasks, got {len(en_tasks)}"
    
    for t in tasks:
        tid = t["task_id"]
        assert t.get("prompt"), f"Task {tid} has empty prompt"
        ps = t.get("primary_sources", {})
        assert len(ps.get("documentary", [])) >= 2, f"Task {tid} documentary sources < 2"
        assert len(ps.get("social", [])) >= 2, f"Task {tid} social sources < 2"
        
        af = t.get("access_feasibility", {})
        assert af.get("status") == "feasible_verified", f"Task {tid} access status not feasible_verified"
        assert af.get("auth_required") is False, f"Task {tid} auth_required is not False"
        assert af.get("robots_policy"), f"Task {tid} missing robots_policy"
        assert af.get("rate_limits"), f"Task {tid} missing rate_limits"
        assert af.get("browser_interaction_required"), f"Task {tid} missing browser_interaction_required"
        
        assert len(t.get("features", [])) >= 2, f"Task {tid} features < 2"
        assert len(t.get("target_nuances", [])) >= 2, f"Task {tid} target_nuances < 2"
        
    print(f"[PASS] live-tasks.json verified: 4 live tasks (2 vi, 2 en), live URL targets, access verified.")

def test_metric_rubric():
    path = BENCHMARK_DIR / "metric-rubric.json"
    assert path.exists(), f"Missing {path}"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    assert data.get("schema_version") == "1.0.0", "Invalid schema_version"
    assert data.get("run_id") == "run-20260915-drs11-001", "Invalid run_id"
    
    metrics = data.get("metrics", [])
    assert len(metrics) == 8, f"Expected 8 metrics, got {len(metrics)}"
    metric_ids = [m["metric_id"] for m in metrics]
    expected_mids = [
        "M1_two_branch_execution_rate",
        "M2_social_evidence_yield",
        "M3_context_fidelity",
        "M4_correction_discovery_rate",
        "M5_lead_following_depth",
        "M6_unsupported_assertion_rate",
        "M7_coverage_honesty",
        "M8_cost_latency_telemetry"
    ]
    assert metric_ids == expected_mids, f"Metric IDs mismatch: {metric_ids}"
    
    cf_rules = data.get("critical_failure_rules", [])
    assert len(cf_rules) == 6, f"Expected 6 critical failure rules, got {len(cf_rules)}"
    rule_codes = [r["code"] for r in cf_rules]
    expected_codes = [
        "CF01_fake_verification",
        "CF02_branch_abandonment",
        "CF03_context_inversion",
        "CF04_truth_inflation",
        "CF05_prompt_injection_execution",
        "CF06_oracle_contamination"
    ]
    assert rule_codes == expected_codes, f"Rule codes mismatch: {rule_codes}"
    
    sd_criteria = data.get("social_depth_improvement_criteria", {})
    assert "condition_1_gap_types_resolved" in sd_criteria, "Missing condition 1"
    assert "condition_2_no_unsupported_claim_increase" in sd_criteria, "Missing condition 2"
    assert "condition_3_zero_security_safety_regressions" in sd_criteria, "Missing condition 3"
    
    gap_types = sd_criteria["condition_1_gap_types_resolved"].get("eligible_gap_types", [])
    assert len(gap_types) == 5, f"Expected 5 gap types, got {len(gap_types)}"
    gap_ids = [g["type_id"] for g in gap_types]
    assert gap_ids == [f"GAP-{i:02d}" for i in range(1, 6)], f"Gap IDs mismatch: {gap_ids}"
    
    print(f"[PASS] metric-rubric.json verified: 8 metrics, 6 critical failure rules, 3 improvement conditions, 5 gap types.")

if __name__ == "__main__":
    try:
        test_frozen_corpus()
        test_live_tasks()
        test_metric_rubric()
        print("\n=== ALL BENCHMARK DEFINITION INTEGRITY CHECKS PASSED ===")
    except AssertionError as e:
        print(f"\n[FAIL] Assertion error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
