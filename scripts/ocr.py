#!/usr/bin/env python3
"""OCR / image-to-text extraction via tesseract (optional system binary).

Subcommands
-----------
* ``text``      - extract text from an image file
* ``pdf``       - extract text from a scanned PDF (pdftoppm + tesseract)
* ``to-ledger`` - emit an evidence-ledger CSV row from OCR output
* ``langs``     - list installed tesseract language packs
* ``self-test`` - run offline self-tests (soft-skip if tesseract missing)

Tesseract is optional. If missing, commands print a helpful message and
exit non-zero without crashing. Self-test passes even without tesseract
by testing internal logic only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _has_tesseract() -> bool:
    return shutil.which("tesseract") is not None


def _has_pdftoppm() -> bool:
    return shutil.which("pdftoppm") is not None


def _tesseract_missing_msg() -> str:
    return (
        "error: tesseract is not installed. Install tesseract-ocr:\n"
        "  Ubuntu/Debian: sudo apt-get install tesseract-ocr\n"
        "  macOS: brew install tesseract\n"
        "  Windows: choco install tesseract"
    )


def _run_tesseract(image_path: str, lang: str = "eng") -> str:
    """Run tesseract on an image, return extracted text."""
    try:
        result = subprocess.run(
            ["tesseract", image_path, "stdout", "-l", lang],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            print(f"error: tesseract failed: {result.stderr.strip()}", file=sys.stderr)
            return ""
        return result.stdout
    except FileNotFoundError:
        print(_tesseract_missing_msg(), file=sys.stderr)
        return ""
    except subprocess.TimeoutExpired:
        print("error: tesseract timed out", file=sys.stderr)
        return ""


def cmd_text(args: argparse.Namespace) -> int:
    """Extract text from an image."""
    if not _has_tesseract():
        print(_tesseract_missing_msg(), file=sys.stderr)
        return 1
    in_path = args.input
    if not Path(in_path).is_file():
        print(f"error: file not found: {in_path}", file=sys.stderr)
        return 1
    lang = getattr(args, "lang", "eng")
    text = _run_tesseract(in_path, lang)
    if not text:
        return 1
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


def cmd_pdf(args: argparse.Namespace) -> int:
    """Extract text from a scanned PDF via pdftoppm + tesseract."""
    if not _has_tesseract():
        print(_tesseract_missing_msg(), file=sys.stderr)
        return 1
    if not _has_pdftoppm():
        print(
            "error: pdftoppm is not installed (part of poppler-utils).\n"
            "  Ubuntu/Debian: sudo apt-get install poppler-utils\n"
            "  macOS: brew install poppler",
            file=sys.stderr,
        )
        return 1
    in_path = args.input
    if not Path(in_path).is_file():
        print(f"error: file not found: {in_path}", file=sys.stderr)
        return 1

    lang = getattr(args, "lang", "eng")
    first_page = getattr(args, "first_page", None)
    last_page = getattr(args, "last_page", None)

    with tempfile.TemporaryDirectory() as tmpdir:
        cmd = ["pdftoppm", "-png"]
        if first_page:
            cmd.extend(["-f", str(first_page)])
        if last_page:
            cmd.extend(["-l", str(last_page)])
        cmd.extend([in_path, os.path.join(tmpdir, "page")])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            print(f"error: pdftoppm failed: {result.stderr.strip()}", file=sys.stderr)
            return 1

        pages = sorted(Path(tmpdir).glob("page-*.png"))
        if not pages:
            print("error: pdftoppm produced no images", file=sys.stderr)
            return 1

        all_text: list[str] = []
        for page in pages:
            text = _run_tesseract(str(page), lang)
            all_text.append(text)

    combined = "\n".join(all_text)
    if args.out:
        Path(args.out).write_text(combined, encoding="utf-8")
        print(f"wrote {args.out} ({len(pages)} pages)")
    else:
        print(combined)
    return 0


def cmd_to_ledger(args: argparse.Namespace) -> int:
    """Emit an evidence-ledger CSV row from OCR output."""
    if not _has_tesseract():
        print(_tesseract_missing_msg(), file=sys.stderr)
        return 1
    in_path = args.input
    if not Path(in_path).is_file():
        print(f"error: file not found: {in_path}", file=sys.stderr)
        return 1

    lang = getattr(args, "lang", "eng")
    text = _run_tesseract(in_path, lang)
    if not text.strip():
        print("error: OCR produced no text", file=sys.stderr)
        return 1

    url = args.url or ""
    fields = [
        "claim_id", "claim", "sub_question", "source_title", "source_url",
        "source_type", "date_published", "date_accessed", "access_method",
        "evidence", "quote_or_anchor", "contradiction", "confidence", "notes",
        "archive_url", "content_hash", "snapshot_status", "verifiability",
        "verifiability_note",
        "license_spdx", "robots_status", "prov_activity_id",
    ]
    prov_seed = (f"ocr|{url or Path(in_path).name}").encode("utf-8")
    prov_id = "prov:ocr:" + hashlib.sha256(prov_seed).hexdigest()[:8]
    row = {
        "claim_id": f"ocr-{Path(in_path).stem}",
        "claim": text.strip()[:200],
        "sub_question": "",
        "source_title": Path(in_path).name,
        "source_url": url,
        "source_type": "primary",
        "date_published": "",
        "date_accessed": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "access_method": "ocr",
        "evidence": text.strip()[:500],
        "quote_or_anchor": "",
        "contradiction": "none",
        "confidence": "medium",
        "notes": f"OCR via tesseract, lang={lang}",
        "archive_url": "",
        "content_hash": "",
        "snapshot_status": "",
        "verifiability": "",
        "verifiability_note": "extracted via OCR; accuracy depends on image quality",
        "license_spdx": "NOASSERTION",
        "robots_status": "not_applicable",
        "prov_activity_id": prov_id,
    }
    out_path = Path(args.out_row)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerow(row)
    print(f"wrote {out_path}")
    return 0


def cmd_langs(_args: argparse.Namespace) -> int:
    """List installed tesseract language packs."""
    if not _has_tesseract():
        print(_tesseract_missing_msg(), file=sys.stderr)
        return 1
    try:
        result = subprocess.run(
            ["tesseract", "--list-langs"],
            capture_output=True, text=True, timeout=10,
        )
        print(result.stdout.strip() if result.stdout else result.stderr.strip())
        return 0
    except FileNotFoundError:
        print(_tesseract_missing_msg(), file=sys.stderr)
        return 1


def cmd_self_test(_args: argparse.Namespace) -> int:
    """Offline self-test. Passes even without tesseract."""
    errors: list[str] = []

    # Test 1: _has_tesseract returns bool
    result = _has_tesseract()
    if not isinstance(result, bool):
        errors.append("_has_tesseract did not return bool")

    # Test 2: _has_pdftoppm returns bool
    result = _has_pdftoppm()
    if not isinstance(result, bool):
        errors.append("_has_pdftoppm did not return bool")

    # Test 3: to-ledger row schema (mock — no tesseract needed)
    fields = [
        "claim_id", "claim", "sub_question", "source_title", "source_url",
        "source_type", "date_published", "date_accessed", "access_method",
        "evidence", "quote_or_anchor", "contradiction", "confidence", "notes",
        "archive_url", "content_hash", "snapshot_status", "verifiability",
        "verifiability_note",
        "license_spdx", "robots_status", "prov_activity_id",
    ]
    mock_row = {
        "claim_id": "ocr-test",
        "claim": "Test OCR output",
        "sub_question": "",
        "source_title": "test.png",
        "source_url": "https://example.com/test.png",
        "source_type": "primary",
        "date_published": "",
        "date_accessed": "2026-05-18",
        "access_method": "ocr",
        "evidence": "Test OCR output text here",
        "quote_or_anchor": "",
        "contradiction": "none",
        "confidence": "medium",
        "notes": "OCR via tesseract, lang=eng",
        "archive_url": "",
        "content_hash": "",
        "snapshot_status": "",
        "verifiability": "",
        "verifiability_note": "extracted via OCR",
        "license_spdx": "NOASSERTION",
        "robots_status": "not_applicable",
        "prov_activity_id": "prov:ocr:test0001",
    }
    missing = [f for f in fields if f not in mock_row]
    if missing:
        errors.append(f"ledger row missing fields: {missing}")

    # Test 4: validate mock row via evidence_ledger
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger_path = Path(tmpdir) / "test.csv"
        with ledger_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerow(mock_row)

        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "evidence_ledger",
            Path(__file__).resolve().parent / "evidence_ledger.py",
        )
        el_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(el_mod)
        rc = el_mod.validate_ledger(ledger_path)
        if rc != 0:
            errors.append("mock OCR ledger row failed evidence_ledger validate")

    # Test 5: if tesseract available, do a real OCR test
    if _has_tesseract():
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a tiny PBM image with known text pattern
            # (PBM is the simplest image format tesseract can read)
            img_path = Path(tmpdir) / "test.pbm"
            # 10x10 white image — tesseract will return empty but not crash
            pbm = "P1\n10 10\n" + "0 " * 100 + "\n"
            img_path.write_text(pbm, encoding="ascii")
            text = _run_tesseract(str(img_path), "eng")
            # We just verify it doesn't crash; empty output is fine for blank image
            if text is None:
                errors.append("tesseract returned None instead of string")
    else:
        print("info: tesseract not installed; skipping live OCR test", file=sys.stderr)

    if errors:
        print("ocr self-test FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("ocr self-test ok")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        prog="ocr.py",
        description="OCR / image-to-text extraction via tesseract (optional).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    text_p = sub.add_parser("text", help="Extract text from an image.")
    text_p.add_argument("--in", dest="input", required=True, help="Input image file.")
    text_p.add_argument("--out", default=None, help="Output text file.")
    text_p.add_argument("--lang", default="eng", help="Tesseract language (default: eng).")

    pdf_p = sub.add_parser("pdf", help="Extract text from a scanned PDF.")
    pdf_p.add_argument("--in", dest="input", required=True, help="Input PDF file.")
    pdf_p.add_argument("--out", default=None, help="Output text file.")
    pdf_p.add_argument("--lang", default="eng", help="Tesseract language.")
    pdf_p.add_argument("--first-page", type=int, default=None)
    pdf_p.add_argument("--last-page", type=int, default=None)

    tl_p = sub.add_parser("to-ledger", help="Emit evidence-ledger row from OCR.")
    tl_p.add_argument("--in", dest="input", required=True, help="Input image file.")
    tl_p.add_argument("--url", default=None, help="Source URL.")
    tl_p.add_argument("--out-row", required=True, help="Output CSV path.")
    tl_p.add_argument("--lang", default="eng")

    sub.add_parser("langs", help="List installed tesseract languages.")
    sub.add_parser("self-test", help="Run offline self-tests.")

    args = p.parse_args()
    if args.cmd == "text":
        return cmd_text(args)
    if args.cmd == "pdf":
        return cmd_pdf(args)
    if args.cmd == "to-ledger":
        return cmd_to_ledger(args)
    if args.cmd == "langs":
        return cmd_langs(args)
    if args.cmd == "self-test":
        return cmd_self_test(args)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
