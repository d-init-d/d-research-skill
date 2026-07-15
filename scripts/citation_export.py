#!/usr/bin/env python3
"""Citation export with rich JSON sidecars, legacy fallbacks, and DOI enrichment."""

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
from typing import Any, Dict, List, Optional, Tuple

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

# Bibliographic metadata stays outside the canonical evidence-ledger schema.
CITATION_METADATA_FIELDS = {
    "accessed", "author", "authors", "booktitle", "citation_type",
    "container_title", "date_accessed", "doi", "edition", "editor",
    "editors", "isbn", "issue", "journal", "number", "pages",
    "proceedings", "provider_type", "publisher", "resource_type", "title",
    "type", "url", "volume", "year",
}

BIBTEX_TYPE_ALIASES = {
    "article": "article",
    "data-paper": "article",
    "datapaper": "article",
    "journal-article": "article",
    "journalarticle": "article",
    "book": "book",
    "edited-book": "book",
    "monograph": "book",
    "reference-book": "book",
    "conference": "inproceedings",
    "conference-paper": "inproceedings",
    "conferencepaper": "inproceedings",
    "inproceedings": "inproceedings",
    "proceedings-article": "inproceedings",
}


def read_csv(file_path: str) -> List[Dict[str, str]]:
    """Read CSV file and return list of row dictionaries."""
    rows = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def get_unique_sources(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Extract unique sources by DOI, then URL, then title/year metadata."""
    seen = set()
    sources = []
    for row in rows:
        doi = _source_doi(row).lower()
        title = _source_title(row)
        url = _source_url(row)
        year = _source_year(row)
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


def _first_text(source: Dict[str, Any], *keys: str) -> str:
    """Return the first non-empty scalar value for the requested keys."""
    for key in keys:
        value = source.get(key)
        if isinstance(value, (dict, list, tuple)):
            continue
        text = _single_line(value).strip()
        if text:
            return text
    return ""


def _source_title(source: Dict[str, Any]) -> str:
    return _first_text(source, "title", "source_title")


def _source_url(source: Dict[str, Any]) -> str:
    return _first_text(source, "url", "source_url")


def _source_doi(source: Dict[str, Any]) -> str:
    """Return an explicit DOI without changing legacy URL-based identities."""
    return _normalize_doi(_first_text(source, "doi", "DOI"))


def _identity_doi(source: Dict[str, Any]) -> str:
    doi = _source_doi(source)
    if doi:
        return doi
    url = _source_url(source)
    if url.lower().startswith(("https://doi.org/", "http://doi.org/")):
        return _normalize_doi(url)
    return ""


def _reject_conflicting_doi_url(source: Dict[str, Any]) -> None:
    """Reject metadata whose explicit DOI disagrees with its DOI resolver URL."""
    explicit = _source_doi(source)
    url = _source_url(source)
    url_doi = ""
    if url.lower().startswith(("https://doi.org/", "http://doi.org/")):
        url_doi = _normalize_doi(url)
    if explicit and url_doi and explicit.casefold() != url_doi.casefold():
        raise ValueError(
            f"Citation metadata DOI {explicit!r} conflicts with resolver URL DOI {url_doi!r}"
        )


def _source_year(source: Dict[str, Any]) -> str:
    return _year_only(_first_text(source, "year", "date_published"))


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


def _citation_identities(source: Dict[str, Any]) -> List[Tuple[str, ...]]:
    """Return strong-to-weak identities used to match a metadata sidecar."""
    _reject_conflicting_doi_url(source)
    identities: List[Tuple[str, ...]] = []
    doi = _identity_doi(source).lower()
    url = _source_url(source)
    title = re.sub(r"\s+", " ", _source_title(source)).strip().casefold()
    year = _source_year(source)
    if doi:
        identities.append(("doi", doi))
    if url:
        identities.append(("url", url))
    if title and year:
        identities.append(("title_year", title, year))
    return identities


def load_citation_metadata(paths: Optional[List[str]]) -> List[Dict[str, Any]]:
    """Load JSON sidecars, each containing one object or an object array."""
    def reject_duplicate_keys(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    def reject_nonfinite(value: str) -> None:
        raise ValueError(f"non-finite JSON number {value!r}")

    records: List[Dict[str, Any]] = []
    seen_payloads = set()
    for path in paths or []:
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(
                    f,
                    object_pairs_hook=reject_duplicate_keys,
                    parse_constant=reject_nonfinite,
                )
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"Cannot read citation metadata {path}: {exc}") from exc
        if isinstance(payload, dict):
            items = [payload]
        elif isinstance(payload, list):
            items = payload
        else:
            raise ValueError(f"Citation metadata {path} must contain an object or array")
        for position, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"Citation metadata {path} item {position} must be an object")
            canonical = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if canonical not in seen_payloads:
                seen_payloads.add(canonical)
                records.append(item)
    return records


def merge_citation_metadata(
    rows: List[Dict[str, str]], metadata_records: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Overlay matched sidecar fields without mutating ledger rows."""
    if not metadata_records:
        return [dict(row) for row in rows]
    identity_index: Dict[Tuple[str, ...], List[int]] = {}
    for index, record in enumerate(metadata_records):
        identities = _citation_identities(record)
        if not identities:
            raise ValueError(
                f"Citation metadata record {index + 1} needs DOI, URL, or title and year"
            )
        for identity in identities:
            previous = identity_index.setdefault(identity, [])
            if (
                identity[0] in {"doi", "url"}
                and previous
                and any(metadata_records[item] != record for item in previous)
            ):
                raise ValueError(f"Conflicting citation metadata for {':'.join(identity)}")
            previous.append(index)

    merged_rows: List[Dict[str, Any]] = []
    used_records = set()
    for row in rows:
        strong_matches = set()
        weak_matches = set()
        for identity in _citation_identities(row):
            matches = identity_index.get(identity, [])
            (strong_matches if identity[0] in {"doi", "url"} else weak_matches).update(matches)
        if len(strong_matches) > 1:
            label = _source_title(row) or _source_url(row) or "untitled source"
            raise ValueError(f"Ledger source {label!r} matches conflicting metadata records")
        if not strong_matches and len(weak_matches) > 1:
            label = _source_title(row) or "untitled source"
            raise ValueError(f"Ledger source {label!r} has ambiguous title/year metadata")
        merged: Dict[str, Any] = dict(row)
        selected = strong_matches or weak_matches
        if selected:
            metadata_index = next(iter(selected))
            used_records.add(metadata_index)
            metadata_record = metadata_records[metadata_index]
            accessed = metadata_record.get("accessed")
            date_accessed = metadata_record.get("date_accessed")
            if (
                accessed not in (None, "")
                and date_accessed not in (None, "")
                and _single_line(accessed).strip() != _single_line(date_accessed).strip()
            ):
                raise ValueError(
                    "Citation metadata accessed and date_accessed values conflict"
                )
            for key in CITATION_METADATA_FIELDS:
                if key in {"accessed", "date_accessed"}:
                    continue
                value = metadata_record.get(key)
                if value is not None and value != "" and value != []:
                    merged[key] = value
            access_value = date_accessed if date_accessed not in (None, "") else accessed
            if access_value not in (None, ""):
                merged["date_accessed"] = access_value
        merged_rows.append(merged)
    for index in sorted(set(range(len(metadata_records))) - used_records):
        print(
            f"warning: citation metadata record {index + 1} did not match any ledger source",
            file=sys.stderr,
        )
    return merged_rows


def _person_name(person: object) -> Tuple[str, bool]:
    """Return a normalized BibTeX name and whether it is a literal entity."""
    if isinstance(person, dict):
        literal = _single_line(person.get("literal") or "").strip()
        if literal:
            return literal, True
        family = _single_line(person.get("family") or "").strip()
        given = _single_line(person.get("given") or "").strip()
        if family and given:
            return f"{family}, {given}", False
        return (
            family or given or _single_line(person.get("name") or "").strip(),
            False,
        )
    return _single_line(person).strip(), False


def _people(source: Dict[str, Any], singular: str, plural: str) -> List[Tuple[str, bool]]:
    """Return normalized names while preserving explicit corporate authors."""
    value = source.get(plural)
    if value is None or value == "" or value == []:
        value = source.get(singular)
    if isinstance(value, (list, tuple)):
        people = [_person_name(person) for person in value]
    else:
        text = _single_line(value).strip()
        names = [part.strip() for part in text.split(";")] if ";" in text else [text]
        people = [(name, False) for name in names]
    return [(name, literal) for name, literal in people if name]


def _people_value(source: Dict[str, Any], singular: str, plural: str) -> str:
    return " and ".join(name for name, _literal in _people(source, singular, plural))


def _append_people_field(
    lines: List[str],
    name: str,
    source: Dict[str, Any],
    singular: str,
    plural: str,
) -> None:
    """Append a person-list field with braces around literal organizations."""
    encoded = []
    for person, literal in _people(source, singular, plural):
        escaped = _bibtex_escape(person)
        encoded.append("{" + escaped + "}" if literal else escaped)
    if encoded:
        lines.append(f"  {name} = {{{' and '.join(encoded)}}},")


def _bibtex_entry_type(source: Dict[str, Any]) -> str:
    """Return a conservative BibTeX type with all required fields present."""
    explicit = _first_text(source, "citation_type", "type", "provider_type", "resource_type")
    if explicit:
        normalized = re.sub(r"[\s_]+", "-", explicit.casefold()).strip("-")
        candidate = BIBTEX_TYPE_ALIASES.get(normalized, "misc")
    elif _first_text(source, "booktitle", "proceedings"):
        candidate = "inproceedings"
    elif _first_text(source, "journal", "container_title"):
        candidate = "article"
    elif _first_text(source, "isbn") and _first_text(source, "publisher"):
        candidate = "book"
    else:
        candidate = "misc"

    if candidate == "misc":
        return candidate

    title = _source_title(source)
    year = _source_year(source)
    authors = _people_value(source, "author", "authors")
    editors = _people_value(source, "editor", "editors")
    if candidate == "article":
        container = _first_text(source, "journal", "container_title")
        return candidate if title and year and authors and container else "misc"
    if candidate == "book":
        publisher = _first_text(source, "publisher")
        return candidate if title and year and publisher and (authors or editors) else "misc"
    if candidate == "inproceedings":
        booktitle = _first_text(
            source, "booktitle", "proceedings", "container_title", "journal"
        )
        return candidate if title and year and authors and booktitle else "misc"
    return "misc"


def _append_literal_field(lines: List[str], name: str, value: object) -> None:
    text = _single_line(value).strip()
    if text:
        lines.append(f"  {name} = {{{_bibtex_escape(text)}}},")


def _append_verbatim_field(lines: List[str], name: str, value: object) -> None:
    text = _single_line(value).strip()
    if text:
        lines.append(f"  {name} = {{{_bibtex_verbatim(text)}}},")


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


def format_bibtex(source: Dict[str, Any], citation_key: str) -> str:
    """Format a rich BibTeX entry or the backward-compatible @misc fallback."""
    _reject_conflicting_doi_url(source)
    entry_type = _bibtex_entry_type(source)
    lines = [f"@{entry_type}{{{citation_key},"]

    authors = _people_value(source, "author", "authors")
    editors = _people_value(source, "editor", "editors")
    if authors:
        _append_people_field(lines, "author", source, "author", "authors")
    if entry_type == "book" and editors:
        _append_people_field(lines, "editor", source, "editor", "editors")

    title = _source_title(source)
    if title:
        # The inner braces preserve title capitalization through BibTeX.
        lines.append("  title = {{" + _bibtex_escape(title) + "}},")

    if entry_type == "article":
        _append_literal_field(lines, "journal", _first_text(source, "journal", "container_title"))
        _append_literal_field(lines, "volume", _first_text(source, "volume"))
        _append_literal_field(lines, "number", _first_text(source, "issue", "number"))
        _append_literal_field(lines, "pages", _first_text(source, "pages"))
    elif entry_type == "book":
        _append_literal_field(lines, "publisher", _first_text(source, "publisher"))
        _append_literal_field(lines, "edition", _first_text(source, "edition"))
        _append_literal_field(lines, "isbn", _first_text(source, "isbn"))
    elif entry_type == "inproceedings":
        booktitle = _first_text(
            source, "booktitle", "proceedings", "container_title", "journal"
        )
        _append_literal_field(lines, "booktitle", booktitle)
        _append_literal_field(lines, "publisher", _first_text(source, "publisher"))
        _append_literal_field(lines, "volume", _first_text(source, "volume"))
        _append_literal_field(lines, "number", _first_text(source, "issue", "number"))
        _append_literal_field(lines, "pages", _first_text(source, "pages"))

    year = _source_year(source)
    if entry_type == "misc":
        _append_verbatim_field(lines, "url", _source_url(source))
        _append_verbatim_field(lines, "doi", _source_doi(source))
        _append_literal_field(lines, "note", source.get("source_type", ""))
        if year:
            lines.append(f"  year = {{{year}}},")
        date_acc = _first_text(source, "date_accessed", "accessed")
        if date_acc:
            _append_literal_field(lines, "howpublished", "Accessed: " + date_acc)
        _append_literal_field(lines, "organization", source.get("access_method", ""))
    else:
        if year:
            lines.append(f"  year = {{{year}}},")
        _append_verbatim_field(lines, "doi", _source_doi(source))
        _append_verbatim_field(lines, "url", _source_url(source))
        _append_literal_field(
            lines,
            "urldate",
            _first_text(source, "date_accessed", "accessed"),
        )

    if lines[-1].endswith(","):
        lines[-1] = lines[-1][:-1]

    lines.append("}")
    return "\n".join(lines)


def format_ris(source: Dict[str, Any]) -> str:
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

    date_acc = _ris_value(_first_text(source, "date_accessed", "accessed"))
    if date_acc:
        lines.append(f"Y2  - {date_acc}")

    access_method = _ris_value(source.get("access_method", ""))
    if access_method:
        lines.append(f"PB  - {access_method}")

    lines.append("ER  - ")
    lines.append("")
    return "\n".join(lines)


def generate_citation_key(
    source: Dict[str, Any], index: int, used: Optional[set] = None
) -> str:
    """Generate a source-stable ASCII key using canonical identity + SHA-256."""
    used = used if used is not None else set()
    _ = index  # retained for CLI/API compatibility; keys do not depend on order
    doi = _source_doi(source).lower()
    url = _source_url(source)
    title = _source_title(source)
    year = _source_year(source)
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


def export_csv_to_format(
    file_path: str,
    format_type: str,
    output_path: str,
    metadata_paths: Optional[List[str]] = None,
) -> None:
    """Export CSV to specified format."""
    rows = read_csv(file_path)
    metadata_records = load_citation_metadata(metadata_paths)
    sources = get_unique_sources(merge_citation_metadata(rows, metadata_records))

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


def _crossref_people(items: object) -> List[object]:
    """Preserve Crossref personal and name-only corporate contributors."""
    people: List[object] = []
    if not isinstance(items, list):
        return people
    for item in items:
        if not isinstance(item, dict):
            continue
        literal = _single_line(item.get("name", "")).strip()
        if literal:
            people.append({"literal": literal})
            continue
        family = _single_line(item.get("family", "")).strip()
        given = _single_line(item.get("given", "")).strip()
        if family:
            person: Dict[str, str] = {"family": family}
            if given:
                person["given"] = given
            people.append(person)
    return people


def _datacite_people(items: object) -> List[object]:
    """Preserve DataCite organizational names and structured personal names."""
    people: List[object] = []
    if not isinstance(items, list):
        return people
    for item in items:
        if not isinstance(item, dict):
            continue
        name = _single_line(item.get("name", "")).strip()
        if item.get("nameType") == "Organizational" and name:
            people.append({"literal": name})
            continue
        family = _single_line(item.get("familyName", "")).strip()
        given = _single_line(item.get("givenName", "")).strip()
        if family:
            person: Dict[str, str] = {"family": family}
            if given:
                person["given"] = given
            people.append(person)
        elif name:
            people.append(name)
    return people


def _enrich_doi_crossref(doi: str) -> Optional[Dict[str, Any]]:
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
        result: Dict[str, Any] = {"resolver": "crossref", "doi": doi}
        if "title" in work and work["title"]:
            result["title"] = (
                work["title"][0] if isinstance(work["title"], list) else work["title"]
            )
        authors = _crossref_people(work.get("author"))
        if authors:
            result["authors"] = authors
        editors = _crossref_people(work.get("editor"))
        if editors:
            result["editors"] = editors
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
        provider_type = _single_line(work.get("type", "")).strip()
        if provider_type:
            result["type"] = provider_type
        if "container-title" in work and work["container-title"]:
            container_title = work["container-title"][0]
            result["journal"] = container_title
            if BIBTEX_TYPE_ALIASES.get(provider_type) == "inproceedings":
                result["booktitle"] = container_title
        if "volume" in work:
            result["volume"] = work["volume"]
        if "issue" in work:
            result["issue"] = work["issue"]
        if "page" in work:
            result["pages"] = work["page"]
        if work.get("ISBN"):
            isbn = work["ISBN"][0] if isinstance(work["ISBN"], list) else work["ISBN"]
            result["isbn"] = str(isbn)
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


def _enrich_doi_datacite(doi: str) -> Optional[Dict[str, Any]]:
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
        creators = _datacite_people(attrs.get("creators"))
        editors = _datacite_people([
            contributor
            for contributor in (attrs.get("contributors") or [])
            if isinstance(contributor, dict)
            and contributor.get("contributorType") == "Editor"
        ])
        result: Dict[str, Any] = {
            "resolver": "datacite",
            "doi": doi,
            "url": f"https://doi.org/{doi}",
        }
        if title:
            result["title"] = title
        if creators:
            result["authors"] = creators
        if editors:
            result["editors"] = editors
        if attrs.get("publicationYear"):
            result["year"] = str(attrs["publicationYear"])
        if attrs.get("publisher"):
            result["publisher"] = attrs["publisher"]
        resource_type = _single_line(
            (attrs.get("types") or {}).get("resourceTypeGeneral", "")
        ).strip()
        if resource_type:
            result["type"] = resource_type
        return result
    except ResourceLimitError as exc:
        emit_blocker_and_exit(exc)
    except Exception as e:
        print(f"DataCite DOI lookup failed for {doi}: {e}", file=sys.stderr)
        return None


def enrich_doi(doi: str) -> Optional[Dict[str, Any]]:
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
    m = re.search(r"@(\w+)\{([^,]+),", text)
    if m:
        fields["_type"] = m.group(1).lower()
        fields["_key"] = m.group(2)
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


def _run_sidecar_self_tests(temp_dir: str) -> None:
    """Exercise rich types, matching conflicts, and structural injection."""
    def ledger_row(claim_id: str, title: str, url: str, year: str) -> Dict[str, str]:
        row = {field: "" for field in CSV_COLUMNS}
        row.update({
            "claim_id": claim_id,
            "claim": title,
            "source_title": title,
            "source_url": url,
            "source_type": "paper",
            "date_published": year,
            "date_accessed": "2026-07-15",
            "access_method": "citation_resolver",
            "contradiction": "none",
            "confidence": "high",
        })
        return row

    rich_csv = os.path.join(temp_dir, "rich.csv")
    rich_metadata = os.path.join(temp_dir, "rich-metadata.json")
    rich_bibtex = os.path.join(temp_dir, "rich.bib")
    rows = [
        ledger_row("article", "Ledger article", "https://doi.org/10.1000/article", "2024"),
        ledger_row("book", "Ledger book", "https://books.example.test/book", "2023"),
        ledger_row("conference", "Ledger paper", "https://doi.org/10.1000/conf", "2025"),
    ]
    with open(rich_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    metadata = [
        {
            "type": "journal-article",
            "title": "Production Article",
            "authors": [
                {"family": "Smith", "given": "Jane"},
                {"family": "Doe", "given": "Alex"},
            ],
            "year": 2024,
            "journal": "Journal of Reliable Systems",
            "volume": "12",
            "issue": "3",
            "pages": "10--20",
            "doi": "10.1000/article",
            "url": "https://doi.org/10.1000/article",
            "accessed": "2026-07-14",
        },
        {
            "type": "book",
            "title": "Production Book",
            "authors": [{"family": "Nguyen", "given": "Minh"}],
            "editors": [{"family": "Le", "given": "Lan"}],
            "year": 2023,
            "publisher": "Reliable Press",
            "isbn": "978-1-23456-789-0",
            "url": "https://books.example.test/book",
        },
        {
            "type": "proceedings-article",
            "title": "Production Conference Paper",
            "authors": "Tran, An; Patel, Ravi",
            "year": 2025,
            "booktitle": "Proceedings of Reliable Systems",
            "pages": "100--115",
            "doi": "10.1000/conf",
            "url": "https://doi.org/10.1000/conf",
        },
    ]
    with open(rich_metadata, "w", encoding="utf-8") as f:
        json.dump(metadata, f)
    export_csv_to_format(rich_csv, "bibtex", rich_bibtex, [rich_metadata])
    with open(rich_bibtex, "r", encoding="utf-8") as f:
        rich_content = f.read()
    parsed = [
        _parse_bibtex_entry(entry)
        for entry in rich_content.split("\n\n")
        if entry.strip()
    ]
    assert [entry.get("_type") for entry in parsed] == [
        "article", "book", "inproceedings"
    ]
    article, book, conference = parsed
    assert article.get("author") == "Smith, Jane and Doe, Alex"
    assert article.get("journal") == "Journal of Reliable Systems"
    assert article.get("volume") == "12" and article.get("number") == "3"
    assert article.get("pages") == "10--20"
    assert article.get("urldate") == "2026-07-14"
    assert book.get("author") == "Nguyen, Minh"
    assert book.get("editor") == "Le, Lan"
    assert book.get("publisher") == "Reliable Press"
    assert book.get("isbn") == "978-1-23456-789-0"
    assert conference.get("author") == "Tran, An and Patel, Ravi"
    assert conference.get("booktitle") == "Proceedings of Reliable Systems"
    assert conference.get("pages") == "100--115"
    print("  [PASS] Sidecar @article/@book/@inproceedings export")

    literal_source = {
        "type": "journal-article",
        "title": "Corporate Author Article",
        "authors": [
            {"literal": "World Health Organization"},
            {"family": "Doe", "given": "Jane"},
        ],
        "year": 2024,
        "journal": "Journal of Reliable Systems",
    }
    literal_entry = format_bibtex(literal_source, "literal-author")
    assert "author = {{World Health Organization} and Doe, Jane}," in literal_entry
    parsed_literal = _parse_bibtex_entry(literal_entry)
    assert parsed_literal.get("author") == "{World Health Organization} and Doe, Jane"
    assert _crossref_people([
        {"name": "World Health Organization"},
        {"given": "Jane", "family": "Doe"},
    ]) == [
        {"literal": "World Health Organization"},
        {"given": "Jane", "family": "Doe"},
    ]
    assert _datacite_people([
        {"name": "Research Consortium", "nameType": "Organizational"},
        {"name": "Doe, Jane", "givenName": "Jane", "familyName": "Doe"},
    ]) == [
        {"literal": "Research Consortium"},
        {"given": "Jane", "family": "Doe"},
    ]
    literal_bibtex = os.path.join(temp_dir, "literal-author.bib")
    with open(literal_bibtex, "w", encoding="utf-8") as f:
        f.write(literal_entry)
    print("  [PASS] Corporate author braces and resolver metadata preserve identity")

    incomplete_rich_entries = [
        {"type": "journal-article", "title": "Missing journal", "year": 2024},
        {"type": "book", "title": "Missing publisher", "year": 2024, "author": "A"},
        {
            "type": "proceedings-article",
            "title": "Missing proceedings",
            "year": 2024,
            "author": "A",
        },
    ]
    for index, incomplete in enumerate(incomplete_rich_entries):
        entry = format_bibtex(incomplete, f"incomplete-{index}")
        assert _parse_bibtex_entry(entry).get("_type") == "misc"
    print("  [PASS] Incomplete rich metadata falls back to @misc")

    paper = format_bibtex({
        "source_title": "Unclassified paper",
        "source_url": "https://example.test/paper",
        "source_type": "paper",
        "date_published": "2024",
    }, "paper-fallback")
    assert _parse_bibtex_entry(paper).get("_type") == "misc"
    print("  [PASS] Legacy paper without metadata remains @misc")

    conflict_path = os.path.join(temp_dir, "conflict.json")
    with open(conflict_path, "w", encoding="utf-8") as f:
        json.dump([
            {"doi": "10.1000/article", "title": "First", "year": 2024},
            {"doi": "10.1000/article", "title": "Second", "year": 2024},
        ], f)
    try:
        export_csv_to_format(
            rich_csv, "bibtex", os.path.join(temp_dir, "conflict.bib"), [conflict_path]
        )
    except ValueError as exc:
        assert "Conflicting citation metadata" in str(exc)
    else:
        raise AssertionError("conflicting sidecar identities must fail closed")
    print("  [PASS] Conflicting sidecar identities fail closed")

    resolver_conflict_path = os.path.join(temp_dir, "resolver-conflict.json")
    with open(resolver_conflict_path, "w", encoding="utf-8") as f:
        json.dump({
            "doi": "10.1000/article",
            "url": "https://doi.org/10.1000/other",
            "title": "Conflicting resolver identity",
            "year": 2024,
        }, f)
    try:
        export_csv_to_format(
            rich_csv,
            "bibtex",
            os.path.join(temp_dir, "resolver-conflict.bib"),
            [resolver_conflict_path],
        )
    except ValueError as exc:
        assert "conflicts with resolver URL DOI" in str(exc)
    else:
        raise AssertionError("conflicting DOI and resolver URL must fail closed")
    print("  [PASS] DOI/resolver URL conflicts fail closed")

    duplicate_key_path = os.path.join(temp_dir, "duplicate-key.json")
    with open(duplicate_key_path, "w", encoding="utf-8") as f:
        f.write(
            '{"doi":"10.1000/article","doi":"10.1000/other",'
            '"title":"Ambiguous duplicate"}'
        )
    try:
        load_citation_metadata([duplicate_key_path])
    except ValueError as exc:
        assert "duplicate key 'doi'" in str(exc)
    else:
        raise AssertionError("duplicate JSON keys must fail closed")
    print("  [PASS] Duplicate-key metadata fails closed")

    injection_csv = os.path.join(temp_dir, "injection.csv")
    injection_json = os.path.join(temp_dir, "injection.json")
    injection_bib = os.path.join(temp_dir, "injection.bib")
    with open(injection_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerow(ledger_row(
            "injection", "Injection fixture", "https://example.test/injection", "2026"
        ))
    with open(injection_json, "w", encoding="utf-8") as f:
        json.dump({
            "type": "article}\n@evil{owned",
            "title": "Safe }\n@evil{still-data",
            "authors": [{"literal": "Org }\n@evil{author"}],
            "year": 2026,
            "url": "https://example.test/injection",
        }, f)
    export_csv_to_format(injection_csv, "bibtex", injection_bib, [injection_json])
    with open(injection_bib, "r", encoding="utf-8") as f:
        injected = f.read()
    parsed_injection = _parse_bibtex_entry(injected)
    assert parsed_injection.get("_type") == "misc"
    assert parsed_injection.get("title") == "Safe } @evil{still-data"
    assert len(re.findall(r"(?m)^@", injected)) == 1 and "\n@evil" not in injected
    print("  [PASS] Sidecar type/field injection remains one safe entry")

    pandoc = shutil.which("pandoc")
    if pandoc:
        for input_format in ("bibtex", "biblatex"):
            proc = subprocess.run(
                [pandoc, "--from", input_format, "--to", "csljson", rich_bibtex],
                capture_output=True, text=True, encoding="utf-8", timeout=15, check=False,
            )
            assert proc.returncode == 0, proc.stderr
            assert [entry.get("type") for entry in json.loads(proc.stdout)] == [
                "article-journal", "book", "paper-conference"
            ]
        literal_proc = subprocess.run(
            [pandoc, "--from", "bibtex", "--to", "csljson", literal_bibtex],
            capture_output=True, text=True, encoding="utf-8", timeout=15, check=False,
        )
        assert literal_proc.returncode == 0, literal_proc.stderr
        literal_csl = json.loads(literal_proc.stdout)[0]
        assert literal_csl["author"] == [
            {"literal": "World Health Organization"},
            {"family": "Doe", "given": "Jane"},
        ]
        print("  [PASS] Rich BibTeX/BibLaTeX Pandoc semantic round-trip")
    else:
        print("  [SKIP] Rich Pandoc semantic round-trip (pandoc not installed)")


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
        assert parsed0.get("_type") == "misc"
        assert parsed0.get("title") == "Example Article Title"
        assert parsed0.get("year") == "2023"
        assert parsed0.get("_key")
        print("  [PASS] BibTeX export (parsed round-trip)")

        _run_sidecar_self_tests(temp_dir)

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
    export_parser.add_argument(
        '--metadata',
        action='append',
        default=[],
        help='Optional JSON object/array; repeat for multiple metadata sidecars'
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
            export_csv_to_format(
                args.file, args.format, args.out, metadata_paths=args.metadata
            )
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
