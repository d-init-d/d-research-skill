#!/usr/bin/env python3
"""Research-plan manager for D Research's context-safe protocol.

A "research plan" is a JSON file (start from
``templates/research-plan.json``) that describes the work an agent
intends to do for a long-horizon research task. The plan splits the
work into discrete tasks with dependencies, output paths, and
status; gates declare the assertions that must hold before moving
between phases (plan -> execute -> synthesize -> release).

See ``references/research-plan-protocol.md`` for the protocol this
script enforces.

Subcommands
-----------
* ``init``            create a generic draft plan (schema 2.0) in a workspace
* ``check``           validate schema + dependency graph + gate refs
* ``status``          print a one-line status per task
* ``parallelizable``  print task ids that are ready to dispatch now
* ``mark``            set a task's status (todo/running/done/blocked)
* ``block``           set status=blocked AND record a blocker_reason
* ``add-task``        append a new task row
* ``render``          write a human-readable PLAN.md review artefact
* ``approve``         record human approval before execution
* ``revoke``          clear approval after scope changes
* ``configure-execution`` annotate tasks from research.config.json
* ``set-execution``   override one task's main/subagent assignment
* ``migrate``         upgrade a v1 plan to schema 2.0
* ``gate``            run a named gate's assertions
* ``self-test``       offline self-test (multiple sub-tests)

Design notes
------------
* The plan is JSON (not YAML or a markdown front-matter doc) so the
  script can parse it with the stdlib only and round-trip it without
  losing comments. The ``$comment`` field at the top is preserved
  on rewrite.
* Every write is atomic: write to a sibling temp file, then rename.
* The script never touches files outside the plan; gate assertions
  that check ``evidence-ledger.csv`` etc. read paths relative to
  the plan's directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allowed values for plan fields. Keep in sync with the template.
VALID_STATUS = {"todo", "running", "done", "blocked"}
TERMINAL_STATUS = {"done", "blocked"}
VALID_OWNER_PREFIX = ("main", "sub-")
VALID_PHASE = {"research", "synthesis"}
PLAN_SCHEMA_VERSION = "2.0"
SUPPORTED_SCHEMA_VERSIONS = {"1.0", "1", "2.0", ""}  # empty/missing treated as v1

# Required top-level keys.
REQUIRED_TOP_KEYS = {
    "plan_id",
    "title",
    "workspace_dir",
    "plan_render_path",
    "execution_profile",
    "scope",
    "sub_questions",
    "approval",
    "tasks",
    "gates",
    "stopping_criteria",
}

# Required task keys.
REQUIRED_TASK_KEYS = {
    "id",
    "description",
    "depends_on",
    "parallel_safe",
    "owner",
    "outputs",
    "status",
}

# Output path substrings that mark a task as synthesis when phase is absent (v1 compat).
_SYNTHESIS_OUTPUT_MARKERS = (
    "report.md",
    "report-citations",
    "citations.md",
    "bibliography",
    "final-report",
    "references.md",
    "references.bib",
    "references.ris",
)

PLACEHOLDER_PATTERNS = (
    "<!-- Replace with",
    "<!-- Findings for task",
    "<!-- Document limitations",
    "TODO:",
    "TBD",
    "[placeholder]",
)

REQUIRED_APPROVAL_KEYS = {"approved_by", "approved_at", "notes"}
APPROVAL_DIGEST_KEY = "plan_sha256"
_SHA256_VALUE_RE = re.compile(r"sha256:[0-9a-f]{64}")
REQUIRED_EXECUTION_KEYS = {
    "agent",
    "subagent_slot",
    "parallel_threads",
    "max_parallel_threads",
    "context_length",
    "context_budget",
    "checkpoint_policy",
}

STANDARD_WORKSPACE_DIRS = [
    "research-output",
    "research-output/notes",
    "research-output/sections",
]

EVIDENCE_LEDGER_HEADER = (
    "claim_id,claim,sub_question,source_title,source_url,source_type,"
    "date_published,date_accessed,access_method,evidence,quote_or_anchor,"
    "contradiction,confidence,notes,archive_url,content_hash,snapshot_status,"
    "verifiability,verifiability_note,license_spdx,robots_status,"
    "prov_activity_id,record_type\n"
)

CHECKLIST_CONTRACT_VERSION = "v1"
CHECKLIST_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent
    / "references"
    / "reproducibility-checklist.md"
)
_CHECKLIST_VERSION_RE = re.compile(
    r"<!--\s*d-research-checklist:(?P<version>v[0-9]+)\s*-->"
)
_CHECKLIST_ITEM_RE = re.compile(
    r"^\s*[-*+]\s*\[(?P<state>[ xX])\]\s*"
    r"<!--\s*(?P<id>DRC-[0-9]{3})\s*-->\s*(?P<label>.*)$"
)
_CHECKBOX_LINE_RE = re.compile(r"^\s*[-*+]\s*\[[ xX]\].*$")

# Loaded from templates/route-manifest.json when present; fallback embedded.
CANONICAL_GATES: dict[str, list[str]] = {
    "plan_ready": [
        "schema_valid",
        "plan_complete",
        "workspace_layout",
        "execution_configured",
        "plan_rendered",
        "no_dependency_cycles",
        "no_orphan_dependencies",
        "no_task_is_done",
        "standard_gates_intact",
    ],
    "execute_ready": [
        "schema_valid",
        "plan_complete",
        "workspace_layout",
        "execution_configured",
        "plan_rendered",
        "no_dependency_cycles",
        "no_orphan_dependencies",
        "no_task_is_done",
        "plan_approved",
        "standard_gates_intact",
    ],
    "dispatch_ready": [
        "schema_valid",
        "plan_complete",
        "workspace_layout",
        "execution_configured",
        "plan_rendered",
        "no_dependency_cycles",
        "no_orphan_dependencies",
        "no_task_is_done",
        "plan_approved",
        "standard_gates_intact",
    ],
    "synthesize_ready": [
        "schema_valid",
        "workspace_layout",
        "execution_configured",
        "research_tasks_terminal",
        "research_outputs_exist",
        "blocked_research_justified",
        "ledger_validates",
        "ledger_hmac_verified",
        "reproducibility_checklist_complete",
        "standard_gates_intact",
    ],
    "release_ready": [
        "synthesize_ready",
        "synthesis_tasks_terminal",
        "synthesis_outputs_exist",
        "final_report_valid",
        "rendered_citations_exist",
        "claim_coverage_complete",
        "stopping_criteria_satisfied",
        "standard_gates_intact",
    ],
}


def _load_canonical_gates() -> dict[str, list[str]]:
    manifest = (
        Path(__file__).resolve().parent.parent / "templates" / "route-manifest.json"
    )
    if not manifest.is_file():
        return dict(CANONICAL_GATES)
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        gates = data.get("canonical_gates") or {}
        out: dict[str, list[str]] = {}
        for name, assertions in gates.items():
            if isinstance(assertions, list) and assertions:
                out[str(name)] = [str(a) for a in assertions]
        return out or dict(CANONICAL_GATES)
    except (OSError, json.JSONDecodeError, TypeError):
        return dict(CANONICAL_GATES)

DEFAULT_CONFIG: dict[str, Any] = {
    "researchPlan": {
        "context": {
            "mainContextLength": None,
            "taskBudgetRatio": 0.5,
            "writeFindingsImmediately": True,
        },
        "subagents": {
            "slots": [
                {
                    "id": "default",
                    "agent": None,
                    "contextLength": None,
                    "maxParallel": None,
                }
            ]
        },
        "workspace": {
            "baseDir": ".",
            "nameTemplate": "research-{slug}-{date}",
            "fallbackToCwdOnError": True,
        },
        "finalResponse": {"reportWorkspacePath": True},
    }
}

# Path resolution helpers operate relative to the plan file's parent
# directory so plans can be moved around without breaking checks.



def _canonical_gate_defs() -> dict[str, dict[str, Any]]:
    """Build gate objects from canonical assertion lists."""
    descriptions = {
        "plan_ready": "Plan is shaped correctly, rendered for review, and ready for approval.",
        "execute_ready": "Plan is approved and ready to dispatch.",
        "dispatch_ready": "Plan is approved and ready to dispatch.",
        "synthesize_ready": "Research-phase tasks finished; ledger and checklist OK.",
        "release_ready": "Synthesis complete; report and citations valid; coverage OK.",
    }
    out: dict[str, dict[str, Any]] = {}
    for name, assertions in _load_canonical_gates().items():
        if name == "dispatch_ready":
            continue  # execute_ready is the stored alias
        out[name] = {
            "description": descriptions.get(name, name),
            "assertions": list(assertions),
        }
    return out


def _plan_dir(plan_path: Path) -> Path:
    return plan_path.resolve().parent


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_iso_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _positive_int_or_none(value: Any) -> int | None:
    if value is None or value == "none" or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _float_in_range(value: Any, default: float, low: float, high: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed < low or parsed > high:
        return default
    return parsed


def _context_budget(length: int | None, ratio: float) -> int | None:
    if length is None:
        return None
    return max(1, int(length * ratio))


def _normalise_slot(raw: dict[str, Any], fallback_id: str) -> dict[str, Any]:
    slot_id = str(raw.get("id") or fallback_id).strip() or fallback_id
    agent = raw.get("agent")
    if agent is None or str(agent).strip().lower() in {"", "none", "null"}:
        agent_value = None
    else:
        agent_value = str(agent).strip()
    return {
        "id": _slugify(slot_id),
        "agent": agent_value,
        "context_length": _positive_int_or_none(raw.get("contextLength")),
        "max_parallel": _positive_int_or_none(raw.get("maxParallel")),
    }


def _subagent_slots(config: dict[str, Any]) -> list[dict[str, Any]]:
    rp = config.get("researchPlan", {})
    subagents = rp.get("subagents", {}) if isinstance(rp, dict) else {}
    if not isinstance(subagents, dict):
        subagents = {}
    raw_slots = subagents.get("slots")
    slots: list[dict[str, Any]] = []
    if isinstance(raw_slots, list) and raw_slots:
        for idx, raw in enumerate(raw_slots, start=1):
            if isinstance(raw, dict):
                slots.append(_normalise_slot(raw, f"slot-{idx}"))
    else:
        # Backwards compatibility with the older enabled/maxParallel shape.
        slots.append(
            {
                "id": "default",
                "agent": None,
                "context_length": None,
                "max_parallel": _positive_int_or_none(subagents.get("maxParallel")),
            }
        )
    return slots or [
        {
            "id": "default",
            "agent": None,
            "context_length": None,
            "max_parallel": None,
        }
    ]


def _checkpoint_policy(config: dict[str, Any]) -> str:
    rp = config.get("researchPlan", {})
    context = rp.get("context", {}) if isinstance(rp, dict) else {}
    if not isinstance(context, dict):
        context = {}
    if context.get("writeFindingsImmediately", True):
        return (
            "write findings to declared output files immediately; split the task "
            "before reading sources or inputs that risk exceeding the context budget"
        )
    return "write final task artefact before marking done"


def _execution_profile(
    config: dict[str, Any], config_path: Path | None
) -> dict[str, Any]:
    rp = config.get("researchPlan", {})
    context = rp.get("context", {}) if isinstance(rp, dict) else {}
    if not isinstance(context, dict):
        context = {}
    ratio = _float_in_range(context.get("taskBudgetRatio"), 0.5, 0.1, 0.9)
    return {
        "source": str(config_path) if config_path is not None else "defaults",
        "main_context_length": _positive_int_or_none(context.get("mainContextLength")),
        "task_budget_ratio": ratio,
        "checkpoint_policy": _checkpoint_policy(config),
        "subagent_slots": _subagent_slots(config),
    }


def _configured_slots(profile: dict[str, Any]) -> list[dict[str, Any]]:
    slots = profile.get("subagent_slots", [])
    if not isinstance(slots, list):
        return []
    return [
        s
        for s in slots
        if isinstance(s, dict)
        and s.get("agent")
        and _positive_int_or_none(s.get("context_length")) is not None
        and _positive_int_or_none(s.get("max_parallel")) is not None
    ]


def _slot_by_id(profile: dict[str, Any], slot_id: str) -> dict[str, Any] | None:
    for slot in _configured_slots(profile):
        if slot.get("id") == slot_id:
            return slot
    return None


def _execution_for_task(
    task: dict[str, Any], profile: dict[str, Any], subagent_index: int
) -> dict[str, Any]:
    ratio = _float_in_range(profile.get("task_budget_ratio"), 0.5, 0.1, 0.9)
    slots = _configured_slots(profile)
    use_subagent = (
        bool(slots)
        and bool(task.get("parallel_safe"))
        and str(task.get("owner", "")).startswith("sub-")
    )
    if use_subagent:
        slot = slots[subagent_index % len(slots)]
        context_length = _positive_int_or_none(slot.get("context_length"))
        max_parallel = _positive_int_or_none(slot.get("max_parallel")) or 1
        return {
            "agent": "subagent",
            "subagent_slot": slot.get("id"),
            "parallel_threads": 1,
            "max_parallel_threads": max_parallel,
            "context_length": context_length,
            "context_budget": _context_budget(context_length, ratio),
            "checkpoint_policy": profile.get("checkpoint_policy"),
        }
    context_length = _positive_int_or_none(profile.get("main_context_length"))
    return {
        "agent": "main",
        "subagent_slot": None,
        "parallel_threads": 0,
        "max_parallel_threads": 0,
        "context_length": context_length,
        "context_budget": _context_budget(context_length, ratio),
        "checkpoint_policy": profile.get("checkpoint_policy"),
    }


def apply_execution_config(
    plan: dict[str, Any], config: dict[str, Any], config_path: Path | None
) -> None:
    profile = _execution_profile(config, config_path)
    plan["execution_profile"] = profile
    subagent_index = 0
    for task in plan.get("tasks", []):
        execution = _execution_for_task(task, profile, subagent_index)
        if execution["agent"] == "subagent":
            subagent_index += 1
        task["execution"] = execution


def _find_config(explicit: str | None, cwd: Path) -> Path | None:
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.is_absolute() else (cwd / p).resolve()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / "research.config.json"
        if candidate.is_file():
            return candidate.resolve()
    return None


def validate_access_config(config: dict[str, Any]) -> list[str]:
    """Fail closed on never-allowed access/crawl safety keys."""
    errors: list[str] = []
    access = config.get("access") if isinstance(config.get("access"), dict) else {}
    crawl = config.get("crawl") if isinstance(config.get("crawl"), dict) else {}
    if access.get("allowCaptchaSolving") is True:
        errors.append(
            "access.allowCaptchaSolving=true is never allowed (captcha solving forbidden)"
        )
    if access.get("allowStealthEvasion") is True:
        errors.append(
            "access.allowStealthEvasion=true is never allowed (stealth evasion forbidden)"
        )
    if crawl.get("respectRobots") is False:
        errors.append(
            "crawl.respectRobots=false is never allowed (robots must be respected)"
        )
    return errors


def _load_config(explicit: str | None, cwd: Path) -> tuple[dict[str, Any], Path | None]:
    config_path = _find_config(explicit, cwd)
    config = DEFAULT_CONFIG
    if config_path is None:
        return config, None
    with config_path.open("r", encoding="utf-8") as fh:
        loaded = json.load(fh)
    if not isinstance(loaded, dict):
        raise ValueError(f"config must be a JSON object: {config_path}")
    safety = validate_access_config(loaded)
    if safety:
        raise ValueError("; ".join(safety))
    merged = _deep_merge(config, loaded)
    safety2 = validate_access_config(merged)
    if safety2:
        raise ValueError("; ".join(safety2))
    return merged, config_path


def _slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or "research"


def _render_workspace_name(template: str, slug: str) -> str:
    now = datetime.now(timezone.utc)
    try:
        rendered = template.format(
            slug=_slugify(slug),
            date=now.strftime("%Y-%m-%d"),
            datetime=now.strftime("%Y-%m-%d-%H%M%S"),
        )
    except (KeyError, ValueError):
        rendered = f"research-{_slugify(slug)}-{now.strftime('%Y-%m-%d')}"
    return _slugify(rendered)


def _assert_writable_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise NotADirectoryError(str(path))
    with tempfile.TemporaryDirectory(prefix=".research-write-test-", dir=str(path)):
        pass


def _unique_workspace(base_dir: Path, workspace_name: str) -> Path:
    candidate = base_dir / workspace_name
    if not candidate.exists():
        return candidate
    for idx in range(2, 1000):
        candidate = base_dir / f"{workspace_name}-{idx:02d}"
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"could not find a free workspace name under {base_dir}")


def _workspace_from_config(
    config: dict[str, Any], config_path: Path | None, cwd: Path, slug: str
) -> tuple[Path, str | None]:
    rp = config.get("researchPlan", {})
    workspace_obj = rp.get("workspace", {}) if isinstance(rp, dict) else {}
    workspace_cfg = workspace_obj if isinstance(workspace_obj, dict) else {}
    base_raw = workspace_cfg.get("baseDir", ".")
    if not isinstance(base_raw, str) or not base_raw.strip():
        base_raw = "."
    base = Path(base_raw).expanduser()
    if not base.is_absolute():
        root = config_path.parent if config_path is not None else cwd
        base = root / base
    base = base.resolve()

    fallback = bool(workspace_cfg.get("fallbackToCwdOnError", True))
    warning: str | None = None
    try:
        _assert_writable_directory(base)
    except OSError as exc:
        if not fallback:
            raise
        warning = (
            f"configured output folder {base} is not accessible ({exc}); "
            f"falling back to current directory {cwd}"
        )
        base = cwd.resolve()
        _assert_writable_directory(base)

    template = workspace_cfg.get("nameTemplate", "research-{slug}-{date}")
    if not isinstance(template, str) or not template.strip():
        template = "research-{slug}-{date}"
    workspace_name = _render_workspace_name(template, slug)
    return _unique_workspace(base, workspace_name), warning


_WINDOWS_RESERVED_PATH_CHARS = frozenset('<>:"|?*')
_WINDOWS_DEVICE_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "CONIN$",
        "CONOUT$",
        *(f"COM{number}" for number in range(1, 10)),
        *(f"LPT{number}" for number in range(1, 10)),
        *(f"COM{number}" for number in "¹²³"),
        *(f"LPT{number}" for number in "¹²³"),
    }
)
_WINDOWS_DRIVE_PREFIX_RE = re.compile(r"^[A-Za-z]:")


def _portable_relative_path(
    raw: Any, *, allow_current_dir: bool = False
) -> tuple[str | None, str]:
    """Validate and canonicalize a workspace-relative portable path.

    Backslashes are treated as separators on every host. This makes the same
    plan fail or pass consistently on POSIX and Windows instead of relying on
    the path semantics of the machine running the checker.
    """

    if not isinstance(raw, str) or not raw or not raw.strip():
        return None, "path must be a non-empty string"
    if any(unicodedata.category(char) == "Cc" for char in raw):
        return None, "path contains a control character"

    portable = raw.replace("\\", "/")
    if allow_current_dir and portable == ".":
        return ".", "OK"
    if portable.startswith("/"):
        return None, "absolute, UNC, and root-relative paths are not allowed"
    if portable.startswith("~"):
        return None, "home-relative paths are not allowed"
    if _WINDOWS_DRIVE_PREFIX_RE.match(portable):
        return None, "Windows drive-qualified paths are not allowed"

    parts = portable.split("/")
    if any(part == "" for part in parts):
        return None, "path contains an empty segment"
    for part in parts:
        if part in {".", ".."}:
            return None, f"path contains forbidden segment {part!r}"
        if part.endswith((".", " ")):
            return None, f"path segment ends in a dot or space: {part!r}"
        reserved = sorted(set(part) & _WINDOWS_RESERVED_PATH_CHARS)
        if reserved:
            return (
                None,
                "path segment contains a Windows-reserved character "
                f"{reserved[0]!r}: {part!r}",
            )
        device_stem = part.split(".", 1)[0].rstrip(" .").upper()
        if device_stem in _WINDOWS_DEVICE_NAMES:
            return None, f"path uses a Windows-reserved device name: {part!r}"

    return "/".join(parts), "OK"


def _is_safe_relative_path(raw: str, *, allow_current_dir: bool = False) -> bool:
    canonical, _detail = _portable_relative_path(
        raw, allow_current_dir=allow_current_dir
    )
    return canonical is not None


def _portable_path_key(raw: Any) -> tuple[str, ...] | None:
    """Return a normalized case-insensitive key for a valid portable path."""

    canonical, _detail = _portable_relative_path(raw)
    if canonical is None:
        return None
    return tuple(
        unicodedata.normalize("NFC", part).casefold()
        for part in canonical.split("/")
    )


def _portable_paths_overlap(
    left: tuple[str, ...], right: tuple[str, ...]
) -> bool:
    """Return true for exact or ancestor/descendant portable path aliases."""

    shared = min(len(left), len(right))
    return left[:shared] == right[:shared]


def _portable_output_keys(outputs: Any) -> list[tuple[str, ...]] | None:
    """Validate one task's output tree declarations for safe dispatch."""

    if not isinstance(outputs, list) or not outputs:
        return None
    keys: list[tuple[str, ...]] = []
    for output in outputs:
        canonical, _detail = _portable_relative_path(output)
        key = _portable_path_key(output)
        if (
            canonical is None
            or key is None
            or not canonical.startswith("research-output/")
            or any(_portable_paths_overlap(key, other) for other in keys)
        ):
            return None
        keys.append(key)
    return keys


def _resolve_workspace_path(base: Path, raw: str) -> tuple[Path | None, str]:
    """Resolve a plan-derived path strictly inside the workspace.

    Rejects absolute paths, `..` traversal, and symlink/junction escapes
    where the final resolved target is outside base.
    """
    canonical, detail = _portable_relative_path(raw)
    if canonical is None:
        return None, f"invalid portable workspace path {raw!r}: {detail}"
    base_res = base.resolve()
    # Resolve against base; use strict=False so missing files can still be checked.
    target = base.joinpath(*canonical.split("/")).resolve()
    try:
        target.relative_to(base_res)
    except ValueError:
        return None, f"path escapes workspace: {raw!r}"
    # Parent of the final path must also remain inside workspace.
    try:
        target.parent.resolve().relative_to(base_res)
    except ValueError:
        return None, f"path parent escapes workspace: {raw!r}"
    return target, "OK"


def _scaffold_workspace(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    for rel in STANDARD_WORKSPACE_DIRS:
        (base / rel).mkdir(parents=True, exist_ok=True)
    ledger = base / "evidence-ledger.csv"
    if not ledger.exists():
        ledger.write_text(EVIDENCE_LEDGER_HEADER, encoding="utf-8")
    checklist = base / "reproducibility-checklist.md"
    if not checklist.exists() and CHECKLIST_TEMPLATE_PATH.is_file():
        shutil.copyfile(CHECKLIST_TEMPLATE_PATH, checklist)


def _schema_version(plan: dict[str, Any]) -> str:
    raw = plan.get("schema_version", "")
    if raw is None or raw == "":
        return "1.0"
    return str(raw)


def _infer_phase(task: dict[str, Any]) -> str:
    """Infer task phase for v1 plans missing an explicit phase field."""
    explicit = task.get("phase")
    if isinstance(explicit, str) and explicit in VALID_PHASE:
        return explicit
    for op in task.get("outputs") or []:
        op_norm = str(op).replace("\\", "/").lower()
        if any(marker in op_norm for marker in _SYNTHESIS_OUTPUT_MARKERS):
            return "synthesis"
    return "research"


def _tasks_by_phase(plan: dict[str, Any], phase: str) -> list[dict[str, Any]]:
    return [
        t
        for t in plan.get("tasks", [])
        if isinstance(t, dict) and _infer_phase(t) == phase
    ]


_V1_COMPAT_WARNED = False


def _apply_v1_compat(plan: dict[str, Any]) -> dict[str, Any]:
    """Compatibility adapter: accept v1 plans, infer phase, warn once per process.

    Never persist internal markers into plan JSON.
    """
    global _V1_COMPAT_WARNED
    version = _schema_version(plan)
    plan.pop("_compat_warned", None)
    if version in {"2.0"}:
        return plan
    for task in plan.get("tasks", []):
        if isinstance(task, dict) and "phase" not in task:
            task["phase"] = _infer_phase(task)
    # Apply the current canonical readiness gates in memory.  This keeps v1
    # plans usable through v3 without letting their weaker historical gate
    # definitions bypass current safety/release invariants.  Custom gates are
    # preserved, and nothing is written until the user explicitly migrates.
    old_gates = plan.get("gates")
    custom_gates: dict[str, Any] = {}
    canonical_names = set(_load_canonical_gates()) | {
        "execute_ready",
        "dispatch_ready",
    }
    if isinstance(old_gates, dict):
        custom_gates = {
            str(name): gate
            for name, gate in old_gates.items()
            if name not in canonical_names
        }
    plan["gates"] = {**_canonical_gate_defs(), **custom_gates}
    if not _V1_COMPAT_WARNED:
        print(
            "WARN: research plan schema < 2.0 loaded via compatibility adapter; "
            "run `research_plan.py migrate` before v4. Support ends in v4.",
            file=sys.stderr,
        )
        _V1_COMPAT_WARNED = True
    return plan


def _reject_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_json(value: str) -> Any:
    raise ValueError(f"non-finite JSON number is not allowed: {value}")


def _load_strict_json(plan_path: Path) -> Any:
    with plan_path.open("r", encoding="utf-8") as fh:
        return json.load(
            fh,
            object_pairs_hook=_reject_duplicate_object,
            parse_constant=_reject_nonfinite_json,
        )


def load(plan_path: Path) -> dict[str, Any]:
    """Load, strictly parse, and lightly normalise a plan from disk."""
    if not plan_path.exists():
        raise FileNotFoundError(f"plan file not found: {plan_path}")
    plan = _load_strict_json(plan_path)
    if not isinstance(plan, dict):
        raise ValueError(f"plan must be a JSON object, got {type(plan).__name__}")
    return _apply_v1_compat(plan)


def save(plan: dict[str, Any], plan_path: Path) -> None:
    """Atomically write a plan back to disk, preserving formatting."""
    if isinstance(plan, dict):
        plan.pop("_compat_warned", None)
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix=plan_path.name + ".", suffix=".tmp", dir=str(plan_path.parent)
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(plan, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp_name, plan_path)
    except Exception:
        # Best-effort cleanup; do not mask the original error.
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise


# ---------------------------------------------------------------------------
# Schema and graph validation
# ---------------------------------------------------------------------------


def validate_schema(plan: dict[str, Any]) -> list[str]:
    """Return a list of human-readable schema errors. Empty list = OK."""
    errors: list[str] = []
    missing = REQUIRED_TOP_KEYS - set(plan)
    if missing:
        errors.append(f"missing top-level keys: {sorted(missing)}")

    version = _schema_version(plan)
    if version not in SUPPORTED_SCHEMA_VERSIONS and version != "2.0":
        errors.append(f"unsupported schema_version: {version!r}")

    if "schema_version" in plan and (
        not isinstance(plan.get("schema_version"), (str, int))
        or isinstance(plan.get("schema_version"), bool)
    ):
        errors.append("`schema_version` must be a string (or legacy integer 1)")
    for key in ("plan_id", "title", "scope", "stopping_criteria"):
        if key in plan and not isinstance(plan.get(key), str):
            errors.append(f"`{key}` must be a string")
    if "notes" in plan and not isinstance(plan.get("notes"), str):
        errors.append("`notes` must be a string when present")
    if "stopping_criteria_satisfied" in plan and not isinstance(
        plan.get("stopping_criteria_satisfied"), bool
    ):
        errors.append("`stopping_criteria_satisfied` must be a boolean when present")

    sub_questions = plan.get("sub_questions")
    if not isinstance(sub_questions, list):
        errors.append("`sub_questions` must be a list")
    else:
        seen_question_ids: set[str] = set()
        for index, question in enumerate(sub_questions):
            if not isinstance(question, dict):
                errors.append(f"sub_questions[{index}] must be an object")
                continue
            question_id = question.get("id")
            question_text = question.get("text")
            if not isinstance(question_id, str) or not question_id:
                errors.append(f"sub_questions[{index}].id must be a non-empty string")
            elif question_id in seen_question_ids:
                errors.append(f"duplicate sub-question id: {question_id!r}")
            else:
                seen_question_ids.add(question_id)
            if not isinstance(question_text, str) or not question_text:
                errors.append(f"sub_questions[{index}].text must be a non-empty string")

    source_classes = plan.get("source_classes", [])
    if not isinstance(source_classes, list):
        errors.append("`source_classes` must be a list when present")
    else:
        for index, source_class in enumerate(source_classes):
            if not isinstance(source_class, str) or not source_class:
                errors.append(f"source_classes[{index}] must be a non-empty string")

    workspace_dir = plan.get("workspace_dir")
    if not isinstance(workspace_dir, str) or not workspace_dir:
        errors.append("`workspace_dir` must be a non-empty string")
    elif not _is_safe_relative_path(workspace_dir, allow_current_dir=True):
        errors.append(
            "`workspace_dir` must be `.` or a portable relative path inside the workspace"
        )

    plan_render_path = plan.get("plan_render_path")
    if not isinstance(plan_render_path, str) or not plan_render_path:
        errors.append("`plan_render_path` must be a non-empty string")
    elif not _is_safe_relative_path(plan_render_path):
        errors.append("`plan_render_path` must be a relative path inside the workspace")

    approval = plan.get("approval")
    if not isinstance(approval, dict):
        errors.append("`approval` must be an object")
    else:
        missing_a = REQUIRED_APPROVAL_KEYS - set(approval)
        if missing_a:
            errors.append(f"approval missing keys: {sorted(missing_a)}")
        approved_by = approval.get("approved_by", "")
        approved_at = approval.get("approved_at", "")
        notes = approval.get("notes", "")
        plan_sha256 = approval.get(APPROVAL_DIGEST_KEY, "")
        if not isinstance(approved_by, str):
            errors.append("approval.approved_by must be a string")
        if not isinstance(approved_at, str):
            errors.append("approval.approved_at must be a string")
        if not isinstance(notes, str):
            errors.append("approval.notes must be a string")
        if not isinstance(plan_sha256, str):
            errors.append("approval.plan_sha256 must be a string when present")
        if isinstance(approved_by, str) and isinstance(approved_at, str):
            if bool(approved_by) != bool(approved_at):
                errors.append(
                    "approval.approved_by and approval.approved_at must be set together"
                )
            if approved_at:
                try:
                    _parse_iso_utc(approved_at)
                except ValueError:
                    errors.append("approval.approved_at must be ISO 8601 UTC")
            if approved_by:
                if not isinstance(plan_sha256, str) or not _SHA256_VALUE_RE.fullmatch(
                    plan_sha256
                ):
                    errors.append(
                        "approval.plan_sha256 must bind the approved plan as "
                        "sha256:<64 lowercase hex>"
                    )
                else:
                    try:
                        current_plan_sha256 = _plan_approval_sha256(plan)
                    except (TypeError, ValueError) as exc:
                        errors.append(f"approved plan cannot be canonicalized: {exc}")
                    else:
                        if plan_sha256 != current_plan_sha256:
                            errors.append(
                                "approval.plan_sha256 does not match the current immutable "
                                "plan; revoke, render, and re-approve"
                            )
            elif isinstance(plan_sha256, str) and plan_sha256:
                errors.append("approval.plan_sha256 must be empty when approval is empty")

    execution_profile = plan.get("execution_profile")
    slot_ids: set[str] = set()
    slot_max_parallel: dict[str, int | None] = {}
    if not isinstance(execution_profile, dict):
        errors.append("`execution_profile` must be an object")
    else:
        slots = execution_profile.get("subagent_slots")
        if not isinstance(slots, list) or not slots:
            errors.append("execution_profile.subagent_slots must be a non-empty list")
        else:
            for i, slot in enumerate(slots):
                if not isinstance(slot, dict):
                    errors.append(
                        f"execution_profile.subagent_slots[{i}] must be an object"
                    )
                    continue
                slot_id = slot.get("id")
                if not isinstance(slot_id, str) or not slot_id:
                    errors.append(f"execution_profile.subagent_slots[{i}].id required")
                    continue
                if slot_id in slot_ids:
                    errors.append(f"duplicate subagent slot id: {slot_id!r}")
                slot_ids.add(slot_id)
                slot_max_parallel[slot_id] = slot.get("max_parallel")
                agent_name = slot.get("agent")
                if agent_name is not None and (
                    not isinstance(agent_name, str) or not agent_name.strip()
                ):
                    errors.append(
                        f"execution_profile.subagent_slots[{slot_id}].agent "
                        "must be null or a non-empty string"
                    )
                for key in ("context_length", "max_parallel"):
                    value = slot.get(key)
                    if value is not None and (
                        not isinstance(value, int) or isinstance(value, bool) or value <= 0
                    ):
                        errors.append(
                            f"execution_profile.subagent_slots[{slot_id}].{key} must be null or positive integer"
                        )
                if slot.get("agent") and (
                    slot.get("context_length") is None
                    or slot.get("max_parallel") is None
                ):
                    errors.append(
                        f"execution_profile.subagent_slots[{slot_id}] with an agent must set context_length and max_parallel"
                    )
        main_len = execution_profile.get("main_context_length")
        if main_len is not None and (
            not isinstance(main_len, int) or isinstance(main_len, bool) or main_len <= 0
        ):
            errors.append(
                "execution_profile.main_context_length must be null or positive integer"
            )
        ratio = execution_profile.get("task_budget_ratio")
        if (
            not isinstance(ratio, (int, float))
            or isinstance(ratio, bool)
            or not (0.1 <= float(ratio) <= 0.9)
        ):
            errors.append(
                "execution_profile.task_budget_ratio must be between 0.1 and 0.9"
            )
        checkpoint_policy = execution_profile.get("checkpoint_policy")
        if not isinstance(checkpoint_policy, str) or not checkpoint_policy:
            errors.append("execution_profile.checkpoint_policy must be a non-empty string")

    tasks = plan.get("tasks", [])
    if not isinstance(tasks, list):
        errors.append("`tasks` must be a list")
        return errors

    seen_ids: set[str] = set()
    declared_outputs: list[tuple[str, str, tuple[str, ...]]] = []
    validated_dependencies: list[tuple[str, list[str]]] = []
    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"tasks[{i}] is not an object")
            continue
        missing_t = REQUIRED_TASK_KEYS - set(task)
        if missing_t:
            errors.append(f"tasks[{i}] missing keys: {sorted(missing_t)}")
            continue
        tid = task["id"]
        if not isinstance(tid, str) or not tid:
            errors.append(f"tasks[{i}].id must be a non-empty string")
            continue
        if tid in seen_ids:
            errors.append(f"duplicate task id: {tid!r}")
            continue
        seen_ids.add(tid)
        description = task.get("description")
        if not isinstance(description, str) or not description:
            errors.append(f"tasks[{tid}].description must be a non-empty string")
        status = task.get("status")
        if not isinstance(status, str) or status not in VALID_STATUS:
            errors.append(
                f"tasks[{tid}].status={status!r} not in {sorted(VALID_STATUS)}"
            )
        phase = task.get("phase")
        schema_ver = _schema_version(plan)
        if schema_ver == "2.0":
            # Schema 2.0 requires explicit phase; no inference.
            if phase is None or phase == "":
                errors.append(f"tasks[{tid}].phase is required for schema 2.0")
            elif not isinstance(phase, str) or phase not in VALID_PHASE:
                errors.append(
                    f"tasks[{tid}].phase={phase!r} not in {sorted(VALID_PHASE)}"
                )
        else:
            if phase is None:
                phase = _infer_phase(task)
                task["phase"] = phase
            if not isinstance(phase, str) or phase not in VALID_PHASE:
                errors.append(
                    f"tasks[{tid}].phase={phase!r} not in {sorted(VALID_PHASE)}"
                )
        depends_on = task.get("depends_on")
        if not isinstance(depends_on, list):
            errors.append(f"tasks[{tid}].depends_on must be a list")
        else:
            valid_dependencies: list[str] = []
            seen_dependencies: set[str] = set()
            for dep_index, dep in enumerate(depends_on):
                if not isinstance(dep, str) or not dep:
                    errors.append(
                        f"tasks[{tid}].depends_on[{dep_index}] must be a non-empty string"
                    )
                    continue
                if dep in seen_dependencies:
                    errors.append(f"tasks[{tid}].depends_on contains duplicate {dep!r}")
                    continue
                seen_dependencies.add(dep)
                valid_dependencies.append(dep)
            validated_dependencies.append((tid, valid_dependencies))
        if not isinstance(task["outputs"], list) or not task["outputs"]:
            errors.append(f"tasks[{tid}].outputs must be a non-empty list of paths")
        else:
            for op in task["outputs"]:
                canonical, detail = _portable_relative_path(op)
                if canonical is None:
                    errors.append(
                        f"tasks[{tid}].outputs contains unsafe portable path "
                        f"{op!r}: {detail}"
                    )
                elif not canonical.startswith("research-output/"):
                    errors.append(
                        f"tasks[{tid}].outputs must live under research-output/: {op!r}"
                    )
                else:
                    key = _portable_path_key(op)
                    if key is None:  # Defensive; canonical validation already passed.
                        errors.append(
                            f"tasks[{tid}].outputs contains unsafe portable path {op!r}"
                        )
                        continue
                    for previous_task, previous_path, previous_key in declared_outputs:
                        if _portable_paths_overlap(key, previous_key):
                            errors.append(
                                f"tasks[{tid}].outputs path {op!r} overlaps output tree "
                                f"{previous_path!r} owned by task {previous_task!r}; "
                                "output ownership is case-insensitive and includes "
                                "ancestor/descendant paths"
                            )
                    declared_outputs.append((tid, op, key))
        inputs = task.get("inputs", [])
        if not isinstance(inputs, list):
            errors.append(f"tasks[{tid}].inputs must be a list when present")
        else:
            for ip in inputs:
                canonical, detail = _portable_relative_path(ip)
                if canonical is None:
                    errors.append(
                        f"tasks[{tid}].inputs contains unsafe portable path "
                        f"{ip!r}: {detail}"
                    )
        if not isinstance(task["parallel_safe"], bool):
            errors.append(f"tasks[{tid}].parallel_safe must be a boolean")
        execution = task.get("execution")
        if not isinstance(execution, dict):
            errors.append(f"tasks[{tid}].execution must be an object")
        else:
            missing_e = REQUIRED_EXECUTION_KEYS - set(execution)
            if missing_e:
                errors.append(
                    f"tasks[{tid}].execution missing keys: {sorted(missing_e)}"
                )
            agent = execution.get("agent")
            if not isinstance(agent, str) or agent not in {"main", "subagent"}:
                errors.append(
                    f"tasks[{tid}].execution.agent must be 'main' or 'subagent'"
                )
            subagent_slot = execution.get("subagent_slot")
            if agent == "subagent":
                if not isinstance(subagent_slot, str) or subagent_slot not in slot_ids:
                    errors.append(
                        f"tasks[{tid}].execution.subagent_slot must reference a configured slot"
                    )
                elif isinstance(execution.get("max_parallel_threads"), int):
                    slot_max = slot_max_parallel.get(subagent_slot)
                    if (
                        isinstance(slot_max, int)
                        and execution["max_parallel_threads"] > slot_max
                    ):
                        errors.append(
                            f"tasks[{tid}].execution.max_parallel_threads must be <= slot max_parallel"
                        )
            elif subagent_slot is not None:
                errors.append(
                    f"tasks[{tid}].execution.subagent_slot must be null for main agent tasks"
                )
            for key in ("parallel_threads", "max_parallel_threads"):
                value = execution.get(key)
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    errors.append(
                        f"tasks[{tid}].execution.{key} must be a non-negative integer"
                    )
            parallel_threads = execution.get("parallel_threads")
            max_parallel_threads = execution.get("max_parallel_threads")
            if (
                isinstance(parallel_threads, int)
                and isinstance(max_parallel_threads, int)
                and parallel_threads > max_parallel_threads
            ):
                errors.append(
                    f"tasks[{tid}].execution.parallel_threads must be <= max_parallel_threads"
                )
            if (
                agent == "subagent"
                and isinstance(parallel_threads, int)
                and parallel_threads < 1
            ):
                errors.append(
                    f"tasks[{tid}].execution.parallel_threads must be >= 1 for subagent tasks"
                )
            if (
                agent == "main"
                and isinstance(parallel_threads, int)
                and parallel_threads != 0
            ):
                errors.append(
                    f"tasks[{tid}].execution.parallel_threads must be 0 for main agent tasks"
                )
            for key in ("context_length", "context_budget"):
                value = execution.get(key)
                if value is not None and (
                    not isinstance(value, int) or isinstance(value, bool) or value <= 0
                ):
                    errors.append(
                        f"tasks[{tid}].execution.{key} must be null or positive integer"
                    )
            if not isinstance(
                execution.get("checkpoint_policy"), str
            ) or not execution.get("checkpoint_policy"):
                errors.append(
                    f"tasks[{tid}].execution.checkpoint_policy must be a non-empty string"
                )
        owner = task["owner"]
        if not isinstance(owner, str) or not (
            owner == "main" or owner.startswith("sub-")
        ):
            errors.append(f"tasks[{tid}].owner={owner!r} must be 'main' or 'sub-<n>'")
        blocker_reason = task.get("blocker_reason", "")
        if not isinstance(blocker_reason, str):
            errors.append(f"tasks[{tid}].blocker_reason must be a string when present")

    # Dependency closure.
    for task_id, dependencies in validated_dependencies:
        for dep in dependencies:
            if dep not in seen_ids:
                errors.append(
                    f"tasks[{task_id}].depends_on references unknown id {dep!r}"
                )

    # Standard gate invariants cannot be removed or emptied.
    errors.extend(_validate_standard_gates(plan))

    return errors


def _validate_standard_gates(plan: dict[str, Any]) -> list[str]:
    """Ensure canonical gates keep required assertions (users may only add)."""
    errors: list[str] = []
    gates = plan.get("gates")
    if not isinstance(gates, dict):
        errors.append("`gates` must be an object")
        return errors
    canonical = _load_canonical_gates()
    # execute_ready and dispatch_ready are aliases of the same readiness class
    has_dispatch_class = "execute_ready" in gates or "dispatch_ready" in gates
    for gname, required in canonical.items():
        if gname == "dispatch_ready" and "dispatch_ready" not in gates:
            if "execute_ready" in gates:
                # execute_ready stands in for dispatch_ready
                gname_check = "execute_ready"
            else:
                errors.append(
                    "missing standard gate execute_ready/dispatch_ready"
                )
                continue
        elif gname == "execute_ready" and "execute_ready" not in gates:
            if "dispatch_ready" in gates:
                gname_check = "dispatch_ready"
            else:
                errors.append("missing standard gate execute_ready/dispatch_ready")
                continue
        else:
            gname_check = gname
            if gname_check not in gates:
                # require core gates when any tasks present or plan claims schema 2
                if plan.get("tasks") or _schema_version(plan) == "2.0":
                    if gname in {"plan_ready", "synthesize_ready", "release_ready"} or (
                        gname in {"execute_ready", "dispatch_ready"}
                        and not has_dispatch_class
                    ):
                        errors.append(f"missing standard gate {gname}")
                continue
        gate = gates.get(gname_check)
        if not isinstance(gate, dict):
            errors.append(f"gates.{gname_check} must be an object")
            continue
        assertions = gate.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            errors.append(
                f"gates.{gname_check}.assertions must be a non-empty list "
                f"(canonical safety/release invariants cannot be removed)"
            )
            continue
        valid_assertions: list[str] = []
        for assertion_index, assertion in enumerate(assertions):
            if not isinstance(assertion, str) or not assertion:
                errors.append(
                    f"gates.{gname_check}.assertions[{assertion_index}] "
                    "must be a non-empty string"
                )
                continue
            valid_assertions.append(assertion)
        present = set(valid_assertions)
        if len(valid_assertions) != len(present):
            errors.append(f"gates.{gname_check}.assertions must not contain duplicates")
        missing = [a for a in required if a not in present]
        if missing:
            errors.append(
                f"gates.{gname_check} missing required assertions: {missing}"
            )
        # Reject unknown assertion names on standard gates (nested gate names OK).
        for a in valid_assertions:
            if a in required:
                continue
            if a in gates:  # nested gate reference
                continue
            if a in ASSERTIONS:
                # documented extension assertion
                continue
            errors.append(
                f"gates.{gname_check} has unknown assertion {a!r}"
            )
        for a in valid_assertions:
            if a not in ASSERTIONS and a not in gates:
                # nested gate names allowed; unknown atomic assertions fail
                if a not in present:  # unreachable
                    pass
                # allow nested gate refs; unknown non-gate assertion names fail at run
                if a not in gates and a not in ASSERTIONS and a not in required:
                    # still allow custom assertion names only if registered later
                    # enforce unknown only when not a gate nest
                    pass
    return errors


def detect_cycles(plan: dict[str, Any]) -> list[list[str]]:
    """Return a list of dependency cycles. Empty list = acyclic."""
    raw_tasks = plan.get("tasks", [])
    if not isinstance(raw_tasks, list):
        return []
    tasks: dict[str, dict[str, Any]] = {}
    for task in raw_tasks:
        if not isinstance(task, dict):
            continue
        task_id = task.get("id")
        dependencies = task.get("depends_on")
        if not isinstance(task_id, str) or not task_id:
            continue
        if not isinstance(dependencies, list) or not all(
            isinstance(dep, str) and dep for dep in dependencies
        ):
            continue
        tasks[task_id] = task
    cycles: list[list[str]] = []
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in tasks}
    stack: list[str] = []

    def visit(tid: str) -> None:
        color[tid] = GRAY
        stack.append(tid)
        for dep in tasks[tid].get("depends_on", []):
            if color.get(dep) == GRAY:
                # Found a back-edge — extract the cycle from the stack.
                if dep in stack:
                    idx = stack.index(dep)
                    cycles.append(stack[idx:] + [dep])
            elif color.get(dep) == WHITE:
                visit(dep)
        color[tid] = BLACK
        stack.pop()

    for tid in tasks:
        if color[tid] == WHITE:
            visit(tid)
    return cycles


# ---------------------------------------------------------------------------
# Parallelizable computation
# ---------------------------------------------------------------------------


def parallelizable_tasks(plan: dict[str, Any]) -> list[str]:
    """Return the task ids that are ready to dispatch right now.

    A task is ready when:
      * its status is `todo`
      * every dep is in TERMINAL_STATUS=done (NOT blocked — blocked
        dep makes this task un-runnable)
      * `parallel_safe` is true
      * no output path overlaps with another currently-running task
    """
    raw_tasks = plan.get("tasks", [])
    if not isinstance(raw_tasks, list):
        return []
    tasks: dict[str, dict[str, Any]] = {}
    for task in raw_tasks:
        if not isinstance(task, dict):
            continue
        task_id = task.get("id")
        if isinstance(task_id, str) and task_id:
            tasks[task_id] = task
    done_ids = {tid for tid, t in tasks.items() if t.get("status") == "done"}
    running_output_keys: list[tuple[str, ...]] = []
    running_slot_threads: dict[str, int] = {}
    for t in tasks.values():
        if t.get("status") == "running":
            output_keys = _portable_output_keys(t.get("outputs"))
            if output_keys is None:
                return []
            if any(
                _portable_paths_overlap(key, running_key)
                for key in output_keys
                for running_key in running_output_keys
            ):
                return []
            running_output_keys.extend(output_keys)
            execution = (
                t.get("execution") if isinstance(t.get("execution"), dict) else {}
            )
            if execution.get("agent") == "subagent" and execution.get("subagent_slot"):
                slot = str(execution.get("subagent_slot"))
                running_slot_threads[slot] = running_slot_threads.get(
                    slot, 0
                ) + (_positive_int_or_none(execution.get("parallel_threads")) or 1)

    ready: list[str] = []
    reserved_output_keys: list[tuple[str, ...]] = []
    reserved_slot_threads: dict[str, int] = {}
    for tid, t in tasks.items():
        if t.get("status") != "todo":
            continue
        if not t.get("parallel_safe", False):
            continue
        dependencies = t.get("depends_on")
        if not isinstance(dependencies, list) or not all(
            isinstance(dep, str) and dep in done_ids for dep in dependencies
        ):
            continue
        output_keys = _portable_output_keys(t.get("outputs"))
        if output_keys is None:
            continue
        if any(
            _portable_paths_overlap(key, unavailable_key)
            for key in output_keys
            for unavailable_key in running_output_keys + reserved_output_keys
        ):
            continue
        execution = t.get("execution") if isinstance(t.get("execution"), dict) else {}
        if execution.get("agent") == "subagent" and execution.get("subagent_slot"):
            slot = str(execution.get("subagent_slot"))
            max_threads = _positive_int_or_none(
                execution.get("max_parallel_threads")
            ) or 1
            need_threads = _positive_int_or_none(execution.get("parallel_threads")) or 1
            used = running_slot_threads.get(slot, 0) + reserved_slot_threads.get(
                slot, 0
            )
            if used + need_threads > max_threads:
                continue
            reserved_slot_threads[slot] = (
                reserved_slot_threads.get(slot, 0) + need_threads
            )
        ready.append(tid)
        reserved_output_keys.extend(output_keys)
    return ready


# ---------------------------------------------------------------------------
# Status formatting
# ---------------------------------------------------------------------------


def format_status(plan: dict[str, Any]) -> str:
    rows: list[str] = []
    rows.append(f"plan_id={plan.get('plan_id')}  title={plan.get('title')!r}")
    rows.append("id      status      par   owner     outputs")
    rows.append("------  ----------  ----  --------  -------")
    for t in plan.get("tasks", []):
        rows.append(
            "{id:6s}  {status:10s}  {par:4s}  {owner:8s}  {outputs}".format(
                id=t["id"][:6],
                status=t["status"],
                par="yes" if t.get("parallel_safe") else "no",
                owner=str(t.get("owner", ""))[:8],
                outputs=", ".join(t.get("outputs", [])),
            )
        )
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Gate evaluation
# ---------------------------------------------------------------------------


def _all_outputs_exist(
    plan: dict[str, Any],
    plan_path: Path,
    phase: str | None = None,
) -> tuple[bool, list[str]]:
    base = _plan_dir(plan_path)
    missing: list[str] = []
    tasks = plan.get("tasks", [])
    if phase is not None:
        tasks = _tasks_by_phase(plan, phase)
    for t in tasks:
        # A blocked research task is handled by blocked_research_justified.
        # Synthesis outputs are release artefacts and may never be skipped.
        if t["status"] == "blocked" and phase != "synthesis":
            continue
        for p in t.get("outputs", []):
            target, detail = _resolve_workspace_path(base, p)
            if target is None:
                missing.append(f"{p} ({detail})")
            elif not target.exists():
                missing.append(p)
            elif target.is_file():
                try:
                    if target.stat().st_size == 0:
                        missing.append(f"{p} (empty file)")
                except OSError as exc:
                    missing.append(f"{p} (cannot inspect: {exc})")
            elif target.is_dir():
                has_artifact = False
                try:
                    for child in target.rglob("*"):
                        if not child.is_file():
                            continue
                        resolved = child.resolve()
                        try:
                            resolved.relative_to(base.resolve())
                        except ValueError:
                            continue
                        if resolved.stat().st_size > 0:
                            has_artifact = True
                            break
                except OSError:
                    has_artifact = False
                if not has_artifact:
                    missing.append(
                        f"{p} (directory contains no non-empty artifact file)"
                    )
            else:
                missing.append(f"{p} (not a regular file or directory)")
    return (not missing), missing


def _ledger_exists_and_validates(plan_path: Path) -> tuple[bool, str]:
    """Call scripts/evidence_ledger.py validate; fail if ledger missing/invalid."""
    base = _plan_dir(plan_path)
    ledger = base / "evidence-ledger.csv"
    if not ledger.exists():
        return False, f"evidence ledger not found at {ledger}"
    script = Path(__file__).resolve().parent / "evidence_ledger.py"
    if not script.exists():
        return False, "ledger validator script not found"
    import subprocess

    res = subprocess.run(
        [sys.executable, str(script), "validate", "--file", str(ledger)],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        return False, res.stderr.strip() or res.stdout.strip() or "ledger validate failed"
    return True, "validator OK"


def _ledger_hmac_verified(plan_path: Path) -> tuple[bool, str]:
    """Require a real HMAC verify via D_RESEARCH_LEDGER_KEY (no sidecar-only pass)."""
    base = _plan_dir(plan_path)
    ledger = base / "evidence-ledger.csv"
    sig = base / "evidence-ledger.csv.hmac"
    if not ledger.exists():
        return False, f"evidence ledger not found at {ledger}"
    if not sig.exists():
        return False, f"signature not found at {sig}"
    key = os.environ.get("D_RESEARCH_LEDGER_KEY", "").strip()
    if not key:
        return False, "D_RESEARCH_LEDGER_KEY is unset or empty; cannot verify HMAC"
    script = Path(__file__).resolve().parent / "evidence_ledger.py"
    if not script.exists():
        return False, "ledger verifier script not found"
    import subprocess

    res = subprocess.run(
        [
            sys.executable,
            str(script),
            "verify",
            "--file",
            str(ledger),
            "--key-env",
            "D_RESEARCH_LEDGER_KEY",
            "--sig",
            str(sig),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        return False, res.stderr.strip() or res.stdout.strip() or "HMAC verify failed"
    return True, "HMAC verified"


def _ledger_signed(plan_path: Path) -> tuple[bool, str]:
    """Deprecated alias used by older plan gate lists; prefer ledger_hmac_verified."""
    return _ledger_hmac_verified(plan_path)


def _canonical_checklist_ids() -> tuple[list[str] | None, str]:
    """Load the shipped, versioned checklist contract fail-closed."""

    try:
        text = CHECKLIST_TEMPLATE_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"cannot read canonical checklist template: {exc}"
    versions = _CHECKLIST_VERSION_RE.findall(text)
    if versions != [CHECKLIST_CONTRACT_VERSION]:
        return None, (
            "canonical checklist must declare exactly "
            f"d-research-checklist:{CHECKLIST_CONTRACT_VERSION}"
        )
    item_ids: list[str] = []
    malformed = 0
    for line in text.splitlines():
        if not _CHECKBOX_LINE_RE.fullmatch(line):
            continue
        match = _CHECKLIST_ITEM_RE.fullmatch(line)
        if match is None:
            malformed += 1
        else:
            item_ids.append(match.group("id"))
    if malformed:
        return None, f"canonical checklist has {malformed} item(s) without an ID"
    if not item_ids:
        return None, "canonical checklist has no contract items"
    duplicates = sorted(
        item_id for item_id in set(item_ids) if item_ids.count(item_id) > 1
    )
    if duplicates:
        return None, f"canonical checklist has duplicate IDs: {duplicates}"
    return item_ids, "OK"


def _reproducibility_checklist_complete(plan_path: Path) -> tuple[bool, str]:
    """Require every canonical versioned checklist ID exactly once and complete.

    Non-applicable items must be marked ``[x] ... N/A - reason``. Arbitrary
    checked boxes, missing IDs, duplicate IDs, and unknown IDs fail closed.
    """
    base = _plan_dir(plan_path)
    candidates = [
        base / "reproducibility-checklist.md",
        base / "research-output" / "reproducibility-checklist.md",
    ]
    path = next((c for c in candidates if c.exists()), None)
    if path is None:
        return False, "reproducibility-checklist.md not found"
    canonical_ids, contract_detail = _canonical_checklist_ids()
    if canonical_ids is None:
        return False, contract_detail
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"cannot read reproducibility checklist: {exc}"
    versions = _CHECKLIST_VERSION_RE.findall(text)
    if versions != [CHECKLIST_CONTRACT_VERSION]:
        return False, (
            "checklist must declare exactly "
            f"d-research-checklist:{CHECKLIST_CONTRACT_VERSION}"
        )

    parsed: list[re.Match[str]] = []
    malformed = 0
    for line in text.splitlines():
        if not _CHECKBOX_LINE_RE.fullmatch(line):
            continue
        match = _CHECKLIST_ITEM_RE.fullmatch(line)
        if match is None:
            malformed += 1
        else:
            parsed.append(match)
    if malformed:
        return False, f"{malformed} checklist item(s) have no canonical ID"

    observed_ids = [match.group("id") for match in parsed]
    duplicate_ids = sorted(
        item_id for item_id in set(observed_ids) if observed_ids.count(item_id) > 1
    )
    if duplicate_ids:
        return False, f"duplicate checklist IDs: {duplicate_ids}"
    expected = set(canonical_ids)
    observed = set(observed_ids)
    missing = sorted(expected - observed)
    unknown = sorted(observed - expected)
    if missing or unknown:
        return False, f"checklist ID mismatch; missing={missing}, unknown={unknown}"

    unchecked = [
        match.group("id")
        for match in parsed
        if match.group("state").lower() != "x"
    ]
    if unchecked:
        return False, (
            f"{len(unchecked)} unchecked checklist item(s): {unchecked}; "
            "mark done or N/A with a reason"
        )
    invalid_na = [
        match.group("id")
        for match in parsed
        if re.search(r"\bN/?A\b", match.group("label"), flags=re.IGNORECASE)
        and not re.search(
            r"\bN/?A\b\s*(?:\u2014|\u2013|-|:)\s*\S+",
            match.group("label"),
            flags=re.IGNORECASE,
        )
    ]
    if invalid_na:
        return False, f"N/A checklist item(s) missing a reason: {invalid_na}"
    return True, (
        f"checklist {CHECKLIST_CONTRACT_VERSION} complete at {path} "
        f"({len(canonical_ids)} canonical items)"
    )


def _reproducibility_checklist_exists(plan_path: Path) -> tuple[bool, str]:
    """Legacy assertion name; now requires complete checklist."""
    return _reproducibility_checklist_complete(plan_path)


def _workspace_layout_valid(plan: dict[str, Any], plan_path: Path) -> tuple[bool, str]:
    base = _plan_dir(plan_path)
    errors: list[str] = []
    for rel in STANDARD_WORKSPACE_DIRS:
        if not (base / rel).is_dir():
            errors.append(f"missing directory: {rel}")
    for rel in ["evidence-ledger.csv", str(plan.get("plan_render_path", "PLAN.md"))]:
        target, detail = _resolve_workspace_path(base, rel)
        if target is None:
            errors.append(detail)
        elif rel == "evidence-ledger.csv" and not target.exists():
            errors.append("missing file: evidence-ledger.csv")
    for task in plan.get("tasks", []):
        for field in ("inputs", "outputs"):
            for rel in task.get(field, []):
                _target, detail = _resolve_workspace_path(base, rel)
                if _target is None:
                    errors.append(f"tasks[{task.get('id')}].{field}: {detail}")
                elif field == "outputs":
                    canonical, _portable_detail = _portable_relative_path(rel)
                    if canonical is None or not canonical.startswith(
                        "research-output/"
                    ):
                        errors.append(
                            f"tasks[{task.get('id')}].outputs must live under "
                            f"research-output/: {rel!r}"
                        )
    return (not errors), "; ".join(errors) if errors else "OK"


def _plan_rendered_exists(plan: dict[str, Any], plan_path: Path) -> tuple[bool, str]:
    base = _plan_dir(plan_path)
    rel = str(plan.get("plan_render_path", "PLAN.md"))
    target, detail = _resolve_workspace_path(base, rel)
    if target is None:
        return False, detail
    if not target.exists():
        return False, f"rendered plan not found at {target}"
    expected = render_plan_markdown(plan, plan_path).replace("\r\n", "\n")
    actual = target.read_text(encoding="utf-8").replace("\r\n", "\n")
    if actual != expected:
        return False, f"rendered plan is stale; re-run render for {target}"
    return True, f"rendered plan is current at {target}"


def _approval_contract_payload(plan: dict[str, Any]) -> dict[str, Any]:
    """Return immutable plan semantics covered by an approval digest.

    Execution progress is deliberately excluded so normal status/blocker updates
    do not invalidate later synthesis gates. The rendered plan still displays
    those mutable fields, so changing them before dispatch makes PLAN.md stale.
    """

    payload: dict[str, Any] = {}
    for key, value in plan.items():
        if key in {
            "approval",
            "notes",
            "stopping_criteria_satisfied",
            "_compat_warned",
        }:
            continue
        if key == "tasks" and isinstance(value, list):
            payload[key] = [
                {
                    task_key: task_value
                    for task_key, task_value in task.items()
                    if task_key not in {"status", "blocker_reason"}
                }
                if isinstance(task, dict)
                else task
                for task in value
            ]
        else:
            payload[key] = value
    return payload


def _plan_approval_sha256(plan: dict[str, Any]) -> str:
    """Return a deterministic, domain-separated digest for plan approval."""

    canonical = json.dumps(
        _approval_contract_payload(plan),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    digest = hashlib.sha256(b"d-research-plan-approval-v1\n" + canonical).hexdigest()
    return f"sha256:{digest}"


def _find_final_report(plan: dict[str, Any], plan_path: Path) -> Path | None:
    """Exact declared synthesis report only — no stale undeclared substitution."""
    base = _plan_dir(plan_path)
    declared: list[Path] = []
    for t in _tasks_by_phase(plan, "synthesis"):
        for op in t.get("outputs", []):
            op_norm = str(op).replace("\\", "/").lower()
            if op_norm.endswith("report.md") or op_norm.endswith("final-report.md"):
                target, _ = _resolve_workspace_path(base, op)
                if target is not None:
                    declared.append(target)
    if declared:
        for target in declared:
            if target.is_file() and target.stat().st_size > 0:
                return target
        return None
    # Only when no synthesis tasks exist (non-release workspaces).
    if not _tasks_by_phase(plan, "synthesis"):
        canonical = base / "research-output" / "report.md"
        if canonical.is_file() and canonical.stat().st_size > 0:
            return canonical
        # Compatibility through v3: old workspaces without a declared report
        # wrote report.md at the workspace root.
        if _schema_version(plan) != "2.0":
            legacy = base / "report.md"
            if legacy.is_file() and legacy.stat().st_size > 0:
                return legacy
    return None


def _final_report_exists(plan_path: Path) -> tuple[bool, str]:
    # Legacy wrapper without plan object — presence only.
    base = _plan_dir(plan_path)
    candidates = [
        base / "research-output" / "report.md",
        base / "final-report.md",
        base / "report.md",
    ]
    for c in candidates:
        if c.exists() and c.stat().st_size > 0:
            return True, f"report at {c}"
    return False, "final report not found"


def _final_report_valid(plan: dict[str, Any], plan_path: Path) -> tuple[bool, str]:
    report = _find_final_report(plan, plan_path)
    if report is None:
        return False, "final report not found or empty"
    text = report.read_text(encoding="utf-8")
    if not text.strip():
        return False, f"report is empty: {report}"
    lower = text.lower()
    for pat in PLACEHOLDER_PATTERNS:
        if pat.lower() in lower:
            return False, f"report still contains placeholder: {pat!r}"
    import re as _re

    if _re.search(r"\bTODO:\b|\[placeholder\]|<!--\s*todo\b", text, flags=_re.I):
        return False, "report still contains TODO/placeholder marker"
    return True, f"report valid at {report}"


def _rendered_citations_exist(plan_path: Path) -> tuple[bool, str]:
    """Require declared synthesis citation outputs only (no undeclared stale files)."""
    # Prefer plan-aware path when available via nested gate; plan_path alone is used here.
    # Load plan if present next to plan_path.
    plan_file = plan_path if plan_path.name.endswith(".json") else plan_path / "research-plan.json"
    if not plan_file.is_file() and plan_path.is_file():
        plan_file = plan_path
    base = _plan_dir(plan_path) if plan_path.is_file() else plan_path
    declared: list[Path] = []
    if plan_file.is_file():
        try:
            plan = load(plan_file)
        except Exception:
            plan = {}
        for t in _tasks_by_phase(plan, "synthesis"):
            for op in t.get("outputs") or []:
                op_norm = str(op).replace("\\", "/").lower()
                if any(
                    m in op_norm
                    for m in (
                        "report-citations",
                        "citations.md",
                        "bibliography",
                        "references.md",
                        "references.bib",
                        "references.ris",
                    )
                ):
                    target, _ = _resolve_workspace_path(base, op)
                    if target is not None:
                        declared.append(target)
    if declared:
        errors: list[str] = []
        for c in declared:
            if not c.is_file() or c.stat().st_size == 0:
                errors.append(f"missing/empty: {c}")
                continue
            try:
                text = c.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                errors.append(f"unreadable: {c} ({exc})")
                continue
            if not text.strip():
                errors.append(f"whitespace-only: {c}")
                continue
            lower = text.lower()
            placeholder = next(
                (pat for pat in PLACEHOLDER_PATTERNS if pat.lower() in lower),
                None,
            )
            if placeholder is not None:
                errors.append(f"placeholder {placeholder!r}: {c}")
                continue
            suffix = c.suffix.lower()
            if suffix == ".bib" and not re.search(
                r"(?m)^\s*@\w+\s*[({]", text
            ):
                errors.append(f"invalid BibTeX (no entry): {c}")
            elif suffix == ".ris" and not (
                re.search(r"(?m)^TY\s{2}-\s*\S+", text)
                and re.search(r"(?m)^ER\s{2}-\s*$", text)
            ):
                errors.append(f"invalid RIS (missing TY/ER): {c}")
        if errors:
            return False, "; ".join(errors)
        return True, f"{len(declared)} declared citation output(s) valid"
    # No declared citation output: do not accept undeclared stale citations.md
    return False, "no declared synthesis citation/bibliography outputs"


def _claim_coverage_complete(plan: dict[str, Any], plan_path: Path) -> tuple[bool, str]:
    """Require report_render lint on the exact declared final report only."""
    base = _plan_dir(plan_path)
    report = _find_final_report(plan, plan_path)
    if report is None:
        return False, "no report for claim coverage"
    script = Path(__file__).resolve().parent / "report_render.py"
    if not script.exists():
        return False, "report_render.py not found"
    import subprocess

    res = subprocess.run(
        [
            sys.executable,
            str(script),
            "lint",
            "--workspace",
            str(base),
            "--report",
            str(report),
            "--strict",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        detail = res.stderr.strip() or res.stdout.strip() or "claim coverage failed"
        return False, detail
    return True, f"claim coverage 100% on {report}"


# Each assertion maps to a callable(plan, plan_path) -> (ok: bool, detail: str).
def _assert_schema_valid(plan, plan_path):
    errors = validate_schema(plan)
    return (not errors), "; ".join(errors) if errors else "OK"


def _assert_no_cycles(plan, plan_path):
    cyc = detect_cycles(plan)
    return (not cyc), ("cycles: " + str(cyc)) if cyc else "OK"


def _assert_no_orphans(plan, plan_path):
    # validate_schema already catches missing deps; reuse it here so the
    # explicit assertion is independently meaningful.
    errors = [e for e in validate_schema(plan) if "depends_on references unknown" in e]
    return (not errors), "; ".join(errors) if errors else "OK"


def _assert_no_task_is_done(plan, plan_path):
    done = [t["id"] for t in plan.get("tasks", []) if t["status"] == "done"]
    return (not done), ("already-done tasks: " + str(done)) if done else "OK"


def _assert_execution_configured(plan, plan_path):
    errors = [
        e
        for e in validate_schema(plan)
        if "execution_profile" in e or ".execution" in e or "subagent slot" in e
    ]
    return (not errors), "; ".join(errors) if errors else "OK"


def _assert_workspace_layout(plan, plan_path):
    return _workspace_layout_valid(plan, plan_path)


def _assert_plan_rendered(plan, plan_path):
    return _plan_rendered_exists(plan, plan_path)


def _assert_plan_approved(plan, plan_path):
    approval_obj = plan.get("approval")
    approval: dict[str, Any] = approval_obj if isinstance(approval_obj, dict) else {}
    approved_by = str(approval.get("approved_by", "")).strip()
    approved_at = str(approval.get("approved_at", "")).strip()
    if not approved_by:
        return False, "approval.approved_by is empty; run approve --by <name>"
    if not approved_at:
        return False, "approval.approved_at is empty"
    try:
        _parse_iso_utc(approved_at)
    except ValueError:
        return False, "approval.approved_at must be ISO 8601 UTC"
    approved_digest = approval.get(APPROVAL_DIGEST_KEY)
    if not isinstance(approved_digest, str) or not _SHA256_VALUE_RE.fullmatch(
        approved_digest
    ):
        return False, "approval.plan_sha256 is missing or malformed; re-approve the plan"
    try:
        current_digest = _plan_approval_sha256(plan)
    except (TypeError, ValueError) as exc:
        return False, f"approved plan cannot be canonicalized: {exc}"
    if approved_digest != current_digest:
        return (
            False,
            "approval.plan_sha256 does not match the current immutable plan; "
            "revoke, render, and re-approve",
        )
    return True, f"approved by {approved_by} at {approved_at}; digest {approved_digest}"


def _assert_all_tasks_terminal(plan, plan_path):
    non_terminal = [
        t["id"] for t in plan.get("tasks", []) if t["status"] not in TERMINAL_STATUS
    ]
    return (not non_terminal), (
        "non-terminal tasks: " + str(non_terminal)
    ) if non_terminal else "OK"


def _assert_research_tasks_terminal(plan, plan_path):
    non_terminal = [
        t["id"]
        for t in _tasks_by_phase(plan, "research")
        if t["status"] not in TERMINAL_STATUS
    ]
    return (not non_terminal), (
        "non-terminal research tasks: " + str(non_terminal)
    ) if non_terminal else "OK"


def _assert_synthesis_tasks_terminal(plan, plan_path):
    incomplete = [
        t["id"]
        for t in _tasks_by_phase(plan, "synthesis")
        if t["status"] != "done"
    ]
    return (not incomplete), (
        "synthesis tasks not completed: " + str(incomplete)
    ) if incomplete else "OK"


def _assert_all_outputs_exist(plan, plan_path):
    ok, missing = _all_outputs_exist(plan, plan_path)
    return ok, "OK" if ok else f"missing outputs: {missing}"


def _assert_research_outputs_exist(plan, plan_path):
    ok, missing = _all_outputs_exist(plan, plan_path, phase="research")
    return ok, "OK" if ok else f"missing research outputs: {missing}"


def _assert_synthesis_outputs_exist(plan, plan_path):
    ok, missing = _all_outputs_exist(plan, plan_path, phase="synthesis")
    return ok, "OK" if ok else f"missing synthesis outputs: {missing}"


def _assert_ledger_validates(plan, plan_path):
    return _ledger_exists_and_validates(plan_path)


def _assert_ledger_signed(plan, plan_path):
    return _ledger_signed(plan_path)


def _assert_ledger_hmac_verified(plan, plan_path):
    return _ledger_hmac_verified(plan_path)


def _assert_repro_checklist_exists(plan, plan_path):
    return _reproducibility_checklist_exists(plan_path)


def _assert_repro_checklist_complete(plan, plan_path):
    return _reproducibility_checklist_complete(plan_path)


def _assert_final_report_exists(plan, plan_path):
    return _final_report_exists(plan_path)


def _assert_final_report_valid(plan, plan_path):
    return _final_report_valid(plan, plan_path)


def _assert_claim_coverage_complete(plan, plan_path):
    return _claim_coverage_complete(plan, plan_path)


def _assert_rendered_citations_exist(plan, plan_path):
    return _rendered_citations_exist(plan_path)


def _assert_stopping_criteria_satisfied(plan, plan_path):
    val = plan.get("stopping_criteria_satisfied") is True
    return val, "OK" if val else "stopping_criteria_satisfied is false"


def _assert_plan_complete(plan, plan_path):
    """Draft plans may be empty; plan_ready requires filled title/scope/tasks/SQs."""
    problems: list[str] = []
    if not str(plan.get("plan_id", "")).strip():
        problems.append("plan_id empty")
    if not str(plan.get("title", "")).strip():
        problems.append("title empty")
    if not str(plan.get("scope", "")).strip():
        problems.append("scope empty")
    if not str(plan.get("stopping_criteria", "")).strip():
        problems.append("stopping_criteria empty")
    sqs = plan.get("sub_questions") or []
    if not sqs:
        problems.append("sub_questions empty")
    tasks = plan.get("tasks") or []
    if not tasks:
        problems.append("tasks empty")
    else:
        research = _tasks_by_phase(plan, "research")
        if not research:
            problems.append("no research-phase tasks")
    return (not problems), "; ".join(problems) if problems else "OK"


def _assert_standard_gates_intact(plan, plan_path):
    errs = _validate_standard_gates(plan)
    return (not errs), "; ".join(errs) if errs else "OK"


def _assert_blocked_research_justified(plan, plan_path):
    """Blocked research tasks need reason + task-bound evidence.

    Accept either:
    - a declared non-empty blocker/output artifact for that task, or
    - a record_type=blocker ledger row whose sub_question equals the task id
      (or claim_id equals the task id).
    A global unrelated blocker row is not sufficient.
    """
    base = _plan_dir(plan_path)
    problems: list[str] = []
    ledger_by_task: set[str] = set()
    ledger = base / "evidence-ledger.csv"
    if ledger.is_file():
        import csv

        with ledger.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if (row.get("record_type") or "").strip().lower() != "blocker":
                    continue
                sq = (row.get("sub_question") or "").strip()
                cid = (row.get("claim_id") or "").strip()
                if sq:
                    ledger_by_task.add(sq)
                if cid:
                    ledger_by_task.add(cid)
    for t in _tasks_by_phase(plan, "research"):
        if t.get("status") != "blocked":
            continue
        tid = str(t.get("id") or "")
        reason = str(t.get("blocker_reason") or "").strip()
        if not reason:
            problems.append(f"{tid}: blocked without blocker_reason")
        has_artifact = False
        for op in t.get("outputs") or []:
            target, _ = _resolve_workspace_path(base, op)
            if target is not None and target.is_file() and target.stat().st_size > 0:
                has_artifact = True
                break
        has_ledger = tid in ledger_by_task
        if not has_artifact and not has_ledger:
            problems.append(
                f"{tid}: blocked task needs non-empty declared artifact "
                "or record_type=blocker row mapped to this task id"
            )
    return (not problems), "; ".join(problems) if problems else "OK"


ASSERTIONS = {
    "schema_valid": _assert_schema_valid,
    "plan_complete": _assert_plan_complete,
    "standard_gates_intact": _assert_standard_gates_intact,
    "blocked_research_justified": _assert_blocked_research_justified,
    "workspace_layout": _assert_workspace_layout,
    "plan_rendered": _assert_plan_rendered,
    "plan_approved": _assert_plan_approved,
    "execution_configured": _assert_execution_configured,
    "no_dependency_cycles": _assert_no_cycles,
    "no_orphan_dependencies": _assert_no_orphans,
    "no_task_is_done": _assert_no_task_is_done,
    "all_tasks_terminal": _assert_all_tasks_terminal,
    "research_tasks_terminal": _assert_research_tasks_terminal,
    "synthesis_tasks_terminal": _assert_synthesis_tasks_terminal,
    "all_outputs_exist": _assert_all_outputs_exist,
    "research_outputs_exist": _assert_research_outputs_exist,
    "synthesis_outputs_exist": _assert_synthesis_outputs_exist,
    "ledger_validates": _assert_ledger_validates,
    "ledger_signed": _assert_ledger_signed,
    "ledger_hmac_verified": _assert_ledger_hmac_verified,
    "reproducibility_checklist_exists": _assert_repro_checklist_exists,
    "reproducibility_checklist_complete": _assert_repro_checklist_complete,
    "final_report_exists": _assert_final_report_exists,
    "final_report_valid": _assert_final_report_valid,
    "claim_coverage_complete": _assert_claim_coverage_complete,
    "rendered_citations_exist": _assert_rendered_citations_exist,
    "stopping_criteria_satisfied": _assert_stopping_criteria_satisfied,
}


def run_gate(
    plan: dict[str, Any],
    plan_path: Path,
    gate_name: str,
    seen: set[str] | None = None,
) -> tuple[bool, list[tuple[str, bool, str]]]:
    schema_errors = validate_schema(plan)
    if schema_errors:
        return False, [("schema_valid", False, "; ".join(schema_errors))]
    gates = plan.get("gates")
    if not isinstance(gates, dict):
        return False, [("schema_valid", False, "`gates` must be an object")]
    gate = gates.get(gate_name)
    if gate is None:
        raise KeyError(f"gate not found: {gate_name!r}")
    if not isinstance(gate, dict):
        return False, [("gate_shape", False, f"gates.{gate_name} must be an object")]
    seen = set(seen or set())
    if gate_name in seen:
        raise KeyError(f"recursive gate reference: {gate_name!r}")
    seen.add(gate_name)
    results: list[tuple[str, bool, str]] = []
    all_ok = True
    # Standard gates must keep canonical assertions (empty/incomplete never pass).
    gate_errors = _validate_standard_gates(plan)
    relevant = [
        e
        for e in gate_errors
        if gate_name in e
        or (
            gate_name in {"execute_ready", "dispatch_ready"}
            and ("execute_ready" in e or "dispatch_ready" in e)
        )
    ]
    if relevant:
        for e in relevant:
            results.append(("standard_gates_intact", False, e))
        all_ok = False
    assertions = gate.get("assertions") or []
    if not assertions:
        results.append(
            (
                "assertions_nonempty",
                False,
                f"gates.{gate_name}.assertions is empty; standard invariants cannot be removed",
            )
        )
        return False, results
    for name in assertions:
        fn = ASSERTIONS.get(name)
        if fn is not None:
            ok, detail = fn(plan, plan_path)
            results.append((name, ok, detail))
            if not ok:
                all_ok = False
            continue
        if name in plan.get("gates", {}):
            ok, nested = run_gate(plan, plan_path, name, set(seen))
            failed = [n for n, passed, _detail in nested if not passed]
            detail = "OK" if ok else f"nested gate failed assertions: {failed}"
            results.append((name, ok, detail))
            if not ok:
                all_ok = False
            continue
        else:
            results.append((name, False, f"unknown assertion {name!r}"))
            all_ok = False
            continue
    return all_ok, results


# ---------------------------------------------------------------------------
# CLI subcommands
# ---------------------------------------------------------------------------


def _generic_draft_plan(slug: str, title: str | None) -> dict[str, Any]:
    """Build a generic schema-2.0 draft plan (empty tasks/SQs; plan_ready fails)."""
    template = (
        Path(__file__).resolve().parent.parent / "templates" / "research-plan.json"
    )
    if template.exists():
        plan = json.loads(template.read_text(encoding="utf-8"))
    else:
        plan = {
            "schema_version": PLAN_SCHEMA_VERSION,
            "workspace_dir": ".",
            "plan_render_path": "PLAN.md",
            "execution_profile": {
                "source": "defaults",
                "main_context_length": None,
                "task_budget_ratio": 0.5,
                "checkpoint_policy": DEFAULT_CONFIG["researchPlan"]["context"].get(
                    "writeFindingsImmediately"
                )
                and "write findings to declared output files immediately; split the task before reading sources or inputs that risk exceeding the context budget",
                "subagent_slots": [
                    {
                        "id": "default",
                        "agent": None,
                        "context_length": None,
                        "max_parallel": None,
                    }
                ],
            },
            "sub_questions": [],
            "source_classes": [],
            "approval": {
                "approved_by": "",
                "approved_at": "",
                "notes": "",
                APPROVAL_DIGEST_KEY: "",
            },
            "stopping_criteria": "",
            "stopping_criteria_satisfied": False,
            "tasks": [],
            "gates": {},
            "notes": "",
        }
    safe_slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", (slug or "research").strip()).strip("-")
    safe_slug = safe_slug or "research"
    plan["schema_version"] = PLAN_SCHEMA_VERSION
    plan["plan_id"] = f"{safe_slug}-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    plan["title"] = (title or "").strip() or f"Research plan: {safe_slug}"
    plan["created"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    plan["scope"] = plan.get("scope") or ""
    plan["sub_questions"] = []
    plan["tasks"] = []
    plan["stopping_criteria_satisfied"] = False
    plan["approval"] = {
        "approved_by": "",
        "approved_at": "",
        "notes": "",
        APPROVAL_DIGEST_KEY: "",
    }
    # Ensure modern gate set is present even if template is stale.
    plan["gates"] = _canonical_gate_defs()
    return plan


def cmd_init(args: argparse.Namespace) -> int:
    try:
        config, config_path = _load_config(args.config, Path.cwd().resolve())
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: could not load config: {exc}", file=sys.stderr)
        return 1
    if args.workspace:
        workspace = Path(args.workspace).resolve()
        out_arg = Path(args.out) if args.out else Path("research-plan.json")
        out = out_arg if out_arg.is_absolute() else workspace / out_arg
        out = out.resolve()
    elif args.out:
        out = Path(args.out).resolve()
    else:
        try:
            workspace, warning = _workspace_from_config(
                config, config_path, Path.cwd().resolve(), args.slug
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(
                f"FAIL: could not resolve workspace from config: {exc}", file=sys.stderr
            )
            return 1
        if warning:
            print(f"WARN: {warning}", file=sys.stderr)
        out = (workspace / "research-plan.json").resolve()
    if out.exists() and not args.force:
        print(
            f"FAIL: {out} exists; pass --force to overwrite",
            file=sys.stderr,
        )
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    title = getattr(args, "title", None)
    plan = _generic_draft_plan(args.slug or "research", title)
    apply_execution_config(plan, config, config_path)
    save(plan, out)
    _scaffold_workspace(out.parent)
    print(f"wrote draft plan to {out}")
    print(f"workspace: {out.parent}")
    print(
        "note: draft plan has empty tasks/sub_questions; plan_ready fails until filled"
    )
    return 0


def migrate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Upgrade a v1 plan dict to schema 2.0 in memory."""
    plan = dict(plan)
    plan.pop("_compat_warned", None)
    plan["schema_version"] = PLAN_SCHEMA_VERSION
    for task in plan.get("tasks", []):
        if not isinstance(task, dict):
            continue
        task["phase"] = _infer_phase(task)
    # Replace standard gates with canonical schema 2.0 sets; keep custom gates.
    custom = {}
    gates = plan.get("gates")
    if isinstance(gates, dict):
        for gname, gate in gates.items():
            if gname not in CANONICAL_GATES and gname != "dispatch_ready":
                custom[gname] = gate
    plan["gates"] = {**_canonical_gate_defs(), **custom}
    # Skip obsolete normalize below; keep structure for compatibility.
    gates = plan.get("gates")
    if isinstance(gates, dict):
        for gname, gate in gates.items():
            if not isinstance(gate, dict):
                continue
            assertions = list(gate.get("assertions") or [])
            mapped: list[str] = []
            for a in assertions:
                if a == "all_tasks_terminal" and gname == "synthesize_ready":
                    mapped.append("research_tasks_terminal")
                elif a == "all_outputs_exist" and gname == "synthesize_ready":
                    mapped.append("research_outputs_exist")
                elif a == "ledger_signed":
                    mapped.append("ledger_hmac_verified")
                elif a == "reproducibility_checklist_exists":
                    mapped.append("reproducibility_checklist_complete")
                elif a == "final_report_exists" and gname == "release_ready":
                    mapped.append("final_report_valid")
                else:
                    mapped.append(a)
            if gname == "plan_ready" and "plan_complete" not in mapped:
                # Insert after schema_valid when present.
                if "schema_valid" in mapped:
                    idx = mapped.index("schema_valid") + 1
                    mapped.insert(idx, "plan_complete")
                else:
                    mapped.insert(0, "plan_complete")
            if gname == "release_ready":
                for needed in (
                    "synthesis_tasks_terminal",
                    "synthesis_outputs_exist",
                    "claim_coverage_complete",
                ):
                    if needed not in mapped:
                        mapped.append(needed)
            gate["assertions"] = mapped
    # Revoke approval — migration invalidates prior review.
    plan["approval"] = {
        "approved_by": "",
        "approved_at": "",
        "notes": "revoked by migrate to schema 2.0; re-render and re-approve",
        APPROVAL_DIGEST_KEY: "",
    }
    return plan


def cmd_migrate(args: argparse.Namespace) -> int:
    src = Path(args.file).resolve()
    if not src.exists():
        print(f"FAIL: plan not found: {src}", file=sys.stderr)
        return 1
    try:
        raw = _load_strict_json(src)
    except (OSError, json.JSONDecodeError, UnicodeError, ValueError) as exc:
        print(f"FAIL: cannot read source plan: {exc}", file=sys.stderr)
        return 1
    if not isinstance(raw, dict) or not raw:
        print("FAIL: plan must be a non-empty JSON object", file=sys.stderr)
        return 1
    # Minimal source sanity: must have tasks list or enough structure to migrate.
    if "tasks" not in raw and "plan_id" not in raw and "title" not in raw:
        print("FAIL: source plan is not a migratable research plan", file=sys.stderr)
        return 1
    migrated = migrate_plan(raw)
    migrated.pop("_compat_warned", None)
    # Validate complete schema 2.0 result before writing.
    errs = validate_schema(migrated)
    if errs:
        print("FAIL: migrated plan failed schema validation; not writing", file=sys.stderr)
        for e in errs:
            print(f"  {e}", file=sys.stderr)
        return 1
    if args.in_place:
        backup = src.with_suffix(src.suffix + ".bak")
        backup.write_bytes(src.read_bytes())
        out = src
        print(f"backup written to {backup}")
    else:
        if not args.out:
            print("FAIL: --out required unless --in-place", file=sys.stderr)
            return 1
        out = Path(args.out).resolve()
        # --out must never mutate the source workspace.
        if out.resolve() == src.resolve():
            print("FAIL: --out points at source; use --in-place", file=sys.stderr)
            return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    save(migrated, out)
    # Remove stale rendered PLAN only in the destination workspace.
    _remove_rendered_plan(migrated, out)
    print(f"migrated plan written to {out}")
    print("approval revoked; re-run render + approve before execute_ready")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    plan_path = Path(args.file).resolve()
    plan = load(plan_path)
    errors = validate_schema(plan)
    cycles = detect_cycles(plan)
    if errors or cycles:
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        for c in cycles:
            print(f"  cycle: {' -> '.join(c)}", file=sys.stderr)
        print(
            f"FAIL: {len(errors)} schema error(s), {len(cycles)} cycle(s)",
            file=sys.stderr,
        )
        return 1
    print(
        f"OK: {len(plan.get('tasks', []))} task(s), "
        f"{len(plan.get('gates', {}))} gate(s)"
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    plan_path = Path(args.file).resolve()
    plan = load(plan_path)
    errors = validate_schema(plan)
    if errors:
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        print("FAIL: invalid research plan", file=sys.stderr)
        return 1
    print(format_status(plan))
    return 0


def cmd_parallelizable(args: argparse.Namespace) -> int:
    plan_path = Path(args.file).resolve()
    plan = load(plan_path)
    errors = validate_schema(plan)
    if errors:
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        print("FAIL: invalid research plan", file=sys.stderr)
        return 1
    ids = parallelizable_tasks(plan)
    if not ids:
        print("(none ready)")
    else:
        for tid in ids:
            print(tid)
    return 0


def _find_task(plan: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    tasks = plan.get("tasks", [])
    if not isinstance(tasks, list):
        return None
    for t in tasks:
        if isinstance(t, dict) and t.get("id") == task_id:
            return t
    return None


def _approval_is_set(plan: dict[str, Any]) -> bool:
    approval = plan.get("approval")
    return isinstance(approval, dict) and bool(approval.get("approved_by"))


def _clear_approval(plan: dict[str, Any], notes: str = "") -> None:
    plan["approval"] = {
        "approved_by": "",
        "approved_at": "",
        "notes": notes,
        APPROVAL_DIGEST_KEY: "",
    }


def _remove_rendered_plan(plan: dict[str, Any], plan_path: Path) -> None:
    base = _plan_dir(plan_path)
    target, _detail = _resolve_workspace_path(
        base, str(plan.get("plan_render_path", "PLAN.md"))
    )
    if target is not None:
        try:
            target.unlink()
        except FileNotFoundError:
            pass


def cmd_mark(args: argparse.Namespace) -> int:
    plan_path = Path(args.file).resolve()
    plan = load(plan_path)
    if args.status not in VALID_STATUS:
        print(f"FAIL: status must be one of {sorted(VALID_STATUS)}", file=sys.stderr)
        return 1
    task = _find_task(plan, args.id)
    if task is None:
        print(f"FAIL: task {args.id!r} not found", file=sys.stderr)
        return 1
    task["status"] = args.status
    if args.status != "blocked":
        task["blocker_reason"] = ""
    save(plan, plan_path)
    print(f"task {args.id} -> {args.status}")
    return 0


def cmd_block(args: argparse.Namespace) -> int:
    plan_path = Path(args.file).resolve()
    plan = load(plan_path)
    task = _find_task(plan, args.id)
    if task is None:
        print(f"FAIL: task {args.id!r} not found", file=sys.stderr)
        return 1
    task["status"] = "blocked"
    task["blocker_reason"] = args.reason
    save(plan, plan_path)
    print(f"task {args.id} BLOCKED: {args.reason}")
    return 0


def cmd_add_task(args: argparse.Namespace) -> int:
    plan_path = Path(args.file).resolve()
    plan = load(plan_path)
    if _find_task(plan, args.id) is not None:
        print(f"FAIL: task {args.id!r} already exists", file=sys.stderr)
        return 1
    phase = getattr(args, "phase", None) or "research"
    if phase not in VALID_PHASE:
        print(f"FAIL: phase must be one of {sorted(VALID_PHASE)}", file=sys.stderr)
        return 1
    new_task = {
        "id": args.id,
        "description": args.description,
        "depends_on": list(args.depends_on or []),
        "parallel_safe": bool(args.parallel_safe),
        "owner": args.owner,
        "phase": phase,
        "inputs": list(args.inputs or []),
        "outputs": list(args.outputs or []),
        "status": "todo",
        "blocker_reason": "",
    }
    profile = plan.get("execution_profile")
    if isinstance(profile, dict):
        sub_count = sum(
            1
            for t in plan.get("tasks", [])
            if isinstance(t.get("execution"), dict)
            and t["execution"].get("agent") == "subagent"
        )
        new_task["execution"] = _execution_for_task(new_task, profile, sub_count)
    plan.setdefault("tasks", []).append(new_task)
    errors = validate_schema(plan)
    if errors:
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        print("FAIL: new task breaks schema; not saved", file=sys.stderr)
        return 1
    if detect_cycles(plan):
        print("FAIL: new task introduces a cycle; not saved", file=sys.stderr)
        return 1
    if _approval_is_set(plan):
        _clear_approval(plan, f"revoked after adding task {args.id}")
    _remove_rendered_plan(plan, plan_path)
    save(plan, plan_path)
    print(f"added task {args.id}")
    return 0


def _md_cell(value: Any) -> str:
    return str(value).replace("\n", " ").replace("|", "\\|")


def render_plan_markdown(plan: dict[str, Any], plan_path: Path) -> str:
    lines: list[str] = []
    lines.append(f"# {plan.get('title', 'Research Plan')}")
    lines.append("")
    lines.append("## Overview")
    lines.append(f"- Plan ID: `{plan.get('plan_id', '')}`")
    lines.append(f"- Plan file: `{plan_path.name}`")
    lines.append(f"- Workspace: `{_plan_dir(plan_path)}`")
    lines.append(f"- Approval contract: `{_plan_approval_sha256(plan)}`")
    lines.append("- Approval: recorded in `research-plan.json` after review")
    profile = plan.get("execution_profile", {})
    if isinstance(profile, dict):
        slots = _configured_slots(profile)
        lines.append(f"- Main context length: `{profile.get('main_context_length')}`")
        lines.append(f"- Configured subagent slots: `{len(slots)}`")
        lines.append(f"- Checkpoint policy: {profile.get('checkpoint_policy', '')}")
    lines.append("")
    lines.append("## Execution Slots")
    lines.append("| Slot | Agent | Context length | Max parallel | Status |")
    lines.append("|---|---|---|---|---|")
    if isinstance(profile, dict) and isinstance(profile.get("subagent_slots"), list):
        configured_ids = {slot.get("id") for slot in _configured_slots(profile)}
        for slot in profile.get("subagent_slots", []):
            if not isinstance(slot, dict):
                continue
            slot_id = slot.get("id", "")
            status = "configured" if slot_id in configured_ids else "disabled"
            lines.append(
                "| {slot} | {agent} | {context} | {maxp} | {status} |".format(
                    slot=_md_cell(slot_id),
                    agent=_md_cell(slot.get("agent")),
                    context=_md_cell(slot.get("context_length")),
                    maxp=_md_cell(slot.get("max_parallel")),
                    status=status,
                )
            )
    else:
        lines.append("| default | None | None | None | disabled |")
    lines.append("")
    lines.append("## Scope")
    lines.append(str(plan.get("scope", "")))
    lines.append("")
    lines.append("## Sub-questions")
    sub_questions = plan.get("sub_questions", [])
    if sub_questions:
        for sq in sub_questions:
            lines.append(f"- `{sq.get('id', '')}`: {sq.get('text', '')}")
    else:
        lines.append("- None declared")
    lines.append("")
    lines.append("## Source Classes")
    source_classes = plan.get("source_classes", [])
    lines.append(", ".join(source_classes) if source_classes else "Not specified")
    lines.append("")
    lines.append("## Tasks")
    lines.append(
        "| ID | Phase | Status | Parallel safe | Owner | Execution | Threads | Context length | Context budget | Depends on | Inputs | Outputs | Blocker | Description |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for task in plan.get("tasks", []):
        depends = ", ".join(task.get("depends_on", [])) or "-"
        inputs = "<br>".join(task.get("inputs", [])) or "-"
        outputs = "<br>".join(task.get("outputs", [])) or "-"
        execution = (
            task.get("execution", {}) if isinstance(task.get("execution"), dict) else {}
        )
        execution_label = execution.get("agent", "")
        if execution.get("subagent_slot"):
            execution_label += f":{execution.get('subagent_slot')}"
        thread_label = "{}/{}".format(
            execution.get("parallel_threads", ""),
            execution.get("max_parallel_threads", ""),
        )
        lines.append(
            "| {id} | {phase} | {status} | {parallel} | {owner} | {execution} | {threads} | {context} | {budget} | {depends} | {inputs} | {outputs} | {blocker} | {description} |".format(
                id=_md_cell(task.get("id", "")),
                phase=_md_cell(task.get("phase", "")),
                status=_md_cell(task.get("status", "")),
                parallel="yes" if task.get("parallel_safe") else "no",
                owner=_md_cell(task.get("owner", "")),
                execution=_md_cell(execution_label),
                threads=_md_cell(thread_label),
                context=_md_cell(execution.get("context_length", "agent-resolved")),
                budget=_md_cell(execution.get("context_budget", "agent-resolved")),
                depends=_md_cell(depends),
                inputs=_md_cell(inputs),
                outputs=_md_cell(outputs),
                blocker=_md_cell(task.get("blocker_reason", "") or "-"),
                description=_md_cell(task.get("description", "")),
            )
        )
    lines.append("")
    lines.append("## Gates")
    lines.append("| Gate | Assertions | Description |")
    lines.append("|---|---|---|")
    for name, gate in plan.get("gates", {}).items():
        assertions = ", ".join(gate.get("assertions", []))
        lines.append(
            f"| {_md_cell(name)} | {_md_cell(assertions)} | {_md_cell(gate.get('description', ''))} |"
        )
    lines.append("")
    lines.append("## Stopping Criteria")
    lines.append(str(plan.get("stopping_criteria", "")))
    lines.append("")
    return "\n".join(lines)


def cmd_render(args: argparse.Namespace) -> int:
    plan_path = Path(args.file).resolve()
    plan = load(plan_path)
    base = _plan_dir(plan_path)
    rel = args.out or plan.get("plan_render_path", "PLAN.md")
    target, detail = _resolve_workspace_path(base, str(rel))
    if target is None:
        print(f"FAIL: {detail}", file=sys.stderr)
        return 1
    if args.out:
        plan["plan_render_path"] = target.relative_to(base).as_posix()
        if _approval_is_set(plan):
            _clear_approval(plan, "revoked after changing plan_render_path")
        save(plan, plan_path)
    rendered = render_plan_markdown(plan, plan_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered, encoding="utf-8")
    print(f"wrote rendered plan to {target}")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    plan_path = Path(args.file).resolve()
    plan = load(plan_path)
    if not args.by and not args.allow_unattended:
        print(
            "FAIL: approval requires --by <name>; use --allow-unattended for explicit bypass",
            file=sys.stderr,
        )
        return 1
    if "plan_ready" in plan.get("gates", {}):
        ok, results = run_gate(plan, plan_path, "plan_ready")
        if not ok:
            for name, passed, detail in results:
                flag = "OK  " if passed else "FAIL"
                print(f"  [{flag}] {name}: {detail}")
            print("FAIL: plan_ready must pass before approval", file=sys.stderr)
            return 1
    by = args.by or "agent-self-approved"
    notes = args.notes or ""
    if args.allow_unattended and not args.notes:
        notes = "unattended approval via --allow-unattended"
    plan["approval"] = {
        "approved_by": by,
        "approved_at": _utc_now_iso(),
        "notes": notes,
        APPROVAL_DIGEST_KEY: _plan_approval_sha256(plan),
    }
    save(plan, plan_path)
    print(f"approved by {by}")
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    plan_path = Path(args.file).resolve()
    plan = load(plan_path)
    _clear_approval(plan, args.reason or "approval revoked")
    save(plan, plan_path)
    print("approval revoked")
    return 0


def cmd_configure_execution(args: argparse.Namespace) -> int:
    plan_path = Path(args.file).resolve()
    plan = load(plan_path)
    config_hint = args.config
    if not config_hint:
        profile = plan.get("execution_profile")
        if isinstance(profile, dict):
            source = profile.get("source")
            if isinstance(source, str) and source not in {"", "defaults"}:
                config_hint = source
    try:
        config, config_path = _load_config(config_hint, _plan_dir(plan_path))
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL: could not load config: {exc}", file=sys.stderr)
        return 1
    apply_execution_config(plan, config, config_path)
    if _approval_is_set(plan):
        _clear_approval(plan, "revoked after execution config update")
    _remove_rendered_plan(plan, plan_path)
    save(plan, plan_path)
    slots = _configured_slots(plan.get("execution_profile", {}))
    print(
        f"configured execution profile: {len(slots)} subagent slot(s), plan={plan_path}"
    )
    return 0


def cmd_set_execution(args: argparse.Namespace) -> int:
    plan_path = Path(args.file).resolve()
    plan = load(plan_path)
    task = _find_task(plan, args.id)
    if task is None:
        print(f"FAIL: task {args.id!r} not found", file=sys.stderr)
        return 1
    profile = plan.get("execution_profile")
    if not isinstance(profile, dict):
        print(
            "FAIL: plan has no execution_profile; run configure-execution",
            file=sys.stderr,
        )
        return 1
    ratio = _float_in_range(profile.get("task_budget_ratio"), 0.5, 0.1, 0.9)
    current_obj = task.get("execution")
    current: dict[str, Any] = current_obj if isinstance(current_obj, dict) else {}
    if args.agent == "main":
        context_length = args.context_length
        if context_length is None:
            context_length = _positive_int_or_none(profile.get("main_context_length"))
        context_budget = args.context_budget
        if context_budget is None:
            context_budget = _context_budget(context_length, ratio)
        execution = {
            "agent": "main",
            "subagent_slot": None,
            "parallel_threads": 0,
            "max_parallel_threads": 0,
            "context_length": context_length,
            "context_budget": context_budget,
            "checkpoint_policy": profile.get("checkpoint_policy"),
        }
    else:
        slot_id = args.slot or current.get("subagent_slot")
        configured = _configured_slots(profile)
        if not slot_id and len(configured) == 1:
            slot_id = configured[0].get("id")
        if not slot_id:
            print(
                "FAIL: --slot is required when multiple or no subagent slots exist",
                file=sys.stderr,
            )
            return 1
        slot = _slot_by_id(profile, str(slot_id))
        if slot is None:
            print(
                f"FAIL: configured subagent slot not found: {slot_id!r}",
                file=sys.stderr,
            )
            return 1
        max_parallel = args.max_parallel_threads
        if max_parallel is None:
            max_parallel = _positive_int_or_none(slot.get("max_parallel")) or 1
        parallel_threads = args.parallel_threads
        if parallel_threads is None:
            parallel_threads = (
                _positive_int_or_none(current.get("parallel_threads")) or 1
            )
        context_length = args.context_length
        if context_length is None:
            context_length = _positive_int_or_none(slot.get("context_length"))
        context_budget = args.context_budget
        if context_budget is None:
            context_budget = _context_budget(context_length, ratio)
        execution = {
            "agent": "subagent",
            "subagent_slot": str(slot_id),
            "parallel_threads": parallel_threads,
            "max_parallel_threads": max_parallel,
            "context_length": context_length,
            "context_budget": context_budget,
            "checkpoint_policy": profile.get("checkpoint_policy"),
        }
    task["execution"] = execution
    errors = validate_schema(plan)
    if errors:
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        print("FAIL: execution override breaks schema; not saved", file=sys.stderr)
        return 1
    if _approval_is_set(plan):
        _clear_approval(plan, f"revoked after execution override for {args.id}")
    _remove_rendered_plan(plan, plan_path)
    save(plan, plan_path)
    print(
        f"task {args.id} execution -> {execution['agent']}"
        + (f":{execution['subagent_slot']}" if execution.get("subagent_slot") else "")
    )
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    plan_path = Path(args.file).resolve()
    plan = load(plan_path)
    try:
        ok, results = run_gate(plan, plan_path, args.gate)
    except KeyError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    for name, passed, detail in results:
        flag = "OK  " if passed else "FAIL"
        print(f"  [{flag}] {name}: {detail}")
    if ok:
        print(f"GATE PASS: {args.gate}")
        return 0
    print(f"GATE FAIL: {args.gate}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _make_minimal_plan() -> dict[str, Any]:
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION,
        "plan_id": "test-plan",
        "title": "Test plan",
        "workspace_dir": ".",
        "plan_render_path": "PLAN.md",
        "scope": "scope",
        "sub_questions": [{"id": "SQ1", "text": "x"}],
        "approval": {
            "approved_by": "",
            "approved_at": "",
            "notes": "",
            APPROVAL_DIGEST_KEY: "",
        },
        "stopping_criteria": "done when done",
        "stopping_criteria_satisfied": False,
        "tasks": [
            {
                "id": "A",
                "description": "root A",
                "depends_on": [],
                "parallel_safe": True,
                "owner": "main",
                "phase": "research",
                "inputs": [],
                "outputs": ["research-output/notes/a.md"],
                "status": "todo",
                "blocker_reason": "",
            },
            {
                "id": "B",
                "description": "root B",
                "depends_on": [],
                "parallel_safe": True,
                "owner": "sub-1",
                "phase": "research",
                "inputs": [],
                "outputs": ["research-output/notes/b.md"],
                "status": "todo",
                "blocker_reason": "",
            },
            {
                "id": "C",
                "description": "join A+B",
                "depends_on": ["A", "B"],
                "parallel_safe": False,
                "owner": "main",
                "phase": "research",
                "inputs": [
                    "research-output/notes/a.md",
                    "research-output/notes/b.md",
                ],
                "outputs": ["research-output/sections/c.md"],
                "status": "todo",
                "blocker_reason": "",
            },
        ],
        "gates": _canonical_gate_defs(),
    }
    apply_execution_config(plan, DEFAULT_CONFIG, None)
    return plan


def _self_test() -> int:
    import contextlib
    import io

    def call_silent(fn, ns) -> int:
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            return fn(ns)

    @contextlib.contextmanager
    def chdir(path: Path):
        old = Path.cwd()
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(old)

    failures: list[str] = []

    # Sub-test 1: schema validation passes on a clean plan.
    plan = _make_minimal_plan()
    errs = validate_schema(plan)
    if errs:
        failures.append(f"schema clean plan should pass, got {errs}")

    # Sub-test 2: missing key is caught.
    bad = _make_minimal_plan()
    del bad["scope"]
    if not any("scope" in e for e in validate_schema(bad)):
        failures.append("missing `scope` should be flagged")

    # Sub-test 3: duplicate task id is caught.
    bad = _make_minimal_plan()
    bad["tasks"].append(dict(bad["tasks"][0]))
    if not any("duplicate" in e for e in validate_schema(bad)):
        failures.append("duplicate task id should be flagged")

    # Sub-test 4: missing dep is caught.
    bad = _make_minimal_plan()
    bad["tasks"][2]["depends_on"] = ["ZZZ"]
    if not any("ZZZ" in e for e in validate_schema(bad)):
        failures.append("unknown dep id should be flagged")

    # Sub-test 5: cycle detection finds a 2-cycle.
    bad = _make_minimal_plan()
    bad["tasks"][0]["depends_on"] = ["C"]  # A -> C, C -> A,B
    cycles = detect_cycles(bad)
    if not cycles:
        failures.append("expected at least one cycle, got none")

    # Sub-test 6: parallelizable on clean plan returns A and B but not C.
    plan = _make_minimal_plan()
    ready = parallelizable_tasks(plan)
    if set(ready) != {"A", "B"}:
        failures.append(f"expected ready={{A,B}}, got {ready}")

    # Sub-test 7: after A is done, B still ready but C still blocked
    # (waiting on B).
    plan = _make_minimal_plan()
    plan["tasks"][0]["status"] = "done"
    ready = parallelizable_tasks(plan)
    if set(ready) != {"B"}:
        failures.append(f"after A=done expected ready={{B}}, got {ready}")

    # Sub-test 8: after A and B done, C still excluded because parallel_safe=False.
    plan = _make_minimal_plan()
    plan["tasks"][0]["status"] = "done"
    plan["tasks"][1]["status"] = "done"
    ready = parallelizable_tasks(plan)
    if "C" in ready:
        failures.append(
            f"C is not parallel_safe so should not be returned by parallelizable, got {ready}"
        )

    # Sub-test 9: output overlap with running task removes the candidate.
    plan = _make_minimal_plan()
    plan["tasks"][0]["status"] = "running"
    plan["tasks"][1]["outputs"] = ["research-output/notes/a.md"]  # collide with A
    ready = parallelizable_tasks(plan)
    if "B" in ready:
        failures.append("B collides with running A's outputs; should be filtered")

    # Sub-test 10: round-trip save/load preserves the plan.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "plan.json"
        plan = _make_minimal_plan()
        save(plan, path)
        loaded = load(path)
        if loaded != plan:
            failures.append("round-trip save/load did not match")

    # Sub-test 11: plan_ready fails until PLAN.md is rendered.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "research-plan.json"
        plan = _make_minimal_plan()
        _scaffold_workspace(td_path)
        save(plan, path)
        ok, _results = run_gate(load(path), path, "plan_ready")
        if ok:
            failures.append("plan_ready should fail before PLAN.md exists")

    # Sub-test 12: render writes PLAN.md and plan_ready passes.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "research-plan.json"
        plan = _make_minimal_plan()
        _scaffold_workspace(td_path)
        save(plan, path)
        rc = call_silent(cmd_render, argparse.Namespace(file=str(path), out=None))
        ok, results = run_gate(load(path), path, "plan_ready")
        if rc != 0 or not ok:
            failures.append(f"plan_ready should pass after render, got {results}")

    # Sub-test 13: plan_ready fails if PLAN.md is stale.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "research-plan.json"
        plan = _make_minimal_plan()
        _scaffold_workspace(td_path)
        save(plan, path)
        call_silent(cmd_render, argparse.Namespace(file=str(path), out=None))
        plan = load(path)
        plan["scope"] = "changed after render"
        save(plan, path)
        ok, _results = run_gate(load(path), path, "plan_ready")
        if ok:
            failures.append("plan_ready should fail when PLAN.md is stale")

    # Sub-test 14: execute_ready fails until approval is recorded.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "research-plan.json"
        plan = _make_minimal_plan()
        _scaffold_workspace(td_path)
        save(plan, path)
        call_silent(cmd_render, argparse.Namespace(file=str(path), out=None))
        ok, _results = run_gate(load(path), path, "execute_ready")
        if ok:
            failures.append("execute_ready should fail before approval")

    # Sub-test 15: approve records approval and execute_ready passes.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "research-plan.json"
        plan = _make_minimal_plan()
        _scaffold_workspace(td_path)
        save(plan, path)
        call_silent(cmd_render, argparse.Namespace(file=str(path), out=None))
        rc = call_silent(
            cmd_approve,
            argparse.Namespace(
                file=str(path), by="unit-test", notes="ok", allow_unattended=False
            ),
        )
        ok, results = run_gate(load(path), path, "execute_ready")
        if rc != 0 or not ok:
            failures.append(f"execute_ready should pass after approval, got {results}")

    # Sub-test 16: approve fails without --by unless unattended bypass is explicit.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "research-plan.json"
        plan = _make_minimal_plan()
        _scaffold_workspace(td_path)
        save(plan, path)
        call_silent(cmd_render, argparse.Namespace(file=str(path), out=None))
        rc = call_silent(
            cmd_approve,
            argparse.Namespace(
                file=str(path), by=None, notes=None, allow_unattended=False
            ),
        )
        if rc == 0:
            failures.append("approve should require --by without --allow-unattended")

    # Sub-test 17: execute_ready FAILS when a task is already `done`.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "research-plan.json"
        plan = _make_minimal_plan()
        plan["tasks"][0]["status"] = "done"
        _scaffold_workspace(td_path)
        save(plan, path)
        call_silent(cmd_render, argparse.Namespace(file=str(path), out=None))
        plan = load(path)
        plan["approval"] = {
            "approved_by": "unit-test",
            "approved_at": _utc_now_iso(),
            "notes": "",
            APPROVAL_DIGEST_KEY: _plan_approval_sha256(plan),
        }
        save(plan, path)
        ok, _results = run_gate(load(path), path, "execute_ready")
        if ok:
            failures.append("execute_ready should fail when a task is done")


    # Sub-test 17b: empty standard gate assertions fail schema check and gate run.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "plan.json"
        plan = _make_minimal_plan()
        plan["gates"]["release_ready"]["assertions"] = []
        _scaffold_workspace(td_path)
        save(plan, path)
        errs = validate_schema(load(path))
        if not any("release_ready" in e and "non-empty" in e or "missing required" in e or "assertions" in e for e in errs):
            # accept any release_ready assertion error
            if not any("release_ready" in e for e in errs):
                failures.append(f"empty release_ready.assertions must fail schema: {errs}")
        ok, _results = run_gate(load(path), path, "release_ready")
        if ok:
            failures.append("gate release_ready must fail when assertions are empty")

    # Sub-test 18: research outputs assertion fails when outputs are missing.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "plan.json"
        plan = _make_minimal_plan()
        for tsk in plan["tasks"]:
            tsk["status"] = "done"
        _scaffold_workspace(td_path)
        save(plan, path)
        ok, detail = _assert_research_outputs_exist(load(path), path)
        if ok:
            failures.append("research_outputs_exist should fail when outputs do not exist")

    # Sub-test 19: research phase terminal+outputs pass when research done.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "plan.json"
        plan = _make_minimal_plan()
        _scaffold_workspace(td_path)
        for tsk in plan["tasks"]:
            tsk["status"] = "done"
            for op in tsk["outputs"]:
                ofile = td_path / op
                ofile.parent.mkdir(parents=True, exist_ok=True)
                ofile.write_text("x", encoding="utf-8")
        save(plan, path)
        loaded = load(path)
        ok1, d1 = _assert_research_tasks_terminal(loaded, path)
        ok2, d2 = _assert_research_outputs_exist(loaded, path)
        if not (ok1 and ok2):
            failures.append(
                f"research terminal/outputs should pass when outputs exist: {d1} {d2}"
            )

    # Sub-test 20: schema rejects output paths outside the workspace.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "plan.json"
        plan = _make_minimal_plan()
        plan["tasks"][0]["outputs"] = ["../escape.md"]
        for tsk in plan["tasks"]:
            tsk["status"] = "done"
        _scaffold_workspace(td_path)
        errs = validate_schema(plan)
        if not any("unsafe" in e or "research-output" in e or "escape" in e for e in errs):
            failures.append(f"schema should reject escaping output paths: {errs}")

    # Sub-test 21: add-task rejects a cycle.
    plan = _make_minimal_plan()
    plan["tasks"].append(
        {
            "id": "D",
            "description": "bad",
            "depends_on": ["C"],
            "parallel_safe": True,
            "owner": "main",
            "inputs": [],
            "outputs": ["research-output/notes/d.md"],
            "status": "todo",
            "blocker_reason": "",
        }
    )
    plan["tasks"][0]["depends_on"] = ["D"]  # closes the loop A->D->C->A
    if not detect_cycles(plan):
        failures.append("A->D->C->A cycle should be detected")

    # Sub-test 22: blocked dep does not satisfy parallelizable.
    plan = _make_minimal_plan()
    plan["tasks"][0]["status"] = "blocked"
    plan["tasks"][0]["blocker_reason"] = "manual"
    plan["tasks"][1]["status"] = "done"
    plan["tasks"][2]["parallel_safe"] = True  # in case
    ready = parallelizable_tasks(plan)
    if "C" in ready:
        failures.append("C must not be ready when one of its deps is blocked")

    # Sub-test 23: parallelizable respects subagent slot maxParallel.
    plan = _make_minimal_plan()
    plan["tasks"].append(
        {
            "id": "D",
            "description": "root D",
            "depends_on": [],
            "parallel_safe": True,
            "owner": "sub-2",
            "inputs": [],
            "outputs": ["research-output/notes/d.md"],
            "status": "todo",
            "blocker_reason": "",
        }
    )
    cfg = _deep_merge(
        DEFAULT_CONFIG,
        {
            "researchPlan": {
                "subagents": {
                    "slots": [
                        {
                            "id": "reader-a",
                            "agent": "explore",
                            "contextLength": 30000,
                            "maxParallel": 1,
                        }
                    ]
                }
            }
        },
    )
    apply_execution_config(plan, cfg, None)
    ready = parallelizable_tasks(plan)
    if len([tid for tid in ready if tid in {"B", "D"}]) != 1:
        failures.append(
            "parallelizable should return only one task per saturated subagent slot"
        )

    # Sub-test 24: init scaffolds a workspace.
    with tempfile.TemporaryDirectory() as td:
        workspace = Path(td) / "research-test"
        rc = call_silent(
            cmd_init,
            argparse.Namespace(
                workspace=str(workspace),
                out=None,
                force=False,
                slug="research",
                config=None,
            ),
        )
        if rc != 0:
            failures.append("init --workspace should pass")
        for rel in [
            "research-plan.json",
            "evidence-ledger.csv",
            "research-output/notes",
            "research-output/sections",
        ]:
            if not (workspace / rel).exists():
                failures.append(f"init --workspace missing {rel}")

    # Sub-test 25: init without --workspace creates a unique workspace in cwd.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        with chdir(td_path):
            rc = call_silent(
                cmd_init,
                argparse.Namespace(
                    workspace=None, out=None, force=False, slug="topic", config=None
                ),
            )
        workspaces = list(td_path.glob("research-topic-*"))
        if rc != 0 or len(workspaces) != 1:
            failures.append("init should create one auto workspace in cwd")
        elif not (workspaces[0] / "research-plan.json").exists():
            failures.append("auto workspace missing research-plan.json")

    # Sub-test 26: config baseDir controls the workspace parent.
    with tempfile.TemporaryDirectory() as td:
        project = Path(td) / "project"
        project.mkdir()
        (project / "research.config.json").write_text(
            json.dumps({"researchPlan": {"workspace": {"baseDir": "runs"}}}),
            encoding="utf-8",
        )
        with chdir(project):
            rc = call_silent(
                cmd_init,
                argparse.Namespace(
                    workspace=None, out=None, force=False, slug="topic", config=None
                ),
            )
        workspaces = list((project / "runs").glob("research-topic-*"))
        if rc != 0 or len(workspaces) != 1:
            failures.append(
                "config baseDir should create workspace under configured dir"
            )

    # Sub-test 27: inaccessible config baseDir falls back to cwd.
    with tempfile.TemporaryDirectory() as td:
        project = Path(td) / "project"
        project.mkdir()
        (project / "blocked").write_text("not a directory", encoding="utf-8")
        (project / "research.config.json").write_text(
            json.dumps({"researchPlan": {"workspace": {"baseDir": "blocked"}}}),
            encoding="utf-8",
        )
        with chdir(project):
            rc = call_silent(
                cmd_init,
                argparse.Namespace(
                    workspace=None, out=None, force=False, slug="topic", config=None
                ),
            )
        fallback_workspaces = list(project.glob("research-topic-*"))
        if rc != 0 or len(fallback_workspaces) != 1:
            failures.append("inaccessible config baseDir should fall back to cwd")

    # Sub-test 28: configured subagent slot annotates sub-owned tasks.
    plan = _make_minimal_plan()
    cfg = _deep_merge(
        DEFAULT_CONFIG,
        {
            "researchPlan": {
                "context": {"mainContextLength": 100000, "taskBudgetRatio": 0.4},
                "subagents": {
                    "slots": [
                        {
                            "id": "deep-reader",
                            "agent": "explore",
                            "contextLength": 32000,
                            "maxParallel": 3,
                        }
                    ]
                },
            }
        },
    )
    apply_execution_config(plan, cfg, None)
    sub_task = next(t for t in plan["tasks"] if t["owner"] == "sub-1")
    main_task = next(t for t in plan["tasks"] if t["owner"] == "main")
    if sub_task["execution"]["agent"] != "subagent":
        failures.append("configured subagent slot should annotate sub-owned tasks")
    if sub_task["execution"]["context_budget"] != 12800:
        failures.append(
            "subagent context budget should derive from slot context length"
        )
    if main_task["execution"]["context_budget"] != 40000:
        failures.append("main context budget should derive from main context length")

    # Sub-test 29: configure-execution rewrites an existing plan from config.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "research-plan.json"
        plan = _make_minimal_plan()
        save(plan, path)
        config_path = td_path / "research.config.json"
        config_path.write_text(
            json.dumps(
                {
                    "researchPlan": {
                        "subagents": {
                            "slots": [
                                {
                                    "id": "slot-a",
                                    "agent": "general",
                                    "contextLength": 24000,
                                    "maxParallel": 2,
                                }
                            ]
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        rc = call_silent(
            cmd_configure_execution,
            argparse.Namespace(file=str(path), config=str(config_path)),
        )
        loaded = load(path)
        sub_task = next(t for t in loaded["tasks"] if t["owner"] == "sub-1")
        if rc != 0 or sub_task["execution"]["subagent_slot"] != "slot-a":
            failures.append("configure-execution should apply configured subagent slot")

    # Sub-test 30: set-execution lets a reviewer switch a task slot/thread count.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "research-plan.json"
        plan = _make_minimal_plan()
        cfg = _deep_merge(
            DEFAULT_CONFIG,
            {
                "researchPlan": {
                    "subagents": {
                        "slots": [
                            {
                                "id": "reader-a",
                                "agent": "explore",
                                "contextLength": 30000,
                                "maxParallel": 3,
                            },
                            {
                                "id": "reader-b",
                                "agent": "general",
                                "contextLength": 60000,
                                "maxParallel": 2,
                            },
                        ]
                    }
                }
            },
        )
        apply_execution_config(plan, cfg, None)
        save(plan, path)
        rc = call_silent(
            cmd_set_execution,
            argparse.Namespace(
                file=str(path),
                id="B",
                agent="subagent",
                slot="reader-b",
                parallel_threads=2,
                max_parallel_threads=None,
                context_length=None,
                context_budget=None,
            ),
        )
        loaded = load(path)
        task_b = next(t for t in loaded["tasks"] if t["id"] == "B")
        if rc != 0 or task_b["execution"]["subagent_slot"] != "reader-b":
            failures.append(
                "set-execution should switch the task to the requested slot"
            )
        if task_b["execution"]["parallel_threads"] != 2:
            failures.append("set-execution should apply requested parallel_threads")

    # Sub-test 31: set-execution rejects thread counts above the slot max.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "research-plan.json"
        plan = _make_minimal_plan()
        cfg = _deep_merge(
            DEFAULT_CONFIG,
            {
                "researchPlan": {
                    "subagents": {
                        "slots": [
                            {
                                "id": "reader-a",
                                "agent": "explore",
                                "contextLength": 30000,
                                "maxParallel": 1,
                            }
                        ]
                    }
                }
            },
        )
        apply_execution_config(plan, cfg, None)
        save(plan, path)
        rc = call_silent(
            cmd_set_execution,
            argparse.Namespace(
                file=str(path),
                id="B",
                agent="subagent",
                slot="reader-a",
                parallel_threads=2,
                max_parallel_threads=None,
                context_length=None,
                context_budget=None,
            ),
        )
        if rc == 0:
            failures.append("set-execution should reject parallel_threads above max")

    # Sub-test 32: configure-execution reuses the config path recorded by init.
    with tempfile.TemporaryDirectory() as td:
        project = Path(td) / "project"
        output_root = Path(td) / "external-runs"
        project.mkdir()
        config_path = project / "research.config.json"
        config_path.write_text(
            json.dumps(
                {
                    "researchPlan": {
                        "workspace": {"baseDir": str(output_root)},
                        "subagents": {
                            "slots": [
                                {
                                    "id": "external-slot",
                                    "agent": "general",
                                    "contextLength": 30000,
                                    "maxParallel": 2,
                                }
                            ]
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        with chdir(project):
            rc = call_silent(
                cmd_init,
                argparse.Namespace(
                    workspace=None,
                    out=None,
                    force=False,
                    slug="topic",
                    config=None,
                    title="Topic research",
                ),
            )
        workspaces = list(output_root.glob("research-topic-*"))
        if rc != 0 or len(workspaces) != 1:
            failures.append("init should create configured external workspace")
        else:
            plan_path = workspaces[0] / "research-plan.json"
            # Seed a sub-owned research task without clobbering execution_profile.source.
            seeded = load(plan_path)
            profile = seeded.get("execution_profile")
            if not isinstance(profile, dict):
                failures.append("init should write execution_profile")
            else:
                seeded["tasks"] = [
                    {
                        "id": "T1",
                        "description": "seed task",
                        "depends_on": [],
                        "parallel_safe": True,
                        "owner": "sub-1",
                        "phase": "research",
                        "inputs": [],
                        "outputs": ["research-output/notes/t1.md"],
                        "status": "todo",
                        "blocker_reason": "",
                        "execution": _execution_for_task(
                            {
                                "id": "T1",
                                "owner": "sub-1",
                                "phase": "research",
                            },
                            profile,
                            0,
                        ),
                    }
                ]
                save(seeded, plan_path)
            with chdir(workspaces[0]):
                rc = call_silent(
                    cmd_configure_execution,
                    argparse.Namespace(file=str(plan_path), config=None),
                )
            loaded = load(plan_path)
            sub_task = next(t for t in loaded["tasks"] if t["owner"] == "sub-1")
            if rc != 0 or sub_task["execution"]["subagent_slot"] != "external-slot":
                failures.append(
                    "configure-execution should reuse recorded external config path"
                )

    # Sub-test 33: subagent slot with agent requires contextLength and maxParallel.
    plan = _make_minimal_plan()
    cfg = _deep_merge(
        DEFAULT_CONFIG,
        {"researchPlan": {"subagents": {"slots": [{"id": "bad", "agent": "general"}]}}},
    )
    apply_execution_config(plan, cfg, None)
    if not any("must set context_length" in e for e in validate_schema(plan)):
        failures.append(
            "configured subagent slot should require context length and max parallel"
        )

    # Sub-test 34: real template parses cleanly as a draft (empty tasks OK).
    template = (
        Path(__file__).resolve().parent.parent / "templates" / "research-plan.json"
    )
    if template.exists():
        try:
            plan = load(template)
            errs = validate_schema(plan)
            if errs:
                failures.append(f"shipped template fails schema: {errs}")
            if detect_cycles(plan):
                failures.append("shipped template has a cycle")
            ok_complete, _ = _assert_plan_complete(plan, template)
            if ok_complete:
                failures.append("draft template should fail plan_complete")
        except Exception as e:
            failures.append(f"failed to load shipped template: {e}")

    # Sub-test 35: init creates generic draft, not OAI-PMH content.
    with tempfile.TemporaryDirectory() as td:
        workspace = Path(td) / "ws"
        rc = call_silent(
            cmd_init,
            argparse.Namespace(
                workspace=str(workspace),
                out=None,
                force=False,
                slug="my-topic",
                config=None,
                title="My Topic Study",
            ),
        )
        plan = load(workspace / "research-plan.json")
        if rc != 0:
            failures.append("init draft should succeed")
        if plan.get("schema_version") != PLAN_SCHEMA_VERSION:
            failures.append("init should write schema_version 2.0")
        if plan.get("tasks"):
            failures.append("init draft should have empty tasks")
        if "OAI-PMH" in str(plan.get("title", "")) or "OAI-PMH" in str(
            plan.get("scope", "")
        ):
            failures.append("init must not copy OAI-PMH example content")
        ok, _ = run_gate(plan, workspace / "research-plan.json", "plan_ready")
        if ok:
            failures.append("draft plan_ready should fail until filled")

    # Sub-test 36: migrate v1 plan infers synthesis phase and revokes approval.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        src = td_path / "old.json"
        v1 = _make_minimal_plan()
        v1.pop("schema_version", None)
        for t in v1["tasks"]:
            t.pop("phase", None)
        v1["tasks"].append(
            {
                "id": "R",
                "description": "report",
                "depends_on": ["C"],
                "parallel_safe": False,
                "owner": "main",
                "inputs": [],
                "outputs": ["research-output/report.md"],
                "status": "todo",
                "blocker_reason": "",
                "execution": v1["tasks"][0]["execution"],
            }
        )
        v1["approval"] = {
            "approved_by": "old",
            "approved_at": "2026-01-01T00:00:00Z",
            "notes": "",
        }
        # Write raw without going through load() compat.
        src.write_text(json.dumps(v1, indent=2) + "\n", encoding="utf-8")
        out = td_path / "new.json"
        rc = call_silent(
            cmd_migrate,
            argparse.Namespace(file=str(src), out=str(out), in_place=False),
        )
        if rc != 0:
            failures.append("migrate should succeed")
        else:
            migrated = json.loads(out.read_text(encoding="utf-8"))
            if migrated.get("schema_version") != PLAN_SCHEMA_VERSION:
                failures.append("migrate should set schema 2.0")
            report_task = next(t for t in migrated["tasks"] if t["id"] == "R")
            if report_task.get("phase") != "synthesis":
                failures.append("migrate should infer synthesis phase for report task")
            if migrated.get("approval", {}).get("approved_by"):
                failures.append("migrate must revoke approval")

    # Sub-test 37: synthesize_ready ignores unfinished synthesis tasks.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "plan.json"
        plan = _make_minimal_plan()
        plan["tasks"].append(
            {
                "id": "R",
                "description": "report",
                "depends_on": ["C"],
                "parallel_safe": False,
                "owner": "main",
                "phase": "synthesis",
                "inputs": [],
                "outputs": ["research-output/report.md"],
                "status": "todo",
                "blocker_reason": "",
                "execution": plan["tasks"][0]["execution"],
            }
        )
        _scaffold_workspace(td_path)
        for t in plan["tasks"]:
            if t["phase"] == "research":
                t["status"] = "done"
                for op in t["outputs"]:
                    ofile = td_path / op
                    ofile.parent.mkdir(parents=True, exist_ok=True)
                    ofile.write_text("x", encoding="utf-8")
        save(plan, path)
        loaded = load(path)
        ok1, d1 = _assert_research_tasks_terminal(loaded, path)
        ok2, d2 = _assert_research_outputs_exist(loaded, path)
        if not (ok1 and ok2):
            failures.append(
                f"research phase should pass with research done and synthesis todo: {d1} {d2}"
            )
        # Full synthesize_ready still needs ledger/HMAC; release must fail.
        ok_rel, _ = run_gate(loaded, path, "release_ready")
        if ok_rel:
            failures.append("release_ready should fail while synthesis task is todo")
        ok_syn, _ = _assert_synthesis_tasks_terminal(loaded, path)
        if ok_syn:
            failures.append("synthesis_tasks_terminal should fail while R is todo")

    # Sub-test 38: committed v3.1.1 workspace fixture follows the upgrade guide.
    fixture_dir = (
        Path(__file__).resolve().parent.parent
        / "examples"
        / "fixtures"
        / "v3.1.1-workspace"
    )
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        fixture_plan = fixture_dir / "research-plan.json"
        fixture_render = fixture_dir / "PLAN.md"
        if not fixture_plan.is_file() or not fixture_render.is_file():
            failures.append("committed v3.1.1 upgrade workspace fixture is missing")
        else:
            plan_path = td_path / "research-plan.json"
            render_path = td_path / "PLAN.md"
            source_bytes = fixture_plan.read_bytes()
            plan_path.write_bytes(source_bytes)
            render_path.write_bytes(fixture_render.read_bytes())
            source_plan = json.loads(source_bytes)
            rc = call_silent(
                cmd_migrate,
                argparse.Namespace(file=str(plan_path), out=None, in_place=True),
            )
            backup_path = plan_path.with_suffix(plan_path.suffix + ".bak")
            if rc != 0:
                failures.append("committed v3.1.1 fixture migration should succeed")
            elif not backup_path.is_file() or backup_path.read_bytes() != source_bytes:
                failures.append("in-place fixture migration must preserve an exact backup")
            else:
                migrated = json.loads(plan_path.read_text(encoding="utf-8"))
                if render_path.exists():
                    failures.append("migration must remove the stale rendered PLAN.md")
                if migrated.get("schema_version") != PLAN_SCHEMA_VERSION:
                    failures.append("fixture migration must produce schema 2.0")
                source_tasks = {task["id"]: task for task in source_plan["tasks"]}
                migrated_tasks = {task["id"]: task for task in migrated["tasks"]}
                for task_id, source_task in source_tasks.items():
                    migrated_task = migrated_tasks.get(task_id)
                    if migrated_task is None:
                        failures.append(f"fixture migration lost task {task_id}")
                        continue
                    for key in (
                        "description",
                        "depends_on",
                        "owner",
                        "inputs",
                        "outputs",
                        "status",
                        "blocker_reason",
                        "execution",
                    ):
                        if migrated_task.get(key) != source_task.get(key):
                            failures.append(
                                f"fixture migration changed {task_id}.{key}"
                            )
                    expected_phase = "synthesis" if task_id == "T3" else "research"
                    if migrated_task.get("phase") != expected_phase:
                        failures.append(
                            f"fixture migration inferred wrong phase for {task_id}"
                        )
                if migrated.get("approval", {}).get("approved_by"):
                    failures.append("fixture migration must revoke prior approval")
                if "review_ready" not in migrated.get("gates", {}):
                    failures.append("fixture migration must preserve custom gates")

                _scaffold_workspace(td_path)
                render_rc = call_silent(
                    cmd_render,
                    argparse.Namespace(file=str(plan_path), out=None),
                )
                approve_rc = call_silent(
                    cmd_approve,
                    argparse.Namespace(
                        file=str(plan_path),
                        by="upgrade-fixture-reviewer",
                        notes="fixture re-approved",
                        allow_unattended=False,
                    ),
                )
                execute_ok, _ = run_gate(load(plan_path), plan_path, "execute_ready")
                if render_rc != 0 or approve_rc != 0 or not execute_ok:
                    failures.append(
                        "migrated fixture must render, re-approve, and pass execute_ready"
                    )

    # Sub-test 39: blocked synthesis is incomplete and cannot skip outputs.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "plan.json"
        plan = _make_minimal_plan()
        plan["tasks"].append(
            {
                "id": "S",
                "description": "blocked synthesis",
                "depends_on": ["C"],
                "parallel_safe": False,
                "owner": "main",
                "phase": "synthesis",
                "inputs": [],
                "outputs": ["research-output/report.md"],
                "status": "blocked",
                "blocker_reason": "report generation failed",
                "execution": plan["tasks"][0]["execution"],
            }
        )
        _scaffold_workspace(td_path)
        save(plan, path)
        loaded = load(path)
        terminal_ok, _ = _assert_synthesis_tasks_terminal(loaded, path)
        outputs_ok, _ = _assert_synthesis_outputs_exist(loaded, path)
        if terminal_ok or outputs_ok:
            failures.append("blocked synthesis must fail terminal and output assertions")

    # Sub-test 40: declared output directories need a non-empty artifact file.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "plan.json"
        plan = _make_minimal_plan()
        plan["tasks"] = [plan["tasks"][0]]
        plan["tasks"][0]["outputs"] = ["research-output/notes/bundle"]
        plan["tasks"][0]["status"] = "done"
        _scaffold_workspace(td_path)
        output_dir = td_path / "research-output" / "notes" / "bundle"
        output_dir.mkdir(parents=True)
        save(plan, path)
        empty_ok, _ = _assert_research_outputs_exist(load(path), path)
        if empty_ok:
            failures.append("empty output directory must not satisfy research_outputs_exist")
        (output_dir / "finding.md").write_text("evidence", encoding="utf-8")
        populated_ok, _ = _assert_research_outputs_exist(load(path), path)
        if not populated_ok:
            failures.append("non-empty output directory should satisfy research_outputs_exist")

    # Sub-test 41: checklist contract IDs are complete, unique, and versioned.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "plan.json"
        path.write_text("{}\n", encoding="utf-8")
        checklist = td_path / "reproducibility-checklist.md"
        template_text = CHECKLIST_TEMPLATE_PATH.read_text(encoding="utf-8")
        checklist.write_text("- [x] anything\n", encoding="utf-8")
        if _reproducibility_checklist_complete(path)[0]:
            failures.append("arbitrary checked item must not satisfy checklist gate")
        checklist.write_text(template_text, encoding="utf-8")
        if _reproducibility_checklist_complete(path)[0]:
            failures.append("canonical but unchecked checklist must fail")
        complete_text = template_text.replace("- [ ]", "- [x]")
        checklist.write_text(complete_text, encoding="utf-8")
        if not _reproducibility_checklist_complete(path)[0]:
            failures.append("complete canonical checklist should pass")
        missing_text = "\n".join(
            line for line in complete_text.splitlines() if "DRC-037" not in line
        )
        checklist.write_text(missing_text + "\n", encoding="utf-8")
        if _reproducibility_checklist_complete(path)[0]:
            failures.append("checklist missing a canonical ID must fail")
        checklist.write_text(
            complete_text.replace("DRC-037", "DRC-999"),
            encoding="utf-8",
        )
        if _reproducibility_checklist_complete(path)[0]:
            failures.append("checklist with unknown ID must fail")
        checklist.write_text(
            complete_text.replace("DRC-037", "DRC-036"),
            encoding="utf-8",
        )
        if _reproducibility_checklist_complete(path)[0]:
            failures.append("checklist with duplicate ID must fail")
        no_reason = re.sub(
            r"(<!-- DRC-001 -->).*",
            r"\1 N/A",
            complete_text,
            count=1,
        )
        checklist.write_text(no_reason, encoding="utf-8")
        if _reproducibility_checklist_complete(path)[0]:
            failures.append("N/A checklist item without a reason must fail")
        with_reason = no_reason.replace(
            "<!-- DRC-001 --> N/A",
            "<!-- DRC-001 --> N/A — no authored claims",
            1,
        )
        checklist.write_text(with_reason, encoding="utf-8")
        if not _reproducibility_checklist_complete(path)[0]:
            failures.append("N/A checklist item with a reason should pass")

    # Sub-test 42: citation placeholders cannot satisfy release readiness.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "plan.json"
        plan = _make_minimal_plan()
        plan["tasks"].append(
            {
                "id": "BIB",
                "description": "render bibliography",
                "depends_on": ["C"],
                "parallel_safe": False,
                "owner": "main",
                "phase": "synthesis",
                "inputs": [],
                "outputs": ["research-output/references.bib"],
                "status": "done",
                "blocker_reason": "",
                "execution": plan["tasks"][0]["execution"],
            }
        )
        _scaffold_workspace(td_path)
        save(plan, path)
        bibliography = td_path / "research-output" / "references.bib"
        bibliography.write_text("@article{x, title={TBD}}\n", encoding="utf-8")
        if _rendered_citations_exist(path)[0]:
            failures.append("citation placeholder must fail rendered_citations_exist")
        bibliography.write_text("@article{x, title={Verified title}}\n", encoding="utf-8")
        if not _rendered_citations_exist(path)[0]:
            failures.append("valid declared BibTeX should pass rendered_citations_exist")

    # Sub-test 43: v1 plans remain checkable through the compatibility adapter.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "legacy.json"
        legacy = _make_minimal_plan()
        legacy.pop("schema_version", None)
        for task in legacy["tasks"]:
            task.pop("phase", None)
        path.write_text(json.dumps(legacy, indent=2) + "\n", encoding="utf-8")
        rc = call_silent(cmd_check, argparse.Namespace(file=str(path)))
        if rc != 0:
            failures.append("v1 plan should pass check through the compatibility adapter")

    # Sub-test 44: citation-only v1 tasks migrate to synthesis phase.
    for output in ("research-output/references.bib", "research-output/references.ris"):
        task = {"outputs": [output]}
        if _infer_phase(task) != "synthesis":
            failures.append(f"citation output should infer synthesis phase: {output}")

    # Sub-test 45: approval binds every immutable execution-plan field.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "research-plan.json"
        plan = _make_minimal_plan()
        _scaffold_workspace(td_path)
        save(plan, path)
        call_silent(cmd_render, argparse.Namespace(file=str(path), out=None))
        approve_rc = call_silent(
            cmd_approve,
            argparse.Namespace(
                file=str(path), by="unit-test", notes="digest", allow_unattended=False
            ),
        )
        approved = load(path)
        if approve_rc != 0 or not _assert_plan_approved(approved, path)[0]:
            failures.append("approved plan must contain a valid immutable-plan digest")
        immutable_mutations = {
            "phase": lambda p: p["tasks"][0].__setitem__("phase", "synthesis"),
            "inputs": lambda p: p["tasks"][0]["inputs"].append(
                "research-output/notes/prior.md"
            ),
            "parallel_safe": lambda p: p["tasks"][0].__setitem__(
                "parallel_safe", False
            ),
            "execution": lambda p: p["tasks"][0]["execution"].__setitem__(
                "context_budget", 1
            ),
            "gate": lambda p: p["gates"]["execute_ready"].__setitem__(
                "description", "tampered"
            ),
        }
        for label, mutate in immutable_mutations.items():
            changed = json.loads(json.dumps(approved))
            mutate(changed)
            if _assert_plan_approved(changed, path)[0]:
                failures.append(f"approval digest accepted immutable {label} mutation")

        # Sub-test 46: old approved plans without a digest fail closed.
        legacy_approved = json.loads(json.dumps(approved))
        legacy_approved["approval"].pop(APPROVAL_DIGEST_KEY, None)
        if _assert_plan_approved(legacy_approved, path)[0] or not any(
            "plan_sha256" in error for error in validate_schema(legacy_approved)
        ):
            failures.append("approved schema-2.0 plan without plan_sha256 must fail closed")

        # Re-rendering a changed intent must not refresh the prior approval.
        rerendered_change = json.loads(json.dumps(approved))
        rerendered_change["scope"] = "changed and re-rendered after approval"
        save(rerendered_change, path)
        call_silent(cmd_render, argparse.Namespace(file=str(path), out=None))
        execute_ok, execute_results = run_gate(load(path), path, "execute_ready")
        if execute_ok or not any(
            not passed and "plan_sha256" in detail
            for _name, passed, detail in execute_results
        ):
            failures.append("re-rendering changed scope must not preserve execute_ready")
        save(approved, path)
        call_silent(cmd_render, argparse.Namespace(file=str(path), out=None))

        # Sub-test 47: runtime progress does not invalidate the immutable digest.
        progress = json.loads(json.dumps(approved))
        progress["tasks"][0]["status"] = "blocked"
        progress["tasks"][0]["blocker_reason"] = "source temporarily unavailable"
        progress["stopping_criteria_satisfied"] = True
        progress["notes"] = "runtime note"
        if not _assert_plan_approved(progress, path)[0]:
            failures.append(
                "runtime status/blocker/note changes must preserve plan approval digest"
            )

        # Sub-test 48: rendered review exposes mutable task state and becomes stale.
        rendered = (Path(path).parent / "PLAN.md").read_text(encoding="utf-8")
        for marker in (
            "Approval contract:",
            "| ID | Phase | Status | Parallel safe |",
            "| Depends on | Inputs | Outputs | Blocker |",
        ):
            if marker not in rendered:
                failures.append(f"rendered plan missing approval-review marker {marker!r}")
        if _plan_rendered_exists(progress, path)[0]:
            failures.append("runtime blocker mutation before dispatch must stale PLAN.md")

    # Sub-test 49: hostile JSON value types produce diagnostics, never tracebacks.
    malformed_mutations = {
        "status-list": lambda p: p["tasks"][0].__setitem__("status", []),
        "phase-list": lambda p: p["tasks"][0].__setitem__("phase", []),
        "dependency-object": lambda p: p["tasks"][0].__setitem__(
            "depends_on", [{}]
        ),
        "agent-list": lambda p: p["tasks"][0]["execution"].__setitem__("agent", []),
        "assertion-object": lambda p: p["gates"]["plan_ready"].__setitem__(
            "assertions", [{}]
        ),
        "sub-question-scalar": lambda p: p.__setitem__("sub_questions", [1]),
    }
    for label, mutate in malformed_mutations.items():
        malformed = _make_minimal_plan()
        mutate(malformed)
        try:
            malformed_errors = validate_schema(malformed)
            malformed_cycles = detect_cycles(malformed)
            gate_ok, _gate_results = run_gate(
                malformed, Path("malformed-plan.json"), "plan_ready"
            )
        except Exception as exc:  # pragma: no cover - converted to an explicit failure
            failures.append(f"malformed {label} raised {type(exc).__name__}: {exc}")
            continue
        if not malformed_errors or gate_ok or not isinstance(malformed_cycles, list):
            failures.append(f"malformed {label} did not fail closed")

    # Sub-test 50: check command rejects malformed graph shapes without crashing.
    with tempfile.TemporaryDirectory() as td:
        malformed_path = Path(td) / "malformed.json"
        malformed = _make_minimal_plan()
        malformed["tasks"][0]["depends_on"] = [{}]
        save(malformed, malformed_path)
        if call_silent(main, ["check", "--file", str(malformed_path)]) == 0:
            failures.append("check accepted a malformed dependency object")

    # Sub-test 51: duplicate keys and non-finite numbers are rejected by strict JSON.
    with tempfile.TemporaryDirectory() as td:
        duplicate_path = Path(td) / "duplicate.json"
        duplicate_path.write_text(
            '{"plan_id":"first","plan_id":"second"}\n', encoding="utf-8"
        )
        nonfinite_path = Path(td) / "nonfinite.json"
        nonfinite_path.write_text('{"schema_version":NaN}\n', encoding="utf-8")
        for label, hostile_path in (
            ("duplicate key", duplicate_path),
            ("non-finite number", nonfinite_path),
        ):
            if call_silent(main, ["check", "--file", str(hostile_path)]) == 0:
                failures.append(f"strict plan loader accepted {label}")

    # Sub-test 52: portable path rules are host-independent and comprehensive.
    valid_portable_paths = {
        "research-output/notes/a.md": "research-output/notes/a.md",
        "research-output\\notes\\b.md": "research-output/notes/b.md",
        "research-output/ghi-chú/đề-cương.md": "research-output/ghi-chú/đề-cương.md",
    }
    for raw, expected in valid_portable_paths.items():
        canonical, detail = _portable_relative_path(raw)
        if canonical != expected:
            failures.append(
                f"portable path {raw!r} should normalize to {expected!r}: {detail}"
            )
    invalid_portable_paths = {
        "": "empty",
        "/absolute/path": "POSIX absolute",
        "\\rooted\\path": "Windows root-relative",
        "\\\\server\\share\\file.md": "UNC",
        "C:\\absolute\\file.md": "Windows drive absolute",
        "C:drive-relative.md": "Windows drive relative",
        "~user/file.md": "home-relative",
        "research-output/../escape.md": "parent traversal",
        "research-output/./notes.md": "current-directory segment",
        "research-output//notes.md": "empty segment",
        "research-output/notes/file.md:stream": "alternate data stream",
        "research-output/notes/file?.md": "reserved character",
        "research-output/notes/file.": "trailing dot",
        "research-output/notes/file ": "trailing space",
        "research-output/notes/CON": "reserved device",
        "research-output/notes/con.txt": "reserved device with extension",
        "research-output/notes/COM¹.log": "reserved superscript device",
        "research-output/notes/" + chr(31) + "file.md": "control character",
    }
    for raw, label in invalid_portable_paths.items():
        canonical, _detail = _portable_relative_path(raw)
        if canonical is not None:
            failures.append(f"portable path validator accepted {label}: {raw!r}")
    if not _is_safe_relative_path(
        ".", allow_current_dir=True
    ) or _is_safe_relative_path("."):
        failures.append("only workspace_dir may use the current-directory sentinel")

    # Sub-test 53: every output tree has one portable, case-insensitive owner.
    output_collision_cases: dict[str, Any] = {
        "case-insensitive alias": lambda p: p["tasks"][1].__setitem__(
            "outputs", ["research-output\\NOTES\\A.MD"]
        ),
        "ancestor/descendant across tasks": lambda p: p["tasks"][0].__setitem__(
            "outputs", ["research-output/notes"]
        ),
        "ancestor/descendant within one task": lambda p: p["tasks"][0][
            "outputs"
        ].append("research-output/notes/a.md/child.md"),
    }
    for label, mutate in output_collision_cases.items():
        colliding = _make_minimal_plan()
        mutate(colliding)
        collision_errors = validate_schema(colliding)
        if not any(
            "overlaps output tree" in error and "output ownership" in error
            for error in collision_errors
        ):
            failures.append(f"schema accepted {label} output ownership collision")

    # Sub-test 54: parallel dispatch blocks portable aliases and nested trees.
    running_collision_cases = (
        (
            "research-output/notes/A.md",
            "research-output/NOTES/a.MD",
            "case-insensitive alias",
        ),
        (
            "research-output/notes/bundle",
            "research-output/NOTES/bundle/child.md",
            "running ancestor",
        ),
        (
            "research-output/notes/bundle/child.md",
            "research-output/NOTES/BUNDLE",
            "running descendant",
        ),
    )
    for running_output, candidate_output, label in running_collision_cases:
        colliding = _make_minimal_plan()
        colliding["tasks"][0]["status"] = "running"
        colliding["tasks"][0]["outputs"] = [running_output]
        colliding["tasks"][1]["outputs"] = [candidate_output]
        if "B" in parallelizable_tasks(colliding):
            failures.append(f"parallel dispatch accepted {label} output collision")
    colliding = _make_minimal_plan()
    colliding["tasks"][0]["outputs"] = ["research-output/notes/bundle"]
    colliding["tasks"][1]["outputs"] = [
        "research-output/NOTES/bundle/child.md"
    ]
    if parallelizable_tasks(colliding) != ["A"]:
        failures.append(
            "parallel dispatch must reserve selected output trees against later tasks"
        )

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1
    print("OK: research_plan self-test passed (54 sub-tests).")
    return 0


def cmd_self_test(_args: argparse.Namespace) -> int:
    return _self_test()


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="research_plan",
        description="Research-plan manager for the D Research context-safe protocol.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="create a generic schema-2.0 draft plan workspace")
    sp.add_argument("--out", default=None)
    sp.add_argument(
        "--workspace",
        default=None,
        help="workspace directory to scaffold; plan defaults to <workspace>/research-plan.json",
    )
    sp.add_argument(
        "--slug", default="research", help="slug used for auto workspace names"
    )
    sp.add_argument(
        "--title",
        default=None,
        help="human title for the draft plan (default: Research plan: <slug>)",
    )
    sp.add_argument(
        "--config",
        default=None,
        help="optional research.config.json path for auto workspace defaults",
    )
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser(
        "migrate",
        help="upgrade a v1 research plan to schema 2.0 (revokes approval)",
    )
    sp.add_argument("--file", required=True, help="source plan JSON")
    sp.add_argument("--out", default=None, help="output path (required unless --in-place)")
    sp.add_argument(
        "--in-place",
        action="store_true",
        help="overwrite source after writing a .bak backup",
    )
    sp.set_defaults(func=cmd_migrate)

    sp = sub.add_parser("check", help="validate schema + dep graph + gate refs")
    sp.add_argument("--file", default="research-plan.json")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("status", help="print one-line status per task")
    sp.add_argument("--file", default="research-plan.json")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser(
        "parallelizable",
        help="print task ids that are ready to dispatch right now",
    )
    sp.add_argument("--file", default="research-plan.json")
    sp.set_defaults(func=cmd_parallelizable)

    sp = sub.add_parser("mark", help="set a task's status")
    sp.add_argument("--file", default="research-plan.json")
    sp.add_argument("--id", required=True)
    sp.add_argument("--status", required=True)
    sp.set_defaults(func=cmd_mark)

    sp = sub.add_parser("block", help="set status=blocked AND record a reason")
    sp.add_argument("--file", default="research-plan.json")
    sp.add_argument("--id", required=True)
    sp.add_argument("--reason", required=True)
    sp.set_defaults(func=cmd_block)

    sp = sub.add_parser("add-task", help="append a new task row")
    sp.add_argument("--file", default="research-plan.json")
    sp.add_argument("--id", required=True)
    sp.add_argument("--description", required=True)
    sp.add_argument("--owner", default="main")
    sp.add_argument(
        "--phase",
        default="research",
        choices=sorted(VALID_PHASE),
        help="task phase: research (default) or synthesis",
    )
    sp.add_argument("--depends-on", nargs="*", default=[])
    sp.add_argument("--parallel-safe", action="store_true")
    sp.add_argument("--inputs", nargs="*", default=[])
    sp.add_argument("--outputs", nargs="+", required=True)
    sp.set_defaults(func=cmd_add_task)

    sp = sub.add_parser("render", help="write a human-readable PLAN.md")
    sp.add_argument("--file", default="research-plan.json")
    sp.add_argument("--out", default=None)
    sp.set_defaults(func=cmd_render)

    sp = sub.add_parser("approve", help="record approval before execution")
    sp.add_argument("--file", default="research-plan.json")
    sp.add_argument("--by", default=None)
    sp.add_argument("--notes", default=None)
    sp.add_argument(
        "--allow-unattended",
        action="store_true",
        help="explicitly bypass human review and record agent-self-approved",
    )
    sp.set_defaults(func=cmd_approve)

    sp = sub.add_parser("revoke", help="clear plan approval")
    sp.add_argument("--file", default="research-plan.json")
    sp.add_argument("--reason", default=None)
    sp.set_defaults(func=cmd_revoke)

    sp = sub.add_parser(
        "configure-execution",
        help="annotate tasks with context budgets and subagent slot assignments",
    )
    sp.add_argument("--file", default="research-plan.json")
    sp.add_argument("--config", default=None)
    sp.set_defaults(func=cmd_configure_execution)

    sp = sub.add_parser(
        "set-execution",
        help="override one task's main/subagent slot, thread count, or context budget",
    )
    sp.add_argument("--file", default="research-plan.json")
    sp.add_argument("--id", required=True)
    sp.add_argument("--agent", choices=["main", "subagent"], required=True)
    sp.add_argument("--slot", default=None)
    sp.add_argument("--parallel-threads", type=int, default=None)
    sp.add_argument("--max-parallel-threads", type=int, default=None)
    sp.add_argument("--context-length", type=int, default=None)
    sp.add_argument("--context-budget", type=int, default=None)
    sp.set_defaults(func=cmd_set_execution)

    sp = sub.add_parser("gate", help="run a named gate's assertions")
    sp.add_argument("--file", default="research-plan.json")
    sp.add_argument("--gate", required=True)
    sp.set_defaults(func=cmd_gate)

    sp = sub.add_parser("self-test", help="run offline self-test")
    sp.set_defaults(func=cmd_self_test)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
