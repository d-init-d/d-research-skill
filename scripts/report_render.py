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
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = REPO_ROOT / "templates" / "report-template.md"


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
    """Verify ledger signature if sidecar exists. Returns True if valid."""
    hmac_path = Path(str(ledger_path) + ".hmac")
    if not hmac_path.is_file():
        return True  # No signature = not signed yet

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

    with contextlib.redirect_stdout(_io.StringIO()):
        rc = el_mod.verify_ledger(ledger_path, "D_RESEARCH_LEDGER_KEY", hmac_path)
    return rc == 0


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
        title = plan.get("title", plan.get("slug", "Research Report"))
        tasks = plan.get("tasks", [])
        for task in tasks:
            task_title = task.get("title", task.get("id", "Section"))
            sections.append(f"## {task_title}\n\n<!-- findings from task -->\n")

    # Fill template
    content = template.replace("{{title}}", title)
    content = content.replace("{{date}}", _utc_now())
    content = content.replace("{{sections}}", "\n".join(sections) if sections else "## Findings\n\n<!-- Add findings here -->\n")

    out_path.write_text(content, encoding="utf-8")
    print(f"wrote {out_path}")
    return 0



def cmd_render(args: argparse.Namespace) -> int:
    """Produce final report.md from workspace artifacts."""
    workspace = Path(args.workspace)
    if not workspace.is_dir():
        print(f"error: workspace not found: {workspace}", file=sys.stderr)
        return 1

    ledger_path = workspace / "evidence-ledger.csv"
    plan_path = workspace / "research-plan.json"
    screening_path = workspace / "screening-log.csv"
    out_path = Path(args.out) if args.out else workspace / "report.md"
    require_sig = getattr(args, "require_signature", False)

    # Step 1: Validate ledger schema
    if ledger_path.is_file():
        rc = _validate_ledger(ledger_path)
        if rc != 0:
            print("error: evidence ledger failed schema validation", file=sys.stderr)
            return 1

        # Step 2: Check signature
        hmac_path = Path(str(ledger_path) + ".hmac")
        if hmac_path.is_file():
            if not _verify_signature(ledger_path):
                print("error: ledger signature verification FAILED — refusing to render", file=sys.stderr)
                return 1
        elif require_sig:
            print("error: --require-signature set but no signature sidecar found", file=sys.stderr)
            return 1
        else:
            print("warning: ledger is not signed; rendering without signature verification", file=sys.stderr)

    # Step 3: Build report
    lines: list[str] = []

    # Title from plan
    title = "Research Report"
    if plan_path.is_file():
        plan = _load_json(plan_path)
        title = plan.get("title", plan.get("slug", "Research Report"))

    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"Generated: {_utc_now()}")
    lines.append("")

    # Executive summary placeholder
    lines.append("## Executive Summary")
    lines.append("")
    lines.append("<!-- Replace with synthesis of key findings -->")
    lines.append("")

    # Sections from plan tasks
    if plan_path.is_file():
        plan = _load_json(plan_path)
        tasks = plan.get("tasks", [])
        for task in tasks:
            task_title = task.get("title", task.get("id", "Section"))
            lines.append(f"## {task_title}")
            lines.append("")
            lines.append(f"<!-- Findings for task: {task.get('id', '')} -->")
            lines.append("")

    # Evidence summary from ledger
    if ledger_path.is_file():
        rows = _load_ledger(ledger_path)
        if rows:
            lines.append("## Evidence Summary")
            lines.append("")
            lines.append(f"Total claims: {len(rows)}")
            lines.append("")
            lines.append("| # | Claim | Source | Confidence |")
            lines.append("|---|-------|--------|------------|")
            for i, row in enumerate(rows[:50], 1):  # Cap at 50 for readability
                claim = (row.get("claim", "") or "")[:80]
                source = (row.get("source_url", "") or "")[:60]
                conf = row.get("confidence", "")
                lines.append(f"| {i} | {claim} | {source} | {conf} |")
            if len(rows) > 50:
                lines.append(f"| ... | *{len(rows) - 50} more rows* | | |")
            lines.append("")

    # PRISMA flow if screening log exists
    if screening_path.is_file():
        screening_rows = _load_ledger(screening_path)
        lines.append("## Screening Summary (PRISMA)")
        lines.append("")
        lines.append(f"Total screened: {len(screening_rows)}")
        included = sum(1 for r in screening_rows if r.get("decision", "").lower() == "include")
        excluded = sum(1 for r in screening_rows if r.get("decision", "").lower() == "exclude")
        lines.append(f"Included: {included}")
        lines.append(f"Excluded: {excluded}")
        lines.append("")

    # References section
    lines.append("## References")
    lines.append("")
    if ledger_path.is_file():
        rows = _load_ledger(ledger_path)
        seen_urls: set[str] = set()
        ref_num = 1
        for row in rows:
            url = (row.get("source_url", "") or "").strip()
            title_ref = (row.get("source_title", "") or "").strip()
            if url and url not in seen_urls:
                seen_urls.add(url)
                lines.append(f"{ref_num}. {title_ref or url} — {url}")
                ref_num += 1
        lines.append("")

    # Caveats and limitations
    lines.append("## Caveats and Limitations")
    lines.append("")
    lines.append("<!-- Document limitations, blocked sources, confidence gaps -->")
    lines.append("")

    # Write output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
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
    """Check workspace for missing/unused claims and broken refs."""
    workspace = Path(args.workspace)
    if not workspace.is_dir():
        print(f"error: workspace not found: {workspace}", file=sys.stderr)
        return 1

    errors: list[str] = []
    warnings: list[str] = []

    ledger_path = workspace / "evidence-ledger.csv"
    report_path = workspace / "report.md"
    draft_path = workspace / "report.draft.md"

    # Load ledger claims
    ledger_claims: set[str] = set()
    if ledger_path.is_file():
        rows = _load_ledger(ledger_path)
        for row in rows:
            cid = (row.get("claim_id", "") or "").strip()
            if cid:
                ledger_claims.add(cid)
    else:
        warnings.append("no evidence-ledger.csv found in workspace")

    # Check report for claim references
    report_file = report_path if report_path.is_file() else draft_path
    referenced_claims: set[str] = set()
    if report_file.is_file():
        content = report_file.read_text(encoding="utf-8")
        # Look for [ref:claim_id] patterns
        import re
        refs = re.findall(r"\[ref:([^\]]+)\]", content)
        referenced_claims = set(refs)

        # Claims referenced but not in ledger
        missing = referenced_claims - ledger_claims
        for cid in sorted(missing):
            errors.append(f"claim referenced in report but not in ledger: {cid}")

    # Unused ledger rows (claims in ledger but not referenced)
    if referenced_claims:
        unused = ledger_claims - referenced_claims
        for cid in sorted(unused):
            warnings.append(f"ledger claim not referenced in report: {cid}")

    # Report results
    if warnings:
        for w in warnings:
            print(f"  warning: {w}", file=sys.stderr)
    if errors:
        print(f"FAIL: {len(errors)} lint error(s):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(f"OK: workspace lint passed ({len(ledger_claims)} claims, {len(referenced_claims)} referenced).")
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

        # Test 3: render with valid signature
        # Sign the ledger
        import importlib.util as _ilu
        _el_spec = _ilu.spec_from_file_location(
            "evidence_ledger",
            Path(__file__).resolve().parent / "evidence_ledger.py",
        )
        _el_mod = _ilu.module_from_spec(_el_spec)
        _el_spec.loader.exec_module(_el_mod)

        test_key = "test-key-for-self-test-only-32chars!"
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
                style="apa", require_signature=False
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

        # Clean up env
        del os.environ["D_RESEARCH_LEDGER_KEY"]

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

        # Test 4: lint (no refs in report, so unused claims are warnings only)
        lint_ns = argparse.Namespace(workspace=str(ws))
        rc = cmd_lint(lint_ns)
        if rc != 0:
            errors.append("lint returned non-zero on valid workspace")

        # Test 5: lint with broken ref
        report_with_ref = (ws / "report.md").read_text(encoding="utf-8")
        report_with_ref += "\n[ref:C001] [ref:MISSING_CLAIM]\n"
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
                          help="Hard-fail if ledger has no valid signature.")

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
