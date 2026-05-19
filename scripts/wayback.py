#!/usr/bin/env python3
"""Wayback Machine integration: lookup, nearest, save, diff, self-test.

Subcommands
-----------
* ``lookup``    - list archived snapshots of a URL from the CDX API
* ``nearest``   - find the closest snapshot to a given timestamp
* ``save``      - submit a URL to Save Page Now
* ``diff``      - compare content between two timestamps
* ``self-test`` - run offline self-tests with a local mock server

Lawful-access note
------------------
This script only queries public Internet Archive APIs (CDX, Availability,
Save Page Now). It does not bypass any access control or rate limit.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import http.server
import io
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

# Optional shared HTTP cache (opt-in via D_RESEARCH_HTTP_CACHE_PATH).
# Imported via sys.path manipulation so this script can be run directly.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import http_cache as _http_cache
except ImportError:  # pragma: no cover
    _http_cache = None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CDX_API = "http://web.archive.org/cdx/search/cdx"
AVAILABILITY_API = "http://archive.org/wayback/available"
SAVE_URL_PREFIX = "https://web.archive.org/save/"
RATE_LIMIT_PER_MIN = 15
MAX_RETRIES = 3

USER_AGENT = "d-research-skill/0.2.0 (https://github.com/d-init-d/d-research-skill)"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_cdx_url(
    url: str,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int | None = None,
) -> str:
    """Construct CDX API query URL with parameters.

    Parameters
    ----------
    url : str
        The target URL to look up in the Wayback Machine.
    from_date : str | None
        Optional start date filter (YYYYMMDD).
    to_date : str | None
        Optional end date filter (YYYYMMDD).
    limit : int | None
        Optional maximum number of results.

    Returns
    -------
    str
        The fully-constructed CDX API query URL.
    """
    params: dict[str, str] = {
        "url": url,
        "output": "json",
    }
    if from_date is not None:
        params["from"] = from_date
    if to_date is not None:
        params["to"] = to_date
    if limit is not None:
        params["limit"] = str(limit)
    return f"{CDX_API}?{urllib.parse.urlencode(params)}"


def parse_cdx_response(raw: str) -> list[dict]:
    """Parse CDX space-separated response lines into list of snapshot dicts.

    The CDX API (with output=json) returns a JSON array of arrays where the
    first row is the header. Without output=json, it returns space-separated
    lines with fields: urlkey timestamp original mimetype statuscode digest length.

    This function handles both formats:
    - JSON array of arrays (first row = header)
    - Space-separated lines (legacy format)

    Returns
    -------
    list[dict]
        List of dicts with keys: timestamp, original, mimetype, status_code,
        digest, length.
    """
    raw = raw.strip()
    if not raw:
        return []

    # Try JSON format first (output=json)
    if raw.startswith("["):
        try:
            rows = json.loads(raw)
            if not rows:
                return []
            # First row is the header
            header = rows[0]
            results = []
            for row in rows[1:]:
                record = {}
                for i, field in enumerate(header):
                    if i < len(row):
                        # Normalize field names
                        key = field.lower()
                        if key == "statuscode":
                            key = "status_code"
                        record[key] = row[i]
                results.append(record)
            return results
        except (json.JSONDecodeError, IndexError, TypeError):
            pass

    # Fallback: space-separated lines
    fields = ["urlkey", "timestamp", "original", "mimetype", "status_code", "digest", "length"]
    results = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 7:
            continue
        record = {}
        for i, field in enumerate(fields):
            if i < len(parts):
                record[field] = parts[i]
        results.append(record)
    return results


def _make_request(url: str) -> bytes:
    """Make an HTTP GET request with a polite User-Agent header.

    When D_RESEARCH_HTTP_CACHE_PATH is set, a successful response is cached
    keyed on the final URL plus the User-Agent. Cache failures are non-fatal.

    Raises
    ------
    SystemExit
        On network errors, prints an error message and exits with code 1.
    """
    request_headers = {"User-Agent": USER_AGENT}

    # Cache lookup (opt-in)
    if _http_cache is not None:
        try:
            cached = _http_cache.get("GET", url, request_headers=request_headers)
            if cached:
                return cached["body"]
        except Exception:  # noqa: BLE001 - cache failures are non-fatal
            pass

    req = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            response_headers = dict(resp.headers.items()) if resp.headers else {}
            status = resp.status
    except urllib.error.HTTPError as e:
        print(f"error: request failed for {url}: HTTP {e.code}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"error: request failed for {url}: {e.reason}", file=sys.stderr)
        sys.exit(1)

    # Cache write (opt-in, non-fatal on failure)
    if _http_cache is not None and 200 <= status < 300:
        try:
            _http_cache.put(
                "GET", url, status, response_headers, body,
                request_headers=request_headers,
            )
        except Exception:  # noqa: BLE001
            pass
    return body


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_lookup(args: argparse.Namespace) -> int:
    """List snapshots from CDX API.

    Queries the CDX API for archived snapshots of the given URL and prints
    a formatted table of results.
    """
    query_url = build_cdx_url(
        args.url,
        from_date=args.from_date,
        to_date=args.to,
        limit=args.limit,
    )

    raw = _make_request(query_url)
    text = raw.decode("utf-8", errors="replace")
    records = parse_cdx_response(text)

    if not records:
        print(f"No snapshots found for {args.url}")
        return 0

    # Print table header
    print(f"{'Timestamp':<16} {'Status':<6} {'MIME Type':<20} {'Original URL'}")
    print("-" * 80)
    for rec in records:
        ts = rec.get("timestamp", "")
        status = rec.get("status_code", rec.get("statuscode", ""))
        mime = rec.get("mimetype", "")
        original = rec.get("original", "")
        print(f"{ts:<16} {status:<6} {mime:<20} {original}")

    print(f"\n{len(records)} snapshot(s) found.")
    return 0


def cmd_nearest(args: argparse.Namespace) -> int:
    """Find closest snapshot via Availability API.

    Queries the Availability API for the nearest snapshot to the given
    timestamp and prints the snapshot URL and timestamp.
    """
    params = urllib.parse.urlencode({
        "url": args.url,
        "timestamp": args.timestamp,
    })
    query_url = f"{AVAILABILITY_API}?{params}"

    raw = _make_request(query_url)
    text = raw.decode("utf-8", errors="replace")

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        print("error: invalid JSON response from Availability API", file=sys.stderr)
        return 1

    snapshots = data.get("archived_snapshots", {})
    closest = snapshots.get("closest")

    if not closest or not closest.get("available", False):
        print(f"No snapshot found for {args.url} near {args.timestamp}")
        return 0

    snapshot_url = closest.get("url", "")
    snapshot_ts = closest.get("timestamp", "")

    print(f"Snapshot URL: {snapshot_url}")
    print(f"Timestamp:    {snapshot_ts}")
    return 0


def fetch_with_backoff(url: str, method: str = "GET", max_retries: int = MAX_RETRIES) -> bytes:
    """HTTP request with exponential backoff on 429.

    Makes an HTTP request with the specified method and User-Agent header.
    On HTTP 429 (rate limited), waits 2^attempt seconds and retries up to
    max_retries times. On success, returns the response body bytes.
    On final failure, prints an error and exits with code 1.

    Parameters
    ----------
    url : str
        The URL to request.
    method : str
        HTTP method (GET or POST).
    max_retries : int
        Maximum number of retry attempts on 429.

    Returns
    -------
    bytes
        The response body on success.

    Raises
    ------
    SystemExit
        On network errors or exhausted retries.
    """
    request_headers = {"User-Agent": USER_AGENT}

    # Cache lookup for GET requests (opt-in)
    if method.upper() == "GET" and _http_cache is not None:
        try:
            cached = _http_cache.get("GET", url, request_headers=request_headers)
            if cached:
                return cached["body"]
        except Exception:  # noqa: BLE001
            pass

    for attempt in range(max_retries + 1):
        req = urllib.request.Request(url, method=method, headers=request_headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                resp_headers = dict(resp.headers.items()) if resp.headers else {}
                status = resp.status
            if method.upper() == "GET" and _http_cache is not None and 200 <= status < 300:
                try:
                    _http_cache.put(
                        "GET", url, status, resp_headers, body,
                        request_headers=request_headers,
                    )
                except Exception:  # noqa: BLE001
                    pass
            return body
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries:
                delay = 2 ** (attempt + 1)
                time.sleep(delay)
                continue
            if e.code == 429:
                print(
                    f"error: rate limited after {max_retries} retries for {url}",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(f"error: request failed for {url}: HTTP {e.code}", file=sys.stderr)
            sys.exit(1)
        except urllib.error.URLError as e:
            print(f"error: request failed for {url}: {e.reason}", file=sys.stderr)
            sys.exit(1)

    # Should not reach here, but guard against logic errors
    print(f"error: unexpected failure for {url}", file=sys.stderr)
    sys.exit(1)


def cmd_save(args: argparse.Namespace) -> int:
    """Submit URL to Save Page Now with rate limiting and retry.

    POSTs to the Save Page Now endpoint with exponential backoff on 429.
    On success, prints the resulting archive URL.
    """
    save_url = f"{SAVE_URL_PREFIX}{args.url}"
    raw = fetch_with_backoff(save_url, method="POST")
    # The Save Page Now endpoint returns the archive URL in the response
    # or redirects to it. Print the constructed archive URL on success.
    text = raw.decode("utf-8", errors="replace").strip()

    # If the response contains a URL, use it; otherwise construct one
    if text and text.startswith("http"):
        print(f"Saved: {text}")
    else:
        print(f"Saved: {save_url}")
    return 0


def hash_content(text: str) -> str:
    """SHA256 hex digest of text content.

    Parameters
    ----------
    text : str
        The text to hash.

    Returns
    -------
    str
        The SHA256 hex digest string.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_diff_summary(
    text_t1: str, text_t2: str, hash_t1: str, hash_t2: str, top_n: int = 5
) -> dict:
    """Build a structured diff summary between two text snapshots.

    Uses stdlib difflib.unified_diff to compute line-level differences,
    then extracts the top-N largest hunks by total changed lines.

    Parameters
    ----------
    text_t1 : str
        Content of the first snapshot.
    text_t2 : str
        Content of the second snapshot.
    hash_t1 : str
        SHA256 hash of text_t1.
    hash_t2 : str
        SHA256 hash of text_t2.
    top_n : int
        Maximum number of hunks to include in the summary.

    Returns
    -------
    dict
        Structured diff summary with hash_t1, hash_t2, identical flag,
        and diff_summary containing added_lines, removed_lines, and top_hunks.
    """
    identical = hash_t1 == hash_t2
    if identical:
        return {
            "hash_t1": hash_t1,
            "hash_t2": hash_t2,
            "identical": True,
            "diff_summary": {
                "added_lines": 0,
                "removed_lines": 0,
                "top_hunks": [],
            },
        }

    lines_t1 = text_t1.splitlines(keepends=True)
    lines_t2 = text_t2.splitlines(keepends=True)

    diff_lines = list(difflib.unified_diff(lines_t1, lines_t2, lineterm=""))

    added_lines = 0
    removed_lines = 0
    hunks: list[dict] = []
    current_hunk_context = ""
    current_added: list[str] = []
    current_removed: list[str] = []

    for line in diff_lines:
        if line.startswith("@@"):
            # Save previous hunk if any
            if current_added or current_removed:
                hunks.append({
                    "context": current_hunk_context.strip(),
                    "added": "\n".join(current_added),
                    "removed": "\n".join(current_removed),
                })
            current_hunk_context = line
            current_added = []
            current_removed = []
        elif line.startswith("+++") or line.startswith("---"):
            continue
        elif line.startswith("+"):
            added_lines += 1
            current_added.append(line[1:].rstrip())
        elif line.startswith("-"):
            removed_lines += 1
            current_removed.append(line[1:].rstrip())

    # Save last hunk
    if current_added or current_removed:
        hunks.append({
            "context": current_hunk_context.strip(),
            "added": "\n".join(current_added),
            "removed": "\n".join(current_removed),
        })

    # Sort hunks by total changed lines (largest first) and take top_n
    hunks.sort(key=lambda h: len(h["added"].splitlines()) + len(h["removed"].splitlines()), reverse=True)
    top_hunks = hunks[:top_n]

    return {
        "hash_t1": hash_t1,
        "hash_t2": hash_t2,
        "identical": False,
        "diff_summary": {
            "added_lines": added_lines,
            "removed_lines": removed_lines,
            "top_hunks": top_hunks,
        },
    }


def cmd_diff(args: argparse.Namespace) -> int:
    """Compare content between two timestamps via hash.

    Queries the Availability API for both timestamps to find snapshot URLs,
    fetches both snapshot pages, hashes the visible text content of each,
    and reports whether the content changed. When --summarize is set, also
    produces a unified diff summary with line counts and top hunks.
    """
    # Find snapshot for t1
    params_t1 = urllib.parse.urlencode({"url": args.url, "timestamp": args.t1})
    query_url_t1 = f"{AVAILABILITY_API}?{params_t1}"
    raw_t1 = _make_request(query_url_t1)
    data_t1 = json.loads(raw_t1.decode("utf-8", errors="replace"))

    snapshots_t1 = data_t1.get("archived_snapshots", {})
    closest_t1 = snapshots_t1.get("closest")

    if not closest_t1 or not closest_t1.get("available", False):
        print(f"No snapshot found for {args.url} near {args.t1}")
        return 1

    # Find snapshot for t2
    params_t2 = urllib.parse.urlencode({"url": args.url, "timestamp": args.t2})
    query_url_t2 = f"{AVAILABILITY_API}?{params_t2}"
    raw_t2 = _make_request(query_url_t2)
    data_t2 = json.loads(raw_t2.decode("utf-8", errors="replace"))

    snapshots_t2 = data_t2.get("archived_snapshots", {})
    closest_t2 = snapshots_t2.get("closest")

    if not closest_t2 or not closest_t2.get("available", False):
        print(f"No snapshot found for {args.url} near {args.t2}")
        return 1

    url_t1 = closest_t1["url"]
    url_t2 = closest_t2["url"]

    # Fetch both snapshots
    content_t1 = _make_request(url_t1).decode("utf-8", errors="replace")
    content_t2 = _make_request(url_t2).decode("utf-8", errors="replace")

    # Hash and compare
    hash_t1 = hash_content(content_t1)
    hash_t2 = hash_content(content_t2)

    summarize = getattr(args, "summarize", False)
    top_n = getattr(args, "top_n", 5)

    if summarize:
        result = build_diff_summary(content_t1, content_t2, hash_t1, hash_t2, top_n)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"URL:       {args.url}")
        print(f"Snapshot 1: {url_t1}")
        print(f"  Hash:    {hash_t1}")
        print(f"Snapshot 2: {url_t2}")
        print(f"  Hash:    {hash_t2}")

        if hash_t1 == hash_t2:
            print("\nResult: Content is IDENTICAL between the two snapshots.")
        else:
            print("\nResult: Content CHANGED between the two snapshots.")

    return 0


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


class _MockHandler(http.server.BaseHTTPRequestHandler):
    """Mock HTTP handler for self-test endpoints."""

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Suppress default request logging."""
        pass

    def do_GET(self) -> None:  # noqa: N802
        """Handle GET requests for mock endpoints."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/cdx/search/cdx":
            # Return mock CDX JSON response
            data = json.dumps([
                ["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"],
                ["com,example)/page", "20200101120000", "https://example.com/page", "text/html", "200", "ABC123", "5000"],
                ["com,example)/page", "20210101120000", "https://example.com/page", "text/html", "200", "DEF456", "5200"],
            ])
            self._respond(200, data.encode("utf-8"), "application/json")

        elif path == "/wayback/available":
            # Return mock availability JSON
            url = query.get("url", [""])[0]
            timestamp = query.get("timestamp", ["20200101"])[0]
            data = json.dumps({
                "url": url,
                "archived_snapshots": {
                    "closest": {
                        "status": "200",
                        "available": True,
                        "url": f"http://127.0.0.1:{self.server.server_address[1]}/web/{timestamp}120000/{url}",
                        "timestamp": f"{timestamp}120000",
                    }
                },
            })
            self._respond(200, data.encode("utf-8"), "application/json")

        elif path.startswith("/web/"):
            # Return mock HTML content based on timestamp
            # Extract timestamp from path: /web/TIMESTAMP/URL
            parts = path.split("/", 3)  # ['', 'web', 'TIMESTAMP...', 'URL...']
            if len(parts) >= 3:
                ts_part = parts[2]
                if ts_part.startswith("20200101"):
                    content = "Page content version A"
                elif ts_part.startswith("20210101"):
                    content = "Page content version B"
                else:
                    content = "Page content default"
            else:
                content = "Page content default"
            self._respond(200, content.encode("utf-8"), "text/html")

        else:
            self._respond(404, b"Not Found", "text/plain")

    def _respond(self, code: int, body: bytes, content_type: str) -> None:
        """Send an HTTP response."""
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def cmd_self_test(args: argparse.Namespace) -> int:
    """Offline self-test with local mock HTTP server.

    Starts a local HTTP server on a random port, overrides API constants
    to point to localhost, exercises lookup/nearest/diff subcommands,
    then restores constants and shuts down the server.
    """
    global CDX_API, AVAILABILITY_API  # noqa: PLW0603

    # Save original constants
    orig_cdx_api = CDX_API
    orig_availability_api = AVAILABILITY_API

    # Isolate the HTTP cache so a stale local cache cannot mask mock HTTP.
    cache_env = "D_RESEARCH_HTTP_CACHE_PATH"
    saved_cache = os.environ.pop(cache_env, None)

    # Start mock server on random port
    server = http.server.HTTPServer(("127.0.0.1", 0), _MockHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        # Override API constants to point to local mock
        CDX_API = f"http://127.0.0.1:{port}/cdx/search/cdx"
        AVAILABILITY_API = f"http://127.0.0.1:{port}/wayback/available"

        errors: list[str] = []

        # --- Test lookup ---
        lookup_ns = argparse.Namespace(
            url="https://example.com/page",
            from_date=None,
            to=None,
            limit=None,
        )
        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            rc = cmd_lookup(lookup_ns)
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()

        if rc != 0:
            errors.append(f"lookup returned exit code {rc}")
        elif "20200101120000" not in output or "20210101120000" not in output:
            errors.append("lookup did not display expected timestamps")
        elif "2 snapshot(s) found" not in output:
            errors.append("lookup did not report correct snapshot count")

        # --- Test nearest ---
        nearest_ns = argparse.Namespace(
            url="https://example.com/page",
            timestamp="20200101",
        )
        captured = io.StringIO()
        sys.stdout = captured
        try:
            rc = cmd_nearest(nearest_ns)
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()

        if rc != 0:
            errors.append(f"nearest returned exit code {rc}")
        elif "Snapshot URL:" not in output:
            errors.append("nearest did not display snapshot URL")
        elif f"127.0.0.1:{port}" not in output and f"localhost:{port}" not in output:
            errors.append("nearest did not point to mock server")

        # --- Test diff ---
        diff_ns = argparse.Namespace(
            url="https://example.com/page",
            t1="20200101",
            t2="20210101",
            summarize=False,
            top_n=5,
        )
        captured = io.StringIO()
        sys.stdout = captured
        try:
            rc = cmd_diff(diff_ns)
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()

        if rc != 0:
            errors.append(f"diff returned exit code {rc}")
        elif "CHANGED" not in output:
            errors.append("diff did not detect content change between timestamps")

        # --- Test diff --summarize ---
        diff_sum_ns = argparse.Namespace(
            url="https://example.com/page",
            t1="20200101",
            t2="20210101",
            summarize=True,
            top_n=3,
        )
        captured = io.StringIO()
        sys.stdout = captured
        try:
            rc = cmd_diff(diff_sum_ns)
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()

        if rc != 0:
            errors.append(f"diff --summarize returned exit code {rc}")
        else:
            try:
                summary = json.loads(output)
                if summary.get("identical") is not False:
                    errors.append("diff --summarize did not detect change (identical should be false)")
                ds = summary.get("diff_summary", {})
                if not isinstance(ds.get("added_lines"), int):
                    errors.append("diff --summarize missing added_lines integer")
                if not isinstance(ds.get("removed_lines"), int):
                    errors.append("diff --summarize missing removed_lines integer")
                if not isinstance(ds.get("top_hunks"), list):
                    errors.append("diff --summarize missing top_hunks list")
                if ds.get("added_lines", 0) == 0 and ds.get("removed_lines", 0) == 0:
                    errors.append("diff --summarize reported 0 changes for different content")
            except json.JSONDecodeError:
                errors.append("diff --summarize output is not valid JSON")

        # --- Test diff --summarize with identical content ---
        diff_same_ns = argparse.Namespace(
            url="https://example.com/page",
            t1="20200101",
            t2="20200101",
            summarize=True,
            top_n=5,
        )
        captured = io.StringIO()
        sys.stdout = captured
        try:
            rc = cmd_diff(diff_same_ns)
        finally:
            sys.stdout = old_stdout
        output = captured.getvalue()

        if rc != 0:
            errors.append(f"diff --summarize (identical) returned exit code {rc}")
        else:
            try:
                summary = json.loads(output)
                if summary.get("identical") is not True:
                    errors.append("diff --summarize did not detect identical content")
                ds = summary.get("diff_summary", {})
                if ds.get("added_lines") != 0 or ds.get("removed_lines") != 0:
                    errors.append("diff --summarize reported changes for identical content")
            except json.JSONDecodeError:
                errors.append("diff --summarize (identical) output is not valid JSON")

        # Report results
        if errors:
            print("wayback self-test FAILED:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 1

        print("wayback self-test ok")
        return 0

    finally:
        # Restore original constants
        CDX_API = orig_cdx_api
        AVAILABILITY_API = orig_availability_api
        # Restore cache env if it was set
        if saved_cache is not None:
            os.environ[cache_env] = saved_cache
        # Shut down mock server
        server.shutdown()


# ---------------------------------------------------------------------------
# Main / argparse
# ---------------------------------------------------------------------------


def main() -> int:
    """Argparse setup with subcommands."""
    p = argparse.ArgumentParser(
        prog="wayback.py",
        description="Wayback Machine integration for archival research workflows.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # -- lookup --
    lookup_p = sub.add_parser("lookup", help="List archived snapshots of a URL.")
    lookup_p.add_argument("--url", required=True, help="Target URL to look up.")
    lookup_p.add_argument(
        "--from",
        dest="from_date",
        metavar="YYYYMMDD",
        default=None,
        help="Start date filter (YYYYMMDD).",
    )
    lookup_p.add_argument(
        "--to",
        metavar="YYYYMMDD",
        default=None,
        help="End date filter (YYYYMMDD).",
    )
    lookup_p.add_argument(
        "--limit",
        type=int,
        metavar="N",
        default=None,
        help="Maximum number of results.",
    )

    # -- nearest --
    nearest_p = sub.add_parser(
        "nearest", help="Find the closest snapshot to a given timestamp."
    )
    nearest_p.add_argument("--url", required=True, help="Target URL to look up.")
    nearest_p.add_argument(
        "--timestamp",
        required=True,
        metavar="YYYYMMDD",
        help="Target timestamp (YYYYMMDD).",
    )

    # -- save (placeholder for future implementation) --
    save_p = sub.add_parser("save", help="Submit URL to Save Page Now.")
    save_p.add_argument("--url", required=True, help="URL to archive.")

    # -- diff (placeholder for future implementation) --
    diff_p = sub.add_parser(
        "diff", help="Compare content between two archived timestamps."
    )
    diff_p.add_argument("--url", required=True, help="Target URL.")
    diff_p.add_argument("--t1", required=True, help="First timestamp (YYYYMMDD).")
    diff_p.add_argument("--t2", required=True, help="Second timestamp (YYYYMMDD).")
    diff_p.add_argument(
        "--summarize",
        action="store_true",
        default=False,
        help="Output a structured JSON diff summary instead of plain text.",
    )
    diff_p.add_argument(
        "--top-n",
        dest="top_n",
        type=int,
        default=5,
        help="Number of largest hunks to include in the summary (default: 5).",
    )

    # -- self-test (placeholder for future implementation) --
    sub.add_parser("self-test", help="Run offline self-tests with mock server.")

    args = p.parse_args()

    if args.cmd == "lookup":
        return cmd_lookup(args)
    if args.cmd == "nearest":
        return cmd_nearest(args)
    if args.cmd == "save":
        return cmd_save(args)
    if args.cmd == "diff":
        return cmd_diff(args)
    if args.cmd == "self-test":
        return cmd_self_test(args)

    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
