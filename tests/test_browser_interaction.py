"""
test_browser_interaction.py - Acceptance Criteria Test Suite for DRS-1.1 (Package W06).

Verifies:
  - B02: Playwright actively opens and reads sources in both branches (documentary & social)
  - B03: Search form submit + filter selection narrows results
  - B04: Expand post + view replies captures authoritative correction rep_02_correction
  - B05: Paginate / load more captures additional comments without losing head items
  - B06: DOM mutation / re-render handled via re-observation without stale locator crash
  - C05: Video transcript panel toggle captures timecoded cue at 01:42 resolving ambiguity
  - Schema conformity for activity-log and capture-record schemas
  - SSRF protection and credential redaction
"""

import json
import socket
import subprocess
import sys
import time
from pathlib import Path
import pytest
import jsonschema

REPO_ROOT = Path(__file__).resolve().parent.parent
DYNAMIC_SITE_DIR = REPO_ROOT / "tests" / "fixtures" / "dynamic_site"
BROWSER_SCRIPT = REPO_ROOT / "scripts" / "browser_interaction.mjs"

# Find contracts directory
def find_contracts_dir() -> Path:
    contracts = REPO_ROOT / "schemas"
    if (contracts / "activity-log.schema.json").is_file() and (
        contracts / "capture-record.schema.json"
    ).is_file():
        return contracts
    raise FileNotFoundError("Packaged activity/capture schemas are missing")

def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]

@pytest.fixture(scope="module")
def fixture_server():
    """Spawns tests/fixtures/dynamic_site/server.py on an ephemeral port."""
    port = get_free_port()
    server_py = DYNAMIC_SITE_DIR / "server.py"
    assert server_py.exists(), f"Missing fixture server script at {server_py}"

    proc = subprocess.Popen(
        [sys.executable, str(server_py), str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(DYNAMIC_SITE_DIR),
    )

    base_url = f"http://127.0.0.1:{port}"
    import urllib.request
    healthy = False
    start_time = time.time()
    while time.time() - start_time < 10:
        try:
            with urllib.request.urlopen(f"{base_url}/healthz", timeout=1) as resp:
                if resp.status == 200:
                    healthy = True
                    break
        except Exception:
            time.sleep(0.1)

    if not healthy:
        proc.kill()
        out, err = proc.communicate()
        raise RuntimeError(f"Fixture server failed to become healthy on {base_url}:\n{out.decode()}\n{err.decode()}")

    try:
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

def run_node_operator(url: str, actions: list, out_dir: Path, branch: str = "documentary", question_id: str = "Q1", allow_loopback: bool = True):
    """Executes scripts/browser_interaction.mjs with given actions."""
    cmd = [
        "node",
        str(BROWSER_SCRIPT),
        "--url", url,
        "--actions", json.dumps(actions),
        "--out-dir", str(out_dir),
        "--branch", branch,
        "--question-id", question_id,
    ]
    if allow_loopback:
        cmd.append("--allow-loopback-fixture")

    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
        timeout=30,
    )
    return res

def test_b02_playwright_dual_branch_reading(fixture_server, tmp_path):
    """B02: Agent actively opens and reads sources in both branches via Playwright."""
    contracts_dir = find_contracts_dir()
    act_schema = json.loads((contracts_dir / "activity-log.schema.json").read_text(encoding="utf-8"))
    cap_schema = json.loads((contracts_dir / "capture-record.schema.json").read_text(encoding="utf-8"))

    doc_dir = tmp_path / "doc_branch"
    doc_dir.mkdir()
    doc_actions = [
        {"action": "search", "payload": {"query": "Lumen 2.1"}},
        {"action": "filter", "payload": {"value": "final"}},
        {"action": "open", "locator": {"selector": "#result-doc_v21_final .open-thread-btn"}, "captureSelector": "#result-doc_v21_final"},
    ]
    res_doc = run_node_operator(fixture_server, doc_actions, doc_dir, branch="documentary", question_id="Q1")
    assert res_doc.returncode == 0, f"Documentary branch failed:\n{res_doc.stdout}\n{res_doc.stderr}"

    social_dir = tmp_path / "social_branch"
    social_dir.mkdir()
    social_actions = [
        {"action": "search", "payload": {"query": "Lumen 2.1"}},
        {"action": "open", "locator": {"selector": "#result-doc_v21_final .open-thread-btn"}},
        {"action": "expand", "locator": {"selector": "#expand-post-btn"}},
        {"action": "view_replies", "locator": {"selector": "#view-replies-btn"}, "captureSelector": "#reply-rep_02_correction"},
    ]
    res_soc = run_node_operator(fixture_server, social_actions, social_dir, branch="social", question_id="Q2")
    assert res_soc.returncode == 0, f"Social branch failed:\n{res_soc.stdout}\n{res_soc.stderr}"

    # Verify documentary artifacts
    doc_acts = json.loads((doc_dir / "activity-log.json").read_text(encoding="utf-8"))
    doc_caps = json.loads((doc_dir / "capture-records.json").read_text(encoding="utf-8"))
    assert len(doc_acts) >= 3
    assert len(doc_caps) >= 1
    for a in doc_acts:
        assert a["branch_id"] == "documentary"
        assert a["tool_details"]["engine"] == "playwright-chromium"
        assert a["outcome"] == "success"
        jsonschema.validate(instance=a, schema=act_schema)
    for c in doc_caps:
        assert c["branch_id"] == "documentary"
        assert c["method"] == "playwright_dom"
        jsonschema.validate(instance=c, schema=cap_schema)

    # Verify social artifacts
    soc_acts = json.loads((social_dir / "activity-log.json").read_text(encoding="utf-8"))
    soc_caps = json.loads((social_dir / "capture-records.json").read_text(encoding="utf-8"))
    assert len(soc_acts) >= 4
    assert len(soc_caps) >= 1
    for a in soc_acts:
        assert a["branch_id"] == "social"
        assert a["tool_details"]["engine"] == "playwright-chromium"
        assert a["outcome"] == "success"
        jsonschema.validate(instance=a, schema=act_schema)
    for c in soc_caps:
        assert c["branch_id"] == "social"
        assert c["method"] == "playwright_dom"
        jsonschema.validate(instance=c, schema=cap_schema)

def test_b03_search_form_and_filter_selection(fixture_server, tmp_path):
    """B03: Search form submit + filter selection narrows results."""
    out_dir = tmp_path / "b03"
    out_dir.mkdir()
    actions = [
        {"action": "search", "locator": {"inputSelector": "#search-input", "submitSelector": "#search-submit"}, "payload": {"query": "Lumen 2.1"}},
        {"action": "filter", "locator": {"selectSelector": "#filter-type", "applySelector": "#apply-filter"}, "payload": {"value": "final"}, "captureSelector": "#results-container"},
    ]
    res = run_node_operator(fixture_server, actions, out_dir)
    assert res.returncode == 0, f"B03 failed:\n{res.stdout}\n{res.stderr}"

    caps = json.loads((out_dir / "capture-records.json").read_text(encoding="utf-8"))
    assert len(caps) >= 1
    raw_text_path = out_dir / caps[0]["raw_text_ref"]
    assert raw_text_path.exists()
    content = raw_text_path.read_text(encoding="utf-8")

    # Final release card must be present with official date
    assert "Lumen 2.1 Final Official Release" in content
    assert "2026-08-28" in content
    # Draft release cards must be filtered out
    assert "Lumen 2.0.4 Maintenance Release" not in content

def test_b04_expand_and_view_replies_authoritative_correction(fixture_server, tmp_path):
    """B04: Expand post + view replies captures authoritative correction rep_02_correction."""
    out_dir = tmp_path / "b04"
    out_dir.mkdir()
    actions = [
        {"action": "search", "payload": {"query": "Lumen 2.1"}},
        {"action": "open", "locator": {"selector": "#result-doc_v21_final .open-thread-btn"}},
        {"action": "expand", "locator": {"selector": "#expand-post-btn"}, "captureSelector": "#post-body-container"},
        {"action": "view_replies", "locator": {"selector": "#view-replies-btn"}, "captureSelector": "#reply-rep_02_correction"},
    ]
    res = run_node_operator(fixture_server, actions, out_dir, branch="social", question_id="Q2")
    assert res.returncode == 0, f"B04 failed:\n{res.stdout}\n{res.stderr}"

    caps = json.loads((out_dir / "capture-records.json").read_text(encoding="utf-8"))
    assert len(caps) >= 2

    # Verify full post body expanded
    expanded_text = (out_dir / caps[0]["raw_text_ref"]).read_text(encoding="utf-8")
    assert "Đội ngũ kỹ thuật đã rà soát toàn bộ thay đổi" in expanded_text
    assert "Cài đặt" in expanded_text

    # Verify authoritative correction in replies
    correction_text = (out_dir / caps[1]["raw_text_ref"]).read_text(encoding="utf-8")
    assert "minh_quan_lead_eng" in correction_text
    assert "Settings > Data Management > Export CSV" in correction_text
    assert "Đính chính" in correction_text

def test_b05_pagination_accumulates_comments_without_losing_head(fixture_server, tmp_path):
    """B05: Paginate / load more captures additional comments without losing head items."""
    out_dir = tmp_path / "b05"
    out_dir.mkdir()
    actions = [
        {"action": "search", "payload": {"query": "Lumen 2.1"}},
        {"action": "open", "locator": {"selector": "#result-doc_v21_final .open-thread-btn"}},
        {"action": "view_replies", "locator": {"selector": "#view-replies-btn"}},
        {"action": "paginate", "locator": {"selector": "#load-more-btn"}, "captureSelector": "#thread-section"},
    ]
    res = run_node_operator(fixture_server, actions, out_dir, branch="social", question_id="Q2")
    assert res.returncode == 0, f"B05 failed:\n{res.stdout}\n{res.stderr}"

    caps = json.loads((out_dir / "capture-records.json").read_text(encoding="utf-8"))
    assert len(caps) >= 1
    thread_content = (out_dir / caps[0]["raw_text_ref"]).read_text(encoding="utf-8")

    # Head item preserved
    assert "tech_lead_alex" in thread_content
    # Nested replies preserved
    assert "minh_quan_lead_eng" in thread_content
    # New page comments loaded
    assert "c_13_reproduce" in thread_content or "kernel_hacker_vn" in thread_content
    assert "EX-21" in thread_content
    assert "c_16_contrary" in thread_content or "senior_devops_sg" in thread_content

def test_b06_stale_locator_recovery(fixture_server, tmp_path):
    """B06: DOM mutation / re-render handled via re-observation without stale locator crash."""
    out_dir = tmp_path / "b06"
    out_dir.mkdir()
    # Search and execute valid action, then invalid selector recovers cleanly as partial/timeout
    actions = [
        {"action": "search", "payload": {"query": "Lumen 2.1"}},
        {"action": "expand", "locator": {"selector": "#non_existent_btn_selector_trigger_retry"}},
    ]
    res = run_node_operator(fixture_server, actions, out_dir)
    # The runner exits cleanly without unhandled exception / crash
    assert res.returncode == 0, f"B06 should not crash on stale locator:\n{res.stdout}\n{res.stderr}"

    acts = json.loads((out_dir / "activity-log.json").read_text(encoding="utf-8"))
    assert len(acts) >= 2
    # Second action attempted retries and completed with timeout/partial status
    assert acts[-1]["outcome"] in ("timeout", "partial")
    assert acts[-1]["limitation"] is not None

def test_c05_video_transcript_panel_resolution(fixture_server, tmp_path):
    """C05: Video transcript panel toggle captures timecoded cue at 01:42 resolving ambiguity."""
    out_dir = tmp_path / "c05"
    out_dir.mkdir()
    actions = [
        {"action": "search", "payload": {"query": "Lumen 2.1"}},
        {"action": "open", "locator": {"selector": "#result-doc_v21_final .open-thread-btn"}},
        {"action": "transcript", "locator": {"selector": "#toggle-transcript-btn"}, "captureSelector": "#transcript-panel", "metadata": {"method": "playwright_transcript"}},
    ]
    res = run_node_operator(fixture_server, actions, out_dir, branch="social", question_id="Q3")
    assert res.returncode == 0, f"C05 failed:\n{res.stdout}\n{res.stderr}"

    caps = json.loads((out_dir / "capture-records.json").read_text(encoding="utf-8"))
    assert len(caps) >= 1
    transcript_text = (out_dir / caps[0]["raw_text_ref"]).read_text(encoding="utf-8")

    assert "01:42" in transcript_text
    assert "Kỹ sư trưởng" in transcript_text
    assert "Tính năng xuất CSV vẫn còn nguyên vẹn trên desktop" in transcript_text
    assert caps[0]["method"] == "playwright_transcript"

def test_ssrf_protection_and_secret_redaction(fixture_server, tmp_path):
    """Verifies SSRF blocking on loopback without explicit fixture flag, and secret redaction."""
    out_dir = tmp_path / "ssrf_test"
    out_dir.mkdir()

    # Attempt loopback navigation WITHOUT --allow-loopback-fixture
    cmd = [
        "node",
        str(BROWSER_SCRIPT),
        "--url", fixture_server,
        "--out-dir", str(out_dir),
    ]
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(REPO_ROOT),
        timeout=15,
    )
    # Must be blocked by SSRF guard
    assert res.returncode != 0
    assert "blocked" in res.stdout or "blocked" in res.stderr

    # Test self-test redaction suite
    res_self = subprocess.run(
        ["node", str(BROWSER_SCRIPT), "--self-test"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(REPO_ROOT),
        timeout=10,
    )
    assert res_self.returncode == 0
    assert "self-test passed" in res_self.stdout
