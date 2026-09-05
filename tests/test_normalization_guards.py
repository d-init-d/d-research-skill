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


def test_vdr07_sign_flip_and_unit_change():
    """VDR07: Sign flip (-5 to +5), decimal changes, percentage differences, and unit switches.

    Normalization must never collapse these into matches; strict mode blocks them.
    """
    import report_render

    cases = [
        # Sign flip
        ("-5 degrees Celsius", "+5 degrees Celsius", "sign_inversion"),
        # Decimal difference
        ("latency was 3.14 ms", "latency was 3.15 ms", "quantity_mismatch"),
        # Percentage difference
        ("grew by 50%", "grew by 55%", "percentage_mismatch"),
        # Unit switch
        ("distance was 10 km", "distance was 10 miles", "unit_mismatch"),
    ]
    for claim_part, ev_part, exp_reason in cases:
        row = {
            "claim_id": "C701",
            "claim": f"Test result shows {claim_part}.",
            "evidence": f"Actual measured data shows {ev_part}.",
            "quote_or_anchor": ev_part,
            "source_url": "https://example.com/data",
            "confidence": "high",
        }
        res = quality_eval.classify_claim_evidence(row["claim"], row["evidence"], row)
        assert res["status"] in {"contradicts", "refutes", "insufficient"}
        assert res.get("supports_claim") is False

        status, reason, _ = report_render._statement_supported_by_row(row["claim"], row, None)
        assert status in {"contradicts", "insufficient"}


def test_vdr08_negation_subject_year_distortion():
    """VDR08: Negation inversion, subject swap, year distortion, or certainty alteration.

    Evaluator must classify as contradicts or requires_review; token overlap cannot fabricate support.
    """
    import report_render

    cases = [
        # Negation inversion
        (
            "The court did not find liability.",
            "The court found liability.",
            "negation_inversion",
        ),
        # Subject swap / direction swap
        (
            "Acme Corp acquired Global Industries.",
            "Global Industries acquired Acme Corp.",
            "citation_does_not_support_statement",
        ),
        # Year mismatch
        (
            "The treaty was signed in 1999.",
            "The treaty was signed in 2005.",
            "year_mismatch",
        ),
    ]
    for claim_text, ev_text, exp_reason in cases:
        row = {
            "claim_id": "C801",
            "claim": claim_text,
            "evidence": ev_text,
            "quote_or_anchor": ev_text,
            "source_url": "https://example.com/record",
            "confidence": "high",
        }
        res = quality_eval.classify_claim_evidence(claim_text, ev_text, row)
        assert res["status"] in {"contradicts", "refutes", "insufficient", "requires_review"}
        assert res.get("supports_claim") is False

        status, reason, _ = report_render._statement_supported_by_row(claim_text, row, None)
        assert status in {"contradicts", "insufficient", "requires_review"}
