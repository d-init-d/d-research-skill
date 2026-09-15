"""
test_reconciliation.py - Acceptance Tests for DRS-1.1 Package W09 (E03 - E06).
"""

import json
from pathlib import Path
import sys
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from reconciliation import (
    CrossBranchReconciler,
    DiscrepancyPair,
    TimelineEvent,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def test_e03_scope_distinction_desktop_vs_mobile():
    """Acceptance E03: Platform scope nuance (Desktop vs Mobile) classified as scope_refinement."""
    reconciler = CrossBranchReconciler()
    pair = reconciler.reconcile_pair(
        pair_id="PAIR-SCOPE-01",
        initial_claim_id="CLM-01",
        initial_text="Trên ứng dụng di động Mobile App, nút xuất CSV không còn hiển thị.",
        initial_source="https://community.example.com/mobile-issues",
        competing_claim_id="CLM-02",
        competing_text="Trên phiên bản Desktop máy tính macOS và Windows, tính năng xuất CSV nằm trong Settings > Data Management.",
        competing_source="https://docs.example.com/desktop-guide"
    )

    assert pair.discrepancy_kind == "scope_refinement"
    assert pair.resolution_status == "resolved"
    assert "Desktop" in pair.reconciliation_summary
    assert "Mobile" in pair.reconciliation_summary


def test_e04_social_correction_refutes_initial_assertion():
    """Acceptance E04: Authoritative correction refutes feature removal rumor and provides path."""
    reconciler = CrossBranchReconciler()
    pair = reconciler.reconcile_pair(
        pair_id="PAIR-CORR-01",
        initial_claim_id="CLM-INIT-01",
        initial_text="Lumen 2.1 đã loại bỏ hoàn toàn tính năng xuất dữ liệu định dạng CSV.",
        initial_source="https://forum.example.vn/thread/102",
        competing_claim_id="CLM-CORR-01",
        competing_text="Đính chính quan trọng: Tính năng xuất CSV không bị loại bỏ mà được chuyển vào Settings > Export trên Desktop.",
        competing_source="https://forum.example.vn/thread/102#reply-2",
        is_authoritative_correction=True
    )

    assert pair.discrepancy_kind == "refuted_by_correction"
    assert pair.resolution_status == "resolved"
    assert "Settings > Export" in pair.resolved_consensus


def test_e05_archaeological_stratigraphy_vs_popular_interpretation():
    """Acceptance E05: Radiocarbon stratigraphy retained over sensational speculation."""
    reconciler = CrossBranchReconciler()
    pair = reconciler.reconcile_pair(
        pair_id="PAIR-ARCH-01",
        initial_claim_id="CLM-C14-01",
        initial_text="Kết quả định niên đại C14 và địa tầng khảo cổ tại hố khai quật xác định niên đại hiện vật từ 1200 - 1000 TCN.",
        initial_source="https://archaeology.gov.vn/report-2026",
        competing_claim_id="CLM-MEDIA-01",
        competing_text="Báo mạng đưa tin giả thuyết giật gân về nền văn minh bí ẩn 10.000 năm trước.",
        competing_source="https://sensational-news.example.com/mystery"
    )

    assert pair.discrepancy_kind == "interpretive_divergence"
    assert pair.resolution_status == "resolved"
    assert "stratigraphy/radiocarbon" in pair.reconciliation_summary


def test_e06_systematic_review_retracted_paper():
    """Acceptance E06: Journal retraction notice supersedes retracted candidate paper."""
    reconciler = CrossBranchReconciler()
    pair = reconciler.reconcile_pair(
        pair_id="PAIR-RETRACT-01",
        initial_claim_id="CLM-PAPER-01",
        initial_text="Nghiên cứu A công bố hiệu quả vượt trội của phương pháp X.",
        initial_source="https://journal.example.org/paper-123",
        competing_claim_id="CLM-RETRACT-01",
        competing_text="Tạp chí đã chính thức rút bài (retract) nghiên cứu A do sai sót trong bộ dữ liệu thực nghiệm.",
        competing_source="https://journal.example.org/retraction-notice-123"
    )

    assert pair.discrepancy_kind == "temporal_evolution"
    assert pair.resolution_status == "resolved"
    assert "retraction" in pair.reconciliation_summary.lower()


def test_reconcile_fixtures_integration():
    """Tests reconciliation engine on correction_pairs_fixtures.json."""
    fixture_path = FIXTURES_DIR / "correction_pairs_fixtures.json"
    reconciler = CrossBranchReconciler()
    report = reconciler.reconcile_from_fixtures(fixture_path)

    assert report.total_discrepancies >= 2
    assert report.resolved_count >= 2
    assert len(report.timeline) >= 4
    # Ensure timeline is chronologically sorted
    timestamps = [t.timestamp for t in report.timeline]
    assert timestamps == sorted(timestamps)
