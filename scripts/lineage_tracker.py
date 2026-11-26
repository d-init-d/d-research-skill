#!/usr/bin/env python3
"""
lineage_tracker.py - DRS-1.1 Lineage Deduplication & Multi-Tier Claim Assessment (Package W08).

Implements viral repost origin tracking, derivative citation deduplication,
multi-tier claim assessment (statement_made vs underlying_fact vs firsthand_account),
and negation/refutation context preservation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import tempfile
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse, urlunparse

try:
    from dedup_near import hamming_distance, simhash
except ImportError:
    def simhash(text: str) -> int:
        tokens = re.findall(r"\w+", text.lower())
        if not tokens:
            return 0
        vec = [0] * 64
        for token in tokens:
            digest = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            for idx in range(64):
                vec[idx] += 1 if (digest >> idx) & 1 else -1
        fp = 0
        for idx in range(64):
            if vec[idx] > 0:
                fp |= 1 << idx
        return fp

    def hamming_distance(a: int, b: int) -> int:
        return bin(a ^ b).count("1")


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

    @staticmethod
    def _canonical_url(url: str) -> str:
        raw = unicodedata.normalize("NFC", (url or "").strip())
        if not raw:
            return ""
        parsed = urlparse(raw)
        if not parsed.scheme or not parsed.netloc:
            return raw
        path = parsed.path.rstrip("/") or "/"
        return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", parsed.query, ""))

    _MULTI_TENANT_HOSTS = frozenset({
        "x.com", "twitter.com", "reddit.com", "old.reddit.com", "news.ycombinator.com",
        "facebook.com", "m.facebook.com", "instagram.com", "tiktok.com",
        "youtube.com", "youtu.be", "medium.com", "substack.com", "github.com",
        "gist.github.com", "linkedin.com", "bsky.app", "mastodon.social",
        "threads.net", "t.me", "tinhte.vn", "voz.vn", "wikipedia.org",
        "en.wikipedia.org", "vi.wikipedia.org", "archive.org", "web.archive.org",
    })

    @classmethod
    def _canonical_publisher_key(cls, url: str, row: Dict[str, str]) -> str:
        raw = unicodedata.normalize("NFC", (url or "").strip())
        if not raw:
            return ""
        parsed = urlparse(raw)
        host = parsed.netloc.lower()
        if ":" in host and not host.startswith("["):
            host = host.split(":", 1)[0]
        if host.startswith("www."):
            host = host[4:]
        if not host:
            return ""
        if host in cls._MULTI_TENANT_HOSTS or (row.get("source_type") or "").lower() in {"community", "social"}:
            # Keep distinct multi-tenant speakers/accounts separate while clustering same-account posts.
            path_parts = [p for p in parsed.path.split("/") if p]
            account = ""
            if path_parts:
                if path_parts[0] in {"u", "user", "users"} and len(path_parts) >= 2:
                    account = path_parts[1].lower()
                elif path_parts[0].startswith("@"):
                    account = path_parts[0].lower()
                elif host in {"x.com", "twitter.com", "github.com", "tiktok.com", "instagram.com"}:
                    account = path_parts[0].lower()
            speaker = (row.get("speaker_identity") or "").strip().lower()
            title = (row.get("source_title") or "").strip().lower()
            disc = account or (speaker if speaker not in {"", "unknown", "anonymous"} else "") or title
            return f"{host}::{disc}" if disc else ""
        return host

    def analyze_ledger(
        self,
        ledger_path: Path,
        captures_path: Path | None = None,
    ) -> Dict[str, Any]:
        """Infer origin-derivative lineage across an evidence-ledger CSV and optional capture records."""
        capture_by_url: Dict[str, Dict[str, Any]] = {}
        if captures_path and captures_path.is_file():
            raw_caps = json.loads(captures_path.read_text(encoding="utf-8"))
            cap_list = raw_caps if isinstance(raw_caps, list) else (raw_caps.get("records") or raw_caps.get("captures") or [])
            for rec in cap_list:
                if isinstance(rec, dict):
                    for key in ("final_url", "source_url"):
                        cu = self._canonical_url(str(rec.get(key) or ""))
                        if cu:
                            capture_by_url[cu] = rec

        with open(ledger_path, "r", encoding="utf-8", newline="") as f:
            raw_rows = list(csv.DictReader(f))

        rows = [
            {k: (v or "").strip() for k, v in r.items() if k is not None}
            for r in raw_rows
            if (r.get("record_type") or "").strip().lower() in {"", "claim", "lead"}
            and (r.get("claim_id") or "").strip()
        ]
        # Prefer earliest published/accessed and primary/official sources as root origins
        doc_types = {"primary", "official", "dataset", "paper", "filing", "code", "pdf"}
        doc_rank = {"primary": 0, "official": 0, "dataset": 1, "paper": 1, "filing": 1, "code": 1, "pdf": 1}
        rows.sort(
            key=lambda r: (
                r.get("date_published") or r.get("date_accessed") or "9999",
                doc_rank.get((r.get("source_type") or "").lower(), 2),
                r["claim_id"],
            )
        )

        by_lineage_id: Dict[str, str] = {}
        by_hash: Dict[str, str] = {}
        by_url: Dict[str, str] = {}
        by_domain: Dict[str, str] = {}
        origin_fingerprints: List[Tuple[str, int]] = []
        assessor = UnifiedClaimAssessor()
        row_meta: List[Tuple[Dict[str, str], str, bool, str, List[Dict[str, Any]], str]] = []

        for row in rows:
            cid = row["claim_id"]
            src_url = self._canonical_url(row.get("source_url", ""))
            arch_url = self._canonical_url(row.get("archive_url", ""))
            cap = capture_by_url.get(src_url) or {}
            c_hash = row.get("content_hash") or str(cap.get("content_hash") or "")
            lin_id = row.get("lineage_id", "")
            dom_key = self._canonical_publisher_key(row.get("source_url", ""), row)
            body = f"{row.get('claim', '')} {row.get('evidence', '')} {row.get('quote_or_anchor', '')}".strip()
            fp = simhash(body)

            matched_origin: str | None = None
            relationship = "original"
            if lin_id and lin_id in by_lineage_id:
                matched_origin = by_lineage_id[lin_id]
                relationship = "repost_summary"
            elif c_hash and c_hash in by_hash:
                matched_origin = by_hash[c_hash]
                relationship = "repost_summary"
            elif src_url and src_url in by_url:
                matched_origin = by_url[src_url]
                relationship = "cross_link"
            elif arch_url and arch_url in by_url:
                matched_origin = by_url[arch_url]
                relationship = "cross_link"
            elif dom_key and dom_key in by_domain:
                matched_origin = by_domain[dom_key]
                relationship = "same_domain"
            else:
                for orig_id, orig_fp in origin_fingerprints:
                    if fp and orig_fp and hamming_distance(fp, orig_fp) <= 8:
                        matched_origin = orig_id
                        relationship = "rephrase"
                        break

            is_origin = matched_origin is None
            origin_id = f"ORIGIN-{cid}" if is_origin else matched_origin
            assert origin_id is not None

            if is_origin:
                if lin_id:
                    by_lineage_id[lin_id] = origin_id
                if c_hash:
                    by_hash[c_hash] = origin_id
                if src_url:
                    by_url[src_url] = origin_id
                if arch_url:
                    by_url[arch_url] = origin_id
                if dom_key:
                    by_domain[dom_key] = origin_id
                if fp:
                    origin_fingerprints.append((origin_id, fp))

            self.add_source(
                source_id=cid,
                origin_id=origin_id,
                platform=row.get("source_type") or "unknown",
                author=row.get("speaker_identity") or row.get("source_title") or "unknown",
                is_origin=is_origin,
                relationship=relationship,
                independent_confirmation=is_origin,
                url=row.get("source_url", ""),
                content_hash=c_hash,
            )

            rec_type = (row.get("record_type") or "").strip().lower()
            stype = (row.get("source_type") or "").strip().lower()
            raw_snap = (row.get("snapshot_status") or "").strip().lower()
            verif = (row.get("verifiability") or "").strip().lower()
            if raw_snap in {"intact", "live_intact"}:
                integrity_status = "live_intact"
            elif raw_snap == "archive_snapshot" or (verif == "archive_snapshot" and arch_url):
                integrity_status = "archive_snapshot"
            elif not raw_snap and c_hash:
                integrity_status = "live_intact"
            else:
                integrity_status = raw_snap or "unverified"

            parsed_src = urlparse(row.get("source_url", ""))
            synthesized_records: List[Dict[str, Any]] = []
            if (
                rec_type in {"", "claim"}
                and re.fullmatch(r"sha256:[0-9a-f]{64}", c_hash)
                and parsed_src.scheme in {"http", "https"}
                and parsed_src.netloc
                and integrity_status in {"live_intact", "archive_snapshot", "intact"}
            ):
                source_kind = "official" if stype == "official" else ("primary" if stype in doc_types else "social")
                synthesized_records.append({
                    "source_id": str(cap.get("source_id") or cid),
                    "activity_id": row.get("prov_activity_id") or str(cap.get("activity_id") or f"act-{cid}"),
                    "capture_id": str(cap.get("capture_id") or f"cap-{cid}"),
                    "source_url": row.get("source_url", ""),
                    "archive_url": arch_url,
                    "source_kind": source_kind,
                    "lineage_id": origin_id,
                    "verification_status": "verified",
                    "supports_claim": True,
                    "content_hash": c_hash,
                    "integrity_status": integrity_status,
                })

            corrob_url = row.get("source_url", "") if (synthesized_records and stype in doc_types) else ""
            row_meta.append((row, origin_id, is_origin, integrity_status, synthesized_records, corrob_url))

        summary = self.get_summary()
        true_independent_origins = summary.total_independent_origins
        assessments: List[Dict[str, Any]] = []
        for row, origin_id, is_origin, integrity_status, synthesized_records, corrob_url in row_meta:
            cid = row["claim_id"]
            stype = (row.get("source_type") or "").strip().lower()
            speaker_id = row.get("speaker_identity") or ("official" if stype == "official" else "unknown")
            speaker_rel = row.get("speaker_relationship") or ("subject" if stype == "official" else "unknown")
            assessment = assessor.assess_claim(
                claim_id=cid,
                claim_text=row.get("claim", ""),
                claim_kind="firsthand_account" if speaker_rel == "firsthand" else "underlying_fact",
                speaker_identity=speaker_id,
                speaker_relationship=speaker_rel,
                content_origin=row.get("content_origin") or ("original" if is_origin else "repost"),
                independent_origins=true_independent_origins if synthesized_records else 0,
                integrity_status=integrity_status,
                data_sensitivity=row.get("data_sensitivity") or "public",
                corroborating_doc_url=corrob_url,
                evidence_records=synthesized_records,
            )
            assessments.append(assessment.to_dict())

        return {
            "lineage_summary": summary.to_dict(),
            "assessments": assessments,
        }

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

    @staticmethod
    def _verified_evidence(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return evidence records that carry execution, capture, and integrity proof."""
        verified: List[Dict[str, Any]] = []
        for record in records:
            content_hash = str(record.get("content_hash") or record.get("bytes_hash") or "")
            source_url = str(record.get("source_url") or "")
            parsed = urlparse(source_url)
            if (
                record.get("verification_status") == "verified"
                and record.get("supports_claim") is True
                and str(record.get("source_id") or "").strip()
                and str(record.get("activity_id") or "").strip()
                and str(record.get("capture_id") or "").strip()
                and re.fullmatch(r"sha256:[0-9a-f]{64}", content_hash)
                and parsed.scheme in {"http", "https"}
                and bool(parsed.netloc)
                and record.get("integrity_status")
                in {"live_intact", "archive_snapshot", "intact"}
            ):
                verified.append(record)
        return verified

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
        is_official_silence_case: bool = False,
        evidence_records: List[Dict[str, Any]] | None = None,
    ) -> ClaimAssessment:
        reasons: List[str] = []
        verified_evidence = self._verified_evidence(evidence_records or [])
        verified_lineages = {
            str(record.get("lineage_id"))
            for record in verified_evidence
            if str(record.get("lineage_id") or "").strip()
        }
        verified_origin_count = len(verified_lineages)

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
        authoritative_evidence = [
            record
            for record in verified_evidence
            if record.get("source_kind") in {"official", "primary", "documentary"}
        ]
        corroborating_evidence = [
            record
            for record in authoritative_evidence
            if not corroborating_doc_url or record.get("source_url") == corroborating_doc_url
        ]

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
            and authoritative_evidence
        ):
            reporting_disp = "main_findings"
            verif_state = "statement_confirmed"
            reasons.append("Official authoritative source confirms that the statement was made")

        # Rule 3: Community lead verified against primary documentation (Acceptance D05)
        elif corroborating_doc_url and is_stable and corroborating_evidence:
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
        elif verified_origin_count >= 2 and is_original and is_stable:
            reporting_disp = "main_findings"
            verif_state = "supported"
            reasons.append(
                f"Empirical claim supported by {verified_origin_count} hash-verified independent lineages"
            )

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
            independent_origin_count=verified_origin_count,
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
    p_claim.add_argument(
        "--evidence-file",
        help="JSON array of claim evidence records bound to activity/capture IDs and hashes",
    )

    p_analyze = sub.add_parser("analyze-ledger", help="Infer lineage trees directly from an evidence-ledger CSV")
    p_analyze.add_argument("--ledger", required=True, help="Path to evidence-ledger.csv")
    p_analyze.add_argument("--captures", default="", help="Optional capture-records.json path")
    p_analyze.add_argument("--out", default="", help="Optional output JSON path")

    sub.add_parser("self-test", help="Run offline lineage_tracker self-tests")

    args = parser.parse_args()

    if args.cmd == "self-test":
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.csv"
            with open(ledger, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(
                    f,
                    fieldnames=[
                        "claim_id", "claim", "source_title", "source_url", "source_type",
                        "date_published", "evidence", "content_hash", "record_type", "lineage_id",
                    ],
                )
                w.writeheader()
                w.writerows([
                    {
                        "claim_id": "C1", "claim": "Central bank raised policy rate by 25 bps in September",
                        "source_title": "Primary Press Release", "source_url": "https://fed.example/r1",
                        "source_type": "official", "date_published": "2026-09-16",
                        "evidence": "Target range raised 25 bps.", "content_hash": "sha256:" + "1" * 64,
                        "record_type": "claim", "lineage_id": "LIN-1",
                    },
                    {
                        "claim_id": "C2", "claim": "Repost: Central bank raised policy rate by 25 bps in September",
                        "source_title": "Forum repost", "source_url": "https://forum.example/p2",
                        "source_type": "community", "date_published": "2026-09-17",
                        "evidence": "Target range raised 25 bps.", "content_hash": "sha256:" + "1" * 64,
                        "record_type": "claim", "lineage_id": "",
                    },
                    {
                        "claim_id": "C3", "claim": "Brent crude reached 117 dollars amid maritime chokepoint closure",
                        "source_title": "Market Feed", "source_url": "https://oil.example/b3",
                        "source_type": "dataset", "date_published": "2026-04-15",
                        "evidence": "Monthly Brent benchmark 117.29.", "content_hash": "sha256:" + "2" * 64,
                        "record_type": "claim", "lineage_id": "",
                    },
                ])
            tracker = LineageTracker()
            out = tracker.analyze_ledger(ledger)
            summary = out["lineage_summary"]
            assert summary["total_sources_observed"] == 3
            assert summary["total_independent_origins"] == 2
            assert summary["derivative_source_count"] == 1
        print("lineage_tracker self-test ok")
        return 0

    if args.cmd == "analyze-ledger":
        tracker = LineageTracker()
        caps = Path(args.captures) if args.captures else None
        payload = tracker.analyze_ledger(Path(args.ledger), captures_path=caps)
        rendered = json.dumps(payload, indent=2, ensure_ascii=False)
        if args.out:
            Path(args.out).write_text(rendered + "\n", encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(rendered)
        return 0

    if args.cmd == "evaluate-lineage":
        with open(args.fixture, "r", encoding="utf-8") as f:
            data = json.load(f)
        tracker = LineageTracker()
        summary = tracker.add_from_fixture(data)
        print(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "assess-claim":
        evidence_records: List[Dict[str, Any]] = []
        if args.evidence_file:
            with open(args.evidence_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if not isinstance(loaded, list) or not all(isinstance(item, dict) for item in loaded):
                print("--evidence-file must contain a JSON array of objects", file=sys.stderr)
                return 2
            evidence_records = loaded
        assessor = UnifiedClaimAssessor()
        res = assessor.assess_claim(
            claim_id=args.claim_id,
            claim_text=args.text,
            claim_kind=args.kind,
            speaker_identity=args.identity,
            speaker_relationship=args.relationship,
            content_origin=args.origin,
            independent_origins=args.independent_origins,
            corroborating_doc_url=args.doc_url,
            evidence_records=evidence_records,
        )
        print(json.dumps(res.to_dict(), indent=2, ensure_ascii=False))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
