#!/usr/bin/env python3
"""Shared HTTP cache for d-research-skill scripts.

Cache enabled only when D_RESEARCH_HTTP_CACHE_PATH is set or --cache-path
is passed. Stdlib-only. Stores response metadata + body on disk.

Cache key inputs
----------------
* method (uppercased)
* URL (final, including all query params)
* request_key: canonical string of request-shaping headers that may change
  the response (Authorization, Cookie, X-API-Key, API-Key, Accept,
  Accept-Language). Hashed into the key only - never stored in metadata.
* body_key: optional explicit body key material for POST requests.

Privacy
-------
Response metadata stores RESPONSE headers only. Request headers
(Authorization, Cookie, API keys) are hashed into the cache key but never
written to disk in plaintext.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

CACHE_ENV = "D_RESEARCH_HTTP_CACHE_PATH"
DEFAULT_MAX_AGE_SECONDS = 7 * 24 * 3600  # 7 days

# Headers that affect response shape and must be hashed into the cache key.
# Listed in lowercase for case-insensitive comparison.
KEY_AFFECTING_HEADERS = [
    "authorization",
    "cookie",
    "x-api-key",
    "api-key",
    "accept",
    "accept-language",
]


def get_cache_path() -> Path | None:
    """Return cache directory path or None if cache is disabled."""
    val = os.environ.get(CACHE_ENV, "").strip()
    if not val:
        return None
    return Path(val)


def canonical_header_key(headers: dict[str, str] | None) -> str:
    """Build a canonical string of key-affecting headers.

    Headers are lowercased and only KEY_AFFECTING_HEADERS are included.
    Result is sorted for deterministic ordering.
    """
    if not headers:
        return ""
    normalized = {k.lower(): str(v) for k, v in headers.items()}
    lines = []
    for name in KEY_AFFECTING_HEADERS:
        if name in normalized:
            lines.append(f"{name}:{normalized[name]}")
    return "\n".join(sorted(lines))


def cache_key(
    method: str,
    url: str,
    request_key: str | None = None,
    body_key: bytes | str | None = None,
) -> str:
    """Compute SHA256 cache key for a request."""
    h = hashlib.sha256()
    h.update(method.upper().encode("utf-8"))
    h.update(b"\n")
    h.update(url.encode("utf-8"))
    if request_key:
        h.update(b"\n")
        h.update(request_key.encode("utf-8"))
    if body_key is not None:
        h.update(b"\n")
        if isinstance(body_key, str):
            h.update(body_key.encode("utf-8"))
        else:
            h.update(body_key)
    return h.hexdigest()


def _ensure_cache_dir(cache_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "entries").mkdir(exist_ok=True)


def get(
    method: str,
    url: str,
    request_headers: dict[str, str] | None = None,
    body_key: bytes | str | None = None,
    max_age: int | None = None,
    cache_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Fetch entry from cache. Returns None if missing or expired.

    request_headers is used to compute the cache key (auth-affecting headers
    only). It is never stored in the cache.
    """
    cd = cache_dir or get_cache_path()
    if cd is None:
        return None
    request_key = canonical_header_key(request_headers)
    key = cache_key(method, url, request_key=request_key, body_key=body_key)
    meta_path = cd / "entries" / f"{key}.json"
    body_path = cd / "entries" / f"{key}.body"
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    age_limit = max_age if max_age is not None else DEFAULT_MAX_AGE_SECONDS
    age = time.time() - meta.get("created_at", 0)
    if age > age_limit:
        return None

    body_bytes = b""
    if body_path.is_file():
        body_bytes = body_path.read_bytes()
    return {
        "key": key,
        "url": meta.get("url", url),
        "method": meta.get("method", method),
        "status": meta.get("status", 200),
        "headers": meta.get("headers", {}),
        "created_at": meta.get("created_at", 0),
        "body": body_bytes,
    }


def put(
    method: str,
    url: str,
    status: int,
    response_headers: dict[str, str] | None,
    body: bytes | str,
    request_headers: dict[str, str] | None = None,
    body_key: bytes | str | None = None,
    cache_dir: Path | None = None,
) -> str | None:
    """Store entry in cache. Returns cache key, or None if cache disabled.

    Only response_headers are persisted in the metadata file.
    request_headers are hashed into the cache key but never stored.
    """
    cd = cache_dir or get_cache_path()
    if cd is None:
        return None
    _ensure_cache_dir(cd)
    request_key = canonical_header_key(request_headers)
    key = cache_key(method, url, request_key=request_key, body_key=body_key)
    meta = {
        "key": key,
        "url": url,
        "method": method.upper(),
        "status": status,
        "headers": dict(response_headers) if response_headers else {},
        "created_at": int(time.time()),
    }
    meta_path = cd / "entries" / f"{key}.json"
    body_path = cd / "entries" / f"{key}.body"
    meta_path.write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if isinstance(body, str):
        body = body.encode("utf-8")
    body_path.write_bytes(body)
    return key


def cmd_get_key(args: argparse.Namespace) -> int:
    """Compute cache key for a URL/method."""
    headers: dict[str, str] = {}
    for h in args.header or []:
        if ":" not in h:
            print(f"warning: ignoring malformed --header {h!r}", file=sys.stderr)
            continue
        name, value = h.split(":", 1)
        headers[name.strip()] = value.strip()
    request_key = canonical_header_key(headers)
    body_key = args.body.encode("utf-8") if args.body else None
    print(cache_key(args.method, args.url, request_key=request_key, body_key=body_key))
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    """Show cache statistics."""
    cd = Path(args.cache_path) if args.cache_path else get_cache_path()
    if cd is None:
        print(
            "error: cache not configured (set D_RESEARCH_HTTP_CACHE_PATH or --cache-path)",
            file=sys.stderr,
        )
        return 1
    if not cd.is_dir():
        print(f"cache directory does not exist: {cd}")
        return 0
    entries_dir = cd / "entries"
    if not entries_dir.is_dir():
        print(f"cache directory has no entries/: {cd}")
        return 0
    meta_files = list(entries_dir.glob("*.json"))
    body_files = list(entries_dir.glob("*.body"))
    total_size = sum(f.stat().st_size for f in meta_files + body_files)
    print(f"cache_dir: {cd}")
    print(f"entries:   {len(meta_files)}")
    print(f"body_files: {len(body_files)}")
    print(f"size_bytes: {total_size}")
    return 0


def cmd_purge(args: argparse.Namespace) -> int:
    """Remove expired or all entries."""
    cd = Path(args.cache_path) if args.cache_path else get_cache_path()
    if cd is None:
        print("error: cache not configured", file=sys.stderr)
        return 1
    entries_dir = cd / "entries"
    if not entries_dir.is_dir():
        print("nothing to purge")
        return 0
    purge_all = args.all
    max_age = args.max_age if args.max_age is not None else DEFAULT_MAX_AGE_SECONDS
    now = time.time()
    purged = 0
    for meta_path in entries_dir.glob("*.json"):
        should_purge = purge_all
        if not should_purge:
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                age = now - meta.get("created_at", 0)
                if age > max_age:
                    should_purge = True
            except (json.JSONDecodeError, OSError):
                should_purge = True
        if should_purge:
            body_path = meta_path.with_suffix(".body")
            meta_path.unlink(missing_ok=True)
            body_path.unlink(missing_ok=True)
            purged += 1
    print(f"purged {purged} entries from {cd}")
    return 0


def cmd_self_test(_args: argparse.Namespace) -> int:
    """Offline self-test with temp directory."""
    import tempfile

    errors: list[str] = []
    saved_env = os.environ.pop(CACHE_ENV, None)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            cd = Path(tmpdir) / "cache"

            # Test 1: cache disabled when env not set
            if get_cache_path() is not None:
                errors.append("get_cache_path should be None when env not set")

            # Test 2: cache enabled when env set
            os.environ[CACHE_ENV] = str(cd)
            if get_cache_path() != cd:
                errors.append("get_cache_path should return cache dir when env set")

            # Test 3: cache key deterministic
            k1 = cache_key("GET", "https://example.com/api")
            k2 = cache_key("GET", "https://example.com/api")
            if k1 != k2:
                errors.append("cache_key not deterministic")

            # Test 4: different URLs -> different keys
            k3 = cache_key("GET", "https://example.com/other")
            if k1 == k3:
                errors.append("cache_key collision for different URLs")

            # Test 5: different methods -> different keys
            k4 = cache_key("POST", "https://example.com/api")
            if k1 == k4:
                errors.append("cache_key collision for different methods")

            # Test 6: different Authorization -> different keys
            kA = cache_key(
                "GET", "https://example.com/api",
                request_key=canonical_header_key({"Authorization": "Bearer A"}),
            )
            kB = cache_key(
                "GET", "https://example.com/api",
                request_key=canonical_header_key({"Authorization": "Bearer B"}),
            )
            if kA == kB:
                errors.append("different Authorization should produce different keys")
            if kA == k1:
                errors.append("Authorization key should differ from no-auth key")

            # Test 7: Cookie also affects key
            k_cookie = cache_key(
                "GET", "https://example.com/api",
                request_key=canonical_header_key({"Cookie": "session=abc"}),
            )
            if k_cookie == k1:
                errors.append("Cookie should affect cache key")

            # Test 8: User-Agent (non-key) does not affect key
            k_ua = cache_key(
                "GET", "https://example.com/api",
                request_key=canonical_header_key({"User-Agent": "test"}),
            )
            if k_ua != k1:
                errors.append("User-Agent should not affect cache key")

            # Test 9: get returns None on miss
            result = get("GET", "https://example.com/missing")
            if result is not None:
                errors.append("get should return None on cache miss")

            # Test 10: put then get round-trip (no auth)
            key = put(
                "GET", "https://example.com/api", 200,
                {"Content-Type": "application/json"}, b'{"hello":"world"}',
            )
            if key is None:
                errors.append("put returned None")
            result = get("GET", "https://example.com/api")
            if result is None:
                errors.append("get returned None after put")
            elif result.get("status") != 200:
                errors.append(f"cached status wrong: {result.get('status')}")
            elif result.get("body") != b'{"hello":"world"}':
                errors.append(f"cached body wrong: {result.get('body')!r}")

            # Test 11: put with Authorization stores under different key
            put(
                "GET", "https://example.com/api", 200,
                {"Content-Type": "application/json"}, b'{"auth":"A"}',
                request_headers={"Authorization": "Bearer A"},
            )

            # Get with Authorization A -> auth-A entry
            hit_a = get(
                "GET", "https://example.com/api",
                request_headers={"Authorization": "Bearer A"},
            )
            if not hit_a or hit_a.get("body") != b'{"auth":"A"}':
                errors.append("get with Authorization A should return auth-A response")

            # Get with no Authorization -> no-auth entry (different body)
            hit_no_auth = get("GET", "https://example.com/api")
            if not hit_no_auth or hit_no_auth.get("body") != b'{"hello":"world"}':
                errors.append(
                    "get without Authorization should return no-auth entry, "
                    "not Bearer A response"
                )

            # Get with Authorization B -> miss (no entry stored)
            hit_b = get(
                "GET", "https://example.com/api",
                request_headers={"Authorization": "Bearer B"},
            )
            if hit_b is not None:
                errors.append(
                    "get with Authorization B should be None (not Bearer A response)"
                )

            # Test 12: response headers stored, request headers not stored
            meta_path = cd / "entries" / f"{key}.json"
            meta_raw = json.loads(meta_path.read_text(encoding="utf-8"))
            stored_headers = {
                k.lower(): v for k, v in (meta_raw.get("headers") or {}).items()
            }
            if "authorization" in stored_headers:
                errors.append("metadata must not store request Authorization header")
            if "cookie" in stored_headers:
                errors.append("metadata must not store request Cookie header")

            # Test 13: TTL expiry
            result = get("GET", "https://example.com/api", max_age=0)
            if result is not None:
                errors.append("get should return None when max_age=0")

            # Test 14: stats
            ns = argparse.Namespace(cache_path=str(cd))
            rc = cmd_stats(ns)
            if rc != 0:
                errors.append("stats failed")

            # Test 15: purge all
            ns = argparse.Namespace(cache_path=str(cd), all=True, max_age=None)
            rc = cmd_purge(ns)
            if rc != 0:
                errors.append("purge failed")
            result = get("GET", "https://example.com/api")
            if result is not None:
                errors.append("entry still exists after purge --all")

            os.environ.pop(CACHE_ENV, None)
    finally:
        if saved_env is not None:
            os.environ[CACHE_ENV] = saved_env

    if errors:
        print("http_cache self-test FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("http_cache self-test ok")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        prog="http_cache.py", description="Shared HTTP cache utility."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    gk_p = sub.add_parser("get-key", help="Compute cache key for a URL.")
    gk_p.add_argument("--method", default="GET")
    gk_p.add_argument("--url", required=True)
    gk_p.add_argument("--body", default=None)
    gk_p.add_argument(
        "--header", action="append", default=[],
        help='Request header in "Name: value" form. Repeatable. Only auth-affecting '
        "headers (Authorization, Cookie, X-API-Key, API-Key, Accept, Accept-Language) "
        "are mixed into the key.",
    )

    st_p = sub.add_parser("stats", help="Show cache statistics.")
    st_p.add_argument("--cache-path", default=None)

    pu_p = sub.add_parser("purge", help="Purge expired or all entries.")
    pu_p.add_argument("--cache-path", default=None)
    pu_p.add_argument("--all", action="store_true")
    pu_p.add_argument("--max-age", type=int, default=None, help="Max age in seconds.")

    sub.add_parser("self-test", help="Run offline self-tests.")

    args = p.parse_args()
    if args.cmd == "get-key":
        return cmd_get_key(args)
    if args.cmd == "stats":
        return cmd_stats(args)
    if args.cmd == "purge":
        return cmd_purge(args)
    if args.cmd == "self-test":
        return cmd_self_test(args)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
