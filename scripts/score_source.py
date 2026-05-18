#!/usr/bin/env python3
"""Apply the source-quality rubric to an evidence-ledger CSV.

The rubric is documented in ``references/source-quality-rubric.md`` and
scores each source across five dimensions:

* **Type** (5): primary/dataset/code/filing > paper/official > pdf/secondary > community > unknown
* **Authority** (5): how authoritative the publisher is for the claim
* **Recency** (5): how recent the publication / access is relative to the claim
* **Methodology** (5): for empirical / dataset claims, how transparent the methods are
* **Independence** (5): how independent the source is from the entities it discusses

Each axis is 0-5 (integer). The total is 0-25 and is bucketed into a
confidence band:

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
import sys
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


@dataclass
class Score:
    type_score: int
    authority: int
    recency: int
    methodology: int
    independence: int
    social_bonus: int = 0

    @property
    def total(self) -> int:
        return (
            self.type_score
            + self.authority
            + self.recency
            + self.methodology
            + self.independence
            + self.social_bonus
        )

    @property
    def band(self) -> str:
        t = self.total
        if t >= 20:
            return "high"
        if t >= 13:
            return "medium"
        return "low"


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


def score_recency(date_published: str, date_accessed: str, today: date) -> int:
    """Score 0-5 based on how recent date_published is relative to today.

    Falls back to date_accessed if date_published is missing.
    """
    s = (date_published or date_accessed or "").strip()
    if not s:
        return 1
    try:
        # accept YYYY, YYYY-MM, YYYY-MM-DD (we just need the year)
        year = int(s[:4])
    except (ValueError, IndexError):
        return 1
    years_old = today.year - year
    if years_old <= 1:
        return 5
    if years_old <= 3:
        return 4
    if years_old <= 7:
        return 3
    if years_old <= 15:
        return 2
    return 1


def score_methodology(row: dict[str, str]) -> int:
    """Score 0-5 based on indicators in the row that methods are disclosed.

    Heuristics (deterministic):
    * +2 if there is a non-empty quote_or_anchor (the evidence is anchored
      to a specific snippet, indicating verifiability).
    * +1 if source_type is in {primary, dataset, code, filing}.
    * +1 if access_method is reproducible (fetch / api / playwright_probe /
      script). Manual screenshots score 0 here.
    * +1 if the evidence cell is non-trivial (> 30 chars).
    """
    sc = 0
    if (row.get("quote_or_anchor") or "").strip():
        sc += 2
    st = (row.get("source_type") or "").strip().lower()
    if st in {"primary", "dataset", "code", "filing"}:
        sc += 1
    am = (row.get("access_method") or "").strip().lower()
    if any(am.startswith(p) for p in ("fetch", "api", "playwright", "script", "rest")):
        sc += 1
    ev = (row.get("evidence") or "").strip()
    if len(ev) > 30:
        sc += 1
    return min(sc, 5)


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
        recency=score_recency(
            row.get("date_published") or "",
            row.get("date_accessed") or "",
            today,
        ),
        methodology=score_methodology(row),
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
        out_rows.append(
            {
                "claim_id": r.get("claim_id", ""),
                "source_url": r.get("source_url", ""),
                "type_score": sc.type_score,
                "authority": sc.authority,
                "recency": sc.recency,
                "methodology": sc.methodology,
                "independence": sc.independence,
                "social_bonus": sc.social_bonus,
                "total": sc.total,
                "band": sc.band,
            }
        )
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
    assert s1.methodology >= 3, f"expected >=3, got {s1.methodology}"
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
    assert s3.recency == 2, f"2018 vs 2026 -> 2 (8-15y), got {s3.recency}"
    assert s3.band == "low", f"expected low, got {s3.band} (total {s3.total})"
    print(f"  [PASS] community forum row -> total={s3.total} band={s3.band}")

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
