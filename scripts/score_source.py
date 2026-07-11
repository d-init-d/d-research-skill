#!/usr/bin/env python3
"""Apply the source-quality rubric to an evidence-ledger CSV.

The rubric is documented in ``references/source-quality-rubric.md`` and
scores each source across five dimensions:

* **Type** (5): primary/dataset/code/filing > paper/official > pdf/secondary > community > unknown
* **Authority** (5): how authoritative the publisher is for the claim
* **Freshness** (5): how recent the publication/update date is relative to the claim
* **Traceability** (5): how precisely the row anchors evidence and its retrieval path
* **Independence** (5): how independent the source is from the entities it discusses

Each axis is 0-5 (integer). ``base_total`` is 0-25; optional social modifiers
produce ``adjusted_total``, which is bucketed into an automated band:

* 20-25 -> ``high``
* 13-19 -> ``medium``
* 0-12  -> ``low``

This script is deterministic. It does not call the network and does not
make subjective judgments — it just applies fixed rules to the columns
already present in the evidence ledger. Use the output as a *baseline*
that the agent or human reviewer can override per-row before finalising.

Subcommands
-----------
* ``score``      apply the rubric to an evidence-ledger CSV
* ``self-test``  run the offline self-test
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# Axis 1: source-type baseline scores. Keep in sync with the
# VALID_SOURCE_TYPES set in scripts/evidence_ledger.py.
TYPE_SCORE: dict[str, int] = {
    "primary": 5,
    "dataset": 5,
    "code": 5,
    "filing": 5,
    "official": 4,
    "paper": 4,
    "pdf": 2,
    "secondary": 2,
    "community": 1,
    "unknown": 0,
}

# Axis 2: authority signals. Heuristic, conservative. Higher = more
# authoritative. The mapping looks at the source URL's apex domain.
AUTHORITY_BY_TLD: dict[str, int] = {
    ".gov": 5,
    ".edu": 5,
    ".mil": 5,
    ".int": 4,
    ".ac.uk": 5,
    ".ac.jp": 5,
    ".org": 3,
}

AUTHORITATIVE_DOMAINS = {
    # Standards bodies and metadata authorities
    "ietf.org": 5,
    "w3.org": 5,
    "iso.org": 5,
    "ieee.org": 5,
    "acm.org": 5,
    "iana.org": 5,
    "nist.gov": 5,
    "europa.eu": 4,
    # Open scholarly infrastructure
    "doi.org": 4,
    "crossref.org": 5,
    "openalex.org": 5,
    "orcid.org": 5,
    "ror.org": 5,
    # Major code/data hosts (authoritative for the artifact itself, not
    # for arbitrary claims about other entities)
    "github.com": 3,
    "gitlab.com": 3,
    "zenodo.org": 4,
    "figshare.com": 4,
    "dataverse.org": 4,
    # Major library/preprint servers
    "arxiv.org": 4,
    "biorxiv.org": 4,
    "medrxiv.org": 4,
    "ssrn.com": 3,
    "europepmc.org": 5,
    "ncbi.nlm.nih.gov": 5,
}


# Every manual gate must be present and pass before a score can be described
# as reviewed.  Keep this tuple in sync with references/source-quality-rubric.md.
REQUIRED_REVIEW_GATES = (
    "relevance",
    "method_transparency",
    "access_quality",
)
# ``reproducibility`` was emitted by early v3.2 RC builds. Keep accepting it
# as an optional compatibility gate, but never require it for the v2 contract.
OPTIONAL_REVIEW_GATES = ("reproducibility",)
KNOWN_REVIEW_GATES = REQUIRED_REVIEW_GATES + OPTIONAL_REVIEW_GATES
REVIEW_PASS_VALUES = {"pass", "passed", "ok"}
REVIEW_FAIL_VALUES = {"fail", "failed", "reject", "rejected"}
REQUIRED_REVIEW_OUTPUT_FIELDS = {
    f"review_{gate}" for gate in REQUIRED_REVIEW_GATES
}
REVIEW_RESERVED_FIELDS = {
    "review_status",
    "review_gates",
    "review_unknown_gates",
}


def _normalize_review_decision(value: object) -> str:
    """Return a canonical review decision without turning unknowns into passes."""
    normalized = str(value or "").strip().lower()
    if normalized in REVIEW_PASS_VALUES:
        return "pass"
    if normalized in REVIEW_FAIL_VALUES:
        return "fail"
    if normalized in {"", "manual_required", "pending", "unreviewed"}:
        return "manual_required"
    return "invalid"


def _review_gates_from_row(row: dict[str, str]) -> dict[str, str]:
    """Load flat CSV or JSON review decisions and retain unknown gate names.

    Flat ``review_<gate>`` columns take precedence over an optional
    ``review_gates`` JSON object.  Missing required gates remain
    ``manual_required``.  Unknown or malformed gates are retained as invalid
    entries so ``Score.review_status`` cannot accidentally mark a partial
    review as complete.
    """
    supplied: dict[str, object] = {}
    raw_json = (row.get("review_gates") or "").strip()
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if not isinstance(parsed, dict):
                supplied["__invalid_review_gates__"] = "invalid"
            else:
                supplied.update(parsed)
        except (TypeError, ValueError):
            supplied["__invalid_review_gates__"] = "invalid"

    for gate in (row.get("review_unknown_gates") or "").split(";"):
        gate = gate.strip()
        if gate:
            supplied[gate] = "invalid"

    for field, value in row.items():
        if not field.startswith("review_"):
            continue
        if field in REVIEW_RESERVED_FIELDS:
            continue
        gate = field.removeprefix("review_")
        if field in REQUIRED_REVIEW_OUTPUT_FIELDS or str(value or "").strip():
            supplied[gate] = value

    gates = {
        gate: _normalize_review_decision(supplied.get(gate))
        for gate in REQUIRED_REVIEW_GATES
    }
    for gate, value in supplied.items():
        if gate not in REQUIRED_REVIEW_GATES:
            gates[gate] = _normalize_review_decision(value)
    return gates


@dataclass
class Score:
    type_score: int
    authority: int
    freshness: int
    traceability: int
    independence: int
    social_bonus: int = 0
    # Manual review gates are deliberately separate from automated scoring.
    review_gates: dict[str, str] | None = None

    @property
    def base_total(self) -> int:
        return (
            self.type_score
            + self.authority
            + self.freshness
            + self.traceability
            + self.independence
        )

    @property
    def recency(self) -> int:
        """Deprecated v3 alias of the canonical freshness axis."""
        return self.freshness

    @property
    def methodology(self) -> int:
        """Deprecated v3 alias of the canonical traceability axis."""
        return self.traceability

    @property
    def adjusted_total(self) -> int:
        return self.base_total + self.social_bonus

    @property
    def total(self) -> int:
        """v3.2 alias of adjusted_total for backward compatibility."""
        return self.adjusted_total

    @property
    def automated_band(self) -> str:
        """Automated score band only — not final reviewed confidence."""
        t = self.adjusted_total
        if t >= 20:
            return "high"
        if t >= 13:
            return "medium"
        return "low"

    @property
    def band(self) -> str:
        """Alias of automated_band (v3.2 compatibility)."""
        return self.automated_band

    @property
    def review_status(self) -> str:
        """Manual review gates are unresolved until a human fills them."""
        gates = self.review_gates or {}
        required = {
            gate: _normalize_review_decision(gates.get(gate))
            for gate in REQUIRED_REVIEW_GATES
        }
        optional = {
            gate: _normalize_review_decision(gates.get(gate))
            for gate in OPTIONAL_REVIEW_GATES
            if gate in gates
        }
        unknown = set(gates) - set(KNOWN_REVIEW_GATES)
        if not gates or (
            all(value == "manual_required" for value in required.values())
            and not optional
            and not unknown
        ):
            return "unreviewed"
        if unknown:
            return "pending_manual_review"
        decisions = [*required.values(), *optional.values()]
        if any(value == "fail" for value in decisions):
            return "review_failed"
        if any(value != "pass" for value in required.values()):
            return "pending_manual_review"
        if any(value not in {"pass", "manual_required"} for value in optional.values()):
            return "pending_manual_review"
        return "reviewed"

    @property
    def final_reviewed_confidence(self) -> str:
        """Final confidence is not high while review gates remain unresolved."""
        if self.review_status == "review_failed":
            return "low_review_failed"
        if self.review_status != "reviewed":
            # Cap reported final confidence at medium until human review completes.
            auto = self.automated_band
            if auto == "high":
                return "medium_pending_review"
            return f"{auto}_pending_review"
        return self.automated_band


def _apex(url: str) -> str:
    """Return the apex domain (e.g. 'docs.openalex.org' -> 'openalex.org')."""
    url = url.strip().lower()
    if "://" in url:
        url = url.split("://", 1)[1]
    host = url.split("/", 1)[0]
    # Strip user@host and port.
    if "@" in host:
        host = host.split("@", 1)[1]
    if ":" in host:
        host = host.split(":", 1)[0]
    parts = [p for p in host.split(".") if p]
    if len(parts) <= 2:
        return ".".join(parts)
    # Handle two-segment public suffixes like 'co.uk', 'ac.uk', 'ac.jp'.
    if parts[-2] in {"co", "ac", "gov", "org"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def score_authority(source_url: str) -> int:
    """Score 0-5 for how authoritative the URL's host is."""
    apex = _apex(source_url)
    if apex in AUTHORITATIVE_DOMAINS:
        return AUTHORITATIVE_DOMAINS[apex]
    for suffix, sc in AUTHORITY_BY_TLD.items():
        if apex.endswith(suffix):
            return sc
    return 2  # generic unknown commercial host


def parse_publication_date(value: object) -> date | None:
    """Parse YYYY / YYYY-MM / YYYY-MM-DD. Return None for invalid values."""
    import re
    from calendar import monthrange

    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    m = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", s)
    if not m:
        return None
    year = int(m.group(1))
    month = int(m.group(2) or "1")
    day = int(m.group(3) or "1")
    if year < 1400 or year > 9999:
        return None
    if month < 1 or month > 12:
        return None
    max_day = monthrange(year, month)[1]
    if day < 1 or day > max_day:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def score_freshness(date_published: object, date_accessed: object, today: date) -> int:
    """Score 0-5 freshness from publication/update date only.

    Accepts valid YYYY / YYYY-MM / YYYY-MM-DD. Rejects garbage dates, impossible
    months/days, invalid leap days, and future dates (low score).
    ``date_accessed`` never substitutes for publication/update date.
    """
    _ = date_accessed  # never a freshness proxy
    if date_published is None or not str(date_published).strip():
        return 1
    pub = parse_publication_date(date_published)
    if pub is None:
        return 1  # invalid format or calendar date
    if pub > today:
        return 1  # future
    years_old = today.year - pub.year
    # Adjust roughly by month when both full dates exist
    if (today.month, today.day) < (pub.month, pub.day):
        years_old -= 1
    if years_old < 0:
        return 1
    if years_old <= 1:
        return 5
    if years_old <= 3:
        return 4
    if years_old <= 7:
        return 3
    if years_old <= 15:
        return 2
    return 1


def score_recency(date_published: object, date_accessed: object, today: date) -> int:
    """Deprecated v3 alias of :func:`score_freshness`."""
    return score_freshness(date_published, date_accessed, today)


def score_traceability(row: dict[str, str]) -> int:
    """Score 0-5 from deterministic evidence-traceability signals.

    Heuristics (deterministic):
    * +2 if there is a non-empty quote_or_anchor (the evidence is anchored
      to a specific snippet, indicating verifiability).
    * +1 if source_url is present.
    * +1 if access_method is reproducible (fetch / api / playwright_probe /
      script). Manual screenshots score 0 here.
    * +1 if the evidence cell is non-trivial (> 30 chars).
    """
    sc = 0
    if (row.get("quote_or_anchor") or "").strip():
        sc += 2
    if (row.get("source_url") or "").strip():
        sc += 1
    am = (row.get("access_method") or "").strip().lower()
    if any(am.startswith(p) for p in ("fetch", "api", "playwright", "script", "rest")):
        sc += 1
    ev = (row.get("evidence") or "").strip()
    if len(ev) > 30:
        sc += 1
    return min(sc, 5)


def score_methodology(row: dict[str, str]) -> int:
    """Deprecated v3 alias of :func:`score_traceability`."""
    return score_traceability(row)


# Words in the source title or URL that suggest the source is the
# publisher / vendor / author of the thing being claimed about itself.
DEPENDENT_HINTS = (
    "press",
    "press-release",
    "press_release",
    "blog",
    "about-us",
    "/about/",
    "company/",
    "/news/",
    "marketing",
    "/help/",
)


def score_independence(row: dict[str, str]) -> int:
    """Score 0-5 for how independent the source is from the claimed entity.

    Pure heuristics — the agent or reviewer should override per row.
    """
    title = (row.get("source_title") or "").lower()
    url = (row.get("source_url") or "").lower()
    st = (row.get("source_type") or "").strip().lower()
    if st == "official":
        return 2  # authoritative *about itself*, less independent
    if any(h in title or h in url for h in DEPENDENT_HINTS):
        return 2
    if st in {"paper", "primary", "dataset", "code"}:
        return 4
    if st == "secondary":
        return 3
    if st == "community":
        return 2
    return 3


def score_row(row: dict[str, str], today: date | None = None) -> Score:
    today = today or date.today()
    sc = Score(
        type_score=TYPE_SCORE.get(
            (row.get("source_type") or "").strip().lower(), 0
        ),
        authority=score_authority(row.get("source_url") or ""),
        freshness=score_freshness(
            row.get("date_published") or "",
            row.get("date_accessed") or "",
            today,
        ),
        traceability=score_traceability(row),
        independence=score_independence(row),
    )
    # Social scoring modifiers (v2.1): applied when verifiability column is present.
    verifiability = (row.get("verifiability") or "").strip().lower()
    if verifiability == "archive_snapshot":
        sc.social_bonus += 2
    if verifiability == "unverified":
        sc.social_bonus -= 1
    # Author handle bonus: check notes field for author_handle indicator
    # or a dedicated column if present in the row.
    notes = (row.get("notes") or "").strip()
    author_handle = (row.get("author_handle") or "").strip()
    if author_handle or "author_handle=" in notes.lower():
        sc.social_bonus += 1
    sc.review_gates = _review_gates_from_row(row)
    return sc


def cmd_score(file: Path, out: Path | None, today: date | None = None) -> int:
    if not file.is_file():
        print(f"error: file not found: {file}", file=sys.stderr)
        return 1
    with file.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        if not rows:
            print("error: ledger is empty", file=sys.stderr)
            return 1
    out_rows = []
    for r in rows:
        sc = score_row(r, today=today)
        output_row = {
            "claim_id": r.get("claim_id", ""),
            "source_url": r.get("source_url", ""),
            "type_score": sc.type_score,
            "authority": sc.authority,
            "freshness": sc.freshness,
            "recency": sc.recency,  # deprecated v3 alias
            "traceability": sc.traceability,
            "methodology": sc.methodology,  # deprecated v3 alias
            "independence": sc.independence,
            "base_total": sc.base_total,
            "social_bonus": sc.social_bonus,
            "adjusted_total": sc.adjusted_total,
            "total": sc.total,  # alias of adjusted_total (v3.2)
            "band": sc.band,  # automated band alias
            "automated_band": sc.automated_band,
            "review_status": sc.review_status,
            "final_reviewed_confidence": sc.final_reviewed_confidence,
        }
        for gate in REQUIRED_REVIEW_GATES:
            output_row[f"review_{gate}"] = (sc.review_gates or {}).get(
                gate, "manual_required"
            )
        for gate in OPTIONAL_REVIEW_GATES:
            output_row[f"review_{gate}"] = (sc.review_gates or {}).get(gate, "")
        unknown_gates = sorted(
            set(sc.review_gates or {}) - set(KNOWN_REVIEW_GATES)
        )
        output_row["review_unknown_gates"] = ";".join(unknown_gates)
        out_rows.append(output_row)
    headers = list(out_rows[0].keys())
    sink = out.open("w", newline="", encoding="utf-8") if out else sys.stdout
    try:
        writer = csv.DictWriter(sink, fieldnames=headers)
        writer.writeheader()
        for r in out_rows:
            writer.writerow(r)
    finally:
        if out:
            sink.close()
            print(f"wrote {out} ({len(out_rows)} rows)")
    # Summary to stderr
    bands = {"high": 0, "medium": 0, "low": 0}
    for r in out_rows:
        bands[r["band"]] += 1
    print(
        f"summary: high={bands['high']} medium={bands['medium']} low={bands['low']}",
        file=sys.stderr,
    )
    return 0


def cmd_self_test() -> int:
    print("score_source self-test")
    fixed_today = date(2026, 5, 15)
    sample = [
        {
            "claim_id": "C001",
            "source_type": "official",
            "source_title": "OpenAlex API Documentation",
            "source_url": "https://docs.openalex.org/how-to-use-the-api",
            "date_published": "2024-03-01",
            "date_accessed": "2026-05-15",
            "access_method": "playwright_probe",
            "evidence": "Per-page parameter accepts 1-200; default 25.",
            "quote_or_anchor": "'You can use the per-page parameter...'",
        },
        {
            "claim_id": "C002",
            "source_type": "primary",
            "source_title": "Playwright Auto-waiting Docs",
            "source_url": "https://playwright.dev/docs/actionability",
            "date_published": "2025-01-10",
            "date_accessed": "2026-05-15",
            "access_method": "fetch",
            "evidence": "Built-in actionability checks include visible, stable, receives-events, enabled, and editable states.",
            "quote_or_anchor": "'Playwright performs a range of actionability checks...'",
        },
        {
            "claim_id": "C003",
            "source_type": "community",
            "source_title": "Random Forum Post About Playwright",
            "source_url": "https://example.com/forum/thread/12345",
            "date_published": "2018-06-01",
            "date_accessed": "2026-05-15",
            "access_method": "playwright_probe",
            "evidence": "User says Playwright is slow on Windows.",
            "quote_or_anchor": "",
        },
    ]

    s1 = score_row(sample[0], today=fixed_today)
    assert s1.type_score == 4, f"official=4, got {s1.type_score}"
    assert s1.authority == 5, f"openalex.org=5, got {s1.authority}"
    assert s1.recency == 4, f"2024 vs 2026 -> 4 (<=3y), got {s1.recency}"
    assert s1.traceability >= 3, f"expected >=3, got {s1.traceability}"
    assert s1.recency == s1.freshness
    assert s1.methodology == s1.traceability
    assert s1.band in {"high", "medium"}, f"expected high/medium, got {s1.band}"
    print(f"  [PASS] official OpenAlex row -> total={s1.total} band={s1.band}")

    s2 = score_row(sample[1], today=fixed_today)
    assert s2.type_score == 5, f"primary=5, got {s2.type_score}"
    assert s2.recency == 5, f"2025 vs 2026 -> 5 (<=1y), got {s2.recency}"
    assert s2.band == "high", f"expected high, got {s2.band} (total {s2.total})"
    print(f"  [PASS] primary Playwright row -> total={s2.total} band={s2.band}")

    s3 = score_row(sample[2], today=fixed_today)
    assert s3.type_score == 1, f"community=1, got {s3.type_score}"
    # 2018 vs 2026 = 8 years -> falls in 8-15y bucket -> 2
    # 2018-06-01 vs 2026-05-15 is just under 8 years after month adjust => band medium/low
    assert s3.recency in {2, 3}, f"2018 vs 2026 expected recency 2-3, got {s3.recency}"
    assert s3.band in {"low", "medium"}, f"expected low/medium, got {s3.band} (total {s3.total})"
    print(f"  [PASS] community forum row -> total={s3.total} band={s3.band}")

    # Undated source: date_accessed alone must not grant high freshness
    s_undated = score_row(
        {
            "claim_id": "C_UNDATED",
            "source_type": "primary",
            "source_title": "Undated note",
            "source_url": "https://example.com/note",
            "date_published": "",
            "date_accessed": "2026-05-15",
            "access_method": "fetch",
            "evidence": "x" * 40,
            "quote_or_anchor": "anchor",
        },
        today=fixed_today,
    )
    assert s_undated.recency == 1, (
        f"undated source must not use date_accessed for freshness, got {s_undated.recency}"
    )
    assert s_undated.base_total == s_undated.total - s_undated.social_bonus
    print(f"  [PASS] undated source freshness low -> recency={s_undated.recency}")
    # Missing review input is distinguishable from a partial review and must
    # never report final reviewed high confidence.
    if s2.automated_band == "high":
        assert s2.review_status == "unreviewed"
        assert s2.final_reviewed_confidence != "high"
        assert "pending" in s2.final_reviewed_confidence
    unreviewed_round_trip = score_row(
        {
            **{f"review_{gate}": "manual_required" for gate in REQUIRED_REVIEW_GATES},
            "review_reproducibility": "",
            "review_status": "unreviewed",
        },
        today=fixed_today,
    )
    assert unreviewed_round_trip.review_status == "unreviewed"
    print("  [PASS] unreviewed rows cap final_reviewed_confidence")

    partial = Score(5, 5, 5, 5, 5, review_gates={"relevance": "pass"})
    assert partial.review_status == "pending_manual_review"
    assert partial.final_reviewed_confidence == "medium_pending_review"
    unknown = Score(
        5,
        5,
        5,
        5,
        5,
        review_gates={
            **{gate: "pass" for gate in REQUIRED_REVIEW_GATES},
            "unknown_gate": "pass",
        },
    )
    assert unknown.review_status == "pending_manual_review"
    persisted_unknown = score_row(
        {
            **{f"review_{gate}": "pass" for gate in REQUIRED_REVIEW_GATES},
            "review_unknown_gates": "unknown_gate",
        },
        today=fixed_today,
    )
    assert persisted_unknown.review_status == "pending_manual_review"
    print("  [PASS] partial and unknown review gates never become reviewed")

    reviewed_row = {
        **sample[1],
        **{f"review_{gate}": "pass" for gate in REQUIRED_REVIEW_GATES},
    }
    reviewed = score_row(reviewed_row, today=fixed_today)
    assert reviewed.review_status == "reviewed"
    assert reviewed.final_reviewed_confidence == reviewed.automated_band == "high"
    failed_row = {**reviewed_row, "review_reproducibility": "fail"}
    failed = score_row(failed_row, today=fixed_today)
    assert failed.review_gates["reproducibility"] == "fail"
    assert failed.review_status == "review_failed"
    assert failed.final_reviewed_confidence == "low_review_failed"
    print("  [PASS] complete human decisions are preserved and gate final confidence")

    with tempfile.TemporaryDirectory() as td:
        input_path = Path(td) / "review-input.csv"
        output_path = Path(td) / "review-output.csv"
        with input_path.open("w", newline="", encoding="utf-8") as f:
            fields = list(dict.fromkeys([*reviewed_row, *failed_row]))
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerow(reviewed_row)
            writer.writerow(failed_row)
        assert cmd_score(input_path, output_path, today=fixed_today) == 0
        with output_path.open(newline="", encoding="utf-8") as f:
            outputs = list(csv.DictReader(f))
        assert len(outputs) == 2
        output, failed_output = outputs
        assert output["review_status"] == "reviewed"
        assert output["final_reviewed_confidence"] == "high"
        assert output["freshness"] == output["recency"]
        assert output["traceability"] == output["methodology"]
        for gate in REQUIRED_REVIEW_GATES:
            assert output[f"review_{gate}"] == "pass"
        assert output["review_unknown_gates"] == ""
        assert failed_output["review_reproducibility"] == "fail"
        assert failed_output["review_status"] == "review_failed"
        assert failed_output["final_reviewed_confidence"] == "low_review_failed"
    print("  [PASS] score CLI preserves valid human review decisions")

    for bad in ("2026-not-a-date", "2026-99-99", "2024-02-30", "9999-01-01"):
        sc_bad = score_recency(bad, "2026-05-15", fixed_today)
        assert sc_bad == 1, f"invalid date {bad!r} must score low, got {sc_bad}"
    assert parse_publication_date("2024-02-29") is not None  # leap year
    assert parse_publication_date("2023-02-29") is None  # non-leap
    assert parse_publication_date(2024) == date(2024, 1, 1)
    assert parse_publication_date(None) is None
    assert score_recency("2024", "", fixed_today) >= 4
    assert score_recency("2024-03", "", fixed_today) >= 4
    print("  [PASS] publication date validation (YYYY / YYYY-MM / YYYY-MM-DD)")

    # Apex domain extractor
    assert _apex("https://docs.openalex.org/x/y") == "openalex.org"
    assert _apex("https://www.ncbi.nlm.nih.gov/pubmed/123") == "nih.gov"
    assert _apex("https://example.co.uk/page") == "example.co.uk"
    print("  [PASS] apex-domain extractor")

    # --- Social scoring bands (v2.1) ---
    social_samples = [
        {
            "claim_id": "S001",
            "source_type": "primary",
            "source_title": "Reddit Post via Archive",
            "source_url": "https://web.archive.org/web/20260515/https://reddit.com/r/test/123",
            "date_published": "2026-01-10",
            "date_accessed": "2026-05-15",
            "access_method": "script",
            "evidence": "User posted about the topic with detailed analysis.",
            "quote_or_anchor": "'This is the exact quote from the post.'",
            "verifiability": "archive_snapshot",
            "notes": "author_handle=@testuser",
        },
        {
            "claim_id": "S002",
            "source_type": "community",
            "source_title": "Unverified Social Claim",
            "source_url": "https://example.com/social/post/456",
            "date_published": "2026-03-01",
            "date_accessed": "2026-05-15",
            "access_method": "screenshot",
            "evidence": "Short claim.",
            "quote_or_anchor": "",
            "verifiability": "unverified",
            "notes": "",
        },
        {
            "claim_id": "S003",
            "source_type": "primary",
            "source_title": "Direct API Capture",
            "source_url": "https://mastodon.social/@user/12345",
            "date_published": "2026-04-01",
            "date_accessed": "2026-05-15",
            "access_method": "api",
            "evidence": "Full post text captured directly from Mastodon API with hash verification.",
            "quote_or_anchor": "'Exact post content here.'",
            "verifiability": "direct_api",
            "notes": "author_handle=@user@mastodon.social",
        },
    ]

    ss1 = score_row(social_samples[0], today=fixed_today)
    # archive_snapshot -> +2, author_handle in notes -> +1 = social_bonus 3
    assert ss1.social_bonus == 3, f"expected social_bonus=3, got {ss1.social_bonus}"
    print(f"  [PASS] social archive_snapshot + author_handle -> social_bonus={ss1.social_bonus}, total={ss1.total}")

    ss2 = score_row(social_samples[1], today=fixed_today)
    # unverified -> -1, no author_handle -> social_bonus -1
    assert ss2.social_bonus == -1, f"expected social_bonus=-1, got {ss2.social_bonus}"
    print(f"  [PASS] social unverified -> social_bonus={ss2.social_bonus}, total={ss2.total}")

    ss3 = score_row(social_samples[2], today=fixed_today)
    # direct_api -> no archive bonus, author_handle in notes -> +1 = social_bonus 1
    assert ss3.social_bonus == 1, f"expected social_bonus=1, got {ss3.social_bonus}"
    print(f"  [PASS] social direct_api + author_handle -> social_bonus={ss3.social_bonus}, total={ss3.total}")

    print("\nAll self-tests passed!")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        prog="score_source.py",
        description=(
            "Apply the source-quality rubric to an evidence ledger and emit "
            "per-row scores."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("score", help="Score a ledger CSV.")
    s.add_argument(
        "--file", required=True, type=Path, help="Evidence-ledger CSV input."
    )
    s.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output CSV path (default: stdout).",
    )

    sub.add_parser("self-test", help="Run offline self-tests.")

    args = p.parse_args()
    if args.cmd == "score":
        return cmd_score(args.file, args.out)
    if args.cmd == "self-test":
        return cmd_self_test()
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
