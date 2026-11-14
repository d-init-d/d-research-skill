#!/usr/bin/env python3
"""Validate DRS-1.1 activity logs and immutable capture records.

This module is the trust boundary between browser/tool execution and research
coverage.  Coverage files may reference IDs, but IDs count only when they
resolve to a valid execution record and, for sources, a hash-verified artifact
on disk.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


VALID_BRANCHES = {"documentary", "social"}
SUCCESS_OUTCOMES = {"success"}
BLOCKED_OUTCOMES = {"blocked", "timeout", "error", "partial"}
VALID_ACTION_TYPES = {
    "navigate",
    "search",
    "filter",
    "open",
    "expand",
    "paginate",
    "scroll",
    "transcript",
    "extract",
    "api_fetch",
}
VALID_OUTCOMES = {"success", "partial", "blocked", "timeout", "error"}
BROWSER_ENGINES = {
    "host-subagent",
    "chrome-devtools-mcp",
    "cua-driver",
    "cdp-session",
    "playwright-chromium",
    "api-fetch",
}
HOST_INTEGRATED_ENGINES = {
    "host-subagent",
    "chrome-devtools-mcp",
    "cua-driver",
    "cdp-session",
}
ENGINE_DEFAULT_METHODS = {
    "host-subagent": "host_browser_dom",
    "chrome-devtools-mcp": "host_browser_mcp",
    "cua-driver": "host_browser_cua",
    "cdp-session": "host_browser_cdp",
    "playwright-chromium": "playwright_dom",
    "api-fetch": "api_fetch",
}
BROWSER_CAPTURE_METHODS = {
    "host_browser_dom",
    "host_browser_mcp",
    "host_browser_cua",
    "host_browser_cdp",
    "playwright_dom",
    "playwright_extract",
    "playwright_crawl",
    "api_fetch",
}


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_iso_datetime(value: str) -> bool:
    if not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError(f"{path}: expected a JSON array of objects")
    return data


def _safe_artifact_path(workspace: Path, manifest: Path, relative_ref: str) -> Path | None:
    if not relative_ref or Path(relative_ref).is_absolute():
        return None
    candidate = (manifest.parent / relative_ref).resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError:
        return None
    return candidate


@dataclass
class EvidenceIndex:
    workspace: Path
    activities: dict[str, dict[str, Any]] = field(default_factory=dict)
    captures: dict[str, dict[str, Any]] = field(default_factory=dict)
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    activity_files: list[str] = field(default_factory=list)
    capture_files: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    def activity_for(self, activity_id: str, branch: str, question_id: str) -> dict[str, Any] | None:
        record = self.activities.get(activity_id)
        if not record or record.get("branch_id") != branch:
            return None
        question_ids = record.get("question_ids") or []
        if question_id not in question_ids:
            return None
        return record

    def source_for(self, source_id: str, branch: str, question_id: str) -> dict[str, Any] | None:
        record = self.sources.get(source_id)
        if not record or record.get("branch_id") != branch:
            return None
        activity = self.activity_for(str(record.get("activity_id", "")), branch, question_id)
        return record if activity else None


def _manifest_paths(
    workspace: Path,
    coverage: dict[str, Any] | None,
    activity_paths: Iterable[Path] | None,
    capture_paths: Iterable[Path] | None,
) -> tuple[list[Path], list[Path]]:
    explicit_activities = list(activity_paths or [])
    explicit_captures = list(capture_paths or [])
    manifest = (coverage or {}).get("execution_evidence") or {}

    def resolve(values: Iterable[str]) -> list[Path]:
        output: list[Path] = []
        for value in values:
            candidate = (workspace / value).resolve()
            try:
                candidate.relative_to(workspace)
            except ValueError:
                continue
            output.append(candidate)
        return output

    if not explicit_activities:
        explicit_activities = resolve(manifest.get("activity_logs") or [])
    if not explicit_captures:
        explicit_captures = resolve(manifest.get("capture_records") or [])
    if not explicit_activities:
        explicit_activities = sorted(workspace.rglob("activity-log.json"))
    if not explicit_captures:
        explicit_captures = sorted(workspace.rglob("capture-records.json"))
    return explicit_activities, explicit_captures


def load_evidence_index(
    workspace: str | Path,
    coverage: dict[str, Any] | None = None,
    activity_paths: Iterable[str | Path] | None = None,
    capture_paths: Iterable[str | Path] | None = None,
) -> EvidenceIndex:
    """Load, cross-link, and hash-check execution evidence under ``workspace``."""
    root = Path(workspace).resolve()
    index = EvidenceIndex(workspace=root)
    activity_files, capture_files = _manifest_paths(
        root,
        coverage,
        [Path(p).resolve() for p in activity_paths or []],
        [Path(p).resolve() for p in capture_paths or []],
    )

    for path in activity_files:
        if not path.is_file():
            index.errors.append(f"missing activity log: {path}")
            continue
        try:
            path.relative_to(root)
            records = _read_json_list(path)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            index.errors.append(f"invalid activity log {path}: {exc}")
            continue
        index.activity_files.append(path.relative_to(root).as_posix())
        for position, record in enumerate(records):
            activity_id = str(record.get("activity_id", "")).strip()
            branch = str(record.get("branch_id", "")).strip()
            questions = record.get("question_ids")
            outcome = str(record.get("outcome", "")).strip()
            prefix = f"{path}:{position + 1}"
            if not activity_id:
                index.errors.append(f"{prefix}: missing activity_id")
                continue
            if activity_id in index.activities:
                index.errors.append(f"{prefix}: duplicate activity_id {activity_id}")
                continue
            if branch not in VALID_BRANCHES:
                index.errors.append(f"{prefix}: invalid branch_id {branch!r}")
            if not isinstance(questions, list) or not questions or not all(
                isinstance(q, str) and q.strip() for q in questions
            ):
                index.errors.append(f"{prefix}: question_ids must be a non-empty string array")
            if outcome not in SUCCESS_OUTCOMES | BLOCKED_OUTCOMES:
                index.errors.append(f"{prefix}: invalid outcome {outcome!r}")
            if not _is_iso_datetime(str(record.get("started_at", ""))) or not _is_iso_datetime(
                str(record.get("finished_at", ""))
            ):
                index.errors.append(f"{prefix}: invalid execution timestamps")
            if outcome == "success" and not _is_http_url(str(record.get("final_url", ""))):
                index.errors.append(f"{prefix}: successful activity needs an HTTP(S) final_url")
            index.activities[activity_id] = record

    for path in capture_files:
        if not path.is_file():
            index.errors.append(f"missing capture record file: {path}")
            continue
        try:
            path.relative_to(root)
            records = _read_json_list(path)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            index.errors.append(f"invalid capture record file {path}: {exc}")
            continue
        index.capture_files.append(path.relative_to(root).as_posix())
        for position, record in enumerate(records):
            capture_id = str(record.get("capture_id", "")).strip()
            source_id = str(record.get("source_id", "")).strip()
            activity_id = str(record.get("activity_id", "")).strip()
            branch = str(record.get("branch_id", "")).strip()
            prefix = f"{path}:{position + 1}"
            if not capture_id or not source_id or not activity_id:
                index.errors.append(f"{prefix}: capture_id, source_id, and activity_id are required")
                continue
            if capture_id in index.captures:
                index.errors.append(f"{prefix}: duplicate capture_id {capture_id}")
                continue
            if source_id in index.sources:
                index.errors.append(f"{prefix}: duplicate source_id {source_id}")
                continue
            activity = index.activities.get(activity_id)
            if not activity:
                index.errors.append(f"{prefix}: unresolved activity_id {activity_id}")
            elif activity.get("branch_id") != branch:
                index.errors.append(f"{prefix}: capture/activity branch mismatch")
            elif activity.get("outcome") != "success":
                index.errors.append(f"{prefix}: capture linked to non-success activity")
            elif capture_id not in (activity.get("output_capture_ids") or []):
                index.errors.append(f"{prefix}: activity does not bind output capture {capture_id}")
            source_url = str(record.get("source_url", ""))
            if branch not in VALID_BRANCHES or not _is_http_url(source_url):
                index.errors.append(f"{prefix}: invalid branch or source_url")
            raw_path = _safe_artifact_path(root, path, str(record.get("raw_text_ref", "")))
            if raw_path is None or not raw_path.is_file():
                index.errors.append(f"{prefix}: raw_text_ref is missing or escapes workspace")
            else:
                payload = raw_path.read_bytes()
                if not payload.strip():
                    index.errors.append(f"{prefix}: capture contains no readable bytes")
                actual_hash = "sha256:" + hashlib.sha256(payload).hexdigest()
                if actual_hash != str(record.get("bytes_hash", "")):
                    index.errors.append(f"{prefix}: bytes_hash mismatch")
                if len(payload) != record.get("byte_length") or not record.get("byte_length"):
                    index.errors.append(f"{prefix}: byte_length mismatch")
            index.captures[capture_id] = record
            index.sources[source_id] = record
    return index


def summarize_consumption(index: EvidenceIndex) -> dict[str, int | float | None]:
    """Derive telemetry from evidence; never synthesize missing values."""
    activities = list(index.activities.values())
    starts: list[datetime] = []
    finishes: list[datetime] = []
    for activity in activities:
        try:
            starts.append(datetime.fromisoformat(str(activity["started_at"]).replace("Z", "+00:00")))
            finishes.append(datetime.fromisoformat(str(activity["finished_at"]).replace("Z", "+00:00")))
        except (KeyError, ValueError):
            continue
    elapsed = (max(finishes) - min(starts)).total_seconds() if starts and finishes else 0.0
    return {
        "total_queries": sum(1 for a in activities if a.get("action_type") == "search"),
        "total_sources_visited": sum(1 for a in activities if a.get("action_type") == "navigate" and a.get("outcome") == "success"),
        "total_comments_extracted": sum(
            int((c.get("extraction_limits") or {}).get("items_extracted") or 0)
            for c in index.captures.values()
            if c.get("branch_id") == "social"
        ),
        "total_browser_actions": len(activities),
        "elapsed_wall_time_seconds": elapsed,
    }


def _utc_now_z() -> str:
    """Return an ISO-8601 UTC timestamp formatted with trailing Z."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _rel_or_str(workspace: Path, target: Path | str | None) -> str | None:
    """Return a workspace-relative POSIX string when inside workspace, else string path."""
    if target is None:
        return None
    candidate = Path(target)
    if not candidate.is_absolute():
        return candidate.as_posix()
    try:
        return candidate.resolve().relative_to(workspace.resolve()).as_posix()
    except ValueError:
        return str(candidate)


def _read_record_list(path: Path) -> list[dict[str, Any]]:
    """Read an existing JSON array of DRS-1.1 records if present."""
    import json

    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, dict):
        for key in ("records", "activities", "captures", "items"):
            if isinstance(raw.get(key), list):
                return list(raw[key])
    raise ValueError(f"Unsupported evidence JSON container in {path}")


def _write_json_list(path: Path, records: list[dict[str, Any]]) -> None:
    """Write a JSON list of DRS-1.1 records atomically."""
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def summarize_browser_provenance(index: EvidenceIndex) -> dict[str, Any]:
    """Summarize execution engines, modes, capture methods, and browser-first tiers."""
    engines: dict[str, int] = {}
    modes: dict[str, int] = {}
    capture_methods: dict[str, int] = {}
    tier_counts = {
        "host_integrated": 0,
        "local_playwright": 0,
        "api_fallback": 0,
        "other": 0,
    }

    for activity in index.activities.values():
        details = activity.get("tool_details") or {}
        engine = str(details.get("engine") or "unknown")
        mode = str(details.get("mode") or "unknown")
        engines[engine] = engines.get(engine, 0) + 1
        modes[mode] = modes.get(mode, 0) + 1
        if engine in HOST_INTEGRATED_ENGINES or mode in {"host_integrated", "cdp_attach", "mcp", "cua"}:
            tier_counts["host_integrated"] += 1
        elif engine.startswith("playwright") or mode == "standalone":
            tier_counts["local_playwright"] += 1
        elif engine == "api-fetch" or mode == "api_fallback":
            tier_counts["api_fallback"] += 1
        else:
            tier_counts["other"] += 1

    for capture in index.captures.values():
        method = str(capture.get("method") or "unknown")
        capture_methods[method] = capture_methods.get(method, 0) + 1

    return {
        "total_activities": len(index.activities),
        "total_captures": len(index.captures),
        "engines": engines,
        "modes": modes,
        "capture_methods": capture_methods,
        "tier_counts": tier_counts,
    }


def record_browser_evidence(
    workspace_dir: str | Path,
    url: str,
    *,
    final_url: str | None = None,
    branch: str = "documentary",
    question_ids: list[str] | None = None,
    source_id: str | None = None,
    engine: str = "host-subagent",
    mode: str = "host_integrated",
    method: str | None = None,
    action_type: str = "navigate",
    outcome: str = "success",
    purpose: str | None = None,
    text: str | None = None,
    text_file: str | Path | None = None,
    raw_text_out: str | Path | None = None,
    screenshot_ref: str | None = None,
    dom_locator: str | None = None,
    observed_state_ref: str | None = None,
    target_locator: dict[str, Any] | None = None,
    action_payload: dict[str, Any] | None = None,
    response_status: int | None = 200,
    items_extracted: int = 1,
    total_estimated: int | None = None,
    truncated: bool = False,
    truncation_reason: str | None = None,
    limitation: str | None = None,
    activity_log_path: str | Path | None = None,
    capture_records_path: str | Path | None = None,
    coverage_path: str | Path | None = None,
    update_coverage: bool = False,
    activity_id: str | None = None,
    capture_id: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
    artifact_version: int = 1,
) -> dict[str, Any]:
    """Record a DRS-1.1 browser activity (and SHA-256 verified capture) from any browser tier."""
    import hashlib
    import json
    import uuid

    if branch not in VALID_BRANCHES:
        raise ValueError(f"Invalid branch {branch!r}; expected one of {sorted(VALID_BRANCHES)}")
    if action_type not in VALID_ACTION_TYPES:
        raise ValueError(f"Invalid action_type {action_type!r}; expected one of {sorted(VALID_ACTION_TYPES)}")
    if outcome not in VALID_OUTCOMES:
        raise ValueError(f"Invalid outcome {outcome!r}; expected one of {sorted(VALID_OUTCOMES)}")

    qids = [str(q).strip() for q in (question_ids or ["Q1"]) if str(q).strip()]
    if not qids:
        raise ValueError("question_ids must contain at least one non-empty question ID")

    workspace = Path(workspace_dir).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    act_log_path = Path(activity_log_path) if activity_log_path else workspace / "activity-log.json"
    if not act_log_path.is_absolute():
        act_log_path = workspace / act_log_path
    cap_rec_path = Path(capture_records_path) if capture_records_path else workspace / "capture-records.json"
    if not cap_rec_path.is_absolute():
        cap_rec_path = workspace / cap_rec_path

    resolved_final_url = final_url or url
    now_z = _utc_now_z()
    start_ts = started_at or now_z
    end_ts = finished_at or start_ts
    act_id = activity_id or f"act-{uuid.uuid4().hex[:12]}"
    resolved_method = method or ENGINE_DEFAULT_METHODS.get(engine, "host_browser_dom")
    resolved_source_id = source_id or f"src-{hashlib.sha256(resolved_final_url.encode('utf-8')).hexdigest()[:10]}"

    raw_content: bytes | None = None
    if text_file is not None:
        raw_content = Path(text_file).read_bytes()
    elif text is not None:
        raw_content = text.encode("utf-8")

    capture_record: dict[str, Any] | None = None
    output_capture_ids: list[str] = []
    written_raw_path: Path | None = None

    if raw_content is not None and len(raw_content) > 0:
        cap_id = capture_id or f"cap-{uuid.uuid4().hex[:12]}"
        if raw_text_out is not None:
            written_raw_path = Path(raw_text_out)
            if not written_raw_path.is_absolute():
                written_raw_path = workspace / written_raw_path
        else:
            written_raw_path = workspace / "captures" / f"{cap_id}.txt"
        written_raw_path.parent.mkdir(parents=True, exist_ok=True)
        written_raw_path.write_bytes(raw_content)

        digest = hashlib.sha256(raw_content).hexdigest()
        raw_ref = _rel_or_str(workspace, written_raw_path) or str(written_raw_path)
        shot_ref = _rel_or_str(workspace, screenshot_ref)
        capture_record = {
            "schema_version": "1.1.0",
            "capture_id": cap_id,
            "source_id": resolved_source_id,
            "branch_id": branch,
            "activity_id": act_id,
            "retrieved_at": end_ts,
            "source_url": url,
            "final_url": resolved_final_url,
            "method": resolved_method,
            "bytes_hash": f"sha256:{digest}",
            "byte_length": len(raw_content),
            "dom_locator": dom_locator,
            "raw_text_ref": raw_ref,
            "screenshot_ref": shot_ref,
            "extraction_limits": {
                "truncated": bool(truncated),
                "items_extracted": max(0, int(items_extracted)),
                "total_estimated": total_estimated,
                "truncation_reason": truncation_reason,
            },
            "artifact_version": max(1, int(artifact_version)),
        }
        captures = _read_record_list(cap_rec_path)
        captures.append(capture_record)
        _write_json_list(cap_rec_path, captures)
        output_capture_ids.append(cap_id)
    elif outcome == "success":
        raise ValueError("Non-empty text or text_file is required when outcome is 'success'")
    elif limitation is None:
        limitation = f"{outcome}_without_capture"

    activity_record = {
        "schema_version": "1.1.0",
        "activity_id": act_id,
        "branch_id": branch,
        "question_ids": qids,
        "purpose": purpose or f"Browser {action_type} ({engine}) for {branch} branch",
        "observed_state_ref": observed_state_ref,
        "action_type": action_type,
        "target_locator": target_locator,
        "action_payload": action_payload,
        "started_at": start_ts,
        "finished_at": end_ts,
        "final_url": resolved_final_url,
        "outcome": outcome,
        "output_capture_ids": output_capture_ids,
        "limitation": limitation,
        "tool_details": {
            "engine": engine,
            "mode": mode,
            "response_status": response_status,
        },
    }
    activities = _read_record_list(act_log_path)
    activities.append(activity_record)
    _write_json_list(act_log_path, activities)

    cov_file = Path(coverage_path) if coverage_path else workspace / "research-coverage.json"
    if not cov_file.is_absolute():
        cov_file = workspace / cov_file
    if update_coverage and cov_file.exists():
        cov = json.loads(cov_file.read_text(encoding="utf-8"))
        ev = cov.setdefault(
            "execution_evidence",
            {"activity_logs": [], "capture_records": [], "validation_errors": []},
        )
        act_rel = _rel_or_str(workspace, act_log_path)
        if act_rel and act_rel not in ev.setdefault("activity_logs", []):
            ev["activity_logs"].append(act_rel)
        if capture_record is not None:
            cap_rel = _rel_or_str(workspace, cap_rec_path)
            if cap_rel and cap_rel not in ev.setdefault("capture_records", []):
                ev["capture_records"].append(cap_rel)
        cov["updated_at"] = _utc_now_z()
        cov_file.write_text(json.dumps(cov, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return {
        "activity": activity_record,
        "capture": capture_record,
        "activity_log_path": str(act_log_path),
        "capture_records_path": str(cap_rec_path),
        "raw_text_path": str(written_raw_path) if written_raw_path else None,
    }


def _cmd_self_test() -> int:
    """Exercise host-browser and playwright evidence recording plus hash verification."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        res_doc = record_browser_evidence(
            ws,
            "https://example.org/spec",
            branch="documentary",
            question_ids=["Q1"],
            engine="host-subagent",
            mode="host_integrated",
            action_type="navigate",
            text="Official specification excerpt for Q1 verification.\n",
        )
        res_soc = record_browser_evidence(
            ws,
            "https://community.example.org/thread/42",
            branch="social",
            question_ids=["Q1"],
            engine="chrome-devtools-mcp",
            mode="host_integrated",
            action_type="extract",
            items_extracted=5,
            text="Practitioner replies confirming the limitation under load.\n",
        )
        record_browser_evidence(
            ws,
            "https://paywall.example.org/report",
            branch="documentary",
            question_ids=["Q1"],
            engine="cua-driver",
            mode="host_integrated",
            action_type="navigate",
            outcome="blocked",
            response_status=403,
            limitation="HTTP 403 paywall",
        )
        index = load_evidence_index(ws)
        if index.errors:
            raise AssertionError(f"Unexpected evidence validation errors: {index.errors}")
        if len(index.activities) != 3 or len(index.captures) != 2:
            raise AssertionError(f"Unexpected counts: activities={len(index.activities)}, captures={len(index.captures)}")
        prov = summarize_browser_provenance(index)
        if prov["tier_counts"]["host_integrated"] != 3:
            raise AssertionError(f"Expected 3 host_integrated actions, got {prov}")
        if res_doc["capture"]["method"] != "host_browser_dom" or res_soc["capture"]["method"] != "host_browser_mcp":
            raise AssertionError("Engine-to-method mapping mismatch")
        cons = summarize_consumption(index)
        if cons["total_comments_extracted"] != 5 or cons["total_sources_visited"] != 1:
            raise AssertionError(f"Unexpected consumption summary: {cons}")
    print("execution_evidence.py self-test ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for recording and verifying DRS-1.1 browser evidence."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="DRS-1.1 browser evidence recording and verification helper")
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record", help="Record a host-integrated or browser capture into DRS-1.1 logs")
    rec.add_argument("--workspace", required=True)
    rec.add_argument("--url", required=True)
    rec.add_argument("--final-url", default=None)
    rec.add_argument("--branch", default="documentary", choices=sorted(VALID_BRANCHES))
    rec.add_argument("--question-id", action="append", dest="question_ids", default=None)
    rec.add_argument("--source-id", default=None)
    rec.add_argument("--engine", default="host-subagent")
    rec.add_argument("--mode", default="host_integrated")
    rec.add_argument("--method", default=None)
    rec.add_argument("--action-type", default="navigate", choices=sorted(VALID_ACTION_TYPES))
    rec.add_argument("--outcome", default="success", choices=sorted(VALID_OUTCOMES))
    rec.add_argument("--purpose", default=None)
    rec.add_argument("--text", default=None)
    rec.add_argument("--text-file", default=None)
    rec.add_argument("--raw-text-out", default=None)
    rec.add_argument("--screenshot", default=None)
    rec.add_argument("--dom-locator", default=None)
    rec.add_argument("--observed-state-ref", default=None)
    rec.add_argument("--response-status", type=int, default=200)
    rec.add_argument("--items-extracted", type=int, default=1)
    rec.add_argument("--total-estimated", type=int, default=None)
    rec.add_argument("--truncated", action="store_true")
    rec.add_argument("--truncation-reason", default=None)
    rec.add_argument("--limitation", default=None)
    rec.add_argument("--activity-log", default=None)
    rec.add_argument("--capture-records", default=None)
    rec.add_argument("--coverage-path", default=None)
    rec.add_argument("--update-coverage", action="store_true")

    ver = sub.add_parser("verify", help="Verify DRS-1.1 activity and capture evidence in a workspace")
    ver.add_argument("--workspace", required=True)
    ver.add_argument("--activity-log", action="append", dest="activity_logs", default=None)
    ver.add_argument("--capture-records", action="append", dest="capture_records", default=None)

    sub.add_parser("self-test", help="Run built-in execution_evidence self-test")

    args = parser.parse_args(argv)
    if args.command == "self-test":
        return _cmd_self_test()
    if args.command == "verify":
        ws = Path(args.workspace).resolve()
        index = load_evidence_index(
            ws,
            activity_paths=args.activity_logs,
            capture_paths=args.capture_records,
        )
        payload = {
            "ok": len(index.errors) == 0,
            "errors": list(index.errors),
            "consumption": summarize_consumption(index),
            "provenance": summarize_browser_provenance(index),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if payload["ok"] else 1
    if args.command == "record":
        result = record_browser_evidence(
            args.workspace,
            args.url,
            final_url=args.final_url,
            branch=args.branch,
            question_ids=args.question_ids,
            source_id=args.source_id,
            engine=args.engine,
            mode=args.mode,
            method=args.method,
            action_type=args.action_type,
            outcome=args.outcome,
            purpose=args.purpose,
            text=args.text,
            text_file=args.text_file,
            raw_text_out=args.raw_text_out,
            screenshot_ref=args.screenshot,
            dom_locator=args.dom_locator,
            observed_state_ref=args.observed_state_ref,
            response_status=args.response_status,
            items_extracted=args.items_extracted,
            total_estimated=args.total_estimated,
            truncated=args.truncated,
            truncation_reason=args.truncation_reason,
            limitation=args.limitation,
            activity_log_path=args.activity_log,
            capture_records_path=args.capture_records,
            coverage_path=args.coverage_path,
            update_coverage=args.update_coverage,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
