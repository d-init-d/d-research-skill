#!/usr/bin/env python3
"""Evidence-backed coverage evaluator for bounded DRS-1.1 routes.

The evaluator does not browse and never invents research. It summarizes
activity logs and capture records produced by an execution host. With no
execution evidence, branches remain ``planned`` and the CLI returns a non-zero
status so callers cannot confuse planning with completed research.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from execution_evidence import (
    BLOCKED_OUTCOMES,
    SUCCESS_OUTCOMES,
    EvidenceIndex,
    load_evidence_index,
    summarize_consumption,
)


PURE_OPERATIONS = {
    "pure_extraction",
    "format_conversion",
    "single_url_raw_archive",
    "existing_dataset_statistics",
    "data_export",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _authorization(kind: str, question: str, applies_to: list[str], value: str) -> dict[str, Any]:
    digest = hashlib.sha256(f"{kind}\n{question}\n{value}".encode()).hexdigest()
    return {
        "authorization_id": f"scope:{digest[:16]}",
        "kind": kind,
        "requested_by": "user",
        "recorded_at": _utc_now_iso(),
        "instruction_sha256": f"sha256:{digest}",
        "applies_to": applies_to,
        "value": value,
    }


def _branch_summary(index: EvidenceIndex, branch: str, question_id: str) -> dict[str, Any]:
    activities = [
        activity
        for activity in index.activities.values()
        if activity.get("branch_id") == branch and question_id in (activity.get("question_ids") or [])
    ]
    sources = [
        capture
        for capture in index.sources.values()
        if capture.get("branch_id") == branch
        and index.activity_for(str(capture.get("activity_id", "")), branch, question_id)
    ]
    activity_ids = [str(item["activity_id"]) for item in activities]
    source_ids = [str(item["source_id"]) for item in sources]
    successes = [item for item in activities if item.get("outcome") in SUCCESS_OUTCOMES]
    failures = [item for item in activities if item.get("outcome") in BLOCKED_OUTCOMES]
    timestamps = [str(item.get("started_at")) for item in activities if item.get("started_at")]
    finishes = [str(item.get("finished_at")) for item in activities if item.get("finished_at")]

    state = "planned"
    stop_reason = "execution_evidence_not_supplied"
    if sources and successes:
        state = "completed"
        stop_reason = "hash_verified_capture_available"
    elif failures and not successes:
        state = "blocked"
        stop_reason = str(failures[-1].get("limitation") or "execution_blocked")
    elif successes:
        state = "partial"
        stop_reason = "activity_completed_without_hash_verified_source_capture"

    return {
        "branch_id": branch,
        "state": state,
        "started_at": min(timestamps) if timestamps else None,
        "finished_at": max(finishes) if finishes else None,
        "activity_ids": activity_ids,
        "source_ids": source_ids,
        "stop_reason": stop_reason,
        "scope_reference": None,
        "scope_authorization_id": None,
    }


def _relative_paths(root: Path, paths: list[str | Path]) -> list[str]:
    output: list[str] = []
    for value in paths:
        path = Path(value).resolve()
        try:
            output.append(path.relative_to(root).as_posix())
        except ValueError as exc:
            raise ValueError(f"evidence path must be inside workspace: {path}") from exc
    return output


def evaluate_fast(
    route: str,
    question: str,
    workspace_dir: str | Path = ".",
    execution_mode: str = "interleaved",
    corpus_only: bool = False,
    pure_operation: str | None = None,
    run_id: str | None = None,
    activity_logs: list[str | Path] | None = None,
    capture_records: list[str | Path] | None = None,
) -> dict[str, Any]:
    """Build research coverage from execution evidence already present on disk."""
    workspace = Path(workspace_dir).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    run_id = run_id or f"run-{datetime.now(timezone.utc).strftime('%Y%m%d')}-fast-001"
    now = _utc_now_iso()
    authorizations: list[dict[str, Any]] = []
    activity_logs = list(activity_logs or [])
    capture_records = list(capture_records or [])

    if pure_operation:
        operation = pure_operation.strip().lower()
        if operation not in PURE_OPERATIONS:
            raise ValueError(f"unsupported pure operation exemption: {operation}")
        authorization = _authorization(
            "pure_operation_exemption", question, ["documentary", "social"], operation
        )
        authorizations.append(authorization)
        branches: dict[str, dict[str, Any]] = {}
        for branch in ("documentary", "social"):
            branches[branch] = {
                "branch_id": branch,
                "state": "scope_excluded",
                "started_at": None,
                "finished_at": None,
                "activity_ids": [],
                "source_ids": [],
                "stop_reason": "pure_operation_exemption",
                "scope_reference": f"pure_operation_exemption:{operation}",
                "scope_authorization_id": authorization["authorization_id"],
            }
        index = EvidenceIndex(workspace=workspace)
    else:
        index = load_evidence_index(
            workspace,
            activity_paths=activity_logs or None,
            capture_paths=capture_records or None,
        )
        branches = {
            branch: _branch_summary(index, branch, "Q1")
            for branch in ("documentary", "social")
        }
        if corpus_only:
            authorization = _authorization(
                "user_provided_corpus_only", question, ["social"], "provided_corpus_only"
            )
            authorizations.append(authorization)
            branches["social"] = {
                "branch_id": "social",
                "state": "scope_excluded",
                "started_at": None,
                "finished_at": None,
                "activity_ids": [],
                "source_ids": [],
                "stop_reason": "user_directed_corpus_only",
                "scope_reference": "user_provided_corpus_only:provided_corpus_only",
                "scope_authorization_id": authorization["authorization_id"],
            }

    states = {branches["documentary"]["state"], branches["social"]["state"]}
    terminal_states = {"completed", "partial", "blocked", "no_relevant_results", "scope_excluded"}
    if states == {"scope_excluded"}:
        overall = "scope_excluded"
    elif states <= {"completed", "scope_excluded"}:
        overall = "completed"
    else:
        overall = "partial" if states <= terminal_states else "planned"
    coverage = {
        "schema_version": "1.1.0",
        "run_id": run_id,
        "revision": 1,
        "execution_mode": execution_mode,
        "execution_evidence": {
            "activity_logs": index.activity_files or _relative_paths(workspace, activity_logs),
            "capture_records": index.capture_files or _relative_paths(workspace, capture_records),
            "validation_errors": list(index.errors),
        },
        "scope_authorizations": authorizations,
        "allocated_budget": {
            "profile_name": "fast",
            "max_queries_per_branch": 2,
            "max_sources_per_branch": 3,
            "max_comments_per_thread": 12,
            "thread_depth_cap": 2,
            "max_browser_actions_per_page": 10,
            "wall_time_cap_seconds": 180,
        },
        "consumed_budget": summarize_consumption(index),
        "questions": [
            {
                "question_id": "Q1",
                "question_text": question,
                "domain_specialist": "general",
                "route_id": route,
                "overall_status": overall,
                "documentary_branch": branches["documentary"],
                "social_branch": branches["social"],
                "coverage_gaps": [] if overall == "completed" else ["Q1"],
                "stop_reason": (
                    "evidence_backed_fast_path_complete"
                    if overall == "completed"
                    else "execution_incomplete"
                ),
            }
        ],
        "created_at": now,
        "updated_at": now,
    }
    (workspace / "research-coverage.json").write_text(
        json.dumps(coverage, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return coverage


def main() -> int:
    parser = argparse.ArgumentParser(description="DRS-1.1 evidence-backed fast evaluator")
    parser.add_argument("--route", default="atomic_fact")
    parser.add_argument("--question", required=True)
    parser.add_argument("--workspace-dir", default=".")
    parser.add_argument("--mode", default="interleaved", choices=["concurrent", "interleaved"])
    parser.add_argument("--corpus-only", action="store_true")
    parser.add_argument("--pure-operation", choices=sorted(PURE_OPERATIONS))
    parser.add_argument("--activity-log", action="append", default=[])
    parser.add_argument("--capture-records", action="append", default=[])
    args = parser.parse_args()
    coverage = evaluate_fast(
        route=args.route,
        question=args.question,
        workspace_dir=args.workspace_dir,
        execution_mode=args.mode,
        corpus_only=args.corpus_only,
        pure_operation=args.pure_operation,
        activity_logs=args.activity_log,
        capture_records=args.capture_records,
    )
    print(json.dumps(coverage, indent=2, ensure_ascii=False))
    question = coverage["questions"][0]
    return 0 if question["overall_status"] in {"completed", "scope_excluded"} else 2


if __name__ == "__main__":
    sys.exit(main())
