import sys
from pathlib import Path

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import quality_eval


def test_d07_negation_and_number_inversion():
    """D07: Normalization preserves negation, numbers, units, versions, and percentages."""
    cases = [
        # Negation inversion: positive claim vs negative evidence
        {
            "claim": "The proposed constitutional amendment was approved by parliament.",
            "evidence": "The proposed constitutional amendment was not approved by parliament.",
            "expected_reason": "negation_inversion",
        },
        # Percentage mismatch
        {
            "claim": "The algorithm achieved 95% classification accuracy on the test set.",
            "evidence": "The algorithm achieved 72% classification accuracy on the test set.",
            "expected_reason": "percentage_mismatch",
        },
        # Unit mismatch
        {
            "claim": "The payload mass is 500 kg.",
            "evidence": "The payload mass is 500 lbs.",
            "expected_reason": "unit_mismatch",
        },
        # Quantity mismatch
        {
            "claim": "The payload mass is 500 kg.",
            "evidence": "The payload mass is 250 kg.",
            "expected_reason": "quantity_mismatch",
        },
        # Year mismatch
        {
            "claim": "The foundation was established in 1995.",
            "evidence": "The foundation was established in 2012.",
            "expected_reason": "year_mismatch",
        },
        # Version mismatch
        {
            "claim": "The release includes engine version 4.2.0.",
            "evidence": "The release includes engine version 3.1.8.",
            "expected_reason": "version_mismatch",
        },
    ]

    for c in cases:
        row = {
            "claim_id": "C700",
            "claim": c["claim"],
            "evidence": c["evidence"],
            "quote_or_anchor": c["claim"],
            "source_url": "https://example.com/spec",
            "confidence": "high",
        }
        res = quality_eval.classify_claim_evidence(c["claim"], c["evidence"], row)
        assert res["status"] in {"contradicts", "refutes", "insufficient"}
        assert res.get("supports_claim") is False
        assert res.get("contradicts_claim") is True
        assert res.get("reason") == c["expected_reason"]
