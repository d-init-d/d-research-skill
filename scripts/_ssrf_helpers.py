#!/usr/bin/env python3
"""SSRF guards for social_snapshot and other outbound URL fetches.

Stdlib-only. Used by social_snapshot.py.

Guarantees:
- HTTPS only by default (HTTP only when allow_http=True)
- No userinfo in URLs
- Blocked hostnames (localhost, cloud metadata names)
- Non-public IPv4/IPv6 literals and DNS resolutions rejected
- IPv4-mapped IPv6 (::ffff:x.x.x.x) evaluated via the embedded IPv4 address
- Optional DNS-pinned HTTPS open to reduce resolve-then-connect TOCTOU
- Production pinned open streams the HTTP body (never buffers unbounded)
"""
from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata",
    "instance-data",
}

# Injectable for offline self-tests (social_snapshot monkey-patches this).
_TEST_URLOPEN: Any = None

# Optional injectable transport for unit-testing the production pinned path
# without a live network. Signature:
#   factory(host, port, timeout, context, method, path, body, headers, ip)
# must return (http.client.HTTPResponse-like, connection-like) or raise.
_TEST_PINNED_TRANSPORT: Any = None

REDIRECT_STATUSES = {301, 302, 303, 307, 308}
DEFAULT_MAX_REDIRECTS = 5
PUBLIC_REDIRECT_HEADERS = {
    "accept",
    "accept-encoding",
    "accept-language",
    "cache-control",
    "content-type",
    "if-modified-since",
    "if-none-match",
    "pragma",
    "user-agent",
}
SECRET_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "client_secret",
    "credential",
    "key",
    "password",
    "refresh_token",
    "secret",
    "token",
}


class RedirectPolicyError(urllib.error.URLError):
    """Raised when a redirect cannot preserve network or credential policy."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def _is_non_public_ip(ip: ipaddress._BaseAddress) -> bool:
    """Return True when *ip* must not be contacted by public research helpers.

    IPv4-mapped IPv6 addresses are evaluated against the embedded IPv4
    address so ::ffff:127.0.0.1 / ::ffff:169.254.169.254 cannot slip through
    platform differences in IPv6 property flags.
    """
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    flags = (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )
    # is_site_local exists on some Python builds for IPv6 only
    flags = flags or bool(getattr(ip, "is_site_local", False))
    # Prefer is_global when available; treat unknown/false as non-public.
    is_global = getattr(ip, "is_global", None)
    if is_global is False:
        flags = True
    return bool(flags)


def _normalize_ip_for_comparison(value: str) -> str:
    """Return a canonical IP string, unwrapping IPv4-mapped IPv6 values."""
    raw = str(value).strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    # Peer strings may carry an IPv6 scope identifier. Public destinations do
    # not need one, but removing it keeps comparison deterministic.
    if ":" in raw and "%" in raw:
        raw = raw.split("%", 1)[0]
    parsed = ipaddress.ip_address(raw)
    mapped = getattr(parsed, "ipv4_mapped", None)
    return str(mapped if mapped is not None else parsed)


def _peer_matches_validated_ips(peer: str, validated_ips: list[str]) -> bool:
    """Return whether the connected peer belongs to the DNS-validated set."""
    try:
        normalized_peer = _normalize_ip_for_comparison(peer)
        normalized_validated = {
            _normalize_ip_for_comparison(value) for value in validated_ips
        }
    except ValueError:
        return False
    return normalized_peer in normalized_validated


def resolve_public_ips(host: str) -> list[str]:
    """Resolve *host* and return only public addresses.

    Raises ValueError if any resolved address is non-public or resolution fails.
    """
    host_l = host.lower().rstrip(".")
    if host_l in BLOCKED_HOSTNAMES or host_l.endswith(".localhost"):
        raise ValueError(f"blocked hostname: {host_l}")
    try:
        literal = ipaddress.ip_address(host_l)
        if _is_non_public_ip(literal):
            raise ValueError(f"non-public IP not allowed: {host_l}")
        return [host_l]
    except ValueError as exc:
        if "non-public" in str(exc) or "not allowed" in str(exc) or "blocked" in str(exc):
            raise
        # not an IP literal — resolve DNS
    try:
        infos = socket.getaddrinfo(host_l, None)
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failed for {host_l}") from exc
    if not infos:
        raise ValueError(f"DNS returned no addresses for {host_l}")
    addrs: list[str] = []
    seen: set[str] = set()
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if _is_non_public_ip(ip):
            raise ValueError(f"host resolves to non-public address: {addr}")
        if addr not in seen:
            seen.add(addr)
            addrs.append(addr)
    if not addrs:
        raise ValueError(f"DNS returned no usable addresses for {host_l}")
    return addrs


def assert_public_http_url(url: str, *, allow_http: bool = False) -> str:
    """Validate URL is public HTTP(S) before any network I/O.

    Raises ValueError on rejection.
    Returns normalized URL string.
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL is required")
    parsed = urllib.parse.urlparse(url.strip())
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("https",) and not (allow_http and scheme == "http"):
        raise ValueError(f"scheme not allowed: {scheme!r}")
    if parsed.username or parsed.password:
        raise ValueError("URL userinfo is not allowed")
    host = parsed.hostname
    if not host:
        raise ValueError("URL host is required")
    # Resolve and reject non-public destinations (literals and DNS).
    resolve_public_ips(host)
    return url.strip()


class _StreamingPinnedResponse:
    """Streaming file-like wrapper over http.client.HTTPResponse.

    Does **not** buffer the network body. Callers (e.g. read_bounded) must
    pass a positive size to ``read(n)``. Unbounded ``read()`` is rejected so
    resource caps cannot be bypassed by an accidental full-socket drain.

    Owns the HTTP connection / TLS socket and closes them on ``close()`` /
    context-manager exit (success, cap, parse error, or other exception).
    """

    def __init__(
        self,
        resp: Any,
        conn: Any,
        url: str,
        status: int,
        headers: Any,
        reason: str = "",
    ) -> None:
        self._resp = resp
        self._conn = conn
        self.status = status
        self.headers = headers
        self.url = url
        self.reason = reason or ""
        self._closed = False
        self.bytes_read = 0
        self.read_call_sizes: list[int | None] = []

    def read(self, n: int | None = None) -> bytes:
        if self._closed:
            return b""
        self.read_call_sizes.append(n)
        if n is None:
            raise ValueError(
                "unbounded response read is not allowed; pass a positive size"
            )
        if not isinstance(n, int) or isinstance(n, bool) or n < 0:
            raise ValueError(f"invalid read size: {n!r}")
        if n == 0:
            return b""
        if self._resp is None:
            return b""
        chunk = self._resp.read(n)
        if chunk:
            self.bytes_read += len(chunk)
        return chunk

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        resp = self._resp
        conn = self._conn
        self._resp = None
        self._conn = None
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def __enter__(self) -> "_StreamingPinnedResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


# Back-compat alias used by older tests / docs.
_PinnedHTTPResponse = _StreamingPinnedResponse


def _pinned_https_open(req: urllib.request.Request, timeout: float | None) -> _StreamingPinnedResponse:
    """Connect to a DNS-validated public IP with original Host/SNI.

    Re-checks the peer address after connect to shrink DNS-rebinding TOCTOU.
    Returns a streaming response; never buffers the full body into memory.
    """
    url = req.full_url
    parsed = urllib.parse.urlparse(url)
    if (parsed.scheme or "").lower() != "https":
        raise ValueError(f"scheme not allowed for pinned open: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise ValueError("URL host is required")
    port = parsed.port or 443
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    ips = resolve_public_ips(host)
    headers = {k: v for k, v in req.header_items()}
    if not any(k.lower() == "host" for k in headers):
        headers["Host"] = host if parsed.port is None else f"{host}:{parsed.port}"
    method = getattr(req, "get_method", lambda: "GET")()
    body = req.data
    last_error: Exception | None = None
    context = ssl.create_default_context()
    for ip in ips:
        sock: socket.socket | None = None
        ssock: ssl.SSLSocket | None = None
        conn: http.client.HTTPSConnection | None = None
        try:
            if _TEST_PINNED_TRANSPORT is not None:
                resp, conn = _TEST_PINNED_TRANSPORT(
                    host=host,
                    port=port,
                    timeout=timeout,
                    context=context,
                    method=method,
                    path=path,
                    body=body,
                    headers=headers,
                    ip=ip,
                )
            else:
                sock = socket.create_connection((ip, port), timeout=timeout)
                peer_ip = sock.getpeername()[0]
                normalized_peer = _normalize_ip_for_comparison(peer_ip)
                if _is_non_public_ip(ipaddress.ip_address(normalized_peer)):
                    raise ValueError(f"peer address is non-public: {peer_ip}")
                if not _peer_matches_validated_ips(peer_ip, ips):
                    raise ValueError(
                        "peer address mismatch: connected peer is not in the "
                        "DNS-validated address set"
                    )
                ssock = context.wrap_socket(sock, server_hostname=host)
                sock = None  # ownership transferred
                conn = http.client.HTTPSConnection(
                    host, port, timeout=timeout, context=context
                )
                conn.sock = ssock
                ssock = None  # ownership transferred to conn
                conn.request(method, path, body=body, headers=headers)
                resp = conn.getresponse()
            status = int(resp.status)
            response_headers = resp.msg
            reason = getattr(resp, "reason", "") or f"HTTP {status}"
            # Transfer connection ownership to the streaming wrapper so the
            # finally block does not close sockets while the caller reads.
            stream = _StreamingPinnedResponse(
                resp, conn, url, status, response_headers, reason
            )
            conn = None
            if status >= 400:
                # Do not pre-buffer error bodies. HTTPError owns the stream fp;
                # callers that only need status should close it.
                raise urllib.error.HTTPError(
                    url,
                    status,
                    reason,
                    response_headers,
                    stream,
                )
            return stream
        except urllib.error.HTTPError:
            # Do not retry alternate IPs for application-level HTTP errors.
            raise
        except (OSError, ssl.SSLError, ValueError, http.client.HTTPException) as exc:
            last_error = exc
            continue
        finally:
            if conn is not None:
                try:
                    conn.close()
                except OSError:
                    pass
            if ssock is not None:
                try:
                    ssock.close()
                except OSError:
                    pass
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
    if last_error is not None:
        raise last_error
    raise OSError(f"could not connect to any validated address for {host}")


def public_urlopen(req: urllib.request.Request, timeout: float | None = None):
    """Open *req* after SSRF validation, preferring DNS-pinned HTTPS.

    Offline tests may inject a replacement via ``_TEST_URLOPEN``.
    When ``urllib.request.urlopen`` has been monkey-patched (legacy
    social_snapshot self-test path), honour that mock after validation.
    """
    url = req.full_url if hasattr(req, "full_url") else str(req)
    assert_public_http_url(url)
    if _TEST_URLOPEN is not None:
        return _TEST_URLOPEN(req, timeout=timeout)
    # Legacy self-test path: social_snapshot replaces urllib.request.urlopen
    # with a plain function. Prefer the mock so offline tests stay hermetic.
    current = urllib.request.urlopen
    if getattr(current, "__module__", "") != "urllib.request":
        return current(req, timeout=timeout)
    return _pinned_https_open(req, timeout)


def _url_origin(url: str) -> tuple[str, str, int]:
    parsed = urllib.parse.urlsplit(url)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        raise RedirectPolicyError("redirect URL host is required")
    try:
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError as exc:
        raise RedirectPolicyError("redirect URL port is invalid") from exc
    return scheme, host, port


def _url_has_credentials(url: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.username or parsed.password:
            return True
        return any(
            key.lower() in SECRET_QUERY_KEYS
            for key, _value in urllib.parse.parse_qsl(
                parsed.query,
                keep_blank_values=True,
            )
        )
    except ValueError:
        return True


def _request_has_private_material(req: urllib.request.Request) -> bool:
    if req.data is not None or _url_has_credentials(req.full_url):
        return True
    return any(
        name.lower() not in PUBLIC_REDIRECT_HEADERS
        for name, _value in req.header_items()
    )


def _validate_redirect_target(
    value: str,
    current_url: str,
    *,
    allow_loopback_fixture: bool,
) -> str:
    try:
        target = urllib.parse.urljoin(current_url, value)
        parsed = urllib.parse.urlsplit(target)
        if parsed.scheme.lower() not in {"http", "https"}:
            raise ValueError(f"scheme not allowed: {parsed.scheme!r}")
        if parsed.username or parsed.password:
            raise ValueError("URL userinfo is not allowed")
        if not parsed.hostname:
            raise ValueError("URL host is required")
        current_scheme = urllib.parse.urlsplit(current_url).scheme.lower()
        if current_scheme == "https" and parsed.scheme.lower() != "https":
            raise ValueError("HTTPS redirect downgrade blocked")
        if not allow_loopback_fixture:
            assert_public_http_url(target, allow_http=False)
        return target
    except ValueError as exc:
        raise RedirectPolicyError(f"redirect target rejected: {exc}") from exc


def _open_without_redirect(
    req: urllib.request.Request,
    *,
    timeout: float | None,
    allow_loopback_fixture: bool,
) -> Any:
    if not allow_loopback_fixture:
        return public_urlopen(req, timeout=timeout)
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        return opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code in REDIRECT_STATUSES:
            return exc
        raise


def public_urlopen_with_redirects(
    req: urllib.request.Request,
    timeout: float | None = None,
    *,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    allow_loopback_fixture: bool = False,
) -> Any:
    """Open with bounded redirects and same-origin-only private material.

    Production hops are individually SSRF-validated and use the DNS-pinned
    transport. Cross-origin redirects are allowed only for public GET/HEAD
    requests, with non-public headers stripped. Credential headers, secret
    query values, and request bodies never cross an origin boundary.

    ``allow_loopback_fixture`` exists only for deterministic offline tests.
    """
    if not isinstance(max_redirects, int) or isinstance(max_redirects, bool):
        raise ValueError("max_redirects must be a non-negative integer")
    if max_redirects < 0:
        raise ValueError("max_redirects must be a non-negative integer")

    current = req
    request_is_private = _request_has_private_material(req)
    for hop in range(max_redirects + 1):
        response = _open_without_redirect(
            current,
            timeout=timeout,
            allow_loopback_fixture=allow_loopback_fixture,
        )
        status = int(getattr(response, "status", getattr(response, "code", 0)) or 0)
        if status not in REDIRECT_STATUSES:
            return response

        location = response.headers.get("Location") if response.headers else None
        response.close()
        if not location:
            raise RedirectPolicyError("redirect response omitted Location")
        if hop >= max_redirects:
            raise RedirectPolicyError(f"too many redirects (>{max_redirects})")

        target = _validate_redirect_target(
            location,
            current.full_url,
            allow_loopback_fixture=allow_loopback_fixture,
        )
        cross_origin = _url_origin(current.full_url) != _url_origin(target)
        target_is_private = _url_has_credentials(target)
        if cross_origin and (request_is_private or target_is_private):
            raise RedirectPolicyError(
                "credentialed or body-bearing cross-origin redirect blocked"
            )

        headers = dict(current.header_items())
        if cross_origin:
            headers = {
                name: value
                for name, value in headers.items()
                if name.lower() in PUBLIC_REDIRECT_HEADERS
            }
        method = current.get_method()
        data = current.data
        if status == 303 or (status in {301, 302} and method not in {"GET", "HEAD"}):
            method = "GET"
            data = None
            headers = {
                name: value
                for name, value in headers.items()
                if name.lower() not in {"content-length", "content-type"}
            }
        current = urllib.request.Request(
            target,
            data=data,
            headers=headers,
            method=method,
        )
        request_is_private = request_is_private or target_is_private
    raise RedirectPolicyError(f"too many redirects (>{max_redirects})")


def self_test() -> int:
    """Offline unit tests for SSRF helpers."""
    import io
    import sys

    errors: list[str] = []

    private_urls = [
        "http://127.0.0.1/x",
        "https://127.0.0.1/x",
        "https://localhost/x",
        "https://169.254.169.254/latest/meta-data/",
        "https://192.168.1.10/x",
        "https://[::1]/x",
        "https://[::ffff:127.0.0.1]/x",
        "https://[::ffff:169.254.169.254]/latest/",
        "https://[::ffff:10.0.0.1]/x",
        "https://user:pass@example.com/x",
        "ftp://example.com/x",
    ]
    for bad in private_urls:
        try:
            assert_public_http_url(bad, allow_http=bad.startswith("http://"))
            errors.append(f"should reject {bad}")
        except ValueError:
            pass

    # Public IPv4-mapped should be allowed at the URL layer (no DNS needed).
    try:
        assert_public_http_url("https://[::ffff:8.8.8.8]/")
    except ValueError as exc:
        errors.append(f"public IPv4-mapped should be allowed: {exc}")

    # Unwrapped classification
    for raw, expect_block in (
        ("::ffff:127.0.0.1", True),
        ("::ffff:169.254.169.254", True),
        ("::ffff:10.1.2.3", True),
        ("8.8.8.8", False),
        ("::ffff:8.8.8.8", False),
    ):
        ip = ipaddress.ip_address(raw)
        blocked = _is_non_public_ip(ip)
        if blocked != expect_block:
            errors.append(f"_is_non_public_ip({raw})={blocked}, expected {expect_block}")

    # Connected peers must match the DNS-validated set after canonical IP and
    # IPv4-mapped IPv6 normalization. This is hermetic: no socket is opened.
    for peer, validated, expected in (
        ("8.8.8.8", ["8.8.8.8"], True),
        ("::ffff:8.8.8.8", ["8.8.8.8"], True),
        ("8.8.8.8", ["::ffff:8.8.8.8"], True),
        (
            "2001:4860:4860:0:0:0:0:8888",
            ["2001:4860:4860::8888"],
            True,
        ),
        ("8.8.4.4", ["8.8.8.8"], False),
        ("not-an-ip", ["8.8.8.8"], False),
    ):
        matched = _peer_matches_validated_ips(peer, validated)
        if matched != expected:
            errors.append(
                "peer membership mismatch: "
                f"peer={peer} validated={validated} got={matched} expected={expected}"
            )

    # --- F-06: streaming wrapper never allows size-less network reads --------
    class _FakeNetResp:
        def __init__(self, payload: bytes, status: int = 200, headers: dict | None = None):
            self.status = status
            self.reason = "OK" if status < 400 else "ERR"
            self.msg = headers or {}
            self._buf = io.BytesIO(payload)
            self.read_sizes: list[int | None] = []
            self.closed = False

        def read(self, n: int | None = None) -> bytes:
            self.read_sizes.append(n)
            if n is None:
                raise AssertionError("production must not call network read() without size")
            return self._buf.read(n)

        def close(self) -> None:
            self.closed = True

    class _FakeConn:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    # Unbounded read rejected on wrapper
    net = _FakeNetResp(b"abcdefghij")
    conn = _FakeConn()
    wrap = _StreamingPinnedResponse(net, conn, "https://example.com/x", 200, net.msg)
    try:
        wrap.read()
        errors.append("streaming wrapper must reject size-less read()")
    except ValueError:
        pass
    if None in net.read_sizes:
        errors.append("network read() must not be called without size")

    # Bounded reads work; close on context exit
    net2 = _FakeNetResp(b"abcdefghij")
    conn2 = _FakeConn()
    with _StreamingPinnedResponse(net2, conn2, "https://example.com/x", 200, net2.msg) as w2:
        chunk = w2.read(4)
        if chunk != b"abcd":
            errors.append(f"bounded read wrong: {chunk!r}")
    if not net2.closed or not conn2.closed:
        errors.append("wrapper must close HTTPResponse and connection on exit")

    # Close on exception path
    net3 = _FakeNetResp(b"xyz")
    conn3 = _FakeConn()
    try:
        with _StreamingPinnedResponse(net3, conn3, "https://example.com/x", 200, net3.msg) as w3:
            w3.read(1)
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    if not net3.closed or not conn3.closed:
        errors.append("wrapper must close on exception exit")

    # Production pinned path via _TEST_PINNED_TRANSPORT: Content-Length > cap
    # is visible before any body byte is read (caller checks headers first).
    global _TEST_PINNED_TRANSPORT  # noqa: PLW0603
    saved_transport = _TEST_PINNED_TRANSPORT
    try:
        oversized = b"X" * 100

        def _transport_oversize_cl(**_kw: Any):
            headers = {"Content-Length": "100"}
            return _FakeNetResp(oversized, status=200, headers=headers), _FakeConn()

        _TEST_PINNED_TRANSPORT = _transport_oversize_cl
        # Bypass DNS by using a public IP literal host
        req = urllib.request.Request("https://8.8.8.8/x")
        # resolve_public_ips will accept 8.8.8.8
        stream = _pinned_https_open(req, timeout=1.0)
        cl = int(stream.headers.get("Content-Length", "0"))
        body_reads_before = stream.bytes_read
        # Simulate social_snapshot pre-check
        if cl > 10:
            stream.close()
            if body_reads_before != 0:
                errors.append("Content-Length oversize must not read body bytes first")
            if None in stream.read_call_sizes:
                errors.append("oversize CL path must not issue size-less read")
        else:
            errors.append("expected Content-Length 100")

        # Chunked / no Content-Length: oversize during bounded read
        def _transport_chunked(**_kw: Any):
            return _FakeNetResp(b"Y" * 50, status=200, headers={}), _FakeConn()

        _TEST_PINNED_TRANSPORT = _transport_chunked
        stream2 = _pinned_https_open(
            urllib.request.Request("https://8.8.8.8/chunked"), timeout=1.0
        )
        # Emulate read_bounded with max 10
        got = b""
        over = False
        while True:
            piece = stream2.read(min(8, 11 - len(got)))
            if not piece:
                break
            got += piece
            if len(got) > 10:
                over = True
                break
        stream2.close()
        if not over:
            errors.append("chunked oversize should exceed bound during read")
        if None in stream2.read_call_sizes:
            errors.append("chunked path issued size-less read")

        # Body exactly at cap
        def _transport_at_cap(**_kw: Any):
            return _FakeNetResp(b"Z" * 10, status=200, headers={"Content-Length": "10"}), _FakeConn()

        _TEST_PINNED_TRANSPORT = _transport_at_cap
        stream3 = _pinned_https_open(
            urllib.request.Request("https://8.8.8.8/cap"), timeout=1.0
        )
        buf = b""
        while True:
            piece = stream3.read(min(8, 10 - len(buf)))
            if not piece:
                break
            buf += piece
            if len(buf) >= 10:
                break
        stream3.close()
        if buf != b"Z" * 10:
            errors.append(f"body at cap should pass, got {len(buf)} bytes")

        # HTTP error status without unbounded error-body read
        def _transport_404(**_kw: Any):
            return (
                _FakeNetResp(b"not found page " * 1000, status=404, headers={"Content-Length": "99999"}),
                _FakeConn(),
            )

        _TEST_PINNED_TRANSPORT = _transport_404
        try:
            _pinned_https_open(urllib.request.Request("https://8.8.8.8/missing"), timeout=1.0)
            errors.append("404 should raise HTTPError")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                errors.append(f"expected 404, got {exc.code}")
            # Error body must not have been pre-buffered via size-less read
            fp = exc.fp
            if fp is not None and hasattr(fp, "read_call_sizes"):
                if None in fp.read_call_sizes:
                    errors.append("HTTPError path must not size-less-read body")
                if getattr(fp, "bytes_read", 0) != 0:
                    errors.append("HTTPError must not pre-read error body")
            try:
                exc.close()
            except Exception:
                pass

        for code in (403, 429):
            def _transport_status(status=code, **_kw: Any):
                return _FakeNetResp(b"err", status=status, headers={}), _FakeConn()

            _TEST_PINNED_TRANSPORT = _transport_status
            try:
                _pinned_https_open(
                    urllib.request.Request(f"https://8.8.8.8/s{code}"), timeout=1.0
                )
                errors.append(f"{code} should raise HTTPError")
            except urllib.error.HTTPError as exc:
                if exc.code != code:
                    errors.append(f"expected {code}, got {exc.code}")
                try:
                    exc.close()
                except Exception:
                    pass

        # Timeout maps to OSError/socket timeout from transport
        def _transport_timeout(**_kw: Any):
            raise TimeoutError("simulated timeout")

        _TEST_PINNED_TRANSPORT = _transport_timeout
        try:
            _pinned_https_open(urllib.request.Request("https://8.8.8.8/t"), timeout=0.01)
            errors.append("timeout should raise")
        except (TimeoutError, OSError):
            pass
        except Exception as exc:  # noqa: BLE001
            errors.append(f"timeout mapped to unexpected {type(exc).__name__}: {exc}")
    finally:
        _TEST_PINNED_TRANSPORT = saved_transport

    # Manual redirect policy: preserve credentials only on the same origin,
    # block before a cross-origin sink request, and bound redirect loops.
    import http.server
    import threading

    class _RedirectSink(http.server.BaseHTTPRequestHandler):
        post_hits = 0
        get_headers: list[dict[str, str]] = []

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

        def do_POST(self) -> None:  # noqa: N802
            type(self).post_hits += 1
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        def do_GET(self) -> None:  # noqa: N802
            type(self).get_headers.append(dict(self.headers.items()))
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

    class _RedirectSource(http.server.BaseHTTPRequestHandler):
        cross_location = ""
        same_origin_authorization: list[str] = []
        loop_hits = 0

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

        def do_POST(self) -> None:  # noqa: N802
            content_length = int(self.headers.get("Content-Length") or 0)
            if content_length:
                self.rfile.read(content_length)
            if self.path == "/same-start":
                self.send_response(307)
                self.send_header("Location", "/same-final")
                self.end_headers()
                return
            if self.path == "/same-final":
                type(self).same_origin_authorization.append(
                    self.headers.get("Authorization", "")
                )
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")
                return
            if self.path == "/cross-start":
                self.send_response(307)
                self.send_header("Location", type(self).cross_location + "/private")
                self.end_headers()
                return
            if self.path == "/loop":
                type(self).loop_hits += 1
                self.send_response(307)
                self.send_header("Location", "/loop")
                self.end_headers()
                return
            self.send_response(404)
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/public-start":
                self.send_response(302)
                self.send_header("Location", type(self).cross_location + "/public")
                self.end_headers()
                return
            self.send_response(404)
            self.end_headers()

    sink_server = http.server.HTTPServer(("127.0.0.1", 0), _RedirectSink)
    sink_port = sink_server.server_address[1]
    _RedirectSource.cross_location = f"http://127.0.0.1:{sink_port}"
    source_server = http.server.HTTPServer(("127.0.0.1", 0), _RedirectSource)
    source_port = source_server.server_address[1]
    sink_thread = threading.Thread(target=sink_server.serve_forever, daemon=True)
    source_thread = threading.Thread(target=source_server.serve_forever, daemon=True)
    sink_thread.start()
    source_thread.start()
    redirect_secret = "Bearer REDIRECT-SELF-TEST-SECRET"
    private_headers = {
        "Authorization": redirect_secret,
        "Content-Type": "application/json",
    }
    try:
        same_req = urllib.request.Request(
            f"http://127.0.0.1:{source_port}/same-start",
            data=b"{}",
            headers=private_headers,
        )
        with public_urlopen_with_redirects(
            same_req,
            timeout=5,
            allow_loopback_fixture=True,
        ):
            pass
        if _RedirectSource.same_origin_authorization != [redirect_secret]:
            errors.append("same-origin redirect did not preserve Authorization")

        cross_req = urllib.request.Request(
            f"http://127.0.0.1:{source_port}/cross-start",
            data=b"{}",
            headers=private_headers,
        )
        try:
            public_urlopen_with_redirects(
                cross_req,
                timeout=5,
                allow_loopback_fixture=True,
            )
            errors.append("credentialed cross-origin redirect should be blocked")
        except RedirectPolicyError as exc:
            if "REDIRECT-SELF-TEST-SECRET" in str(exc):
                errors.append("redirect policy error exposed Authorization")
        if _RedirectSink.post_hits != 0:
            errors.append("cross-origin redirect sink received a private POST")

        public_req = urllib.request.Request(
            f"http://127.0.0.1:{source_port}/public-start",
            headers={"User-Agent": "redirect-self-test"},
        )
        with public_urlopen_with_redirects(
            public_req,
            timeout=5,
            allow_loopback_fixture=True,
        ):
            pass
        if len(_RedirectSink.get_headers) != 1:
            errors.append("public cross-origin GET redirect was not followed")
        elif _RedirectSink.get_headers[0].get("User-Agent") != "redirect-self-test":
            errors.append("public cross-origin header was not preserved")

        loop_req = urllib.request.Request(
            f"http://127.0.0.1:{source_port}/loop",
            data=b"{}",
            headers=private_headers,
        )
        try:
            public_urlopen_with_redirects(
                loop_req,
                timeout=5,
                allow_loopback_fixture=True,
            )
            errors.append("redirect loop should be bounded")
        except RedirectPolicyError as exc:
            if "too many redirects" not in str(exc):
                errors.append(f"unexpected redirect-loop error: {exc}")
        if _RedirectSource.loop_hits != DEFAULT_MAX_REDIRECTS + 1:
            errors.append(
                "redirect loop hop count mismatch: "
                f"{_RedirectSource.loop_hits}"
            )
    finally:
        source_server.shutdown()
        sink_server.shutdown()
        source_server.server_close()
        sink_server.server_close()

    # Source-level guard: production pinned open must not contain unbounded resp.read()
    import inspect
    import re

    src = inspect.getsource(_pinned_https_open)
    if re.search(r"resp\.read\(\s*\)", src):
        errors.append("production _pinned_https_open still calls resp.read() without size")

    if errors:
        print("ssrf_helpers self-test FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("ssrf_helpers self-test ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
