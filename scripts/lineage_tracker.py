#!/usr/bin/env python3
"""
lineage_tracker.py - DRS-1.1 Lineage Deduplication & Multi-Tier Claim Assessment (Package W08).

Implements viral repost origin tracking, derivative citation deduplication,
multi-tier claim assessment (statement_made vs underlying_fact vs firsthand_account),
and negation/refutation context preservation.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class LineageNode:
    source_id: str
    origin_id: str
    platform: str
    author: str
    url: str = ""
    is_origin: bool = False
    relationship: str = "original"  # "original", "direct_quote", "cross_link", "repost_summary", "screenshot_share", "retweet_reblog", "rephrase", "blog_syndication", "aggregator_feed", "commentary_repost"
    independent_confirmation: bool = False
    content_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LineageSummary:
    total_sources_observed: int
    total_independent_origins: int
    origins: Dict[str, List[str]] = field(default_factory=dict)  # origin_id -> [source_ids]
    independent_origin_ids: List[str] = field(default_factory=list)
    derivative_source_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimAssessment:
    claim_id: str
    claim_text: str
    claim_kind: str  # "statement_made", "underlying_fact", "firsthand_account", "opinion", "reception"
    verification_state: str  # "supported", "statement_confirmed", "firsthand_unverified", "unverified", "disputed", "refuted", "not_assessable"
    reporting_disposition: str  # "main_findings", "firsthand_unverified", "non_official_unverified_leads", "contradictions_and_unknowns", "prohibited"
    speaker_identity: str
    speaker_relationship: str
    content_origin: str
    independent_origin_count: int
    has_negation_context: bool = False
    negation_note: str = ""
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Negation & Refutation Context Analyzer (Acceptance D08)
# ---------------------------------------------------------------------------

VIETNAMESE_NEGATION_PATTERNS = [
    r"hoàn\s+toàn\s+không\s+(?:có|phải)",
    r"không\s+(?:có|hề|đúng|xảy\s+ra|tồn\s+tại)",
    r"chưa\s+(?:từng|bao\s+giờ|xác\s+nhận)",
    r"phủ\s+nhận(?:\s+hoàn\s+toàn)?",
    r"bác\s+bỏ(?:\s+thông\s+tin)?",
    r"không\s+thể\s+xác\s+minh",
    r"chỉ\s+là\s+tin\s+đồn",
    r"thông\s+tin\s+sai\s+sự\s+thật",
]

ENGLISH_NEGATION_PATTERNS = [
    r"no\s+evidence\s+that",
    r"completely\s+untrue",
    r"false\s+claim",
    r"categorically\s+denied",
    r"has\s+not\s+occurred",
    r"refutes\s+the\s+claim",
    r"not\s+supported\s+by",
]


class NegationContextAnalyzer:
    """Analyzes whether a quoted claim appears within grammatical negation or refutation context."""

    def __init__(self):
        self.patterns = [re.compile(p, re.IGNORECASE) for p in (VIETNAMESE_NEGATION_PATTERNS + ENGLISH_NEGATION_PATTERNS)]

    def analyze(self, text: str) -> Tuple[bool, str]:
        norm = unicodedata.normalize("NFC", text)
        for pat in self.patterns:
            m = pat.search(norm)
            if m:
                return True, f"Found refutation/negation context marker: '{m.group(0)}'"
        return False, ""


# ---------------------------------------------------------------------------
# Lineage Tracker (Acceptance D03, D04)
# ---------------------------------------------------------------------------

class LineageTracker:
    """Tracks and deduplicates viral reposts, mirrors, and syndicated stories back to common roots."""

    def __init__(self):
        self.nodes: Dict[str, LineageNode] = {}
        self.origin_map: Dict[str, List[str]] = {}  # origin_id -> [source_ids]

    def add_source(
        self,
        source_id: str,
        origin_id: str,
        platform: str,
        author: str,
        is_origin: bool = False,
        relationship: str = "original",
        independent_confirmation: bool = False,
        url: str = "",
        content_hash: str = ""
    ) -> LineageNode:
        node = LineageNode(
            source_id=source_id,
            origin_id=origin_id,
            platform=platform,
            author=author,
            url=url,
            is_origin=is_origin,
            relationship=relationship,
            independent_confirmation=independent_confirmation,
            content_hash=content_hash
        )
        self.nodes[source_id] = node

        if origin_id not in self.origin_map:
            self.origin_map[origin_id] = []
        if source_id not in self.origin_map[origin_id]:
            self.origin_map[origin_id].append(source_id)

        return node

    def add_from_fixture(self, fixture_dict: Dict[str, Any]) -> LineageSummary:
        """Load lineage data from fixture specification."""
        origin_src = fixture_dict.get("origin_source", {})
        if origin_src:
            self.add_source(
                source_id=origin_src.get("origin_id", "ORIGIN"),
                origin_id=origin_src.get("origin_id", "ORIGIN"),
                platform=origin_src.get("platform", ""),
                author=origin_src.get("author", ""),
                is_origin=True,
                relationship="original",
                independent_confirmation=True,
                url=origin_src.get("canonical_url", "")
            )

        for rep in fixture_dict.get("derivative_reposts", []):
            self.add_source(
                source_id=rep.get("source_id", ""),
                origin_id=rep.get("origin_id", origin_src.get("origin_id", "ORIGIN")),
                platform=rep.get("platform", ""),
                author=rep.get("author", ""),
                is_origin=False,
                relationship=rep.get("relationship", "repost"),
                independent_confirmation=rep.get("independent_confirmation", False)
            )

        indep = fixture_dict.get("independent_empirical_study")
        if indep:
            self.add_source(
                source_id=indep.get("source_id", ""),
                origin_id=indep.get("origin_id", "ORIGIN_INDEP"),
                platform=indep.get("platform", ""),
                author=indep.get("author", ""),
                is_origin=True,
                relationship="independent_empirical",
                independent_confirmation=True,
                url=indep.get("canonical_url", "")
            )

        return self.get_summary()

    def get_summary(self) -> LineageSummary:
        """Calculates true independent origin count vs derivative repost count."""
        independent_origins: List[str] = []
        derivative_count = 0

        for origin_id, sources in self.origin_map.items():
            # Check if this origin represents an independent source
            origin_nodes = [self.nodes[s] for s in sources if s in self.nodes]
            has_independent = any(n.independent_confirmation or n.is_origin for n in origin_nodes)
            if has_independent:
                independent_origins.append(origin_id)

            # All non-origin sources under this origin are derivative
            for n in origin_nodes:
                if not n.is_origin:
                    derivative_count += 1

        return LineageSummary(
            total_sources_observed=len(self.nodes),
            total_independent_origins=len(independent_origins),
            origins=dict(self.origin_map),
            independent_origin_ids=sorted(independent_origins),
            derivative_source_count=derivative_count
        )


# ---------------------------------------------------------------------------
# Multi-Tier Claim Assessor (Acceptance D01, D02, D05, D06, D07)
# ---------------------------------------------------------------------------

class UnifiedClaimAssessor:
    """Evaluates admission of claims into main_findings, firsthand, or unverified leads."""

    def __init__(self):
        self.negation_analyzer = NegationContextAnalyzer()

    def assess_claim(
        self,
        claim_id: str,
        claim_text: str,
        claim_kind: str,
        speaker_identity: str,
        speaker_relationship: str,
        content_origin: str,
        independent_origins: int,
        integrity_status: str = "live_intact",
        data_sensitivity: str = "public",
        corroborating_doc_url: str = "",
        is_official_silence_case: bool = False
    ) -> ClaimAssessment:
        reasons: List[str] = []

        # Check negation context
        has_neg, neg_note = self.negation_analyzer.analyze(claim_text)
        if has_neg:
            reasons.append(neg_note)

        # Base disposition
        reporting_disp = "non_official_unverified_leads"
        verif_state = "unverified"

        is_authoritative = speaker_identity in {"official", "verified_public_role"}
        is_direct = speaker_relationship in {"subject", "authorized_representative"}
        is_original = content_origin == "original"
        is_stable = integrity_status in {"live_intact", "archive_snapshot", "intact"}

        # Rule 1: Prohibited sensitivity
        if data_sensitivity in {"secret", "minor"}:
            return ClaimAssessment(
                claim_id=claim_id,
                claim_text=claim_text,
                claim_kind=claim_kind,
                verification_state="refuted",
                reporting_disposition="prohibited",
                speaker_identity=speaker_identity,
                speaker_relationship=speaker_relationship,
                content_origin=content_origin,
                independent_origin_count=independent_origins,
                has_negation_context=has_neg,
                negation_note=neg_note,
                reasons=["Prohibited data sensitivity: secret or minor"]
            )

        # Rule 2: Official statement with statement_made kind (Acceptance D01)
        if (
            claim_kind == "statement_made"
            and is_authoritative
            and is_direct
            and is_original
            and is_stable
        ):
            reporting_disp = "main_findings"
            verif_state = "statement_confirmed"
            reasons.append("Official authoritative source confirms that the statement was made")

        # Rule 3: Community lead verified against primary documentation (Acceptance D05)
        elif corroborating_doc_url and is_stable:
            reporting_disp = "main_findings"
            verif_state = "supported"
            reasons.append(f"Community lead corroborated by primary documentary source: {corroborating_doc_url}")

        # Rule 4: Firsthand account from community / pseudonymous user (Acceptance D02)
        elif claim_kind == "firsthand_account":
            reporting_disp = "firsthand_unverified"
            verif_state = "firsthand_unverified"
            reasons.append("Valuable firsthand user experience retained under firsthand_unverified with attribution")

        # Rule 5: Official silence with coverup allegations (Acceptance D07)
        elif is_official_silence_case:
            reporting_disp = "non_official_unverified_leads"
            verif_state = "unverified"
            reasons.append("Official silence noted; social coverup allegations retained as unverified leads, not factual proof of coverup")

        # Rule 6: Multiple independent origins corroboration
        elif independent_origins >= 2 and is_original and is_stable:
            reporting_disp = "main_findings"
            verif_state = "supported"
            reasons.append(f"Empirical claim supported by {independent_origins} distinct independent lineages")

        else:
            reporting_disp = "non_official_unverified_leads"
            verif_state = "unverified"
            reasons.append("Item retained as unverified lead pending authoritative confirmation or primary documentation")

        # If claim contains negation context, ensure underlying fact is not declared supported
        if has_neg and verif_state == "supported" and claim_kind == "underlying_fact":
            verif_state = "statement_confirmed"
            reasons.append("Claim text contains negation context; downgraded to statement_confirmed to preserve semantics")

        return ClaimAssessment(
            claim_id=claim_id,
            claim_text=claim_text,
            claim_kind=claim_kind,
            verification_state=verif_state,
            reporting_disposition=reporting_disp,
            speaker_identity=speaker_identity,
            speaker_relationship=speaker_relationship,
            content_origin=content_origin,
            independent_origin_count=independent_origins,
            has_negation_context=has_neg,
            negation_note=neg_note,
            reasons=reasons
        )


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="DRS-1.1 Lineage Tracker & Claim Assessor")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # evaluate-lineage
    p_lin = sub.add_parser("evaluate-lineage", help="Deduplicate lineage from JSON fixture")
    p_lin.add_argument("--fixture", required=True, help="Path to lineage fixture JSON")

    # assess-claim
    p_claim = sub.add_parser("assess-claim", help="Assess claim admission")
    p_claim.add_argument("--claim-id", default="CLM-01")
    p_claim.add_argument("--text", required=True)
    p_claim.add_argument("--kind", default="underlying_fact", choices=["statement_made", "underlying_fact", "firsthand_account", "opinion", "reception"])
    p_claim.add_argument("--identity", default="unknown")
    p_claim.add_argument("--relationship", default="unknown")
    p_claim.add_argument("--origin", default="original")
    p_claim.add_argument("--independent-origins", type=int, default=1)
    p_claim.add_argument("--doc-url", default="")

    args = parser.parse_args()

    if args.cmd == "evaluate-lineage":
        with open(args.fixture, "r", encoding="utf-8") as f:
            data = json.load(f)
        tracker = LineageTracker()
        summary = tracker.add_from_fixture(data)
        print(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "assess-claim":
        assessor = UnifiedClaimAssessor()
        res = assessor.assess_claim(
            claim_id=args.claim_id,
            claim_text=args.text,
            claim_kind=args.kind,
            speaker_identity=args.identity,
            speaker_relationship=args.relationship,
            content_origin=args.origin,
            independent_origins=args.independent_origins,
            corroborating_doc_url=args.doc_url
        )
        print(json.dumps(res.to_dict(), indent=2, ensure_ascii=False))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
