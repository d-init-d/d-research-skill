#!/usr/bin/env python3
"""Social media archival: snapshot, verify, to-ledger, self-test.

Subcommands
-----------
* ``snapshot <platform>`` - capture a public social post
* ``verify``              - re-fetch and compare content hash
* ``to-ledger``          - convert snapshot JSON to evidence-ledger CSV row
* ``self-test``          - offline validation with mocked HTTP

Privacy boundary
----------------
All requests pass through check_privacy_boundary() BEFORE any HTTP call.
Violations exit with code 2.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_AGENT = "d-research-skill/3.2.0 (https://github.com/d-init-d/d-research-skill)"
SCHEMA_VERSION = "1.1"

VALID_VERIFICATION_STATUS = {
    "intact",
    "edited",
    "deleted",
    "access_denied",
    "rate_limited",
    "unavailable",
    "malformed",
    "unknown",
}

# Platforms and accepted host suffixes for verify policy checks.
PLATFORM_HOST_HINTS = {
    "reddit": ("reddit.com", "redd.it"),
    "hn": ("news.ycombinator.com", "ycombinator.com"),
    "mastodon": (),  # instance-specific
    "bluesky": ("bsky.app", "bsky.social"),
    "lemmy": (),
    "x": ("x.com", "twitter.com"),
    "facebook": ("facebook.com", "fb.com"),
    "instagram": ("instagram.com",),
    "tiktok": ("tiktok.com",),
    "youtube": ("youtube.com", "youtu.be"),
    "threads": ("threads.net",),
    "linkedin": ("linkedin.com",),
}

TIER_A_PLATFORMS = {"reddit", "hn", "mastodon", "bluesky", "lemmy"}
TIER_B_PLATFORMS = {"x", "facebook", "instagram", "tiktok", "youtube", "threads", "linkedin"}

SCRIPTS_DIR = Path(__file__).resolve().parent
WAYBACK_SCRIPT = SCRIPTS_DIR / "wayback.py"
sys.path.insert(0, str(SCRIPTS_DIR))
from resource_limits import (  # type: ignore
    ResourceLimitError,
    add_resource_limit_arguments,
    apply_cli_limit_overrides,
    check_file_size,
    emit_blocker,
    load_limits,
    read_bounded,
)


# ---------------------------------------------------------------------------
# Privacy Boundary
# ---------------------------------------------------------------------------

_NITTER_PATTERNS = ["nitter.", "nitter-"]
_MINOR_KEYWORDS = ["/minor", "teen", "child", "underage", "kid"]
_HARASSMENT_KEYWORDS = ["stalk", "doxx", "harass", "bully", "revenge"]

# In-process refusal locale, set by main(); defaults to English.
_REFUSAL_LOCALE = "en"

# Fallback English templates if the JSON file is missing.
_REFUSAL_FALLBACK = {
    "minor": "refused: account appears to belong to a minor",
    "third_party_mirror": "refused: third-party mirror URLs are not allowed",
    "harassment_or_doxxing": "refused: request framing violates privacy boundary",
}


def _load_refusal_templates(locale: str) -> dict[str, str]:
    """Load refusal templates from references/i18n/refusal.<locale>.json.

    Returns the fallback English dict if the file is missing or malformed.
    """
    repo_root = SCRIPTS_DIR.parent
    candidate = repo_root / "references" / "i18n" / f"refusal.{locale}.json"
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return dict(_REFUSAL_FALLBACK)
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, str)}


def _refusal(key: str) -> str:
    """Look up a refusal message by key in the active locale."""
    templates = _load_refusal_templates(_REFUSAL_LOCALE)
    if key in templates:
        return templates[key]
    return _REFUSAL_FALLBACK.get(key, f"refused: {key}")


def check_privacy_boundary(url: str, platform: str) -> None:
    """Refuse requests that violate privacy rules.

    Checks BEFORE any HTTP call. Raises SystemExit(2) on violation.
    """
    url_lower = url.lower()

    # Refuse Nitter-style mirrors
    for pat in _NITTER_PATTERNS:
        if pat in url_lower:
            print(_refusal("third_party_mirror"), file=sys.stderr)
            sys.exit(2)

    # Refuse minor account indicators
    for kw in _MINOR_KEYWORDS:
        if kw in url_lower:
            print(_refusal("minor"), file=sys.stderr)
            sys.exit(2)

    # Refuse harassment framing
    for kw in _HARASSMENT_KEYWORDS:
        if kw in url_lower:
            print(_refusal("harassment_or_doxxing"), file=sys.stderr)
            sys.exit(2)


# ---------------------------------------------------------------------------
# Content Hash Module
# ---------------------------------------------------------------------------


def canonicalize_text(text: str | None) -> str:
    """Normalize text for hashing: strip, NFC normalize, Unix line endings."""
    if text is None:
        return ""
    text = text.strip()
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def compute_content_hash(text: str | None) -> str:
    """SHA-256 hex digest of canonicalized text. Returns empty string if text is None."""
    if text is None:
        return ""
    canonical = canonicalize_text(text)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# HTTP Helper
# ---------------------------------------------------------------------------


class FetchError(Exception):
    """Structured network/fetch failure for status mapping."""

    def __init__(self, status: str, message: str, http_code: int | None = None):
        super().__init__(message)
        self.status = status  # maps to verification status
        self.http_code = http_code
        self.message = message


def _assert_safe_url(url: str) -> str:
    """SSRF guard before any network call (public HTTPS only)."""
    try:
        # Prefer same-directory import; fall back to path load.
        from _ssrf_helpers import assert_public_http_url  # type: ignore
    except ImportError:
        import importlib.util

        helper = Path(__file__).resolve().parent / "_ssrf_helpers.py"
        spec = importlib.util.spec_from_file_location("ssrf_helpers", helper)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        assert_public_http_url = mod.assert_public_http_url
    try:
        return assert_public_http_url(url, allow_http=False)
    except ValueError as e:
        raise FetchError("malformed", f"SSRF guard rejected URL: {e}") from e


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise FetchError(
            "unavailable",
            f"HTTP redirect blocked (manual revalidation required): {code}",
            code,
        )


def _public_urlopen(req: urllib.request.Request, timeout: float | None = None):
    """SSRF-validated open with DNS pin (via _ssrf_helpers.public_urlopen)."""
    try:
        from _ssrf_helpers import public_urlopen as _ssrf_open  # type: ignore
    except ImportError:
        import importlib.util

        helper = Path(__file__).resolve().parent / "_ssrf_helpers.py"
        spec = importlib.util.spec_from_file_location("ssrf_helpers", helper)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        _ssrf_open = mod.public_urlopen
    return _ssrf_open(req, timeout=timeout)


def _fetch_json(url: str) -> dict:
    """Fetch URL and parse JSON response. Raises FetchError on failure."""
    url = _assert_safe_url(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    # Redirects are refused: pinned open does not follow them, and legacy
    # urlopen mocks used in self-test never issue redirects.
    try:
        urllib.request.install_opener(urllib.request.build_opener(_NoRedirect()))
    except Exception:
        pass
    try:
        limits = load_limits()
        with _public_urlopen(req, timeout=limits.http_timeout_sec) as resp:
            response_headers = getattr(resp, "headers", None)
            raw_length = response_headers.get("Content-Length") if response_headers else None
            if raw_length:
                try:
                    content_length = int(raw_length)
                except (TypeError, ValueError):
                    content_length = None
                if content_length is not None and content_length > limits.social_max_bytes:
                    raise ResourceLimitError(
                        "social_max_bytes",
                        "social Content-Length exceeds response limit",
                        limit=limits.social_max_bytes,
                        observed=content_length,
                    )
            data = read_bounded(
                resp,
                limits.social_max_bytes,
                code="social_max_bytes",
            )
            return json.loads(data.decode("utf-8", errors="replace"))
    except FetchError:
        raise
    except urllib.error.HTTPError as e:
        try:
            if e.code in (404, 410):
                raise FetchError("deleted", f"post not found at {url}", e.code) from e
            if e.code == 403:
                raise FetchError("access_denied", f"access denied for {url}", e.code) from e
            if e.code == 429:
                raise FetchError("rate_limited", f"rate limited for {url}", e.code) from e
            raise FetchError("unavailable", f"HTTP {e.code} for {url}", e.code) from e
        finally:
            # Close pinned streaming error body without draining it unbounded.
            try:
                e.close()
            except Exception:
                pass
    except urllib.error.URLError as e:
        raise FetchError("unavailable", f"could not resolve or connect to {url}: {e.reason}") from e
    except TimeoutError as e:
        raise FetchError("unavailable", f"timeout fetching {url}") from e
    except json.JSONDecodeError as e:
        raise FetchError("malformed", f"invalid JSON from {url}") from e


def _fetch_json_or_exit(url: str) -> dict:
    """Fetch helper for snapshot capture path (exits with mapped codes)."""
    try:
        return _fetch_json(url)
    except FetchError as e:
        print(f"error: {e.message}", file=sys.stderr)
        # deleted/not found still exit 1 for capture; verify maps status separately
        sys.exit(1)


def _read_snapshot_json(file: Path) -> dict:
    limits = load_limits()
    check_file_size(file, limits.download_max_bytes, code="download_file_bytes")
    with file.open("rb") as stream:
        raw = read_bounded(
            stream,
            limits.download_max_bytes,
            code="download_file_bytes",
        )
    return json.loads(raw.decode("utf-8", errors="strict"))


# ---------------------------------------------------------------------------
# Snapshot JSON Builder
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_rfc3339(value: object) -> bool:
    """Return whether *value* is a timezone-aware RFC 3339 timestamp."""
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _mark_snapshot_malformed(file: Path, snap: dict, message: str) -> int:
    """Persist a deterministic malformed result without making a network call."""
    print(f"error: {message}", file=sys.stderr)
    verification = snap.get("verification")
    if not isinstance(verification, dict):
        verification = {}
        snap["verification"] = verification
    verification["status"] = "malformed"
    verification["last_verified_at"] = _now_iso()
    file.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    return 1


def _build_snapshot(
    platform: str,
    tier: str,
    verifiability: str,
    verifiability_note: str,
    url_original: str,
    url_canonical: str,
    url_archive: str | None,
    post: dict,
    content_hash: str,
    limitations: list[str],
    archive_submission: dict | None = None,
) -> dict:
    """Build a schema v1.1 Snapshot JSON dict."""
    now = _now_iso()
    return {
        "schema_version": SCHEMA_VERSION,
        "platform": platform,
        "tier": tier,
        "verifiability": verifiability,
        "verifiability_note": verifiability_note,
        "url_original": url_original,
        "url_canonical": url_canonical,
        "url_archive": url_archive,
        "captured_at": now,
        "post": post,
        "content_hash_sha256": content_hash,
        "verification": {
            "first_capture_at": now,
            "last_verified_at": None,
            "status": "intact" if tier == "A" else "unknown",
        },
        "archive_submission": archive_submission
        or {
            "requested": False,
            "status": "not_requested",
            "timestamp": None,
            "archive_url": url_archive,
        },
        "limitations": limitations,
    }


def _default_post() -> dict:
    """Return a post object with all required fields set to defaults."""
    return {
        "id": None,
        "author_handle": None,
        "author_display_name": None,
        "posted_at": None,
        "text": None,
        "lang": None,
        "engagement_at_capture": {"score": 0, "reposts": 0, "comments": 0, "reactions": {}},
        "media": [],
        "thread_context": {"parent_id": None, "channel": None, "permalink": None},
    }


# ---------------------------------------------------------------------------
# Tier A Handlers
# ---------------------------------------------------------------------------


def snapshot_reddit(url: str, out: Path) -> int:
    """Fetch Reddit post via JSON API."""
    # Normalize URL to get permalink .json
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.rstrip("/")
    if not path.endswith(".json"):
        path += ".json"
    api_url = f"https://www.reddit.com{path}"

    data = _fetch_json_or_exit(api_url)
    # Reddit returns a list of listings; first listing has the post
    if isinstance(data, list) and len(data) > 0:
        post_data = data[0].get("data", {}).get("children", [{}])[0].get("data", {})
    else:
        post_data = {}

    text = post_data.get("selftext") or post_data.get("title") or ""
    content_hash = compute_content_hash(text)

    post = _default_post()
    post["id"] = post_data.get("id", "")
    post["author_handle"] = post_data.get("author")
    post["author_display_name"] = post_data.get("author")
    post["posted_at"] = None
    post["text"] = text if text else None
    post["lang"] = None
    post["engagement_at_capture"] = {
        "score": post_data.get("score", 0),
        "reposts": 0,
        "comments": post_data.get("num_comments", 0),
        "reactions": {},
    }
    post["thread_context"]["permalink"] = post_data.get("permalink")
    post["thread_context"]["channel"] = post_data.get("subreddit")

    snap = _build_snapshot(
        platform="reddit",
        tier="A",
        verifiability="direct_api",
        verifiability_note="Content fetched directly from Reddit JSON API; hash verifiable.",
        url_original=url,
        url_canonical=f"https://www.reddit.com{post_data.get('permalink', '')}",
        url_archive=None,
        post=post,
        content_hash=content_hash,
        limitations=[],
    )
    out.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


def snapshot_hn(item_id: str, out: Path) -> int:
    """Fetch Hacker News item via Algolia API."""
    api_url = f"https://hn.algolia.com/api/v1/items/{item_id}"
    data = _fetch_json_or_exit(api_url)

    text = data.get("text") or data.get("title") or ""
    content_hash = compute_content_hash(text)

    post = _default_post()
    post["id"] = str(data.get("id", item_id))
    post["author_handle"] = data.get("author")
    post["author_display_name"] = data.get("author")
    post["posted_at"] = data.get("created_at")
    post["text"] = text if text else None
    post["lang"] = "en"
    post["engagement_at_capture"] = {
        "score": data.get("points", 0) or 0,
        "reposts": 0,
        "comments": len(data.get("children", [])),
        "reactions": {},
    }

    snap = _build_snapshot(
        platform="hn",
        tier="A",
        verifiability="direct_api",
        verifiability_note="Content fetched directly from Hacker News Algolia API; hash verifiable.",
        url_original=f"https://news.ycombinator.com/item?id={item_id}",
        url_canonical=f"https://news.ycombinator.com/item?id={item_id}",
        url_archive=None,
        post=post,
        content_hash=content_hash,
        limitations=[],
    )
    out.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


def snapshot_mastodon(url: str, out: Path) -> int:
    """Fetch Mastodon status via instance API."""
    parsed = urllib.parse.urlparse(url)
    instance = parsed.hostname
    # Extract status ID from path like /@user/123456 or /users/user/statuses/123456
    match = re.search(r"/(\d+)$", parsed.path)
    if not match:
        print(f"error: cannot extract status ID from {url}", file=sys.stderr)
        sys.exit(1)
    status_id = match.group(1)

    api_url = f"https://{instance}/api/v1/statuses/{status_id}"
    data = _fetch_json_or_exit(api_url)

    # Mastodon returns HTML content; strip tags for plain text
    html_content = data.get("content", "")
    text = re.sub(r"<[^>]+>", "", html_content).strip() if html_content else ""
    content_hash = compute_content_hash(text if text else None)

    account = data.get("account", {})
    post = _default_post()
    post["id"] = str(data.get("id", status_id))
    post["author_handle"] = f"@{account.get('acct', '')}"
    post["author_display_name"] = account.get("display_name")
    post["posted_at"] = data.get("created_at")
    post["text"] = text if text else None
    post["lang"] = data.get("language")
    post["engagement_at_capture"] = {
        "score": data.get("favourites_count", 0),
        "reposts": data.get("reblogs_count", 0),
        "comments": data.get("replies_count", 0),
        "reactions": {},
    }

    snap = _build_snapshot(
        platform="mastodon",
        tier="A",
        verifiability="direct_api",
        verifiability_note="Content fetched directly from Mastodon instance API; hash verifiable.",
        url_original=url,
        url_canonical=data.get("url", url),
        url_archive=None,
        post=post,
        content_hash=content_hash,
        limitations=[],
    )
    out.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


def snapshot_bluesky(url: str, out: Path) -> int:
    """Fetch Bluesky post via AT Protocol public API."""
    # URL format: https://bsky.app/profile/<handle>/post/<rkey>
    parsed = urllib.parse.urlparse(url)
    match = re.match(r"/profile/([^/]+)/post/([^/]+)", parsed.path)
    if not match:
        print(f"error: cannot parse Bluesky URL: {url}", file=sys.stderr)
        sys.exit(1)
    handle = match.group(1)
    rkey = match.group(2)

    # Construct AT URI
    at_uri = f"at://{handle}/app.bsky.feed.post/{rkey}"
    params = urllib.parse.urlencode({"uri": at_uri, "depth": "0"})
    api_url = f"https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?{params}"
    data = _fetch_json_or_exit(api_url)

    thread = data.get("thread", {})
    post_record = thread.get("post", {}).get("record", {})
    post_meta = thread.get("post", {})
    author = post_meta.get("author", {})

    text = post_record.get("text", "")
    content_hash = compute_content_hash(text if text else None)

    post = _default_post()
    post["id"] = rkey
    post["author_handle"] = f"@{author.get('handle', handle)}"
    post["author_display_name"] = author.get("displayName")
    post["posted_at"] = post_record.get("createdAt")
    post["text"] = text if text else None
    post["lang"] = None
    if post_record.get("langs"):
        post["lang"] = post_record["langs"][0] if post_record["langs"] else None
    post["engagement_at_capture"] = {
        "score": post_meta.get("likeCount", 0),
        "reposts": post_meta.get("repostCount", 0),
        "comments": post_meta.get("replyCount", 0),
        "reactions": {},
    }

    snap = _build_snapshot(
        platform="bluesky",
        tier="A",
        verifiability="direct_api",
        verifiability_note="Content fetched directly from Bluesky AT Protocol public API; hash verifiable.",
        url_original=url,
        url_canonical=f"https://bsky.app/profile/{handle}/post/{rkey}",
        url_archive=None,
        post=post,
        content_hash=content_hash,
        limitations=[],
    )
    out.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


def snapshot_lemmy(url: str, out: Path) -> int:
    """Fetch Lemmy post via instance API."""
    parsed = urllib.parse.urlparse(url)
    instance = parsed.hostname
    # Extract post ID from path like /post/12345
    match = re.search(r"/post/(\d+)", parsed.path)
    if not match:
        print(f"error: cannot extract post ID from {url}", file=sys.stderr)
        sys.exit(1)
    post_id = match.group(1)

    api_url = f"https://{instance}/api/v3/post?id={post_id}"
    data = _fetch_json_or_exit(api_url)

    post_view = data.get("post_view", {})
    post_data = post_view.get("post", {})
    creator = post_view.get("creator", {})
    counts = post_view.get("counts", {})

    text = post_data.get("body") or post_data.get("name") or ""
    content_hash = compute_content_hash(text if text else None)

    post = _default_post()
    post["id"] = str(post_data.get("id", post_id))
    post["author_handle"] = f"@{creator.get('name', '')}"
    post["author_display_name"] = creator.get("display_name")
    post["posted_at"] = post_data.get("published")
    post["text"] = text if text else None
    post["lang"] = None
    post["engagement_at_capture"] = {
        "score": counts.get("score", 0),
        "reposts": 0,
        "comments": counts.get("comments", 0),
        "reactions": {},
    }
    post["thread_context"]["channel"] = post_view.get("community", {}).get("name")

    snap = _build_snapshot(
        platform="lemmy",
        tier="A",
        verifiability="direct_api",
        verifiability_note="Content fetched directly from Lemmy instance API; hash verifiable.",
        url_original=url,
        url_canonical=post_data.get("ap_id", url),
        url_archive=None,
        post=post,
        content_hash=content_hash,
        limitations=[],
    )
    out.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


# ---------------------------------------------------------------------------
# Tier B Handler (archive-only via wayback.py subprocess)
# ---------------------------------------------------------------------------

_TIER_B_LIMITATIONS = {
    "x": [
        "No direct API access; content from Wayback archive only",
        "Text may be incomplete or missing",
    ],
    "facebook": [
        "No direct API access; content from Wayback archive only",
        "Login-walled content not captured",
    ],
    "instagram": ["No direct API access; content from Wayback archive only", "Media not captured"],
    "tiktok": [
        "No direct API access; content from Wayback archive only",
        "Video content not captured",
    ],
    "youtube": [
        "No direct API access; content from Wayback archive only",
        "Video content not captured",
        "Comments not captured",
    ],
    "threads": [
        "No direct API access; content from Wayback archive only",
        "Text may be incomplete",
    ],
    "linkedin": [
        "No direct API access; content from Wayback archive only",
        "Login-walled content not captured",
    ],
}

_TIER_B_NOTES = {
    "x": "Archived via Wayback Machine; original post may differ from archive snapshot.",
    "facebook": "Archived via Wayback Machine; login-walled content cannot be captured.",
    "instagram": "Archived via Wayback Machine; media and stories not captured.",
    "tiktok": "Archived via Wayback Machine; video content not captured.",
    "youtube": "Archived via Wayback Machine; video content not captured.",
    "threads": "Archived via Wayback Machine; content may be incomplete.",
    "linkedin": "Archived via Wayback Machine; login-walled content cannot be captured.",
}


def snapshot_tier_b(platform: str, url: str, out: Path, submit_archive: bool = False) -> int:
    """Archive-only path via wayback.py.

    Default: lookup existing Wayback snapshot only (no POST/Save Page Now).
    Opt-in mutation: pass submit_archive=True / --submit-archive.
    """
    python_cmd = sys.executable or "python3"
    limits = load_limits()
    archive_url = None
    submission = {
        "requested": bool(submit_archive),
        "status": "not_requested",
        "timestamp": None,
        "archive_url": None,
    }

    # Step 1 (default): lookup nearest existing snapshot — no mutation.
    today = datetime.date.today().strftime("%Y%m%d")
    nearest_result = subprocess.run(
        [python_cmd, str(WAYBACK_SCRIPT), "nearest", "--url", url, "--timestamp", today],
        capture_output=True,
        text=True,
        timeout=limits.subprocess_timeout_sec,
    )
    if nearest_result.returncode != 0 and not submit_archive:
        submission["status"] = "lookup_failed"
        submission["timestamp"] = _now_iso()
        limitations = list(
            _TIER_B_LIMITATIONS.get(
                platform, ["No direct API access; content from Wayback archive only"]
            )
        ) + [f"wayback nearest failed: {(nearest_result.stderr or '').strip()[:200]}"]
        note = _TIER_B_NOTES.get(platform, "Archived via Wayback Machine; verifiability limited.")
        post = _default_post()
        snap = _build_snapshot(
            platform=platform,
            tier="B",
            verifiability="archive_snapshot",
            verifiability_note=note,
            url_original=url,
            url_canonical=url,
            url_archive=None,
            post=post,
            content_hash="",
            limitations=limitations,
            archive_submission=submission,
        )
        out.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            f"error: wayback nearest lookup failed for {url}: "
            f"{(nearest_result.stderr or nearest_result.stdout or '').strip()}",
            file=sys.stderr,
        )
        return 1
    for line in nearest_result.stdout.splitlines():
        if line.startswith("Snapshot URL:"):
            archive_url = line.split(":", 1)[1].strip()
            break

    # Step 2 (opt-in only): Save Page Now
    if submit_archive:
        submission["timestamp"] = _now_iso()
        save_result = subprocess.run(
            [python_cmd, str(WAYBACK_SCRIPT), "save", "--url", url],
            capture_output=True,
            text=True,
            timeout=limits.subprocess_timeout_sec,
        )
        if save_result.returncode != 0:
            submission["status"] = "failed"
            print(
                f"error: wayback.py save failed: {save_result.stderr.strip()}",
                file=sys.stderr,
            )
            # Still write snapshot with failure metadata; exit non-zero.
            limitations = _TIER_B_LIMITATIONS.get(
                platform, ["No direct API access; content from Wayback archive only"]
            )
            note = _TIER_B_NOTES.get(
                platform, "Archived via Wayback Machine; verifiability limited."
            )
            post = _default_post()
            snap = _build_snapshot(
                platform=platform,
                tier="B",
                verifiability="archive_snapshot",
                verifiability_note=note,
                url_original=url,
                url_canonical=url,
                url_archive=archive_url,
                post=post,
                content_hash="",
                limitations=limitations + ["archive_submission_failed"],
                archive_submission=submission,
            )
            out.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
            sys.exit(1)
        submission["status"] = "submitted"
        # Re-lookup after save
        nearest_result = subprocess.run(
            [
                python_cmd,
                str(WAYBACK_SCRIPT),
                "nearest",
                "--url",
                url,
                "--timestamp",
                today,
            ],
            capture_output=True,
            text=True,
            timeout=limits.subprocess_timeout_sec,
        )
        for line in nearest_result.stdout.splitlines():
            if line.startswith("Snapshot URL:"):
                archive_url = line.split(":", 1)[1].strip()
                break
        submission["archive_url"] = archive_url
    else:
        submission["status"] = "lookup_only"
        submission["archive_url"] = archive_url

    limitations = _TIER_B_LIMITATIONS.get(
        platform, ["No direct API access; content from Wayback archive only"]
    )
    if not submit_archive:
        limitations = list(limitations) + [
            "Wayback Save Page Now not requested; lookup-only (use --submit-archive to opt in)"
        ]
    note = _TIER_B_NOTES.get(platform, "Archived via Wayback Machine; verifiability limited.")

    post = _default_post()
    post["text"] = None  # Cannot extract text from archive HTML

    snap = _build_snapshot(
        platform=platform,
        tier="B",
        verifiability="archive_snapshot",
        verifiability_note=note,
        url_original=url,
        url_canonical=url,
        url_archive=archive_url,
        post=post,
        content_hash="",
        limitations=limitations,
        archive_submission=submission,
    )
    out.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


# ---------------------------------------------------------------------------
# Generic Handler
# ---------------------------------------------------------------------------


def snapshot_generic(url: str, out: Path, submit_archive: bool = False) -> int:
    """Generic fallback: Wayback lookup-only unless --submit-archive."""
    return snapshot_tier_b("generic", url, out, submit_archive=submit_archive)


# ---------------------------------------------------------------------------
# Platform Router
# ---------------------------------------------------------------------------


def route_platform(
    platform: str,
    url: str,
    item_id: str | None,
    out: Path,
    submit_archive: bool = False,
) -> int:
    """Dispatch to the correct handler based on platform tier."""
    if platform in TIER_A_PLATFORMS:
        if platform == "reddit":
            return snapshot_reddit(url, out)
        elif platform == "hn":
            if not item_id:
                print("error: --id is required for hn platform", file=sys.stderr)
                sys.exit(1)
            return snapshot_hn(item_id, out)
        elif platform == "mastodon":
            return snapshot_mastodon(url, out)
        elif platform == "bluesky":
            return snapshot_bluesky(url, out)
        elif platform == "lemmy":
            return snapshot_lemmy(url, out)
    elif platform in TIER_B_PLATFORMS:
        return snapshot_tier_b(platform, url, out, submit_archive=submit_archive)
    elif platform == "generic":
        return snapshot_generic(url, out, submit_archive=submit_archive)
    else:
        print(f"error: unknown platform '{platform}'", file=sys.stderr)
        sys.exit(1)
    return 0


# ---------------------------------------------------------------------------
# Verification Module
# ---------------------------------------------------------------------------


def _platform_host_ok(platform: str, url: str) -> bool:
    hints = PLATFORM_HOST_HINTS.get(platform)
    if hints is None:
        return False
    if not hints:
        return True  # instance-specific (mastodon/lemmy)
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return False
    host = host.lower()
    return any(host == h or host.endswith("." + h) for h in hints)


def verify_snapshot(file: Path) -> int:
    """Re-fetch and compare hash for verification."""
    try:
        snap = _read_snapshot_json(file)
    except (json.JSONDecodeError, OSError, UnicodeError) as e:
        print(f"error: invalid snapshot file: {e}", file=sys.stderr)
        sys.exit(1)

    if snap.get("schema_version") not in {SCHEMA_VERSION, "1.0"}:
        print(
            f"error: unsupported snapshot schema_version {snap.get('schema_version')!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    platform = snap.get("platform", "")
    tier = snap.get("tier", "")
    now = _now_iso()
    url_original = snap.get("url_original", "")

    # Validate schema and tier policy before any network call.
    if platform not in TIER_A_PLATFORMS | TIER_B_PLATFORMS | {"generic"}:
        print(f"error: unknown platform in snapshot: {platform!r}", file=sys.stderr)
        sys.exit(1)
    expected_tier = "A" if platform in TIER_A_PLATFORMS else "B"
    if tier != expected_tier:
        return _mark_snapshot_malformed(
            file,
            snap,
            f"tier {tier!r} conflicts with platform {platform!r}; expected {expected_tier}",
        )
    verification = snap.get("verification")
    if not isinstance(verification, dict):
        return _mark_snapshot_malformed(file, snap, "verification must be an object")
    for label, value in (
        ("captured_at", snap.get("captured_at")),
        ("verification.first_capture_at", verification.get("first_capture_at")),
    ):
        if not _is_rfc3339(value):
            return _mark_snapshot_malformed(file, snap, f"{label} must be RFC3339")
    last_verified_at = verification.get("last_verified_at")
    if last_verified_at is not None and not _is_rfc3339(last_verified_at):
        return _mark_snapshot_malformed(
            file, snap, "verification.last_verified_at must be null or RFC3339"
        )

    if snap.get("schema_version") == SCHEMA_VERSION:
        submission = snap.get("archive_submission")
        if not isinstance(submission, dict):
            return _mark_snapshot_malformed(file, snap, "archive_submission must be an object")
        requested = submission.get("requested")
        status = submission.get("status")
        submitted_at = submission.get("timestamp")
        archive_submission_url = submission.get("archive_url")
        if not isinstance(requested, bool):
            return _mark_snapshot_malformed(
                file, snap, "archive_submission.requested must be boolean"
            )
        allowed_statuses = (
            {"submitted", "failed"}
            if requested
            else ({"not_requested"} if tier == "A" else {"lookup_only", "lookup_failed"})
        )
        if status not in allowed_statuses:
            return _mark_snapshot_malformed(
                file,
                snap,
                f"archive_submission.status {status!r} conflicts with tier/request policy",
            )
        timestamp_required = status in {"submitted", "failed", "lookup_failed"}
        if timestamp_required != (submitted_at is not None):
            return _mark_snapshot_malformed(
                file,
                snap,
                "archive_submission.timestamp presence conflicts with submission status",
            )
        if submitted_at is not None and not _is_rfc3339(submitted_at):
            return _mark_snapshot_malformed(
                file, snap, "archive_submission.timestamp must be RFC3339"
            )
        if archive_submission_url not in {None, "", snap.get("url_archive")}:
            return _mark_snapshot_malformed(
                file,
                snap,
                "archive_submission.archive_url must match url_archive",
            )

    # Policy: check original/canonical/archive domains before content retrieval.
    try:
        _assert_safe_url(str(url_original))
    except FetchError as e:
        return _mark_snapshot_malformed(
            file, snap, f"url_original failed public-host safety check: {e.message}"
        )
    if platform in PLATFORM_HOST_HINTS and not _platform_host_ok(platform, url_original):
        return _mark_snapshot_malformed(
            file,
            snap,
            f"url host does not match platform policy metadata ({platform}): {url_original}",
        )

    # Validate url_canonical / archive URL public-host safety before network.
    url_canonical = str(snap.get("url_canonical") or "").strip()
    url_archive = str(snap.get("url_archive") or "").strip()
    for label, candidate in (
        ("url_canonical", url_canonical),
        ("url_archive", url_archive),
    ):
        if not candidate:
            continue
        try:
            _assert_safe_url(candidate)
        except FetchError as e:
            return _mark_snapshot_malformed(
                file, snap, f"{label} failed public-host safety check: {e.message}"
            )
        if label == "url_archive":
            archive_host = (urllib.parse.urlparse(candidate).hostname or "").lower()
            if archive_host != "web.archive.org":
                return _mark_snapshot_malformed(
                    file, snap, "url_archive must use the canonical web.archive.org host"
                )
    if url_canonical and platform in PLATFORM_HOST_HINTS:
        if not _platform_host_ok(platform, url_canonical):
            # Federated platforms (mastodon/lemmy) allow empty host hints, so
            # _platform_host_ok is permissive; for others enforce identity match.
            return _mark_snapshot_malformed(
                file,
                snap,
                f"url_canonical host does not match platform {platform}: {url_canonical}",
            )

    if tier == "B":
        snap["verification"]["status"] = "unknown"
        snap["verification"]["last_verified_at"] = now
        print(
            "info: Tier B snapshots cannot be re-verified against the original; "
            "status set to unknown."
        )
        file.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
        return 0

    # Tier A: re-fetch and compare
    stored_hash = snap.get("content_hash_sha256", "")

    try:
        if platform == "reddit":
            parsed = urllib.parse.urlparse(url_original)
            path = parsed.path.rstrip("/")
            if not path.endswith(".json"):
                path += ".json"
            api_url = f"https://www.reddit.com{path}"
            data = _fetch_json(api_url)
            if isinstance(data, list) and len(data) > 0:
                post_data = data[0].get("data", {}).get("children", [{}])[0].get("data", {})
            else:
                post_data = {}
            text = post_data.get("selftext") or post_data.get("title") or ""
        elif platform == "hn":
            item_id = snap.get("post", {}).get("id", "")
            api_url = f"https://hn.algolia.com/api/v1/items/{item_id}"
            data = _fetch_json(api_url)
            text = data.get("text") or data.get("title") or ""
        elif platform == "mastodon":
            parsed = urllib.parse.urlparse(url_original)
            instance = parsed.hostname
            match = re.search(r"/(\d+)$", parsed.path)
            status_id = match.group(1) if match else ""
            api_url = f"https://{instance}/api/v1/statuses/{status_id}"
            data = _fetch_json(api_url)
            html_content = data.get("content", "")
            text = re.sub(r"<[^>]+>", "", html_content).strip()
        elif platform == "bluesky":
            parsed = urllib.parse.urlparse(url_original)
            match = re.match(r"/profile/([^/]+)/post/([^/]+)", parsed.path)
            if match:
                handle, rkey = match.group(1), match.group(2)
                at_uri = f"at://{handle}/app.bsky.feed.post/{rkey}"
                params = urllib.parse.urlencode({"uri": at_uri, "depth": "0"})
                api_url = f"https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?{params}"
                data = _fetch_json(api_url)
                text = data.get("thread", {}).get("post", {}).get("record", {}).get("text", "")
            else:
                text = ""
        elif platform == "lemmy":
            parsed = urllib.parse.urlparse(url_original)
            instance = parsed.hostname
            match = re.search(r"/post/(\d+)", parsed.path)
            post_id = match.group(1) if match else ""
            api_url = f"https://{instance}/api/v3/post?id={post_id}"
            data = _fetch_json(api_url)
            post_view = data.get("post_view", {})
            post_data = post_view.get("post", {})
            text = post_data.get("body") or post_data.get("name") or ""
        else:
            print(f"error: unsupported platform for verification: {platform}", file=sys.stderr)
            return 1

    except FetchError as e:
        # Only 404/410 map to deleted; other failures keep their status.
        status = e.status if e.status in VALID_VERIFICATION_STATUS else "unknown"
        snap["verification"]["status"] = status
        snap["verification"]["last_verified_at"] = now
        if status == "deleted":
            snap["verifiability"] = "direct_api_deleted"
            print("warning: original post appears deleted.")
        else:
            print(f"warning: verification status={status}: {e.message}")
        file.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
        return 0 if status == "deleted" else 1

    new_hash = compute_content_hash(text if text else None)

    if new_hash == stored_hash:
        snap["verification"]["status"] = "intact"
    else:
        snap["verification"]["status"] = "edited"
        print("warning: content hash differs; post may have been edited.")

    snap["verification"]["last_verified_at"] = now
    file.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


# ---------------------------------------------------------------------------
# To-Ledger Row Generator
# ---------------------------------------------------------------------------

LEDGER_FIELDS = [
    "claim_id",
    "claim",
    "sub_question",
    "source_title",
    "source_url",
    "source_type",
    "date_published",
    "date_accessed",
    "access_method",
    "evidence",
    "quote_or_anchor",
    "contradiction",
    "confidence",
    "notes",
    "archive_url",
    "content_hash",
    "snapshot_status",
    "verifiability",
    "verifiability_note",
    "license_spdx",
    "robots_status",
    "prov_activity_id",
]


def _prov_activity_id(prefix: str, *parts: str) -> str:
    """Compute a deterministic prov:Activity identifier."""
    seed = "|".join(p for p in parts if p)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]
    return f"prov:{prefix}:{digest}"


def to_ledger_row(file: Path, out_row: Path) -> int:
    """Convert Snapshot JSON to evidence-ledger CSV row."""
    try:
        snap = _read_snapshot_json(file)
    except (json.JSONDecodeError, OSError, UnicodeError) as e:
        print(f"error: invalid snapshot file: {e}", file=sys.stderr)
        sys.exit(1)

    post = snap.get("post", {})
    text = post.get("text") or ""
    platform = snap.get("platform", "")
    verification = snap.get("verification", {})
    source_url = snap.get("url_original", "")
    content_hash = snap.get("content_hash_sha256", "")
    claim_seed = f"{platform}:{source_url}:{post.get('id') or ''}:{content_hash}"
    claim_hash = hashlib.sha256(claim_seed.encode("utf-8")).hexdigest()[:10]
    author_handle = post.get("author_handle") or ""
    notes = []
    if author_handle:
        notes.append(f"author_handle={author_handle}")
    if snap.get("url_archive"):
        notes.append("archive_url_present=true")

    row = {
        "claim_id": f"SOCIAL_{claim_hash}",
        "claim": text[:200] if text else f"[{platform} post archived]",
        "sub_question": "",
        "source_title": f"{platform} post by {post.get('author_handle', 'unknown')}",
        "source_url": source_url,
        "source_type": "community",
        "date_published": post.get("posted_at") or "",
        "date_accessed": snap.get("captured_at", ""),
        "access_method": "social_snapshot",
        "evidence": text[:500] if text else "",
        "quote_or_anchor": "",
        "contradiction": "none",
        "confidence": "high" if snap.get("tier") == "A" else "medium",
        "notes": "; ".join(notes),
        "archive_url": snap.get("url_archive") or "",
        "content_hash": content_hash,
        "snapshot_status": verification.get("status", ""),
        "verifiability": snap.get("verifiability", ""),
        "verifiability_note": snap.get("verifiability_note", ""),
        # v3.0 provenance/compliance fields. We do not check robots.txt for
        # public social-media APIs - the platform's API ToS governs use.
        "license_spdx": "NOASSERTION",
        "robots_status": "not_applicable",
        "prov_activity_id": _prov_activity_id(
            f"social-{platform.lower() or 'unknown'}",
            source_url,
            content_hash,
        ),
    }

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=LEDGER_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerow(row)
    out_row.write_text(buf.getvalue(), encoding="utf-8")
    return 0


# ---------------------------------------------------------------------------
# Self-Test (offline, no network)
# ---------------------------------------------------------------------------

# Mock API responses for each Tier A platform
_MOCK_REDDIT_JSON = [
    {
        "data": {
            "children": [
                {
                    "data": {
                        "id": "abc123",
                        "author": "testuser",
                        "selftext": "Hello from Reddit",
                        "title": "Test Post",
                        "score": 42,
                        "num_comments": 5,
                        "permalink": "/r/test/comments/abc123/test_post/",
                        "subreddit": "test",
                    }
                }
            ]
        }
    },
]

_MOCK_HN_JSON = {
    "id": 12345,
    "author": "hnuser",
    "text": "Hello from HN",
    "title": "HN Test",
    "points": 100,
    "created_at": "2026-01-01T00:00:00Z",
    "children": [{"id": 1}, {"id": 2}],
}

_MOCK_MASTODON_JSON = {
    "id": "109876",
    "content": "<p>Hello from Mastodon</p>",
    "created_at": "2026-01-01T00:00:00Z",
    "language": "en",
    "favourites_count": 10,
    "reblogs_count": 3,
    "replies_count": 1,
    "url": "https://mastodon.social/@user/109876",
    "account": {"acct": "user", "display_name": "Test User"},
}

_MOCK_BLUESKY_JSON = {
    "thread": {
        "post": {
            "record": {
                "text": "Hello from Bluesky",
                "createdAt": "2026-01-01T00:00:00Z",
                "langs": ["en"],
            },
            "author": {"handle": "user.bsky.social", "displayName": "Bsky User"},
            "likeCount": 5,
            "repostCount": 2,
            "replyCount": 1,
        }
    },
}

_MOCK_LEMMY_JSON = {
    "post_view": {
        "post": {
            "id": 999,
            "name": "Lemmy Test",
            "body": "Hello from Lemmy",
            "published": "2026-01-01T00:00:00Z",
            "ap_id": "https://lemmy.ml/post/999",
        },
        "creator": {"name": "lemmyuser", "display_name": "Lemmy User"},
        "counts": {"score": 20, "comments": 3},
        "community": {"name": "test"},
    },
}


def self_test() -> int:
    """Offline self-test with mocked HTTP and subprocess."""
    import types

    calls_made: list[str] = []
    errors: list[str] = []

    # --- Monkey-patch urllib.request.urlopen ---
    original_urlopen = urllib.request.urlopen

    class _MockResponse:
        def __init__(self, data: bytes):
            self._stream = io.BytesIO(data)
            self.headers = {"Content-Length": str(len(data))}

        def read(self, _n: int | None = None):
            return self._stream.read(_n)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    def mock_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        calls_made.append(url)

        if "reddit.com" in url and ".json" in url:
            return _MockResponse(json.dumps(_MOCK_REDDIT_JSON).encode())
        elif "hn.algolia.com/api/v1/items" in url:
            return _MockResponse(json.dumps(_MOCK_HN_JSON).encode())
        elif "/api/v1/statuses/" in url:
            return _MockResponse(json.dumps(_MOCK_MASTODON_JSON).encode())
        elif "public.api.bsky.app/xrpc" in url:
            return _MockResponse(json.dumps(_MOCK_BLUESKY_JSON).encode())
        elif "/api/v3/post" in url:
            return _MockResponse(json.dumps(_MOCK_LEMMY_JSON).encode())
        else:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    urllib.request.urlopen = mock_urlopen

    # --- Monkey-patch subprocess.run ---
    original_subprocess_run = subprocess.run

    def mock_subprocess_run(args, **kwargs):
        cmd_str = " ".join(str(a) for a in args)
        calls_made.append(f"subprocess: {cmd_str}")
        result = types.SimpleNamespace()
        result.returncode = 0
        result.stderr = ""
        if "wayback.py" in cmd_str and "save" in cmd_str:
            result.stdout = "Saved: https://web.archive.org/web/20260101/https://example.com"
        elif "wayback.py" in cmd_str and "nearest" in cmd_str:
            result.stdout = "Snapshot URL: https://web.archive.org/web/20260101000000/https://example.com\nTimestamp:    20260101000000"
        elif "evidence_ledger.py" in cmd_str and "validate" in cmd_str:
            result.stdout = ""
            result.returncode = 0
        else:
            result.stdout = ""
        return result

    subprocess.run = mock_subprocess_run

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            # --- Test 1: Tier A handlers ---
            tier_a_tests = [
                ("reddit", "https://www.reddit.com/r/test/comments/abc123/test_post/", None),
                ("hn", "https://news.ycombinator.com/item?id=12345", "12345"),
                ("mastodon", "https://mastodon.social/@user/109876", None),
                ("bluesky", "https://bsky.app/profile/user.bsky.social/post/rkey1", None),
                ("lemmy", "https://lemmy.ml/post/999", None),
            ]

            for platform, url, item_id in tier_a_tests:
                out_file = tmp / f"{platform}_snap.json"
                if platform == "hn":
                    snapshot_hn(item_id, out_file)
                elif platform == "reddit":
                    snapshot_reddit(url, out_file)
                elif platform == "mastodon":
                    snapshot_mastodon(url, out_file)
                elif platform == "bluesky":
                    snapshot_bluesky(url, out_file)
                elif platform == "lemmy":
                    snapshot_lemmy(url, out_file)

                snap = json.loads(out_file.read_text(encoding="utf-8"))
                # Validate schema compliance
                if snap.get("schema_version") != SCHEMA_VERSION:
                    errors.append(
                        f"{platform}: expected schema_version {SCHEMA_VERSION}, "
                        f"got {snap.get('schema_version')!r}"
                    )
                if snap.get("platform") != platform:
                    errors.append(f"{platform}: wrong platform field")
                if "archive_submission" not in snap:
                    errors.append(f"{platform}: missing archive_submission")
                if snap.get("tier") != "A":
                    errors.append(f"{platform}: tier should be A")
                if snap.get("verifiability") != "direct_api":
                    errors.append(f"{platform}: verifiability should be direct_api")
                if not snap.get("verifiability_note"):
                    errors.append(f"{platform}: missing verifiability_note")
                if not snap.get("captured_at"):
                    errors.append(f"{platform}: missing captured_at")
                if not snap.get("content_hash_sha256"):
                    errors.append(f"{platform}: missing content_hash_sha256")
                if "post" not in snap:
                    errors.append(f"{platform}: missing post object")
                if "verification" not in snap:
                    errors.append(f"{platform}: missing verification object")

            # --- Test 2: Tier B handlers ---
            tier_b_platforms = list(TIER_B_PLATFORMS) + ["generic"]
            for platform in tier_b_platforms:
                out_file = tmp / f"{platform}_snap.json"
                if platform == "generic":
                    snapshot_generic("https://example.com/post/1", out_file)
                else:
                    snapshot_tier_b(platform, f"https://{platform}.com/post/1", out_file)

                snap = json.loads(out_file.read_text(encoding="utf-8"))
                if snap.get("schema_version") != SCHEMA_VERSION:
                    errors.append(f"{platform}: wrong schema_version")
                if snap.get("tier") != "B":
                    errors.append(f"{platform}: tier should be B")
                if snap.get("verifiability") != "archive_snapshot":
                    errors.append(f"{platform}: verifiability should be archive_snapshot")
                if snap.get("post", {}).get("text") is not None:
                    errors.append(f"{platform}: post.text should be null for Tier B")
                if not snap.get("limitations"):
                    errors.append(f"{platform}: limitations should be non-empty")
                arch = snap.get("archive_submission") or {}
                if arch.get("requested"):
                    errors.append(f"{platform}: default Tier B must not request archive submit")
                if arch.get("status") != "lookup_only":
                    errors.append(f"{platform}: default Tier B status should be lookup_only")

            # Tier B default must not call wayback save
            save_calls = [c for c in calls_made if "wayback.py" in c and "save" in c]
            if save_calls:
                errors.append(f"Tier B default must not submit archive; save calls: {save_calls}")

            # Opt-in submit-archive does call save
            calls_before = len(calls_made)
            submit_out = tmp / "x_submit.json"
            snapshot_tier_b("x", "https://x.com/post/2", submit_out, submit_archive=True)
            save_after = [c for c in calls_made[calls_before:] if "wayback.py" in c and "save" in c]
            if not save_after:
                errors.append("--submit-archive should invoke wayback save")
            submit_snap = json.loads(submit_out.read_text(encoding="utf-8"))
            if not (submit_snap.get("archive_submission") or {}).get("requested"):
                errors.append("submit-archive snapshot should set requested=true")

            # --- Test 3: Hash stability ---
            known_input = "Hello, world!"
            known_hash = hashlib.sha256("Hello, world!".encode("utf-8")).hexdigest()
            computed = compute_content_hash(known_input)
            if computed != known_hash:
                errors.append(f"hash stability: expected {known_hash}, got {computed}")

            # Canonicalize idempotency
            text_with_crlf = "  Hello\r\nWorld  "
            c1 = canonicalize_text(text_with_crlf)
            c2 = canonicalize_text(c1)
            if c1 != c2:
                errors.append("canonicalize is not idempotent")

            # None input
            if compute_content_hash(None) != "":
                errors.append("hash of None should be empty string")

            # --- Test 4: Verification logic ---
            # Same content → intact
            reddit_snap_file = tmp / "reddit_snap.json"
            verify_snapshot(reddit_snap_file)
            snap = json.loads(reddit_snap_file.read_text(encoding="utf-8"))
            if snap["verification"]["status"] != "intact":
                errors.append(
                    f"verification: expected intact, got {snap['verification']['status']}"
                )

            # Different content → edited
            snap["content_hash_sha256"] = (
                "0000000000000000000000000000000000000000000000000000000000000000"
            )
            reddit_snap_file.write_text(json.dumps(snap, indent=2), encoding="utf-8")
            verify_snapshot(reddit_snap_file)
            snap = json.loads(reddit_snap_file.read_text(encoding="utf-8"))
            if snap["verification"]["status"] != "edited":
                errors.append(
                    f"verification: expected edited, got {snap['verification']['status']}"
                )

            # Tier B → unknown
            tier_b_file = tmp / "x_snap.json"
            verify_snapshot(tier_b_file)
            snap = json.loads(tier_b_file.read_text(encoding="utf-8"))
            if snap["verification"]["status"] != "unknown":
                errors.append(
                    f"verification: expected unknown for Tier B, got {snap['verification']['status']}"
                )

            # Tier/platform mismatch and malformed timestamps must fail before
            # any content re-fetch is attempted.
            tier_policy_file = tmp / "tier_policy_invalid.json"
            tier_policy_snap = json.loads(tier_b_file.read_text(encoding="utf-8"))
            tier_policy_snap["tier"] = "A"
            tier_policy_file.write_text(json.dumps(tier_policy_snap), encoding="utf-8")
            calls_before_policy_check = len(calls_made)
            if verify_snapshot(tier_policy_file) == 0:
                errors.append("verification: tier/platform mismatch should fail")
            if len(calls_made) != calls_before_policy_check:
                errors.append(
                    "verification: tier-policy failure must not perform HTTP/subprocess work"
                )

            timestamp_file = tmp / "timestamp_invalid.json"
            timestamp_snap = json.loads(tier_b_file.read_text(encoding="utf-8"))
            timestamp_snap["captured_at"] = "not-a-timestamp"
            timestamp_file.write_text(json.dumps(timestamp_snap), encoding="utf-8")
            calls_before_timestamp_check = len(calls_made)
            if verify_snapshot(timestamp_file) == 0:
                errors.append("verification: malformed captured_at should fail")
            if len(calls_made) != calls_before_timestamp_check:
                errors.append(
                    "verification: timestamp failure must not perform HTTP/subprocess work"
                )

            # --- Test 5: To-ledger ---
            ledger_out = tmp / "row.csv"
            to_ledger_row(tmp / "reddit_snap.json", ledger_out)
            csv_content = ledger_out.read_text(encoding="utf-8")
            if "verifiability" not in csv_content:
                errors.append("to-ledger: missing verifiability column")
            if "content_hash" not in csv_content:
                errors.append("to-ledger: missing content_hash column")
            with ledger_out.open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            if not rows:
                errors.append("to-ledger: no data row written")
            else:
                row = rows[0]
                if not row.get("claim_id", "").startswith("SOCIAL_"):
                    errors.append("to-ledger: claim_id should be populated with SOCIAL_ prefix")
                if "author_handle=" not in row.get("notes", ""):
                    errors.append("to-ledger: notes should preserve author_handle provenance")
            try:
                from evidence_ledger import validate_ledger

                if validate_ledger(ledger_out) != 0:
                    errors.append(
                        "to-ledger: generated ledger row failed evidence_ledger validation"
                    )
            except ImportError as exc:
                errors.append(f"to-ledger: could not import evidence_ledger validator: {exc}")

            # --- Test 6a: SSRF guard blocks private targets before fetch ---
            for bad in (
                "http://127.0.0.1/x",
                "https://127.0.0.1/x",
                "https://localhost/x",
                "https://169.254.169.254/latest/meta-data/",
                "https://192.168.1.10/x",
                "https://[::1]/x",
                "https://[::ffff:127.0.0.1]/x",
                "https://[::ffff:169.254.169.254]/latest/",
                "https://[::ffff:10.0.0.1]/x",
            ):
                try:
                    _assert_safe_url(bad)
                    errors.append(f"SSRF: should reject {bad}")
                except FetchError:
                    pass
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"SSRF: unexpected error for {bad}: {exc}")

            # url_canonical private must not verify as intact
            bad_canon = tmp / "bad_canonical.json"
            bad_canon.write_text(
                json.dumps(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "platform": "reddit",
                        "tier": "A",
                        "url_original": "https://www.reddit.com/r/test/comments/abc/x/",
                        "url_canonical": "http://127.0.0.1/admin",
                        "url_archive": None,
                        "verification": {
                            "status": "intact",
                            "first_capture_at": "2026-01-01T00:00:00Z",
                            "last_verified_at": None,
                        },
                        "content_hash_sha256": "abc",
                        "post": {"id": "1", "text": "hi"},
                    }
                ),
                encoding="utf-8",
            )
            vrc = verify_snapshot(bad_canon)
            vsnap = json.loads(bad_canon.read_text(encoding="utf-8"))
            if vrc == 0 or vsnap.get("verification", {}).get("status") == "intact":
                errors.append("verify must fail when url_canonical is private (not intact)")

            # --- Test 6: Privacy refusal probe ---
            privacy_calls_before = len(calls_made)
            try:
                check_privacy_boundary("https://twitter.com/minor_account/teen", "x")
                errors.append("privacy: should have refused minor account")
            except SystemExit as e:
                if e.code != 2:
                    errors.append(f"privacy: expected exit code 2, got {e.code}")
            # Verify no HTTP calls were made for the privacy check
            if len(calls_made) > privacy_calls_before:
                errors.append("privacy: HTTP call made before privacy check completed")

            # Nitter mirror refusal
            try:
                check_privacy_boundary("https://nitter.net/user/status/123", "x")
                errors.append("privacy: should have refused nitter mirror")
            except SystemExit as e:
                if e.code != 2:
                    errors.append(f"privacy: nitter refusal expected exit code 2, got {e.code}")

            # Harassment framing refusal
            try:
                check_privacy_boundary("https://twitter.com/user/doxx_target", "x")
                errors.append("privacy: should have refused harassment framing")
            except SystemExit as e:
                if e.code != 2:
                    errors.append(f"privacy: harassment refusal expected exit code 2, got {e.code}")

            # Social HTTP limit must propagate as a ResourceLimitError so the
            # CLI can emit exit 3 and an incomplete sidecar.
            limit_env = "D_RESEARCH_SOCIAL_MAX_BYTES"
            previous_limit = os.environ.get(limit_env)
            os.environ[limit_env] = "4"
            try:
                _fetch_json("https://www.reddit.com/r/test/comments/abc123/test_post/.json")
                errors.append("social oversized response should fail closed")
            except ResourceLimitError as exc:
                if exc.code != "social_max_bytes":
                    errors.append(f"social oversized response wrong code: {exc.code}")
            finally:
                if previous_limit is None:
                    os.environ.pop(limit_env, None)
                else:
                    os.environ[limit_env] = previous_limit

    finally:
        # Restore originals
        urllib.request.urlopen = original_urlopen
        subprocess.run = original_subprocess_run

    if errors:
        print("social_snapshot self-test FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("social_snapshot self-test ok")
    return 0


# ---------------------------------------------------------------------------
# CLI (argparse)
# ---------------------------------------------------------------------------


def main() -> int:
    global _REFUSAL_LOCALE  # noqa: PLW0603

    parser = argparse.ArgumentParser(
        prog="social_snapshot.py",
        description="Social media archival: snapshot, verify, to-ledger, self-test.",
    )
    parser.add_argument(
        "--locale",
        default="en",
        choices=("en", "vi"),
        help="Locale for refusal messages (default: en).",
    )
    subparsers = parser.add_subparsers(dest="command")

    # snapshot subcommand
    snap_parser = subparsers.add_parser("snapshot", help="Capture a public social post")
    snap_parser.add_argument(
        "platform", help="Platform name (reddit, hn, mastodon, bluesky, lemmy, x, facebook, etc.)"
    )
    snap_parser.add_argument("--url", help="URL of the post to capture")
    snap_parser.add_argument("--id", dest="item_id", help="Item ID (required for hn)")
    snap_parser.add_argument("--out", required=True, help="Output JSON file path")
    snap_parser.add_argument(
        "--submit-archive",
        action="store_true",
        default=False,
        help="Opt-in: submit URL to Wayback Save Page Now (Tier B). Default is lookup-only.",
    )

    # verify subcommand
    verify_parser = subparsers.add_parser("verify", help="Re-fetch and compare content hash")
    verify_parser.add_argument("--file", required=True, help="Snapshot JSON file to verify")

    # to-ledger subcommand
    ledger_parser = subparsers.add_parser(
        "to-ledger", help="Convert snapshot to evidence-ledger CSV row"
    )
    ledger_parser.add_argument("--file", required=True, help="Snapshot JSON file")
    ledger_parser.add_argument("--out-row", required=True, help="Output CSV row file")
    for command_parser in (snap_parser, verify_parser, ledger_parser):
        add_resource_limit_arguments(
            command_parser,
            (
                "download_max_bytes",
                "social_max_bytes",
                "http_timeout_sec",
                "subprocess_timeout_sec",
            ),
        )

    # self-test subcommand
    subparsers.add_parser("self-test", help="Run offline self-tests")

    args = parser.parse_args()
    _REFUSAL_LOCALE = args.locale

    try:
        apply_cli_limit_overrides(args)
        if args.command == "snapshot":
            platform = args.platform.lower()
            url = args.url or ""
            # Privacy check BEFORE any HTTP call
            if url:
                check_privacy_boundary(url, platform)
            return route_platform(
                platform,
                url,
                args.item_id,
                Path(args.out),
                submit_archive=bool(getattr(args, "submit_archive", False)),
            )

        if args.command == "verify":
            return verify_snapshot(Path(args.file))

        if args.command == "to-ledger":
            return to_ledger_row(Path(args.file), Path(args.out_row))

        if args.command == "self-test":
            return self_test()
    except ResourceLimitError as error:
        output = None
        if args.command == "snapshot":
            output = getattr(args, "out", None)
        elif args.command == "verify":
            output = getattr(args, "file", None)
        elif args.command == "to-ledger":
            output = getattr(args, "out_row", None)
        return emit_blocker(error, output)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
