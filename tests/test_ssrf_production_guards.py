import ipaddress
import sys
from pathlib import Path

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import _ssrf_helpers as ssrf_helpers


def test_n04_ssrf_production_inviolability():
    """N04: Production SSRF guards strictly block loopback, private subnets, link-local, and IPv4-mapped addresses."""
    forbidden_urls = [
        "http://127.0.0.1/",
        "http://127.0.0.1:8080/secret",
        "http://localhost/",
        "http://10.0.0.1/",
        "http://10.254.0.1/admin",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://[::ffff:169.254.169.254]/",
        "http://[fe80::1]/",
        "http://[fc00::1]/",
    ]

    for url in forbidden_urls:
        blocked = False
        try:
            ssrf_helpers.assert_public_http_url(url, allow_http=True)
        except Exception as exc:
            blocked = True
            msg = str(exc).lower()
            assert (
                "non-public" in msg
                or "blocked" in msg
                or "not allowed" in msg
                or "loopback" in msg
                or "private" in msg
            )
        assert blocked is True, f"Failed to block dangerous URL: {url}"

    # Also verify IP classification helper directly
    forbidden_ips = [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.0.1",
        "169.254.169.254",
        "::1",
        "::ffff:127.0.0.1",
        "::ffff:192.168.1.1",
        "fe80::1",
        "fc00::1",
    ]
    for ip_str in forbidden_ips:
        addr = ipaddress.ip_address(ip_str)
        assert ssrf_helpers._is_non_public_ip(addr) is True, f"Failed to identify non-public IP: {ip_str}"

    # Verify that genuine public IP is recognized as public
    public_addr = ipaddress.ip_address("8.8.8.8")
    assert ssrf_helpers._is_non_public_ip(public_addr) is False
