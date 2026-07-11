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


class _PinnedHTTPResponse:
    """Minimal file-like response compatible with social_snapshot readers."""

    def __init__(self, status: int, headers: http.client.HTTPMessage, body: bytes, url: str):
        self.status = status
        self.headers = headers
        self._body = body
        self._fp = __import__("io").BytesIO(body)
        self.url = url
        # urllib.error.HTTPError expects these attributes when re-raised.
        self.reason = headers.get("Reason", "") if headers else ""

    def read(self, n: int | None = None) -> bytes:
        return self._fp.read() if n is None else self._fp.read(n)

    def __enter__(self) -> "_PinnedHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        self._fp.close()


def _pinned_https_open(req: urllib.request.Request, timeout: float | None) -> _PinnedHTTPResponse:
    """Connect to a DNS-validated public IP with original Host/SNI.

    Re-checks the peer address after connect to shrink DNS-rebinding TOCTOU.
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
        try:
            sock = socket.create_connection((ip, port), timeout=timeout)
            peer_ip = sock.getpeername()[0]
            if _is_non_public_ip(ipaddress.ip_address(peer_ip)):
                raise ValueError(f"peer address is non-public: {peer_ip}")
            ssock = context.wrap_socket(sock, server_hostname=host)
            sock = None  # ownership transferred
            conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=context)
            conn.sock = ssock
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            status = resp.status
            response_headers = resp.msg
            # Detach so closing conn does not discard already-read body.
            conn.sock = None
            ssock.close()
            ssock = None
            if status >= 400:
                raise urllib.error.HTTPError(
                    url,
                    status,
                    getattr(resp, "reason", "") or f"HTTP {status}",
                    response_headers,
                    __import__("io").BytesIO(data),
                )
            return _PinnedHTTPResponse(status, response_headers, data, url)
        except (OSError, ssl.SSLError, ValueError, http.client.HTTPException) as exc:
            last_error = exc
            continue
        finally:
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

    if errors:
        print("ssrf_helpers self-test FAILED:", file=__import__("sys").stderr)
        for e in errors:
            print(f"  - {e}", file=__import__("sys").stderr)
        return 1
    print("ssrf_helpers self-test ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(self_test())
