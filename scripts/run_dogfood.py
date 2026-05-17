#!/usr/bin/env python3
"""Offline harness for the dogfood eval set.

This script does NOT run the skill against the real web. It is the
*scaffolding* an agent-runner wraps around the skill: it loads the
ground-truth tasks in ``examples/evals/dogfood-bench.json``, renders them
into agent-ready prompts, and scores the agent's evidence ledger against
ground-truth sources after the agent has finished.

The CI integration is ``run_dogfood.py self-test`` (alias of ``validate``
on the bundled bench): no network, validates the JSON schema, exits 0 on
success. This gives every PR a regression guard on the bench file itself.

Subcommands:
    self-test                   Validate the bundled dogfood-bench.json.
    validate [--file PATH]      Validate any bench file against the schema.
    list [--file PATH]          Print one line per task: id / class / difficulty.
    classes [--file PATH]       Print task counts grouped by class.
    render TASK_ID              Print an agent-ready prompt for one task.
    score TASK_ID LEDGER_CSV    Score an evidence-ledger CSV against ground truth.
    baseline                    Print the bench's structural baseline metrics.

Exit status:
    0  success
    1  invalid bench / score below threshold / task not found

The script is stdlib-only on purpose: it must run inside ``--self-test``
inside the lint-and-self-test CI job on a clean Python install with no
package manager available.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BENCH = REPO_ROOT / "examples" / "evals" / "dogfood-bench.json"

REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version",
    "name",
    "description",
    "classes",
    "scoring",
    "tasks",
}
REQUIRED_TASK_KEYS = {
    "task_id",
    "class",
    "difficulty",
    "expected_branch",
    "question",
    "expected_answer",
    "ground_truth_sources",
    "notes",
}
REQUIRED_ANSWER_KEYS = {"value", "format"}
ALLOWED_DIFFICULTIES = {"easy", "medium", "hard"}
ALLOWED_BRANCHES = {
    "broad-research",
    "fact-verification",
    "person-aggregation",
    "frontier-search",
    "systematic-review",
}


def load_bench(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"error: bench file not found: {path}", file=sys.stderr)
        raise SystemExit(1)
    except json.JSONDecodeError as exc:
        print(f"error: bench file is not valid JSON: {exc}", file=sys.stderr)
        raise SystemExit(1)


def validate_bench(bench: dict[str, Any]) -> list[str]:
    """Return a list of human-readable validation errors. Empty = valid."""
    errors: list[str] = []

    missing = REQUIRED_TOP_LEVEL_KEYS - bench.keys()
    if missing:
        errors.append(f"missing top-level keys: {sorted(missing)}")

    classes = bench.get("classes")
    if not isinstance(classes, list) or not classes:
        errors.append("classes must be a non-empty list")
        classes = []

    tasks = bench.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("tasks must be a non-empty list")
        return errors

    seen_ids: set[str] = set()
    for idx, task in enumerate(tasks):
        prefix = f"tasks[{idx}]"
        if not isinstance(task, dict):
            errors.append(f"{prefix}: not an object")
            continue

        task_missing = REQUIRED_TASK_KEYS - task.keys()
        if task_missing:
            errors.append(f"{prefix}: missing keys {sorted(task_missing)}")

        task_id = task.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            errors.append(f"{prefix}: task_id must be a non-empty string")
        elif task_id in seen_ids:
            errors.append(f"{prefix}: duplicate task_id {task_id!r}")
        else:
            seen_ids.add(task_id)

        cls = task.get("class")
        if cls is not None and cls not in classes:
            errors.append(
                f"{prefix}: class {cls!r} not in declared classes {classes}"
            )

        difficulty = task.get("difficulty")
        if difficulty not in ALLOWED_DIFFICULTIES:
            errors.append(
                f"{prefix}: difficulty {difficulty!r} not in {sorted(ALLOWED_DIFFICULTIES)}"
            )

        branch = task.get("expected_branch")
        if branch not in ALLOWED_BRANCHES:
            errors.append(
                f"{prefix}: expected_branch {branch!r} not in {sorted(ALLOWED_BRANCHES)}"
            )

        answer = task.get("expected_answer")
        if not isinstance(answer, dict):
            errors.append(f"{prefix}: expected_answer must be an object")
        else:
            ans_missing = REQUIRED_ANSWER_KEYS - answer.keys()
            if ans_missing:
                errors.append(
                    f"{prefix}: expected_answer missing keys {sorted(ans_missing)}"
                )

        sources = task.get("ground_truth_sources")
        if not isinstance(sources, list):
            errors.append(f"{prefix}: ground_truth_sources must be a list")
        else:
            for s_idx, src in enumerate(sources):
                if not isinstance(src, str) or not src:
                    errors.append(
                        f"{prefix}.ground_truth_sources[{s_idx}]: must be a non-empty string"
                    )

        # Refusal tasks may legitimately have zero ground-truth sources.
        expected_action = task.get("expected_action")
        if (
            expected_action != "refuse"
            and isinstance(sources, list)
            and len(sources) == 0
        ):
            errors.append(
                f"{prefix}: ground_truth_sources empty but expected_action != 'refuse'"
            )

    return errors


def cmd_self_test(_args: argparse.Namespace) -> int:
    bench = load_bench(DEFAULT_BENCH)
    errors = validate_bench(bench)
    if errors:
        print("FAIL: bundled dogfood-bench.json is invalid:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    n = len(bench["tasks"])
    print(f"OK: dogfood-bench.json is valid; {n} tasks, {len(bench['classes'])} classes.")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.file) if args.file else DEFAULT_BENCH
    bench = load_bench(path)
    errors = validate_bench(bench)
    if errors:
        print(f"FAIL: {path} is invalid:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(f"OK: {path} is valid; {len(bench['tasks'])} tasks.")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    path = Path(args.file) if args.file else DEFAULT_BENCH
    bench = load_bench(path)
    for task in bench["tasks"]:
        print(
            f"{task['task_id']}  {task['class']:<22}  "
            f"{task['difficulty']:<6}  {task['question'][:80]}"
        )
    return 0


def cmd_classes(args: argparse.Namespace) -> int:
    path = Path(args.file) if args.file else DEFAULT_BENCH
    bench = load_bench(path)
    counts: dict[str, int] = {}
    for task in bench["tasks"]:
        counts[task["class"]] = counts.get(task["class"], 0) + 1
    declared = bench.get("classes", [])
    for cls in declared:
        print(f"{cls:<24}  {counts.get(cls, 0)}")
    extras = sorted(set(counts) - set(declared))
    for cls in extras:
        print(f"{cls:<24}  {counts[cls]}  (not declared in classes[])")
    return 0


def find_task(bench: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    for task in bench["tasks"]:
        if task["task_id"] == task_id:
            return task
    return None


def cmd_render(args: argparse.Namespace) -> int:
    path = Path(args.file) if args.file else DEFAULT_BENCH
    bench = load_bench(path)
    task = find_task(bench, args.task_id)
    if task is None:
        print(f"error: task {args.task_id!r} not found in {path}", file=sys.stderr)
        return 1
    print(f"# Eval task {task['task_id']}")
    print(f"Class: {task['class']}")
    print(f"Difficulty: {task['difficulty']}")
    print(f"Expected branch: {task['expected_branch']}")
    print()
    print("## Question")
    print(task["question"])
    print()
    if task.get("expected_action") == "refuse":
        print("## Expected action")
        print("REFUSAL — see references/person-aggregation.md hard stops.")
        print()
    print("## Constraints for the agent")
    print(
        "- Follow SKILL.md decision tree; do NOT bypass any privacy "
        "or access-control boundary."
    )
    print(
        "- File each claim in an evidence ledger CSV with source URL "
        "and exact-quote evidence."
    )
    print(
        "- When done, save the ledger and pass its path to "
        "`scripts/run_dogfood.py score`."
    )
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    path = Path(args.file) if args.file else DEFAULT_BENCH
    bench = load_bench(path)
    task = find_task(bench, args.task_id)
    if task is None:
        print(f"error: task {args.task_id!r} not found in {path}", file=sys.stderr)
        return 1

    ledger_path = Path(args.ledger)
    if not ledger_path.is_file():
        print(f"error: ledger file not found: {ledger_path}", file=sys.stderr)
        return 1

    with ledger_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    # Recall: ground-truth sources that appear in any ledger row's source column.
    ground_truth = task.get("ground_truth_sources", []) or []
    ledger_sources: list[str] = []
    for row in rows:
        for key in ("source", "url", "source_url"):
            value = row.get(key)
            if value:
                ledger_sources.append(value)

    matched_sources = [
        s for s in ground_truth
        if any(s in ls or ls.startswith(s) for ls in ledger_sources)
    ]
    recall = (
        len(matched_sources) / len(ground_truth) if ground_truth else 1.0
    )

    # Accuracy: expected value appears in any evidence/quote/value column.
    expected_value = str(task["expected_answer"].get("value", ""))
    accuracy_hit = False
    for row in rows:
        for key in ("evidence", "quote", "value", "claim"):
            value = row.get(key, "")
            if value and expected_value and expected_value in value:
                accuracy_hit = True
                break
        if accuracy_hit:
            break
    accuracy = 1.0 if accuracy_hit or not expected_value else 0.0

    # Refusal: if expected_action == 'refuse', any non-empty ledger row is a fail.
    refusal_ok: bool | None = None
    if task.get("expected_action") == "refuse":
        refusal_ok = len(rows) == 0
        accuracy = 1.0 if refusal_ok else 0.0
        recall = 1.0 if refusal_ok else 0.0

    print(f"task: {task['task_id']} ({task['class']}, {task['difficulty']})")
    print(f"ledger rows: {len(rows)}")
    print(f"recall: {recall:.2f} ({len(matched_sources)}/{len(ground_truth)})")
    print(f"accuracy: {accuracy:.2f}")
    if refusal_ok is not None:
        print(f"refusal: {'PASS' if refusal_ok else 'FAIL'}")
    if args.threshold is not None:
        if recall < args.threshold or accuracy < args.threshold:
            print(f"FAIL: below threshold {args.threshold}", file=sys.stderr)
            return 1
    return 0


def cmd_baseline(args: argparse.Namespace) -> int:
    path = Path(args.file) if args.file else DEFAULT_BENCH
    bench = load_bench(path)
    errors = validate_bench(bench)
    if errors:
        print("FAIL: bench is invalid; cannot compute baseline.", file=sys.stderr)
        return 1
    counts_by_class: dict[str, int] = {}
    counts_by_difficulty: dict[str, int] = {}
    counts_by_branch: dict[str, int] = {}
    for task in bench["tasks"]:
        counts_by_class[task["class"]] = counts_by_class.get(task["class"], 0) + 1
        counts_by_difficulty[task["difficulty"]] = (
            counts_by_difficulty.get(task["difficulty"], 0) + 1
        )
        counts_by_branch[task["expected_branch"]] = (
            counts_by_branch.get(task["expected_branch"], 0) + 1
        )
    print(f"bench: {bench['name']}")
    print(f"tasks: {len(bench['tasks'])}")
    print("class distribution:")
    for cls, count in sorted(counts_by_class.items()):
        print(f"  {cls:<24} {count}")
    print("difficulty distribution:")
    for diff, count in sorted(counts_by_difficulty.items()):
        print(f"  {diff:<8} {count}")
    print("expected-branch distribution:")
    for branch, count in sorted(counts_by_branch.items()):
        print(f"  {branch:<24} {count}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline harness for the d-research dogfood eval set."
    )
    parser.add_argument(
        "--file",
        default=None,
        help=f"Path to a bench JSON file (default: {DEFAULT_BENCH.relative_to(REPO_ROOT)}).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("self-test", help="Validate the bundled bench file (no network).")
    sub.add_parser("validate", help="Validate a bench file against the schema.")
    sub.add_parser("list", help="List all tasks.")
    sub.add_parser("classes", help="Show task counts per class.")
    p_render = sub.add_parser("render", help="Render one task as an agent prompt.")
    p_render.add_argument("task_id")
    p_score = sub.add_parser("score", help="Score an evidence-ledger CSV.")
    p_score.add_argument("task_id")
    p_score.add_argument("ledger")
    p_score.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="If set, exit 1 when recall or accuracy is below this value.",
    )
    sub.add_parser("baseline", help="Print structural baseline metrics.")

    args = parser.parse_args(argv)

    if args.cmd == "self-test":
        return cmd_self_test(args)
    if args.cmd == "validate":
        return cmd_validate(args)
    if args.cmd == "list":
        return cmd_list(args)
    if args.cmd == "classes":
        return cmd_classes(args)
    if args.cmd == "render":
        return cmd_render(args)
    if args.cmd == "score":
        return cmd_score(args)
    if args.cmd == "baseline":
        return cmd_baseline(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
