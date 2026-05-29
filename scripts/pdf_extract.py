#!/usr/bin/env python3
"""PDF extraction utilities: text, metadata, tables, evidence-ledger row.

This is a thin wrapper around poppler-utils (``pdftotext``, ``pdfinfo``)
for text and metadata extraction, with optional ``pdfplumber`` support
for table extraction.

Subcommands
-----------
* ``text``       - extract full text from a PDF
* ``meta``       - extract metadata as JSON
* ``tables``     - extract tables as CSV files (requires pdfplumber)
* ``to-ledger``  - generate an evidence-ledger CSV row from a PDF
* ``self-test``  - run offline self-tests against the test fixture

Prerequisites
-------------
System binaries (poppler-utils):
  Debian/Ubuntu: sudo apt-get install -y poppler-utils
  macOS:         brew install poppler

Optional Python package (for tables subcommand only):
  pip install pdfplumber
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def check_binary(name: str) -> None:
    """Exit with clear error if system binary is not on PATH."""
    if not shutil.which(name):
        print(
            f"error: {name} not found on PATH\n"
            f"  hint: install with: sudo apt-get install poppler-utils",
            file=sys.stderr,
        )
        sys.exit(2)


def parse_pdfinfo(raw: str) -> dict:
    """Parse pdfinfo key:value output into a dict with normalized keys.

    Handles multi-word keys (e.g. "Creation Date") and maps them to
    snake_case JSON keys. The ``page_count`` field is converted to int.
    """
    # Map pdfinfo keys to our normalized JSON keys
    key_map = {
        "title": "title",
        "author": "author",
        "creator": "creator",
        "producer": "producer",
        "creationdate": "creation_date",
        "moddate": "modification_date",
        "pages": "page_count",
    }

    parsed: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        # Split on first colon only (values may contain colons)
        key_part, _, value_part = line.partition(":")
        normalized_key = key_part.strip().lower().replace(" ", "")
        value = value_part.strip()
        if normalized_key in key_map:
            parsed[key_map[normalized_key]] = value

    # Build result with all expected keys
    result: dict = {
        "title": parsed.get("title") or None,
        "author": parsed.get("author") or None,
        "creation_date": parsed.get("creation_date") or None,
        "modification_date": parsed.get("modification_date") or None,
        "page_count": 0,
        "producer": parsed.get("producer") or None,
        "creator": parsed.get("creator") or None,
    }

    # Convert page_count to int
    pages_str = parsed.get("page_count", "0")
    try:
        result["page_count"] = int(pages_str)
    except (ValueError, TypeError):
        result["page_count"] = 0

    return result


def cmd_text(args: argparse.Namespace) -> int:
    """Extract full text via pdftotext. Write to stdout or --out."""
    check_binary("pdftotext")

    pdf_path = Path(args.input)
    if not pdf_path.is_file():
        print(f"error: file not found: {pdf_path}", file=sys.stderr)
        return 1

    # pdftotext <input> - (dash means stdout)
    cmd = ["pdftotext", str(pdf_path), "-"]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )

    if proc.returncode != 0:
        snippet = proc.stderr.strip()[:200] if proc.stderr else "unknown error"
        print(
            f"error: pdftotext failed (exit {proc.returncode}): {snippet}",
            file=sys.stderr,
        )
        return 1

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(proc.stdout, encoding="utf-8")
    else:
        sys.stdout.write(proc.stdout)

    return 0


def cmd_meta(args: argparse.Namespace) -> int:
    """Extract metadata via pdfinfo. Output JSON to stdout or --out."""
    check_binary("pdfinfo")

    pdf_path = Path(args.input)
    if not pdf_path.is_file():
        print(f"error: file not found: {pdf_path}", file=sys.stderr)
        return 1

    cmd = ["pdfinfo", str(pdf_path)]
    proc = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )

    if proc.returncode != 0:
        snippet = proc.stderr.strip()[:200] if proc.stderr else "unknown error"
        print(
            f"error: pdfinfo failed (exit {proc.returncode}): {snippet}",
            file=sys.stderr,
        )
        return 1

    meta = parse_pdfinfo(proc.stdout)
    output = json.dumps(meta, indent=2, ensure_ascii=False)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)

    return 0


def cmd_tables(args: argparse.Namespace) -> int:
    """Extract tables via pdfplumber. Write CSVs to --out-dir."""
    try:
        import pdfplumber  # noqa: F401 — soft dependency
    except ImportError:
        print(
            "warning: pdfplumber not installed; table extraction skipped\n"
            "  hint: install with: pip install pdfplumber",
            file=sys.stderr,
        )
        return 0

    pdf_path = Path(args.input)
    if not pdf_path.is_file():
        print(f"error: file not found: {pdf_path}", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            if not tables:
                continue
            for table_idx, table in enumerate(tables, start=1):
                csv_name = f"p{page_idx}_t{table_idx}.csv"
                csv_path = out_dir / csv_name
                with csv_path.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    for row in table:
                        # Replace None cells with empty string
                        writer.writerow([(cell if cell is not None else "") for cell in row])

    return 0


def format_ledger_row(meta: dict, text: str, url: str) -> dict:
    """Build a dict matching templates/evidence-ledger.csv column schema.

    Args:
        meta: Parsed PDF metadata dict (from parse_pdfinfo).
        text: Full extracted text from the PDF.
        url: Source URL for the PDF.

    Returns:
        Dict with keys matching the evidence-ledger.csv header columns.
    """
    # Generate claim_id from hash of url + title
    hash_input = f"{url}:{meta.get('title') or ''}"
    content_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
    claim_id = f"PDF_{content_hash[:8]}"

    # Derive source_title from metadata title or filename
    source_title = meta.get("title") or ""

    # Derive claim text
    claim = f"Extracted from: {source_title}" if source_title else "Extracted from: unknown PDF"

    # Evidence: first 500 chars of extracted text
    evidence = text[:500] if text else ""

    # date_published from creation_date or empty
    date_published = meta.get("creation_date") or ""

    # date_accessed is today in ISO 8601
    date_accessed = datetime.date.today().isoformat()

    prov_seed = f"pdf_extract|{url or source_title}".encode("utf-8")
    prov_id = f"prov:pdf_extract:{hashlib.sha256(prov_seed).hexdigest()[:8]}"

    return {
        "claim_id": claim_id,
        "claim": claim,
        "sub_question": "",
        "source_title": source_title,
        "source_url": url,
        "source_type": "pdf",
        "date_published": date_published,
        "date_accessed": date_accessed,
        "access_method": "pdf_extract",
        "evidence": evidence,
        "quote_or_anchor": "",
        "contradiction": "none",
        "confidence": "medium",
        "notes": "Auto-generated by pdf_extract.py to-ledger",
        "archive_url": "",
        "content_hash": "",
        "snapshot_status": "",
        "verifiability": "",
        "verifiability_note": "",
        "license_spdx": "NOASSERTION",
        "robots_status": "not_applicable",
        "prov_activity_id": prov_id,
    }


def cmd_to_ledger(args: argparse.Namespace) -> int:
    """Generate evidence-ledger CSV row from PDF metadata + text snippet."""
    check_binary("pdfinfo")
    check_binary("pdftotext")

    pdf_path = Path(args.input)
    if not pdf_path.is_file():
        print(f"error: file not found: {pdf_path}", file=sys.stderr)
        return 1

    # Extract metadata via pdfinfo
    meta_proc = subprocess.run(
        ["pdfinfo", str(pdf_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if meta_proc.returncode != 0:
        snippet = meta_proc.stderr.strip()[:200] if meta_proc.stderr else "unknown error"
        print(
            f"error: pdfinfo failed (exit {meta_proc.returncode}): {snippet}",
            file=sys.stderr,
        )
        return 1

    meta = parse_pdfinfo(meta_proc.stdout)

    # Extract text via pdftotext
    text_proc = subprocess.run(
        ["pdftotext", str(pdf_path), "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if text_proc.returncode != 0:
        snippet = text_proc.stderr.strip()[:200] if text_proc.stderr else "unknown error"
        print(
            f"error: pdftotext failed (exit {text_proc.returncode}): {snippet}",
            file=sys.stderr,
        )
        return 1

    text = text_proc.stdout

    # Build ledger row
    row = format_ledger_row(meta, text, args.url)

    # Write/append to CSV file
    out_path = Path(args.out_row)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Determine if we need to write the header
    write_header = not out_path.is_file() or out_path.stat().st_size == 0

    fieldnames = [
        "claim_id", "claim", "sub_question", "source_title", "source_url",
        "source_type", "date_published", "date_accessed", "access_method",
        "evidence", "quote_or_anchor", "contradiction", "confidence", "notes",
        "archive_url", "content_hash", "snapshot_status", "verifiability",
        "verifiability_note",
        "license_spdx", "robots_status", "prov_activity_id",
    ]

    with out_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    return 0


def cmd_self_test(args: argparse.Namespace) -> int:
    """Offline self-test using examples/fixtures/test.pdf."""
    missing = [name for name in ("pdftotext", "pdfinfo") if not shutil.which(name)]
    if missing:
        print(
            "pdf_extract self-test ok (skipped: missing poppler-utils binaries "
            f"{', '.join(missing)})",
        )
        return 0

    # Resolve fixture path relative to this script's location
    script_dir = Path(__file__).resolve().parent
    fixture = script_dir.parent / "examples" / "fixtures" / "test.pdf"

    # Step 1: Verify fixture exists and is ≤ 10 KB
    if not fixture.is_file():
        print(f"error: test fixture not found: {fixture}", file=sys.stderr)
        return 1

    size_kb = fixture.stat().st_size / 1024
    if size_kb > 10:
        print(
            f"error: test fixture too large ({size_kb:.1f} KB > 10 KB)",
            file=sys.stderr,
        )
        return 1

    # Use a temporary directory for all output files
    with tempfile.TemporaryDirectory(prefix="pdf_extract_selftest_") as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Step 2: Run cmd_text against fixture → assert non-empty output
        text_out = tmp_path / "text_output.txt"
        text_args = argparse.Namespace(input=str(fixture), out=str(text_out))
        rc = cmd_text(text_args)
        if rc != 0:
            print("error: self-test failed: text subcommand returned non-zero", file=sys.stderr)
            return 1
        if not text_out.is_file() or text_out.stat().st_size == 0:
            print("error: self-test failed: text subcommand produced empty output", file=sys.stderr)
            return 1

        # Step 3: Run cmd_meta against fixture → assert valid JSON with required keys
        meta_out = tmp_path / "meta_output.json"
        meta_args = argparse.Namespace(input=str(fixture), out=str(meta_out))
        rc = cmd_meta(meta_args)
        if rc != 0:
            print("error: self-test failed: meta subcommand returned non-zero", file=sys.stderr)
            return 1
        if not meta_out.is_file() or meta_out.stat().st_size == 0:
            print("error: self-test failed: meta subcommand produced empty output", file=sys.stderr)
            return 1

        meta_content = meta_out.read_text(encoding="utf-8")
        try:
            meta_dict = json.loads(meta_content)
        except json.JSONDecodeError as e:
            print(f"error: self-test failed: meta output is not valid JSON: {e}", file=sys.stderr)
            return 1

        required_keys = {"title", "author", "creation_date", "modification_date", "page_count"}
        missing_keys = required_keys - set(meta_dict.keys())
        if missing_keys:
            print(
                f"error: self-test failed: meta output missing keys: {sorted(missing_keys)}",
                file=sys.stderr,
            )
            return 1

        # Step 4: Run cmd_to_ledger against fixture → assert valid CSV row with all columns
        ledger_out = tmp_path / "ledger_output.csv"
        ledger_args = argparse.Namespace(
            input=str(fixture),
            url="https://example.com/test.pdf",
            out_row=str(ledger_out),
        )
        rc = cmd_to_ledger(ledger_args)
        if rc != 0:
            print("error: self-test failed: to-ledger subcommand returned non-zero", file=sys.stderr)
            return 1
        if not ledger_out.is_file() or ledger_out.stat().st_size == 0:
            print("error: self-test failed: to-ledger subcommand produced empty output", file=sys.stderr)
            return 1

        # Verify CSV has header + at least one data row with all expected columns
        expected_columns = [
            "claim_id", "claim", "sub_question", "source_title", "source_url",
            "source_type", "date_published", "date_accessed", "access_method",
            "evidence", "quote_or_anchor", "contradiction", "confidence", "notes",
            "archive_url", "content_hash", "snapshot_status", "verifiability",
            "verifiability_note",
            "license_spdx", "robots_status", "prov_activity_id",
        ]
        with ledger_out.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                print("error: self-test failed: to-ledger CSV has no header", file=sys.stderr)
                return 1
            missing_cols = set(expected_columns) - set(reader.fieldnames)
            if missing_cols:
                print(
                    f"error: self-test failed: to-ledger CSV missing columns: {sorted(missing_cols)}",
                    file=sys.stderr,
                )
                return 1
            rows = list(reader)
            if len(rows) == 0:
                print("error: self-test failed: to-ledger CSV has no data rows", file=sys.stderr)
                return 1
        try:
            from evidence_ledger import validate_ledger
        except ImportError as exc:
            print(f"error: self-test failed: could not import evidence_ledger: {exc}", file=sys.stderr)
            return 1
        if validate_ledger(ledger_out) != 0:
            print("error: self-test failed: generated ledger did not validate", file=sys.stderr)
            return 1

        # Step 5: If pdfplumber importable, run cmd_tables against fixture
        try:
            import pdfplumber  # noqa: F401

            tables_dir = tmp_path / "tables_out"
            tables_args = argparse.Namespace(input=str(fixture), out_dir=str(tables_dir))
            rc = cmd_tables(tables_args)
            if rc != 0:
                print("error: self-test failed: tables subcommand returned non-zero", file=sys.stderr)
                return 1
            # Check that at least one CSV was created (fixture has a table)
            csv_files = list(tables_dir.glob("*.csv")) if tables_dir.is_dir() else []
            if not csv_files:
                print(
                    "warning: tables subcommand produced no CSV files (fixture may lack detectable tables)",
                    file=sys.stderr,
                )
        except ImportError:
            pass  # pdfplumber not available, skip tables test

    # Step 6: All checks passed
    print("pdf_extract self-test ok")
    return 0


def main() -> int:
    """Argparse setup with subcommands."""
    p = argparse.ArgumentParser(
        prog="pdf_extract.py",
        description="PDF extraction utilities: text, metadata, tables, evidence-ledger row.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # --- text subcommand ---
    text_p = sub.add_parser("text", help="Extract full text from a PDF.")
    text_p.add_argument(
        "--in", dest="input", required=True, help="Path to input PDF file."
    )
    text_p.add_argument(
        "--out", default=None, help="Write output to this file (default: stdout)."
    )

    # --- meta subcommand ---
    meta_p = sub.add_parser("meta", help="Extract metadata as JSON.")
    meta_p.add_argument(
        "--in", dest="input", required=True, help="Path to input PDF file."
    )
    meta_p.add_argument(
        "--out", default=None, help="Write JSON to this file (default: stdout)."
    )

    # --- tables subcommand ---
    tables_p = sub.add_parser(
        "tables", help="Extract tables as CSV files (requires pdfplumber)."
    )
    tables_p.add_argument(
        "--in", dest="input", required=True, help="Path to input PDF file."
    )
    tables_p.add_argument(
        "--out-dir", required=True, help="Directory to write CSV files."
    )

    # --- to-ledger subcommand ---
    ledger_p = sub.add_parser(
        "to-ledger", help="Generate an evidence-ledger CSV row from a PDF."
    )
    ledger_p.add_argument(
        "--in", dest="input", required=True, help="Path to input PDF file."
    )
    ledger_p.add_argument("--url", required=True, help="Source URL for the PDF.")
    ledger_p.add_argument(
        "--out-row", required=True, help="CSV file to append the ledger row to."
    )

    # --- self-test subcommand ---
    sub.add_parser("self-test", help="Run offline self-tests.")

    args = p.parse_args()

    if args.cmd == "text":
        return cmd_text(args)
    if args.cmd == "meta":
        return cmd_meta(args)
    if args.cmd == "tables":
        return cmd_tables(args)
    if args.cmd == "to-ledger":
        return cmd_to_ledger(args)
    if args.cmd == "self-test":
        return cmd_self_test(args)

    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
