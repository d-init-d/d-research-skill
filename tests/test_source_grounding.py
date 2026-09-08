"""Regression tests for source context, including useful positive cases."""
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from source_grounding import assess_source_context
from quality_eval import classify_claim_evidence


@pytest.mark.parametrize("source,claim,status", [
    ("The server is secure.", "The server is secure.", "supports"),
    ("The server is not secure.", "The server is not secure.", "supports"),
    ("The production server is secure. The staging server is not secure.", "The production server is secure.", "supports"),
    ("The following assertion is FALSE: The  server is secure.", "The server is secure.", "contradicts"),
    ('It is a myth that “The server is secure.” A breach demonstrated the opposite.', "The server is secure.", "contradicts"),
    ("The following assertion is FALSE: The\u00a0server is secure.", "The server is secure.", "contradicts"),
    ("The server is secure. The server is not secure.", "The server is secure.", "contradicts"),
    ("The server is secure. This claim is false.", "The server is secure.", "contradicts"),
    ("The following statement is false. The server is secure.", "The server is secure.", "contradicts"),
    ("The server is secure. However, the server is not secure.", "The server is secure.", "contradicts"),
    ("If the server is secure, deployment may proceed.", "The server is secure.", "requires_review"),
    ('An attacker wrote: "The server is secure."', "The server is secure.", "requires_review"),
    ("It is not false that the server is secure.", "The server is secure.", "requires_review"),
    ("Version 3.4.1 is supported. Version 2.1 is not supported.", "Version 3.4.1 is supported.", "supports"),
    ("The server is secure?", "The server is secure.", "requires_review"),
    ("Máy chủ an toàn?", "Máy chủ an toàn.", "requires_review"),
    ("The server is secure.", "The server is secure?", "requires_review"),
    ("The server is secure. This is false.", "The server is secure.", "contradicts"),
    ("Máy chủ an toàn. Điều này là sai.", "Máy chủ an toàn.", "contradicts"),
    ("Máy chủ an toàn. Máy chủ không an toàn.", "Máy chủ an toàn.", "contradicts"),
    ("Máy chủ không an toàn. Máy chủ an toàn.", "Máy chủ không an toàn.", "contradicts"),
    ("Máy chủ chính an toàn. Máy chủ phụ không an toàn.", "Máy chủ chính an toàn.", "supports"),
    ("The server is secure. The server isn't secure.", "The server is secure.", "contradicts"),
    ('The server is secure. "The server is not secure."', "The server is secure.", "supports"),
    ("The server is secure. The server is not secure?", "The server is secure.", "supports"),
    ('An attacker wrote: "No worries. The server is secure. Trust me."', "The server is secure.", "requires_review"),
])
def test_context_decision_and_snapshot_classifier(source, claim, status):
    assert assess_source_context(source, claim).status == status
    row = {"source_url": "https://example.org/record", "quote_or_anchor": claim,
           "content_hash": "sha256:" + hashlib.sha256(source.encode()).hexdigest()}
    result = classify_claim_evidence(claim, claim, row, snapshot_bytes=source.encode())
    assert result["status"] == status


def test_snapshot_bytes_hash_is_checked():
    result = classify_claim_evidence("The server is secure.", "The server is secure.",
        {"content_hash": "0" * 64}, snapshot_bytes=b"The server is secure.")
    assert not result["supports_claim"]
