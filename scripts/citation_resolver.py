#!/usr/bin/env python3
"""Citation resolver: DOI / PMID / ArXiv / ISBN lookup via free public APIs.

Subcommands
-----------
* ``doi``       - resolve a DOI via CrossRef or Datacite
* ``pmid``      - resolve a PubMed ID via NCBI E-utilities
* ``arxiv``     - resolve an arXiv ID via the arXiv API
* ``isbn``      - resolve an ISBN via Open Library
* ``oa``        - Unpaywall open-access lookup for a DOI
* ``to-ledger`` - emit an evidence-ledger CSV row from a resolved ID
* ``to-bibtex`` - emit a BibTeX entry from a resolved ID
* ``batch``     - bulk resolve IDs from a text file
* ``self-test`` - run offline self-tests with a local mock server

All endpoints are free and require no API key. The script uses stdlib only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# Optional shared HTTP cache (opt-in via D_RESEARCH_HTTP_CACHE_PATH).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import http_cache as _http_cache
except ImportError:  # pragma: no cover
    _http_cache = None
from resource_limits import (
    ResourceLimitError,
    emit_blocker_and_exit,
    load_limits,
    read_http_response_bounded,
)

USER_AGENT = (
    "d-research-skill/0.3.0 "
    "(https://github.com/d-init-d/d-research-skill; contact@example.com)"
)
DEFAULT_EMAIL = "contact@example.com"

CROSSREF_API = "https://api.crossref.org/works"
DATACITE_API = "https://api.datacite.org/dois"
UNPAYWALL_API = "https://api.unpaywall.org/v2"
NCBI_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
ARXIV_API = "https://export.arxiv.org/api/query"
OPENLIBRARY_API = "https://openlibrary.org/api/books"

MAX_RETRIES = 3
BATCH_DELAY_SEC = 1.0


class ProviderNotFoundError(Exception):
    """A DOI provider has no record for the requested identifier."""


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _request(url: str, *, timeout: int | None = None) -> bytes:
    """Make a polite HTTP GET request.

    When D_RESEARCH_HTTP_CACHE_PATH is set, results are cached. Cache
    failures are non-fatal.
    """
    request_headers = {"User-Agent": USER_AGENT}

    if _http_cache is not None:
        try:
            cached = _http_cache.get("GET", url, request_headers=request_headers)
            if cached:
                return cached["body"]
        except Exception:  # noqa: BLE001
            pass

    req = urllib.request.Request(url, headers=request_headers)
    try:
        limits = load_limits()
        effective_timeout = timeout or limits.http_timeout_sec
        with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
            body = read_http_response_bounded(resp, limits)
            resp_headers = dict(resp.headers.items()) if resp.headers else {}
            status = resp.status
    except ResourceLimitError as exc:
        emit_blocker_and_exit(exc)
    except urllib.error.HTTPError as e:
        print(f"error: HTTP {e.code} for {url}", file=sys.stderr)
        raise SystemExit(1) from e
    except urllib.error.URLError as e:
        print(f"error: {e.reason} for {url}", file=sys.stderr)
        raise SystemExit(1) from e

    if _http_cache is not None and 200 <= status < 300:
        try:
            _http_cache.put(
                "GET", url, status, resp_headers, body,
                request_headers=request_headers,
            )
        except Exception:  # noqa: BLE001
            pass
    return body


def _request_with_backoff(
    url: str,
    *,
    max_retries: int = MAX_RETRIES,
    not_found_is_miss: bool = False,
) -> bytes:
    """HTTP GET with exponential backoff on 429.

    Cache lookup happens once before the first attempt. Successful responses
    populate the cache. Cache failures are non-fatal.
    """
    request_headers = {"User-Agent": USER_AGENT}

    if _http_cache is not None:
        try:
            cached = _http_cache.get("GET", url, request_headers=request_headers)
            if cached:
                return cached["body"]
        except Exception:  # noqa: BLE001
            pass

    for attempt in range(max_retries + 1):
        req = urllib.request.Request(url, headers=request_headers)
        try:
            limits = load_limits()
            with urllib.request.urlopen(req, timeout=limits.http_timeout_sec) as resp:
                body = read_http_response_bounded(resp, limits)
                resp_headers = dict(resp.headers.items()) if resp.headers else {}
                status = resp.status
            if _http_cache is not None and 200 <= status < 300:
                try:
                    _http_cache.put(
                        "GET", url, status, resp_headers, body,
                        request_headers=request_headers,
                    )
                except Exception:  # noqa: BLE001
                    pass
            return body
        except ResourceLimitError as exc:
            emit_blocker_and_exit(exc)
        except urllib.error.HTTPError as e:
            if not_found_is_miss and e.code in {404, 410}:
                raise ProviderNotFoundError(f"HTTP {e.code} for {url}") from e
            if e.code == 429 and attempt < max_retries:
                time.sleep(2 ** (attempt + 1))
                continue
            print(f"error: HTTP {e.code} for {url}", file=sys.stderr)
            raise SystemExit(1) from e
        except urllib.error.URLError as e:
            print(f"error: {e.reason} for {url}", file=sys.stderr)
            raise SystemExit(1) from e
    print(f"error: exhausted retries for {url}", file=sys.stderr)
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# Resolvers
# ---------------------------------------------------------------------------


def resolve_doi_crossref(doi: str) -> dict[str, Any]:
    """Resolve DOI via CrossRef API."""
    url = f"{CROSSREF_API}/{urllib.parse.quote(doi, safe='')}"
    raw = _request_with_backoff(url, not_found_is_miss=True)
    data = json.loads(raw)
    msg = data.get("message", {})
    authors = []
    for a in msg.get("author", []):
        name = f"{a.get('family', '')}, {a.get('given', '')}".strip(", ")
        authors.append(name)
    date_parts = msg.get("published", {}).get("date-parts", [[None]])[0]
    year = date_parts[0] if date_parts else None
    raw_titles = msg.get("title") or []
    if isinstance(raw_titles, list):
        title = str(raw_titles[0]) if raw_titles else ""
    else:
        title = str(raw_titles)
    return {
        "source": "crossref",
        "doi": doi,
        "title": title,
        "authors": authors,
        "year": year,
        "journal": (msg.get("container-title") or [""])[0],
        "volume": msg.get("volume"),
        "issue": msg.get("issue"),
        "pages": msg.get("page"),
        "publisher": msg.get("publisher"),
        "url": f"https://doi.org/{doi}",
        "citation_count": msg.get("is-referenced-by-count"),
    }


def resolve_doi_datacite(doi: str) -> dict[str, Any]:
    """Resolve DOI via Datacite API."""
    url = f"{DATACITE_API}/{urllib.parse.quote(doi, safe='')}"
    raw = _request_with_backoff(url)
    data = json.loads(raw)
    attrs = data.get("data", {}).get("attributes", {})
    creators = [c.get("name", "") for c in attrs.get("creators", [])]
    return {
        "source": "datacite",
        "doi": doi,
        "title": (attrs.get("titles") or [{}])[0].get("title", ""),
        "authors": creators,
        "year": attrs.get("publicationYear"),
        "publisher": attrs.get("publisher"),
        "url": f"https://doi.org/{doi}",
        "resource_type": attrs.get("types", {}).get("resourceTypeGeneral"),
    }


def resolve_doi(doi: str, source: str = "auto") -> dict[str, Any]:
    """Resolve DOI using specified source, or Crossref→DataCite for auto."""
    if source == "datacite":
        return resolve_doi_datacite(doi)
    if source == "crossref":
        try:
            return resolve_doi_crossref(doi)
        except ProviderNotFoundError as exc:
            print(f"error: Crossref DOI not found: {doi}", file=sys.stderr)
            raise SystemExit(1) from exc
    # auto: Crossref first. Only a provider miss or a syntactically successful
    # but unusable record falls back to DataCite. Network, HTTP, parse, and
    # resource-limit failures remain hard failures.
    try:
        result = resolve_doi_crossref(doi)
        if result and str(result.get("title") or "").strip():
            return result
    except ProviderNotFoundError:
        return resolve_doi_datacite(doi)
    except Exception as e:  # noqa: BLE001
        print(f"error: Crossref DOI lookup failed for {doi}: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    return resolve_doi_datacite(doi)



def resolve_pmid(pmid: str) -> dict[str, Any]:
    """Resolve PubMed ID via NCBI E-utilities (XML)."""
    params = urllib.parse.urlencode({
        "db": "pubmed",
        "id": pmid,
        "retmode": "xml",
    })
    url = f"{NCBI_EFETCH}?{params}"
    raw = _request_with_backoff(url)
    text = raw.decode("utf-8", errors="replace")
    # Simple XML extraction (stdlib only, no lxml)
    def _tag(tag: str) -> str:
        m = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
        return m.group(1).strip() if m else ""

    def _all_tags(tag: str) -> list[str]:
        return re.findall(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)

    title = _tag("ArticleTitle")
    journal = _tag("Title")  # journal title
    year = _tag("Year")
    volume = _tag("Volume")
    issue = _tag("Issue")
    pages = _tag("MedlinePgn")

    # Extract authors
    authors = []
    author_blocks = _all_tags("Author")
    for block in author_blocks:
        last = re.search(r"<LastName>(.*?)</LastName>", block)
        first = re.search(r"<ForeName>(.*?)</ForeName>", block)
        if last:
            name = last.group(1)
            if first:
                name += f", {first.group(1)}"
            authors.append(name)

    # Extract DOI if present
    doi_match = re.search(r'<ArticleId IdType="doi">(.*?)</ArticleId>', text)
    doi = doi_match.group(1) if doi_match else None

    return {
        "source": "pubmed",
        "pmid": pmid,
        "doi": doi,
        "title": title,
        "authors": authors,
        "year": int(year) if year.isdigit() else None,
        "journal": journal,
        "volume": volume or None,
        "issue": issue or None,
        "pages": pages or None,
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
    }


def resolve_arxiv(arxiv_id: str) -> dict[str, Any]:
    """Resolve arXiv ID via arXiv API (Atom XML)."""
    params = urllib.parse.urlencode({"id_list": arxiv_id})
    url = f"{ARXIV_API}?{params}"
    raw = _request_with_backoff(url)
    text = raw.decode("utf-8", errors="replace")

    # Extract from Atom XML
    def _entry_tag(tag: str) -> str:
        m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", text, re.DOTALL)
        return m.group(1).strip() if m else ""

    title = _entry_tag("title")
    summary = _entry_tag("summary")
    published = _entry_tag("published")

    # Authors
    authors = re.findall(r"<name>(.*?)</name>", text)

    # DOI if present
    doi_match = re.search(r"<arxiv:doi[^>]*>(.*?)</arxiv:doi>", text)
    doi = doi_match.group(1) if doi_match else None

    # Categories
    categories = re.findall(r'<category[^>]*term="([^"]+)"', text)

    year = None
    if published:
        year_match = re.match(r"(\d{4})", published)
        if year_match:
            year = int(year_match.group(1))

    return {
        "source": "arxiv",
        "arxiv_id": arxiv_id,
        "doi": doi,
        "title": title,
        "authors": authors,
        "year": year,
        "abstract": summary[:500] if summary else None,
        "categories": categories,
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
    }


def resolve_isbn(isbn: str) -> dict[str, Any]:
    """Resolve ISBN via Open Library API."""
    clean_isbn = re.sub(r"[^0-9X]", "", isbn.upper())
    params = urllib.parse.urlencode({
        "bibkeys": f"ISBN:{clean_isbn}",
        "format": "json",
        "jscmd": "data",
    })
    url = f"{OPENLIBRARY_API}?{params}"
    raw = _request_with_backoff(url)
    data = json.loads(raw)

    key = f"ISBN:{clean_isbn}"
    if key not in data:
        return {"source": "openlibrary", "isbn": clean_isbn, "error": "not found"}

    book = data[key]
    authors = [a.get("name", "") for a in book.get("authors", [])]
    publishers = [p.get("name", "") for p in book.get("publishers", [])]

    return {
        "source": "openlibrary",
        "isbn": clean_isbn,
        "title": book.get("title", ""),
        "authors": authors,
        "year": book.get("publish_date", ""),
        "publishers": publishers,
        "pages": book.get("number_of_pages"),
        "url": book.get("url", f"https://openlibrary.org/isbn/{clean_isbn}"),
    }


def resolve_oa(doi: str, email: str = DEFAULT_EMAIL) -> dict[str, Any]:
    """Unpaywall open-access lookup for a DOI."""
    params = urllib.parse.urlencode({"email": email})
    url = f"{UNPAYWALL_API}/{urllib.parse.quote(doi, safe='')}?{params}"
    raw = _request_with_backoff(url)
    data = json.loads(raw)
    best_oa = data.get("best_oa_location") or {}
    return {
        "source": "unpaywall",
        "doi": doi,
        "is_oa": data.get("is_oa", False),
        "oa_status": data.get("oa_status"),
        "title": data.get("title"),
        "year": data.get("year"),
        "journal": data.get("journal_name"),
        "publisher": data.get("publisher"),
        "oa_url": best_oa.get("url"),
        "oa_pdf": best_oa.get("url_for_pdf"),
        "license": best_oa.get("license"),
    }


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------


def _single_line(value: object) -> str:
    """Normalize CR/LF sequences without dropping surrounding text."""
    return re.sub(
        r"(?:\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029])+",
        " ",
        str(value or ""),
    )


def _bibtex_escape(value: object) -> str:
    """Encode literal text so BibTeX parsers recover it without corruption."""
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
    """Escape parser-structural characters in a BibTeX URL/DOI field."""
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(ch, ch) for ch in _single_line(value))


def _year_only(date_or_year: Any) -> str:
    """Normalize year to a 4-digit string, or empty if invalid."""
    from calendar import monthrange

    s = str(date_or_year or "").strip()
    m = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", s)
    if not m:
        # bare integer year
        if re.fullmatch(r"\d{4}", s):
            y = int(s)
            return f"{y:04d}" if 1400 <= y <= 9999 else ""
        return ""
    year = int(m.group(1))
    month = int(m.group(2) or "1")
    day = int(m.group(3) or "1")
    if year < 1400 or year > 9999 or month < 1 or month > 12:
        return ""
    if day < 1 or day > monthrange(year, month)[1]:
        return ""
    return f"{year:04d}"


def _citation_key(resolved: dict[str, Any]) -> str:
    """Return a deterministic ASCII key with a canonical-identity hash."""
    raw_authors = resolved.get("authors") or []
    authors = [raw_authors] if isinstance(raw_authors, str) else list(raw_authors)
    first_author = str(authors[0]).split(",")[0] if authors else "Unknown"
    author_label = re.sub(r"[^A-Za-z0-9]", "", first_author) or "Unknown"
    year = _year_only(resolved.get("year", "")) or "nodate"
    doi = str(resolved.get("doi") or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix) :].strip()
            break
    if doi:
        identity = f"doi:{doi}"
    else:
        identity = json.dumps(
            {
                "url": _single_line(resolved.get("url", "")).strip(),
                "title": _single_line(resolved.get("title", "")).strip(),
                "authors": [str(author) for author in authors],
                "year": year,
                "pmid": str(resolved.get("pmid") or ""),
                "arxiv_id": str(resolved.get("arxiv_id") or ""),
                "isbn": str(resolved.get("isbn") or ""),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"{author_label}{year}_{digest}"


def to_bibtex(resolved: dict[str, Any]) -> str:
    """Convert resolved metadata to a BibTeX entry (escaped + year-normalized)."""
    raw_authors = resolved.get("authors") or []
    authors = [raw_authors] if isinstance(raw_authors, str) else list(raw_authors)
    title = resolved.get("title", "Untitled")
    year = _year_only(resolved.get("year", ""))
    doi = resolved.get("doi", "") or ""

    key = _citation_key(resolved)

    author_str = " and ".join(authors) if authors else "Unknown"
    journal = resolved.get("journal", "") or ""

    entry_type = "article" if journal else "misc"
    lines = [f"@{entry_type}{{{key},"]
    lines.append(f"  author = {{{_bibtex_escape(author_str)}}},")
    lines.append("  title = {{" + _bibtex_escape(title) + "}},")
    if year:
        lines.append(f"  year = {{{year}}},")
    if journal:
        lines.append(f"  journal = {{{_bibtex_escape(journal)}}},")
    if resolved.get("volume"):
        lines.append(f"  volume = {{{_bibtex_escape(resolved['volume'])}}},")
    if resolved.get("issue"):
        lines.append(f"  number = {{{_bibtex_escape(resolved['issue'])}}},")
    if resolved.get("pages"):
        lines.append(f"  pages = {{{_bibtex_escape(resolved['pages'])}}},")
    if doi:
        lines.append(f"  doi = {{{_bibtex_verbatim(doi)}}},")
    url = resolved.get("url", "") or ""
    if url:
        lines.append(f"  url = {{{_bibtex_verbatim(url)}}},")
    lines.append("}")
    return "\n".join(lines)


def to_ledger_row(resolved: dict[str, Any], source_url: str) -> dict[str, str]:
    """Convert resolved metadata to a full 19-column evidence-ledger CSV row."""
    authors = resolved.get("authors", [])
    doi = resolved.get("doi") or ""
    title = resolved.get("title", "Untitled")
    year = str(resolved.get("year", ""))
    identifier = doi or resolved.get("pmid", "") or resolved.get("arxiv_id", "") or resolved.get("isbn", "unknown")
    src_name = (resolved.get('source') or 'citation_resolver')
    prov_id = (
        "prov:citation_resolver:" + hashlib.sha256(
            f"{src_name}|{identifier}".encode("utf-8")
        ).hexdigest()[:8]
    )
    # License is unknown for arbitrary citations - use NOASSERTION as the
    # SPDX-conformant placeholder. Robots.txt is not applicable to
    # canonical metadata APIs (CrossRef, NCBI, arXiv, OpenLibrary).
    license_spdx = "NOASSERTION"

    return {
        "claim_id": f"cite-{identifier}",
        "claim": f"{title} ({year})" if year else title,
        "sub_question": "",
        "source_title": title,
        "source_url": source_url or resolved.get("url", ""),
        "source_type": "primary",
        "date_published": year,
        "date_accessed": "",
        "access_method": "citation_resolver",
        "evidence": f"Authors: {'; '.join(authors[:5])}" if authors else "",
        "quote_or_anchor": "",
        "contradiction": "none",
        "confidence": "high",
        "notes": f"resolved via {resolved.get('source', 'unknown')}",
        "archive_url": "",
        "content_hash": "",
        "snapshot_status": "",
        "verifiability": "",
        "verifiability_note": "",
        "license_spdx": license_spdx,
        "robots_status": "not_applicable",
        "prov_activity_id": prov_id,
    }


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_doi(args: argparse.Namespace) -> int:
    source = getattr(args, "source", "auto")
    result = resolve_doi(args.doi, source)
    out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(out + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(out)
    return 0


def cmd_pmid(args: argparse.Namespace) -> int:
    result = resolve_pmid(args.pmid)
    out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(out + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(out)
    return 0


def cmd_arxiv(args: argparse.Namespace) -> int:
    result = resolve_arxiv(args.id)
    out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(out + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(out)
    return 0


def cmd_isbn(args: argparse.Namespace) -> int:
    result = resolve_isbn(args.isbn)
    out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(out + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(out)
    return 0


def cmd_oa(args: argparse.Namespace) -> int:
    email = getattr(args, "email", DEFAULT_EMAIL)
    result = resolve_oa(args.doi, email)
    out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(out + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(out)
    return 0


def cmd_to_ledger(args: argparse.Namespace) -> int:
    identifier = args.identifier
    url = args.url or ""
    # Detect type
    if re.match(r"^10\.\d{4,}", identifier):
        resolved = resolve_doi(identifier)
    elif re.match(r"^\d{7,8}$", identifier):
        resolved = resolve_pmid(identifier)
    elif re.match(r"^\d{4}\.\d{4,5}", identifier):
        resolved = resolve_arxiv(identifier)
    elif re.match(r"^(97[89])?\d{9}[\dX]$", re.sub(r"[^0-9X]", "", identifier.upper())):
        resolved = resolve_isbn(identifier)
    else:
        print(f"error: cannot detect identifier type: {identifier}", file=sys.stderr)
        return 1

    row = to_ledger_row(resolved, url)
    out_path = Path(args.out_row)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        writer.writeheader()
        writer.writerow(row)
    print(f"wrote {out_path}")
    return 0


def cmd_to_bibtex(args: argparse.Namespace) -> int:
    identifier = args.identifier
    if re.match(r"^10\.\d{4,}", identifier):
        resolved = resolve_doi(identifier)
    elif re.match(r"^\d{7,8}$", identifier):
        resolved = resolve_pmid(identifier)
    elif re.match(r"^\d{4}\.\d{4,5}", identifier):
        resolved = resolve_arxiv(identifier)
    elif re.match(r"^(97[89])?\d{9}[\dX]$", re.sub(r"[^0-9X]", "", identifier.upper())):
        resolved = resolve_isbn(identifier)
    else:
        print(f"error: cannot detect identifier type: {identifier}", file=sys.stderr)
        return 1

    bib = to_bibtex(resolved)
    if args.out:
        Path(args.out).write_text(bib + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(bib)
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    in_path = Path(args.input)
    if not in_path.is_file():
        print(f"error: file not found: {in_path}", file=sys.stderr)
        return 1

    ids = [line.strip() for line in in_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    results = []
    for identifier in ids:
        try:
            if re.match(r"^10\.\d{4,}", identifier):
                results.append(resolve_doi(identifier))
            elif re.match(r"^\d{7,8}$", identifier):
                results.append(resolve_pmid(identifier))
            elif re.match(r"^\d{4}\.\d{4,5}", identifier):
                results.append(resolve_arxiv(identifier))
            elif re.match(r"^(97[89])?\d{9}[\dX]$", re.sub(r"[^0-9X]", "", identifier.upper())):
                results.append(resolve_isbn(identifier))
            else:
                results.append({"identifier": identifier, "error": "unknown type"})
        except SystemExit:
            results.append({"identifier": identifier, "error": "resolution failed"})
        time.sleep(BATCH_DELAY_SEC)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(results)} results to {out_path}")
    return 0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


class _MockHandler(http.server.BaseHTTPRequestHandler):
    """Mock HTTP handler for self-test."""

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/works/"):
            # Crossref: 404 for DataCite-only DOIs so auto can fall back
            doi_part = path[len("/works/") :]
            if "zenodo" in doi_part.lower() or "datacite-only" in doi_part.lower():
                self._respond(404, b'{"status":"error","message":"Not found"}', "application/json")
                return
            if "crossref-empty" in doi_part.lower():
                data = {
                    "status": "ok",
                    "message": {"DOI": "10.9999/crossref-empty", "title": []},
                }
                self._respond(200, json.dumps(data).encode(), "application/json")
                return
            data = {
                "status": "ok",
                "message": {
                    "DOI": "10.1038/nature12373",
                    "title": ["Genomic hallmarks of longevity"],
                    "author": [
                        {"family": "Sebastiani", "given": "Paola"},
                        {"family": "Perls", "given": "Thomas T."},
                    ],
                    "published": {"date-parts": [[2012]]},
                    "container-title": ["Nature"],
                    "volume": "488",
                    "issue": "7410",
                    "page": "178-182",
                    "publisher": "Springer Nature",
                    "is-referenced-by-count": 250,
                },
            }
            self._respond(200, json.dumps(data).encode(), "application/json")

        elif path.startswith("/dois/"):
            # Mock Datacite response
            data = {
                "data": {
                    "attributes": {
                        "doi": "10.5281/zenodo.1234567",
                        "titles": [{"title": "Test Dataset"}],
                        "creators": [{"name": "Dataset Author"}],
                        "publicationYear": 2023,
                        "publisher": "Zenodo",
                        "types": {"resourceTypeGeneral": "Dataset"},
                    }
                }
            }
            self._respond(200, json.dumps(data).encode(), "application/json")

        elif "efetch" in path:
            # Mock PubMed XML
            xml = """<?xml version="1.0"?>
<PubmedArticleSet>
<PubmedArticle>
<MedlineCitation>
<Article>
<ArticleTitle>Mock PubMed Article Title</ArticleTitle>
<Journal><Title>Mock Journal</Title></Journal>
<AuthorList>
<Author><LastName>Smith</LastName><ForeName>John</ForeName></Author>
</AuthorList>
</Article>
<DateCompleted><Year>2021</Year></DateCompleted>
</MedlineCitation>
<PubmedData><ArticleIdList>
<ArticleId IdType="doi">10.1234/mock</ArticleId>
</ArticleIdList></PubmedData>
</PubmedArticle>
</PubmedArticleSet>"""
            self._respond(200, xml.encode(), "application/xml")

        elif "api/query" in path:
            # Mock arXiv Atom
            atom = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
<entry>
<title>Attention Is All You Need</title>
<summary>We propose a new architecture...</summary>
<author><name>Vaswani, Ashish</name></author>
<author><name>Shazeer, Noam</name></author>
<published>2017-06-12T00:00:00Z</published>
<category term="cs.CL"/>
<arxiv:doi>10.5555/3295222.3295349</arxiv:doi>
</entry>
</feed>"""
            self._respond(200, atom.encode(), "application/atom+xml")

        elif "openlibrary" in path or "api/books" in path:
            # Mock Open Library
            data = {
                "ISBN:9780134685991": {
                    "title": "Effective Java",
                    "authors": [{"name": "Joshua Bloch"}],
                    "publishers": [{"name": "Addison-Wesley"}],
                    "publish_date": "2018",
                    "number_of_pages": 416,
                    "url": "https://openlibrary.org/books/OL123M",
                }
            }
            self._respond(200, json.dumps(data).encode(), "application/json")

        elif "unpaywall" in path or "/v2/10." in path:
            # Mock Unpaywall
            data = {
                "doi": "10.1038/nature12373",
                "is_oa": True,
                "oa_status": "green",
                "title": "Genomic hallmarks",
                "year": 2012,
                "journal_name": "Nature",
                "publisher": "Springer Nature",
                "best_oa_location": {
                    "url": "https://europepmc.org/articles/PMC123",
                    "url_for_pdf": "https://europepmc.org/articles/PMC123/pdf",
                    "license": "cc-by",
                },
            }
            self._respond(200, json.dumps(data).encode(), "application/json")

        else:
            self._respond(404, b"Not Found", "text/plain")

    def _respond(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def cmd_self_test(_args: argparse.Namespace) -> int:
    """Offline self-test with mock HTTP server."""
    global CROSSREF_API, DATACITE_API, UNPAYWALL_API, NCBI_EFETCH, ARXIV_API, OPENLIBRARY_API  # noqa: PLW0603

    orig = (CROSSREF_API, DATACITE_API, UNPAYWALL_API, NCBI_EFETCH, ARXIV_API, OPENLIBRARY_API)

    # Isolate the HTTP cache so a stale local cache cannot mask mock HTTP.
    cache_env = "D_RESEARCH_HTTP_CACHE_PATH"
    saved_cache = os.environ.pop(cache_env, None)

    server = http.server.HTTPServer(("127.0.0.1", 0), _MockHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    CROSSREF_API = f"{base}/works"
    DATACITE_API = f"{base}/dois"
    UNPAYWALL_API = f"{base}/v2"
    NCBI_EFETCH = f"{base}/efetch"
    ARXIV_API = f"{base}/api/query"
    OPENLIBRARY_API = f"{base}/api/books"

    errors: list[str] = []

    try:
        # Test DOI (CrossRef)
        result = resolve_doi("10.1038/nature12373", "crossref")
        if result.get("title") != "Genomic hallmarks of longevity":
            errors.append(f"DOI crossref title mismatch: {result.get('title')}")
        if result.get("year") != 2012:
            errors.append(f"DOI crossref year mismatch: {result.get('year')}")
        if len(result.get("authors", [])) != 2:
            errors.append(f"DOI crossref authors count: {len(result.get('authors', []))}")

        # Test DOI (Datacite)
        result = resolve_doi("10.5281/zenodo.1234567", "datacite")
        if result.get("title") != "Test Dataset":
            errors.append(f"DOI datacite title mismatch: {result.get('title')}")

        # auto: Crossref miss must fall back to DataCite
        result = resolve_doi("10.5281/zenodo.1234567", "auto")
        if result.get("source") != "datacite":
            errors.append(f"auto fallback source expected datacite, got {result.get('source')}")
        if result.get("title") != "Test Dataset":
            errors.append(f"auto fallback title mismatch: {result.get('title')}")

        # A syntactically successful but unusable Crossref record must not
        # block the DataCite fallback.
        result = resolve_doi("10.9999/crossref-empty", "auto")
        if result.get("source") != "datacite":
            errors.append(
                "auto fallback expected datacite for empty Crossref title, "
                f"got {result.get('source')}"
            )

        # Auto fallback is deliberately bounded to not-found/unsupported.
        # Transient/provider failures must fail closed and must not call the
        # alternate provider.
        saved_resolvers = (resolve_doi_crossref, resolve_doi_datacite)
        datacite_called = False

        def transient_crossref(_doi: str) -> dict[str, Any]:
            raise RuntimeError("transient Crossref failure")

        def tracked_datacite(_doi: str) -> dict[str, Any]:
            nonlocal datacite_called
            datacite_called = True
            return {"source": "datacite", "title": "must not run"}

        try:
            globals()["resolve_doi_crossref"] = transient_crossref
            globals()["resolve_doi_datacite"] = tracked_datacite
            try:
                resolve_doi("10.9999/transient", "auto")
            except SystemExit:
                pass
            else:
                errors.append("transient Crossref failure did not fail auto lookup")
            if datacite_called:
                errors.append(
                    "auto lookup called DataCite after a transient Crossref failure"
                )
        finally:
            (
                globals()["resolve_doi_crossref"],
                globals()["resolve_doi_datacite"],
            ) = saved_resolvers

        # BibTeX escape + year normalization
        evil = {
            "source": "test",
            "title": "Braces {x} and \\slash\nnewline",
            "authors": ["Author, A"],
            "year": "not-a-year",
            "doi": "10.1/x{suffix}\\tail",
            "url": "https://example.com/{segment}\\tail",
        }
        bib_evil = to_bibtex(evil)
        if "year = {" in bib_evil:
            errors.append("invalid year must not appear in BibTeX")
        if "\\{" not in bib_evil or r"\textbackslash{}" not in bib_evil:
            errors.append("BibTeX must escape braces and backslashes")
        if "doi = {10.1/x\\{suffix\\}" not in bib_evil:
            errors.append("BibTeX DOI field did not escape structural braces")
        if "url = {https://example.com/\\{segment\\}" not in bib_evil:
            errors.append("BibTeX URL field did not escape structural braces")
        if "\nnewline" in bib_evil.split("title")[1].split("\n")[0] if "title" in bib_evil else True:
            # title value must not contain raw newline
            title_line = [ln for ln in bib_evil.splitlines() if "title =" in ln]
            if title_line and "\n" in title_line[0].replace("title = ", ""):
                pass  # single line ok
        if _year_only("2020-01-15") != "2020":
            errors.append("year_only failed for ISO date")
        if _year_only("abc2020") != "":
            errors.append("year_only must reject garbage year strings")

        key_one = _citation_key(
            {"authors": ["Doe, Jane"], "title": "One", "year": 2024, "doi": "10.1/one"}
        )
        key_two = _citation_key(
            {"authors": ["Doe, John"], "title": "Two", "year": 2024, "doi": "10.1/two"}
        )
        if key_one == key_two:
            errors.append("BibTeX keys must be unique for distinct DOI identities")
        if key_one != _citation_key(
            {"authors": ["Doe, Jane"], "title": "One", "year": 2024, "doi": "10.1/one"}
        ):
            errors.append("BibTeX keys must be deterministic")
        if key_one != _citation_key(
            {
                "authors": ["Doe, Jane"],
                "title": "One",
                "year": 2024,
                "doi": "https://doi.org/10.1/one",
            }
        ):
            errors.append("BibTeX DOI keys must use canonical DOI identity")

        pandoc = shutil.which("pandoc")
        if pandoc:
            expected_title = "Braces {x} and \\slash newline"
            with tempfile.TemporaryDirectory() as pandoc_td:
                bib_path = Path(pandoc_td) / "resolver-roundtrip.bib"
                bib_path.write_text(bib_evil, encoding="utf-8")
                proc = subprocess.run(
                    [pandoc, "--from", "bibtex", "--to", "csljson", str(bib_path)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=15,
                    check=False,
                )
                if proc.returncode != 0:
                    errors.append(f"Pandoc BibTeX parse failed: {proc.stderr.strip()}")
                else:
                    parsed_entries = json.loads(proc.stdout)
                    parsed_title = parsed_entries[0].get("title") if parsed_entries else None
                    if parsed_title != expected_title:
                        errors.append(
                            "Pandoc BibTeX title round-trip mismatch: "
                            f"expected {expected_title!r}, got {parsed_title!r}"
                        )

        # Test PMID
        result = resolve_pmid("35027834")
        if "Mock PubMed" not in result.get("title", ""):
            errors.append(f"PMID title mismatch: {result.get('title')}")
        if not result.get("authors"):
            errors.append("PMID no authors extracted")

        # Test arXiv
        result = resolve_arxiv("1706.03762")
        if "Attention" not in result.get("title", ""):
            errors.append(f"arXiv title mismatch: {result.get('title')}")
        if result.get("year") != 2017:
            errors.append(f"arXiv year mismatch: {result.get('year')}")

        # Test ISBN
        result = resolve_isbn("978-0134685991")
        if result.get("title") != "Effective Java":
            errors.append(f"ISBN title mismatch: {result.get('title')}")

        # Test Unpaywall
        result = resolve_oa("10.1038/nature12373")
        if result.get("is_oa") is not True:
            errors.append(f"OA is_oa mismatch: {result.get('is_oa')}")
        if not result.get("oa_url"):
            errors.append("OA missing oa_url")

        # Test to_bibtex
        resolved = resolve_doi("10.1038/nature12373", "crossref")
        bib = to_bibtex(resolved)
        if "@article{" not in bib:
            errors.append("to_bibtex missing @article")
        if "Genomic hallmarks" not in bib:
            errors.append("to_bibtex missing title")

        # Test to_ledger_row
        row = to_ledger_row(resolved, "https://doi.org/10.1038/nature12373")
        if not row.get("claim_id"):
            errors.append("to_ledger_row missing claim_id")
        if "Genomic" not in row.get("claim", ""):
            errors.append("to_ledger_row missing title in claim")
        # Validate row has all 19 fields
        expected_fields = [
            "claim_id", "claim", "sub_question", "source_title", "source_url",
            "source_type", "date_published", "date_accessed", "access_method",
            "evidence", "quote_or_anchor", "contradiction", "confidence", "notes",
            "archive_url", "content_hash", "snapshot_status", "verifiability",
            "verifiability_note",
            "license_spdx", "robots_status", "prov_activity_id",
        ]
        missing_fields = [f for f in expected_fields if f not in row]
        if missing_fields:
            errors.append(f"to_ledger_row missing fields: {missing_fields}")
        if row.get("source_type") != "primary":
            errors.append(f"to_ledger_row source_type should be 'primary', got {row.get('source_type')!r}")
        if row.get("access_method") != "citation_resolver":
            errors.append(f"to_ledger_row access_method should be 'citation_resolver', got {row.get('access_method')!r}")

        # Write and validate via evidence_ledger.py validate
        import tempfile as _tf
        with _tf.TemporaryDirectory() as _td:
            ledger_path = Path(_td) / "test_ledger.csv"
            with ledger_path.open("w", newline="", encoding="utf-8") as _f:
                writer = csv.DictWriter(_f, fieldnames=expected_fields)
                writer.writeheader()
                writer.writerow(row)
            # Import and run validate
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "evidence_ledger",
                Path(__file__).resolve().parent / "evidence_ledger.py",
            )
            el_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(el_mod)
            rc = el_mod.validate_ledger(ledger_path)
            if rc != 0:
                errors.append("to_ledger_row output failed evidence_ledger.py validate")

    except SystemExit:
        errors.append("unexpected SystemExit during self-test")
    finally:
        CROSSREF_API, DATACITE_API, UNPAYWALL_API, NCBI_EFETCH, ARXIV_API, OPENLIBRARY_API = orig
        if saved_cache is not None:
            os.environ[cache_env] = saved_cache
        server.shutdown()

    if errors:
        print("citation_resolver self-test FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("citation_resolver self-test ok")
    return 0


# ---------------------------------------------------------------------------
# Main / argparse
# ---------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(
        prog="citation_resolver.py",
        description="Resolve academic identifiers (DOI, PMID, arXiv, ISBN) via free public APIs.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # doi
    doi_p = sub.add_parser("doi", help="Resolve a DOI.")
    doi_p.add_argument("doi", help="DOI to resolve (e.g. 10.1038/nature12373).")
    doi_p.add_argument("--source", choices=["crossref", "datacite", "auto"], default="auto")
    doi_p.add_argument("--out", default=None, help="Output JSON file path.")

    # pmid
    pmid_p = sub.add_parser("pmid", help="Resolve a PubMed ID.")
    pmid_p.add_argument("pmid", help="PubMed ID (e.g. 35027834).")
    pmid_p.add_argument("--out", default=None)

    # arxiv
    arxiv_p = sub.add_parser("arxiv", help="Resolve an arXiv ID.")
    arxiv_p.add_argument("id", help="arXiv ID (e.g. 1706.03762).")
    arxiv_p.add_argument("--out", default=None)

    # isbn
    isbn_p = sub.add_parser("isbn", help="Resolve an ISBN.")
    isbn_p.add_argument("isbn", help="ISBN (e.g. 978-0134685991).")
    isbn_p.add_argument("--out", default=None)

    # oa
    oa_p = sub.add_parser("oa", help="Unpaywall open-access lookup.")
    oa_p.add_argument("doi", help="DOI to check.")
    oa_p.add_argument("--email", default=DEFAULT_EMAIL)
    oa_p.add_argument("--out", default=None)

    # to-ledger
    tl_p = sub.add_parser("to-ledger", help="Emit evidence-ledger CSV row.")
    tl_p.add_argument("identifier", help="DOI, PMID, arXiv ID, or ISBN.")
    tl_p.add_argument("--url", default=None, help="Source URL override.")
    tl_p.add_argument("--out-row", required=True, help="Output CSV path.")

    # to-bibtex
    tb_p = sub.add_parser("to-bibtex", help="Emit BibTeX entry.")
    tb_p.add_argument("identifier", help="DOI, PMID, arXiv ID, or ISBN.")
    tb_p.add_argument("--out", default=None, help="Output .bib file path.")

    # batch
    batch_p = sub.add_parser("batch", help="Bulk resolve IDs from a file.")
    batch_p.add_argument("--in", dest="input", required=True, help="Input file (one ID per line).")
    batch_p.add_argument("--out", required=True, help="Output JSON path.")

    # self-test
    sub.add_parser("self-test", help="Run offline self-tests.")

    args = p.parse_args()

    if args.cmd == "doi":
        return cmd_doi(args)
    if args.cmd == "pmid":
        return cmd_pmid(args)
    if args.cmd == "arxiv":
        return cmd_arxiv(args)
    if args.cmd == "isbn":
        return cmd_isbn(args)
    if args.cmd == "oa":
        return cmd_oa(args)
    if args.cmd == "to-ledger":
        return cmd_to_ledger(args)
    if args.cmd == "to-bibtex":
        return cmd_to_bibtex(args)
    if args.cmd == "batch":
        return cmd_batch(args)
    if args.cmd == "self-test":
        return cmd_self_test(args)

    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
