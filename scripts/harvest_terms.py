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
import re
import sys
import tempfile
from pathlib import Path


_CAPTURE_STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "have", "has", "had", "not", "but", "you", "your", "our", "all", "can",
    "will", "its", "into", "about", "more", "than", "when", "what", "which",
    "who", "how", "why", "use", "using", "used", "also", "other", "such",
    "của", "và", "các", "những", "trong", "cho", "với", "được", "không", "một",
    "này", "khi", "như", "từ", "về", "để", "tại", "theo", "trên", "nên",
})


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


def _extract_capture_terms(text: str) -> list[str]:
    """Extract deterministic candidate bigrams, hyphenated compounds, and acronyms from text."""
    seen: list[str] = []
    seen_lower: set[str] = set()

    def _add(term: str) -> None:
        key = term.lower()
        if key not in seen_lower:
            seen_lower.add(key)
            seen.append(term)

    for acro in re.findall(r"\b[A-Z][A-Z0-9-]{2,}\b", text):
        _add(acro)

    tokens = [
        tok
        for tok in re.findall(r"[0-9A-Za-zÀ-ỹ_-]{2,}", text)
        if not tok.isdigit()
    ]
    for tok in tokens:
        if "-" in tok and len(tok) >= 4 and tok.lower() not in _CAPTURE_STOPWORDS:
            _add(tok.lower())

    for idx in range(len(tokens) - 1):
        w1 = tokens[idx].lower()
        w2 = tokens[idx + 1].lower()
        if len(w1) < 3 or len(w2) < 3:
            continue
        if w1 in _CAPTURE_STOPWORDS or w2 in _CAPTURE_STOPWORDS:
            continue
        _add(f"{w1} {w2}")
    return seen


def harvest_from_captures(
    capture_records_path: str | Path,
    *,
    workspace_dir: str | Path | None = None,
    threshold: int = 2,
) -> dict:
    """Harvest cross-source recurring terms directly from DRS-1.1 capture records."""
    cap_path = Path(capture_records_path).resolve()
    ws = Path(workspace_dir).resolve() if workspace_dir else cap_path.parent
    raw_obj = json.loads(cap_path.read_text(encoding="utf-8"))
    if isinstance(raw_obj, list):
        records = raw_obj
    elif isinstance(raw_obj, dict):
        records = raw_obj.get("records") or raw_obj.get("captures") or []
    else:
        records = []

    lines: list[str] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        source_key = str(
            rec.get("source_id")
            or rec.get("final_url")
            or rec.get("source_url")
            or rec.get("capture_id")
            or ""
        ).strip()
        raw_ref = rec.get("raw_text_ref")
        if not source_key or not raw_ref:
            continue
        ref_path = Path(str(raw_ref))
        if not ref_path.is_absolute():
            ref_path = ws / ref_path
        if not ref_path.exists():
            continue
        body = ref_path.read_text(encoding="utf-8", errors="replace")
        for term in _extract_capture_terms(body):
            lines.append(f"{source_key}\t{term}")
    return harvest("\n".join(lines), delimiter="\t", threshold=threshold)


def cmd_harvest(args: argparse.Namespace) -> int:
    if args.threshold < 1:
        print("error: --threshold must be >= 1", file=sys.stderr)
        return 1
    if getattr(args, "from_captures", None):
        result = harvest_from_captures(
            args.from_captures,
            workspace_dir=getattr(args, "workspace", None),
            threshold=args.threshold,
        )
    else:
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

    # harvest directly from DRS-1.1 capture-records.json + raw text captures
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "captures").mkdir()
        (ws / "captures" / "c1.txt").write_text(
            "Forum post discussing brain fog and CDP fallback behavior.\n",
            encoding="utf-8",
        )
        (ws / "captures" / "c2.txt").write_text(
            "Issue tracker confirming brain fog under rate limit.\n",
            encoding="utf-8",
        )
        cap_file = ws / "capture-records.json"
        cap_file.write_text(
            json.dumps([
                {"capture_id": "cap1", "source_id": "src-a", "raw_text_ref": "captures/c1.txt"},
                {"capture_id": "cap2", "source_id": "src-b", "raw_text_ref": "captures/c2.txt"},
            ]),
            encoding="utf-8",
        )
        cap_res = harvest_from_captures(cap_file, workspace_dir=ws, threshold=2)
        confirmed_lower = {t.lower() for t in cap_res["confirmed"]}
        if "brain fog" not in confirmed_lower:
            errors.append(f"harvest_from_captures missed recurring bigram: {cap_res['confirmed']}")

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
        "--from-captures", dest="from_captures", default=None,
        help="Harvest recurring terms from DRS-1.1 capture-records.json + raw text files.",
    )
    h.add_argument(
        "--workspace", default=None,
        help="Workspace root for resolving relative raw_text_ref paths in --from-captures.",
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
