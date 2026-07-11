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
    "proxy-authorization",
    "cookie",
    "x-api-key",
    "api-key",
    "x-auth-token",
    "x-access-token",
    "x-token",
    "accept",
    "accept-language",
    "range",
]

_PUBLIC_HEADERS = {
    "accept",
    "accept-language",
    "accept-encoding",
    "content-type",
    "user-agent",
    "cache-control",
    "pragma",
    "if-none-match",
    "if-modified-since",
}


def _is_auth_secret_header(name: str) -> bool:
    """Headers that make a request credentialed for cache-blocking purposes.

    Representation selectors (Range, Accept, …) are NOT secrets.
    """
    n = (name or "").strip().lower()
    if not n:
        return False
    if n in {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "x-auth-token",
        "x-access-token",
        "x-token",
    }:
        return True
    import re

    return bool(
        re.search(
            r"(token|secret|credential|authori[sz]ation|authentication|"
            r"api-?key|password|session|csrf|xsrf)",
            n,
        )
    )


def _is_sensitive_header(name: str) -> bool:
    """Headers that must never be persisted in cache metadata."""
    n = (name or "").strip().lower()
    if not n or n in _PUBLIC_HEADERS:
        return False
    if _is_auth_secret_header(n):
        return True
    # Do not persist arbitrary custom headers that look private
    if n.startswith("x-") and _is_auth_secret_header(n):
        return True
    return n in {"set-cookie"}


def get_cache_path() -> Path | None:
    """Return cache directory path or None if cache is disabled."""
    val = os.environ.get(CACHE_ENV, "").strip()
    if not val:
        return None
    return Path(val)


def canonical_header_key(
    headers: dict[str, str] | None,
    *,
    extra_key_headers: list[str] | None = None,
) -> str:
    """Build a canonical string of key-affecting headers.

    Headers are lowercased. Includes KEY_AFFECTING_HEADERS plus any declared
    custom cache-key headers. Result is sorted for deterministic ordering.
    """
    if not headers:
        return ""
    normalized = {k.lower(): str(v) for k, v in headers.items()}
    names = list(KEY_AFFECTING_HEADERS)
    if extra_key_headers:
        for n in extra_key_headers:
            ln = str(n).lower()
            if ln not in names:
                names.append(ln)
    lines = []
    for name in names:
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


def _body_sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


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
    extra_key_headers: list[str] | None = None,
) -> dict[str, Any] | None:
    """Fetch entry from cache. Returns None if missing, expired, or mismatched.

    Validates body_sha256/body_size against metadata so concurrent writers
    cannot mix generations. Incomplete/stale temp artifacts are ignored.
    """
    cd = cache_dir or get_cache_path()
    if cd is None:
        return None
    request_key = canonical_header_key(
        request_headers, extra_key_headers=extra_key_headers
    )
    key = cache_key(method, url, request_key=request_key, body_key=body_key)
    entries = cd / "entries"
    meta_path = entries / f"{key}.json"
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

    # Prefer generation-scoped body path (atomic publish); fall back to legacy key.body.
    body_rel = meta.get("body_file")
    if isinstance(body_rel, str) and body_rel and ".." not in Path(body_rel).parts:
        body_path = entries / body_rel
    else:
        gen = meta.get("generation_id")
        if isinstance(gen, str) and gen:
            candidate = entries / f"{key}.{gen}.body"
            body_path = candidate if candidate.is_file() else entries / f"{key}.body"
        else:
            body_path = entries / f"{key}.body"
    if not body_path.is_file():
        return None

    body_bytes = body_path.read_bytes()
    expected_hash = meta.get("body_sha256")
    expected_size = meta.get("body_size")
    if expected_hash is not None and expected_hash != _body_sha256(body_bytes):
        return None  # generation mismatch — never mix writers
    if expected_size is not None and int(expected_size) != len(body_bytes):
        return None
    return {
        "key": key,
        "url": meta.get("url", url),
        "method": meta.get("method", method),
        "status": meta.get("status", 200),
        "headers": meta.get("headers", {}),
        "created_at": meta.get("created_at", 0),
        "body": body_bytes,
        "body_sha256": expected_hash or _body_sha256(body_bytes),
        "generation_id": meta.get("generation_id"),
    }


def _has_credential_headers(request_headers: dict[str, str] | None) -> bool:
    if not request_headers:
        return False
    return any(_is_auth_secret_header(k) for k in request_headers)


def _sanitize_response_headers(headers: dict[str, str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not headers:
        return out
    for k, v in headers.items():
        if _is_sensitive_header(k) or k.lower() == "set-cookie":
            continue
        out[k] = v
    return out


def _redact_url(url: str) -> str:
    # Never persist secret-bearing query params in metadata.
    try:
        from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

        parts = urlsplit(url)
        q = []
        for k, v in parse_qsl(parts.query, keep_blank_values=True):
            if k.lower() in {
                "access_token",
                "api_key",
                "apikey",
                "token",
                "key",
                "auth",
                "password",
                "secret",
            }:
                q.append((k, "[REDACTED]"))
            else:
                q.append((k, v))
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment)
        )
    except Exception:
        return url


def put(
    method: str,
    url: str,
    status: int,
    response_headers: dict[str, str] | None,
    body: bytes | str,
    request_headers: dict[str, str] | None = None,
    body_key: bytes | str | None = None,
    cache_dir: Path | None = None,
    allow_private: bool = False,
    extra_key_headers: list[str] | None = None,
) -> str | None:
    """Store entry in cache. Returns cache key, or None if cache disabled.

    Credentialed / secret-query requests are not cached unless allow_private=True.
    Vary: * responses are never cached. Each writer uses unique temp files and
    publishes one complete generation (body hash + metadata) atomically.
    """
    import uuid
    from urllib.parse import parse_qsl, urlsplit

    cd = cache_dir or get_cache_path()
    if cd is None:
        return None
    if _has_credential_headers(request_headers) and not allow_private:
        return None
    # Query secrets are private/uncacheable by default
    try:
        for k, _v in parse_qsl(urlsplit(url).query, keep_blank_values=True):
            if k.lower() in {
                "access_token",
                "api_key",
                "apikey",
                "token",
                "key",
                "auth",
                "password",
                "secret",
                "credential",
            }:
                if not allow_private:
                    return None
    except Exception:
        pass

    # Vary: * is not cacheable
    resp = {str(k).lower(): str(v) for k, v in (response_headers or {}).items()}
    vary = resp.get("vary", "")
    if vary.strip() == "*":
        return None
    # Honor Vary: fold named request headers into the key
    extra = list(extra_key_headers or [])
    if vary:
        for part in vary.split(","):
            name = part.strip().lower()
            if name and name not in extra:
                extra.append(name)

    _ensure_cache_dir(cd)
    request_key = canonical_header_key(
        request_headers, extra_key_headers=extra or None
    )
    key = cache_key(method, url, request_key=request_key, body_key=body_key)
    if isinstance(body, str):
        body = body.encode("utf-8")
    gen_id = uuid.uuid4().hex
    body_hash = _body_sha256(body)
    # Generation-scoped body path so concurrent writers never interleave
    # body and meta of different generations on a shared {key}.body file.
    body_file = f"{key}.{gen_id}.body"
    meta = {
        "key": key,
        "url": _redact_url(url),
        "method": method.upper(),
        "status": status,
        "headers": _sanitize_response_headers(response_headers),
        "created_at": int(time.time()),
        "body_sha256": body_hash,
        "body_size": len(body),
        "generation_id": gen_id,
        "body_file": body_file,
    }
    entries = cd / "entries"
    meta_path = entries / f"{key}.json"
    body_path = entries / body_file
    # Unique temps per writer — never shared .tmp names
    tmp_body = entries / f"{key}.{gen_id}.body.tmp"
    tmp_meta = entries / f"{key}.{gen_id}.json.tmp"
    try:
        tmp_body.write_bytes(body)
        tmp_meta.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        # 1) Publish body to a unique generation path (no cross-writer collision).
        # 2) Atomically publish meta pointing at that body. Losers of the meta
        # race leave orphan generation bodies; the live entry always matches.
        last_err: Exception | None = None
        for attempt in range(12):
            try:
                os.replace(str(tmp_body), str(body_path))
                last_err = None
                break
            except OSError as exc:
                last_err = exc
                time.sleep(0.02 * (attempt + 1))
        if last_err is not None:
            for p in (tmp_body, tmp_meta):
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
            return key
        last_err = None
        for attempt in range(12):
            try:
                os.replace(str(tmp_meta), str(meta_path))
                last_err = None
                break
            except OSError as exc:
                last_err = exc
                time.sleep(0.02 * (attempt + 1))
        if last_err is not None:
            try:
                tmp_meta.unlink(missing_ok=True)
            except OSError:
                pass
            # Contended concurrent writers: another generation may already be live.
            return key
        try:
            os.chmod(meta_path, 0o600)
            os.chmod(body_path, 0o600)
        except OSError:
            pass
    except Exception:
        for p in (tmp_body, tmp_meta):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
        return key
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

            # Test 11: credentialed requests are NOT cached by default
            refused = put(
                "GET", "https://example.com/api", 200,
                {"Content-Type": "application/json"}, b'{"auth":"A"}',
                request_headers={"Authorization": "Bearer A"},
            )
            if refused is not None:
                errors.append("credentialed put must return None without allow_private")

            # Explicit private-cache mode stores under auth-keyed entry
            put(
                "GET", "https://example.com/api", 200,
                {"Content-Type": "application/json"}, b'{"auth":"A"}',
                request_headers={"Authorization": "Bearer A"},
                allow_private=True,
            )
            hit_a = get(
                "GET", "https://example.com/api",
                request_headers={"Authorization": "Bearer A"},
            )
            if not hit_a or hit_a.get("body") != b'{"auth":"A"}':
                errors.append("private-cache get with Authorization A should hit")

            hit_no_auth = get("GET", "https://example.com/api")
            if not hit_no_auth or hit_no_auth.get("body") != b'{"hello":"world"}':
                errors.append(
                    "get without Authorization should return no-auth entry, "
                    "not Bearer A response"
                )

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
            secret_header_key = put(
                "GET",
                "https://example.com/response-secrets",
                200,
                {
                    "Content-Type": "application/json",
                    "Authentication-Info": "nextnonce=SUPERSECRET",
                    "X-Session-ID": "SESSIONSECRET",
                    "X-CSRF-Token": "CSRFSECRET",
                },
                b"{}",
            )
            secret_meta = json.loads(
                (cd / "entries" / f"{secret_header_key}.json").read_text(
                    encoding="utf-8"
                )
            )
            secret_names = {
                name.lower() for name in (secret_meta.get("headers") or {})
            }
            if secret_names & {
                "authentication-info",
                "x-session-id",
                "x-csrf-token",
            }:
                errors.append("metadata persisted a response authentication/session header")

            # Test 13: TTL expiry
            result = get("GET", "https://example.com/api", max_age=0)
            if result is not None:
                errors.append("get should return None when max_age=0")

            # Test 14: Range variants do not collide
            put(
                "GET",
                "https://example.com/range",
                206,
                {"Content-Type": "text/plain", "Content-Range": "bytes 0-3/10"},
                b"abcd",
                request_headers={"Range": "bytes=0-3"},
            )
            put(
                "GET",
                "https://example.com/range",
                206,
                {"Content-Type": "text/plain", "Content-Range": "bytes 4-7/10"},
                b"efgh",
                request_headers={"Range": "bytes=4-7"},
            )
            r0 = get(
                "GET",
                "https://example.com/range",
                request_headers={"Range": "bytes=0-3"},
            )
            r1 = get(
                "GET",
                "https://example.com/range",
                request_headers={"Range": "bytes=4-7"},
            )
            if not r0 or r0.get("body") != b"abcd":
                errors.append("Range 0-3 cache miss/collision")
            if not r1 or r1.get("body") != b"efgh":
                errors.append("Range 4-7 cache miss/collision")

            # Test 15: Vary: Accept variants do not collide
            put(
                "GET",
                "https://example.com/vary",
                200,
                {"Content-Type": "application/json", "Vary": "Accept"},
                b'{"fmt":"json"}',
                request_headers={"Accept": "application/json"},
            )
            put(
                "GET",
                "https://example.com/vary",
                200,
                {"Content-Type": "text/html", "Vary": "Accept"},
                b"<html/>",
                request_headers={"Accept": "text/html"},
            )
            vj = get(
                "GET",
                "https://example.com/vary",
                request_headers={"Accept": "application/json"},
            )
            vh = get(
                "GET",
                "https://example.com/vary",
                request_headers={"Accept": "text/html"},
            )
            if not vj or vj.get("body") != b'{"fmt":"json"}':
                errors.append("Vary Accept json collision")
            if not vh or vh.get("body") != b"<html/>":
                errors.append("Vary Accept html collision")

            # Test 16: Vary: * is not cached
            starred = put(
                "GET",
                "https://example.com/star",
                200,
                {"Vary": "*"},
                b"nope",
            )
            if starred is not None:
                errors.append("Vary:* must not be cacheable")

            # Test 17: 100 concurrent writers to same key
            import concurrent.futures
            import traceback

            url_c = "https://example.com/concurrent"
            exceptions: list[str] = []

            def _writer(i: int) -> None:
                try:
                    put(
                        "GET",
                        url_c,
                        200,
                        {"Content-Type": "text/plain"},
                        f"body-{i}".encode("utf-8"),
                    )
                except Exception as exc:  # noqa: BLE001
                    exceptions.append(f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")

            with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
                list(pool.map(_writer, range(100)))
            if exceptions:
                errors.append(
                    f"concurrent writers raised {len(exceptions)} exception(s): "
                    f"{exceptions[0][:200]}"
                )
            final = get("GET", url_c)
            if final is None:
                errors.append("concurrent writers left unreadable cache entry")
            elif not final.get("body_sha256"):
                errors.append("final concurrent entry missing body_sha256")
            elif final.get("body") is None:
                errors.append("final concurrent entry missing body")
            else:
                # body matches declared hash
                if _body_sha256(final["body"]) != final.get("body_sha256"):
                    errors.append("final concurrent entry body/meta hash mismatch")
            # repeated get deterministic
            final2 = get("GET", url_c)
            if final and final2 and final.get("body") != final2.get("body"):
                errors.append("repeated concurrent get not deterministic")

            # Test 18: stats
            ns = argparse.Namespace(cache_path=str(cd))
            rc = cmd_stats(ns)
            if rc != 0:
                errors.append("stats failed")

            # Test 19: purge all
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
