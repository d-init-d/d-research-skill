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
                if _is_non_public_ip(ipaddress.ip_address(peer_ip)):
                    raise ValueError(f"peer address is non-public: {peer_ip}")
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
