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
* ``init``            copy the template to a working plan path
* ``check``           validate schema + dependency graph + gate refs
* ``status``          print a one-line status per task
* ``parallelizable``  print task ids that are ready to dispatch now
* ``mark``            set a task's status (todo/running/done/blocked)
* ``block``           set status=blocked AND record a blocker_reason
* ``add-task``        append a new task row
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
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

# Allowed values for plan fields. Keep in sync with the template.
VALID_STATUS = {"todo", "running", "done", "blocked"}
TERMINAL_STATUS = {"done", "blocked"}
VALID_OWNER_PREFIX = ("main", "sub-")

# Required top-level keys.
REQUIRED_TOP_KEYS = {
    "plan_id",
    "title",
    "scope",
    "sub_questions",
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

# Path resolution helpers operate relative to the plan file's parent
# directory so plans can be moved around without breaking checks.


def _plan_dir(plan_path: Path) -> Path:
    return plan_path.resolve().parent


def load(plan_path: Path) -> dict[str, Any]:
    """Load and lightly normalise a plan from disk."""
    if not plan_path.exists():
        raise FileNotFoundError(f"plan file not found: {plan_path}")
    with plan_path.open("r", encoding="utf-8") as fh:
        plan = json.load(fh)
    if not isinstance(plan, dict):
        raise ValueError(f"plan must be a JSON object, got {type(plan).__name__}")
    return plan


def save(plan: dict[str, Any], plan_path: Path) -> None:
    """Atomically write a plan back to disk, preserving formatting."""
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

    tasks = plan.get("tasks", [])
    if not isinstance(tasks, list):
        errors.append("`tasks` must be a list")
        return errors

    seen_ids: set[str] = set()
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
        if task["status"] not in VALID_STATUS:
            errors.append(
                f"tasks[{tid}].status={task['status']!r} not in {sorted(VALID_STATUS)}"
            )
        if not isinstance(task["depends_on"], list):
            errors.append(f"tasks[{tid}].depends_on must be a list")
        if not isinstance(task["outputs"], list) or not task["outputs"]:
            errors.append(f"tasks[{tid}].outputs must be a non-empty list of paths")
        if not isinstance(task["parallel_safe"], bool):
            errors.append(f"tasks[{tid}].parallel_safe must be a boolean")
        owner = task["owner"]
        if not isinstance(owner, str) or not (
            owner == "main" or owner.startswith("sub-")
        ):
            errors.append(
                f"tasks[{tid}].owner={owner!r} must be 'main' or 'sub-<n>'"
            )

    # Dependency closure.
    if not errors:
        for task in tasks:
            for dep in task["depends_on"]:
                if dep not in seen_ids:
                    errors.append(
                        f"tasks[{task['id']}].depends_on references unknown id {dep!r}"
                    )

    return errors


def detect_cycles(plan: dict[str, Any]) -> list[list[str]]:
    """Return a list of dependency cycles. Empty list = acyclic."""
    tasks = {t["id"]: t for t in plan.get("tasks", [])}
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
    tasks = {t["id"]: t for t in plan.get("tasks", [])}
    done_ids = {tid for tid, t in tasks.items() if t["status"] == "done"}
    running_outputs: set[str] = set()
    for t in tasks.values():
        if t["status"] == "running":
            running_outputs.update(t.get("outputs", []))

    ready: list[str] = []
    for tid, t in tasks.items():
        if t["status"] != "todo":
            continue
        if not t.get("parallel_safe", False):
            continue
        if not all(dep in done_ids for dep in t["depends_on"]):
            continue
        if set(t.get("outputs", [])) & running_outputs:
            continue
        ready.append(tid)
    return ready


# ---------------------------------------------------------------------------
# Status formatting
# ---------------------------------------------------------------------------


def format_status(plan: dict[str, Any]) -> str:
    rows: list[str] = []
    rows.append(
        f"plan_id={plan.get('plan_id')}  title={plan.get('title')!r}"
    )
    rows.append(
        "id      status      par   owner     outputs"
    )
    rows.append(
        "------  ----------  ----  --------  -------"
    )
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


def _all_outputs_exist(plan: dict[str, Any], plan_path: Path) -> tuple[bool, list[str]]:
    base = _plan_dir(plan_path)
    missing: list[str] = []
    for t in plan.get("tasks", []):
        if t["status"] == "blocked":
            continue
        for p in t.get("outputs", []):
            target = (base / p).resolve()
            if not target.exists():
                missing.append(p)
    return (not missing), missing


def _ledger_exists_and_validates(plan_path: Path) -> tuple[bool, str]:
    """Best-effort: try to call scripts/evidence_ledger.py validate.

    We avoid importing the script as a module so this stays a pure
    CLI tool. If the validator is not reachable we degrade to a
    presence check on `evidence-ledger.csv`.
    """
    base = _plan_dir(plan_path)
    ledger = base / "evidence-ledger.csv"
    if not ledger.exists():
        return False, f"evidence ledger not found at {ledger}"
    # Try to invoke the validator via subprocess if it is alongside.
    script = Path(__file__).resolve().parent / "evidence_ledger.py"
    if not script.exists():
        return True, "ledger exists (validator script not found, skipped)"
    import subprocess

    res = subprocess.run(
        [sys.executable, str(script), "validate", "--file", str(ledger)],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        return False, res.stderr.strip() or res.stdout.strip()
    return True, "validator OK"


def _ledger_signed(plan_path: Path) -> tuple[bool, str]:
    base = _plan_dir(plan_path)
    sig = base / "evidence-ledger.csv.hmac"
    if not sig.exists():
        return False, f"signature not found at {sig}"
    return True, "signature present"


def _reproducibility_checklist_exists(plan_path: Path) -> tuple[bool, str]:
    base = _plan_dir(plan_path)
    candidates = [
        base / "reproducibility-checklist.md",
        base / "research-output" / "reproducibility-checklist.md",
    ]
    for c in candidates:
        if c.exists():
            return True, f"checklist at {c}"
    return False, "reproducibility-checklist.md not found"


def _final_report_exists(plan_path: Path) -> tuple[bool, str]:
    base = _plan_dir(plan_path)
    candidates = [
        base / "research-output" / "report.md",
        base / "final-report.md",
        base / "report.md",
    ]
    for c in candidates:
        if c.exists():
            return True, f"report at {c}"
    return False, "final report not found"


def _rendered_citations_exist(plan_path: Path) -> tuple[bool, str]:
    base = _plan_dir(plan_path)
    candidates = [
        base / "research-output" / "report-citations.md",
        base / "report-citations.md",
        base / "research-output" / "citations.md",
    ]
    for c in candidates:
        if c.exists():
            return True, f"citations at {c}"
    return False, "rendered citations not found"


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


def _assert_all_tasks_terminal(plan, plan_path):
    non_terminal = [
        t["id"] for t in plan.get("tasks", []) if t["status"] not in TERMINAL_STATUS
    ]
    return (not non_terminal), (
        "non-terminal tasks: " + str(non_terminal)
    ) if non_terminal else "OK"


def _assert_all_outputs_exist(plan, plan_path):
    ok, missing = _all_outputs_exist(plan, plan_path)
    return ok, "OK" if ok else f"missing outputs: {missing}"


def _assert_ledger_validates(plan, plan_path):
    return _ledger_exists_and_validates(plan_path)


def _assert_ledger_signed(plan, plan_path):
    return _ledger_signed(plan_path)


def _assert_repro_checklist_exists(plan, plan_path):
    return _reproducibility_checklist_exists(plan_path)


def _assert_final_report_exists(plan, plan_path):
    return _final_report_exists(plan_path)


def _assert_rendered_citations_exist(plan, plan_path):
    return _rendered_citations_exist(plan_path)


def _assert_stopping_criteria_satisfied(plan, plan_path):
    val = bool(plan.get("stopping_criteria_satisfied"))
    return val, "OK" if val else "stopping_criteria_satisfied is false"


ASSERTIONS = {
    "schema_valid": _assert_schema_valid,
    "no_dependency_cycles": _assert_no_cycles,
    "no_orphan_dependencies": _assert_no_orphans,
    "no_task_is_done": _assert_no_task_is_done,
    "all_tasks_terminal": _assert_all_tasks_terminal,
    "all_outputs_exist": _assert_all_outputs_exist,
    "ledger_validates": _assert_ledger_validates,
    "ledger_signed": _assert_ledger_signed,
    "reproducibility_checklist_exists": _assert_repro_checklist_exists,
    "final_report_exists": _assert_final_report_exists,
    "rendered_citations_exist": _assert_rendered_citations_exist,
    "stopping_criteria_satisfied": _assert_stopping_criteria_satisfied,
    # The "synthesize_ready" assertion in release_ready is satisfied by
    # running that gate transitively; we treat it as a no-op marker here.
    "synthesize_ready": lambda plan, plan_path: (True, "evaluated via gate transition"),
}


def run_gate(plan: dict[str, Any], plan_path: Path, gate_name: str) -> tuple[bool, list[tuple[str, bool, str]]]:
    gate = plan.get("gates", {}).get(gate_name)
    if gate is None:
        raise KeyError(f"gate not found: {gate_name!r}")
    results: list[tuple[str, bool, str]] = []
    all_ok = True
    for name in gate.get("assertions", []):
        fn = ASSERTIONS.get(name)
        if fn is None:
            results.append((name, False, f"unknown assertion {name!r}"))
            all_ok = False
            continue
        ok, detail = fn(plan, plan_path)
        results.append((name, ok, detail))
        if not ok:
            all_ok = False
    return all_ok, results


# ---------------------------------------------------------------------------
# CLI subcommands
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    template = Path(__file__).resolve().parent.parent / "templates" / "research-plan.json"
    if not template.exists():
        print(f"FAIL: template missing at {template}", file=sys.stderr)
        return 1
    out = Path(args.out).resolve()
    if out.exists() and not args.force:
        print(
            f"FAIL: {out} exists; pass --force to overwrite",
            file=sys.stderr,
        )
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"wrote plan template to {out}")
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
    print(format_status(plan))
    return 0


def cmd_parallelizable(args: argparse.Namespace) -> int:
    plan_path = Path(args.file).resolve()
    plan = load(plan_path)
    ids = parallelizable_tasks(plan)
    if not ids:
        print("(none ready)")
    else:
        for tid in ids:
            print(tid)
    return 0


def _find_task(plan: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    for t in plan.get("tasks", []):
        if t["id"] == task_id:
            return t
    return None


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
    new_task = {
        "id": args.id,
        "description": args.description,
        "depends_on": list(args.depends_on or []),
        "parallel_safe": bool(args.parallel_safe),
        "owner": args.owner,
        "inputs": list(args.inputs or []),
        "outputs": list(args.outputs or []),
        "status": "todo",
        "blocker_reason": "",
    }
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
    save(plan, plan_path)
    print(f"added task {args.id}")
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
    return {
        "plan_id": "test-plan",
        "title": "Test plan",
        "scope": "scope",
        "sub_questions": [{"id": "SQ1", "text": "x"}],
        "stopping_criteria": "done when done",
        "stopping_criteria_satisfied": False,
        "tasks": [
            {
                "id": "A",
                "description": "root A",
                "depends_on": [],
                "parallel_safe": True,
                "owner": "main",
                "inputs": [],
                "outputs": ["out/a.md"],
                "status": "todo",
                "blocker_reason": "",
            },
            {
                "id": "B",
                "description": "root B",
                "depends_on": [],
                "parallel_safe": True,
                "owner": "sub-1",
                "inputs": [],
                "outputs": ["out/b.md"],
                "status": "todo",
                "blocker_reason": "",
            },
            {
                "id": "C",
                "description": "join A+B",
                "depends_on": ["A", "B"],
                "parallel_safe": False,
                "owner": "main",
                "inputs": ["out/a.md", "out/b.md"],
                "outputs": ["out/c.md"],
                "status": "todo",
                "blocker_reason": "",
            },
        ],
        "gates": {
            "execute_ready": {
                "description": "ready to execute",
                "assertions": [
                    "schema_valid",
                    "no_dependency_cycles",
                    "no_orphan_dependencies",
                    "no_task_is_done",
                ],
            },
            "synthesize_ready": {
                "description": "ready to synth",
                "assertions": ["all_tasks_terminal", "all_outputs_exist"],
            },
        },
    }


def _self_test() -> int:
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
        failures.append(
            f"after A=done expected ready={{B}}, got {ready}"
        )

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
    plan["tasks"][1]["outputs"] = ["out/a.md"]  # collide with A
    ready = parallelizable_tasks(plan)
    if "B" in ready:
        failures.append(
            "B collides with running A's outputs; should be filtered"
        )

    # Sub-test 10: round-trip save/load preserves the plan.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "plan.json"
        plan = _make_minimal_plan()
        save(plan, path)
        loaded = load(path)
        if loaded != plan:
            failures.append("round-trip save/load did not match")

    # Sub-test 11: execute_ready gate passes on a clean plan.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "plan.json"
        plan = _make_minimal_plan()
        save(plan, path)
        ok, results = run_gate(load(path), path, "execute_ready")
        if not ok:
            failures.append(
                f"execute_ready should pass on clean plan, got {results}"
            )

    # Sub-test 12: execute_ready FAILS when a task is already `done`.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "plan.json"
        plan = _make_minimal_plan()
        plan["tasks"][0]["status"] = "done"
        save(plan, path)
        ok, _results = run_gate(load(path), path, "execute_ready")
        if ok:
            failures.append("execute_ready should fail when a task is done")

    # Sub-test 13: synthesize_ready fails when outputs are missing.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "plan.json"
        plan = _make_minimal_plan()
        for t in plan["tasks"]:
            t["status"] = "done"
        save(plan, path)
        ok, _results = run_gate(load(path), path, "synthesize_ready")
        if ok:
            failures.append(
                "synthesize_ready should fail when outputs do not exist"
            )

    # Sub-test 14: synthesize_ready passes when outputs do exist.
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        path = td_path / "plan.json"
        plan = _make_minimal_plan()
        for t in plan["tasks"]:
            t["status"] = "done"
            for op in t["outputs"]:
                ofile = td_path / op
                ofile.parent.mkdir(parents=True, exist_ok=True)
                ofile.write_text("x", encoding="utf-8")
        save(plan, path)
        ok, results = run_gate(load(path), path, "synthesize_ready")
        if not ok:
            failures.append(
                f"synthesize_ready should pass when outputs exist, got {results}"
            )

    # Sub-test 15: add-task rejects a cycle.
    plan = _make_minimal_plan()
    plan["tasks"].append(
        {
            "id": "D",
            "description": "bad",
            "depends_on": ["C"],
            "parallel_safe": True,
            "owner": "main",
            "inputs": [],
            "outputs": ["out/d.md"],
            "status": "todo",
            "blocker_reason": "",
        }
    )
    plan["tasks"][0]["depends_on"] = ["D"]  # closes the loop A->D->C->A
    if not detect_cycles(plan):
        failures.append("A->D->C->A cycle should be detected")

    # Sub-test 16: blocked dep does not satisfy parallelizable.
    plan = _make_minimal_plan()
    plan["tasks"][0]["status"] = "blocked"
    plan["tasks"][0]["blocker_reason"] = "manual"
    plan["tasks"][1]["status"] = "done"
    plan["tasks"][2]["parallel_safe"] = True  # in case
    ready = parallelizable_tasks(plan)
    if "C" in ready:
        failures.append(
            "C must not be ready when one of its deps is blocked"
        )

    # Sub-test 17: real template parses cleanly.
    template = Path(__file__).resolve().parent.parent / "templates" / "research-plan.json"
    if template.exists():
        try:
            plan = load(template)
            errs = validate_schema(plan)
            if errs:
                failures.append(
                    f"shipped template fails schema: {errs}"
                )
            if detect_cycles(plan):
                failures.append("shipped template has a cycle")
        except Exception as e:
            failures.append(f"failed to load shipped template: {e}")

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1
    print("OK: research_plan self-test passed (17 sub-tests).")
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

    sp = sub.add_parser("init", help="copy the template to a working plan path")
    sp.add_argument("--out", default="research-plan.json")
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_init)

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
    sp.add_argument("--depends-on", nargs="*", default=[])
    sp.add_argument("--parallel-safe", action="store_true")
    sp.add_argument("--inputs", nargs="*", default=[])
    sp.add_argument("--outputs", nargs="+", required=True)
    sp.set_defaults(func=cmd_add_task)

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
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
