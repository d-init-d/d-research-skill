#!/usr/bin/env python3
"""Append local run metadata to a JSONL file.

Captures a single record per invocation:
  - ``timestamp``       ISO-8601 UTC
  - ``git_sha``         short SHA of HEAD if `git` is on PATH
  - ``hostname``        ``socket.gethostname()``
  - ``python_version``  ``sys.version_info`` major.minor.micro
  - ``node_version``    ``node --version`` if Node is on PATH
  - ``command``         optional free-form description / shell line
  - ``label``           optional one-word run label

Strictly local. Never uploaded. Never reads secrets. The JSONL file
chosen by ``--out`` is created if missing and appended to otherwise.

Subcommands
-----------
* ``record`` - append a record
* ``self-test`` - offline round-trip with a temp directory

Privacy
-------
This is process-level metadata. It does **not** capture environment
variables, command-line arguments of other processes, file contents, or
user identity beyond ``socket.gethostname()``. If your hostname is
sensitive, set ``--hostname`` or ``D_RESEARCH_RUN_HOSTNAME`` to a label
of your choice.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any


def _git_short_sha(repo: Path | None = None) -> str:
    """Return the short SHA of HEAD or empty string."""
    try:
        kwargs: dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
            "timeout": 5,
            "check": False,
        }
        if repo is not None:
            kwargs["cwd"] = str(repo)
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], **kwargs)
        if r.returncode == 0:
            return r.stdout.decode("utf-8", errors="replace").strip()
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        pass
    return ""


def _node_version() -> str:
    try:
        r = subprocess.run(
            ["node", "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        if r.returncode == 0:
            return r.stdout.decode("utf-8", errors="replace").strip()
    except (FileNotFoundError, subprocess.SubprocessError, OSError):
        pass
    return ""


def _python_version() -> str:
    info = sys.version_info
    return f"{info.major}.{info.minor}.{info.micro}"


def _now_utc_iso() -> str:
    return (
        _dt.datetime.now(_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_record(
    *,
    command: str = "",
    label: str = "",
    hostname: str | None = None,
    repo: Path | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Return the record dict that ``record`` would write."""
    if hostname is None:
        hostname = (
            os.environ.get("D_RESEARCH_RUN_HOSTNAME", "").strip()
            or socket.gethostname()
        )
    return {
        "timestamp": now or _now_utc_iso(),
        "git_sha": _git_short_sha(repo),
        "hostname": hostname,
        "python_version": _python_version(),
        "node_version": _node_version(),
        "command": command,
        "label": label,
    }


def append_record(out: Path, record: dict[str, Any]) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        f.write("\n")


def cmd_record(args: argparse.Namespace) -> int:
    record = build_record(
        command=args.command or "",
        label=args.label or "",
        hostname=args.hostname,
        repo=Path(args.repo).resolve() if args.repo else None,
    )
    out = Path(args.out)
    append_record(out, record)
    if args.print:
        print(json.dumps(record, ensure_ascii=False, sort_keys=True))
    else:
        print(f"appended run record to {out}")
    return 0


def cmd_self_test(_args: argparse.Namespace) -> int:
    import tempfile

    errors: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "runs.jsonl"

        # Test 1: build_record returns the documented keys.
        rec = build_record(command="self-test", label="t1", hostname="testhost")
        for key in (
            "timestamp",
            "git_sha",
            "hostname",
            "python_version",
            "node_version",
            "command",
            "label",
        ):
            if key not in rec:
                errors.append(f"build_record missing key {key!r}")
        if rec.get("hostname") != "testhost":
            errors.append("hostname override not honoured")
        if rec.get("command") != "self-test":
            errors.append("command not recorded")
        if not rec.get("python_version", "").startswith(
            f"{sys.version_info.major}.{sys.version_info.minor}"
        ):
            errors.append(f"python_version wrong: {rec.get('python_version')!r}")
        # timestamp must look like an ISO-8601 Z string
        ts = rec.get("timestamp", "")
        if not (ts.endswith("Z") and "T" in ts):
            errors.append(f"timestamp not ISO-8601 UTC: {ts!r}")

        # Test 2: append_record creates the file and writes one JSONL line.
        append_record(out, rec)
        if not out.is_file():
            errors.append("output JSONL was not created")
        text = out.read_text(encoding="utf-8")
        if text.count("\n") != 1:
            errors.append(f"expected 1 line, got {text.count(chr(10))}")
        try:
            parsed = json.loads(text.strip())
        except json.JSONDecodeError as e:
            errors.append(f"JSONL line is not valid JSON: {e}")
            parsed = {}
        if parsed.get("hostname") != "testhost":
            errors.append("JSONL hostname mismatch")

        # Test 3: a second append yields a second line (true append, not overwrite).
        rec2 = build_record(command="round-trip-2", label="t2", hostname="testhost")
        append_record(out, rec2)
        text = out.read_text(encoding="utf-8")
        if text.count("\n") != 2:
            errors.append(f"expected 2 lines after second append, got {text.count(chr(10))}")
        lines = [json.loads(line) for line in text.splitlines() if line.strip()]
        if len(lines) != 2 or lines[1].get("command") != "round-trip-2":
            errors.append("second record not appended correctly")

        # Test 4: D_RESEARCH_RUN_HOSTNAME env var override.
        os.environ["D_RESEARCH_RUN_HOSTNAME"] = "env-host"
        try:
            rec3 = build_record(command="env-host-test")
            if rec3.get("hostname") != "env-host":
                errors.append(
                    f"env hostname override failed: got {rec3.get('hostname')!r}"
                )
        finally:
            os.environ.pop("D_RESEARCH_RUN_HOSTNAME", None)

        # Test 5: cmd_record writes to a JSONL file via the CLI surface.
        out2 = Path(tmpdir) / "cli.jsonl"
        ns = argparse.Namespace(
            command="cli-test",
            label="t3",
            out=str(out2),
            print=False,
            repo=None,
            hostname="testhost",
        )
        if cmd_record(ns) != 0:
            errors.append("cmd_record returned non-zero")
        if not out2.is_file():
            errors.append("cmd_record did not write the JSONL file")

    if errors:
        print("run_metadata self-test FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("run_metadata self-test ok")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        prog="run_metadata.py",
        description="Append a JSONL line of local run metadata.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    rec_p = sub.add_parser("record", help="Append a run-metadata record.")
    rec_p.add_argument("--out", required=True, help="JSONL output file.")
    rec_p.add_argument("--command", default="", help="Free-form command/label.")
    rec_p.add_argument("--label", default="", help="Single-word run label.")
    rec_p.add_argument(
        "--hostname",
        default=None,
        help="Override hostname. Defaults to D_RESEARCH_RUN_HOSTNAME or socket.gethostname().",
    )
    rec_p.add_argument(
        "--repo",
        default=None,
        help="Repository root for git SHA detection (default: current dir).",
    )
    rec_p.add_argument(
        "--print", action="store_true", help="Also print the record to stdout."
    )

    sub.add_parser("self-test", help="Run offline self-test.")

    args = p.parse_args()
    if args.cmd == "record":
        return cmd_record(args)
    if args.cmd == "self-test":
        return cmd_self_test(args)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
