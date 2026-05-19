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

USER_AGENT = "d-research-skill/0.3.0 (https://github.com/d-init-d/d-research-skill)"
SCHEMA_VERSION = "1.0"

TIER_A_PLATFORMS = {"reddit", "hn", "mastodon", "bluesky", "lemmy"}
TIER_B_PLATFORMS = {"x", "facebook", "instagram", "tiktok", "youtube", "threads", "linkedin"}

SCRIPTS_DIR = Path(__file__).resolve().parent
WAYBACK_SCRIPT = SCRIPTS_DIR / "wayback.py"


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


def _fetch_json(url: str) -> dict:
    """Fetch URL and parse JSON response. Exits on error."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            return json.loads(data.decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"error: post not found at {url}", file=sys.stderr)
        elif e.code == 403:
            print(f"error: access denied for {url}", file=sys.stderr)
        else:
            print(f"error: HTTP {e.code} for {url}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"error: could not resolve or connect to {url}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"error: invalid JSON from {url}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Snapshot JSON Builder
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
) -> dict:
    """Build a schema v1.0 Snapshot JSON dict."""
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

    data = _fetch_json(api_url)
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
    data = _fetch_json(api_url)

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
    data = _fetch_json(api_url)

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
    data = _fetch_json(api_url)

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
    data = _fetch_json(api_url)

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
    "x": ["No direct API access; content from Wayback archive only", "Text may be incomplete or missing"],
    "facebook": ["No direct API access; content from Wayback archive only", "Login-walled content not captured"],
    "instagram": ["No direct API access; content from Wayback archive only", "Media not captured"],
    "tiktok": ["No direct API access; content from Wayback archive only", "Video content not captured"],
    "youtube": ["No direct API access; content from Wayback archive only", "Video content not captured", "Comments not captured"],
    "threads": ["No direct API access; content from Wayback archive only", "Text may be incomplete"],
    "linkedin": ["No direct API access; content from Wayback archive only", "Login-walled content not captured"],
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


def snapshot_tier_b(platform: str, url: str, out: Path) -> int:
    """Archive-only path via wayback.py subprocess."""
    python_cmd = sys.executable or "python3"

    # Step 1: Save to Wayback
    save_result = subprocess.run(
        [python_cmd, str(WAYBACK_SCRIPT), "save", "--url", url],
        capture_output=True, text=True, timeout=60,
    )
    if save_result.returncode != 0:
        print(f"error: wayback.py save failed: {save_result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    # Step 2: Find nearest snapshot
    today = datetime.date.today().strftime("%Y%m%d")
    nearest_result = subprocess.run(
        [python_cmd, str(WAYBACK_SCRIPT), "nearest", "--url", url, "--timestamp", today],
        capture_output=True, text=True, timeout=60,
    )

    # Parse archive URL from stdout
    archive_url = None
    for line in nearest_result.stdout.splitlines():
        if line.startswith("Snapshot URL:"):
            archive_url = line.split(":", 1)[1].strip()
            break

    limitations = _TIER_B_LIMITATIONS.get(platform, ["No direct API access; content from Wayback archive only"])
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
    )
    out.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


# ---------------------------------------------------------------------------
# Generic Handler
# ---------------------------------------------------------------------------


def snapshot_generic(url: str, out: Path) -> int:
    """Generic fallback: attempt Wayback snapshot path."""
    python_cmd = sys.executable or "python3"

    # Save to Wayback
    save_result = subprocess.run(
        [python_cmd, str(WAYBACK_SCRIPT), "save", "--url", url],
        capture_output=True, text=True, timeout=60,
    )
    if save_result.returncode != 0:
        print(f"error: wayback.py save failed: {save_result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    # Find nearest snapshot
    today = datetime.date.today().strftime("%Y%m%d")
    nearest_result = subprocess.run(
        [python_cmd, str(WAYBACK_SCRIPT), "nearest", "--url", url, "--timestamp", today],
        capture_output=True, text=True, timeout=60,
    )

    archive_url = None
    for line in nearest_result.stdout.splitlines():
        if line.startswith("Snapshot URL:"):
            archive_url = line.split(":", 1)[1].strip()
            break

    post = _default_post()
    post["text"] = None

    snap = _build_snapshot(
        platform="generic",
        tier="B",
        verifiability="archive_snapshot",
        verifiability_note="Platform not specifically recognized; archived via Wayback Machine.",
        url_original=url,
        url_canonical=url,
        url_archive=archive_url,
        post=post,
        content_hash="",
        limitations=["Platform not recognized; generic archive-only path used"],
    )
    out.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


# ---------------------------------------------------------------------------
# Platform Router
# ---------------------------------------------------------------------------


def route_platform(platform: str, url: str, item_id: str | None, out: Path) -> int:
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
        return snapshot_tier_b(platform, url, out)
    elif platform == "generic":
        return snapshot_generic(url, out)
    else:
        print(f"error: unknown platform '{platform}'", file=sys.stderr)
        sys.exit(1)
    return 0


# ---------------------------------------------------------------------------
# Verification Module
# ---------------------------------------------------------------------------


def verify_snapshot(file: Path) -> int:
    """Re-fetch and compare hash for verification."""
    try:
        snap = json.loads(file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"error: invalid snapshot file: {e}", file=sys.stderr)
        sys.exit(1)

    tier = snap.get("tier", "")
    now = _now_iso()

    if tier == "B":
        snap["verification"]["status"] = "unknown"
        snap["verification"]["last_verified_at"] = now
        print("info: Tier B snapshots cannot be re-verified against the original; status set to unknown.")
        file.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
        return 0

    # Tier A: re-fetch and compare
    platform = snap.get("platform", "")
    url_original = snap.get("url_original", "")
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

    except SystemExit:
        # _fetch_json calls sys.exit(1) on 404 → treat as deleted
        snap["verification"]["status"] = "deleted"
        snap["verification"]["last_verified_at"] = now
        snap["verifiability"] = "direct_api_deleted"
        file.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
        print("warning: original post appears deleted.")
        return 0

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
    "claim_id", "claim", "sub_question", "source_title", "source_url",
    "source_type", "date_published", "date_accessed", "access_method",
    "evidence", "quote_or_anchor", "contradiction", "confidence", "notes",
    "archive_url", "content_hash", "snapshot_status", "verifiability",
    "verifiability_note",
    "license_spdx", "robots_status", "prov_activity_id",
]


def _prov_activity_id(prefix: str, *parts: str) -> str:
    """Compute a deterministic prov:Activity identifier."""
    seed = "|".join(p for p in parts if p)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8]
    return f"prov:{prefix}:{digest}"


def to_ledger_row(file: Path, out_row: Path) -> int:
    """Convert Snapshot JSON to evidence-ledger CSV row."""
    try:
        snap = json.loads(file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
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
    {"data": {"children": [{"data": {
        "id": "abc123", "author": "testuser", "selftext": "Hello from Reddit",
        "title": "Test Post", "score": 42, "num_comments": 5,
        "permalink": "/r/test/comments/abc123/test_post/", "subreddit": "test",
    }}]}},
]

_MOCK_HN_JSON = {
    "id": 12345, "author": "hnuser", "text": "Hello from HN",
    "title": "HN Test", "points": 100, "created_at": "2026-01-01T00:00:00Z",
    "children": [{"id": 1}, {"id": 2}],
}

_MOCK_MASTODON_JSON = {
    "id": "109876", "content": "<p>Hello from Mastodon</p>",
    "created_at": "2026-01-01T00:00:00Z", "language": "en",
    "favourites_count": 10, "reblogs_count": 3, "replies_count": 1,
    "url": "https://mastodon.social/@user/109876",
    "account": {"acct": "user", "display_name": "Test User"},
}

_MOCK_BLUESKY_JSON = {
    "thread": {"post": {
        "record": {"text": "Hello from Bluesky", "createdAt": "2026-01-01T00:00:00Z", "langs": ["en"]},
        "author": {"handle": "user.bsky.social", "displayName": "Bsky User"},
        "likeCount": 5, "repostCount": 2, "replyCount": 1,
    }},
}

_MOCK_LEMMY_JSON = {
    "post_view": {
        "post": {"id": 999, "name": "Lemmy Test", "body": "Hello from Lemmy",
                 "published": "2026-01-01T00:00:00Z", "ap_id": "https://lemmy.ml/post/999"},
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
            self._data = data
        def read(self):
            return self._data
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
                if snap.get("schema_version") != "1.0":
                    errors.append(f"{platform}: missing schema_version")
                if snap.get("platform") != platform:
                    errors.append(f"{platform}: wrong platform field")
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
                if snap.get("tier") != "B":
                    errors.append(f"{platform}: tier should be B")
                if snap.get("verifiability") != "archive_snapshot":
                    errors.append(f"{platform}: verifiability should be archive_snapshot")
                if snap.get("post", {}).get("text") is not None:
                    errors.append(f"{platform}: post.text should be null for Tier B")
                if not snap.get("limitations"):
                    errors.append(f"{platform}: limitations should be non-empty")


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
                errors.append(f"verification: expected intact, got {snap['verification']['status']}")

            # Different content → edited
            snap["content_hash_sha256"] = "0000000000000000000000000000000000000000000000000000000000000000"
            reddit_snap_file.write_text(json.dumps(snap, indent=2), encoding="utf-8")
            verify_snapshot(reddit_snap_file)
            snap = json.loads(reddit_snap_file.read_text(encoding="utf-8"))
            if snap["verification"]["status"] != "edited":
                errors.append(f"verification: expected edited, got {snap['verification']['status']}")

            # Tier B → unknown
            tier_b_file = tmp / "x_snap.json"
            verify_snapshot(tier_b_file)
            snap = json.loads(tier_b_file.read_text(encoding="utf-8"))
            if snap["verification"]["status"] != "unknown":
                errors.append(f"verification: expected unknown for Tier B, got {snap['verification']['status']}")

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
                    errors.append("to-ledger: generated ledger row failed evidence_ledger validation")
            except ImportError as exc:
                errors.append(f"to-ledger: could not import evidence_ledger validator: {exc}")


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
    snap_parser.add_argument("platform", help="Platform name (reddit, hn, mastodon, bluesky, lemmy, x, facebook, etc.)")
    snap_parser.add_argument("--url", help="URL of the post to capture")
    snap_parser.add_argument("--id", dest="item_id", help="Item ID (required for hn)")
    snap_parser.add_argument("--out", required=True, help="Output JSON file path")

    # verify subcommand
    verify_parser = subparsers.add_parser("verify", help="Re-fetch and compare content hash")
    verify_parser.add_argument("--file", required=True, help="Snapshot JSON file to verify")

    # to-ledger subcommand
    ledger_parser = subparsers.add_parser("to-ledger", help="Convert snapshot to evidence-ledger CSV row")
    ledger_parser.add_argument("--file", required=True, help="Snapshot JSON file")
    ledger_parser.add_argument("--out-row", required=True, help="Output CSV row file")

    # self-test subcommand
    subparsers.add_parser("self-test", help="Run offline self-tests")

    args = parser.parse_args()
    _REFUSAL_LOCALE = args.locale

    if args.command == "snapshot":
        platform = args.platform.lower()
        url = args.url or ""
        # Privacy check BEFORE any HTTP call
        if url:
            check_privacy_boundary(url, platform)
        return route_platform(platform, url, args.item_id, Path(args.out))

    elif args.command == "verify":
        return verify_snapshot(Path(args.file))

    elif args.command == "to-ledger":
        return to_ledger_row(Path(args.file), Path(args.out_row))

    elif args.command == "self-test":
        return self_test()

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
