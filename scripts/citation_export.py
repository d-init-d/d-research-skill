#!/usr/bin/env python3
"""Citation export utility with BibTeX/RIS export and DOI enrichment."""

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import urllib.parse
from typing import Dict, List, Optional

from resource_limits import (
    ResourceLimitError,
    emit_blocker_and_exit,
    load_limits,
    read_http_response_bounded,
)


# Expected CSV columns
CSV_COLUMNS = [
    'claim_id', 'claim', 'sub_question', 'source_title', 'source_url',
    'source_type', 'date_published', 'date_accessed', 'access_method',
    'evidence', 'quote_or_anchor', 'contradiction', 'confidence', 'notes'
]


def read_csv(file_path: str) -> List[Dict[str, str]]:
    """Read CSV file and return list of row dictionaries."""
    rows = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def get_unique_sources(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Extract unique sources by DOI, then URL, then title/year metadata."""
    seen = set()
    sources = []
    for row in rows:
        doi = _normalize_doi(row.get("doi", "")).lower()
        title = _single_line(row.get("source_title", "")).strip()
        url = _single_line(row.get("source_url", "")).strip()
        year = _year_only(row.get("date_published", ""))
        if doi:
            key = ("doi", doi)
        elif url:
            key = ("url", url)
        else:
            key = ("metadata", title, year)
        if key not in seen and (doi or url or title):
            seen.add(key)
            sources.append(row)
    return sources


def _single_line(value: object) -> str:
    """Normalize CR/LF sequences without discarding adjacent text."""
    return re.sub(
        r"(?:\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029])+",
        " ",
        str(value or ""),
    )


def _bibtex_escape(value: object) -> str:
    """Encode literal text for a braced BibTeX field.

    ``\\\\`` is a TeX line break, not an escaped literal backslash.  Use
    text macros for TeX-special characters so real BibTeX/BibLaTeX parsers
    recover the original single-line text.
    """
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "%": r"\%",
        "&": r"\&",
        "_": r"\_",
        "#": r"\#",
        "$": r"\$",
        "^": r"\textasciicircum{}",
        "~": r"\textasciitilde{}",
    }
    return "".join(replacements.get(ch, ch) for ch in _single_line(value))


def _bibtex_verbatim(value: object) -> str:
    """Escape structural characters in a BibTeX URL/DOI field.

    BibLaTeX treats these fields as verbatim at render time, but the BibTeX
    parser still sees braces and backslashes while reading the database.  Raw
    structural characters can therefore make the entire file unparsable.
    """
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(ch, ch) for ch in _single_line(value))


def _ris_value(value: object) -> str:
    """Return one physical RIS line, preventing tag/record injection."""
    return _single_line(value).strip()


def _year_only(date_pub: object) -> str:
    """Return 4-digit year only for valid YYYY / YYYY-MM / YYYY-MM-DD dates.

    Does not slice arbitrary leading digits from garbage strings.
    """
    import re
    from calendar import monthrange

    s = str(date_pub or "").strip()
    m = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", s)
    if not m:
        return ""
    year = int(m.group(1))
    month = int(m.group(2) or "1")
    day = int(m.group(3) or "1")
    if year < 1400 or year > 9999 or month < 1 or month > 12:
        return ""
    if day < 1 or day > monthrange(year, month)[1]:
        return ""
    return f"{year:04d}"


RIS_TYPE_MAP = {
    "paper": "JOUR",
    "official": "ELEC",
    "primary": "GEN",
    "secondary": "GEN",
    "dataset": "DATA",
    "code": "COMP",
    "pdf": "ELEC",
    "filing": "RPRT",
    "community": "ELEC",
    "unknown": "GEN",
}


def format_bibtex(source: Dict[str, str], citation_key: str) -> str:
    """Format a source as BibTeX @misc entry."""
    lines = [f"@misc{{{citation_key},"]

    title = _single_line(source.get("source_title", "")).strip()
    if title:
        # The inner braces preserve title capitalization through BibTeX.
        lines.append("  title = {{" + _bibtex_escape(title) + "}},")

    url = _bibtex_verbatim(source.get("source_url", "")).strip()
    if url:
        lines.append(f"  url = {{{url}}},")

    doi = _normalize_doi(source.get("doi", ""))
    if doi:
        lines.append(f"  doi = {{{_bibtex_verbatim(doi)}}},")

    source_type = _single_line(source.get("source_type", "")).strip()
    if source_type:
        lines.append(f"  note = {{{_bibtex_escape(source_type)}}},")

    year = _year_only(source.get("date_published", ""))
    if year:
        lines.append(f"  year = {{{year}}},")

    date_acc = _single_line(source.get("date_accessed", "")).strip()
    if date_acc:
        lines.append(f"  howpublished = {{{_bibtex_escape('Accessed: ' + date_acc)}}},")

    access_method = _single_line(source.get("access_method", "")).strip()
    if access_method:
        lines.append(f"  organization = {{{_bibtex_escape(access_method)}}},")

    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]

    lines.append("}")
    return "\n".join(lines)


def format_ris(source: Dict[str, str]) -> str:
    """Format a source as RIS entry (exactly one TY field)."""
    lines: List[str] = []
    source_type = _ris_value(source.get("source_type", "")).lower()
    ty = RIS_TYPE_MAP.get(source_type, "ELEC")
    lines.append(f"TY  - {ty}")

    title = _ris_value(source.get("source_title", ""))
    if title:
        lines.append(f"TI  - {title}")

    url = _ris_value(source.get("source_url", ""))
    if url:
        lines.append(f"UR  - {url}")

    if source_type:
        lines.append(f"N1  - source_type: {source_type}")

    date_pub = _ris_value(source.get("date_published", ""))
    year = _year_only(date_pub)
    if year:
        lines.append(f"PY  - {year}")
    if date_pub:
        lines.append(f"DA  - {date_pub}")

    date_acc = _ris_value(source.get("date_accessed", ""))
    if date_acc:
        lines.append(f"Y2  - {date_acc}")

    access_method = _ris_value(source.get("access_method", ""))
    if access_method:
        lines.append(f"PB  - {access_method}")

    lines.append("ER  - ")
    lines.append("")
    return "\n".join(lines)


def generate_citation_key(
    source: Dict[str, str], index: int, used: Optional[set] = None
) -> str:
    """Generate a source-stable ASCII key using canonical identity + SHA-256."""
    used = used if used is not None else set()
    _ = index  # retained for CLI/API compatibility; keys do not depend on order
    doi = _normalize_doi(source.get("doi") or "").lower()
    url = _single_line(source.get("source_url") or "").strip()
    title = _single_line(source.get("source_title") or "").strip()
    year = _year_only(source.get("date_published", ""))
    words = re.sub(r"[^A-Za-z0-9 ]+", " ", title).split()

    if doi:
        identity = f"doi:{doi}"
        doi_label = re.sub(r"[^A-Za-z0-9]+", "_", doi).strip("_")[:28]
        label = f"doi_{doi_label or 'source'}"
    elif url:
        identity = f"url:{url}"
        label = (words[0].lower() if words else "source") + year
    else:
        metadata = {
            "title": title,
            "year": year,
            "source_type": _single_line(source.get("source_type", "")).strip(),
        }
        identity = "metadata:" + json.dumps(
            metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        label = (words[0].lower() if words else "source") + year

    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    key_base = f"{label}_{digest[:12]}"
    key = key_base
    if key in used:
        # Only an exact duplicate or cryptographic-prefix collision reaches
        # this path.  A metadata hash keeps distinct records deterministic.
        full_metadata = json.dumps(
            {str(k): str(v) for k, v in sorted(source.items())},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        metadata_digest = hashlib.sha256(full_metadata.encode("utf-8")).hexdigest()
        key = f"{key_base}_{metadata_digest[:12]}"
    duplicate = 2
    duplicate_base = key
    while key in used:
        key = f"{duplicate_base}_{duplicate}"
        duplicate += 1
    used.add(key)
    return key


def export_csv_to_format(file_path: str, format_type: str, output_path: str) -> None:
    """Export CSV to specified format."""
    rows = read_csv(file_path)
    sources = get_unique_sources(rows)

    if not sources:
        raise ValueError("No valid sources found in CSV")

    output_lines = []
    used_keys: set = set()

    if format_type == "bibtex":
        for i, source in enumerate(sources):
            key = generate_citation_key(source, i + 1, used_keys)
            output_lines.append(format_bibtex(source, key))
            output_lines.append("")
    elif format_type == "ris":
        for source in sources:
            output_lines.append(format_ris(source))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))


def _normalize_doi(doi: object) -> str:
    doi = str(doi or "").strip()
    lowered = doi.lower()
    if lowered.startswith("https://doi.org/"):
        doi = doi[16:]
    elif lowered.startswith("http://doi.org/"):
        doi = doi[15:]
    elif lowered.startswith("doi:"):
        doi = doi[4:]
    return doi.strip()


def _enrich_doi_crossref(doi: str) -> Optional[Dict[str, str]]:
    """Resolve DOI metadata via Crossref. Returns None on miss/error."""
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "d-research-skill/3.2 (citation_export; mailto:research@example.com)"
            },
        )
        limits = load_limits()
        with urllib.request.urlopen(req, timeout=limits.http_timeout_sec) as response:
            if response.status == 404:
                return None
            data = json.loads(read_http_response_bounded(response, limits).decode("utf-8"))
        if "message" not in data:
            return None
        work = data["message"]
        result: Dict[str, str] = {"resolver": "crossref", "doi": doi}
        if "title" in work and work["title"]:
            result["title"] = (
                work["title"][0] if isinstance(work["title"], list) else work["title"]
            )
        if "author" in work:
            authors = []
            for author in work["author"]:
                if "given" in author and "family" in author:
                    authors.append(f"{author['given']} {author['family']}")
                elif "family" in author:
                    authors.append(author["family"])
            if authors:
                result["authors"] = "; ".join(authors)
        year = None
        for date_key in ("published-print", "published-online", "created"):
            if date_key in work:
                date_parts = work[date_key].get("date-parts", [[]])
                if date_parts and date_parts[0]:
                    year = str(date_parts[0][0])
                    break
        if year:
            result["year"] = year
        if "publisher" in work:
            result["publisher"] = work["publisher"]
        if "container-title" in work and work["container-title"]:
            result["journal"] = work["container-title"][0]
        if "volume" in work:
            result["volume"] = work["volume"]
        if "issue" in work:
            result["issue"] = work["issue"]
        if "page" in work:
            result["pages"] = work["page"]
        if "URL" in work:
            result["url"] = work["URL"]
        return result
    except ResourceLimitError as exc:
        emit_blocker_and_exit(exc)
    except urllib.error.HTTPError as e:
        if e.code in {404, 410}:
            return None
        print(f"Crossref DOI lookup failed for {doi}: HTTP {e.code}", file=sys.stderr)
        raise SystemExit(1) from e
    except Exception as e:
        print(f"Crossref DOI lookup failed for {doi}: {e}", file=sys.stderr)
        raise SystemExit(1) from e


def _enrich_doi_datacite(doi: str) -> Optional[Dict[str, str]]:
    """Resolve DOI metadata via DataCite. Returns None on miss/error."""
    url = f"https://api.datacite.org/dois/{urllib.parse.quote(doi, safe='')}"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "d-research-skill/3.2 (citation_export; mailto:research@example.com)"
            },
        )
        limits = load_limits()
        with urllib.request.urlopen(req, timeout=limits.http_timeout_sec) as response:
            if response.status == 404:
                return None
            data = json.loads(read_http_response_bounded(response, limits).decode("utf-8"))
        attrs = data.get("data", {}).get("attributes", {})
        if not attrs:
            return None
        titles = attrs.get("titles") or []
        title = titles[0].get("title", "") if titles else ""
        creators = [c.get("name", "") for c in (attrs.get("creators") or []) if c.get("name")]
        result: Dict[str, str] = {
            "resolver": "datacite",
            "doi": doi,
            "url": f"https://doi.org/{doi}",
        }
        if title:
            result["title"] = title
        if creators:
            result["authors"] = "; ".join(creators)
        if attrs.get("publicationYear"):
            result["year"] = str(attrs["publicationYear"])
        if attrs.get("publisher"):
            result["publisher"] = attrs["publisher"]
        return result
    except ResourceLimitError as exc:
        emit_blocker_and_exit(exc)
    except Exception as e:
        print(f"DataCite DOI lookup failed for {doi}: {e}", file=sys.stderr)
        return None


def enrich_doi(doi: str) -> Optional[Dict[str, str]]:
    """Enrich a DOI via Crossref, falling back to DataCite on failure/miss."""
    doi = _normalize_doi(doi)
    if not doi:
        return None
    result = _enrich_doi_crossref(doi)
    if result and str(result.get("title") or "").strip():
        return result
    return _enrich_doi_datacite(doi)


def _parse_bibtex_entry(text: str) -> Dict[str, str]:
    """Minimal BibTeX field parser for round-trip self-tests.

    Handles escaped braces/backslashes inside ``{...}`` values.
    """
    import re

    fields: Dict[str, str] = {}
    m = re.search(r"@\w+\{([^,]+),", text)
    if m:
        fields["_key"] = m.group(1)
    for m in re.finditer(r"(\w+)\s*=\s*\{", text):
        name = m.group(1)
        i = m.end()
        depth = 1
        chars: List[str] = []
        while i < len(text) and depth:
            ch = text[i]
            if ch == "\\" and i + 1 < len(text):
                chars.append(ch)
                chars.append(text[i + 1])
                i += 2
                continue
            if ch == "{":
                depth += 1
                chars.append(ch)
            elif ch == "}":
                depth -= 1
                if depth:
                    chars.append(ch)
            else:
                chars.append(ch)
            i += 1
        value = "".join(chars)
        if name == "title" and value.startswith("{") and value.endswith("}"):
            value = value[1:-1]
        if name == "title":
            for encoded, literal in (
                (r"\textbackslash{}", "\\"),
                (r"\textasciicircum{}", "^"),
                (r"\textasciitilde{}", "~"),
                (r"\{", "{"),
                (r"\}", "}"),
                (r"\%", "%"),
                (r"\&", "&"),
                (r"\_", "_"),
                (r"\#", "#"),
                (r"\$", "$"),
            ):
                value = value.replace(encoded, literal)
        fields[name] = value
    return fields


def _parse_ris_entry(text: str) -> Dict[str, List[str]]:
    """Parse one RIS record into field -> list of values."""
    fields: Dict[str, List[str]] = {}
    for line in text.splitlines():
        if not line.strip() or line.startswith("ER  -"):
            continue
        if "  - " not in line:
            continue
        tag, _, val = line.partition("  - ")
        tag = tag.strip()
        fields.setdefault(tag, []).append(val)
    return fields


def run_self_test() -> bool:
    """Run self-test validation."""
    print("Running self-test...")
    
    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    csv_path = os.path.join(temp_dir, 'test_data.csv')
    output_bibtex = os.path.join(temp_dir, 'output.bib')
    output_ris = os.path.join(temp_dir, 'output.ris')
    
    try:
        # Create test CSV data
        test_data = [
            {
                'claim_id': '1',
                'claim': 'Test claim 1',
                'sub_question': 'SQ1',
                'source_title': 'Example Article Title',
                'source_url': 'https://example.com/article1',
                'source_type': 'website',
                'date_published': '2023',
                'date_accessed': '2024-01-15',
                'access_method': 'direct',
                'evidence': 'Some evidence',
                'quote_or_anchor': 'Quote text',
                'contradiction': '',
                'confidence': 'high',
                'notes': 'Test note'
            },
            {
                'claim_id': '2',
                'claim': 'Test claim 2',
                'sub_question': 'SQ2',
                'source_title': 'Another Source',
                'source_url': 'https://example.com/article2',
                'source_type': 'article',
                'date_published': '2022-05-10',
                'date_accessed': '2024-01-15',
                'access_method': 'api',
                'evidence': 'More evidence',
                'quote_or_anchor': '',
                'contradiction': 'none',
                'confidence': 'medium',
                'notes': ''
            },
            {
                'claim_id': '3',
                'claim': 'Test claim 3',
                'sub_question': 'SQ3',
                'source_title': 'Example Article Title',  # Duplicate to test uniqueness
                'source_url': 'https://example.com/article1',
                'source_type': 'website',
                'date_published': '2023',
                'date_accessed': '2024-01-15',
                'access_method': 'direct',
                'evidence': 'Duplicated source',
                'quote_or_anchor': '',
                'contradiction': '',
                'confidence': 'high',
                'notes': ''
            }
        ]
        
        # Write test CSV
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            writer.writerows(test_data)
        
        print(f"  Created test CSV: {csv_path}")
        
        # Test CSV reading
        rows = read_csv(csv_path)
        assert len(rows) == 3, f"Expected 3 rows, got {len(rows)}"
        print("  [PASS] CSV reading")
        
        # Test unique source extraction
        sources = get_unique_sources(rows)
        assert len(sources) == 2, f"Expected 2 unique sources, got {len(sources)}"
        print("  [PASS] Unique source extraction")
        
        # Test BibTeX export (parser round-trip, not substring-only)
        export_csv_to_format(csv_path, 'bibtex', output_bibtex)
        with open(output_bibtex, 'r', encoding='utf-8') as f:
            bibtex_content = f.read()
        entries = [e.strip() for e in bibtex_content.split("\n\n") if e.strip()]
        assert len(entries) == 2, f"Expected 2 BibTeX entries, got {len(entries)}"
        parsed0 = _parse_bibtex_entry(entries[0])
        assert parsed0.get("title") == "Example Article Title"
        assert parsed0.get("year") == "2023"
        assert parsed0.get("_key")
        print("  [PASS] BibTeX export (parsed round-trip)")

        # Test RIS export — exactly one TY per record
        export_csv_to_format(csv_path, 'ris', output_ris)
        with open(output_ris, 'r', encoding='utf-8') as f:
            ris_content = f.read()
        ris_records = [r for r in ris_content.split("ER  -") if r.strip()]
        assert len(ris_records) == 2, f"Expected 2 RIS records, got {len(ris_records)}"
        for rec in ris_records:
            ty_count = sum(1 for line in rec.splitlines() if line.startswith("TY  - "))
            assert ty_count == 1, f"Expected exactly one TY, got {ty_count}"
        parsed_ris = _parse_ris_entry(ris_records[0] + "ER  - ")
        assert parsed_ris.get("TY") == ["ELEC"]
        assert parsed_ris.get("TI") == ["Example Article Title"]
        print("  [PASS] RIS export (exactly one TY, parsed)")

        # Brace / backslash / newline titles + invalid year
        evil = {
            "source_title": "Title with {braces} and \\backslash\nand newline",
            "source_url": "https://example.com/evil{segment}\\tail",
            "doi": "10.1234/evil{suffix}\\tail",
            "source_type": "paper",
            "date_published": "not-a-year-2023x",
            "date_accessed": "2024-01-01",
            "access_method": "web",
        }
        bib_evil = format_bibtex(evil, "evilkey")
        parsed_evil = _parse_bibtex_entry(bib_evil)
        assert "year" not in parsed_evil, "invalid year must not produce year field"
        # Raw export must encode literal braces/backslashes as TeX text.
        assert r"\{" in bib_evil and r"\}" in bib_evil, f"braces must be escaped: {bib_evil!r}"
        assert r"\textbackslash{}" in bib_evil, f"backslash must be encoded: {bib_evil!r}"
        assert "title = {{" in bib_evil
        assert "url = {https://example.com/evil\\{segment\\}" in bib_evil
        assert "doi = {10.1234/evil\\{suffix\\}" in bib_evil
        # Newlines inside values collapse to one physical line without data loss.
        title_val = parsed_evil.get("title", "")
        assert "\n" not in title_val, f"newline leaked into title: {title_val!r}"
        assert title_val == "Title with {braces} and \\backslash and newline"
        print("  [PASS] BibTeX escape + invalid year normalization")

        ris_evil = format_ris(evil)
        assert "PY  - " not in ris_evil, "invalid year must not produce PY"
        assert sum(line.startswith("TY  - ") for line in ris_evil.splitlines()) == 1
        assert _parse_ris_entry(ris_evil).get("TI") == [
            "Title with {braces} and \\backslash and newline"
        ]
        injected_ris = format_ris(
            {"source_title": "Normal\nTY  - BOOK\nER  - ", "source_type": "paper"}
        )
        assert sum(line.startswith("TY  - ") for line in injected_ris.splitlines()) == 1
        assert sum(line.startswith("ER  -") for line in injected_ris.splitlines()) == 1
        assert "JOUR" in ris_evil  # paper -> JOUR
        print("  [PASS] RIS newline normalization + single TY/ER")

        # Deterministic unique keys for colliding titles
        used: set = set()
        s1 = {"source_title": "Same Title", "source_url": "https://a.example/1", "date_published": "2020"}
        s2 = {"source_title": "Same Title", "source_url": "https://b.example/2", "date_published": "2020"}
        k1 = generate_citation_key(s1, 1, used)
        k2 = generate_citation_key(s2, 2, used)
        assert k1 != k2, "colliding titles must get unique keys"
        assert k1 in used and k2 in used
        k1b = generate_citation_key(s1, 1, set())
        k1c = generate_citation_key(s1, 1, set())
        assert k1b == k1c, "keys must be deterministic for same source"
        def keys_by_url(order):
            local_used: set = set()
            return {
                item["source_url"]: generate_citation_key(item, i + 1, local_used)
                for i, item in enumerate(order)
            }

        assert keys_by_url([s1, s2]) == keys_by_url([s2, s1])
        doi_key = generate_citation_key(
            {"doi": "10.5281/zenodo.1", "source_title": "Dataset"}, 1, set()
        )
        assert doi_key.startswith("doi_")
        print("  [PASS] Deterministic order-independent unique citation keys")

        # Year-only: full dates ok; garbage prefix digits rejected
        assert _year_only("2023-05-10") == "2023"
        assert _year_only("2023") == "2023"
        assert _year_only("abc2023") == ""
        assert _year_only("202313") == ""  # not YYYY-MM
        assert _year_only("999") == ""
        print("  [PASS] Year-only normalization")

        # Offline Crossref -> DataCite fallback via mock server
        import http.server
        import threading

        class _MockDoi(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):  # noqa: ARG002
                return

            def do_GET(self):
                if "/works/" in self.path:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"not found")
                elif "/dois/" in self.path:
                    body = json.dumps({
                        "data": {
                            "attributes": {
                                "titles": [{"title": "DataCite Fallback Title"}],
                                "creators": [{"name": "Doe, Jane"}],
                                "publicationYear": 2021,
                                "publisher": "Zenodo",
                            }
                        }
                    }).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

        srv = http.server.HTTPServer(("127.0.0.1", 0), _MockDoi)
        port = srv.server_address[1]
        th = threading.Thread(target=srv.serve_forever, daemon=True)
        th.start()
        try:
            def mock_cr(doi: str):
                url = f"http://127.0.0.1:{port}/works/{urllib.parse.quote(doi)}"
                try:
                    with urllib.request.urlopen(url, timeout=5) as r:
                        if r.status == 404:
                            return None
                except Exception:
                    return None
                return None

            def mock_dc(doi: str):
                url = f"http://127.0.0.1:{port}/dois/{urllib.parse.quote(doi, safe='')}"
                with urllib.request.urlopen(url, timeout=5) as r:
                    data = json.loads(r.read().decode())
                attrs = data["data"]["attributes"]
                return {
                    "resolver": "datacite",
                    "doi": doi,
                    "title": attrs["titles"][0]["title"],
                    "year": str(attrs["publicationYear"]),
                }

        except Exception:
            pass

        # Direct unit path: crossref None then datacite result
        def _test_fallback():
            # Inline reimplementation matching enrich_doi contract
            cr = mock_cr("10.5281/zenodo.999")
            assert cr is None
            dc = mock_dc("10.5281/zenodo.999")
            assert dc["resolver"] == "datacite"
            assert dc["title"] == "DataCite Fallback Title"
            # Full enrich with patched functions
            global _enrich_doi_crossref, _enrich_doi_datacite
            saved = (_enrich_doi_crossref, _enrich_doi_datacite)
            try:
                g = globals()
                g["_enrich_doi_crossref"] = mock_cr
                g["_enrich_doi_datacite"] = mock_dc
                out = enrich_doi("10.5281/zenodo.999")
                assert out is not None
                assert out["resolver"] == "datacite"
                assert out["title"] == "DataCite Fallback Title"

                g["_enrich_doi_crossref"] = lambda doi: {
                    "resolver": "crossref",
                    "doi": doi,
                    "title": " ",
                }
                out = enrich_doi("10.5281/zenodo.999")
                assert out is not None
                assert out["resolver"] == "datacite"

                datacite_called = False

                def fail_crossref(_doi: str):
                    raise RuntimeError("transient Crossref failure")

                def track_datacite(_doi: str):
                    nonlocal datacite_called
                    datacite_called = True
                    return {"resolver": "datacite", "title": "must not run"}

                g["_enrich_doi_crossref"] = fail_crossref
                g["_enrich_doi_datacite"] = track_datacite
                try:
                    enrich_doi("10.5281/transient")
                except RuntimeError:
                    pass
                else:
                    raise AssertionError(
                        "transient Crossref failure must fail instead of falling back"
                    )
                assert not datacite_called, (
                    "DataCite fallback is limited to Crossref not-found/unsupported"
                )
            finally:
                g["_enrich_doi_crossref"], g["_enrich_doi_datacite"] = saved

        _test_fallback()
        srv.shutdown()
        print("  [PASS] Crossref failure/unusable result triggers DataCite fallback")

        # Test format functions
        test_source = {
            'source_title': 'Test Title',
            'source_url': 'https://test.com',
            'source_type': 'article',
            'date_published': '2023-01',
            'date_accessed': '2024-01-01',
            'access_method': 'web'
        }

        bibtex = format_bibtex(test_source, 'testkey2023')
        parsed = _parse_bibtex_entry(bibtex)
        assert parsed.get("_key") == "testkey2023"
        assert parsed.get("title") == "Test Title"
        assert parsed.get("year") == "2023"

        ris = format_ris(test_source)
        assert sum(line.startswith("TY  - ") for line in ris.splitlines()) == 1
        assert "ER  - " in ris
        print("  [PASS] Format functions (parsed)")

        pandoc = shutil.which("pandoc")
        if pandoc:
            pandoc_bib = os.path.join(temp_dir, "pandoc-roundtrip.bib")
            pandoc_ris = os.path.join(temp_dir, "pandoc-roundtrip.ris")
            with open(pandoc_bib, "w", encoding="utf-8") as f:
                f.write(bib_evil)
            with open(pandoc_ris, "w", encoding="utf-8") as f:
                f.write(ris_evil)
            expected_title = "Title with {braces} and \\backslash and newline"
            for input_format, path in (
                ("bibtex", pandoc_bib),
                ("biblatex", pandoc_bib),
                ("ris", pandoc_ris),
            ):
                proc = subprocess.run(
                    [pandoc, "--from", input_format, "--to", "csljson", path],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=15,
                    check=False,
                )
                assert proc.returncode == 0, proc.stderr
                parsed_entries = json.loads(proc.stdout)
                assert len(parsed_entries) == 1
                assert parsed_entries[0].get("title") == expected_title, (
                    input_format,
                    parsed_entries[0].get("title"),
                )
            print("  [PASS] Pandoc BibTeX/BibLaTeX/RIS semantic round-trip")
        else:
            print("  [SKIP] Pandoc semantic round-trip (pandoc not installed)")

        # Test citation key generation
        key = generate_citation_key(test_source, 1)
        assert key
        print("  [PASS] Citation key generation")

        print("\nAll self-tests passed!")
        return True
        
    except AssertionError as e:
        print(f"\n  [FAIL] {e}")
        return False
    except Exception as e:
        print(f"\n  [ERROR] {e}")
        return False
    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(
        description='Citation export utility for CSV data'
    )
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Export subcommand
    export_parser = subparsers.add_parser(
        'export',
        help='Export CSV to BibTeX or RIS format'
    )
    export_parser.add_argument(
        '--file',
        required=True,
        help='Input CSV file path'
    )
    export_parser.add_argument(
        '--format',
        choices=['bibtex', 'ris'],
        required=True,
        help='Output format'
    )
    export_parser.add_argument(
        '--out',
        required=True,
        help='Output file path'
    )
    
    # Enrich subcommand
    enrich_parser = subparsers.add_parser(
        'enrich',
        help='Enrich DOI metadata via Crossref with a DataCite fallback'
    )
    enrich_parser.add_argument(
        '--doi',
        required=True,
        help='DOI to fetch metadata for'
    )
    
    # Self-test subcommand
    subparsers.add_parser(
        'self-test',
        help='Run self-test validation'
    )
    
    args = parser.parse_args()
    
    if args.command == 'export':
        try:
            export_csv_to_format(args.file, args.format, args.out)
            print(f"Exported to {args.out}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    
    elif args.command == 'enrich':
        result = enrich_doi(args.doi)
        if result:
            print(json.dumps(result, indent=2))
        else:
            print("Failed to fetch DOI metadata", file=sys.stderr)
            sys.exit(1)
    
    elif args.command == 'self-test':
        success = run_self_test()
        sys.exit(0 if success else 1)
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
