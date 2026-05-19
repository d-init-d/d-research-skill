#!/usr/bin/env python3
"""Evidence ledger helper for D Research.

Commands:
  init --out evidence.csv
  validate --file evidence.csv
  sign --file evidence.csv --key-env LEDGER_KEY [--out evidence.csv.hmac]
  verify --file evidence.csv --key-env LEDGER_KEY [--sig evidence.csv.hmac]
  prov-export --file evidence.csv [--out prov.jsonld]
  self-test

The `sign`/`verify` subcommands implement tamper-evident audit trails
using HMAC-SHA256 over the canonicalised CSV bytes (rewritten with a
stable field order and Unix line endings before hashing). This is *not*
the "Merkle tree + RSA-4096" sketched by an earlier README draft - HMAC
is a much simpler primitive that does not require key management
infrastructure, but it is sufficient for tamper-evidence when the
signing key is held by a single trusted party.

The `prov-export` subcommand emits a PROV-O JSON-LD document describing
the ledger as a graph of prov:Entity (claims/sources) and prov:Activity
(extraction events identified by ``prov_activity_id``). It accepts
14-column legacy, 19-column v2.1, and 22-column v3.0 ledgers; the
prov:Activity graph is only populated for rows whose ``prov_activity_id``
column exists and is non-empty (so legacy and v2.1 exports yield an
entity-only graph).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import io
import os
import re
import sys
from pathlib import Path

FIELDS = [
    "claim_id",
    "claim",
    "sub_question",
    "source_title",
    "source_url",
    "source_type",
    "date_published",
    "date_accessed",
    "access_method",
    "evidence",
    "quote_or_anchor",
    "contradiction",
    "confidence",
    "notes",
    "archive_url",
    "content_hash",
    "snapshot_status",
    "verifiability",
    "verifiability_note",
    "license_spdx",
    "robots_status",
    "prov_activity_id",
]

# The original 14 columns (pre-v2.1) for backward compatibility.
FIELDS_LEGACY = FIELDS[:14]

# v2.1 social-media archival schema (19 columns).
FIELDS_V2_1 = FIELDS[:19]

# New columns added in v2.1 for social-media archival support.
FIELDS_SOCIAL = FIELDS[14:19]

# Optional v3.0 provenance/compliance columns appended at the end.
FIELDS_PROVENANCE = FIELDS[19:]

# All currently-accepted header sets, in the order validate_ledger /
# canonicalise / sign / verify try to match them. Newest first.
ACCEPTED_FIELD_SETS = [FIELDS, FIELDS_V2_1, FIELDS_LEGACY]

VALID_SOURCE_TYPES = {
    "primary",
    "official",
    "dataset",
    "code",
    "pdf",
    "paper",
    "filing",
    "secondary",
    "community",
    "unknown",
}

VALID_CONFIDENCE = {"high", "medium", "low"}
VALID_CONTRADICTION = {"none", "possible", "direct", "unresolved", ""}

VALID_VERIFIABILITY = {
    "direct_api",
    "direct_api_deleted",
    "archive_snapshot",
    "screenshot_only",
    "unverified",
    "",
}

VALID_SNAPSHOT_STATUS = {"intact", "edited", "deleted", "unknown", ""}

# v3.0 optional provenance/compliance column rules.
VALID_ROBOTS_STATUS = {
    "allowed",
    "disallowed",
    "unknown",
    "not_checked",
    "not_applicable",
    "",
}

# Lightweight SPDX-like identifier check. Accepts:
#   - empty string
#   - NOASSERTION
#   - LicenseRef-<token>
#   - SPDX-style tokens such as MIT, Apache-2.0, CC-BY-4.0, GPL-3.0-or-later
# This is deliberately permissive - we only catch obviously invalid values
# (whitespace, weird characters) and let upstream tools normalise the rest.
_LICENSE_SPDX_RE = re.compile(r"^[A-Za-z0-9.\-+]{1,64}$")


def _is_valid_license_spdx(value: str) -> bool:
    if not value:
        return True
    if value == "NOASSERTION":
        return True
    if value.startswith("LicenseRef-"):
        return bool(_LICENSE_SPDX_RE.match(value[len("LicenseRef-"):])) if value[len("LicenseRef-"):] else False
    return bool(_LICENSE_SPDX_RE.match(value))


# prov_activity_id is intentionally permissive: any non-whitespace token up
# to 128 chars is acceptable. We recommend `prov:<slug>` or a UUID-like
# string in docs, but we do not enforce a specific shape.
_PROV_ID_RE = re.compile(r"^\S{1,128}$")


def _is_valid_prov_activity_id(value: str) -> bool:
    if not value:
        return True
    return bool(_PROV_ID_RE.match(value))


def init_ledger(out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
    print(f"created {out}")


def validate_ledger(file: Path) -> int:
    errors: list[str] = []
    with file.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # Accept legacy (14), v2.1 social (19), and v3.0 provenance (22).
        if reader.fieldnames == FIELDS:
            active_fields = FIELDS
        elif reader.fieldnames == FIELDS_V2_1:
            active_fields = FIELDS_V2_1
        elif reader.fieldnames == FIELDS_LEGACY:
            active_fields = FIELDS_LEGACY
        else:
            errors.append(
                "header mismatch: expected 14, 19, or 22 column header; "
                f"got {reader.fieldnames}"
            )
            print("\n".join(errors), file=sys.stderr)
            return 1
        has_social_cols = len(active_fields) >= 19
        has_prov_cols = len(active_fields) >= 22
        seen_ids: set[str] = set()
        for i, row in enumerate(reader, start=2):
            claim_id = row.get("claim_id", "").strip()
            if not claim_id:
                errors.append(f"line {i}: missing claim_id")
            elif claim_id in seen_ids:
                errors.append(f"line {i}: duplicate claim_id {claim_id}")
            seen_ids.add(claim_id)
            if not row.get("claim", "").strip():
                errors.append(f"line {i}: missing claim")
            if not row.get("source_url", "").strip():
                errors.append(f"line {i}: missing source_url")
            source_type = row.get("source_type", "").strip().lower()
            if source_type and source_type not in VALID_SOURCE_TYPES:
                errors.append(f"line {i}: invalid source_type {source_type}")
            confidence = row.get("confidence", "").strip().lower()
            if confidence and confidence not in VALID_CONFIDENCE:
                errors.append(f"line {i}: invalid confidence {confidence}")
            contradiction = row.get("contradiction", "").strip().lower()
            if contradiction not in VALID_CONTRADICTION:
                errors.append(f"line {i}: invalid contradiction {contradiction}")
            if has_social_cols:
                verifiability = row.get("verifiability", "").strip().lower()
                if verifiability not in VALID_VERIFIABILITY:
                    errors.append(f"line {i}: invalid verifiability {verifiability!r}")
                snapshot_status = row.get("snapshot_status", "").strip().lower()
                if snapshot_status not in VALID_SNAPSHOT_STATUS:
                    errors.append(f"line {i}: invalid snapshot_status {snapshot_status!r}")
            if has_prov_cols:
                license_spdx = row.get("license_spdx", "").strip()
                if not _is_valid_license_spdx(license_spdx):
                    errors.append(
                        f"line {i}: invalid license_spdx {license_spdx!r} "
                        "(expected SPDX-like token, NOASSERTION, LicenseRef-..., or empty)"
                    )
                robots_status = row.get("robots_status", "").strip().lower()
                if robots_status not in VALID_ROBOTS_STATUS:
                    errors.append(
                        f"line {i}: invalid robots_status {robots_status!r} "
                        f"(expected one of {sorted(VALID_ROBOTS_STATUS)})"
                    )
                prov_id = row.get("prov_activity_id", "").strip()
                if not _is_valid_prov_activity_id(prov_id):
                    errors.append(
                        f"line {i}: invalid prov_activity_id {prov_id!r}"
                    )
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"validated {file}")
    return 0


# ----------------------------------------------------------------------
# Tamper-evidence: HMAC-SHA256 over the canonicalised CSV bytes.
# ----------------------------------------------------------------------

SIG_VERSION = "d-research-skill/hmac-sha256/v1"


def canonicalise(file: Path) -> bytes:
    """Rewrite the CSV with a stable field order, Unix line endings, and no
    trailing whitespace, then return its UTF-8 bytes.

    This is the input that gets HMAC'd. Both `sign` and `verify` MUST go
    through this function so that benign formatting differences (e.g. a
    text editor switching to CRLF) do not falsely invalidate a signature.

    Supports both legacy (14-column) and extended (19-column) ledgers.
    When the new social columns are present, they are included in the
    canonical bytes so that tampering with them is detected.
    """
    with file.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames == FIELDS:
            active_fields = FIELDS
        elif reader.fieldnames == FIELDS_V2_1:
            active_fields = FIELDS_V2_1
        elif reader.fieldnames == FIELDS_LEGACY:
            active_fields = FIELDS_LEGACY
        else:
            raise ValueError(
                "header mismatch: expected 14, 19, or 22 column header; "
                f"got {reader.fieldnames}"
            )
        rows = list(reader)
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=active_fields, lineterminator="\n", quoting=csv.QUOTE_MINIMAL
    )
    writer.writeheader()
    for row in rows:
        clean = {k: (row.get(k) or "").strip() for k in active_fields}
        writer.writerow(clean)
    return buf.getvalue().encode("utf-8")


def _load_key(key_env: str) -> bytes:
    val = os.environ.get(key_env)
    if not val:
        raise RuntimeError(
            f"environment variable {key_env!r} is not set or is empty"
        )
    return val.encode("utf-8")


def sign_ledger(file: Path, key_env: str, out: Path | None) -> int:
    try:
        key = _load_key(key_env)
        body = canonicalise(file)
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    digest = hmac.new(key, body, hashlib.sha256).hexdigest()
    sig_path = out or file.with_suffix(file.suffix + ".hmac")
    sig_path.parent.mkdir(parents=True, exist_ok=True)
    sig_path.write_text(
        f"{SIG_VERSION} {digest}\n", encoding="utf-8"
    )
    print(f"signed {file} -> {sig_path}")
    return 0


def verify_ledger(file: Path, key_env: str, sig: Path | None) -> int:
    sig_path = sig or file.with_suffix(file.suffix + ".hmac")
    if not sig_path.is_file():
        print(f"error: signature file not found: {sig_path}", file=sys.stderr)
        return 2
    try:
        key = _load_key(key_env)
        body = canonicalise(file)
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    content = sig_path.read_text(encoding="utf-8").strip()
    parts = content.split()
    if len(parts) != 2 or parts[0] != SIG_VERSION:
        print(
            f"error: unrecognised signature format in {sig_path}: {content!r}",
            file=sys.stderr,
        )
        return 2
    stored = parts[1].lower()
    actual = hmac.new(key, body, hashlib.sha256).hexdigest()
    if hmac.compare_digest(stored, actual):
        print(f"verified {file} matches {sig_path}")
        return 0
    print(
        f"TAMPER DETECTED: {file} does not match {sig_path}",
        file=sys.stderr,
    )
    print(f"  stored:   {stored}", file=sys.stderr)
    print(f"  computed: {actual}", file=sys.stderr)
    return 1


def prov_export(file: Path, out: Path | None) -> int:
    """Emit a PROV-O JSON-LD graph for an evidence ledger.

    The output uses a tiny PROV-O subset:
      - prov:Entity     for each ledger row (the claim) and its source URL
      - prov:Activity   for each distinct prov_activity_id
      - prov:wasGeneratedBy linking claims to the activity that produced them
      - prov:used       linking activities to source URLs

    Rows without a prov_activity_id are still exported as entities; they
    just do not participate in the activity graph.
    """
    import json

    try:
        with file.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames not in (FIELDS, FIELDS_V2_1, FIELDS_LEGACY):
                print(
                    "error: prov-export requires a 14, 19, or 22 column ledger; "
                    f"got {reader.fieldnames}",
                    file=sys.stderr,
                )
                return 1
            rows = list(reader)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    graph: list[dict] = []
    activities: dict[str, dict] = {}
    seen_sources: dict[str, dict] = {}

    for row in rows:
        claim_id = (row.get("claim_id") or "").strip()
        if not claim_id:
            continue
        source_url = (row.get("source_url") or "").strip()
        source_title = (row.get("source_title") or "").strip()
        prov_id = (row.get("prov_activity_id") or "").strip()
        license_spdx = (row.get("license_spdx") or "").strip()
        robots_status = (row.get("robots_status") or "").strip()
        access_method = (row.get("access_method") or "").strip()
        date_accessed = (row.get("date_accessed") or "").strip()

        # Claim entity
        claim_entity: dict = {
            "@id": f"claim:{claim_id}",
            "@type": "prov:Entity",
            "rdfs:label": (row.get("claim") or "").strip()[:200],
            "dcterms:identifier": claim_id,
        }
        if prov_id:
            claim_entity["prov:wasGeneratedBy"] = {"@id": prov_id}
        if license_spdx:
            claim_entity["dcterms:license"] = license_spdx
        graph.append(claim_entity)

        # Source entity (deduplicated)
        if source_url and source_url not in seen_sources:
            source_entity = {
                "@id": source_url,
                "@type": "prov:Entity",
                "rdfs:label": source_title or source_url,
            }
            if license_spdx:
                source_entity["dcterms:license"] = license_spdx
            if robots_status:
                source_entity["dres:robotsStatus"] = robots_status
            seen_sources[source_url] = source_entity
            graph.append(source_entity)

        # Activity (deduplicated by id)
        if prov_id and prov_id not in activities:
            activity = {
                "@id": prov_id,
                "@type": "prov:Activity",
                "rdfs:label": access_method or "extraction",
            }
            if date_accessed:
                activity["prov:endedAtTime"] = date_accessed
            activity["prov:used"] = []
            activities[prov_id] = activity
            graph.append(activity)
        if prov_id and source_url:
            used_list = activities[prov_id]["prov:used"]
            ref = {"@id": source_url}
            if ref not in used_list:
                used_list.append(ref)

    doc = {
        "@context": {
            "prov": "http://www.w3.org/ns/prov#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "dcterms": "http://purl.org/dc/terms/",
            "dres": "https://github.com/d-init-d/d-research-skill/ns#",
        },
        "@graph": graph,
    }
    body = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    if out is None:
        print(body)
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(body, encoding="utf-8")
        print(f"wrote PROV-O export to {out}")
    return 0


def self_test() -> int:
    import json
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "evidence.csv"
        init_ledger(path)
        if validate_ledger(path) != 0:
            return 1
        # Sign / verify / tamper-detection round-trip.
        os.environ["D_RESEARCH_LEDGER_KEY"] = "unit-test-key-do-not-use-in-prod"
        # Add one valid row with the new social columns populated.
        with path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writerow(
                {
                    "claim_id": "C001",
                    "claim": "the sky is blue",
                    "sub_question": "colour of the sky",
                    "source_title": "Example title",
                    "source_url": "https://example.com/sky",
                    "source_type": "primary",
                    "date_published": "2024-01-01",
                    "date_accessed": "2026-05-15",
                    "access_method": "fetch",
                    "evidence": "observed",
                    "quote_or_anchor": "",
                    "contradiction": "none",
                    "confidence": "high",
                    "notes": "",
                    "archive_url": "https://web.archive.org/web/20260515/https://example.com/sky",
                    "content_hash": "abc123def456",
                    "snapshot_status": "intact",
                    "verifiability": "direct_api",
                    "verifiability_note": "Fetched directly from public API.",
                }
            )
        sig_path = path.with_suffix(".csv.hmac")
        rc = sign_ledger(path, "D_RESEARCH_LEDGER_KEY", None)
        if rc != 0:
            print("sign failed", file=sys.stderr)
            return 1
        if verify_ledger(path, "D_RESEARCH_LEDGER_KEY", None) != 0:
            print("initial verify failed", file=sys.stderr)
            return 1
        # Tamper with a legacy column; verify must reject.
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace("the sky is blue", "the sky is green"),
            encoding="utf-8",
        )
        if verify_ledger(path, "D_RESEARCH_LEDGER_KEY", None) == 0:
            print("tamper on legacy column not detected", file=sys.stderr)
            return 1
        # Restore and re-sign for next tamper test.
        path.write_text(text, encoding="utf-8")
        sign_ledger(path, "D_RESEARCH_LEDGER_KEY", None)

        # Tamper with a NEW social column; verify must reject.
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace("direct_api", "unverified"),
            encoding="utf-8",
        )
        if verify_ledger(path, "D_RESEARCH_LEDGER_KEY", None) == 0:
            print("tamper on verifiability column not detected", file=sys.stderr)
            return 1
        # Restore and re-sign for next tamper test.
        path.write_text(text, encoding="utf-8")
        sign_ledger(path, "D_RESEARCH_LEDGER_KEY", None)

        # Tamper with snapshot_status column; verify must reject.
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace("intact", "deleted"),
            encoding="utf-8",
        )
        if verify_ledger(path, "D_RESEARCH_LEDGER_KEY", None) == 0:
            print("tamper on snapshot_status column not detected", file=sys.stderr)
            return 1

        sig_path.unlink(missing_ok=True)

        # --- Test backward compatibility with legacy (14-column) ledger ---
        legacy_path = Path(d) / "legacy.csv"
        with legacy_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS_LEGACY)
            writer.writeheader()
            writer.writerow(
                {
                    "claim_id": "C001",
                    "claim": "legacy claim",
                    "sub_question": "test",
                    "source_title": "Legacy Source",
                    "source_url": "https://example.com/legacy",
                    "source_type": "primary",
                    "date_published": "2024-01-01",
                    "date_accessed": "2026-05-15",
                    "access_method": "fetch",
                    "evidence": "observed",
                    "quote_or_anchor": "",
                    "contradiction": "none",
                    "confidence": "high",
                    "notes": "",
                }
            )
        if validate_ledger(legacy_path) != 0:
            print("legacy ledger validation failed", file=sys.stderr)
            return 1
        rc = sign_ledger(legacy_path, "D_RESEARCH_LEDGER_KEY", None)
        if rc != 0:
            print("legacy sign failed", file=sys.stderr)
            return 1
        if verify_ledger(legacy_path, "D_RESEARCH_LEDGER_KEY", None) != 0:
            print("legacy verify failed", file=sys.stderr)
            return 1

        # --- Test validation rejects invalid verifiability/snapshot_status ---
        bad_path = Path(d) / "bad_verifiability.csv"
        with bad_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerow(
                {
                    "claim_id": "C001",
                    "claim": "test claim",
                    "sub_question": "test",
                    "source_title": "Test",
                    "source_url": "https://example.com",
                    "source_type": "primary",
                    "date_published": "2024-01-01",
                    "date_accessed": "2026-05-15",
                    "access_method": "fetch",
                    "evidence": "test",
                    "quote_or_anchor": "",
                    "contradiction": "none",
                    "confidence": "high",
                    "notes": "",
                    "archive_url": "",
                    "content_hash": "",
                    "snapshot_status": "INVALID_STATUS",
                    "verifiability": "INVALID_VALUE",
                    "verifiability_note": "",
                }
            )
        if validate_ledger(bad_path) == 0:
            print("validation should have rejected invalid verifiability/snapshot_status", file=sys.stderr)
            return 1

        # --- Test v3.0 (22-column) ledger validates/signs/verifies ---
        v3_path = Path(d) / "v3.csv"
        with v3_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerow(
                {
                    "claim_id": "C001",
                    "claim": "v3 claim",
                    "sub_question": "test",
                    "source_title": "Source",
                    "source_url": "https://example.com/v3",
                    "source_type": "primary",
                    "date_published": "2024-01-01",
                    "date_accessed": "2026-05-19",
                    "access_method": "fetch",
                    "evidence": "test evidence",
                    "quote_or_anchor": "",
                    "contradiction": "none",
                    "confidence": "high",
                    "notes": "",
                    "archive_url": "",
                    "content_hash": "",
                    "snapshot_status": "intact",
                    "verifiability": "direct_api",
                    "verifiability_note": "Public API.",
                    "license_spdx": "CC-BY-4.0",
                    "robots_status": "allowed",
                    "prov_activity_id": "prov:fetch:abcd1234",
                }
            )
        if validate_ledger(v3_path) != 0:
            print("v3.0 ledger validation failed", file=sys.stderr)
            return 1
        if sign_ledger(v3_path, "D_RESEARCH_LEDGER_KEY", None) != 0:
            print("v3.0 sign failed", file=sys.stderr)
            return 1
        if verify_ledger(v3_path, "D_RESEARCH_LEDGER_KEY", None) != 0:
            print("v3.0 verify failed", file=sys.stderr)
            return 1
        # Tamper with prov_activity_id; verify must reject.
        text = v3_path.read_text(encoding="utf-8")
        v3_path.write_text(
            text.replace("prov:fetch:abcd1234", "prov:fetch:00000000"),
            encoding="utf-8",
        )
        if verify_ledger(v3_path, "D_RESEARCH_LEDGER_KEY", None) == 0:
            print("tamper on prov_activity_id not detected", file=sys.stderr)
            return 1
        v3_path.write_text(text, encoding="utf-8")
        sign_ledger(v3_path, "D_RESEARCH_LEDGER_KEY", None)
        # Tamper with license_spdx; verify must reject.
        text = v3_path.read_text(encoding="utf-8")
        v3_path.write_text(
            text.replace("CC-BY-4.0", "MIT"),
            encoding="utf-8",
        )
        if verify_ledger(v3_path, "D_RESEARCH_LEDGER_KEY", None) == 0:
            print("tamper on license_spdx not detected", file=sys.stderr)
            return 1
        v3_path.write_text(text, encoding="utf-8")

        # --- Test 22-column validation rejects bad provenance values ---
        bad_prov = Path(d) / "bad_prov.csv"
        with bad_prov.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerow(
                {
                    "claim_id": "C001", "claim": "x", "sub_question": "",
                    "source_title": "", "source_url": "https://x.example",
                    "source_type": "primary", "date_published": "",
                    "date_accessed": "", "access_method": "fetch",
                    "evidence": "", "quote_or_anchor": "",
                    "contradiction": "none", "confidence": "high", "notes": "",
                    "archive_url": "", "content_hash": "",
                    "snapshot_status": "", "verifiability": "",
                    "verifiability_note": "",
                    "license_spdx": "Not A License Token",
                    "robots_status": "INVALID",
                    "prov_activity_id": "has space invalid",
                }
            )
        if validate_ledger(bad_prov) == 0:
            print(
                "validation should have rejected invalid provenance fields",
                file=sys.stderr,
            )
            return 1

        # --- Test prov-export on a 22-column ledger ---
        prov_out = Path(d) / "prov.jsonld"
        if prov_export(v3_path, prov_out) != 0:
            print("prov-export failed", file=sys.stderr)
            return 1
        prov_doc = json.loads(prov_out.read_text(encoding="utf-8"))
        if "@graph" not in prov_doc or not prov_doc["@graph"]:
            print("prov-export missing @graph", file=sys.stderr)
            return 1
        types = {n.get("@type") for n in prov_doc["@graph"]}
        if "prov:Entity" not in types:
            print("prov-export missing prov:Entity", file=sys.stderr)
            return 1
        if "prov:Activity" not in types:
            print("prov-export missing prov:Activity", file=sys.stderr)
            return 1
        # wasGeneratedBy + used links present
        joined = json.dumps(prov_doc)
        if "prov:wasGeneratedBy" not in joined:
            print("prov-export missing prov:wasGeneratedBy", file=sys.stderr)
            return 1
        if "prov:used" not in joined:
            print("prov-export missing prov:used", file=sys.stderr)
            return 1

    print("evidence_ledger self-test ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Evidence ledger helper")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init")
    p_init.add_argument("--out", default="evidence.csv")
    p_val = sub.add_parser("validate")
    p_val.add_argument("--file", default="evidence.csv")
    p_sign = sub.add_parser("sign", help="Emit an HMAC sidecar for the ledger.")
    p_sign.add_argument("--file", default="evidence.csv")
    p_sign.add_argument(
        "--key-env",
        default="D_RESEARCH_LEDGER_KEY",
        help="Environment variable holding the HMAC key.",
    )
    p_sign.add_argument(
        "--out",
        default=None,
        help="Output sidecar path (default: <ledger>.csv.hmac).",
    )
    p_ver = sub.add_parser(
        "verify", help="Verify an HMAC sidecar against the ledger."
    )
    p_ver.add_argument("--file", default="evidence.csv")
    p_ver.add_argument(
        "--key-env",
        default="D_RESEARCH_LEDGER_KEY",
        help="Environment variable holding the HMAC key.",
    )
    p_ver.add_argument(
        "--sig",
        default=None,
        help="Signature sidecar path (default: <ledger>.csv.hmac).",
    )
    p_prov = sub.add_parser(
        "prov-export",
        help="Export the ledger as a PROV-O JSON-LD graph.",
    )
    p_prov.add_argument("--file", default="evidence.csv")
    p_prov.add_argument(
        "--out",
        default=None,
        help="Output JSON-LD path (default: stdout).",
    )
    sub.add_parser("self-test")
    args = parser.parse_args()
    if args.cmd == "init":
        init_ledger(Path(args.out))
        return 0
    if args.cmd == "validate":
        return validate_ledger(Path(args.file))
    if args.cmd == "sign":
        out = Path(args.out) if args.out else None
        return sign_ledger(Path(args.file), args.key_env, out)
    if args.cmd == "verify":
        sig = Path(args.sig) if args.sig else None
        return verify_ledger(Path(args.file), args.key_env, sig)
    if args.cmd == "prov-export":
        out = Path(args.out) if args.out else None
        return prov_export(Path(args.file), out)
    if args.cmd == "self-test":
        return self_test()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
