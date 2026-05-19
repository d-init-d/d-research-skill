#!/usr/bin/env python3
"""Multi-format extraction: DOCX, EPUB, XLSX, mbox, HTML structured.

Subcommands
-----------
* ``text``       - extract text from any supported format
* ``meta``       - extract metadata (title, author, dates)
* ``tables``     - extract tables (XLSX sheets, DOCX tables)
* ``structured`` - extract JSON-LD, microdata, and RDFa from HTML
* ``mbox-search``- search mbox archive by query/from/date
* ``to-ledger``  - emit evidence-ledger CSV row
* ``self-test``  - run offline self-tests

Backends:
- DOCX/EPUB: pandoc (soft-fail if missing)
- XLSX: stdlib zipfile + sharedStrings.xml + worksheets
- mbox: stdlib mailbox
- HTML structured: stdlib html.parser
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import email.utils
import html.parser
import json
import mailbox
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

def _detect_format(path: Path) -> str:
    ext = path.suffix.lower()
    fmt_map = {
        ".docx": "docx", ".epub": "epub", ".xlsx": "xlsx",
        ".mbox": "mbox", ".html": "html", ".htm": "html",
        ".xhtml": "html",
    }
    return fmt_map.get(ext, "unknown")


# ---------------------------------------------------------------------------
# XLSX extraction (stdlib only)
# ---------------------------------------------------------------------------

def _xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    """Extract shared strings from XLSX."""
    try:
        xml_data = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(xml_data)
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings: list[str] = []
    for si in root.findall(".//s:si", ns):
        parts = []
        for t_el in si.iter():
            if t_el.text:
                parts.append(t_el.text)
        strings.append("".join(parts))
    return strings


def _col_index(ref: str) -> int:
    """Convert cell reference like 'A1', 'C1', 'AA3' to 0-based column index."""
    col_str = ""
    for ch in ref:
        if ch.isalpha():
            col_str += ch
        else:
            break
    if not col_str:
        return 0
    idx = 0
    for ch in col_str.upper():
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def _xlsx_sheet_text(zf: zipfile.ZipFile, sheet_path: str, shared: list[str]) -> list[list[str]]:
    """Extract cell values from one XLSX sheet, preserving sparse columns."""
    try:
        xml_data = zf.read(sheet_path)
    except KeyError:
        return []
    root = ET.fromstring(xml_data)
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    rows: list[list[str]] = []
    for row_el in root.findall(".//s:sheetData/s:row", ns):
        max_col = 0
        cell_data: list[tuple[int, str]] = []
        for c in row_el.findall("s:c", ns):
            r_attr = c.get("r", "")
            col_idx = _col_index(r_attr) if r_attr else len(cell_data)
            t = c.get("t", "")
            val = ""
            if t == "s":
                # Shared string reference
                v_el = c.find("s:v", ns)
                if v_el is not None and v_el.text and v_el.text.isdigit():
                    idx = int(v_el.text)
                    val = shared[idx] if idx < len(shared) else ""
            elif t == "inlineStr":
                # Inline string: <is><t>text</t></is> or rich text runs
                is_el = c.find("s:is", ns)
                if is_el is not None:
                    parts = []
                    for t_el in is_el.iter():
                        if t_el.text:
                            parts.append(t_el.text)
                    val = "".join(parts)
            else:
                # Numeric or cached value
                v_el = c.find("s:v", ns)
                if v_el is not None and v_el.text:
                    val = v_el.text
            cell_data.append((col_idx, val))
            if col_idx > max_col:
                max_col = col_idx
        # Build row with proper column positions
        row = [""] * (max_col + 1)
        for col_idx, val in cell_data:
            row[col_idx] = val
        rows.append(row)
    return rows


def _extract_xlsx_text(path: Path) -> str:
    """Extract all text from XLSX using stdlib zipfile."""
    with zipfile.ZipFile(path) as zf:
        shared = _xlsx_shared_strings(zf)
        sheets = sorted(n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
        all_text: list[str] = []
        for sheet in sheets:
            rows = _xlsx_sheet_text(zf, sheet, shared)
            for row in rows:
                all_text.append("\t".join(row))
    return "\n".join(all_text)

def _extract_xlsx_tables(path: Path, out_dir: Path) -> int:
    """Extract each XLSX sheet as a CSV file."""
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as zf:
        shared = _xlsx_shared_strings(zf)
        sheets = sorted(n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
        for i, sheet in enumerate(sheets, 1):
            rows = _xlsx_sheet_text(zf, sheet, shared)
            csv_path = out_dir / f"sheet{i}.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                for row in rows:
                    writer.writerow(row)
    return len(sheets)


# ---------------------------------------------------------------------------
# DOCX/EPUB via pandoc
# ---------------------------------------------------------------------------

def _has_pandoc() -> bool:
    return shutil.which("pandoc") is not None


def _pandoc_to_text(path: Path) -> str:
    """Convert DOCX/EPUB to plain text via pandoc."""
    if not _has_pandoc():
        print(
            "error: pandoc is not installed (needed for DOCX/EPUB extraction).\n"
            "  Ubuntu/Debian: sudo apt-get install pandoc\n"
            "  macOS: brew install pandoc",
            file=sys.stderr,
        )
        return ""
    try:
        result = subprocess.run(
            ["pandoc", str(path), "-t", "plain", "--wrap=none"],
            capture_output=True, text=True, timeout=60,
        )
        return result.stdout if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


# ---------------------------------------------------------------------------
# mbox extraction (stdlib)
# ---------------------------------------------------------------------------

def _mbox_search(path: Path, query: str, from_addr: str = "", date_filter: str = "") -> list[dict[str, str]]:
    """Search mbox by query string, optional from/date filter."""
    results: list[dict[str, str]] = []
    mbox_obj = mailbox.mbox(str(path))
    query_lower = query.lower()
    for msg in mbox_obj:
        subject = msg.get("Subject", "")
        from_hdr = msg.get("From", "")
        date_hdr = msg.get("Date", "")
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        body = payload.decode("utf-8", errors="replace")
                    break
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body = payload.decode("utf-8", errors="replace")

        # Apply filters
        if from_addr and from_addr.lower() not in from_hdr.lower():
            continue
        if date_filter:
            parsed_date = email.utils.parsedate_to_datetime(date_hdr) if date_hdr else None
            if parsed_date and not str(parsed_date.date()).startswith(date_filter):
                continue
        # Query match
        searchable = f"{subject} {body}".lower()
        if query_lower in searchable:
            results.append({
                "from": from_hdr,
                "date": date_hdr,
                "subject": subject,
                "body_preview": body[:300],
            })
    return results


# ---------------------------------------------------------------------------
# HTML structured data extraction
# ---------------------------------------------------------------------------

class _JsonLdExtractor(html.parser.HTMLParser):
    """Extract JSON-LD from <script type="application/ld+json"> tags."""

    def __init__(self) -> None:
        super().__init__()
        self._in_jsonld = False
        self._data: list[str] = []
        self.results: list[Any] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            attr_dict = dict(attrs)
            if attr_dict.get("type") == "application/ld+json":
                self._in_jsonld = True
                self._data = []

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._data.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_jsonld:
            self._in_jsonld = False
            raw = "".join(self._data)
            try:
                self.results.append(json.loads(raw))
            except json.JSONDecodeError:
                pass


class _MicrodataExtractor(html.parser.HTMLParser):
    """Extract basic microdata (itemscope/itemtype/itemprop)."""

    def __init__(self) -> None:
        super().__init__()
        self._stack: list[dict[str, Any]] = []
        self.items: list[dict[str, Any]] = []
        self._current_prop: str | None = None
        self._prop_data: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        if "itemscope" in attr_dict or ("itemscope", None) in attrs:
            item: dict[str, Any] = {"type": attr_dict.get("itemtype", ""), "properties": {}}
            self._stack.append(item)
        if "itemprop" in attr_dict and self._stack:
            prop_name = attr_dict.get("itemprop", "")
            # Check for value in content/href/src attributes
            for val_attr in ("content", "href", "src"):
                if val_attr in attr_dict:
                    self._stack[-1]["properties"][prop_name] = attr_dict[val_attr]
                    return
            self._current_prop = prop_name
            self._prop_data = []

    def handle_data(self, data: str) -> None:
        if self._current_prop is not None:
            self._prop_data.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._current_prop and self._stack:
            val = "".join(self._prop_data).strip()
            if val:
                self._stack[-1]["properties"][self._current_prop] = val
            self._current_prop = None
            self._prop_data = []
        # Note: simplified — doesn't track nested itemscope depth perfectly
        # but sufficient for basic extraction

    def close(self) -> None:
        super().close()
        self.items.extend(self._stack)


def _extract_rdfa(content: str) -> list[dict[str, str]]:
    """Extract basic RDFa (typeof/property/content) via regex."""
    items: list[dict[str, str]] = []
    # Find elements with typeof
    typeof_pattern = re.compile(r'<[^>]+\btypeof="([^"]*)"[^>]*>(.*?)</\w+>', re.DOTALL)
    for m in typeof_pattern.finditer(content):
        items.append({"typeof": m.group(1), "text": re.sub(r"<[^>]+>", "", m.group(2)).strip()[:200]})
    # Find elements with property + content
    prop_pattern = re.compile(r'<[^>]+\bproperty="([^"]*)"[^>]*\bcontent="([^"]*)"[^>]*/?>')
    for m in prop_pattern.finditer(content):
        items.append({"property": m.group(1), "content": m.group(2)})
    return items


def _extract_structured_html(path: Path) -> dict[str, Any]:
    """Extract JSON-LD, microdata, and RDFa from HTML."""
    content = path.read_text(encoding="utf-8", errors="replace")

    # JSON-LD
    jsonld_parser = _JsonLdExtractor()
    jsonld_parser.feed(content)

    # Microdata
    micro_parser = _MicrodataExtractor()
    micro_parser.feed(content)
    micro_parser.close()

    # RDFa
    rdfa_items = _extract_rdfa(content)

    return {
        "json_ld": jsonld_parser.results,
        "microdata": micro_parser.items,
        "rdfa": rdfa_items,
        "source": str(path),
    }


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------

def cmd_text(args: argparse.Namespace) -> int:
    path = Path(args.input)
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1
    fmt = _detect_format(path)
    text = ""
    if fmt in ("docx", "epub"):
        text = _pandoc_to_text(path)
        if not text:
            return 1
    elif fmt == "xlsx":
        text = _extract_xlsx_text(path)
    elif fmt == "mbox":
        mbox_obj = mailbox.mbox(str(path))
        parts: list[str] = []
        for msg in mbox_obj:
            parts.append(f"Subject: {msg.get('Subject', '')}")
            payload = msg.get_payload(decode=True)
            if payload:
                parts.append(payload.decode("utf-8", errors="replace")[:2000])
        text = "\n---\n".join(parts)
    elif fmt == "html":
        text = path.read_text(encoding="utf-8", errors="replace")
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
    else:
        print(f"error: unsupported format: {path.suffix}", file=sys.stderr)
        return 1

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


def cmd_meta(args: argparse.Namespace) -> int:
    path = Path(args.input)
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1
    fmt = _detect_format(path)
    meta: dict[str, Any] = {"file": str(path), "format": fmt}

    if fmt in ("xlsx", "docx"):
        try:
            with zipfile.ZipFile(path) as zf:
                if "docProps/core.xml" in zf.namelist():
                    core = zf.read("docProps/core.xml").decode("utf-8", errors="replace")
                    title_m = re.search(r"<dc:title>(.*?)</dc:title>", core)
                    creator_m = re.search(r"<dc:creator>(.*?)</dc:creator>", core)
                    modified_m = re.search(r"<dcterms:modified[^>]*>(.*?)</dcterms:modified>", core)
                    if title_m:
                        meta["title"] = title_m.group(1)
                    if creator_m:
                        meta["author"] = creator_m.group(1)
                    if modified_m:
                        meta["modified"] = modified_m.group(1)
        except zipfile.BadZipFile:
            pass
    elif fmt == "epub":
        try:
            with zipfile.ZipFile(path) as zf:
                # Read container.xml to find OPF path
                if "META-INF/container.xml" in zf.namelist():
                    container = zf.read("META-INF/container.xml").decode("utf-8", errors="replace")
                    opf_m = re.search(r'full-path="([^"]+)"', container)
                    if opf_m:
                        opf_path = opf_m.group(1)
                        if opf_path in zf.namelist():
                            opf = zf.read(opf_path).decode("utf-8", errors="replace")
                            title_m = re.search(r"<dc:title[^>]*>(.*?)</dc:title>", opf)
                            creator_m = re.search(r"<dc:creator[^>]*>(.*?)</dc:creator>", opf)
                            if title_m:
                                meta["title"] = title_m.group(1)
                            if creator_m:
                                meta["author"] = creator_m.group(1)
        except zipfile.BadZipFile:
            pass

    print(json.dumps(meta, indent=2, ensure_ascii=False))
    return 0


def cmd_tables(args: argparse.Namespace) -> int:
    path = Path(args.input)
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1
    out_dir = Path(args.out_dir)
    fmt = _detect_format(path)

    if fmt == "xlsx":
        count = _extract_xlsx_tables(path, out_dir)
        print(f"extracted {count} sheet(s) -> {out_dir}")
        return 0
    else:
        print(f"error: tables extraction not supported for {fmt}", file=sys.stderr)
        return 1


def cmd_structured(args: argparse.Namespace) -> int:
    path = Path(args.input)
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1
    result = _extract_structured_html(path)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def cmd_mbox_search(args: argparse.Namespace) -> int:
    path = Path(args.input)
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1
    results = _mbox_search(path, args.q, getattr(args, "from_addr", ""), getattr(args, "date", ""))
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


def cmd_to_ledger(args: argparse.Namespace) -> int:
    path = Path(args.input)
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 1
    fmt = _detect_format(path)
    # Extract a preview
    if fmt == "xlsx":
        text = _extract_xlsx_text(path)[:500]
    elif fmt in ("docx", "epub"):
        text = _pandoc_to_text(path)[:500]
        if not text:
            text = f"[{fmt} file, pandoc not available]"
    elif fmt == "mbox":
        text = f"mbox archive: {path.name}"
    elif fmt == "html":
        raw = path.read_text(encoding="utf-8", errors="replace")
        text = re.sub(r"<[^>]+>", " ", raw)[:500]
    else:
        text = f"[{fmt} file]"

    fields = [
        "claim_id", "claim", "sub_question", "source_title", "source_url",
        "source_type", "date_published", "date_accessed", "access_method",
        "evidence", "quote_or_anchor", "contradiction", "confidence", "notes",
        "archive_url", "content_hash", "snapshot_status", "verifiability",
        "verifiability_note",
        "license_spdx", "robots_status", "prov_activity_id",
    ]
    prov_seed = (f"multi_extract|{args.url or path.name}").encode("utf-8")
    prov_id = "prov:multi_extract:" + hashlib.sha256(prov_seed).hexdigest()[:8]
    row = {
        "claim_id": f"extract-{path.stem}",
        "claim": text.strip()[:200],
        "sub_question": "",
        "source_title": path.name,
        "source_url": args.url or "",
        "source_type": "primary",
        "date_published": "",
        "date_accessed": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "access_method": f"multi_extract_{fmt}",
        "evidence": text.strip()[:500],
        "quote_or_anchor": "",
        "contradiction": "none",
        "confidence": "medium",
        "notes": f"extracted from {fmt} via multi_extract.py",
        "archive_url": "",
        "content_hash": "",
        "snapshot_status": "",
        "verifiability": "",
        "verifiability_note": "",
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


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def cmd_self_test(_args: argparse.Namespace) -> int:
    errors: list[str] = []

    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)

        # Test 1: XLSX extraction with shared strings
        xlsx_path = td / "test.xlsx"
        _create_test_xlsx(xlsx_path)
        text = _extract_xlsx_text(xlsx_path)
        if "Hello" not in text:
            errors.append(f"XLSX text extraction failed: {text[:100]}")

        # Test 2: XLSX with inlineStr and gapped columns (A1, C1)
        xlsx_gap_path = td / "gap.xlsx"
        _create_test_xlsx_inline_gap(xlsx_gap_path)
        text_gap = _extract_xlsx_text(xlsx_gap_path)
        # Should have "Alpha\t\tGamma" (A1=Alpha, B1=empty, C1=Gamma)
        if "Alpha" not in text_gap or "Gamma" not in text_gap:
            errors.append(f"XLSX inlineStr extraction failed: {text_gap[:100]}")
        # Check gap preservation
        lines = text_gap.strip().split("\n")
        if lines:
            cols = lines[0].split("\t")
            if len(cols) < 3:
                errors.append(f"XLSX gap columns not preserved: got {len(cols)} cols, expected >=3")
            elif cols[0] != "Alpha" or cols[1] != "" or cols[2] != "Gamma":
                errors.append(f"XLSX gap values wrong: {cols[:3]}")

        # Test 3: XLSX tables
        tables_dir = td / "tables"
        count = _extract_xlsx_tables(xlsx_gap_path, tables_dir)
        if count < 1:
            errors.append("XLSX tables extraction produced 0 sheets")
        elif (tables_dir / "sheet1.csv").is_file():
            content = (tables_dir / "sheet1.csv").read_text(encoding="utf-8")
            if "Alpha" not in content:
                errors.append("XLSX table CSV missing expected content")

        # Test 4: mbox search
        mbox_path = td / "test.mbox"
        _create_test_mbox(mbox_path)
        results = _mbox_search(mbox_path, "research")
        if not results:
            errors.append("mbox search returned no results")

        # Test 5: HTML structured (JSON-LD + microdata + RDFa)
        html_path = td / "test.html"
        html_path.write_text(
            '<html><head>'
            '<script type="application/ld+json">{"@type": "Article", "name": "Test"}</script>'
            '</head><body>'
            '<div itemscope itemtype="http://schema.org/Person">'
            '<span itemprop="name">John Doe</span>'
            '</div>'
            '<div typeof="foaf:Person" property="foaf:name" content="Jane Smith"></div>'
            '</body></html>',
            encoding="utf-8",
        )
        result = _extract_structured_html(html_path)
        if not result.get("json_ld"):
            errors.append("HTML structured: no JSON-LD found")
        elif result["json_ld"][0].get("name") != "Test":
            errors.append("HTML JSON-LD name mismatch")
        if not result.get("microdata"):
            errors.append("HTML structured: no microdata found")
        elif result["microdata"][0].get("type") != "http://schema.org/Person":
            errors.append(f"HTML microdata type mismatch: {result['microdata'][0]}")
        if not result.get("rdfa"):
            errors.append("HTML structured: no RDFa found")

        # Test 6: to-ledger schema
        ledger_path = td / "row.csv"
        ns = argparse.Namespace(input=str(xlsx_path), url="https://example.com/data.xlsx", out_row=str(ledger_path))
        rc = cmd_to_ledger(ns)
        if rc != 0:
            errors.append("to-ledger failed")
        elif ledger_path.is_file():
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "evidence_ledger", Path(__file__).resolve().parent / "evidence_ledger.py",
            )
            el_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(el_mod)
            vrc = el_mod.validate_ledger(ledger_path)
            if vrc != 0:
                errors.append("to-ledger output failed evidence_ledger validate")

        # Test 7: DOCX/EPUB via pandoc (skip if pandoc missing)
        if _has_pandoc():
            docx_path = td / "test.docx"
            _create_test_docx_via_pandoc(docx_path)
            if docx_path.is_file():
                text = _pandoc_to_text(docx_path)
                if "sample" not in text.lower():
                    errors.append(f"DOCX pandoc extraction missing content: {text[:50]}")
        else:
            print("info: pandoc not installed; skipping DOCX/EPUB test", file=sys.stderr)

        # Test 8: format detection
        if _detect_format(Path("test.xlsx")) != "xlsx":
            errors.append("format detection failed for .xlsx")
        if _detect_format(Path("test.docx")) != "docx":
            errors.append("format detection failed for .docx")
        if _detect_format(Path("test.mbox")) != "mbox":
            errors.append("format detection failed for .mbox")

    if errors:
        print("multi_extract self-test FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("multi_extract self-test ok")
    return 0


def _create_test_xlsx(path: Path) -> None:
    """Create a minimal valid XLSX file using stdlib zipfile."""
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/></Types>')
        zf.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        zf.writestr("xl/workbook.xml", '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/></sheets></workbook>')
        zf.writestr("xl/sharedStrings.xml", '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="2"><si><t>Hello</t></si><si><t>World</t></si></sst>')
        zf.writestr("xl/worksheets/sheet1.xml", '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row></sheetData></worksheet>')
    path.write_bytes(buf.getvalue())


def _create_test_xlsx_inline_gap(path: Path) -> None:
    """Create XLSX with inlineStr cells at A1 and C1 (B1 is empty gap)."""
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/></Types>')
        zf.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        zf.writestr("xl/workbook.xml", '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/></sheets></workbook>')
        # No sharedStrings needed for inlineStr
        sheet_xml = (
            '<?xml version="1.0"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData>'
            '<row r="1">'
            '<c r="A1" t="inlineStr"><is><t>Alpha</t></is></c>'
            '<c r="C1" t="inlineStr"><is><t>Gamma</t></is></c>'
            '</row>'
            '</sheetData>'
            '</worksheet>'
        )
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    path.write_bytes(buf.getvalue())


def _create_test_mbox(path: Path) -> None:
    """Create a minimal mbox file."""
    content = (
        "From sender@example.com Mon Jan  1 00:00:00 2024\n"
        "From: sender@example.com\n"
        "To: recipient@example.com\n"
        "Subject: Test Research Email\n"
        "Date: Mon, 01 Jan 2024 00:00:00 +0000\n"
        "\n"
        "This is a test email about research methodology.\n"
        "\n"
    )
    path.write_text(content, encoding="utf-8")


def _create_test_docx_via_pandoc(path: Path) -> None:
    """Create a test DOCX via pandoc from markdown."""
    md_content = "# Sample Document\n\nThis is a sample document for testing.\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(md_content)
        md_path = f.name
    try:
        subprocess.run(["pandoc", md_path, "-o", str(path)], capture_output=True, timeout=10)
    finally:
        Path(md_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(prog="multi_extract.py", description="Multi-format extraction.")
    sub = p.add_subparsers(dest="cmd", required=True)

    t_p = sub.add_parser("text", help="Extract text.")
    t_p.add_argument("--in", dest="input", required=True)
    t_p.add_argument("--out", default=None)

    m_p = sub.add_parser("meta", help="Extract metadata.")
    m_p.add_argument("--in", dest="input", required=True)

    tb_p = sub.add_parser("tables", help="Extract tables.")
    tb_p.add_argument("--in", dest="input", required=True)
    tb_p.add_argument("--out-dir", required=True)

    s_p = sub.add_parser("structured", help="Extract JSON-LD, microdata, and RDFa from HTML.")
    s_p.add_argument("--in", dest="input", required=True)

    mb_p = sub.add_parser("mbox-search", help="Search mbox archive.")
    mb_p.add_argument("--in", dest="input", required=True)
    mb_p.add_argument("--q", required=True)
    mb_p.add_argument("--from", dest="from_addr", default="")
    mb_p.add_argument("--date", default="")

    tl_p = sub.add_parser("to-ledger", help="Emit evidence-ledger row.")
    tl_p.add_argument("--in", dest="input", required=True)
    tl_p.add_argument("--url", default="")
    tl_p.add_argument("--out-row", required=True)

    sub.add_parser("self-test", help="Run offline self-tests.")

    args = p.parse_args()
    if args.cmd == "text":
        return cmd_text(args)
    if args.cmd == "meta":
        return cmd_meta(args)
    if args.cmd == "tables":
        return cmd_tables(args)
    if args.cmd == "structured":
        return cmd_structured(args)
    if args.cmd == "mbox-search":
        return cmd_mbox_search(args)
    if args.cmd == "to-ledger":
        return cmd_to_ledger(args)
    if args.cmd == "self-test":
        return cmd_self_test(args)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
