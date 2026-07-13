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
import re
import stat
import sys
import time
from pathlib import Path
from typing import Any

CACHE_ENV = "D_RESEARCH_HTTP_CACHE_PATH"
DEFAULT_MAX_AGE_SECONDS = 7 * 24 * 3600  # 7 days

# Generation ids are uuid4().hex / 16 random bytes as hex (32 lowercase hex).
_GENERATION_ID_RE = re.compile(r"^[0-9a-f]{32}$")

# ---------------------------------------------------------------------------
# Generation lifecycle protocol (Python ↔ Node must match)
# ---------------------------------------------------------------------------
# Writers A and B may both observe old generation O, then:
#   1) each publishes body to a unique {key}.{gen}.body path
#   2) each atomically publishes {key}.json meta pointing at its body
#   3) after meta publish, re-read live meta:
#        - if live generation == ours: we won → delete O and other non-live
#          generation bodies for this key (never delete live body)
#        - if live generation != ours: we lost → delete only our body
#   4) if meta publish fails: delete our temp meta and our body if unreferenced
# Readers must return one consistent generation (meta+body hash/size match)
# or a miss — never mixed generations. Concurrent purge may cause a temporary
# miss; that is acceptable. Never delete a body still referenced by live meta.
# ---------------------------------------------------------------------------

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


def _is_generation_id(value: object) -> bool:
    return isinstance(value, str) and bool(_GENERATION_ID_RE.fullmatch(value))


def _is_unsafe_body_file_name(name: str) -> bool:
    """True when body_file cannot be a safe basenamed generation body."""
    if not name or not isinstance(name, str):
        return True
    # Absolute, drive-relative, UNC, or any directory component.
    if name.startswith(("/", "\\")):
        return True
    if len(name) >= 2 and name[1] == ":":
        return True
    if "\\" in name or "/" in name:
        return True
    if ".." in name:
        return True
    try:
        if Path(name).is_absolute():
            return True
    except (OSError, ValueError):
        return True
    # Must be a single path segment (basename only).
    if Path(name).name != name:
        return True
    return False


def _canonical_generation_body_name(key: str, generation_id: str) -> str:
    return f"{key}.{generation_id}.body"


def _is_canonical_body_file(name: str, key: str, generation_id: object | None) -> bool:
    """Accept only ``<key>.<generation>.body`` under the declared generation."""
    if _is_unsafe_body_file_name(name):
        return False
    if not name.endswith(".body"):
        return False
    prefix = f"{key}."
    if not name.startswith(prefix):
        return False
    gen_part = name[len(prefix) : -len(".body")]
    if not _is_generation_id(gen_part):
        return False
    if generation_id is not None and generation_id != "":
        if not _is_generation_id(generation_id):
            return False
        if gen_part != generation_id:
            return False
    return True


def _path_contained_in_entries(entries: Path, candidate: Path) -> bool:
    """True when resolved *candidate* stays inside resolved *entries*."""
    try:
        entries_r = entries.resolve()
        cand_r = candidate.resolve()
        cand_r.relative_to(entries_r)
        return True
    except (OSError, ValueError):
        return False


def _resolve_body_path(entries: Path, key: str, meta: dict[str, Any]) -> Path | None:
    """Resolve a safe on-disk body path for *meta*, or None (cache miss).

    New-format metadata with ``body_file`` must pass strict filename and
    containment checks. Invalid ``body_file`` is a hard miss — no fallback to
    alternate paths (prevents poisoned-meta path escape).

    Legacy entries without ``body_file`` may use ``{key}.{generation}.body`` or
    ``{key}.body``.
    """
    body_rel = meta.get("body_file")
    gen = meta.get("generation_id")

    if isinstance(body_rel, str) and body_rel:
        # Invalid new-format body_file → miss (do not fall back).
        if not _is_canonical_body_file(body_rel, key, gen):
            return None
        candidate = entries / body_rel
        if not _path_contained_in_entries(entries, candidate):
            return None
        if not candidate.is_file():
            return None
        # Symlink escape: resolve must still be inside entries.
        if not _path_contained_in_entries(entries, candidate):
            return None
        return candidate

    # True legacy metadata (no body_file field).
    if _is_generation_id(gen):
        gen_path = entries / _canonical_generation_body_name(key, str(gen))
        if gen_path.is_file() and _path_contained_in_entries(entries, gen_path):
            return gen_path
    legacy = entries / f"{key}.body"
    if legacy.is_file() and _path_contained_in_entries(entries, legacy):
        return legacy
    return None


def _meta_referenced_body_name(key: str, meta: dict[str, Any]) -> str | None:
    """Return the basenamed body file referenced by *meta*, if determinable."""
    body_rel = meta.get("body_file")
    gen = meta.get("generation_id")
    if isinstance(body_rel, str) and body_rel:
        if _is_canonical_body_file(body_rel, key, gen):
            return body_rel
        return None
    if _is_generation_id(gen):
        return _canonical_generation_body_name(key, str(gen))
    return f"{key}.body"


def _safe_unlink(path: Path, *, attempts: int = 6) -> bool:
    """Unlink with a bounded retry for transient Windows file locks."""
    attempts = max(1, attempts)
    for attempt in range(attempts):
        try:
            path.unlink(missing_ok=True)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            if attempt + 1 < attempts:
                time.sleep(0.01 * (attempt + 1))
    return False


def _gc_unreferenced_bodies_for_key(entries: Path, key: str) -> int:
    """Delete generation/legacy bodies for *key* not referenced by live meta.

    Safe only when no concurrent writers are publishing that key (post-settle
    or purge). Returns number of unlinks attempted.
    """
    live_body, _live_gen = _read_live_body_ref(entries, key)
    removed = 0
    for path in list(entries.glob(f"{key}*.body")):
        # Match {key}.body or {key}.{gen}.body — not unrelated keys that share prefix.
        name = path.name
        if name == f"{key}.body":
            if live_body == name:
                continue
            if _safe_unlink(path):
                removed += 1
            continue
        prefix = f"{key}."
        if not name.startswith(prefix) or not name.endswith(".body"):
            continue
        mid = name[len(prefix) : -len(".body")]
        if not _is_generation_id(mid):
            continue
        if live_body == name:
            continue
        if _safe_unlink(path):
            removed += 1
    return removed


def _read_live_body_ref(entries: Path, key: str) -> tuple[str | None, str | None]:
    """Return (live_body_name, live_generation_id) for *key*, or (None, None)."""
    meta_path = entries / f"{key}.json"
    if not meta_path.is_file():
        return None, None
    try:
        live_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, None
    live_body_name = _meta_referenced_body_name(key, live_meta)
    lg = live_meta.get("generation_id")
    live_gen = str(lg) if _is_generation_id(lg) else None
    return live_body_name, live_gen


def _cleanup_writer_generation(
    entries: Path,
    key: str,
    gen_id: str,
    *,
    published_meta: bool,
    prev_body_name: str | None = None,
) -> None:
    """Apply post-publish / failed-publish generation body cleanup.

    See module protocol comment. Winner only deletes the previously observed
    live body (``prev_body_name``), never every unreferenced generation — that
    would race with in-flight writers that have published a body but not yet
    swapped meta. Loser deletes only its own body when unreferenced. Orphan
    generation bodies are collected by age-based / purge-all GC.
    """
    our_name = _canonical_generation_body_name(key, gen_id)
    our_body = entries / our_name
    live_body_name, live_gen = _read_live_body_ref(entries, key)

    if not published_meta:
        # Meta publish failed: drop our body only if live meta does not ref it.
        if live_body_name != our_name:
            _safe_unlink(our_body)
        return

    if live_gen == gen_id and live_body_name == our_name:
        # We own live meta: delete only the superseded body we observed.
        if (
            prev_body_name
            and prev_body_name != our_name
            and not _is_unsafe_body_file_name(prev_body_name)
        ):
            cur_body, cur_gen = _read_live_body_ref(entries, key)
            if cur_gen == gen_id and cur_body == our_name and cur_body != prev_body_name:
                candidate = entries / prev_body_name
                if _path_contained_in_entries(entries, candidate):
                    _safe_unlink(candidate)
        return

    # We lost the meta race (or meta missing): delete only our unreferenced body.
    live_body_name, _live_gen = _read_live_body_ref(entries, key)
    if live_body_name != our_name:
        _safe_unlink(our_body)


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

    body_path = _resolve_body_path(entries, key, meta)
    if body_path is None:
        return None

    try:
        body_bytes = body_path.read_bytes()
    except OSError:
        return None
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
    # Snapshot the live body we intend to supersede (winner cleanup target only).
    prev_body_name, _prev_gen = _read_live_body_ref(entries, key)
    # Unique temps per writer — never shared .tmp names
    tmp_body = entries / f"{key}.{gen_id}.body.tmp"
    tmp_meta = entries / f"{key}.{gen_id}.json.tmp"
    try:
        tmp_body.write_bytes(body)
        tmp_meta.write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        # 1) Publish body to a unique generation path (no cross-writer collision).
        # 2) Atomically publish meta pointing at that body.
        # 3) Re-read live meta and cleanup: winner deletes prev body only;
        #    loser deletes only its own unreferenced body (see module protocol).
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
                _safe_unlink(p)
            return None
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
            _safe_unlink(tmp_meta)
            # Meta not published: drop our body if not referenced by live meta.
            _cleanup_writer_generation(
                entries,
                key,
                gen_id,
                published_meta=False,
                prev_body_name=prev_body_name,
            )
            return None
        try:
            os.chmod(meta_path, 0o600)
            os.chmod(body_path, 0o600)
        except OSError:
            pass
        _cleanup_writer_generation(
            entries,
            key,
            gen_id,
            published_meta=True,
            prev_body_name=prev_body_name,
        )
    except Exception:
        for p in (tmp_body, tmp_meta):
            _safe_unlink(p)
        # Best-effort: if body was published but meta was not, drop only our
        # unreferenced generation. Existing live metadata may still be present.
        if body_path.is_file():
            _cleanup_writer_generation(
                entries,
                key,
                gen_id,
                published_meta=False,
                prev_body_name=prev_body_name,
            )
        return None
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


def _count_cache_files(entries_dir: Path) -> tuple[int, int, int]:
    """Return (meta_count, body_count, temp_count) excluding nested junk."""
    meta = 0
    body = 0
    temp = 0
    if not entries_dir.is_dir():
        return 0, 0, 0
    for p in entries_dir.iterdir():
        if not p.is_file():
            continue
        name = p.name.lower()
        if name.endswith(".tmp") or ".tmp." in name:
            temp += 1
        elif name.endswith(".json"):
            meta += 1
        elif name.endswith(".body"):
            body += 1
    return meta, body, temp


def _cache_artifact_paths(entries_dir: Path) -> list[Path]:
    """Return one handle-confirmed snapshot of purge-managed artifacts.

    On Windows, a directory enumeration can briefly return a stale,
    case-normalized name after a concurrent rename/unlink. Opening the path
    distinguishes that ghost entry from a real file or a genuinely locked one.
    """
    try:
        entries_mode = entries_dir.stat().st_mode
    except FileNotFoundError:
        return []
    if not stat.S_ISDIR(entries_mode):
        return []
    try:
        candidates = list(entries_dir.iterdir())
    except FileNotFoundError:
        return []
    confirmed: list[Path] = []
    for path in candidates:
        if not path.name.lower().endswith((".body", ".tmp", ".json")):
            continue
        try:
            with path.open("rb"):
                pass
        except FileNotFoundError:
            continue
        except OSError:
            # Permission/sharing failures indicate a real, currently locked
            # artifact that purge must continue to treat as present.
            confirmed.append(path)
        else:
            confirmed.append(path)
    return confirmed


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
    meta_n, body_n, temp_n = _count_cache_files(entries_dir)
    total_size = 0
    for p in entries_dir.iterdir():
        if p.is_file():
            try:
                total_size += p.stat().st_size
            except OSError:
                pass
    print(f"cache_dir: {cd}")
    print(f"entries:   {meta_n}")
    print(f"body_files: {body_n}")
    print(f"temp_files: {temp_n}")
    print(f"size_bytes: {total_size}")
    return 0


def _unlink_meta_and_body(entries_dir: Path, meta_path: Path) -> bool:
    """Parse meta, delete meta + referenced body. Return True if work done."""
    key = meta_path.name[: -len(".json")] if meta_path.name.endswith(".json") else meta_path.stem
    body_name: str | None = None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        body_name = _meta_referenced_body_name(key, meta)
    except (json.JSONDecodeError, OSError):
        body_name = None
    deleted_any = _safe_unlink(meta_path)
    if body_name and not _is_unsafe_body_file_name(body_name):
        candidate = entries_dir / body_name
        if _path_contained_in_entries(entries_dir, candidate):
            deleted_any = _safe_unlink(candidate) or deleted_any
    # Also remove legacy companion if present and distinct.
    legacy = entries_dir / f"{key}.body"
    if legacy.is_file() and (body_name is None or legacy.name != body_name):
        if _path_contained_in_entries(entries_dir, legacy):
            deleted_any = _safe_unlink(legacy) or deleted_any
    return deleted_any


def cmd_purge(args: argparse.Namespace) -> int:
    """Remove expired or all entries, including generation bodies and temps."""
    cd = Path(args.cache_path) if args.cache_path else get_cache_path()
    if cd is None:
        print("error: cache not configured", file=sys.stderr)
        return 1
    entries_dir = cd / "entries"
    try:
        entries_mode = entries_dir.stat().st_mode
    except FileNotFoundError:
        print("nothing to purge")
        return 0
    except OSError as exc:
        print(
            f"error: cannot inspect cache entries for purge: {exc}",
            file=sys.stderr,
        )
        return 1
    if not stat.S_ISDIR(entries_mode):
        print("nothing to purge")
        return 0
    purge_all = args.all
    max_age = args.max_age if args.max_age is not None else DEFAULT_MAX_AGE_SECONDS
    now = time.time()
    purged = 0
    referenced_bodies: set[str] = set()

    try:
        meta_candidates = list(entries_dir.glob("*.json"))
    except OSError as exc:
        print(
            f"error: cannot enumerate cache entries for purge: {exc}",
            file=sys.stderr,
        )
        return 1

    for meta_path in meta_candidates:
        # Skip temp meta names if any match the glob oddly
        if meta_path.name.endswith(".tmp") or ".json.tmp" in meta_path.name:
            continue
        should_purge = purge_all
        meta: dict[str, Any] | None = None
        key = meta_path.name[: -len(".json")]
        if not should_purge:
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                age = now - meta.get("created_at", 0)
                if age > max_age:
                    should_purge = True
            except (json.JSONDecodeError, OSError):
                should_purge = True
        if should_purge:
            if _unlink_meta_and_body(entries_dir, meta_path):
                purged += 1
        else:
            if meta is None:
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    meta = None
            if meta is not None:
                ref = _meta_referenced_body_name(key, meta)
                if ref:
                    referenced_bodies.add(ref.lower())

    if purge_all:
        # Remove every remaining body, orphan, and temp. Retry the bounded
        # sweep because Windows scanners can transiently lock freshly replaced
        # cache files even after their writer has closed them.
        deadline = time.monotonic() + 2.0
        clean_since: float | None = None
        settle_seconds = 0.2
        try:
            while True:
                for path in _cache_artifact_paths(entries_dir):
                    if _safe_unlink(path, attempts=8):
                        purged += 1
                remaining = _cache_artifact_paths(entries_dir)
                observed_at = time.monotonic()
                if not remaining:
                    if clean_since is None:
                        clean_since = observed_at
                    elif observed_at - clean_since >= settle_seconds:
                        break
                else:
                    clean_since = None
                if observed_at >= deadline:
                    break
                time.sleep(0.025)
        except OSError as exc:
            print(
                f"error: cannot enumerate cache entries for purge: {exc}",
                file=sys.stderr,
            )
            return 1
    else:
        # Age-based: collect orphan generation bodies older than max_age.
        # Do not delete fresh in-flight temps/bodies (age <= max_age).
        try:
            age_candidates = list(entries_dir.iterdir())
        except OSError as exc:
            print(
                f"error: cannot enumerate cache entries for purge: {exc}",
                file=sys.stderr,
            )
            return 1
        for path in age_candidates:
            if not path.is_file():
                continue
            name = path.name
            lower_name = name.lower()
            try:
                age = now - path.stat().st_mtime
            except OSError:
                continue
            if lower_name.endswith(".tmp"):
                if age > max_age:
                    if _safe_unlink(path):
                        purged += 1
                continue
            if not lower_name.endswith(".body"):
                continue
            if lower_name in referenced_bodies:
                continue
            if age > max_age:
                if _safe_unlink(path):
                    purged += 1

    # A successful purge is a strict postcondition: no handle-confirmed cache
    # artifact remains. Directory-only tombstones are filtered by
    # _cache_artifact_paths(), but a locked temp is real state and must fail
    # closed instead of being downgraded to a warning.
    if purge_all:
        try:
            remaining = sorted(path.name for path in _cache_artifact_paths(entries_dir))
        except OSError as exc:
            print(
                f"error: cannot enumerate cache entries for purge: {exc}",
                file=sys.stderr,
            )
            return 1
        if remaining:
            lower_names = [name.lower() for name in remaining]
            _m = sum(name.endswith(".json") for name in lower_names)
            bodies_left = sum(name.endswith(".body") for name in lower_names)
            temps_left = sum(name.endswith(".tmp") for name in lower_names)
            print(
                "error: purge --all incomplete "
                f"(meta={_m} body={bodies_left} temp={temps_left} "
                f"remaining={remaining})",
                file=sys.stderr,
            )
            return 1

    print(f"purged {purged} entries from {cd}")
    return 0


def cmd_self_test(_args: argparse.Namespace) -> int:
    """Offline self-test with temp directory."""
    import tempfile

    errors: list[str] = []
    saved_env = os.environ.pop(CACHE_ENV, None)

    try:
        # Windows indexers can briefly retain handles after the assertions have
        # already verified that cache files were purged correctly.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
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

            # Atomic publish failures report failure and leave no readable hit.
            original_replace = os.replace
            original_sleep = time.sleep
            time.sleep = lambda _seconds: None
            try:
                body_fail_url = "https://example.com/atomic-body-fail"

                def _fail_all_replaces(_src: str, _dst: str) -> None:
                    raise OSError("simulated body publish failure")

                os.replace = _fail_all_replaces
                body_fail_result = put(
                    "GET", body_fail_url, 200, {}, b"must-not-publish"
                )
                if body_fail_result is not None:
                    errors.append("body publish failure must return None")
                if get("GET", body_fail_url) is not None:
                    errors.append("body publish failure must not create a cache hit")

                meta_fail_url = "https://example.com/atomic-meta-fail"

                def _fail_meta_replace(src: str, dst: str) -> None:
                    if str(src).endswith(".json.tmp"):
                        raise OSError("simulated metadata publish failure")
                    original_replace(src, dst)

                os.replace = _fail_meta_replace
                meta_fail_result = put(
                    "GET", meta_fail_url, 200, {}, b"must-not-publish"
                )
                if meta_fail_result is not None:
                    errors.append("metadata publish failure must return None")
                if get("GET", meta_fail_url) is not None:
                    errors.append("metadata publish failure must not create a cache hit")
                meta_fail_key = cache_key("GET", meta_fail_url)
                leaked = list((cd / "entries").glob(f"{meta_fail_key}*"))
                if leaked:
                    errors.append(
                        "metadata publish failure left cache artifacts: "
                        + ", ".join(path.name for path in leaked)
                    )
            finally:
                os.replace = original_replace
                time.sleep = original_sleep

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
            # Post-settle GC for this key (no writers active).
            _gc_unreferenced_bodies_for_key(cd / "entries", cache_key("GET", url_c))
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

            # Test 19: sequential overwrites leave one referenced body
            url5 = "https://example.com/five-overwrites"
            for i in range(5):
                put(
                    "GET",
                    url5,
                    200,
                    {"Content-Type": "text/plain"},
                    f"gen-body-{i}".encode("utf-8"),
                )
            hit5 = get("GET", url5)
            if not hit5 or hit5.get("body") != b"gen-body-4":
                errors.append("5 overwrites should hit latest generation body")
            entries_dir = cd / "entries"
            key5 = cache_key("GET", url5)
            metas5 = list(entries_dir.glob(f"{key5}.json"))
            bodies5 = list(entries_dir.glob(f"{key5}*.body"))
            temps5 = [
                p
                for p in entries_dir.iterdir()
                if p.is_file() and p.name.startswith(key5) and p.name.endswith(".tmp")
            ]
            if len(metas5) != 1 or len(bodies5) != 1 or temps5:
                errors.append(
                    f"after 5 overwrites expected meta=1 body=1 temp=0, "
                    f"got meta={len(metas5)} body={len(bodies5)} temp={len(temps5)}"
                )

            # Test 20: F-08 body_file containment — absolute / traversal / bad gen
            secret_path = Path(tmpdir) / "outside-secret.txt"
            secret_bytes = b"TOPSECRET-OUTSIDE-BYTES"
            secret_path.write_bytes(secret_bytes)
            poison_url = "https://example.com/poison"
            poison_key = put("GET", poison_url, 200, {}, b"legit-inside")
            poison_meta_path = entries_dir / f"{poison_key}.json"
            poison_meta = json.loads(poison_meta_path.read_text(encoding="utf-8"))

            def _poison_and_get(body_file_val: str, body: bytes) -> dict[str, Any] | None:
                m = dict(poison_meta)
                m["body_file"] = body_file_val
                m["body_sha256"] = _body_sha256(body)
                m["body_size"] = len(body)
                poison_meta_path.write_text(json.dumps(m), encoding="utf-8")
                return get("GET", poison_url)

            abs_hit = _poison_and_get(str(secret_path), secret_bytes)
            if abs_hit is not None:
                errors.append("absolute body_file must miss (F-08)")
            if abs_hit and abs_hit.get("body") == secret_bytes:
                errors.append("poisoned absolute body_file leaked outside bytes")

            (cd / "secret2.txt").write_bytes(b"TRAVERSAL")
            trav_hit = _poison_and_get("../secret2.txt", b"TRAVERSAL")
            if trav_hit is not None:
                errors.append("traversal body_file must miss")

            nested_hit = _poison_and_get("subdir/file.body", b"NESTED")
            if nested_hit is not None:
                errors.append("nested body_file must miss")

            win_hit = _poison_and_get(r"C:\Windows\win.ini", b"WIN")
            if win_hit is not None:
                errors.append("Windows drive body_file must miss")

            unc_hit = _poison_and_get(r"\\server\share\x.body", b"UNC")
            if unc_hit is not None:
                errors.append("UNC body_file must miss")

            wrong_key = _poison_and_get(
                f"{'0' * 64}.{poison_meta.get('generation_id')}.body",
                b"WRONGKEY",
            )
            if wrong_key is not None:
                errors.append("wrong key prefix body_file must miss")

            wrong_gen = _poison_and_get(
                f"{poison_key}.{'a' * 32}.body",
                b"WRONGGEN",
            )
            if wrong_gen is not None:
                errors.append("wrong generation body_file must miss")

            # Canonical generation body still hits
            poison_meta_path.write_text(json.dumps(poison_meta), encoding="utf-8")
            canon_hit = get("GET", poison_url)
            if not canon_hit or canon_hit.get("body") != b"legit-inside":
                errors.append("canonical generation body must hit")

            # Legacy body without body_file
            legacy_key = cache_key("GET", "https://example.com/legacy")
            legacy_meta = {
                "key": legacy_key,
                "url": "https://example.com/legacy",
                "method": "GET",
                "status": 200,
                "headers": {},
                "created_at": int(time.time()),
                "body_sha256": _body_sha256(b"legacy-body"),
                "body_size": len(b"legacy-body"),
            }
            (entries_dir / f"{legacy_key}.json").write_text(
                json.dumps(legacy_meta), encoding="utf-8"
            )
            (entries_dir / f"{legacy_key}.body").write_bytes(b"legacy-body")
            leg_hit = get("GET", "https://example.com/legacy")
            if not leg_hit or leg_hit.get("body") != b"legacy-body":
                errors.append("legacy cache without body_file must hit")

            # Symlink escape (POSIX / Windows reparse when supported)
            try:
                outside_link_target = Path(tmpdir) / "symlink-target.txt"
                outside_link_target.write_bytes(b"SYMLINK-SECRET")
                link_name = f"{poison_key}.{'b' * 32}.body"
                link_path = entries_dir / link_name
                if link_path.exists():
                    link_path.unlink()
                link_path.symlink_to(outside_link_target)
                m = dict(poison_meta)
                m["body_file"] = link_name
                m["generation_id"] = "b" * 32
                m["body_sha256"] = _body_sha256(b"SYMLINK-SECRET")
                m["body_size"] = len(b"SYMLINK-SECRET")
                poison_meta_path.write_text(json.dumps(m), encoding="utf-8")
                sym_hit = get("GET", poison_url)
                if sym_hit is not None and sym_hit.get("body") == b"SYMLINK-SECRET":
                    errors.append("symlink escape body_file must miss")
            except (OSError, NotImplementedError):
                pass  # platform may disallow symlinks without elevation

            # Corrupt meta does not crash
            bad_key = cache_key("GET", "https://example.com/corrupt")
            (entries_dir / f"{bad_key}.json").write_text("{not-json", encoding="utf-8")
            if get("GET", "https://example.com/corrupt") is not None:
                errors.append("corrupt meta must miss without crash")

            # Missing body → miss
            miss_body_url = "https://example.com/missing-body"
            mk = put("GET", miss_body_url, 200, {}, b"will-delete")
            for bp in entries_dir.glob(f"{mk}*.body"):
                bp.unlink(missing_ok=True)
            if get("GET", miss_body_url) is not None:
                errors.append("missing body must miss")

            # Hash mismatch → miss
            hm_url = "https://example.com/hash-mismatch"
            hk = put("GET", hm_url, 200, {}, b"original")
            for bp in entries_dir.glob(f"{hk}*.body"):
                bp.write_bytes(b"tampered-content!!")
            if get("GET", hm_url) is not None:
                errors.append("body hash mismatch must miss")

            # Test 21: age-based purge removes generation body
            aged_url = "https://example.com/aged"
            ak = put("GET", aged_url, 200, {}, b"old-entry")
            ameta = entries_dir / f"{ak}.json"
            data = json.loads(ameta.read_text(encoding="utf-8"))
            data["created_at"] = int(time.time()) - 10_000
            ameta.write_text(json.dumps(data), encoding="utf-8")
            # also age the body mtime for orphan GC path coverage
            for bp in entries_dir.glob(f"{ak}*.body"):
                os.utime(bp, (time.time() - 10_000, time.time() - 10_000))
            ns_age = argparse.Namespace(cache_path=str(cd), all=False, max_age=60)
            rc_age = cmd_purge(ns_age)
            if rc_age != 0:
                errors.append("age-based purge failed")
            if get("GET", aged_url) is not None:
                errors.append("aged entry should be purged")
            aged_bodies = list(entries_dir.glob(f"{ak}*.body"))
            if aged_bodies:
                errors.append("age-based purge must remove generation body")

            # Test 22: purge all clears meta/body/temp
            (entries_dir / "UPPER.BODY.TMP").write_text("orphan", encoding="utf-8")
            ns = argparse.Namespace(cache_path=str(cd), all=True, max_age=None)
            rc = cmd_purge(ns)
            if rc != 0:
                errors.append("purge failed")
            result = get("GET", "https://example.com/api")
            if result is not None:
                errors.append("entry still exists after purge --all")

            # A directory enumeration tombstone is not a real cache artifact.
            # Reproduce it deterministically with a missing path returned by
            # iterdir(); handle confirmation must discard it.
            from unittest import mock
            from contextlib import redirect_stderr, redirect_stdout
            from io import StringIO

            stat_failed_closed = False
            with mock.patch.object(
                Path,
                "stat",
                side_effect=PermissionError("simulated stat denial"),
            ):
                try:
                    _cache_artifact_paths(entries_dir)
                except PermissionError:
                    stat_failed_closed = True
            if not stat_failed_closed:
                errors.append("cache artifact stat failure must propagate")

            ghost = entries_dir / ("A" * 64 + "." + "B" * 32 + ".BODY.tmp")
            with mock.patch.object(Path, "iterdir", return_value=iter([ghost])):
                if _cache_artifact_paths(entries_dir):
                    errors.append("missing directory tombstone must not count as artifact")

            glob_output = StringIO()
            with (
                mock.patch.object(
                    Path,
                    "glob",
                    side_effect=PermissionError("simulated metadata enumeration denial"),
                ),
                redirect_stdout(glob_output),
                redirect_stderr(glob_output),
            ):
                glob_rc = cmd_purge(ns)
            if glob_rc == 0:
                errors.append("metadata enumeration failure must fail purge --all")
            if "cannot enumerate cache entries for purge" not in glob_output.getvalue():
                errors.append("metadata enumeration failure must be reported")

            # An enumeration failure is not an empty cache. Purge must report a
            # structured failure instead of converting PermissionError/OSError
            # to a successful empty snapshot.
            enumeration_output = StringIO()
            with (
                mock.patch.object(
                    Path,
                    "iterdir",
                    side_effect=PermissionError("simulated enumeration denial"),
                ),
                redirect_stdout(enumeration_output),
                redirect_stderr(enumeration_output),
            ):
                enumeration_rc = cmd_purge(ns)
            if enumeration_rc == 0:
                errors.append("cache enumeration failure must fail purge --all")
            if "cannot enumerate cache entries for purge" not in enumeration_output.getvalue():
                errors.append("cache enumeration failure must be reported")

            # Conversely, a handle-confirmed temp that cannot be removed is a
            # strict purge failure. Patch only I/O/timing so this regression is
            # deterministic and does not depend on obtaining an OS file lock.
            locked_cd = Path(tmpdir) / "locked-cache"
            locked_entries = locked_cd / "entries"
            locked_entries.mkdir(parents=True)
            locked_temp = locked_entries / ("c" * 64 + "." + "d" * 32 + ".body.tmp")
            locked_temp.write_bytes(b"locked")
            locked_ns = argparse.Namespace(
                cache_path=str(locked_cd), all=True, max_age=None
            )
            locked_output = StringIO()
            module = sys.modules[__name__]
            with (
                mock.patch.object(module, "_safe_unlink", return_value=False),
                mock.patch.object(time, "monotonic", side_effect=[0.0, 3.0]),
                mock.patch.object(time, "sleep", return_value=None),
                redirect_stdout(locked_output),
                redirect_stderr(locked_output),
            ):
                locked_rc = cmd_purge(locked_ns)
            if locked_rc == 0:
                errors.append("handle-confirmed locked temp must fail purge --all")
            if "temp=1" not in locked_output.getvalue():
                errors.append("locked temp purge failure must report temp count")
            locked_temp.unlink(missing_ok=True)

            # Re-check concurrent writers still valid after cleanup changes
            url_c2 = "https://example.com/concurrent2"
            exceptions2: list[str] = []

            def _writer2(i: int) -> None:
                try:
                    put(
                        "GET",
                        url_c2,
                        200,
                        {"Content-Type": "text/plain"},
                        f"c2-{i}".encode("utf-8"),
                    )
                except Exception as exc:  # noqa: BLE001
                    exceptions2.append(f"{type(exc).__name__}: {exc}")

            with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
                list(pool.map(_writer2, range(100)))
            if exceptions2:
                errors.append(f"concurrent2 raised: {exceptions2[0]}")
            ck = cache_key("GET", url_c2)
            _gc_unreferenced_bodies_for_key(entries_dir, ck)
            final_c2 = get("GET", url_c2)
            if final_c2 is None:
                errors.append("concurrent2 final miss")
            elif _body_sha256(final_c2["body"]) != final_c2.get("body_sha256"):
                errors.append("concurrent2 hash mismatch")
            else:
                orphan_n = len(list(entries_dir.glob(f"{ck}*.body")))
                if orphan_n != 1:
                    errors.append(
                        f"after concurrent settle expected 1 body, got {orphan_n}"
                    )

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
