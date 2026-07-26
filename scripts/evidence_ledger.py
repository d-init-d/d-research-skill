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
(extraction events identified by ``prov_activity_id``). It accepts exact
14-column legacy, 19-column v2.1, 22-column v3.0, 23-column v3.1, and
37-column v3.3 ledgers. The prov:Activity graph is populated only for rows
whose ``prov_activity_id`` exists and is non-empty.
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
from datetime import datetime, timedelta, timezone
from pathlib import Path

FIELDS_BASE = [
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

# v3.1 optional column (schema-compatible extension).
FIELDS_V3_1 = FIELDS_BASE + ["record_type"]

# v3.3 investigative-policy columns. These are appended after the exact v3.1
# header so older ledgers remain byte-for-byte schema compatible.
FIELDS_POLICY = [
    "source_access_class",
    "subject_class",
    "purpose_category",
    "policy_tier",
    "speaker_identity",
    "speaker_relationship",
    "content_origin",
    "lineage_id",
    "data_sensitivity",
    "discovery_disposition",
    "reporting_disposition",
    "redaction_class",
    "retention_until",
    "authorization_scope_hash",
]

# Current v3.3 schema (37 columns).
FIELDS_V3_3 = FIELDS_V3_1 + FIELDS_POLICY
FIELDS = FIELDS_V3_3

# The original 14 columns (pre-v2.1) for backward compatibility.
FIELDS_LEGACY = FIELDS_BASE[:14]

# v2.1 social-media archival schema (19 columns).
FIELDS_V2_1 = FIELDS_BASE[:19]

# v3.0 provenance (22 columns) without record_type.
FIELDS_V3_0 = FIELDS_BASE[:]

# New columns added in v2.1 for social-media archival support.
FIELDS_SOCIAL = FIELDS_BASE[14:19]

# Optional v3.0 provenance/compliance columns appended at the end.
FIELDS_PROVENANCE = FIELDS_BASE[19:]

# All currently-accepted *exact* header sets, in the order validate_ledger /
# canonicalise / sign / verify try to match them. Newest first.
ACCEPTED_FIELD_SETS = [
    FIELDS_V3_3,
    FIELDS_V3_1,
    FIELDS_V3_0,
    FIELDS_V2_1,
    FIELDS_LEGACY,
]

VALID_RECORD_TYPES = {"claim", "lead", "process", "blocker", ""}

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

VALID_SNAPSHOT_STATUS = {
    "intact",
    "edited",
    "deleted",
    "access_denied",
    "rate_limited",
    "unavailable",
    "malformed",
    "unknown",
    "",
}

# v3.0 optional provenance/compliance column rules.
VALID_ROBOTS_STATUS = {
    "allowed",
    "disallowed",
    "unknown",
    "not_checked",
    "not_applicable",
    "",
}

VALID_SOURCE_ACCESS_CLASSES = {
    "standard_public",
    "public_reporting",
    "authorized_provider",
    "user_provided_private",
    "raw_leak_lead_only",
    "prohibited_secret",
    "",
}

VALID_SUBJECT_CLASSES = {
    "organization",
    "public_role_person",
    "private_person",
    "self",
    "minor",
    "infrastructure",
    "event",
    "unknown",
    "",
}

VALID_PURPOSE_CATEGORIES = {
    "general_research",
    "academic",
    "journalism",
    "public_interest",
    "due_diligence",
    "fraud_prevention",
    "low_risk_factual",
    "self_research",
    "self_audit",
    "defensive_security",
    "threat_intel",
    "incident_response",
    "authorized_pentest",
    "",
}

VALID_POLICY_TIERS = {"R0", "R1", "R2", "R3", "R4", "RX", ""}

VALID_SPEAKER_IDENTITIES = {
    "official",
    "verified_public_role",
    "claimed_identity",
    "pseudonymous",
    "anonymous",
    "unknown",
    "",
}

VALID_SPEAKER_RELATIONSHIPS = {
    "subject",
    "authorized_representative",
    "firsthand",
    "journalist",
    "secondhand",
    "commentary",
    "repost",
    "unknown",
    "",
}

VALID_CONTENT_ORIGINS = {
    "original",
    "firsthand",
    "quote",
    "repost",
    "screenshot",
    "unknown",
    "",
}

VALID_DATA_SENSITIVITY = {
    "public",
    "professional",
    "personal",
    "sensitive",
    "secret",
    "minor",
    "",
}

VALID_DISCOVERY_DISPOSITIONS = {
    "permitted",
    "evidence",
    "lead_only",
    "context_only",
    "contradiction",
    "discarded",
    "blocked",
    "prohibited",
    "",
}

VALID_REPORTING_DISPOSITIONS = {
    "main_findings",
    "non_official_unverified_leads",
    "context_only",
    "blocked_prohibited_sources",
    "redacted",
    "excluded",
    "prohibited",
    "",
}

VALID_REDACTION_CLASSES = {
    "none",
    "personal_contact",
    "residential",
    "government_id",
    "financial",
    "medical",
    "family_minor",
    "whereabouts",
    "secret",
    "other_pii",
    "",
}

_LINEAGE_ID_RE = re.compile(r"^\S{1,128}$")
_SCOPE_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_RFC3339_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)

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


def _is_valid_lineage_id(value: str) -> bool:
    if not value:
        return True
    return bool(_LINEAGE_ID_RE.fullmatch(value))


def _is_valid_scope_hash(value: str) -> bool:
    if not value:
        return True
    return bool(_SCOPE_HASH_RE.fullmatch(value))


def _is_valid_retention_until(value: str) -> bool:
    """Accept an empty value or an RFC 3339 timestamp with a timezone."""
    if not value:
        return True
    if not _RFC3339_RE.fullmatch(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _parse_retention_until(value: str) -> datetime | None:
    if not _is_valid_retention_until(value):
        return None
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _retention_anchor(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def init_ledger(out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
    print(f"created {out}")


def _match_fieldnames(fieldnames: list[str] | None) -> list[str] | None:
    if fieldnames is None:
        return None
    names = list(fieldnames)
    for candidate in ACCEPTED_FIELD_SETS:
        if names == candidate:
            return candidate
    return None


def validate_ledger(file: Path) -> int:
    errors: list[str] = []
    with file.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # Accept only the canonical exact headers: legacy (14), v2.1 (19),
        # v3.0 (22), v3.1 (23), and v3.3 investigative policy (37).
        active_fields = _match_fieldnames(
            list(reader.fieldnames) if reader.fieldnames else None
        )
        if active_fields is None:
            errors.append(
                "header mismatch: expected 14, 19, 22, 23, or 37 column header; "
                f"got {reader.fieldnames}"
            )
            print("\n".join(errors), file=sys.stderr)
            return 1
        has_social_cols = len(active_fields) >= 19
        has_prov_cols = len(active_fields) >= 22
        has_record_type = "record_type" in active_fields
        has_policy_cols = active_fields == FIELDS_V3_3
        seen_ids: set[str] = set()
        for i, row in enumerate(reader, start=2):
            claim_id = row.get("claim_id", "").strip()
            if not claim_id:
                errors.append(f"line {i}: missing claim_id")
            elif claim_id in seen_ids:
                errors.append(f"line {i}: duplicate claim_id {claim_id}")
            seen_ids.add(claim_id)
            record_type = (row.get("record_type") or "").strip().lower()
            if not has_record_type or not record_type:
                record_type = "claim"  # default for pre-3.1 ledgers
            if record_type not in VALID_RECORD_TYPES - {""}:
                errors.append(
                    f"line {i}: invalid record_type {record_type!r} "
                    "(expected claim, lead, process, blocker, or empty)"
                )
            if record_type == "lead" and not has_policy_cols:
                errors.append(
                    f"line {i}: record_type=lead requires the 37-column v3.3 header"
                )
            if not row.get("claim", "").strip():
                errors.append(f"line {i}: missing claim")

            source_access_class = (
                (row.get("source_access_class") or "").strip().lower()
            )
            subject_class = (row.get("subject_class") or "").strip().lower()
            purpose_category = (
                (row.get("purpose_category") or "").strip().lower()
            )
            policy_tier = (row.get("policy_tier") or "").strip().upper()
            speaker_identity = (
                (row.get("speaker_identity") or "").strip().lower()
            )
            speaker_relationship = (
                (row.get("speaker_relationship") or "").strip().lower()
            )
            content_origin = (row.get("content_origin") or "").strip().lower()
            lineage_id = (row.get("lineage_id") or "").strip()
            data_sensitivity = (
                (row.get("data_sensitivity") or "").strip().lower()
            )
            discovery_disposition = (
                (row.get("discovery_disposition") or "").strip().lower()
            )
            reporting_disposition = (
                (row.get("reporting_disposition") or "").strip().lower()
            )
            redaction_class = (row.get("redaction_class") or "").strip().lower()
            retention_until = (row.get("retention_until") or "").strip()
            authorization_scope_hash = (
                (row.get("authorization_scope_hash") or "").strip()
            )

            # Process/blocker rows are exempt from narrative claim coverage, but
            # still need auditable source context, a reason, and a status.  A
            # public URL is optional for failures that happened before a stable
            # URL was reached; source_title then names the attempted source.
            source_url = row.get("source_url", "").strip()
            if not source_url and record_type == "claim":
                errors.append(f"line {i}: missing source_url")
            if (
                not source_url
                and record_type == "lead"
                and source_access_class != "raw_leak_lead_only"
            ):
                errors.append(f"line {i}: lead row needs source_url")
            if record_type in {"process", "blocker"}:
                source_title = (row.get("source_title") or "").strip()
                notes = (row.get("notes") or "").strip()
                evidence = (row.get("evidence") or "").strip()
                if not (source_url or source_title):
                    errors.append(
                        f"line {i}: {record_type} row needs source_url or source_title"
                    )
                if not (notes or evidence):
                    errors.append(
                        f"line {i}: {record_type} row needs a reason in evidence or notes"
                    )
                status_fields = (
                    (row.get("snapshot_status") or "").strip(),
                    (row.get("robots_status") or "").strip(),
                    (row.get("verifiability") or "").strip(),
                )
                structured_status = re.search(
                    r"\b(?:status|result|reason|fallback_result)\s*=\s*\S+",
                    notes,
                    flags=re.IGNORECASE,
                )
                if not any(status_fields) and structured_status is None:
                    errors.append(
                        f"line {i}: {record_type} row needs a status field or structured status/result in notes"
                    )
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
            if has_policy_cols:
                enum_values = (
                    (
                        "source_access_class",
                        source_access_class,
                        VALID_SOURCE_ACCESS_CLASSES,
                    ),
                    ("subject_class", subject_class, VALID_SUBJECT_CLASSES),
                    (
                        "purpose_category",
                        purpose_category,
                        VALID_PURPOSE_CATEGORIES,
                    ),
                    ("policy_tier", policy_tier, VALID_POLICY_TIERS),
                    (
                        "speaker_identity",
                        speaker_identity,
                        VALID_SPEAKER_IDENTITIES,
                    ),
                    (
                        "speaker_relationship",
                        speaker_relationship,
                        VALID_SPEAKER_RELATIONSHIPS,
                    ),
                    ("content_origin", content_origin, VALID_CONTENT_ORIGINS),
                    (
                        "data_sensitivity",
                        data_sensitivity,
                        VALID_DATA_SENSITIVITY,
                    ),
                    (
                        "discovery_disposition",
                        discovery_disposition,
                        VALID_DISCOVERY_DISPOSITIONS,
                    ),
                    (
                        "reporting_disposition",
                        reporting_disposition,
                        VALID_REPORTING_DISPOSITIONS,
                    ),
                    (
                        "redaction_class",
                        redaction_class,
                        VALID_REDACTION_CLASSES,
                    ),
                )
                for field_name, value, allowed in enum_values:
                    if value not in allowed:
                        errors.append(f"line {i}: invalid {field_name} {value!r}")

                required_policy_values = {
                    "source_access_class": source_access_class,
                    "subject_class": subject_class,
                    "purpose_category": purpose_category,
                    "policy_tier": policy_tier,
                    "data_sensitivity": data_sensitivity,
                    "discovery_disposition": discovery_disposition,
                    "reporting_disposition": reporting_disposition,
                    "redaction_class": redaction_class,
                }
                for field_name, value in required_policy_values.items():
                    if not value:
                        errors.append(
                            f"line {i}: 37-column ledger requires {field_name}"
                        )

                if policy_tier in {"R0", "R1"} and record_type in {"claim", "lead"}:
                    if subject_class in {
                        "public_role_person",
                        "private_person",
                        "self",
                        "minor",
                    }:
                        errors.append(
                            f"line {i}: {policy_tier} person rows must use R2 or R3"
                        )
                    if (
                        data_sensitivity not in {"public", "professional"}
                        and not (
                            record_type == "lead"
                            and source_access_class == "raw_leak_lead_only"
                            and data_sensitivity in {"personal", "sensitive"}
                        )
                    ):
                        errors.append(
                            f"line {i}: {policy_tier} permits only public/professional data"
                        )
                if policy_tier == "R2":
                    if subject_class not in {
                        "public_role_person",
                        "private_person",
                        "self",
                    }:
                        errors.append(f"line {i}: R2 requires a person/self subject")
                    if (
                        record_type in {"claim", "lead"}
                        and data_sensitivity not in {"public", "professional"}
                    ):
                        errors.append(
                            f"line {i}: R2 permits only public/professional data"
                        )
                if policy_tier == "R3" and subject_class not in {"self", "organization"}:
                    errors.append(f"line {i}: R3 requires self or organization subject")

                if reporting_disposition == "main_findings" and record_type != "claim":
                    errors.append(
                        f"line {i}: main_findings requires record_type=claim"
                    )
                if reporting_disposition == "non_official_unverified_leads" and record_type != "lead":
                    errors.append(
                        f"line {i}: non_official_unverified_leads requires record_type=lead"
                    )
                if discovery_disposition == "lead_only" and record_type != "lead":
                    errors.append(f"line {i}: lead_only requires record_type=lead")
                if data_sensitivity in {"personal", "sensitive"} and redaction_class in {
                    "",
                    "none",
                }:
                    errors.append(
                        f"line {i}: personal/sensitive data requires a redaction_class"
                    )

                if not _is_valid_lineage_id(lineage_id):
                    errors.append(f"line {i}: invalid lineage_id {lineage_id!r}")
                if not _is_valid_retention_until(retention_until):
                    errors.append(
                        f"line {i}: retention_until must be an RFC3339 "
                        "timestamp with timezone"
                    )
                if not _is_valid_scope_hash(authorization_scope_hash):
                    errors.append(
                        f"line {i}: authorization_scope_hash must be "
                        "sha256:<64 lowercase hex>"
                    )

                social_values = (
                    speaker_identity,
                    speaker_relationship,
                    content_origin,
                )
                if any(social_values) and not all(social_values):
                    errors.append(
                        f"line {i}: social classification requires speaker_identity, "
                        "speaker_relationship, and content_origin together"
                    )
                if reporting_disposition == "main_findings" and any(social_values):
                    direct_integrity = bool(
                        verifiability == "direct_api"
                        and snapshot_status == "intact"
                        and (row.get("content_hash") or "").strip()
                    )
                    archive_integrity = bool(
                        verifiability == "archive_snapshot"
                        and (row.get("archive_url") or "").strip()
                        and (row.get("content_hash") or "").strip()
                    )
                    notes_value = (row.get("notes") or "").strip().lower()
                    if not (
                        speaker_identity in {"official", "verified_public_role"}
                        and speaker_relationship
                        in {"subject", "authorized_representative"}
                        and content_origin == "original"
                        and (direct_integrity or archive_integrity)
                    ):
                        errors.append(
                            f"line {i}: social main_findings requires an official/"
                            "verified subject or representative, original content, "
                            "and intact hash-bound direct or archive evidence"
                        )
                    if not re.search(
                        r"(?:^|;\s*)claim_kind=statement_made(?:;|$)", notes_value
                    ):
                        errors.append(
                            f"line {i}: social main_findings requires "
                            "notes claim_kind=statement_made"
                        )
                if (
                    content_origin in {"quote", "repost", "screenshot"}
                    or speaker_relationship == "repost"
                ) and not lineage_id:
                    errors.append(
                        f"line {i}: derivative social evidence requires lineage_id"
                    )

                prohibited_for_evidence = (
                    data_sensitivity in {"secret", "minor"}
                    or subject_class == "minor"
                    or source_access_class == "prohibited_secret"
                    or policy_tier == "RX"
                    or discovery_disposition == "prohibited"
                    or reporting_disposition == "prohibited"
                )
                if record_type in {"claim", "lead"} and prohibited_for_evidence:
                    errors.append(
                        f"line {i}: secret, minor, RX, or prohibited material "
                        "cannot use record_type=claim or lead"
                    )
                if (
                    prohibited_for_evidence
                    and reporting_disposition == "main_findings"
                ):
                    errors.append(
                        f"line {i}: prohibited material cannot report under "
                        "main_findings"
                    )

                if (
                    source_access_class == "prohibited_secret"
                    or data_sensitivity == "secret"
                ):
                    secret_fields = {
                        "source_url": source_url,
                        "evidence": (row.get("evidence") or "").strip(),
                        "quote_or_anchor": (
                            row.get("quote_or_anchor") or ""
                        ).strip(),
                        "archive_url": (row.get("archive_url") or "").strip(),
                        "content_hash": (row.get("content_hash") or "").strip(),
                    }
                    populated_secret_fields = [
                        name for name, value in secret_fields.items() if value
                    ]
                    if populated_secret_fields:
                        errors.append(
                            f"line {i}: secret/prohibited metadata must not retain "
                            + ", ".join(populated_secret_fields)
                        )

                if record_type == "lead":
                    if not discovery_disposition:
                        errors.append(
                            f"line {i}: lead row requires discovery_disposition"
                        )
                    if not reporting_disposition:
                        errors.append(
                            f"line {i}: lead row requires reporting_disposition"
                        )
                    elif reporting_disposition == "main_findings":
                        errors.append(
                            f"line {i}: lead row cannot use "
                            "reporting_disposition=main_findings"
                        )

                if source_access_class == "raw_leak_lead_only":
                    if record_type not in {"lead", "process", "blocker"}:
                        errors.append(
                            f"line {i}: raw_leak_lead_only requires "
                            "record_type=lead, process, or blocker"
                        )
                    raw_fields = {
                        "source_url": source_url,
                        "evidence": (row.get("evidence") or "").strip(),
                        "quote_or_anchor": (
                            row.get("quote_or_anchor") or ""
                        ).strip(),
                        "archive_url": (row.get("archive_url") or "").strip(),
                        "content_hash": (row.get("content_hash") or "").strip(),
                    }
                    populated = [name for name, value in raw_fields.items() if value]
                    if populated:
                        errors.append(
                            f"line {i}: raw_leak_lead_only must not retain "
                            + ", ".join(populated)
                        )
                    if not (row.get("source_title") or "").strip():
                        errors.append(
                            f"line {i}: raw_leak_lead_only needs a redacted "
                            "source_title"
                        )
                    if reporting_disposition == "main_findings":
                        errors.append(
                            f"line {i}: raw_leak_lead_only cannot report under "
                            "main_findings"
                        )
                    if (
                        record_type == "lead"
                        and reporting_disposition
                        != "non_official_unverified_leads"
                    ):
                        errors.append(
                            f"line {i}: raw leak lead must report only under "
                            "non_official_unverified_leads"
                        )

                if policy_tier in {"R3", "R4"}:
                    if not authorization_scope_hash:
                        errors.append(
                            f"line {i}: {policy_tier} requires "
                            "authorization_scope_hash"
                        )
                    if not retention_until:
                        errors.append(
                            f"line {i}: {policy_tier} requires retention_until"
                        )
                if policy_tier == "R3" and retention_until:
                    retention_dt = _parse_retention_until(retention_until)
                    anchor_dt = _retention_anchor(
                        (row.get("date_accessed") or "").strip()
                    )
                    if anchor_dt is None:
                        errors.append(
                            f"line {i}: R3 requires a valid date_accessed "
                            "to enforce the retention limit"
                        )
                    elif (
                        retention_dt is not None
                        and retention_dt > anchor_dt + timedelta(days=30)
                    ):
                        errors.append(
                            f"line {i}: R3 retention_until exceeds the 30-day maximum"
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

# Stable identifier for the canonical CSV byte layout that `canonicalise`
# produces and that both `sign` and `verify` HMAC over. Downstream consumers
# (e.g. Aleph) pin this so they can detect a canonicalisation change that would
# silently invalidate existing signatures.
CANON_VERSION = "d-research-skill/csv/v1"

# Version of the downstream interop contract shape emitted by `contract --json`.
# Bumped only when the contract *structure* changes, independent of the package
# release version.
INTEROP_CONTRACT_VERSION = "1.0.0"

# Artifact profiles this skill publishes. `full` is the historical source/dev
# tree; additional profiles (e.g. `runtime`) are appended as they are added,
# never by removing an existing one.
ARTIFACT_PROFILES = ["full"]


def _skill_root() -> Path:
    """Repository root, resolved relative to this script (scripts/..)."""
    return Path(__file__).resolve().parent.parent


def build_interop_contract(root: Path | None = None) -> dict:
    """Build the downstream interop contract from live code + repo constants.

    Single source of truth: the ledger schema numbers and identifiers come from
    this module's own constants, and the package version / routes come from the
    committed manifests, so the contract can never silently drift from what the
    validator and signer actually enforce.
    """
    import json

    root = root or _skill_root()
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))

    routes: list[str] = []
    entrypoints: list[str] = ["scripts/evidence_ledger.py"]
    manifest_path = root / "templates" / "route-manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        routes = sorted(
            str(r.get("id")) for r in manifest.get("routes", []) if r.get("id")
        )
        contract = manifest.get("repository_contract", {})
        for entry in contract.get("cli_contracts", []) or []:
            path = entry.get("path") if isinstance(entry, dict) else None
            if path:
                entrypoints.append(str(path))
    entrypoints = sorted(set(entrypoints))

    header_sizes = sorted({len(fields) for fields in ACCEPTED_FIELD_SETS})
    record_types = sorted(t for t in VALID_RECORD_TYPES if t)

    return {
        "contract_version": INTEROP_CONTRACT_VERSION,
        "package_version": package.get("version"),
        "ledger": {
            "header_sizes": header_sizes,
            "record_types": record_types,
            "canonicalization": CANON_VERSION,
            "signature": SIG_VERSION,
        },
        "routes": routes,
        "entrypoints": entrypoints,
        "artifact_profiles": list(ARTIFACT_PROFILES),
    }


def emit_interop_contract(out: Path | None) -> int:
    import json

    text = json.dumps(build_interop_contract(), indent=2, ensure_ascii=False) + "\n"
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"wrote interop contract -> {out}")
    else:
        sys.stdout.write(text)
    return 0


def canonicalise(file: Path) -> bytes:
    """Rewrite the CSV with a stable field order, Unix line endings, and no
    trailing whitespace, then return its UTF-8 bytes.

    This is the input that gets HMAC'd. Both `sign` and `verify` MUST go
    through this function so that benign formatting differences (e.g. a
    text editor switching to CRLF) do not falsely invalidate a signature.

    Supports the exact 14-, 19-, 22-, 23-, and 37-column schemas. Every
    column present in the active schema is included in the canonical bytes,
    so tampering with social, provenance, record-type, or policy fields is
    detected.
    """
    with file.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        active_fields = _match_fieldnames(
            list(reader.fieldnames) if reader.fieldnames else None
        )
        if active_fields is None:
            raise ValueError(
                "header mismatch: expected 14, 19, 22, 23, or 37 column header; "
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
            active = _match_fieldnames(
                list(reader.fieldnames) if reader.fieldnames else None
            )
            if active is None:
                print(
                    "error: prov-export requires a 14, 19, 22, 23, or 37 "
                    "column ledger; "
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
        policy_properties: dict[str, str] = {}
        if active == FIELDS_V3_3:
            policy_properties = {
                "dres:recordType": (row.get("record_type") or "claim").strip()
                or "claim",
                "dres:sourceAccessClass": (
                    row.get("source_access_class") or ""
                ).strip(),
                "dres:subjectClass": (row.get("subject_class") or "").strip(),
                "dres:purposeCategory": (
                    row.get("purpose_category") or ""
                ).strip(),
                "dres:policyTier": (row.get("policy_tier") or "").strip(),
                "dres:speakerIdentity": (
                    row.get("speaker_identity") or ""
                ).strip(),
                "dres:speakerRelationship": (
                    row.get("speaker_relationship") or ""
                ).strip(),
                "dres:contentOrigin": (
                    row.get("content_origin") or ""
                ).strip(),
                "dres:lineageId": (row.get("lineage_id") or "").strip(),
                "dres:dataSensitivity": (
                    row.get("data_sensitivity") or ""
                ).strip(),
                "dres:discoveryDisposition": (
                    row.get("discovery_disposition") or ""
                ).strip(),
                "dres:reportingDisposition": (
                    row.get("reporting_disposition") or ""
                ).strip(),
                "dres:redactionClass": (
                    row.get("redaction_class") or ""
                ).strip(),
                "dres:retentionUntil": (
                    row.get("retention_until") or ""
                ).strip(),
                "dres:authorizationScopeHash": (
                    row.get("authorization_scope_hash") or ""
                ).strip(),
            }

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
        for property_name, value in policy_properties.items():
            if value:
                claim_entity[property_name] = value
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
                    "license_spdx": "",
                    "robots_status": "",
                    "prov_activity_id": "",
                    "record_type": "claim",
                    "source_access_class": "standard_public",
                    "subject_class": "organization",
                    "purpose_category": "general_research",
                    "policy_tier": "R0",
                    "speaker_identity": "",
                    "speaker_relationship": "",
                    "content_origin": "",
                    "lineage_id": "",
                    "data_sensitivity": "public",
                    "discovery_disposition": "permitted",
                    "reporting_disposition": "main_findings",
                    "redaction_class": "none",
                    "retention_until": "",
                    "authorization_scope_hash": "",
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

        # Restore, re-sign, and verify that v3.3 policy fields are covered.
        path.write_text(text, encoding="utf-8")
        sign_ledger(path, "D_RESEARCH_LEDGER_KEY", None)
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace("standard_public", "public_reporting"),
            encoding="utf-8",
        )
        if verify_ledger(path, "D_RESEARCH_LEDGER_KEY", None) == 0:
            print("tamper on policy column not detected", file=sys.stderr)
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

        # Every historical exact header must remain readable, validatable,
        # signable, verifiable, and exportable without migration.
        compatibility_sets = (
            ("legacy14", FIELDS_LEGACY),
            ("social19", FIELDS_V2_1),
            ("provenance22", FIELDS_V3_0),
            ("record_type23", FIELDS_V3_1),
        )
        compatibility_row = {
            "claim_id": "C900",
            "claim": "compatibility claim",
            "sub_question": "schema compatibility",
            "source_title": "Compatibility Source",
            "source_url": "https://example.com/compatibility",
            "source_type": "primary",
            "date_published": "2024-01-01",
            "date_accessed": "2026-07-25",
            "access_method": "fetch",
            "evidence": "observed",
            "quote_or_anchor": "section 1",
            "contradiction": "none",
            "confidence": "high",
            "notes": "",
            "archive_url": "",
            "content_hash": "",
            "snapshot_status": "intact",
            "verifiability": "direct_api",
            "verifiability_note": "Direct public API.",
            "license_spdx": "CC-BY-4.0",
            "robots_status": "not_applicable",
            "prov_activity_id": "prov:compatibility:test",
            "record_type": "claim",
        }
        for schema_name, field_set in compatibility_sets:
            compatibility_path = Path(d) / f"{schema_name}.csv"
            with compatibility_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=field_set)
                writer.writeheader()
                writer.writerow(
                    {name: compatibility_row.get(name, "") for name in field_set}
                )
            if validate_ledger(compatibility_path) != 0:
                print(f"{schema_name} validation failed", file=sys.stderr)
                return 1
            if sign_ledger(
                compatibility_path, "D_RESEARCH_LEDGER_KEY", None
            ) != 0:
                print(f"{schema_name} sign failed", file=sys.stderr)
                return 1
            if verify_ledger(
                compatibility_path, "D_RESEARCH_LEDGER_KEY", None
            ) != 0:
                print(f"{schema_name} verify failed", file=sys.stderr)
                return 1
            compatibility_prov = Path(d) / f"{schema_name}.jsonld"
            if prov_export(compatibility_path, compatibility_prov) != 0:
                print(f"{schema_name} PROV-O export failed", file=sys.stderr)
                return 1
            exported = json.loads(
                compatibility_prov.read_text(encoding="utf-8")
            )
            if not exported.get("@graph"):
                print(f"{schema_name} PROV-O graph is empty", file=sys.stderr)
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

        # --- Social schema 1.1 statuses and process/blocker row discipline ---
        social_status_path = Path(d) / "social_statuses.csv"
        with social_status_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            for index, status in enumerate(sorted(VALID_SNAPSHOT_STATUS - {""}), start=1):
                writer.writerow(
                    {
                        "claim_id": f"S{index:03d}",
                        "claim": f"social status {status}",
                        "source_title": "Public social fixture",
                        "source_url": "https://example.com/post",
                        "source_type": "primary",
                        "access_method": "api",
                        "evidence": "status mapping fixture",
                        "contradiction": "none",
                        "confidence": "low",
                        "snapshot_status": status,
                        "verifiability": "direct_api",
                        "record_type": "claim",
                        "source_access_class": "standard_public",
                        "subject_class": "organization",
                        "purpose_category": "general_research",
                        "policy_tier": "R0",
                        "data_sensitivity": "public",
                        "discovery_disposition": "evidence",
                        "reporting_disposition": "main_findings",
                        "redaction_class": "none",
                    }
                )
        if validate_ledger(social_status_path) != 0:
            print("social schema 1.1 statuses should validate", file=sys.stderr)
            return 1

        weak_process_path = Path(d) / "weak_process.csv"
        with weak_process_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerow(
                {
                    "claim_id": "P001",
                    "claim": "attempted fetch",
                    "source_type": "unknown",
                    "confidence": "low",
                    "record_type": "process",
                }
            )
        if validate_ledger(weak_process_path) == 0:
            print("weak process row should require source, reason, and status", file=sys.stderr)
            return 1

        blocker_path = Path(d) / "blocker.csv"
        with blocker_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerow(
                {
                    "claim_id": "B001",
                    "claim": "public source could not be reached",
                    "source_title": "Attempted canonical source",
                    "source_type": "official",
                    "access_method": "fetch",
                    "evidence": "Access failed after the bounded fallback chain.",
                    "contradiction": "none",
                    "confidence": "low",
                    "notes": "status=blocked; reason=access_control",
                    "record_type": "blocker",
                    "source_access_class": "standard_public",
                    "subject_class": "organization",
                    "purpose_category": "general_research",
                    "policy_tier": "R0",
                    "data_sensitivity": "public",
                    "discovery_disposition": "blocked",
                    "reporting_disposition": "blocked_prohibited_sources",
                    "redaction_class": "none",
                }
            )
        if validate_ledger(blocker_path) != 0:
            print("well-formed blocker row should validate without source_url", file=sys.stderr)
            return 1

        # --- Test v3.0 (22-column) ledger validates/signs/verifies ---
        v3_path = Path(d) / "v3.csv"
        with v3_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS_V3_0)
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
            writer = csv.DictWriter(f, fieldnames=FIELDS_V3_0)
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

        # --- Test v3.3 investigative-policy conditional validation ---
        policy_base = {
            "claim_id": "C330",
            "claim": "v3.3 policy claim",
            "sub_question": "policy validation",
            "source_title": "Public policy source",
            "source_url": "https://example.com/policy",
            "source_type": "primary",
            "date_published": "2026-07-01",
            "date_accessed": "2026-07-25",
            "access_method": "fetch",
            "evidence": "public evidence",
            "quote_or_anchor": "section 3",
            "contradiction": "none",
            "confidence": "high",
            "notes": "",
            "archive_url": "",
            "content_hash": "",
            "snapshot_status": "intact",
            "verifiability": "direct_api",
            "verifiability_note": "Direct public source.",
            "license_spdx": "",
            "robots_status": "not_checked",
            "prov_activity_id": "prov:policy:test",
            "record_type": "claim",
            "source_access_class": "standard_public",
            "subject_class": "organization",
            "purpose_category": "due_diligence",
            "policy_tier": "R1",
            "speaker_identity": "",
            "speaker_relationship": "",
            "content_origin": "",
            "lineage_id": "",
            "data_sensitivity": "public",
            "discovery_disposition": "evidence",
            "reporting_disposition": "main_findings",
            "redaction_class": "none",
            "retention_until": "",
            "authorization_scope_hash": "",
        }

        def write_policy_fixture(name: str, **overrides: str) -> Path:
            fixture = dict(policy_base)
            fixture.update(overrides)
            fixture_path = Path(d) / f"{name}.csv"
            with fixture_path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=FIELDS_V3_3)
                writer.writeheader()
                writer.writerow(fixture)
            return fixture_path

        valid_lead = write_policy_fixture(
            "valid_lead",
            claim_id="L001",
            claim="Community report suggests a checkable lead",
            source_title="Public community post",
            source_url="https://example.com/community/post",
            source_type="community",
            evidence="Public post describes the lead.",
            confidence="low",
            record_type="lead",
            speaker_identity="anonymous",
            speaker_relationship="commentary",
            content_origin="original",
            lineage_id="lineage:community:001",
            discovery_disposition="lead_only",
            reporting_disposition="non_official_unverified_leads",
        )
        if validate_ledger(valid_lead) != 0:
            print("well-formed v3.3 lead should validate", file=sys.stderr)
            return 1

        lead_in_main = write_policy_fixture(
            "lead_in_main",
            claim_id="L002",
            record_type="lead",
            discovery_disposition="lead_only",
            reporting_disposition="main_findings",
        )
        if validate_ledger(lead_in_main) == 0:
            print("lead must not enter main_findings", file=sys.stderr)
            return 1

        prohibited_cases = (
            ("secret_claim", {"data_sensitivity": "secret"}),
            ("minor_claim", {"subject_class": "minor"}),
            ("minor_data_claim", {"data_sensitivity": "minor"}),
            (
                "prohibited_source_claim",
                {"source_access_class": "prohibited_secret"},
            ),
            ("rx_claim", {"policy_tier": "RX"}),
            (
                "prohibited_disposition_claim",
                {"discovery_disposition": "prohibited"},
            ),
        )
        for case_name, overrides in prohibited_cases:
            prohibited_path = write_policy_fixture(case_name, **overrides)
            if validate_ledger(prohibited_path) == 0:
                print(
                    f"{case_name} should not validate as claim evidence",
                    file=sys.stderr,
                )
                return 1

        secret_blocker = write_policy_fixture(
            "secret_blocker",
            claim_id="B330",
            claim="Secret material was excluded before retention",
            source_title="Redacted prohibited-secret source",
            source_url="",
            evidence="",
            quote_or_anchor="",
            archive_url="",
            content_hash="",
            notes="status=prohibited; reason=secret_material",
            record_type="blocker",
            source_access_class="prohibited_secret",
            data_sensitivity="secret",
            discovery_disposition="prohibited",
            reporting_disposition="blocked_prohibited_sources",
            redaction_class="secret",
        )
        if validate_ledger(secret_blocker) != 0:
            print(
                "redacted prohibited-secret blocker should validate",
                file=sys.stderr,
            )
            return 1

        raw_leak = write_policy_fixture(
            "raw_leak",
            claim_id="L003",
            claim="A raw-leak claim exists and requires lawful verification",
            source_title="Redacted raw-leak lead",
            source_url="",
            source_type="community",
            evidence="",
            quote_or_anchor="",
            archive_url="",
            content_hash="",
            record_type="lead",
            source_access_class="raw_leak_lead_only",
            data_sensitivity="personal",
            discovery_disposition="lead_only",
            reporting_disposition="non_official_unverified_leads",
            redaction_class="other_pii",
        )
        if validate_ledger(raw_leak) != 0:
            print("redacted raw-leak lead should validate", file=sys.stderr)
            return 1

        raw_forbidden_fields = {
            "source_url": "https://leak.invalid/raw",
            "evidence": "raw row",
            "quote_or_anchor": "raw quote",
            "archive_url": "https://web.archive.org/raw",
            "content_hash": "deadbeef",
        }
        for field_name, value in raw_forbidden_fields.items():
            raw_overrides = {
                "claim_id": f"L-{field_name}",
                "claim": "raw leak field must be rejected",
                "source_title": "Redacted raw-leak lead",
                "source_url": "",
                "evidence": "",
                "quote_or_anchor": "",
                "archive_url": "",
                "content_hash": "",
                "record_type": "lead",
                "source_access_class": "raw_leak_lead_only",
                "discovery_disposition": "lead_only",
                "reporting_disposition": "non_official_unverified_leads",
            }
            raw_overrides[field_name] = value
            raw_invalid = write_policy_fixture(
                f"raw_leak_with_{field_name}",
                **raw_overrides,
            )
            if validate_ledger(raw_invalid) == 0:
                print(
                    f"raw leak must reject populated {field_name}",
                    file=sys.stderr,
                )
                return 1

        raw_as_claim = write_policy_fixture(
            "raw_leak_as_claim",
            source_title="Redacted raw-leak lead",
            source_url="",
            evidence="",
            quote_or_anchor="",
            source_access_class="raw_leak_lead_only",
            record_type="claim",
            discovery_disposition="lead_only",
            reporting_disposition="non_official_unverified_leads",
        )
        if validate_ledger(raw_as_claim) == 0:
            print("raw leak cannot use record_type=claim", file=sys.stderr)
            return 1

        social_repost = write_policy_fixture(
            "social_repost",
            record_type="lead",
            speaker_identity="claimed_identity",
            speaker_relationship="repost",
            content_origin="repost",
            lineage_id="lineage:social:001",
            discovery_disposition="lead_only",
            reporting_disposition="non_official_unverified_leads",
        )
        if validate_ledger(social_repost) != 0:
            print("complete social lineage should validate", file=sys.stderr)
            return 1
        missing_lineage = write_policy_fixture(
            "missing_lineage",
            record_type="lead",
            speaker_identity="claimed_identity",
            speaker_relationship="repost",
            content_origin="repost",
            lineage_id="",
            discovery_disposition="lead_only",
            reporting_disposition="non_official_unverified_leads",
        )
        if validate_ledger(missing_lineage) == 0:
            print("derivative social row must require lineage_id", file=sys.stderr)
            return 1
        invalid_social_enum = write_policy_fixture(
            "invalid_social_enum",
            speaker_identity="certainly_real",
            speaker_relationship="commentary",
            content_origin="original",
        )
        if validate_ledger(invalid_social_enum) == 0:
            print("invalid social enum should fail", file=sys.stderr)
            return 1

        official_social_main = write_policy_fixture(
            "official_social_main",
            notes="claim_kind=statement_made",
            content_hash="a" * 64,
            speaker_identity="official",
            speaker_relationship="subject",
            content_origin="original",
            lineage_id="lineage:social:official",
        )
        if validate_ledger(official_social_main) != 0:
            print("intact official social statement should validate", file=sys.stderr)
            return 1
        anonymous_social_main = write_policy_fixture(
            "anonymous_social_main",
            notes="claim_kind=statement_made",
            content_hash="a" * 64,
            speaker_identity="anonymous",
            speaker_relationship="secondhand",
            content_origin="repost",
            lineage_id="lineage:social:anonymous",
        )
        if validate_ledger(anonymous_social_main) == 0:
            print("anonymous repost must not enter main findings", file=sys.stderr)
            return 1

        for tier in ("R3", "R4"):
            missing_scope = write_policy_fixture(
                f"{tier.lower()}_missing_scope",
                policy_tier=tier,
                authorization_scope_hash="",
                retention_until="",
            )
            if validate_ledger(missing_scope) == 0:
                print(f"{tier} must require scope hash and retention", file=sys.stderr)
                return 1
            invalid_scope = write_policy_fixture(
                f"{tier.lower()}_invalid_scope",
                policy_tier=tier,
                authorization_scope_hash="sha256:not-a-valid-hash",
                retention_until="2026-07-26 00:00:00",
            )
            if validate_ledger(invalid_scope) == 0:
                print(
                    f"{tier} must reject malformed scope hash or retention",
                    file=sys.stderr,
                )
                return 1
            valid_scope = write_policy_fixture(
                f"{tier.lower()}_valid_scope",
                policy_tier=tier,
                authorization_scope_hash="sha256:" + "a" * 64,
                retention_until="2026-07-26T00:00:00Z",
            )
            if validate_ledger(valid_scope) != 0:
                print(f"well-formed {tier} scope should validate", file=sys.stderr)
                return 1

        r3_missing_anchor = write_policy_fixture(
            "r3_missing_anchor",
            policy_tier="R3",
            date_accessed="",
            authorization_scope_hash="sha256:" + "a" * 64,
            retention_until="2026-07-26T00:00:00Z",
        )
        if validate_ledger(r3_missing_anchor) == 0:
            print("R3 retention must require a valid date_accessed", file=sys.stderr)
            return 1

        policy_prov = Path(d) / "policy.jsonld"
        if prov_export(valid_lead, policy_prov) != 0:
            print("v3.3 PROV-O export failed", file=sys.stderr)
            return 1
        policy_doc = json.loads(policy_prov.read_text(encoding="utf-8"))
        policy_joined = json.dumps(policy_doc)
        for marker in (
            "dres:recordType",
            "dres:sourceAccessClass",
            "dres:reportingDisposition",
            "dres:lineageId",
        ):
            if marker not in policy_joined:
                print(f"v3.3 PROV-O export missing {marker}", file=sys.stderr)
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

    # --- Interop contract invariants (D1) ---
    contract = build_interop_contract()
    if contract["ledger"]["header_sizes"] != [14, 19, 22, 23, 37]:
        print("interop contract header_sizes drift", file=sys.stderr)
        return 1
    for rt in ("claim", "lead", "process", "blocker"):
        if rt not in contract["ledger"]["record_types"]:
            print(f"interop contract missing record_type {rt}", file=sys.stderr)
            return 1
    if contract["ledger"]["signature"] != SIG_VERSION:
        print("interop contract signature drift", file=sys.stderr)
        return 1
    if contract["ledger"]["canonicalization"] != CANON_VERSION:
        print("interop contract canonicalization drift", file=sys.stderr)
        return 1
    if "full" not in contract["artifact_profiles"]:
        print("interop contract missing full artifact profile", file=sys.stderr)
        return 1
    # Determinism: two independent builds must be byte-identical.
    if json.dumps(build_interop_contract(), sort_keys=True) != json.dumps(
        contract, sort_keys=True
    ):
        print("interop contract not deterministic", file=sys.stderr)
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
    p_contract = sub.add_parser(
        "contract",
        help="Emit the downstream interop contract (ledger schema, routes, "
        "entrypoints, artifact profiles) as JSON.",
    )
    p_contract.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON (default and only format; accepted for explicitness).",
    )
    p_contract.add_argument(
        "--out",
        default=None,
        help="Output path (default: stdout).",
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
    if args.cmd == "contract":
        out = Path(args.out) if args.out else None
        return emit_interop_contract(out)
    if args.cmd == "self-test":
        return self_test()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
