"""
test_lineage_and_claim_policy.py - Acceptance Tests for DRS-1.1 Package W08 (D01 - D08).
"""

import json
from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lineage_tracker import (
    LineageTracker,
    UnifiedClaimAssessor,
    NegationContextAnalyzer,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _verified_evidence(source_id, lineage_id, source_url, source_kind="primary"):
    return {
        "source_id": source_id,
        "activity_id": f"act-{source_id}",
        "capture_id": f"cap-{source_id}",
        "source_url": source_url,
        "source_kind": source_kind,
        "lineage_id": lineage_id,
        "verification_status": "verified",
        "supports_claim": True,
        "content_hash": "sha256:" + "a" * 64,
        "integrity_status": "live_intact",
    }


def test_d01_official_corporate_social_post():
    """Acceptance D01: Official corporate social post asserting claim X admitted under statement_made."""
    assessor = UnifiedClaimAssessor()
    res = assessor.assess_claim(
        claim_id="CLM-OFFICIAL-01",
        claim_text="Tất cả các lỗi liên quan đến EX-21 đã được giải quyết triệt để trong bản 2.1.1.",
        claim_kind="statement_made",
        speaker_identity="official",
        speaker_relationship="authorized_representative",
        content_origin="original",
        independent_origins=1,
        integrity_status="live_intact",
        evidence_records=[
            _verified_evidence(
                "SRC-OFFICIAL-01",
                "LIN-OFFICIAL-01",
                "https://official.example/releases/2.1.1",
                "official",
            )
        ],
    )

    assert res.reporting_disposition == "main_findings"
    assert res.verification_state == "statement_confirmed"
    assert "Official authoritative source confirms that the statement was made" in res.reasons[0]


def test_d02_firsthand_user_experience():
    """Acceptance D02: Firsthand user experience from pseudonymous account retained with attribution."""
    assessor = UnifiedClaimAssessor()
    res = assessor.assess_claim(
        claim_id="CLM-USER-01",
        claim_text="Tôi đã cài bản 2.1 trên Windows 11 và gặp lỗi văng app khi chọn đồng bộ thư mục tiếng Việt.",
        claim_kind="firsthand_account",
        speaker_identity="pseudonymous",
        speaker_relationship="firsthand",
        content_origin="original",
        independent_origins=1,
        integrity_status="live_intact"
    )

    assert res.reporting_disposition == "firsthand_unverified"
    assert res.verification_state == "firsthand_unverified"
    assert any("firsthand_unverified" in r for r in res.reasons)


def test_d03_d04_viral_repost_lineage_deduplication():
    """Acceptance D03, D04: 10 viral reposts collapsed into 1 root origin; exactly 2 independent origins."""
    fixture_path = FIXTURES_DIR / "lineage_repost_fixtures.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        fixture_data = json.load(f)

    tracker = LineageTracker()
    summary = tracker.add_from_fixture(fixture_data)

    assert summary.total_sources_observed == 12  # 1 origin + 10 derivative reposts + 1 independent study
    assert summary.total_independent_origins == 2  # ORIGIN-POST-001 and ORIGIN-STUDY-002
    assert summary.derivative_source_count == 10
    assert "ORIGIN-POST-001" in summary.independent_origin_ids
    assert "ORIGIN-STUDY-002" in summary.independent_origin_ids
    assert len(summary.origins["ORIGIN-POST-001"]) == 11  # root + 10 reposts


def test_d05_community_lead_verified_by_primary_docs():
    """Acceptance D05: Community lead verified against primary documentation admitted into main_findings."""
    assessor = UnifiedClaimAssessor()
    res = assessor.assess_claim(
        claim_id="CLM-LEAD-01",
        claim_text="Nút xuất CSV đã được chuyển vào Settings > Data Management > Export CSV.",
        claim_kind="underlying_fact",
        speaker_identity="community_member",
        speaker_relationship="firsthand",
        content_origin="original",
        independent_origins=1,
        corroborating_doc_url="https://docs.lumen.example.com/v2.1/data-export",
        evidence_records=[
            _verified_evidence(
                "SRC-DOC-01",
                "LIN-DOC-01",
                "https://docs.lumen.example.com/v2.1/data-export",
                "documentary",
            )
        ],
    )

    assert res.reporting_disposition == "main_findings"
    assert res.verification_state == "supported"
    assert "corroborated by primary documentary source" in res.reasons[0]


def test_d06_unified_admission_policy_consistency():
    """Acceptance D06: Policy consistently admits supported facts and separates unverified leads."""
    assessor = UnifiedClaimAssessor()

    # Case A: Low confidence single unverified rumor
    res_rumor = assessor.assess_claim(
        claim_id="CLM-RUMOR-01",
        claim_text="Công ty sắp đóng cửa dịch vụ đám mây vào cuối tháng.",
        claim_kind="underlying_fact",
        speaker_identity="anonymous",
        speaker_relationship="unknown",
        content_origin="original",
        independent_origins=1
    )
    assert res_rumor.reporting_disposition == "non_official_unverified_leads"
    assert res_rumor.verification_state == "unverified"

    # Case B: Multi-origin corroborated fact
    res_corrob = assessor.assess_claim(
        claim_id="CLM-CORROB-01",
        claim_text="Phiên bản 2.1 nâng cấp thuật toán mã hóa lên AES-256-GCM.",
        claim_kind="underlying_fact",
        speaker_identity="verified_expert",
        speaker_relationship="firsthand",
        content_origin="original",
        independent_origins=3,
        evidence_records=[
            _verified_evidence("SRC-01", "LIN-01", "https://one.example/finding"),
            _verified_evidence("SRC-02", "LIN-02", "https://two.example/finding"),
        ],
    )
    assert res_corrob.reporting_disposition == "main_findings"
    assert res_corrob.verification_state == "supported"


def test_d07_official_silence_with_social_allegations():
    """Acceptance D07: Official silence does not prove coverup; allegations kept as unverified leads."""
    assessor = UnifiedClaimAssessor()
    res = assessor.assess_claim(
        claim_id="CLM-SILENCE-01",
        claim_text="Cộng đồng nghi ngờ công ty cố tình che giấu việc máy chủ dữ liệu bị tấn công.",
        claim_kind="opinion",
        speaker_identity="community_collective",
        speaker_relationship="observer",
        content_origin="original",
        independent_origins=1,
        is_official_silence_case=True
    )

    assert res.reporting_disposition == "non_official_unverified_leads"
    assert res.verification_state == "unverified"
    assert "Official silence noted" in res.reasons[0]


def test_d08_quote_embedded_in_negation_context():
    """Acceptance D08: Negation context detected and underlying fact not elevated to supported."""
    analyzer = NegationContextAnalyzer()

    # Vietnamese negation check
    has_neg_vi, note_vi = analyzer.analyze("Người đại diện khẳng định hoàn toàn không có bằng chứng rằng máy chủ bị xâm nhập.")
    assert has_neg_vi is True
    assert "hoàn toàn không có" in note_vi

    # English negation check
    has_neg_en, note_en = analyzer.analyze("The official report states there is no evidence that customer data was leaked.")
    assert has_neg_en is True
    assert "no evidence that" in note_en

    # Assessor handling of negated quote
    assessor = UnifiedClaimAssessor()
    res = assessor.assess_claim(
        claim_id="CLM-NEG-01",
        claim_text="Hoàn toàn không có bằng chứng rằng dữ liệu khách hàng bị rò rỉ.",
        claim_kind="underlying_fact",
        speaker_identity="official",
        speaker_relationship="authorized_representative",
        content_origin="original",
        independent_origins=2,
        evidence_records=[
            _verified_evidence("SRC-NEG-01", "LIN-NEG-01", "https://one.example/denial"),
            _verified_evidence("SRC-NEG-02", "LIN-NEG-02", "https://two.example/denial"),
        ],
    )

    assert res.has_negation_context is True
    assert res.verification_state == "statement_confirmed"
    assert any("downgraded to statement_confirmed to preserve semantics" in r for r in res.reasons)


def test_url_only_and_unresolved_origin_count_never_promote_claim():
    assessor = UnifiedClaimAssessor()
    result = assessor.assess_claim(
        claim_id="CLM-UNREAD-URL",
        claim_text="An audit-only event is confirmed.",
        claim_kind="underlying_fact",
        speaker_identity="unknown",
        speaker_relationship="unknown",
        content_origin="original",
        independent_origins=99,
        corroborating_doc_url="https://example.invalid/never-read-source",
    )
    assert result.verification_state == "unverified"
    assert result.reporting_disposition == "non_official_unverified_leads"
    assert result.independent_origin_count == 0
