"""
Unit tests validating the structure, schemas, and integrity of synthetic test fixtures
created for Package W03 (W03.02).
"""

import json
import unicodedata
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"

def test_social_thread_fixture_integrity():
    path = FIXTURES_DIR / "social_thread_fixtures.json"
    assert path.exists(), f"Missing fixture {path}"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    assert data["fixture_id"] == "FIX-THREAD-001"
    assert "root_post" in data
    assert "comments_tree" in data
    assert "virtualized_window_pages" in data
    
    # Verify hierarchical nesting depth
    tree = data["comments_tree"]
    assert len(tree) >= 2
    c2 = next(c for c in tree if c["comment_id"] == "c_02_correction")
    assert c2["is_authoritative_correction"] is True
    assert "Settings > Data Management > Export CSV" in c2["body"]
    assert len(c2["replies"]) >= 2
    
    # Verify virtualized pagination window items
    pages = data["virtualized_window_pages"]
    assert len(pages) == 4
    for pg in pages:
        assert len(pg["item_ids"]) == 4

def test_correction_pairs_fixture_integrity():
    path = FIXTURES_DIR / "correction_pairs_fixtures.json"
    assert path.exists(), f"Missing fixture {path}"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    pairs = data["pairs"]
    assert len(pairs) >= 3
    for pair in pairs:
        assert "initial_assertion" in pair
        assert "correction_assertion" in pair
        assert "reconciliation_rule" in pair
        assert pair["initial_assertion"]["claim_id"].startswith("CLM-INIT")
        assert pair["correction_assertion"]["claim_id"].startswith("CLM-CORR")

def test_lineage_repost_fixture_deduplication():
    path = FIXTURES_DIR / "lineage_repost_fixtures.json"
    assert path.exists(), f"Missing fixture {path}"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    origin = data["origin_source"]
    reposts = data["derivative_reposts"]
    study = data["independent_empirical_study"]
    
    assert origin["is_origin"] is True
    assert len(reposts) == 10
    
    # All 10 reposts must point to the same origin_id
    for rep in reposts:
        assert rep["origin_id"] == origin["origin_id"]
        assert rep["independent_confirmation"] is False
    
    # Independent empirical study has distinct origin_id and independent_confirmation=True
    assert study["origin_id"] != origin["origin_id"]
    assert study["independent_confirmation"] is True
    
    # Distinct origins count
    all_origins = {origin["origin_id"]} | {r["origin_id"] for r in reposts} | {study["origin_id"]}
    assert len(all_origins) == 2, f"Expected exactly 2 independent origins, found {len(all_origins)}"

def test_vietnamese_slang_and_unicode_normalization():
    path = FIXTURES_DIR / "vietnamese_slang_fixtures.json"
    assert path.exists(), f"Missing fixture {path}"
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    terms = data["terms"]
    assert len(terms) >= 4
    for term in terms:
        assert "colloquial_slang" in term
        assert "canonical_technical_term" in term
        assert len(term["expanded_formal_queries"]) >= 2
    
    # Test Unicode NFC / NFD normalization
    cases = data["unicode_diacritic_normalization_cases"]
    c1 = next(c for c in cases if c["case_id"] == "DIACRITIC-01")
    nfd_text = c1["decomposed_nfd"]
    nfc_text = c1["composed_nfc"]
    
    # Raw strings differ in code points
    assert nfd_text != nfc_text
    # Normalized strings must match
    assert unicodedata.normalize("NFC", nfd_text) == unicodedata.normalize("NFC", nfc_text)
