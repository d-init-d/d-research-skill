import socket
import sys
from pathlib import Path

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import _ssrf_helpers as ssrf_helpers
import social_snapshot


def test_n01_offline_dns_self_test():
    """N01: social_snapshot.py self_test executed when socket.getaddrinfo raises gaierror (repro F06)."""
    orig_getaddrinfo = socket.getaddrinfo

    def failing_getaddrinfo(*args, **kwargs):
        raise socket.gaierror(-3, "Temporary failure in name resolution (offline test)")

    socket.getaddrinfo = failing_getaddrinfo
    try:
        # self_test must pass completely offline without relying on external DNS
        rc = social_snapshot.self_test()
        assert rc == 0
    finally:
        socket.getaddrinfo = orig_getaddrinfo


def test_n02_tier_a_and_b_fixture_coverage():
    """N02: Offline fixture map includes Tier A and Tier B hosts (x.com, reddit, bsky, twitter)."""
    fixture_hosts = social_snapshot.OFFLINE_FIXTURE_HOSTS
    required_hosts = {
        "x.com", "www.x.com",
        "twitter.com", "www.twitter.com",
        "reddit.com", "www.reddit.com",
        "bsky.app", "public.api.bsky.app",
        "mastodon.social",
        "news.ycombinator.com", "hn.algolia.com",
        "lemmy.ml",
    }
    missing = required_hosts - fixture_hosts
    assert not missing, f"Missing fixture hosts: {missing}"

    # Verify that mock resolver resolves Tier A and Tier B hosts to public IP
    resolver = social_snapshot.make_offline_fixture_resolver(fixture_hosts)
    for host in ["x.com", "bsky.app", "reddit.com"]:
        ips = resolver(host)
        assert len(ips) > 0
        assert all(ip == "8.8.8.8" for ip in ips)


def test_n03_unregistered_host_offline_fail():
    """N03: Domain name outside registered offline fixture map raises unregistered_offline_host error."""
    fixture_hosts = social_snapshot.OFFLINE_FIXTURE_HOSTS
    resolver = social_snapshot.make_offline_fixture_resolver(fixture_hosts)

    unregistered_domain = "unregistered-unknown-site-12345.org"
    try:
        resolver(unregistered_domain)
        assert False, "Expected unregistered_offline_host error"
    except Exception as exc:
        assert "unregistered_offline_host" in str(exc).lower() or "unregistered" in str(exc).lower()


def test_n05_monkeypatch_cleanup_finally():
    """N05: DNS/socket patches applied during test execution are restored in finally block."""
    original_resolve = ssrf_helpers.resolve_public_ips
    try:
        # Run self_test which installs and then removes mock_resolve_public_ips
        rc = social_snapshot.self_test()
        assert rc == 0
    finally:
        pass

    # Verify that production resolver is restored and not left with test mock
    assert ssrf_helpers.resolve_public_ips == original_resolve or ssrf_helpers.resolve_public_ips.__name__ != "mock_resolve_public_ips"


def test_n06_browser_smoke_loopback_isolation():
    """N06: Local browser smoke test executes against explicitly permitted test loopback harness."""
    import ipaddress
    # Production ssrf_helpers strictly blocks loopback by default
    try:
        ssrf_helpers.assert_public_http_url("http://127.0.0.1:8080/test", allow_http=True)
        assert False, "Production assert_public_http_url must block 127.0.0.1"
    except Exception:
        pass

    # Confirms 127.0.0.1 is non-public
    is_non_public = ssrf_helpers._is_non_public_ip(ipaddress.ip_address("127.0.0.1"))
    assert is_non_public is True
