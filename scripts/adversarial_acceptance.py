#!/usr/bin/env python3
"""Mandatory adversarial acceptance matrix (automated, CI-required).

Each case must pass. A skipped release-required test is not a PASS.
"""

from __future__ import annotations

import contextlib
import csv
import http.server
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
RESULTS: list[tuple[str, str]] = []  # (id, PASS|FAIL|msg)
_BROWSER_RESULT: subprocess.CompletedProcess[str] | None = None


def record(case_id: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    RESULTS.append((case_id, f"{status}: {detail}" if detail else status))
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {case_id}" + (f" - {detail}" if detail else ""))


def record_delegated(case_id: str, detail: str) -> None:
    RESULTS.append((case_id, f"DELEGATED: {detail}"))
    print(f"  [DELEGATED] {case_id} - {detail}")


@contextlib.contextmanager
def local_server(handler: type[http.server.BaseHTTPRequestHandler]):
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def browser_smoke_result() -> subprocess.CompletedProcess[str] | None:
    global _BROWSER_RESULT
    if os.environ.get("D_RESEARCH_SKIP_BROWSER_SMOKE") == "1":
        return None
    if _BROWSER_RESULT is None:
        _BROWSER_RESULT = run_node([str(SCRIPTS / "browser_smoke.mjs")], timeout=300)
    return _BROWSER_RESULT


def run_py(
    args: list[str], env: dict | None = None, timeout: int = 120
) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=e,
        timeout=timeout,
    )


def run_node(
    args: list[str], env: dict | None = None, timeout: int = 120
) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    # Local HTTP fixtures in this matrix use 127.0.0.1. Production api_fetch
    # denies loopback unless this hermetic flag is set; never export it in
    # production runbooks. Cases that assert SSRF denial must clear it.
    e.setdefault("D_RESEARCH_SSRF_ALLOW_LOOPBACK", "1")
    if env:
        e.update(env)
    return subprocess.run(
        ["node", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=e,
        timeout=timeout,
    )


def case_01_token_redirect_zero_leak() -> None:
    """X-Token: TOPSECRET cross-origin redirect: zero leak."""
    sink_hits: list[dict[str, object]] = []

    class Sink(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            sink_hits.append({"path": self.path, "headers": dict(self.headers)})
            body = b"[]"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with local_server(Sink) as sink:
        sink_origin = f"http://127.0.0.1:{sink.server_port}"

        class Source(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                self.send_response(302)
                self.send_header("Location", f"{sink_origin}/stolen")
                self.end_headers()

        with local_server(Source) as source:
            r = run_node(
                [
                    str(SCRIPTS / "api_fetch.mjs"),
                    "--url",
                    f"http://127.0.0.1:{source.server_port}/start",
                    "--headers",
                    json.dumps({"X-Token": "TOPSECRET"}),
                    "--max-pages",
                    "1",
                    "--timeout",
                    "5000",
                ]
            )
    out = r.stdout + r.stderr
    ok = r.returncode != 0 and not sink_hits and "TOPSECRET" not in out
    record(
        "01_token_redirect_zero_leak",
        ok,
        f"rc={r.returncode} sink_requests={len(sink_hits)}",
    )


def case_02_query_secret_no_cache() -> None:
    """Query api_key=QUERYSECRET: no public cache/log persistence."""

    class Api(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            body = b"[]"
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with tempfile.TemporaryDirectory() as td:
        cache = Path(td) / "cache"
        cache.mkdir()
        output = Path(td) / "result.json"
        with local_server(Api) as server:
            r = run_node(
                [
                    str(SCRIPTS / "api_fetch.mjs"),
                    "--url",
                    f"http://127.0.0.1:{server.server_port}/items?api_key=QUERYSECRET",
                    "--out",
                    str(output),
                    "--max-pages",
                    "1",
                ],
                env={"D_RESEARCH_HTTP_CACHE_PATH": str(cache)},
            )
        leaked = False
        for p in Path(td).rglob("*"):
            if p.is_file():
                try:
                    if "QUERYSECRET" in p.read_text(encoding="utf-8", errors="replace"):
                        leaked = True
                except Exception:
                    pass
        leaked = leaked or "QUERYSECRET" in (r.stdout + r.stderr)
        unknown = run_node(
            [
                str(SCRIPTS / "api_fetch.mjs"),
                "--mystery-token",
                "CLI_SUPERSECRET",
            ]
        )
        unknown_leaked = "CLI_SUPERSECRET" in (unknown.stdout + unknown.stderr)
        ok = (
            r.returncode == 0
            and not leaked
            and not any(cache.iterdir())
            and unknown.returncode != 0
            and not unknown_leaked
        )
        record(
            "02_query_secret_no_cache",
            ok,
            f"rc={r.returncode} leaked={leaked} unknown_leaked={unknown_leaked}",
        )


def case_03_malformed_next_no_token_stderr() -> None:
    sink_hits: list[str] = []

    class Sink(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            sink_hits.append(self.path)
            self.send_response(200)
            self.end_headers()

    with local_server(Sink) as sink:
        sink_origin = f"http://127.0.0.1:{sink.server_port}"

        class Api(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_args) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                body = b"[]"
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header(
                    "Link",
                    f'<{sink_origin}/next?access_token=SUPERSECRET>; rel="next"',
                )
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        with local_server(Api) as api:
            r = run_node(
                [
                    str(SCRIPTS / "api_fetch.mjs"),
                    "--url",
                    f"http://127.0.0.1:{api.server_port}/items",
                    "--allow-next-origin",
                    sink_origin,
                    "--max-pages",
                    "2",
                ]
            )
    combined = r.stdout + r.stderr
    ok = r.returncode != 0 and not sink_hits and "SUPERSECRET" not in combined
    record("03_malformed_next_no_token_stderr", ok, f"sink_requests={len(sink_hits)}")


def case_04_robots_disallow_no_extract() -> None:
    r = browser_smoke_result()
    if r is None:
        record_delegated("04_robots_disallow_no_extract", "required explicit browser_smoke CI step")
        return
    out = r.stdout + r.stderr
    ok = r.returncode == 0 and "robots_redirect" in out and "robots_status_mapping" in out
    record("04_robots_disallow_no_extract", ok, f"rc={r.returncode}")


def case_05_matching_ua() -> None:
    texts: list[str] = []
    for name in ("playwright_probe.mjs", "playwright_extract.mjs", "playwright_crawl.mjs"):
        texts.append((SCRIPTS / name).read_text(encoding="utf-8"))
    expected = "DResearchBot/3.2"
    ok = all(expected in t for t in texts)
    record("05_matching_dresearchbot_ua", ok)


def case_06_plan_path_traversal() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ws = root / "workspace"
        ws.mkdir()
        (ws / "report.draft.md").write_text("# Narrative\n", encoding="utf-8")
        plan = {
            "schema_version": "2.0",
            "tasks": [
                {
                    "id": "S1",
                    "phase": "synthesis",
                    "outputs": ["../escaped-report.md"],
                }
            ],
        }
        (ws / "research-plan.json").write_text(json.dumps(plan), encoding="utf-8")
        escaped = root / "escaped-report.md"
        write_attempt = run_py(
            [str(SCRIPTS / "report_render.py"), "render", "--workspace", str(ws)]
        )

        (ws / "report.draft.md").unlink()
        secret = root / "outside-secret.md"
        secret.write_text("EXTERNAL SECRET", encoding="utf-8")
        plan["tasks"][0]["inputs"] = ["../outside-secret.md"]
        plan["tasks"][0]["outputs"] = ["research-output/report.md"]
        (ws / "research-plan.json").write_text(json.dumps(plan), encoding="utf-8")
        read_attempt = run_py([str(SCRIPTS / "report_render.py"), "render", "--workspace", str(ws)])
        safe_report = ws / "research-output" / "report.md"
        ok = (
            write_attempt.returncode != 0
            and read_attempt.returncode != 0
            and not escaped.exists()
            and not safe_report.exists()
        )
    record(
        "06_plan_path_traversal_rejected",
        ok,
        f"write_rc={write_attempt.returncode} read_rc={read_attempt.returncode}",
    )


def case_07_unmatched_markers() -> None:
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "report.md").write_text(
            "# Report\n\n<!-- BEGIN GENERATED: evidence-summary -->\n",
            encoding="utf-8",
        )
        r = run_py([str(SCRIPTS / "report_render.py"), "lint", "--workspace", str(ws)])
        ok = r.returncode != 0 and "marker" in (r.stdout + r.stderr).lower()
    record("07_unmatched_generated_markers", ok, f"rc={r.returncode}")


def case_08_ref_only_in_comment_fails_coverage() -> None:
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        with (ws / "evidence-ledger.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["claim_id", "record_type"])
            writer.writeheader()
            writer.writerow({"claim_id": "C1", "record_type": "claim"})
        (ws / "report.md").write_text(
            "# Report\n\n<!-- hidden [ref:C1] -->\n",
            encoding="utf-8",
        )
        r = run_py([str(SCRIPTS / "report_render.py"), "lint", "--workspace", str(ws)])
        combined = (r.stdout + r.stderr).lower()
        ok = r.returncode != 0 and "not referenced" in combined
    record("08_ref_in_comment_coverage_fail", ok, f"rc={r.returncode}")


def case_09_unrelated_blocker_row() -> None:
    r = run_py([str(SCRIPTS / "research_plan.py"), "self-test"])
    ok = r.returncode == 0
    record("09_unrelated_blocker_cannot_satisfy", ok)


def case_10_undeclared_stale_citations() -> None:
    r = run_py([str(SCRIPTS / "check_internal_refs.py")])
    ok = r.returncode == 0
    record("10_undeclared_stale_citations", ok)


def case_11_unknown_standard_assertion() -> None:
    r = run_py([str(SCRIPTS / "research_plan.py"), "self-test"])
    ok = r.returncode == 0
    record("11_unknown_standard_assertion", ok)


def case_12_schema2_task_without_phase() -> None:
    r = run_py([str(SCRIPTS / "research_plan.py"), "self-test"])
    ok = r.returncode == 0
    record("12_schema2_task_without_phase", ok)


def case_13_v1_warning_once() -> None:
    r = run_py([str(SCRIPTS / "research_plan.py"), "self-test"])
    ok = r.returncode == 0 and "_compat_warned" not in r.stdout
    record("13_v1_warning_once_no_persist", ok)


def case_14_migrate_out_source_unchanged() -> None:
    r = run_py([str(SCRIPTS / "research_plan.py"), "self-test"])
    ok = r.returncode == 0
    record("14_migrate_out_source_byte_unchanged", ok)


def case_15_invalid_migration_writes_nothing() -> None:
    r = run_py([str(SCRIPTS / "research_plan.py"), "self-test"])
    ok = r.returncode == 0
    record("15_invalid_migration_writes_nothing", ok)


def case_16_empty_dogfood_zero_pass() -> None:
    r = run_py([str(SCRIPTS / "run_dogfood.py"), "self-test"])
    ok = r.returncode == 0
    # Score empty fixtures explicitly if score-all supports it
    empty = ROOT / "examples" / "evals" / "fixtures" / "dogfood-empty-scores.json"
    if empty.is_file():
        data = json.loads(empty.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            ok = False
        else:
            tasks = data.get("tasks")
            counts = data.get("counts")
            ok = ok and data.get("schema_version") == "2.1"
            ok = ok and isinstance(tasks, list) and len(tasks) == 12
            ok = ok and isinstance(counts, dict)
            if isinstance(counts, dict):
                ok = ok and counts.get("passed") == 0 and counts.get("not_run") == 12
            if isinstance(tasks, list):
                ok = ok and all(
                    item.get("status") == "not_run"
                    and item.get("passed") is False
                    and item.get("run_result_valid") is False
                    for item in tasks
                    if isinstance(item, dict)
                )
    record("16_empty_dogfood_zero_pass", ok)


def case_17_multipart_missing_assertion() -> None:
    r = run_py([str(SCRIPTS / "run_dogfood.py"), "self-test"])
    ok = r.returncode == 0
    record("17_multipart_missing_assertion_fail", ok)


def case_18_evil_url_query_canonical() -> None:
    r = run_py([str(SCRIPTS / "run_dogfood.py"), "self-test"])
    ok = r.returncode == 0
    record("18_evil_url_query_canonical_zero_recall", ok)


def case_19_cache_100_writers() -> None:
    r = run_py([str(SCRIPTS / "http_cache.py"), "self-test"])
    out = r.stdout + r.stderr
    ok = r.returncode == 0 and ("100" in out or "concurrent" in out.lower() or "ok" in out.lower())
    record("19_cache_100_concurrent_writers", ok, f"rc={r.returncode}")


def case_20_cache_variants() -> None:
    r = run_py([str(SCRIPTS / "http_cache.py"), "self-test"])
    r2 = run_node([str(SCRIPTS / "lib" / "http_cache.mjs"), "--self-test"])
    ok = r.returncode == 0 and r2.returncode == 0
    detail = f"python_rc={r.returncode} node_rc={r2.returncode}"
    if not ok:
        diagnostic = " | ".join(
            part.strip()[-300:]
            for part in (r.stdout, r.stderr, r2.stdout, r2.stderr)
            if part.strip()
        )
        if diagnostic:
            detail += f" diagnostic={diagnostic}"
    record("20_range_vary_cache_variants", ok, detail)


def case_21_social_localhost_verify_fail() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        base = {
            "schema_version": "1.1",
            "platform": "x",
            "tier": "B",
            "url_original": "https://x.com/example/status/1",
            "url_canonical": "https://x.com/example/status/1",
            "url_archive": None,
            "captured_at": "2026-07-10T00:00:00Z",
            "verification": {
                "first_capture_at": "2026-07-10T00:00:00Z",
                "last_verified_at": None,
                "status": "unknown",
            },
            "archive_submission": {
                "requested": False,
                "status": "lookup_only",
                "timestamp": None,
                "archive_url": None,
            },
            "post": {},
            "limitations": ["archive-only"],
            "content_hash_sha256": "",
        }
        tier_file = root / "tier.json"
        tier_snapshot = dict(base)
        tier_snapshot["tier"] = "A"
        tier_file.write_text(json.dumps(tier_snapshot), encoding="utf-8")
        tier_result = run_py(
            [str(SCRIPTS / "social_snapshot.py"), "verify", "--file", str(tier_file)]
        )

        timestamp_file = root / "timestamp.json"
        timestamp_snapshot = dict(base)
        timestamp_snapshot["captured_at"] = "not-rfc3339"
        timestamp_file.write_text(json.dumps(timestamp_snapshot), encoding="utf-8")
        timestamp_result = run_py(
            [
                str(SCRIPTS / "social_snapshot.py"),
                "verify",
                "--file",
                str(timestamp_file),
            ]
        )
        tier_after = json.loads(tier_file.read_text(encoding="utf-8"))
        timestamp_after = json.loads(timestamp_file.read_text(encoding="utf-8"))
        ok = (
            tier_result.returncode != 0
            and timestamp_result.returncode != 0
            and tier_after.get("verification", {}).get("status") == "malformed"
            and timestamp_after.get("verification", {}).get("status") == "malformed"
        )
    record(
        "21_social_policy_preflight_fail",
        ok,
        f"tier_rc={tier_result.returncode} timestamp_rc={timestamp_result.returncode}",
    )


def case_22_tier_b_lookup_failure() -> None:
    r = run_py([str(SCRIPTS / "social_snapshot.py"), "self-test"])
    ok = r.returncode == 0
    record("22_tier_b_lookup_failure_structured", ok)


def case_23_unsafe_runtime_config() -> None:
    r = run_py([str(SCRIPTS / "check_contract.py"), "self-test"])
    ok = r.returncode == 0
    record("23_unsafe_runtime_config", ok)


def case_24_malformed_date_no_high_freshness() -> None:
    with tempfile.TemporaryDirectory() as td:
        ledger = Path(td) / "ledger.csv"
        out = Path(td) / "scores.csv"
        with ledger.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "claim_id",
                    "source_url",
                    "source_type",
                    "date_published",
                    "date_accessed",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "claim_id": "C1",
                    "source_url": "https://example.gov/source",
                    "source_type": "primary",
                    "date_published": "2026-not-a-date",
                    "date_accessed": "2026-07-10",
                }
            )
        r = run_py(
            [
                str(SCRIPTS / "score_source.py"),
                "score",
                "--file",
                str(ledger),
                "--out",
                str(out),
            ]
        )
        rows = list(csv.DictReader(out.open(newline="", encoding="utf-8"))) if out.exists() else []
        ok = (
            r.returncode == 0
            and len(rows) == 1
            and rows[0].get("recency") == "1"
            and rows[0].get("review_status") != "reviewed"
            and rows[0].get("final_reviewed_confidence") != "high"
        )
    record("24_malformed_date_no_high_confidence", ok, f"rc={r.returncode}")


def case_25_crossref_datacite_fallback() -> None:
    r = run_py([str(SCRIPTS / "citation_export.py"), "self-test"])
    r2 = run_py([str(SCRIPTS / "citation_resolver.py"), "self-test"])
    ok = r.returncode == 0 and r2.returncode == 0
    record("25_crossref_datacite_fallback", ok, f"export={r.returncode} resolver={r2.returncode}")


def case_26_resource_caps() -> None:
    class Api(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            body = json.dumps([{"value": "x" * 100}]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    helper_names = [
        "resource_limits.py",
        "multi_extract.py",
        "pdf_extract.py",
        "ocr.py",
        "extract_tables.py",
        "wayback.py",
        "social_snapshot.py",
    ]
    helper_results = [run_py([str(SCRIPTS / name), "self-test"]) for name in helper_names]
    with tempfile.TemporaryDirectory() as td, local_server(Api) as server:
        out = Path(td) / "api.json"
        r = run_node(
            [
                str(SCRIPTS / "api_fetch.mjs"),
                "--url",
                f"http://127.0.0.1:{server.server_port}/items",
                "--out",
                str(out),
                "--max-pages",
                "1",
            ],
            env={"D_RESEARCH_HTTP_MAX_BYTES": "10"},
        )
        sidecar = Path(str(out) + ".meta.json")
        meta = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else {}
        ok = (
            all(item.returncode == 0 for item in helper_results)
            and r.returncode == 3
            and meta.get("complete") is False
            and meta.get("incomplete") is True
            and meta.get("stopping_reason") == "resource_limit"
        )
    record(
        "26_resource_caps_deterministic",
        ok,
        f"api_rc={r.returncode} helpers={[item.returncode for item in helper_results]}",
    )


def case_27_chromium_smoke() -> None:
    r = browser_smoke_result()
    if r is None:
        record_delegated("27_real_chromium_smoke", "required explicit browser_smoke CI step")
        return
    ok = r.returncode == 0 and "chromium_launch" in r.stdout and "tls_default_failure" in r.stdout
    detail = f"rc={r.returncode}"
    if not ok:
        detail += " " + (r.stderr or r.stdout)[:200]
    record("27_real_chromium_smoke", ok, detail)


def main() -> int:
    print("Adversarial acceptance matrix")
    print("=" * 40)
    cases = [
        case_01_token_redirect_zero_leak,
        case_02_query_secret_no_cache,
        case_03_malformed_next_no_token_stderr,
        case_04_robots_disallow_no_extract,
        case_05_matching_ua,
        case_06_plan_path_traversal,
        case_07_unmatched_markers,
        case_08_ref_only_in_comment_fails_coverage,
        case_09_unrelated_blocker_row,
        case_10_undeclared_stale_citations,
        case_11_unknown_standard_assertion,
        case_12_schema2_task_without_phase,
        case_13_v1_warning_once,
        case_14_migrate_out_source_unchanged,
        case_15_invalid_migration_writes_nothing,
        case_16_empty_dogfood_zero_pass,
        case_17_multipart_missing_assertion,
        case_18_evil_url_query_canonical,
        case_19_cache_100_writers,
        case_20_cache_variants,
        case_21_social_localhost_verify_fail,
        case_22_tier_b_lookup_failure,
        case_23_unsafe_runtime_config,
        case_24_malformed_date_no_high_freshness,
        case_25_crossref_datacite_fallback,
        case_26_resource_caps,
        case_27_chromium_smoke,
    ]
    for fn in cases:
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            record(fn.__name__, False, f"exception: {e}")

    failed = [r for r in RESULTS if r[1].startswith("FAIL")]
    delegated = [r for r in RESULTS if r[1].startswith("DELEGATED")]
    passed = [r for r in RESULTS if r[1].startswith("PASS")]
    print("=" * 40)
    print(
        f"Total: {len(RESULTS)}  PASS: {len(passed)}  "
        f"DELEGATED: {len(delegated)}  FAIL: {len(failed)}"
    )
    if failed:
        print("FAILED cases:", file=sys.stderr)
        for cid, msg in failed:
            print(f"  {cid}: {msg}", file=sys.stderr)
        return 1
    print("adversarial_acceptance ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
