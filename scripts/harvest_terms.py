#!/usr/bin/env python3
"""Register/jargon term harvester — cross-source recurrence filter.

Turns the "keep only terms that recur across >=2 independent community
sources" rule from ``references/register-and-jargon-expansion.md`` into a
deterministic, offline, stdlib-only tool.

It does NOT invent vocabulary. The input is candidate terms that the agent
already harvested from fresh search results, each tagged with the source it
came from. The tool counts how many *distinct* sources contain each candidate
term and labels terms ``confirmed`` (>= threshold) or ``candidate`` (below it).
Harvested vocabulary is a discovery layer only, never evidence.

Input format (one occurrence per line, ``source<delimiter>term``)::

    patient-forum-a\tbrain fog
    patient-forum-b\tbrain fog
    blog-c\tbrain fog
    random-thread\ttotally cured lol

Lines that are blank or start with ``#`` are ignored. The default delimiter is
a TAB; override with ``--delimiter``. Source and term are stripped; terms are
grouped case-insensitively while preserving the first-seen surface form.

Subcommands:
    harvest     Count independent sources per term and apply the threshold.
    self-test   Run offline self-tests with synthetic data.

Exit status:
    0  success
    1  error (e.g. no usable input)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _read_input(path: str | None) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    return sys.stdin.read()


def harvest(text: str, *, delimiter: str = "\t", threshold: int = 2) -> dict:
    """Group ``source<delimiter>term`` lines and apply the recurrence threshold.

    Returns a deterministic result dict with per-term independent-source counts
    and a ``confirmed``/``candidate`` split. Order follows first appearance.
    """
    order: list[str] = []
    sources_by_key: dict[str, set[str]] = {}
    surface_by_key: dict[str, str] = {}
    malformed = 0

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if delimiter not in line:
            malformed += 1
            continue
        source, term = line.split(delimiter, 1)
        source = source.strip()
        term = term.strip()
        if not source or not term:
            malformed += 1
            continue
        key = term.lower()
        if key not in sources_by_key:
            sources_by_key[key] = set()
            surface_by_key[key] = term
            order.append(key)
        sources_by_key[key].add(source)

    terms = []
    confirmed: list[str] = []
    candidates: list[str] = []
    for key in order:
        count = len(sources_by_key[key])
        status = "confirmed" if count >= threshold else "candidate"
        surface = surface_by_key[key]
        terms.append(
            {
                "term": surface,
                "independent_sources": count,
                "sources": sorted(sources_by_key[key]),
                "status": status,
            }
        )
        (confirmed if status == "confirmed" else candidates).append(surface)

    return {
        "threshold": threshold,
        "malformed_lines": malformed,
        "terms": terms,
        "confirmed": confirmed,
        "candidates": candidates,
    }


def _render_text(result: dict) -> str:
    lines = [
        f"threshold: {result['threshold']} independent source(s)",
        f"terms: {len(result['terms'])}  "
        f"confirmed: {len(result['confirmed'])}  "
        f"candidate: {len(result['candidates'])}",
        "",
    ]
    for entry in result["terms"]:
        mark = "KEEP" if entry["status"] == "confirmed" else "----"
        lines.append(
            f"[{mark}] {entry['independent_sources']:>2}  "
            f"{entry['term']}  ({', '.join(entry['sources'])})"
        )
    return "\n".join(lines) + "\n"


def cmd_harvest(args: argparse.Namespace) -> int:
    if args.threshold < 1:
        print("error: --threshold must be >= 1", file=sys.stderr)
        return 1
    delimiter = "\t" if args.delimiter == "\\t" else args.delimiter
    text = _read_input(args.input)
    result = harvest(text, delimiter=delimiter, threshold=args.threshold)
    if not result["terms"]:
        print("error: no usable 'source<delimiter>term' lines found", file=sys.stderr)
        return 1
    output = (
        json.dumps(result, indent=2, ensure_ascii=False)
        if args.format == "json"
        else _render_text(result)
    )
    if args.out:
        Path(args.out).write_text(
            output if output.endswith("\n") else output + "\n", encoding="utf-8"
        )
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(output if output.endswith("\n") else output + "\n")
    return 0


def cmd_self_test(_args: argparse.Namespace) -> int:
    errors: list[str] = []

    sample = (
        "# comment line ignored\n"
        "\n"
        "forum-a\tbrain fog\n"
        "forum-b\tBrain Fog\n"   # case-insensitive grouping
        "blog-c\tbrain fog\n"
        "forum-a\tbrain fog\n"   # duplicate source does not add to count
        "thread-x\ttotally cured lol\n"
        "malformed-line-without-delimiter\n"
    )
    result = harvest(sample, threshold=2)

    by_term = {e["term"].lower(): e for e in result["terms"]}

    # "brain fog" seen in 3 distinct sources (forum-a counted once) -> confirmed
    if by_term["brain fog"]["independent_sources"] != 3:
        errors.append("brain fog should have 3 independent sources")
    if by_term["brain fog"]["status"] != "confirmed":
        errors.append("brain fog should be confirmed at threshold 2")

    # single-source term stays candidate
    if by_term["totally cured lol"]["independent_sources"] != 1:
        errors.append("single-source term should have 1 independent source")
    if by_term["totally cured lol"]["status"] != "candidate":
        errors.append("single-source term should be candidate, not confirmed")

    if result["malformed_lines"] != 1:
        errors.append("expected exactly 1 malformed line")
    if result["confirmed"] != ["brain fog"]:
        errors.append(f"unexpected confirmed list: {result['confirmed']}")
    if "totally cured lol" not in result["candidates"]:
        errors.append("totally cured lol should be in candidates")

    # threshold of 3 should still keep brain fog, raising it keeps determinism
    high = harvest(sample, threshold=4)
    if high["confirmed"]:
        errors.append("threshold 4 should leave nothing confirmed")

    # custom delimiter
    delim = harvest("a,foo\nb,foo\n", delimiter=",", threshold=2)
    if delim["confirmed"] != ["foo"]:
        errors.append("custom delimiter grouping failed")

    if errors:
        print("harvest_terms self-test FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("harvest_terms self-test ok")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        prog="harvest_terms.py",
        description=(
            "Count independent sources per candidate register/jargon term and "
            "keep only terms recurring across >= threshold sources. Discovery "
            "layer only — harvested vocabulary is never evidence."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # --- harvest subcommand ---
    h = sub.add_parser(
        "harvest", help="Filter candidate terms by cross-source recurrence."
    )
    h.add_argument(
        "--in", dest="input", default=None,
        help="Input file of 'source<delimiter>term' lines (default: stdin).",
    )
    h.add_argument(
        "--out", default=None, help="Write output to this file (default: stdout)."
    )
    h.add_argument(
        "--threshold", type=int, default=2,
        help="Minimum distinct sources for a term to be 'confirmed' (default: 2).",
    )
    h.add_argument(
        "--delimiter", default="\t",
        help="Field delimiter between source and term (default: TAB; use '\\t').",
    )
    h.add_argument(
        "--format", choices=("json", "text"), default="json",
        help="Output format (default: json).",
    )

    # --- self-test subcommand ---
    sub.add_parser("self-test", help="Run offline self-tests.")

    args = p.parse_args()

    if args.cmd == "harvest":
        return cmd_harvest(args)
    if args.cmd == "self-test":
        return cmd_self_test(args)

    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
