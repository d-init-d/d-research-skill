"""
Pytest integration test executing the dynamic site fixture verification runner
and validating zero precomputed answer strings (W03.03, W03.04).
"""

import subprocess
import sys
from pathlib import Path

DYNAMIC_SITE_DIR = Path(__file__).parent / "fixtures" / "dynamic_site"

def test_initial_html_contains_zero_precomputed_answers():
    """W03.04: Confirm index.html contains zero forbidden answer strings."""
    index_path = DYNAMIC_SITE_DIR / "index.html"
    assert index_path.exists(), "Missing index.html"
    content = index_path.read_text(encoding="utf-8")
    
    forbidden_strings = [
        "2026-08-28",
        "Settings > Data Management > Export CSV",
        "CSV không bị loại bỏ",
        "EX-21",
        "01:42",
        "Đính chính: Tính năng xuất CSV",
        "Phương pháp tái hiện lỗi sync",
    ]
    for s in forbidden_strings:
        assert s not in content, f"Integrity error: index.html contains precomputed answer '{s}'"

def test_playwright_dynamic_site_interaction():
    """W03.03: Execute Playwright interactive 7-step test via verify_dynamic_site.mjs."""
    script_path = DYNAMIC_SITE_DIR / "verify_dynamic_site.mjs"
    assert script_path.exists(), "Missing verify_dynamic_site.mjs"
    
    proc = subprocess.run(
        ["node", str(script_path)],
        cwd=str(Path(__file__).parent.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30
    )
    assert proc.returncode == 0, f"Dynamic site test failed with output:\n{proc.stdout}\n{proc.stderr}"
    assert "ALL 7 INTERACTIVE STEPS AND W03.04 INTEGRITY CHECKS PASSED PERFECTLY!" in proc.stdout
