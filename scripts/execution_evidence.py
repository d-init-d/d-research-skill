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
                actual_hash = "sha256:" + hashlib.sha256(payload).hexdigest()
                if actual_hash != str(record.get("bytes_hash", "")):
                    index.errors.append(f"{prefix}: bytes_hash mismatch")
                if len(payload) != record.get("byte_length"):
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
