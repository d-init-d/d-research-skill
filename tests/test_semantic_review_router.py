import sys
from pathlib import Path

# Add scripts directory to sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import quality_eval


def test_d09_valid_paraphrase_review_route():
    """D09: Claim is a valid paraphrase of evidence but not verbatim character match."""
    # Semantic paraphrase without verbatim quote match
    evidence = (
        "The municipal government concluded negotiations and finalized the public transit budget allocation."
    )
    paraphrase_claim = (
        "The city administration completed the transit funding agreement."
    )
    row = {
        "claim_id": "C900",
        "claim": paraphrase_claim,
        "evidence": evidence,
        "quote_or_anchor": "",
        "source_url": "https://example.com/city-council-transit",
        "confidence": "high",
    }
    res = quality_eval.classify_claim_evidence(paraphrase_claim, evidence, row)
    # Must route to requires_review / semantic adjudication, not falsely reject as contradiction or fabricate supports
    assert res["status"] in {"requires_review", "unsupported", "insufficient"}
    assert res.get("status") == "requires_review" or res.get("reason") in {
        "semantic_paraphrase",
        "semantic_adjudication",
        "no_deterministic_support",
    }
    assert res.get("contradicts_claim") is False


def test_d21_missing_backend_graceful_degradation():
    """D21: Semantic reviewer service is offline or unavailable during report gate execution.

    Gate degrades to deterministic exact verification; marks ambiguous spans as requires_review or degraded assurance.
    """
    evidence = "Company revenue reached fifty million dollars during the fiscal year."
    claim = "Annual corporate earnings equaled 50 million USD."
    row = {
        "claim_id": "C901",
        "claim": claim,
        "evidence": evidence,
        "quote_or_anchor": "",
        "source_url": "https://example.com/annual-report",
        "confidence": "high",
    }
    # When no external LLM oracle is supplied, system must gracefully degrade to requires_review/insufficient
    res = quality_eval.classify_claim_evidence(claim, evidence, row, oracle=None)
    assert res["status"] != "supports"
    assert res.get("supports_claim") is False
    assert res["status"] in {"requires_review", "unsupported", "insufficient"}
