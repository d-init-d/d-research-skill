#!/usr/bin/env python3
"""SSRF guards for social_snapshot and other outbound URL fetches.

Stdlib-only. Used by social_snapshot.py.

Guarantees:
- HTTPS only by default (HTTP only when allow_http=True)
- No userinfo in URLs
- Blocked hostnames (localhost, cloud metadata names)
- Non-public IPv4/IPv6 literals and DNS resolutions rejected
- IPv4-mapped IPv6 (::ffff:x.x.x.x) evaluated via the embedded IPv4 address
- Deterministic IPv6 public-destination policy shared with Node
  (scripts/lib/ssrf_guards.mjs); not version-drifting ipaddress.is_global
- Optional DNS-pinned HTTPS open to reduce resolve-then-connect TOCTOU
- Production pinned open streams the HTTP body (never buffers unbounded)

IPv6 policy (IANA IPv6 Special-Purpose Address Registry, last updated
2025-10-09):
1. IPv4-mapped (::ffff:0:0/96) → embedded IPv4 policy first.
2. Fail closed outside global-unicast envelope 2000::/3.
3. Translation prefixes always blocked (SSRF via encoded IPv4): 64:ff9b::/96,
   64:ff9b:1::/48, 2002::/16 (6to4).
4. Within 2000::/3 block 2001::/23 (entire parent; no more-specific IANA
   exceptions — CPython 3.10–3.12 disagree, so fail-closed parent is the only
   identical Node/Python choice), 2001:db8::/32, 2002::/16, 3fff::/20.
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

# Explicit IPv6 policy tables (containment only; not is_global/is_reserved).
_IPV4_MAPPED_NET = ipaddress.IPv6Network("::ffff:0:0/96")
_IPV6_GLOBAL_UNICAST = ipaddress.IPv6Network("2000::/3")
# Translation / SSRF-encoding prefixes (block even if IANA Globally Reachable).
_IPV6_TRANSLATION_NETS = (
    ipaddress.IPv6Network("64:ff9b::/96"),  # NAT64 well-known (RFC 6052)
    ipaddress.IPv6Network("64:ff9b:1::/48"),  # local-use NAT64 (RFC 8215)
)
# Non-public / special-use inside the GUA envelope.
_IPV6_GUA_BLOCK_NETS = (
    ipaddress.IPv6Network("2001::/23"),  # IETF Protocol Assignments parent
    ipaddress.IPv6Network("2001:db8::/32"),  # documentation
    ipaddress.IPv6Network("2002::/16"),  # 6to4 translation
    ipaddress.IPv6Network("3fff::/20"),  # documentation
)

# Injectable for offline self-tests (social_snapshot monkey-patches this).
_TEST_URLOPEN: Any = None

# Optional injectable transport for unit-testing the production pinned path
# without a live network. Signature:
#   factory(host, port, timeout, context, method, path, body, headers, ip)
# must return exactly (HTTPResponse-like, connection-like, peer_ip) or raise.
# peer_ip is required so production _assert_connected_peer always runs (tests
# cannot bypass peer validation by omitting a peer). Wrong arity / missing peer
# fails closed.
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


def _is_non_public_ipv4(ip: ipaddress.IPv4Address) -> bool:
    """IPv4 destination policy (stdlib property flags; stable across 3.10–3.12)."""
    flags = (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )
    is_global = getattr(ip, "is_global", None)
    if is_global is False:
        flags = True
    return bool(flags)


def _is_non_public_ipv6(ip: ipaddress.IPv6Address) -> bool:
    """Deterministic IPv6 public-destination policy (parity with Node)."""
    # 1) IPv4-mapped → embedded IPv4 policy first.
    mapped = ip.ipv4_mapped
    if mapped is not None:
        return _is_non_public_ipv4(mapped)

    # 2) Translation prefixes always blocked (SSRF via encoded IPv4).
    for net in _IPV6_TRANSLATION_NETS:
        if ip in net:
            return True

    # 3) Fail closed outside currently allocated global-unicast envelope.
    if ip not in _IPV6_GLOBAL_UNICAST:
        return True

    # 4) Block IANA non-global / special-use ranges inside 2000::/3.
    for net in _IPV6_GUA_BLOCK_NETS:
        if ip in net:
            return True

    return False


def _is_non_public_ip(ip: ipaddress._BaseAddress) -> bool:
    """Return True when *ip* must not be contacted by public research helpers.

    IPv4-mapped IPv6 addresses are evaluated against the embedded IPv4
    address so ::ffff:127.0.0.1 / ::ffff:169.254.169.254 cannot slip through
    platform differences in IPv6 property flags. Pure IPv6 uses the explicit
    deterministic tables documented in the module docstring (not is_global).
    """
    if isinstance(ip, ipaddress.IPv6Address):
        return _is_non_public_ipv6(ip)
    if isinstance(ip, ipaddress.IPv4Address):
        return _is_non_public_ipv4(ip)
    # Fail closed for unexpected address types.
    return True


def _normalize_ip_for_comparison(value: str) -> str:
    """Return a canonical IP string, unwrapping IPv4-mapped IPv6 values."""
    if not isinstance(value, str) or not value:
        raise ValueError("IP value must be a non-empty string")
    raw = value
    # Peer and resolver values are socket/DNS outputs, not URL authorities.
    # Do not repair whitespace, brackets, or scope identifiers before matching:
    # public peers never need a zone and scoped IPv6 is non-public.
    if raw != raw.strip() or "%" in raw or "[" in raw or "]" in raw:
        raise ValueError(f"malformed IP value: {value!r}")
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
    except (TypeError, ValueError):
        return False
    return normalized_peer in normalized_validated


def _assert_connected_peer(
    peer_ip: str | None,
    validated_ips: list[str],
) -> None:
    """Fail-closed peer gate used by production and the test transport seam.

    Rejects missing, empty, malformed, non-public, and unvalidated peers.
    Canonical comparison covers compressed/expanded IPv6 and IPv4-mapped forms.
    """
    if peer_ip is None or peer_ip == "":
        raise ValueError("peer address unavailable")
    if not isinstance(peer_ip, str):
        raise ValueError(f"peer address is malformed: {peer_ip}")
    raw = peer_ip
    try:
        normalized_peer = _normalize_ip_for_comparison(raw)
    except ValueError as exc:
        raise ValueError(f"peer address is malformed: {peer_ip}") from exc
    try:
        if _is_non_public_ip(ipaddress.ip_address(normalized_peer)):
            raise ValueError(f"peer address is non-public: {peer_ip}")
    except ValueError as exc:
        # Re-raise our non-public / malformed messages; wrap unexpected parse errors.
        msg = str(exc)
        if msg.startswith("peer address"):
            raise
        raise ValueError(f"peer address is malformed: {peer_ip}") from exc
    if not isinstance(validated_ips, list) or not validated_ips:
        raise ValueError(
            "peer address mismatch: connected peer is not in the "
            "DNS-validated address set"
        )
    if not _peer_matches_validated_ips(raw, validated_ips):
        raise ValueError(
            "peer address mismatch: connected peer is not in the "
            "DNS-validated address set"
        )


def _canonical_http_host_header(parsed: urllib.parse.ParseResult) -> str:
    """RFC 7230 Host authority from a validated URL (never caller-supplied).

    IPv6 literals are bracketed. Non-default ports are appended. Default ports
    for http/https are omitted so Host matches Node hostHeaderFromUrl.
    """
    host = parsed.hostname
    if not host:
        raise ValueError("URL host is required")
    try:
        addr = ipaddress.ip_address(host)
        if isinstance(addr, ipaddress.IPv6Address):
            authority = f"[{host}]"
        else:
            authority = host
    except ValueError:
        authority = host  # DNS name
    port = parsed.port
    scheme = (parsed.scheme or "").lower()
    if port is not None:
        default_port = 443 if scheme == "https" else 80 if scheme == "http" else None
        if default_port is None or port != default_port:
            return f"{authority}:{port}"
    return authority


def _headers_with_url_derived_host(
    header_items: list[tuple[str, str]] | Any,
    parsed: urllib.parse.ParseResult,
) -> dict[str, str]:
    """Strip every case-insensitive Host key and set one URL-derived Host."""
    headers = {
        str(k): v for k, v in header_items if str(k).lower() != "host"
    }
    headers["Host"] = _canonical_http_host_header(parsed)
    return headers


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
    try:
        # Force port syntax/range validation before DNS or any other network I/O.
        parsed.port
    except ValueError as exc:
        raise ValueError("URL port is invalid") from exc
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
    """Connect to a DNS-validated public IP with URL-derived Host and SNI.

    Caller-supplied Host headers are stripped; Host is always rebuilt from the
    validated URL (IPv6 bracketed). Peer address is checked via the shared
    ``_assert_connected_peer`` on both production and test-transport paths.
    Returns a streaming response; never buffers the full body into memory.
    """
    url = req.full_url
    parsed = urllib.parse.urlparse(url)
    if (parsed.scheme or "").lower() != "https":
        raise ValueError(f"scheme not allowed for pinned open: {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise ValueError("URL host is required")
    port = 443 if parsed.port is None else parsed.port
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    ips = resolve_public_ips(host)
    headers = _headers_with_url_derived_host(req.header_items(), parsed)
    method = getattr(req, "get_method", lambda: "GET")()
    body = req.data
    last_error: Exception | None = None
    context = ssl.create_default_context()
    for ip in ips:
        sock: socket.socket | None = None
        ssock: ssl.SSLSocket | None = None
        conn: http.client.HTTPSConnection | None = None
        resp: Any = None
        try:
            if _TEST_PINNED_TRANSPORT is not None:
                result = _TEST_PINNED_TRANSPORT(
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
                # Fail closed if the seam omits peer or returns wrong arity —
                # tests must exercise production _assert_connected_peer.
                if not isinstance(result, tuple) or len(result) != 3:
                    candidates = result if isinstance(result, tuple) else (result,)
                    for candidate in candidates:
                        close = getattr(candidate, "close", None)
                        if callable(close):
                            try:
                                close()
                            except Exception:
                                pass
                    raise ValueError(
                        "pinned transport must return "
                        "(response, connection, peer_ip)"
                    )
                resp, conn, peer_ip = result
                _assert_connected_peer(peer_ip, ips)
            else:
                sock = socket.create_connection((ip, port), timeout=timeout)
                peer_ip = sock.getpeername()[0]
                _assert_connected_peer(peer_ip, ips)
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
            resp = None
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
            if resp is not None:
                try:
                    resp.close()
                except Exception:
                    pass
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
        port = (
            (443 if scheme == "https" else 80)
            if parsed.port is None
            else parsed.port
        )
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
        "https://[::]/x",
        "https://[::ffff:127.0.0.1]/x",
        "https://[::ffff:169.254.169.254]/latest/",
        "https://[::ffff:10.0.0.1]/x",
        "https://[::192.168.1.1]/x",
        "https://[0:0:0:0:0:0:c0a8:101]/x",
        "https://[100:0:0:1::1]/x",
        "https://[2002::1]/x",
        "https://[5f00::1]/x",
        "https://[fec0::1]/x",
        "https://[4000::1]/x",
        "https://[8000::1]/x",
        "https://[2001:db8::1]/x",
        "https://[3fff::1]/x",
        "https://[64:ff9b::7f00:1]/x",
        "https://[64:ff9b::c0a8:1]/x",
        "https://[100::1]/x",
        "https://[2001::1]/x",
        "https://[2001:1::1]/x",
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
    try:
        assert_public_http_url("https://[2001:4860:4860::8888]/")
    except ValueError as exc:
        errors.append(f"public IPv6 unicast should be allowed: {exc}")

    # Deterministic cross-runtime public-destination matrix (must match Node).
    for raw, expect_block in (
        # Unspecified / loopback / expanded forms
        ("::", True),
        ("0:0:0:0:0:0:0:0", True),
        ("::1", True),
        # IPv4-mapped private / metadata
        ("::ffff:127.0.0.1", True),
        ("::ffff:169.254.169.254", True),
        ("::ffff:10.1.2.3", True),
        ("::ffff:c0a8:101", True),
        ("0:0:0:0:0:ffff:192.168.1.1", True),
        ("0:0:0:0:0:ffff:c0a8:101", True),
        # Deprecated IPv4-compatible with embedded private (outside 2000::/3)
        ("::192.168.1.1", True),
        ("0:0:0:0:0:0:c0a8:101", True),
        # Outside global-unicast envelope 2000::/3
        ("100:0:0:1::1", True),  # IANA dummy IPv6 prefix (RFC 9780)
        ("100::1", True),
        ("5f00::1", True),  # SRv6 SIDs
        ("fec0::1", True),  # deprecated site-local
        ("4000::1", True),
        ("8000::1", True),
        ("fc00::1", True),
        ("fe80::1", True),
        ("ff02::1", True),
        # Translation prefixes
        ("64:ff9b::7f00:1", True),
        ("64:ff9b::808:808", True),
        ("64:ff9b:1::1", True),
        ("2002::1", True),
        ("2002:c0a8:101::1", True),
        # Inside 2000::/3 special-use + entire 2001::/23 parent
        ("2001::1", True),
        ("2001:2::1", True),
        ("2001:10::1", True),
        ("2001:1::1", True),
        ("2001:1::2", True),
        ("2001:1::3", True),
        ("2001:1:1::1", True),
        ("2001:3::1", True),
        ("2001:4:112::1", True),
        ("2001:20::1", True),
        ("2001:30::1", True),
        ("2001:db8::1", True),
        ("3fff::1", True),
        # Safe public controls
        ("8.8.8.8", False),
        ("1.1.1.1", False),
        ("::ffff:8.8.8.8", False),
        ("::ffff:808:808", False),
        ("0:0:0:0:0:ffff:8.8.8.8", False),
        ("2001:4860:4860::8888", False),
        ("2606:4700:4700::1111", False),
        ("2000::1", False),
        ("2620:4f:8000::1", False),
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

    # Pure fail-closed peer assertion (shared production / test-seam gate).
    for peer, validated, expect_substr in (
        (None, ["8.8.8.8"], "unavailable"),
        ("", ["8.8.8.8"], "unavailable"),
        ("not-an-ip", ["8.8.8.8"], "malformed"),
        ("127.0.0.1", ["8.8.8.8"], "non-public"),
        ("10.0.0.1", ["10.0.0.1"], "non-public"),
        ("8.8.8.8", ["1.2.3.4"], "mismatch"),
        ("8.8.8.8", [], "mismatch"),
    ):
        try:
            _assert_connected_peer(peer, validated)
            errors.append(
                f"_assert_connected_peer must reject peer={peer!r} validated={validated!r}"
            )
        except ValueError as exc:
            if expect_substr not in str(exc).lower():
                errors.append(
                    f"_assert_connected_peer({peer!r}) error {exc!r} "
                    f"missing {expect_substr!r}"
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(
                f"_assert_connected_peer({peer!r}) unexpected {type(exc).__name__}: {exc}"
            )
    try:
        _assert_connected_peer("8.8.8.8", ["8.8.8.8"])
        _assert_connected_peer("::ffff:8.8.8.8", ["8.8.8.8"])
        _assert_connected_peer("8.8.8.8", ["::ffff:8.8.8.8"])
        _assert_connected_peer(
            "2001:4860:4860:0:0:0:0:8888",
            ["2001:4860:4860::8888"],
        )
        _assert_connected_peer(
            "2001:4860:4860::8888",
            ["2001:4860:4860:0:0:0:0:8888"],
        )
    except Exception as exc:  # noqa: BLE001
        errors.append(f"_assert_connected_peer must accept equivalents: {exc}")

    malformed_peers = (
        " 8.8.8.8",
        "8.8.8.8 ",
        "[2001:4860:4860::8888]",
        "2001:4860:4860::8888%",
        "2001:4860:4860::8888%%",
        "2001:4860:4860::8888%2",
        "2001:4860:4860::8888%a%b",
        "[2001:4860:4860::8888]%7",
        "fe80::1%2",
        "fe80::1%eth0",
        "::ffff:008.008.008.008",
    )
    for peer in malformed_peers:
        if _peer_matches_validated_ips(
            peer, ["2001:4860:4860::8888", "8.8.8.8"]
        ):
            errors.append(f"malformed/scoped peer must not match: {peer!r}")
        try:
            _assert_connected_peer(
                peer, ["2001:4860:4860::8888", "8.8.8.8"]
            )
            errors.append(f"malformed/scoped peer must fail closed: {peer!r}")
        except ValueError:
            pass

    # URL-derived Host: DNS / IPv4 / bracketed IPv6 / ports; never caller Host.
    for raw_url, expect_host in (
        ("https://example.com/x", "example.com"),
        ("https://example.com:443/x", "example.com"),
        ("https://example.com:8443/x", "example.com:8443"),
        ("https://8.8.8.8/", "8.8.8.8"),
        ("https://8.8.8.8:8443/", "8.8.8.8:8443"),
        ("https://[2001:db8::1]/", "[2001:db8::1]"),
        ("https://[2001:db8::1]:8443/", "[2001:db8::1]:8443"),
        ("https://[2001:4860:4860::8888]/", "[2001:4860:4860::8888]"),
        ("https://[2001:4860:4860::8888]:8443/", "[2001:4860:4860::8888]:8443"),
    ):
        parsed_h = urllib.parse.urlparse(raw_url)
        got_h = _canonical_http_host_header(parsed_h)
        if got_h != expect_host:
            errors.append(
                f"_canonical_http_host_header({raw_url})={got_h!r}, expected {expect_host!r}"
            )
    # Hostile Host keys stripped; only URL-derived Host remains.
    hostile_items = [
        ("Host", "127.0.0.1"),
        ("HOST", "169.254.169.254"),
        ("host", "metadata"),
        ("User-Agent", "ssrf-test"),
    ]
    bound = _headers_with_url_derived_host(
        hostile_items,
        urllib.parse.urlparse("https://example.com:8443/x"),
    )
    host_keys = [k for k in bound if k.lower() == "host"]
    if host_keys != ["Host"] or bound.get("Host") != "example.com:8443":
        errors.append(f"hostile Host strip failed: {bound!r}")
    if bound.get("User-Agent") != "ssrf-test":
        errors.append("non-Host headers must be preserved after Host rebinding strip")
    ipv6_bound = _headers_with_url_derived_host(
        [("HoSt", "127.0.0.1")],
        urllib.parse.urlparse("https://[2001:db8::1]:8443/"),
    )
    if ipv6_bound.get("Host") != "[2001:db8::1]:8443":
        errors.append(f"IPv6 Host authority wrong: {ipv6_bound!r}")

    # Invalid ports must fail before DNS/network access.
    saved_getaddrinfo = socket.getaddrinfo
    invalid_port_dns_called = False

    def _unexpected_invalid_port_dns(*_args: Any, **_kwargs: Any):
        nonlocal invalid_port_dns_called
        invalid_port_dns_called = True
        raise AssertionError("invalid port reached DNS")

    socket.getaddrinfo = _unexpected_invalid_port_dns
    try:
        for invalid_port_url in (
            "https://invalid-port.test:65536/",
            "https://invalid-port.test:-1/",
            "https://invalid-port.test:abc/",
        ):
            try:
                assert_public_http_url(invalid_port_url)
                errors.append(f"invalid port must fail closed: {invalid_port_url}")
            except ValueError:
                pass
    finally:
        socket.getaddrinfo = saved_getaddrinfo
    if invalid_port_dns_called:
        errors.append("invalid URL port must be rejected before DNS")

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
    # Transport must return (resp, conn, peer_ip); peer goes through
    # production _assert_connected_peer (cannot bypass via the test seam).
    global _TEST_PINNED_TRANSPORT  # noqa: PLW0603
    saved_transport = _TEST_PINNED_TRANSPORT
    try:
        oversized = b"X" * 100

        def _transport_oversize_cl(**_kw: Any):
            headers = {"Content-Length": "100"}
            return (
                _FakeNetResp(oversized, status=200, headers=headers),
                _FakeConn(),
                "8.8.8.8",
            )

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
            return _FakeNetResp(b"Y" * 50, status=200, headers={}), _FakeConn(), "8.8.8.8"

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
            return (
                _FakeNetResp(b"Z" * 10, status=200, headers={"Content-Length": "10"}),
                _FakeConn(),
                "8.8.8.8",
            )

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
                _FakeNetResp(
                    b"not found page " * 1000,
                    status=404,
                    headers={"Content-Length": "99999"},
                ),
                _FakeConn(),
                "8.8.8.8",
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
                return (
                    _FakeNetResp(b"err", status=status, headers={}),
                    _FakeConn(),
                    "8.8.8.8",
                )

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

        # Peer validation through production path (test seam cannot skip it).
        wrong_arity_resp = _FakeNetResp(b"x", status=200, headers={})
        wrong_arity_conn = _FakeConn()

        def _transport_wrong_arity(**_kw: Any):
            return wrong_arity_resp, wrong_arity_conn

        _TEST_PINNED_TRANSPORT = _transport_wrong_arity
        try:
            _pinned_https_open(urllib.request.Request("https://8.8.8.8/arity"), timeout=1.0)
            errors.append("wrong-arity transport must fail closed")
        except ValueError as exc:
            if "peer_ip" not in str(exc) and "pinned transport" not in str(exc).lower():
                errors.append(f"wrong-arity error unexpected: {exc}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"wrong-arity unexpected {type(exc).__name__}: {exc}")
        if not wrong_arity_resp.closed or not wrong_arity_conn.closed:
            errors.append("wrong-arity transport resources must be closed")

        for peer_label, peer_val, expect_sub in (
            ("missing", None, "unavailable"),
            ("empty", "", "unavailable"),
            ("malformed", "not-an-ip", "malformed"),
            ("private", "127.0.0.1", "non-public"),
            ("mismatch", "1.2.3.4", "mismatch"),
        ):
            bad_peer_resp = _FakeNetResp(b"x", status=200, headers={})
            bad_peer_conn = _FakeConn()

            def _transport_bad_peer(peer=peer_val, **_kw: Any):
                return bad_peer_resp, bad_peer_conn, peer

            _TEST_PINNED_TRANSPORT = _transport_bad_peer
            try:
                _pinned_https_open(
                    urllib.request.Request(f"https://8.8.8.8/peer-{peer_label}"),
                    timeout=1.0,
                )
                errors.append(f"bad peer ({peer_label}) must fail via production assert")
            except ValueError as exc:
                if expect_sub not in str(exc).lower():
                    errors.append(
                        f"bad peer ({peer_label}) error {exc!r} missing {expect_sub!r}"
                    )
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    f"bad peer ({peer_label}) unexpected {type(exc).__name__}: {exc}"
                )
            if not bad_peer_resp.closed or not bad_peer_conn.closed:
                errors.append(f"bad peer ({peer_label}) resources must be closed")

        # Canonical IPv6 / IPv4-mapped peer accepted through production assert.
        def _transport_mapped_peer(**_kw: Any):
            return (
                _FakeNetResp(b"ok", status=200, headers={"Content-Length": "2"}),
                _FakeConn(),
                "::ffff:8.8.8.8",
            )

        _TEST_PINNED_TRANSPORT = _transport_mapped_peer
        try:
            stream_map = _pinned_https_open(
                urllib.request.Request("https://8.8.8.8/mapped-peer"), timeout=1.0
            )
            stream_map.close()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"IPv4-mapped peer via production assert must pass: {exc}")

        # Hostile Host override overridden by URL authority on pinned open.
        captured_headers: dict[str, str] = {}

        def _transport_capture_headers(**kw: Any):
            captured_headers.clear()
            captured_headers.update(kw.get("headers") or {})
            captured_headers["__transport_port__"] = str(kw.get("port"))
            peer = kw.get("ip") or "8.8.8.8"
            return (
                _FakeNetResp(b"ok", status=200, headers={"Content-Length": "2"}),
                _FakeConn(),
                peer,
            )

        _TEST_PINNED_TRANSPORT = _transport_capture_headers
        hostile_req = urllib.request.Request(
            "https://8.8.8.8:8443/host-rebinding",
            headers={"Host": "127.0.0.1", "HOST": "169.254.169.254", "User-Agent": "t"},
        )
        try:
            stream_h = _pinned_https_open(hostile_req, timeout=1.0)
            stream_h.close()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Host rebinding capture path failed: {exc}")
        else:
            host_keys = [k for k in captured_headers if k.lower() == "host"]
            if len(host_keys) != 1 or captured_headers.get("Host") != "8.8.8.8:8443":
                errors.append(
                    f"pinned open must bind URL Host, got {captured_headers!r}"
                )
            for hk in host_keys:
                val = str(captured_headers.get(hk, ""))
                if val in {"127.0.0.1", "169.254.169.254", "metadata"}:
                    errors.append("hostile Host value leaked into pinned request")

        # Explicit port zero must not silently connect to 443 or collapse to
        # the default origin. The test seam avoids making a real port-0 socket.
        captured_headers.clear()
        try:
            stream_zero = _pinned_https_open(
                urllib.request.Request("https://8.8.8.8:0/explicit-zero-port"),
                timeout=1.0,
            )
            stream_zero.close()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"explicit port zero capture path failed: {exc}")
        else:
            if captured_headers.get("Host") != "8.8.8.8:0":
                errors.append(f"explicit port zero Host mismatch: {captured_headers!r}")
            if captured_headers.get("__transport_port__") != "0":
                errors.append(
                    f"explicit port zero must reach transport unchanged: {captured_headers!r}"
                )
            if _url_origin("https://example.test:0/") == _url_origin(
                "https://example.test/"
            ):
                errors.append("explicit port zero must not equal the default HTTPS origin")

        # IPv6 literal Host must be bracketed (with and without non-default port).
        for ipv6_url, expect_host in (
            (
                "https://[2001:4860:4860::8888]/host-ipv6",
                "[2001:4860:4860::8888]",
            ),
            (
                "https://[2001:4860:4860::8888]:8443/host-ipv6-port",
                "[2001:4860:4860::8888]:8443",
            ),
        ):
            captured_headers.clear()
            try:
                stream_v6 = _pinned_https_open(
                    urllib.request.Request(
                        ipv6_url,
                        headers={"Host": "127.0.0.1"},
                    ),
                    timeout=1.0,
                )
                stream_v6.close()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"IPv6 Host capture ({ipv6_url}) failed: {exc}")
            else:
                if captured_headers.get("Host") != expect_host:
                    errors.append(
                        f"IPv6 Host for {ipv6_url}: "
                        f"got {captured_headers.get('Host')!r}, expected {expect_host!r}"
                    )
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
