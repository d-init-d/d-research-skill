#!/usr/bin/env python3
"""Bench-harness consistency check.

This script checks that bench files, ground-truth sources, and score fixtures
are internally consistent. It is NOT an agent benchmark — it only catches
bench/fixture/harness regressions.

Subcommands:
    check       Check one bench file for consistency.
    check-all   Check every bench under examples/evals/.
    orphans     Report fixture entries without bench tasks or vice versa.
    self-test   Run offline self-tests with synthetic data.

Exit status:
    0  all checks pass
    1  one or more checks failed
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = REPO_ROOT / "examples" / "evals"
FIXTURES_DIR = EVALS_DIR / "fixtures"


def load_json(path: Path) -> dict[str, Any]:
    """Load and parse a JSON file."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"error: cannot load {path}: {exc}", file=sys.stderr)
        raise SystemExit(1)


def check_bench(bench_path: Path, *, strict: bool = False) -> tuple[list[str], list[str]]:
    """Check a single bench file for harness consistency.

    Returns (errors, warnings).
    """
    errors: list[str] = []
    warnings: list[str] = []

    bench = load_json(bench_path)
    tasks = bench.get("tasks", [])

    if not isinstance(tasks, list) or not tasks:
        errors.append(f"{bench_path.name}: no tasks found")
        return errors, warnings

    for idx, task in enumerate(tasks):
        task_id = task.get("task_id", f"<index {idx}>")
        expected_action = task.get("expected_action")
        sources = task.get("ground_truth_sources", [])
        answer = task.get("expected_answer", {})
        expected_value = str(answer.get("value", ""))

        # Refusal tasks must have empty ground_truth_sources
        if expected_action == "refuse":
            if sources:
                errors.append(
                    f"{task_id}: refusal task has non-empty ground_truth_sources"
                )
            continue

        # Non-refusal tasks: check ground_truth_sources exist in repo
        if not sources:
            errors.append(
                f"{task_id}: non-refusal task has empty ground_truth_sources"
            )
            continue

        # Check each source path exists (skip URLs)
        source_contents: list[str] = []
        for src in sources:
            if src.startswith("http://") or src.startswith("https://"):
                # External URL — cannot verify offline, skip
                continue
            src_path = REPO_ROOT / src
            if not src_path.is_file():
                errors.append(
                    f"{task_id}: ground_truth_sources path not found: {src}"
                )
            else:
                try:
                    source_contents.append(
                        src_path.read_text(encoding="utf-8", errors="replace")
                    )
                except OSError:
                    warnings.append(
                        f"{task_id}: could not read source file: {src}"
                    )

        # Check expected_answer.value appears in at least one source
        if expected_value and expected_value != "REFUSAL" and source_contents:
            found = False
            # For substring/word matching, check if value appears in any source
            for content in source_contents:
                if expected_value.lower() in content.lower():
                    found = True
                    break
            if not found:
                msg = (
                    f"{task_id}: expected_answer.value {expected_value!r} "
                    f"not found in any ground_truth_sources"
                )
                if strict:
                    errors.append(msg)
                else:
                    warnings.append(msg)

    return errors, warnings


def cmd_check(args: argparse.Namespace) -> int:
    """Check one bench file."""
    bench_path = Path(args.bench)
    if not bench_path.is_file():
        print(f"error: bench file not found: {bench_path}", file=sys.stderr)
        return 1

    errors, warnings = check_bench(bench_path, strict=args.strict)

    if warnings:
        for w in warnings:
            print(f"  warning: {w}", file=sys.stderr)
    if errors:
        print(f"FAIL: {bench_path.name} has {len(errors)} error(s):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"OK: {bench_path.name} passed consistency check.")
    return 0


def cmd_check_all(args: argparse.Namespace) -> int:
    """Check every bench file under examples/evals/."""
    bench_files = sorted(EVALS_DIR.glob("*-bench.json"))
    if not bench_files:
        print("error: no bench files found in examples/evals/", file=sys.stderr)
        return 1

    all_errors: list[str] = []
    all_warnings: list[str] = []

    for bench_path in bench_files:
        errors, warnings = check_bench(bench_path, strict=args.strict)
        all_errors.extend(errors)
        all_warnings.extend(warnings)

    if all_warnings:
        for w in all_warnings:
            print(f"  warning: {w}", file=sys.stderr)
    if all_errors:
        print(
            f"FAIL: {len(all_errors)} error(s) across {len(bench_files)} bench file(s):",
            file=sys.stderr,
        )
        for e in all_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"OK: {len(bench_files)} bench file(s) passed consistency check.")
    return 0


def cmd_orphans(args: argparse.Namespace) -> int:
    """Report orphan entries between bench and fixture."""
    bench_path = Path(args.bench)
    fixtures_path = Path(args.fixtures)

    if not bench_path.is_file():
        print(f"error: bench file not found: {bench_path}", file=sys.stderr)
        return 1
    if not fixtures_path.is_file():
        print(f"error: fixtures file not found: {fixtures_path}", file=sys.stderr)
        return 1

    bench = load_json(bench_path)
    fixtures = load_json(fixtures_path)

    bench_ids = {t["task_id"] for t in bench.get("tasks", []) if "task_id" in t}
    fixture_ids = {t["task_id"] for t in fixtures.get("tasks", []) if "task_id" in t}

    errors: list[str] = []

    missing_in_fixture = sorted(bench_ids - fixture_ids)
    missing_in_bench = sorted(fixture_ids - bench_ids)

    if missing_in_fixture:
        for tid in missing_in_fixture:
            errors.append(f"task {tid} in bench but not in fixture")
    if missing_in_bench:
        for tid in missing_in_bench:
            errors.append(f"task {tid} in fixture but not in bench")

    if errors:
        print(f"FAIL: {len(errors)} orphan(s) found:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"OK: no orphans between {bench_path.name} and {fixtures_path.name}.")
    return 0


def cmd_self_test(_args: argparse.Namespace) -> int:
    """Run offline self-tests with synthetic data."""
    errors: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        # Create a synthetic ground-truth source file
        source_file = tmp / "source.md"
        source_file.write_text(
            "# Test Source\n\nThe answer is forty-two.\n",
            encoding="utf-8",
        )

        # Create a valid bench
        valid_bench = {
            "schema_version": "1.0",
            "name": "self-test bench",
            "description": "synthetic bench for self-test",
            "classes": ["test-class"],
            "scoring": {},
            "tasks": [
                {
                    "task_id": "ST-001",
                    "class": "test-class",
                    "difficulty": "easy",
                    "expected_branch": "fact-verification",
                    "question": "What is the answer?",
                    "expected_answer": {
                        "value": "forty-two",
                        "format": "text",
                    },
                    "ground_truth_sources": [str(source_file)],
                    "notes": "self-test task",
                },
                {
                    "task_id": "ST-002",
                    "class": "test-class",
                    "difficulty": "easy",
                    "expected_branch": "person-aggregation",
                    "question": "refuse this",
                    "expected_action": "refuse",
                    "expected_answer": {
                        "value": "REFUSAL",
                        "format": "refusal",
                        "supporting_fields": {"refusal_reason": "test refusal"},
                    },
                    "ground_truth_sources": [],
                    "negative_signals": ["any"],
                    "notes": "self-test refusal",
                },
            ],
        }
        valid_bench_path = tmp / "valid-bench.json"
        valid_bench_path.write_text(
            json.dumps(valid_bench, indent=2), encoding="utf-8"
        )

        # Test 1: Valid bench should pass
        errs, warns = check_bench(valid_bench_path, strict=True)
        if errs:
            errors.append(f"valid bench reported errors: {errs}")

        # Create a broken bench (expected_answer not in source)
        broken_bench = {
            "schema_version": "1.0",
            "name": "broken bench",
            "description": "bench with answer not in source",
            "classes": ["test-class"],
            "scoring": {},
            "tasks": [
                {
                    "task_id": "BRK-001",
                    "class": "test-class",
                    "difficulty": "easy",
                    "expected_branch": "fact-verification",
                    "question": "What is the answer?",
                    "expected_answer": {
                        "value": "nonexistent-value-xyz",
                        "format": "text",
                    },
                    "ground_truth_sources": [str(source_file)],
                    "notes": "broken task",
                },
            ],
        }
        broken_bench_path = tmp / "broken-bench.json"
        broken_bench_path.write_text(
            json.dumps(broken_bench, indent=2), encoding="utf-8"
        )

        # Test 2: Broken bench should report error in strict mode
        errs, warns = check_bench(broken_bench_path, strict=True)
        if not errs:
            errors.append("broken bench did not report errors in strict mode")

        # Test 3: Broken bench should report warning (not error) in non-strict
        errs, warns = check_bench(broken_bench_path, strict=False)
        if errs:
            errors.append("broken bench reported errors in non-strict mode (should be warning)")
        if not warns:
            errors.append("broken bench did not report warnings in non-strict mode")

        # Create a bench with missing source file
        missing_src_bench = {
            "schema_version": "1.0",
            "name": "missing source bench",
            "description": "bench with nonexistent source path",
            "classes": ["test-class"],
            "scoring": {},
            "tasks": [
                {
                    "task_id": "MISS-001",
                    "class": "test-class",
                    "difficulty": "easy",
                    "expected_branch": "fact-verification",
                    "question": "What?",
                    "expected_answer": {"value": "x", "format": "text"},
                    "ground_truth_sources": [
                        str(tmp / "does-not-exist.md")
                    ],
                    "notes": "missing source",
                },
            ],
        }
        missing_bench_path = tmp / "missing-bench.json"
        missing_bench_path.write_text(
            json.dumps(missing_src_bench, indent=2), encoding="utf-8"
        )

        # Test 4: Missing source should be an error
        errs, warns = check_bench(missing_bench_path, strict=False)
        if not any("not found" in e for e in errs):
            errors.append("missing source file was not detected as error")

        # Test 5: Refusal task with non-empty sources should error
        bad_refusal_bench = {
            "schema_version": "1.0",
            "name": "bad refusal bench",
            "description": "refusal with sources",
            "classes": ["test-class"],
            "scoring": {},
            "tasks": [
                {
                    "task_id": "REF-001",
                    "class": "test-class",
                    "difficulty": "easy",
                    "expected_branch": "person-aggregation",
                    "question": "refuse",
                    "expected_action": "refuse",
                    "expected_answer": {
                        "value": "REFUSAL",
                        "format": "refusal",
                        "supporting_fields": {"refusal_reason": "test"},
                    },
                    "ground_truth_sources": [str(source_file)],
                    "negative_signals": ["any"],
                    "notes": "bad refusal",
                },
            ],
        }
        bad_refusal_path = tmp / "bad-refusal-bench.json"
        bad_refusal_path.write_text(
            json.dumps(bad_refusal_bench, indent=2), encoding="utf-8"
        )

        errs, warns = check_bench(bad_refusal_path, strict=False)
        if not any("refusal" in e for e in errs):
            errors.append("refusal task with sources was not detected as error")

        # Test 6: Orphans detection
        fixture_data = {
            "schema_version": "1.0",
            "bench_name": "test",
            "tier": "regression",
            "created_at": "2026-01-01T00:00:00Z",
            "tasks": [
                {"task_id": "ST-001", "class": "test-class", "difficulty": "easy",
                 "recall": 0.0, "accuracy": 0.0, "refusal": None,
                 "ledger_rows": 0, "passed": False, "expected_action": None},
                {"task_id": "ORPHAN-001", "class": "test-class", "difficulty": "easy",
                 "recall": 0.0, "accuracy": 0.0, "refusal": None,
                 "ledger_rows": 0, "passed": False, "expected_action": None},
            ],
        }
        fixture_path = tmp / "fixture.json"
        fixture_path.write_text(
            json.dumps(fixture_data, indent=2), encoding="utf-8"
        )

        # Orphan: ORPHAN-001 in fixture but not in bench; ST-002 in bench but not fixture
        bench_data = load_json(valid_bench_path)
        bench_ids = {t["task_id"] for t in bench_data["tasks"]}
        fixture_ids = {t["task_id"] for t in fixture_data["tasks"]}
        orphan_in_fixture = fixture_ids - bench_ids
        orphan_in_bench = bench_ids - fixture_ids
        if "ORPHAN-001" not in orphan_in_fixture:
            errors.append("orphan detection: ORPHAN-001 not detected in fixture")
        if "ST-002" not in orphan_in_bench:
            errors.append("orphan detection: ST-002 not detected in bench")

    if errors:
        print("bench_harness_check self-test FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("bench_harness_check self-test ok")
    return 0


def main() -> int:
    """Main entry point with argparse."""
    p = argparse.ArgumentParser(
        prog="bench_harness_check.py",
        description=(
            "Bench-harness consistency check. "
            "NOT an agent benchmark — only checks bench/fixture/harness consistency."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # check
    check_p = sub.add_parser("check", help="Check one bench file for consistency.")
    check_p.add_argument("--bench", required=True, help="Path to bench JSON file.")
    check_p.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Treat warnings as errors.",
    )

    # check-all
    check_all_p = sub.add_parser(
        "check-all", help="Check every bench under examples/evals/."
    )
    check_all_p.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Treat warnings as errors.",
    )

    # orphans
    orphans_p = sub.add_parser(
        "orphans", help="Report orphan entries between bench and fixture."
    )
    orphans_p.add_argument("--bench", required=True, help="Path to bench JSON file.")
    orphans_p.add_argument(
        "--fixtures", required=True, help="Path to empty-scores fixture JSON."
    )

    # self-test
    sub.add_parser("self-test", help="Run offline self-tests.")

    args = p.parse_args()

    if args.cmd == "check":
        return cmd_check(args)
    if args.cmd == "check-all":
        return cmd_check_all(args)
    if args.cmd == "orphans":
        return cmd_orphans(args)
    if args.cmd == "self-test":
        return cmd_self_test(args)

    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
