#!/usr/bin/env python3
"""Final report generator for research workspaces.

Takes a research workspace (plan + evidence ledger + optional screening log)
and produces a structured Markdown report with citations. Depends on
citation_render.py for style rendering and evidence_ledger.py for validation.

Subcommands
-----------
* ``init``        - write report.draft.md skeleton from template + plan
* ``render``      - produce final report.md from workspace artifacts
* ``to-pdf``      - convert markdown to PDF via pandoc
* ``to-docx``     - convert markdown to DOCX via pandoc
* ``to-html``     - convert markdown to HTML via pandoc
* ``list-styles`` - list available CSL citation styles
* ``lint``        - check workspace for missing/unused claims
* ``self-test``   - run offline self-tests with synthetic workspace

Pandoc export commands soft-fail with a helpful message if pandoc is missing.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from content_sanitize import redact_secrets

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = REPO_ROOT / "templates" / "report-template.md"
_MARKDOWN_SPECIAL_RE = re.compile(r"([\\`*_[\]{}()#+!|])")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")
_MAX_SOURCE_URL_LENGTH = 2048


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"error: cannot load {path}: {e}", file=sys.stderr)
        raise SystemExit(1)


def _load_ledger(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _generated_markdown_text(value: Any, *, limit: int) -> str:
    """Render untrusted generated metadata as inert single-line Markdown text."""

    text = _CONTROL_RE.sub(" ", str(value or ""))
    text = re.sub(r"\s+", " ", redact_secrets(text)).strip()
    text = text[:limit]
    text = html.escape(text, quote=True)
    return _MARKDOWN_SPECIAL_RE.sub(r"\\\1", text)


def _safe_source_url(value: Any) -> str | None:
    """Return a displayable HTTP(S) URL without credentials or controls."""

    raw = str(value or "").strip()
    if not raw or len(raw) > _MAX_SOURCE_URL_LENGTH:
        return None
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in raw):
        return None
    if redact_secrets(raw) != raw:
        return None
    try:
        parsed = urlsplit(raw)
        _ = parsed.port
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    return raw


def _path_in_workspace(workspace: Path, raw: str | Path, *, label: str) -> Path:
    """Resolve a user/plan path and require it to remain inside ``workspace``.

    Research plans are agent-generated input, so report rendering must not trust
    their input/output paths. ``Path.resolve(strict=False)`` also resolves any
    existing symlinked parent before the containment check.
    """
    root = workspace.resolve()
    value = Path(raw)
    candidate = value if value.is_absolute() else root / value
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} must stay inside workspace: {raw!s}") from exc
    return resolved


def _has_pandoc() -> bool:
    return shutil.which("pandoc") is not None


def _run_pandoc(args: list[str]) -> int:
    if not _has_pandoc():
        print(
            "error: pandoc is not installed. Install pandoc >= 2.11 for export.\n"
            "  Ubuntu/Debian: sudo apt-get install pandoc\n"
            "  macOS: brew install pandoc\n"
            "  Windows: choco install pandoc",
            file=sys.stderr,
        )
        return 1
    try:
        result = subprocess.run(
            ["pandoc", *args],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            print(f"error: pandoc failed: {result.stderr}", file=sys.stderr)
            return 1
        return 0
    except subprocess.TimeoutExpired:
        print("error: pandoc timed out", file=sys.stderr)
        return 1
    except FileNotFoundError:
        print("error: pandoc binary not found", file=sys.stderr)
        return 1


def _validate_ledger(ledger_path: Path) -> int:
    """Validate ledger using evidence_ledger.py's validate function."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "evidence_ledger",
        Path(__file__).resolve().parent / "evidence_ledger.py",
    )
    el_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(el_mod)
    return el_mod.validate_ledger(ledger_path)


def _verify_signature(ledger_path: Path) -> bool:
    """Verify the ledger HMAC sidecar. Return ``True`` only when valid."""
    if not ledger_path.is_file():
        print(f"error: evidence ledger not found: {ledger_path}", file=sys.stderr)
        return False

    hmac_path = Path(str(ledger_path) + ".hmac")
    if not hmac_path.is_file():
        print(f"error: signature file not found: {hmac_path}", file=sys.stderr)
        return False

    key = os.environ.get("D_RESEARCH_LEDGER_KEY", "")
    if not key:
        print(
            "error: D_RESEARCH_LEDGER_KEY not set but signature sidecar exists; "
            "cannot verify ledger integrity",
            file=sys.stderr,
        )
        return False

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "evidence_ledger",
        Path(__file__).resolve().parent / "evidence_ledger.py",
    )
    el_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(el_mod)

    import contextlib
    import io as _io

    try:
        with contextlib.redirect_stdout(_io.StringIO()):
            rc = el_mod.verify_ledger(
                ledger_path, "D_RESEARCH_LEDGER_KEY", hmac_path
            )
    except Exception as exc:
        print(f"error: ledger signature verification failed: {exc}", file=sys.stderr)
        return False
    return rc == 0


def _required_signature_preflight(ledger_path: Path) -> bool:
    """Fail closed before report inputs are loaded when HMAC is mandatory."""
    if not ledger_path.is_file():
        print(
            "error: --require-signature requires evidence-ledger.csv",
            file=sys.stderr,
        )
        return False

    hmac_path = Path(str(ledger_path) + ".hmac")
    if not hmac_path.is_file():
        print(
            "error: --require-signature set but no signature sidecar found",
            file=sys.stderr,
        )
        return False

    if not _verify_signature(ledger_path):
        print(
            "error: ledger signature verification FAILED - refusing to render",
            file=sys.stderr,
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    """Write report.draft.md skeleton from template + plan."""
    workspace = Path(args.workspace)
    if not workspace.is_dir():
        print(f"error: workspace not found: {workspace}", file=sys.stderr)
        return 1

    plan_path = workspace / "research-plan.json"
    out_path = workspace / "report.draft.md"

    # Load template
    if TEMPLATE_PATH.is_file():
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
    else:
        template = _default_template()

    # Load plan if exists
    title = "Research Report"
    sections: list[str] = []
    if plan_path.is_file():
        plan = _load_json(plan_path)
        title = _generated_markdown_text(
            plan.get("title", plan.get("slug", "Research Report")), limit=200
        )
        tasks = plan.get("tasks", [])
        for task in tasks:
            if not isinstance(task, dict):
                continue
            task_title = _generated_markdown_text(
                task.get("title", task.get("id", "Section")), limit=160
            )
            sections.append(f"## {task_title}\n\n<!-- findings from task -->\n")

    # Fill template
    content = template.replace("{{title}}", title)
    content = content.replace("{{date}}", _utc_now())
    content = content.replace("{{sections}}", "\n".join(sections) if sections else "## Findings\n\n<!-- Add findings here -->\n")

    out_path.write_text(content, encoding="utf-8")
    print(f"wrote {out_path}")
    return 0



GENERATED_EVIDENCE_BEGIN = "<!-- BEGIN GENERATED: evidence-summary -->"
GENERATED_EVIDENCE_END = "<!-- END GENERATED: evidence-summary -->"
GENERATED_REFS_BEGIN = "<!-- BEGIN GENERATED: references -->"
GENERATED_REFS_END = "<!-- END GENERATED: references -->"

PLACEHOLDER_SNIPPETS = (
    "<!-- Replace with synthesis of key findings -->",
    "<!-- Findings for task:",
    "<!-- Document limitations, blocked sources, confidence gaps -->",
    "<!-- Add findings here -->",
    "<!-- findings from task -->",
    "[placeholder]",
    "[PLACEHOLDER]",
)

# Bounded placeholder patterns (case-insensitive). Avoid matching prose about TODOs.
_PLACEHOLDER_RES = (
    r"\[placeholder\]",
    r"<!--\s*todo[\s:].*?-->",
    r"<!--\s*replace with\b",
    r"<!--\s*findings for task\b",
    r"<!--\s*add findings\b",
    r"<!--\s*document limitations\b",
    r"\bTODO:\b",
    r"\bTBD\b",
)


def _authored_narrative(content: str) -> tuple[str, list[str]]:
    """Return authored prose only, plus parse errors for malformed markers."""
    import re

    errors: list[str] = []
    text = content
    # Generated blocks must be well-formed pairs.
    for begin, end in (
        (GENERATED_EVIDENCE_BEGIN, GENERATED_EVIDENCE_END),
        (GENERATED_REFS_BEGIN, GENERATED_REFS_END),
    ):
        bcount = text.count(begin)
        ecount = text.count(end)
        if bcount != ecount:
            errors.append(f"unmatched generated markers: {begin!r} / {end!r}")
        if bcount > 1 or ecount > 1:
            errors.append(f"duplicate generated markers: {begin!r}")
        text = _strip_generated_block(text, begin, end)

    # Strip HTML comments
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    # Strip fenced code blocks
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    # Strip indented code-ish quote blocks used for evidence excerpts (lines starting with >)
    # Keep them out of coverage scanning.
    lines = []
    for line in text.splitlines():
        if line.lstrip().startswith(">"):
            continue
        lines.append(line)
    text = "\n".join(lines)
    return text, errors


def _has_placeholder(content: str) -> list[str]:
    import re

    hits: list[str] = []
    lower = content
    for snip in PLACEHOLDER_SNIPPETS:
        if snip.lower() in lower.lower():
            hits.append(snip)
    for pat in _PLACEHOLDER_RES:
        if re.search(pat, content, flags=re.I | re.S):
            hits.append(pat)
    return hits


def _infer_task_phase(task: dict[str, Any]) -> str:
    phase = task.get("phase")
    if phase in {"research", "synthesis"}:
        return phase
    for op in task.get("outputs") or []:
        op_norm = str(op).replace("\\", "/").lower()
        if any(
            m in op_norm
            for m in ("report.md", "report-citations", "citations.md", "bibliography")
        ):
            return "synthesis"
    return "research"


def _resolve_report_out(workspace: Path, plan: dict[str, Any] | None, out_arg: str | None) -> Path:
    if out_arg:
        return _path_in_workspace(workspace, out_arg, label="report output")
    if plan:
        for task in plan.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            if _infer_task_phase(task) != "synthesis":
                continue
            for op in task.get("outputs") or []:
                op_norm = str(op).replace("\\", "/")
                if op_norm.lower().endswith("report.md"):
                    return _path_in_workspace(workspace, op_norm, label="plan report output")
    canonical = workspace / "research-output" / "report.md"
    if (workspace / "research-output").is_dir():
        return canonical
    print(
        "warning: using deprecated root report.md; prefer research-output/report.md",
        file=sys.stderr,
    )
    return workspace / "report.md"


def _strip_generated_block(text: str, begin: str, end: str) -> str:
    import re

    pattern = re.compile(
        re.escape(begin) + r".*?" + re.escape(end),
        flags=re.DOTALL,
    )
    return pattern.sub("", text)


def _build_evidence_block(rows: list[dict[str, str]]) -> list[str]:
    claim_rows = [
        r
        for r in rows
        if (r.get("record_type") or "claim").strip().lower() in {"", "claim"}
    ]
    lines = [
        GENERATED_EVIDENCE_BEGIN,
        "## Evidence Summary",
        "",
        f"Total claims: {len(claim_rows)}",
        "",
        "| # | Claim | Source | Confidence |",
        "|---|-------|--------|------------|",
    ]
    for i, row in enumerate(claim_rows[:50], 1):
        claim = _generated_markdown_text(row.get("claim", ""), limit=160)
        safe_url = _safe_source_url(row.get("source_url", ""))
        source = (
            _generated_markdown_text(safe_url, limit=_MAX_SOURCE_URL_LENGTH)
            if safe_url
            else "[invalid URL omitted]"
        )
        conf = _generated_markdown_text(row.get("confidence", ""), limit=32)
        lines.append(f"| {i} | {claim} | {source} | {conf} |")
    if len(claim_rows) > 50:
        lines.append(f"| ... | *{len(claim_rows) - 50} more rows* | | |")
    lines.extend(["", GENERATED_EVIDENCE_END, ""])
    return lines


def _build_references_block(rows: list[dict[str, str]]) -> list[str]:
    lines = [GENERATED_REFS_BEGIN, "## References", ""]
    seen_urls: set[str] = set()
    ref_num = 1
    for row in rows:
        url = _safe_source_url(row.get("source_url", ""))
        title_ref = _generated_markdown_text(row.get("source_title", ""), limit=300)
        if url and url not in seen_urls:
            seen_urls.add(url)
            display_url = _generated_markdown_text(url, limit=_MAX_SOURCE_URL_LENGTH)
            lines.append(f"{ref_num}. {title_ref or display_url} — {display_url}")
            ref_num += 1
        elif not url and title_ref:
            lines.append(f"{ref_num}. {title_ref} — [invalid URL omitted]")
            ref_num += 1
    lines.extend(["", GENERATED_REFS_END, ""])
    return lines


def _collect_narrative(workspace: Path, plan: dict[str, Any] | None) -> str | None:
    """Primary narrative from report.draft.md or synthesis task section inputs."""
    draft = workspace / "report.draft.md"
    if draft.is_file() and draft.stat().st_size > 0:
        text = draft.read_text(encoding="utf-8").strip()
        if text:
            return text
    if not plan:
        return None
    parts: list[str] = []
    for task in plan.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        if _infer_task_phase(task) != "synthesis":
            continue
        for rel in task.get("inputs") or []:
            path = _path_in_workspace(
                workspace,
                str(rel).replace("\\", "/"),
                label="synthesis input",
            )
            if path.is_file() and path.stat().st_size > 0:
                parts.append(path.read_text(encoding="utf-8").strip())
    if not parts:
        # Fall back to research section files in declaration order.
        for task in plan.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            if _infer_task_phase(task) != "research":
                continue
            for rel in task.get("outputs") or []:
                path = _path_in_workspace(
                    workspace,
                    str(rel).replace("\\", "/"),
                    label="research output",
                )
                if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
                    body = path.read_text(encoding="utf-8").strip()
                    if body:
                        heading = _generated_markdown_text(
                            task.get("title") or task.get("id") or path.stem,
                            limit=160,
                        )
                        parts.append(f"## {heading}\n\n{body}")
    if not parts:
        return None
    return "\n\n".join(parts)


def cmd_render(args: argparse.Namespace) -> int:
    """Produce final report from draft/sections + generated evidence/refs blocks."""
    workspace = Path(args.workspace).resolve()
    if not workspace.is_dir():
        print(f"error: workspace not found: {workspace}", file=sys.stderr)
        return 1

    ledger_path = workspace / "evidence-ledger.csv"
    plan_path = workspace / "research-plan.json"
    screening_path = workspace / "screening-log.csv"
    require_sig = getattr(args, "require_signature", False)

    # Signature-required rendering is a preflight gate. Run it before parsing
    # the plan, collecting narrative, resolving the output path, or validating
    # any other report input so a missing/tampered ledger always fails first.
    if require_sig and not _required_signature_preflight(ledger_path):
        return 1

    plan: dict[str, Any] | None = None
    if plan_path.is_file():
        plan = _load_json(plan_path)

    try:
        out_path = _resolve_report_out(workspace, plan, getattr(args, "out", None))
        narrative = _collect_narrative(workspace, plan)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # Step 1: Validate ledger schema
    if ledger_path.is_file():
        rc = _validate_ledger(ledger_path)
        if rc != 0:
            print("error: evidence ledger failed schema validation", file=sys.stderr)
            return 1

        hmac_path = Path(str(ledger_path) + ".hmac")
        # Re-verify after schema validation as a defense-in-depth check against
        # changes between the early required-signature preflight and rendering.
        if hmac_path.is_file():
            if not _verify_signature(ledger_path):
                print(
                    "error: ledger signature verification FAILED — refusing to render",
                    file=sys.stderr,
                )
                return 1
        elif not hmac_path.is_file():
            print(
                "warning: ledger is not signed; rendering without signature verification",
                file=sys.stderr,
            )

    if not narrative:
        print(
            "error: no narrative found; write report.draft.md or synthesis section inputs",
            file=sys.stderr,
        )
        return 1

    # Strip prior generated blocks if re-rendering an existing draft that already has them.
    narrative = _strip_generated_block(
        narrative, GENERATED_EVIDENCE_BEGIN, GENERATED_EVIDENCE_END
    )
    narrative = _strip_generated_block(
        narrative, GENERATED_REFS_BEGIN, GENERATED_REFS_END
    )

    for snip in PLACEHOLDER_SNIPPETS:
        if snip in narrative:
            print(
                f"error: narrative still contains placeholder {snip!r}; "
                "fill draft/sections before render",
                file=sys.stderr,
            )
            return 1

    lines: list[str] = [narrative.rstrip(), ""]

    # Screening summary (non-placeholder factual block when present)
    if screening_path.is_file():
        screening_rows = _load_ledger(screening_path)
        lines.append("## Screening Summary (PRISMA)")
        lines.append("")
        lines.append(f"Total screened: {len(screening_rows)}")
        included = sum(
            1 for r in screening_rows if r.get("decision", "").lower() == "include"
        )
        excluded = sum(
            1 for r in screening_rows if r.get("decision", "").lower() == "exclude"
        )
        lines.append(f"Included: {included}")
        lines.append(f"Excluded: {excluded}")
        lines.append("")

    if ledger_path.is_file():
        rows = _load_ledger(ledger_path)
        if rows:
            lines.extend(_build_evidence_block(rows))
            lines.extend(_build_references_block(rows))

    body = "\n".join(lines).rstrip() + "\n"
    if not body.strip():
        print("error: render produced empty output", file=sys.stderr)
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


def cmd_to_pdf(args: argparse.Namespace) -> int:
    """Convert markdown to PDF via pandoc."""
    return _run_pandoc([args.input, "-o", args.out, "--pdf-engine=xelatex"])


def cmd_to_docx(args: argparse.Namespace) -> int:
    """Convert markdown to DOCX via pandoc."""
    return _run_pandoc([args.input, "-o", args.out])


def cmd_to_html(args: argparse.Namespace) -> int:
    """Convert markdown to HTML via pandoc."""
    return _run_pandoc([args.input, "-o", args.out, "--standalone"])


def cmd_list_styles(_args: argparse.Namespace) -> int:
    """List available CSL citation styles."""
    styles = [
        "apa", "apa7", "mla", "mla9", "ieee", "chicago-author-date",
        "chicago-note", "vancouver", "harvard-cite-them-right", "nature",
        "science", "acm-sig-proceedings", "ama", "elsevier-harvard", "acs", "aiaa",
    ]
    print("Available citation style aliases:")
    for s in styles:
        print(f"  {s}")
    print("\nAny CSL identifier is also accepted (pandoc will download it).")
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    """Check workspace for missing/unused claims and broken refs.

    Factual ``record_type=claim`` rows must appear as ``[ref:claim_id]`` in the
    narrative. ``process`` and ``blocker`` rows are exempt from coverage.
    ``--strict`` (used by release gates) treats unreferenced claims as errors.
    ``--allow-unreferenced`` is a manual escape hatch that never runs in gates.
    """
    import re

    workspace = Path(args.workspace).resolve()
    if not workspace.is_dir():
        print(f"error: workspace not found: {workspace}", file=sys.stderr)
        return 1

    errors: list[str] = []
    warnings: list[str] = []
    allow_unref = getattr(args, "allow_unreferenced", False)
    explicit_report = getattr(args, "report", None)

    ledger_path = workspace / "evidence-ledger.csv"
    if explicit_report:
        try:
            report_file = _path_in_workspace(
                workspace, explicit_report, label="lint report path"
            )
        except ValueError as exc:
            errors.append(str(exc))
            report_file = None
        if report_file is None or not report_file.is_file():
            errors.append(f"exact report path not found: {explicit_report}")
            report_file = None
    else:
        candidates = [
            workspace / "research-output" / "report.md",
            workspace / "report.md",
            workspace / "report.draft.md",
        ]
        report_file = next((p for p in candidates if p.is_file()), None)

    claim_ids: set[str] = set()
    process_blocker_ids: set[str] = set()
    seen_ids: set[str] = set()
    if ledger_path.is_file():
        rows = _load_ledger(ledger_path)
        for row in rows:
            cid = (row.get("claim_id", "") or "").strip()
            if not cid:
                continue
            if cid in seen_ids:
                errors.append(f"duplicate claim_id in ledger: {cid}")
            seen_ids.add(cid)
            rtype = (row.get("record_type") or "claim").strip().lower() or "claim"
            if rtype in {"process", "blocker"}:
                process_blocker_ids.add(cid)
            else:
                claim_ids.add(cid)
    else:
        warnings.append("no evidence-ledger.csv found in workspace")

    referenced_claims: set[str] = set()
    if report_file is not None:
        content = report_file.read_text(encoding="utf-8")
        for hit in _has_placeholder(content):
            errors.append(f"report still contains placeholder: {hit!r}")
        narrative, marker_errors = _authored_narrative(content)
        errors.extend(marker_errors)
        refs = re.findall(r"\[ref:([^\]]+)\]", narrative)
        referenced_claims = {r.strip() for r in refs if r.strip()}

        missing = referenced_claims - seen_ids
        for cid in sorted(missing):
            errors.append(f"claim referenced in report but not in ledger: {cid}")
    else:
        if claim_ids:
            errors.append("no report found for claim coverage")

    unreferenced = claim_ids - referenced_claims
    if unreferenced:
        msg_base = "ledger claim not referenced in report"
        for cid in sorted(unreferenced):
            if allow_unref:
                warnings.append(f"{msg_base} (allowed by --allow-unreferenced): {cid}")
            else:
                errors.append(f"{msg_base}: {cid}")

    if allow_unref:
        print(
            "warning: --allow-unreferenced is a manual override; "
            "release gates never use this flag",
            file=sys.stderr,
        )

    if warnings:
        for w in warnings:
            print(f"  warning: {w}", file=sys.stderr)
    if errors:
        print(f"FAIL: {len(errors)} lint error(s):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(
        f"OK: workspace lint passed "
        f"({len(claim_ids)} claims, {len(process_blocker_ids)} process/blocker, "
        f"{len(referenced_claims)} referenced)."
    )
    return 0


def _default_template() -> str:
    """Fallback template if templates/report-template.md is missing."""
    return """# {{title}}

Generated: {{date}}

## Executive Summary

<!-- Replace with synthesis of key findings -->

{{sections}}

## References

<!-- Auto-generated from evidence ledger -->

## Caveats and Limitations

<!-- Document limitations, blocked sources, confidence gaps -->
"""


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def cmd_self_test(_args: argparse.Namespace) -> int:
    """Offline self-test with synthetic workspace."""
    errors: list[str] = []
    original_ledger_key = os.environ.get("D_RESEARCH_LEDGER_KEY")
    test_key = "test-key-for-self-test-only-32chars!"

    import contextlib as _selftest_contextlib
    import io as _selftest_io

    def run_render_captured(
        namespace: argparse.Namespace,
    ) -> tuple[int, str, bool]:
        captured = _selftest_io.StringIO()
        raised_system_exit = False
        with _selftest_contextlib.redirect_stderr(captured):
            try:
                rc = cmd_render(namespace)
            except SystemExit as exc:
                raised_system_exit = True
                rc = int(exc.code) if isinstance(exc.code, int) else 1
        return rc, captured.getvalue(), raised_system_exit

    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir) / "test-workspace"
        ws.mkdir()

        # Create synthetic plan
        plan = {
            "slug": "test-research",
            "title": "Test Research Report",
            "tasks": [
                {"id": "T1", "title": "Literature Review"},
                {"id": "T2", "title": "Data Collection"},
                {"id": "T3", "title": "Analysis"},
            ],
        }
        (ws / "research-plan.json").write_text(
            json.dumps(plan, indent=2), encoding="utf-8"
        )

        # Create synthetic ledger (19-column schema)
        fields = [
            "claim_id", "claim", "sub_question", "source_title", "source_url",
            "source_type", "date_published", "date_accessed", "access_method",
            "evidence", "quote_or_anchor", "contradiction", "confidence", "notes",
            "archive_url", "content_hash", "snapshot_status", "verifiability",
            "verifiability_note",
        ]
        ledger_rows = [
            {
                "claim_id": "C001", "claim": "Test claim one",
                "sub_question": "", "source_title": "Source A",
                "source_url": "https://example.com/a", "source_type": "primary",
                "date_published": "2024", "date_accessed": "2026-05-18",
                "access_method": "browser", "evidence": "Found evidence A",
                "quote_or_anchor": "", "contradiction": "none",
                "confidence": "high", "notes": "",
                "archive_url": "", "content_hash": "", "snapshot_status": "",
                "verifiability": "", "verifiability_note": "",
            },
            {
                "claim_id": "C002", "claim": "Test claim two",
                "sub_question": "", "source_title": "Source B",
                "source_url": "https://example.com/b", "source_type": "secondary",
                "date_published": "2023", "date_accessed": "2026-05-18",
                "access_method": "api_fetch", "evidence": "Found evidence B",
                "quote_or_anchor": "", "contradiction": "none",
                "confidence": "medium", "notes": "",
                "archive_url": "", "content_hash": "", "snapshot_status": "",
                "verifiability": "", "verifiability_note": "",
            },
        ]
        ledger_path = ws / "evidence-ledger.csv"
        with ledger_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in ledger_rows:
                writer.writerow(row)

        # Signature-required rendering must gate before parsing any other
        # report input. A malformed plan makes regressions in this ordering
        # observable without relying only on the final return code.
        preflight_ws = Path(tmpdir) / "signature-preflight"
        preflight_ws.mkdir()
        (preflight_ws / "research-plan.json").write_text("{", encoding="utf-8")
        preflight_out = preflight_ws / "must-not-exist.md"
        preflight_ns = argparse.Namespace(
            workspace=str(preflight_ws),
            out=str(preflight_out),
            style="apa",
            require_signature=True,
        )

        rc, stderr_text, raised = run_render_captured(preflight_ns)
        if rc == 0 or "requires evidence-ledger.csv" not in stderr_text:
            errors.append("required-signature preflight did not reject missing ledger")
        if raised:
            errors.append("missing-ledger preflight parsed another report input")

        preflight_ledger = preflight_ws / "evidence-ledger.csv"
        shutil.copyfile(ledger_path, preflight_ledger)
        rc, stderr_text, raised = run_render_captured(preflight_ns)
        if rc == 0 or "no signature sidecar found" not in stderr_text:
            errors.append("required-signature preflight did not reject missing sidecar")
        if raised:
            errors.append("missing-sidecar preflight parsed another report input")

        os.environ["D_RESEARCH_LEDGER_KEY"] = test_key
        preflight_sidecar = Path(str(preflight_ledger) + ".hmac")
        preflight_sidecar.write_text(
            "d-research-skill/hmac-sha256/v1 " + ("0" * 64) + "\n",
            encoding="utf-8",
        )
        rc, stderr_text, raised = run_render_captured(preflight_ns)
        if rc == 0 or "signature verification FAILED" not in stderr_text:
            errors.append("required-signature preflight did not reject invalid HMAC")
        if raised:
            errors.append("invalid-HMAC preflight parsed another report input")
        if preflight_out.exists():
            errors.append("required-signature preflight wrote a report on failure")

        # Create screening log
        screening_path = ws / "screening-log.csv"
        with screening_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "title", "decision", "reason"])
            writer.writeheader()
            writer.writerow({"id": "S1", "title": "Paper A", "decision": "include", "reason": ""})
            writer.writerow({"id": "S2", "title": "Paper B", "decision": "exclude", "reason": "off-topic"})
            writer.writerow({"id": "S3", "title": "Paper C", "decision": "include", "reason": ""})

        # Test 1: init
        init_ns = argparse.Namespace(workspace=str(ws))
        rc = cmd_init(init_ns)
        if rc != 0:
            errors.append("init returned non-zero")
        elif not (ws / "report.draft.md").is_file():
            errors.append("init did not create report.draft.md")
        else:
            draft = (ws / "report.draft.md").read_text(encoding="utf-8")
            if "Test Research Report" not in draft:
                errors.append("init draft missing title from plan")
            if "Literature Review" not in draft:
                errors.append("init draft missing task section")

        # Replace draft with real narrative (no placeholders) + claim refs
        (ws / "report.draft.md").write_text(
            "# Test Research Report\n\n"
            "Generated: 2026-06-01T00:00:00Z\n\n"
            "## Executive Summary\n\n"
            "Claim one is supported [ref:C001]. Claim two is supported [ref:C002].\n\n"
            "## Literature Review\n\n"
            "Literature findings without placeholders.\n\n"
            "## Data Collection\n\n"
            "Data collection findings.\n\n"
            "## Analysis\n\n"
            "Analysis findings.\n\n"
            "## Caveats and Limitations\n\n"
            "No material limitations for self-test.\n",
            encoding="utf-8",
        )

        # Test 2: render
        render_ns = argparse.Namespace(
            workspace=str(ws), out=None, style="apa", require_signature=False
        )
        rc = cmd_render(render_ns)
        if rc != 0:
            errors.append("render returned non-zero")
        elif not (ws / "report.md").is_file():
            errors.append("render did not create report.md")
        else:
            report = (ws / "report.md").read_text(encoding="utf-8")
            if "Test Research Report" not in report:
                errors.append("render report missing title")
            if "Evidence Summary" not in report:
                errors.append("render report missing evidence summary")
            if "Total claims: 2" not in report:
                errors.append("render report wrong claim count")
            if "Screening Summary" not in report:
                errors.append("render report missing screening summary")
            if "https://example.com/a" not in report:
                errors.append("render report missing source URL")
            if "<!-- Replace with" in report:
                errors.append("render overwrote narrative with placeholders")

        # Test 3: render with valid signature
        # Sign the ledger
        import importlib.util as _ilu
        _el_spec = _ilu.spec_from_file_location(
            "evidence_ledger",
            Path(__file__).resolve().parent / "evidence_ledger.py",
        )
        _el_mod = _ilu.module_from_spec(_el_spec)
        _el_spec.loader.exec_module(_el_mod)

        os.environ["D_RESEARCH_LEDGER_KEY"] = test_key
        import contextlib
        import io as _io
        with contextlib.redirect_stdout(_io.StringIO()):
            sign_rc = _el_mod.sign_ledger(ledger_path, "D_RESEARCH_LEDGER_KEY", None)
        if sign_rc != 0:
            errors.append("failed to sign ledger for self-test")
        else:
            # Render with valid signature should succeed
            render_signed_ns = argparse.Namespace(
                workspace=str(ws), out=str(ws / "report-signed.md"),
                style="apa", require_signature=True
            )
            old_stderr = sys.stderr
            sys.stderr = _io.StringIO()
            rc = cmd_render(render_signed_ns)
            sys.stderr = old_stderr
            if rc != 0:
                errors.append("render failed with valid signed ledger")

            # Test 3b: tamper ledger after signing, render should fail
            with ledger_path.open("a", encoding="utf-8") as f:
                f.write("TAMPERED,tampered claim,,,,,,,,,,,,,,,,,\n")
            render_tampered_ns = argparse.Namespace(
                workspace=str(ws), out=str(ws / "report-tampered.md"),
                style="apa", require_signature=False
            )
            old_stderr = sys.stderr
            sys.stderr = _io.StringIO()
            rc = cmd_render(render_tampered_ns)
            sys.stderr = old_stderr
            if rc == 0:
                errors.append("render should fail with tampered signed ledger")

        # Restore the caller's environment before unsigned-signature tests.
        if original_ledger_key is None:
            os.environ.pop("D_RESEARCH_LEDGER_KEY", None)
        else:
            os.environ["D_RESEARCH_LEDGER_KEY"] = original_ledger_key

        # Test 4: render with --require-signature but no signature (fresh ledger)
        # Recreate fresh unsigned ledger
        with ledger_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in ledger_rows:
                writer.writerow(row)
        # Remove .hmac sidecar
        hmac_sidecar = Path(str(ledger_path) + ".hmac")
        if hmac_sidecar.is_file():
            hmac_sidecar.unlink()

        render_sig_ns = argparse.Namespace(
            workspace=str(ws), out=str(ws / "report-sig.md"),
            style="apa", require_signature=True
        )
        old_stderr = sys.stderr
        sys.stderr = _io.StringIO()
        rc = cmd_render(render_sig_ns)
        sys.stderr = old_stderr
        if rc == 0:
            errors.append("render with --require-signature should fail without signature")

        # Test 4: lint requires claim coverage
        lint_ns = argparse.Namespace(
            workspace=str(ws), strict=True, allow_unreferenced=False
        )
        old_stderr = sys.stderr
        sys.stderr = _io.StringIO()
        rc = cmd_lint(lint_ns)
        sys.stderr = old_stderr
        if rc != 0:
            errors.append("lint returned non-zero on fully-referenced workspace")

        # Test 4b: unreferenced claim fails strict lint
        bare = (ws / "report.md").read_text(encoding="utf-8")
        (ws / "report.md").write_text(
            bare.replace("[ref:C002]", ""),
            encoding="utf-8",
        )
        old_stderr = sys.stderr
        sys.stderr = _io.StringIO()
        rc = cmd_lint(lint_ns)
        sys.stderr = old_stderr
        if rc == 0:
            errors.append("lint should fail when a claim is unreferenced")
        # restore full refs
        (ws / "report.md").write_text(bare, encoding="utf-8")

        # Test 5: lint with broken ref
        report_with_ref = (ws / "report.md").read_text(encoding="utf-8")
        report_with_ref += "\n[ref:MISSING_CLAIM]\n"
        (ws / "report.md").write_text(report_with_ref, encoding="utf-8")
        import io as _io2
        old_stderr = sys.stderr
        sys.stderr = _io2.StringIO()
        rc = cmd_lint(lint_ns)
        sys.stderr = old_stderr
        if rc == 0:
            errors.append("lint should fail when report references non-existent claim")

        # Test 6: list-styles
        import io as _io
        captured = _io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        rc = cmd_list_styles(argparse.Namespace())
        sys.stdout = old_stdout
        if rc != 0:
            errors.append("list-styles returned non-zero")
        elif "apa" not in captured.getvalue():
            errors.append("list-styles missing apa")

        # Test 7: plan-derived report paths cannot escape the workspace.
        escape_ws = Path(tmpdir) / "escape-workspace"
        escape_ws.mkdir()
        (escape_ws / "report.draft.md").write_text(
            "# Safe narrative\n", encoding="utf-8"
        )
        outside_report = Path(tmpdir) / "escaped-report.md"
        escape_plan = {
            "schema_version": "2.0",
            "tasks": [
                {
                    "id": "S1",
                    "phase": "synthesis",
                    "outputs": ["../escaped-report.md"],
                }
            ],
        }
        (escape_ws / "research-plan.json").write_text(
            json.dumps(escape_plan), encoding="utf-8"
        )
        with contextlib.redirect_stderr(_io.StringIO()):
            rc = cmd_render(
                argparse.Namespace(
                    workspace=str(escape_ws),
                    out=None,
                    style="apa",
                    require_signature=False,
                )
            )
        if rc == 0 or outside_report.exists():
            errors.append("render allowed a plan output outside the workspace")

        # Test 8: plan-derived narrative inputs cannot read outside files.
        outside_input = Path(tmpdir) / "outside-secret.md"
        outside_input.write_text("EXTERNAL SECRET", encoding="utf-8")
        (escape_ws / "report.draft.md").unlink()
        escape_plan["tasks"][0]["inputs"] = ["../outside-secret.md"]
        escape_plan["tasks"][0]["outputs"] = ["research-output/report.md"]
        (escape_ws / "research-plan.json").write_text(
            json.dumps(escape_plan), encoding="utf-8"
        )
        with contextlib.redirect_stderr(_io.StringIO()):
            rc = cmd_render(
                argparse.Namespace(
                    workspace=str(escape_ws),
                    out=None,
                    style="apa",
                    require_signature=False,
                )
            )
        escaped_body = escape_ws / "research-output" / "report.md"
        if rc == 0 or escaped_body.exists():
            errors.append("render allowed a narrative input outside the workspace")

        # Test 9: lint's explicit report path is workspace-contained too.
        with contextlib.redirect_stderr(_io.StringIO()):
            rc = cmd_lint(
                argparse.Namespace(
                    workspace=str(escape_ws),
                    report=str(outside_input),
                    strict=True,
                    allow_unreferenced=False,
                )
            )
        if rc == 0:
            errors.append("lint accepted an explicit report outside the workspace")

        # Test 10: ledger metadata is inert in generated Markdown and HTML.
        hostile_rows = [
            {
                "record_type": "claim",
                "claim": (
                    "claim | <img src=x onerror=alert(1)>\n"
                    + GENERATED_EVIDENCE_END
                    + " SECRET_TOKEN_DO_NOT_LEAK"
                ),
                "source_title": '<script id="title-xss">alert(2)</script>',
                "source_url": "https://example.com/<svg/onload=alert(3)>",
                "confidence": '<img src=x onerror="alert(4)">',
            },
            {
                "record_type": "claim",
                "claim": "invalid URL scheme",
                "source_title": "Unsafe link",
                "source_url": "javascript:alert(5)",
                "confidence": "high",
            },
            {
                "record_type": "claim",
                "claim": "credential URL",
                "source_title": "Credential-bearing source",
                "source_url": "https://user:pass@example.com/private",
                "confidence": "low",
            },
        ]
        hostile_md = "\n".join(
            [*_build_evidence_block(hostile_rows), *_build_references_block(hostile_rows)]
        )
        if hostile_md.count(GENERATED_EVIDENCE_END) != 1:
            errors.append("ledger metadata injected a generated-block marker")
        for active_fragment in ("<script", "<img", "<svg", "javascript:", "user:pass"):
            if active_fragment.lower() in hostile_md.lower():
                errors.append(f"generated Markdown contains active fragment {active_fragment!r}")
        if "REDACTED" not in hostile_md or "SECRET_TOKEN_DO_NOT_LEAK" in hostile_md:
            errors.append("generated Markdown did not redact known secret material")
        if "[invalid URL omitted]" not in hostile_md:
            errors.append("generated Markdown did not omit an unsafe source URL")
        if _has_pandoc():
            hostile_md_path = Path(tmpdir) / "hostile-generated.md"
            hostile_html_path = Path(tmpdir) / "hostile-generated.html"
            hostile_md_path.write_text(hostile_md, encoding="utf-8")
            pandoc_result = subprocess.run(
                [
                    "pandoc",
                    str(hostile_md_path),
                    "--standalone",
                    "-o",
                    str(hostile_html_path),
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if pandoc_result.returncode != 0:
                errors.append("pandoc failed hostile generated-metadata regression")
            else:
                hostile_html = hostile_html_path.read_text(encoding="utf-8")
                active_html = re.search(
                    r"(?is)<(?:script|img|svg)\b[^>]*(?:on\w+\s*=)?",
                    hostile_html,
                )
                if active_html:
                    errors.append(
                        "generated ledger metadata produced an active HTML element: "
                        f"{active_html.group(0)!r}"
                    )

    if errors:
        print("report_render self-test FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("report_render self-test ok")
    return 0


# ---------------------------------------------------------------------------
# Main / argparse
# ---------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(
        prog="report_render.py",
        description="Final report generator for research workspaces.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # init
    init_p = sub.add_parser("init", help="Write report.draft.md skeleton.")
    init_p.add_argument("--workspace", required=True, help="Research workspace directory.")

    # render
    render_p = sub.add_parser("render", help="Produce final report.md.")
    render_p.add_argument("--workspace", required=True, help="Research workspace directory.")
    render_p.add_argument("--style", default="apa", help="Citation style (default: apa).")
    render_p.add_argument("--out", default=None, help="Output path (default: workspace/report.md).")
    render_p.add_argument("--require-signature", action="store_true", default=False,
                          help="Preflight: require a ledger and valid HMAC sidecar.")

    # to-pdf
    pdf_p = sub.add_parser("to-pdf", help="Convert markdown to PDF via pandoc.")
    pdf_p.add_argument("--in", dest="input", required=True, help="Input markdown file.")
    pdf_p.add_argument("--out", required=True, help="Output PDF path.")

    # to-docx
    docx_p = sub.add_parser("to-docx", help="Convert markdown to DOCX via pandoc.")
    docx_p.add_argument("--in", dest="input", required=True, help="Input markdown file.")
    docx_p.add_argument("--out", required=True, help="Output DOCX path.")

    # to-html
    html_p = sub.add_parser("to-html", help="Convert markdown to HTML via pandoc.")
    html_p.add_argument("--in", dest="input", required=True, help="Input markdown file.")
    html_p.add_argument("--out", required=True, help="Output HTML path.")

    # list-styles
    sub.add_parser("list-styles", help="List available citation styles.")

    # lint
    lint_p = sub.add_parser("lint", help="Check workspace for issues.")
    lint_p.add_argument("--workspace", required=True, help="Research workspace directory.")
    lint_p.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Fail when any record_type=claim is unreferenced (release gate default).",
    )
    lint_p.add_argument(
        "--allow-unreferenced",
        action="store_true",
        default=False,
        help="Manual override: warn instead of fail on unreferenced claims. Never used by release gates.",
    )
    lint_p.add_argument(
        "--report",
        default=None,
        help="Exact report path to lint (required by release gates; no fallback).",
    )

    # self-test
    sub.add_parser("self-test", help="Run offline self-tests.")

    args = p.parse_args()

    if args.cmd == "init":
        return cmd_init(args)
    if args.cmd == "render":
        return cmd_render(args)
    if args.cmd == "to-pdf":
        return cmd_to_pdf(args)
    if args.cmd == "to-docx":
        return cmd_to_docx(args)
    if args.cmd == "to-html":
        return cmd_to_html(args)
    if args.cmd == "list-styles":
        return cmd_list_styles(args)
    if args.cmd == "lint":
        return cmd_lint(args)
    if args.cmd == "self-test":
        return cmd_self_test(args)

    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
