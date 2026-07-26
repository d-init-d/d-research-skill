#!/usr/bin/env python3
"""Policy-as-code helper for scoped investigative research.

Commands:
  init --mode R1 --out investigation-scope.json
  check --file investigation-scope.json
  assess-source [classification flags]
  self-test

The helper validates research scope and source-reporting disposition. It does
not fetch data, prove legal authority, or grant access to any target.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "templates" / "investigation-scope.json"

TOP_LEVEL_KEYS = {
    "schema_version",
    "mode",
    "purpose",
    "subject",
    "authorization",
    "scope",
    "access",
    "output",
}
SUBJECT_KEYS = {"class", "name_or_id"}
AUTHORIZATION_KEYS = {
    "status",
    "method",
    "scope_hash",
    "reviewed_by",
    "reviewed_at",
    "expires_at",
}
SCOPE_KEYS = {
    "allowed_entities",
    "allowed_domains",
    "source_access_classes",
    "data_classes",
    "max_sources",
    "max_depth",
    "stop_after_no_new_claims",
}
ACCESS_KEYS = {
    "read_only",
    "allow_login_with_user_permission",
    "allow_paywalled_sources",
    "allow_captcha_solving",
    "allow_stealth_evasion",
    "respect_robots",
}
OUTPUT_KEYS = {"sections", "redaction_classes", "retention_days", "audience"}

VALID_MODES = {"R0", "R1", "R2", "R3", "R4", "RX"}
INIT_MODES = {"R0", "R1", "R2", "R3", "R4"}
VALID_PURPOSES = {
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
}
VALID_AUTHORIZATION_STATUS = {
    "not_required",
    "pending",
    "reviewed_public_interest",
    "self_verified",
    "authorized",
}
VALID_SOURCE_ACCESS_CLASSES = {
    "standard_public",
    "public_reporting",
    "authorized_provider",
    "user_provided_private",
    "raw_leak_lead_only",
    "prohibited_secret",
}
VALID_DATA_CLASSES = {"public", "professional", "personal", "sensitive", "secret", "minor"}
VALID_SECTIONS = {
    "main_findings",
    "non_official_unverified_leads",
    "blocked_prohibited_sources",
    "contradictions_unknowns",
    "confidence_stopping_criteria",
    "next_verification_steps",
}
VALID_AUDIENCES = {"named_recipient", "authorized_team", "confidential_case"}
REQUIRED_SECTIONS = {
    "main_findings",
    "non_official_unverified_leads",
    "blocked_prohibited_sources",
    "contradictions_unknowns",
}
VALID_REDACTION_CLASSES = {
    "personal_contact",
    "residential",
    "government_id",
    "financial",
    "medical",
    "family_minor",
    "whereabouts",
    "secret",
    "other_pii",
}
REQUIRED_REDACTION_CLASSES = VALID_REDACTION_CLASSES
SCOPE_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
UNBOUNDED_SCOPE_TOKENS = {
    "*",
    "all",
    "any",
    "everything",
    "everyone",
    "internet",
    "world",
    "0.0.0.0/0",
    "::/0",
}
PLACEHOLDER_SCOPE_TOKENS = {
    "target",
    "tokenized-target",
    "replace-me",
    "todo",
    "unknown",
}
MAX_AUTHORIZATION_DAYS = {
    "reviewed_public_interest": 365,
    "self_verified": 30,
    "authorized": 365,
}

VALID_SPEAKER_IDENTITIES = {
    "official",
    "verified_public_role",
    "claimed_identity",
    "pseudonymous",
    "anonymous",
    "unknown",
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
}
VALID_ORIGINS = {"original", "firsthand", "quote", "repost", "screenshot", "unknown"}
VALID_INTEGRITY = {
    "live_intact",
    "edited",
    "deleted_archived",
    "archive_snapshot",
    "screenshot_only",
    "unverified",
    "unknown",
}
VALID_IMPACTS = {"low", "material", "high"}
VALID_CLAIM_KINDS = {"statement_made", "underlying_fact", "opinion", "reception"}
VALID_AUTHORIZATION_METHODS = {
    "reviewed_public_interest": {
        "editorial_review",
        "legal_review",
        "public_interest_review",
    },
    "self_verified": {
        "email_challenge",
        "dns_challenge",
        "platform_oauth",
        "provider_native_verification",
        "signed_challenge",
    },
    "authorized": {
        "signed_rules_of_engagement",
        "written_authorization",
        "provider_contract",
        "incident_case_authorization",
        "organization_admin_proof",
    },
}


class DuplicateKeyError(ValueError):
    """Raised when strict JSON parsing encounters a duplicate key."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except (OSError, json.JSONDecodeError, DuplicateKeyError) as exc:
        raise ValueError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _parse_utc(value: str, label: str, errors: list[str]) -> datetime | None:
    if not value:
        errors.append(f"{label} must be a non-empty ISO 8601 UTC timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{label} must be an ISO 8601 UTC timestamp")
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        errors.append(f"{label} must use UTC")
        return None
    return parsed


def authorization_scope_digest(data: dict[str, Any]) -> str:
    """Bind authorization to the exact declared mode, purpose, scope, and output.

    The digest deliberately excludes ``authorization.scope_hash`` to avoid a
    circular value. It is a tamper-evidence binding, not proof that a person or
    organization actually granted authorization.
    """
    authorization = data.get("authorization")
    auth_view = dict(authorization) if isinstance(authorization, dict) else {}
    auth_view.pop("scope_hash", None)
    view = {
        "schema_version": data.get("schema_version"),
        "mode": data.get("mode"),
        "purpose": data.get("purpose"),
        "subject": data.get("subject"),
        "authorization": auth_view,
        "scope": data.get("scope"),
        "access": data.get("access"),
        "output": data.get("output"),
    }
    body = json.dumps(
        view,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _check_exact_keys(
    value: object,
    expected: set[str],
    label: str,
    errors: list[str],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return {}
    keys = set(value)
    missing = sorted(expected - keys)
    extra = sorted(keys - expected)
    if missing:
        errors.append(f"{label} missing key(s): {', '.join(missing)}")
    if extra:
        errors.append(f"{label} has unknown key(s): {', '.join(extra)}")
    return value


def _string_list(
    value: object,
    label: str,
    errors: list[str],
    *,
    allowed: set[str] | None = None,
) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        errors.append(f"{label} must be a list of non-empty strings")
        return []
    items = list(value)
    if len(set(items)) != len(items):
        errors.append(f"{label} must not contain duplicates")
    if allowed is not None:
        invalid = sorted(set(items) - allowed)
        if invalid:
            errors.append(f"{label} contains invalid value(s): {', '.join(invalid)}")
    return items


def _positive_int(
    value: object,
    label: str,
    errors: list[str],
    *,
    maximum: int,
) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > maximum:
        errors.append(f"{label} must be an integer from 1 to {maximum}")
        return None
    return value


def _validate_bounded_targets(
    values: list[str], label: str, errors: list[str]
) -> None:
    """Reject selectors that do not identify a finite, reviewable target."""
    for value in values:
        normalized = value.strip().lower()
        final_token = re.split(r"[:/_-]+", normalized)[-1]
        if value != value.strip() or any(ch.isspace() for ch in value):
            errors.append(f"{label} entries must be whitespace-free scoped tokens")
        if len(value) > 512:
            errors.append(f"{label} entries must be 512 characters or fewer")
        if (
            normalized in UNBOUNDED_SCOPE_TOKENS
            or final_token in PLACEHOLDER_SCOPE_TOKENS
        ):
            errors.append(
                f"{label} contains an unbounded or placeholder target: {value!r}"
            )


def validate_scope(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    root = _check_exact_keys(data, TOP_LEVEL_KEYS, "scope", errors)

    if root.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")

    mode = root.get("mode")
    if mode not in VALID_MODES:
        errors.append(f"mode must be one of {sorted(VALID_MODES)}")

    purpose = root.get("purpose")
    if purpose not in VALID_PURPOSES:
        errors.append(f"purpose must be one of {sorted(VALID_PURPOSES)}")

    subject = _check_exact_keys(root.get("subject"), SUBJECT_KEYS, "subject", errors)
    subject_class = subject.get("class")
    if subject_class not in VALID_SUBJECT_CLASSES:
        errors.append(f"subject.class must be one of {sorted(VALID_SUBJECT_CLASSES)}")
    subject_name_or_id = subject.get("name_or_id")
    if not isinstance(subject_name_or_id, str) or not subject_name_or_id.strip():
        errors.append("subject.name_or_id must be a non-empty string")
    elif subject_name_or_id.strip().lower() in {"replace-me", "todo", "unknown"}:
        errors.append("subject.name_or_id must identify the scoped subject, not a placeholder")

    authorization = _check_exact_keys(
        root.get("authorization"), AUTHORIZATION_KEYS, "authorization", errors
    )
    authorization_status = authorization.get("status")
    if authorization_status not in VALID_AUTHORIZATION_STATUS:
        errors.append(
            "authorization.status must be one of "
            f"{sorted(VALID_AUTHORIZATION_STATUS)}"
        )
    for key in ("method", "scope_hash", "reviewed_by", "reviewed_at", "expires_at"):
        if not isinstance(authorization.get(key), str):
            errors.append(f"authorization.{key} must be a string")

    scope = _check_exact_keys(root.get("scope"), SCOPE_KEYS, "scope.scope", errors)
    entities = _string_list(scope.get("allowed_entities"), "scope.allowed_entities", errors)
    domains = _string_list(scope.get("allowed_domains"), "scope.allowed_domains", errors)
    _validate_bounded_targets(entities, "scope.allowed_entities", errors)
    _validate_bounded_targets(domains, "scope.allowed_domains", errors)
    source_classes = _string_list(
        scope.get("source_access_classes"),
        "scope.source_access_classes",
        errors,
        allowed=VALID_SOURCE_ACCESS_CLASSES,
    )
    data_classes = _string_list(
        scope.get("data_classes"),
        "scope.data_classes",
        errors,
        allowed=VALID_DATA_CLASSES,
    )
    _positive_int(scope.get("max_sources"), "scope.max_sources", errors, maximum=5000)
    _positive_int(scope.get("max_depth"), "scope.max_depth", errors, maximum=5)
    _positive_int(
        scope.get("stop_after_no_new_claims"),
        "scope.stop_after_no_new_claims",
        errors,
        maximum=20,
    )

    access = _check_exact_keys(root.get("access"), ACCESS_KEYS, "access", errors)
    for key in ACCESS_KEYS:
        if not isinstance(access.get(key), bool):
            errors.append(f"access.{key} must be boolean")
    if access.get("read_only") is not True:
        errors.append("access.read_only must be true")
    if access.get("allow_paywalled_sources") is not False:
        errors.append("access.allow_paywalled_sources must be false")
    if access.get("allow_captcha_solving") is not False:
        errors.append("access.allow_captcha_solving must be false")
    if access.get("allow_stealth_evasion") is not False:
        errors.append("access.allow_stealth_evasion must be false")
    if access.get("respect_robots") is not True:
        errors.append("access.respect_robots must be true")
    if access.get("allow_login_with_user_permission") is True and mode not in {"R3", "R4"}:
        errors.append("authenticated sessions are permitted only in verified R3 or R4 scopes")

    output = _check_exact_keys(root.get("output"), OUTPUT_KEYS, "output", errors)
    sections = _string_list(
        output.get("sections"), "output.sections", errors, allowed=VALID_SECTIONS
    )
    redactions = _string_list(
        output.get("redaction_classes"),
        "output.redaction_classes",
        errors,
        allowed=VALID_REDACTION_CLASSES,
    )
    missing_sections = sorted(REQUIRED_SECTIONS - set(sections))
    if missing_sections:
        errors.append(f"output.sections missing required section(s): {', '.join(missing_sections)}")
    missing_redactions = sorted(REQUIRED_REDACTION_CLASSES - set(redactions))
    if missing_redactions:
        errors.append(
            "output.redaction_classes missing mandatory class(es): "
            + ", ".join(missing_redactions)
        )
    retention_days = _positive_int(
        output.get("retention_days"), "output.retention_days", errors, maximum=3650
    )
    audience = output.get("audience")
    if audience not in VALID_AUDIENCES:
        errors.append(f"output.audience must be one of {sorted(VALID_AUDIENCES)}")

    if subject_class == "minor" or "minor" in data_classes:
        errors.append("minor subjects or minor data are prohibited")
    if "prohibited_secret" in source_classes or "secret" in data_classes:
        errors.append("prohibited-secret sources and secret data are never allowed")

    if mode == "RX":
        errors.append("RX is a prohibited classification and cannot be executed")

    if mode == "R0":
        allowed = {"standard_public", "public_reporting"}
        if set(source_classes) - allowed:
            errors.append("R0 permits only standard_public and public_reporting sources")

    if mode in {"R0", "R1"}:
        if subject_class in {"public_role_person", "private_person", "self", "minor"}:
            errors.append(f"{mode} person research must use the scoped R2 or R3 route")
        if set(data_classes) - {"public", "professional"}:
            errors.append(f"{mode} permits only public and professional data classes")

    if mode == "R2":
        if subject_class not in {"public_role_person", "private_person", "self"}:
            errors.append("R2 subject.class must be public_role_person, private_person, or self")
        if set(data_classes) - {"public", "professional"}:
            errors.append("R2 permits only public and professional data classes")
        if subject_class == "private_person":
            public_interest_purposes = {
                "public_interest",
                "journalism",
                "due_diligence",
                "fraud_prevention",
            }
            if authorization_status == "reviewed_public_interest":
                if purpose not in public_interest_purposes:
                    errors.append(
                        "R2 reviewed_public_interest requires a public-interest, journalism, "
                        "due-diligence, or fraud-prevention purpose"
                    )
            elif authorization_status != "authorized":
                errors.append(
                    "R2 private_person requires authorization or reviewed_public_interest"
                )

    scope_hash = authorization.get("scope_hash", "")
    method = authorization.get("method", "")
    if scope_hash and not SCOPE_HASH_RE.fullmatch(scope_hash):
        errors.append("authorization.scope_hash must be sha256:<64 lowercase hex>")

    reviewed_statuses = {"reviewed_public_interest", "self_verified", "authorized"}
    if authorization_status in reviewed_statuses:
        reviewed_by = authorization.get("reviewed_by", "")
        reviewed_at = authorization.get("reviewed_at", "")
        expires_at = authorization.get("expires_at", "")
        if not isinstance(method, str) or not method.strip():
            errors.append("reviewed authorization requires authorization.method")
        elif method not in VALID_AUTHORIZATION_METHODS[authorization_status]:
            errors.append(
                f"authorization.method must be one of "
                f"{sorted(VALID_AUTHORIZATION_METHODS[authorization_status])} for "
                f"status={authorization_status}"
            )
        if not isinstance(reviewed_by, str) or not reviewed_by.strip():
            errors.append("reviewed authorization requires authorization.reviewed_by")
        reviewed_dt = _parse_utc(str(reviewed_at), "authorization.reviewed_at", errors)
        expires_dt = _parse_utc(str(expires_at), "authorization.expires_at", errors)
        now = datetime.now(timezone.utc)
        if reviewed_dt is not None and expires_dt is not None and expires_dt <= reviewed_dt:
            errors.append("authorization.expires_at must be later than reviewed_at")
        if reviewed_dt is not None and reviewed_dt > now + timedelta(minutes=5):
            errors.append("authorization.reviewed_at must not be in the future")
        if expires_dt is not None and expires_dt <= now:
            errors.append("authorization attestation has expired")
        if reviewed_dt is not None and expires_dt is not None:
            maximum_days = MAX_AUTHORIZATION_DAYS[authorization_status]
            if expires_dt > reviewed_dt + timedelta(days=maximum_days):
                errors.append(
                    f"authorization validity exceeds the {maximum_days}-day maximum "
                    f"for status={authorization_status}"
                )
        if not isinstance(scope_hash, str) or not SCOPE_HASH_RE.fullmatch(scope_hash):
            errors.append("reviewed authorization requires a valid authorization.scope_hash")
        elif scope_hash != authorization_scope_digest(root):
            errors.append(
                "authorization.scope_hash does not bind the current scope; run bind-authorization again"
            )
    elif any(
        authorization.get(key)
        for key in ("method", "scope_hash", "reviewed_by", "reviewed_at", "expires_at")
    ):
        errors.append(
            "pending/not_required authorization must not carry stale review or scope-hash fields"
        )

    if mode == "R3":
        if purpose not in {"self_audit", "incident_response"}:
            errors.append("R3 purpose must be self_audit or incident_response")
        if subject_class not in {"self", "organization"}:
            errors.append("R3 subject.class must be self or organization")
        if not entities and not domains:
            errors.append("R3 requires at least one tokenized allowed entity or owned domain")
        if authorization_status not in {"self_verified", "authorized"}:
            errors.append("R3 requires self_verified or authorized status")
        allowed = {
            "standard_public",
            "public_reporting",
            "authorized_provider",
            "user_provided_private",
        }
        if set(source_classes) - allowed:
            errors.append("R3 does not permit raw-leak or prohibited-secret source classes")
        if set(data_classes) - {"public", "professional", "personal"}:
            errors.append("R3 permits only public, professional, and personal data classes")
        if retention_days is not None and retention_days > 30:
            errors.append("R3 output.retention_days must be 30 or less")

    if mode == "R4":
        if purpose not in {
            "defensive_security",
            "threat_intel",
            "incident_response",
            "authorized_pentest",
        }:
            errors.append("R4 requires a defensive/security purpose")
        if authorization_status != "authorized":
            errors.append("R4 requires authorization.status=authorized")
        if subject_class not in {"organization", "infrastructure"}:
            errors.append("R4 subject.class must be organization or infrastructure")
        if not entities and not domains:
            errors.append("R4 requires at least one allowed entity or domain")
        if retention_days is not None and retention_days > 365:
            errors.append("R4 output.retention_days must be 365 or less")

    if "raw_leak_lead_only" in source_classes and mode in {"R0", "R3"}:
        errors.append(f"{mode} does not permit raw_leak_lead_only sources")

    return errors


def scope_for_mode(mode: str) -> dict[str, Any]:
    data = copy.deepcopy(load_json(TEMPLATE))
    data["mode"] = mode
    if mode == "R0":
        data["scope"]["max_sources"] = 100
        data["scope"]["max_depth"] = 2
    elif mode == "R2":
        data["purpose"] = "due_diligence"
        data["subject"]["class"] = "public_role_person"
        data["subject"]["name_or_id"] = "public-role:target"
    elif mode == "R3":
        data["purpose"] = "self_audit"
        data["subject"]["class"] = "self"
        data["subject"]["name_or_id"] = "self:tokenized-target"
        data["authorization"]["status"] = "pending"
        data["scope"]["allowed_entities"] = ["self:tokenized-target"]
        data["scope"]["source_access_classes"] = [
            "public_reporting",
            "authorized_provider",
            "user_provided_private",
        ]
        data["scope"]["data_classes"] = ["public", "professional", "personal"]
        data["scope"]["max_sources"] = 100
        data["scope"]["max_depth"] = 2
        data["output"]["retention_days"] = 3
    elif mode == "R4":
        data["purpose"] = "authorized_pentest"
        data["subject"]["class"] = "infrastructure"
        data["subject"]["name_or_id"] = "infrastructure:target"
        data["authorization"]["status"] = "pending"
        data["scope"]["source_access_classes"] = [
            "standard_public",
            "public_reporting",
            "authorized_provider",
            "user_provided_private",
        ]
        data["scope"]["max_sources"] = 500
    return data


def init_scope(out: Path, mode: str) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(scope_for_mode(mode), indent=2) + "\n", encoding="utf-8")
    print(f"wrote draft {mode} investigation scope to {out}")
    if mode in {"R3", "R4"}:
        print("note: authorization fields are pending; check fails until verified")
    return 0


def check_scope(path: Path) -> int:
    try:
        data = load_json(path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    errors = validate_scope(data)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"investigation scope valid: {path}")
    return 0


def bind_authorization(
    path: Path,
    status: str,
    method: str,
    reviewed_by: str,
    reviewed_at: str,
    expires_at: str,
) -> int:
    """Record an attestation and bind it to the exact current scope.

    This command records a review claim; it does not independently verify the
    reviewer's identity or legal authority.
    """
    try:
        data = load_json(path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    authorization = data.get("authorization")
    if not isinstance(authorization, dict):
        print("error: authorization must be an object", file=sys.stderr)
        return 1
    authorization.update(
        {
            "status": status,
            "method": method,
            "reviewed_by": reviewed_by,
            "reviewed_at": reviewed_at,
            "expires_at": expires_at,
            "scope_hash": "",
        }
    )
    authorization["scope_hash"] = authorization_scope_digest(data)
    errors = validate_scope(data)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"bound {status} authorization to {path}: {authorization['scope_hash']}")
    return 0


def assess_source(args: argparse.Namespace) -> dict[str, Any]:
    reasons: list[str] = []
    discovery = "permitted"
    reporting = "non_official_unverified_leads"
    human_review = False
    corroboration_ids = list(dict.fromkeys(args.corroboration_id))

    if args.source_access_class == "prohibited_secret" or args.data_sensitivity in {
        "secret",
        "minor",
    }:
        return {
            "schema_version": "1.0",
            "discovery_disposition": "prohibited",
            "reporting_disposition": "prohibited",
            "requires_human_review": False,
            "reasons": ["prohibited secret or minor data class"],
        }

    if args.source_access_class == "raw_leak_lead_only":
        return {
            "schema_version": "1.0",
            "discovery_disposition": "lead_only",
            "reporting_disposition": "non_official_unverified_leads",
            "requires_human_review": args.claim_impact != "low",
            "reasons": ["raw leak claims may create metadata leads but are not admissible evidence"],
        }

    if args.source_access_class in {"authorized_provider", "user_provided_private"}:
        reasons.append("authorized/private source requires scope and audience verification")
        human_review = True

    authoritative_speaker = args.speaker_identity in {"official", "verified_public_role"}
    direct_relationship = args.speaker_relationship in {
        "subject",
        "authorized_representative",
        "firsthand",
    }
    original = args.origin in {"original", "firsthand"}
    stable = args.integrity in {"live_intact", "archive_snapshot", "deleted_archived"}

    if args.origin in {"repost", "screenshot"} or args.speaker_relationship == "repost":
        reasons.append("repost or screenshot is not an independent source")
    elif (
        args.claim_kind == "statement_made"
        and authoritative_speaker
        and direct_relationship
        and original
        and stable
    ):
        reporting = "main_findings"
        reasons.append("stable authoritative source verifies that the statement was made")
    elif (
        args.primary_corroborated
        and corroboration_ids
        and args.human_reviewed
        and stable
    ):
        reporting = "main_findings"
        reasons.append("human-reviewed primary corroboration has a distinct lineage identifier")
    elif (
        args.claim_impact == "low"
        and args.data_sensitivity in {"public", "professional"}
        and len(corroboration_ids) >= 2
        and args.speaker_identity not in {"anonymous", "unknown"}
        and stable
    ):
        reporting = "main_findings"
        reasons.append("low-impact claim has multiple declared independent lineages")
    else:
        reasons.append("item remains a lead pending stronger identity or corroboration")

    if args.primary_corroborated and not corroboration_ids:
        human_review = True
        reasons.append("primary corroboration needs at least one lineage identifier")

    if args.data_sensitivity in {"personal", "sensitive"}:
        human_review = True
        if reporting == "main_findings" and not (
            args.primary_corroborated and corroboration_ids and args.human_reviewed
        ):
            reporting = "non_official_unverified_leads"
            reasons.append("personal or sensitive claims require primary corroboration")

    if args.claim_impact in {"material", "high"} and reporting == "main_findings":
        if args.claim_kind != "statement_made" and not (
            args.primary_corroborated and corroboration_ids and args.human_reviewed
        ):
            reporting = "non_official_unverified_leads"
            human_review = True
            reasons.append("material/high-impact underlying claim lacks reviewed primary support")

    if args.speaker_identity in {"anonymous", "unknown"}:
        reporting = "non_official_unverified_leads"
        reasons.append("anonymous or unknown identity cannot independently support main findings")

    if args.claim_kind == "underlying_fact" and reporting == "main_findings":
        if not args.human_reviewed and args.claim_impact != "low":
            reporting = "non_official_unverified_leads"
            human_review = True
            reasons.append("material underlying facts require explicit human review")

    if reporting == "main_findings" and args.source_access_class in {
        "authorized_provider",
        "user_provided_private",
    }:
        human_review = True

    return {
        "schema_version": "1.0",
        "discovery_disposition": discovery,
        "reporting_disposition": reporting,
        "requires_human_review": human_review,
        "corroboration_ids": corroboration_ids,
        "reasons": reasons,
    }


def self_test() -> int:
    failures: list[str] = []
    now = datetime.now(timezone.utc).replace(microsecond=0)
    reviewed_at = (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    short_expiry = (now + timedelta(days=7)).isoformat().replace("+00:00", "Z")

    base = scope_for_mode("R1")
    if validate_scope(base):
        failures.append("default R1 scope should validate")

    unsafe = copy.deepcopy(base)
    unsafe["access"]["allow_captcha_solving"] = True
    if not any("allow_captcha_solving" in error for error in validate_scope(unsafe)):
        failures.append("captcha solving must fail closed")

    minor = copy.deepcopy(base)
    minor["subject"]["class"] = "minor"
    if not any("minor" in error for error in validate_scope(minor)):
        failures.append("minor subject must fail closed")

    r0_private = scope_for_mode("R0")
    r0_private["subject"]["class"] = "private_person"
    r0_private["scope"]["data_classes"] = ["public", "sensitive"]
    if not validate_scope(r0_private):
        failures.append("R0 private-person sensitive scope must fail closed")

    r1_private = scope_for_mode("R1")
    r1_private["subject"]["class"] = "private_person"
    if not validate_scope(r1_private):
        failures.append("R1 person scope must route through R2")

    r2_sensitive = scope_for_mode("R2")
    r2_sensitive["scope"]["data_classes"] = ["public", "sensitive"]
    if not validate_scope(r2_sensitive):
        failures.append("R2 sensitive retention must fail closed")

    r3 = scope_for_mode("R3")
    if not validate_scope(r3):
        failures.append("draft R3 scope must fail until authorization is verified")
    r3_target = "self:sha256:" + "a" * 32
    r3["subject"]["name_or_id"] = r3_target
    r3["scope"]["allowed_entities"] = [r3_target]
    r3["authorization"].update(
        {
            "status": "self_verified",
            "method": "email_challenge",
            "reviewed_by": "self-service-provider",
            "reviewed_at": reviewed_at,
            "expires_at": short_expiry,
            "scope_hash": "",
        }
    )
    r3["authorization"]["scope_hash"] = authorization_scope_digest(r3)
    if validate_scope(r3):
        failures.append("verified R3 scope should validate")
    r3_public = copy.deepcopy(r3)
    r3_public["output"]["audience"] = "public"
    r3_public["authorization"]["scope_hash"] = authorization_scope_digest(r3_public)
    if not validate_scope(r3_public):
        failures.append("R3 public audience must fail closed")
    r3_no_target = copy.deepcopy(r3)
    r3_no_target["scope"]["allowed_entities"] = []
    r3_no_target["scope"]["allowed_domains"] = []
    r3_no_target["authorization"]["scope_hash"] = authorization_scope_digest(r3_no_target)
    if not validate_scope(r3_no_target):
        failures.append("R3 without a tokenized target must fail closed")
    r3_tampered = copy.deepcopy(r3)
    r3_tampered["scope"]["max_sources"] += 1
    if not any("does not bind" in error for error in validate_scope(r3_tampered)):
        failures.append("scope mutation must invalidate the authorization digest")

    r4 = scope_for_mode("R4")
    r4["authorization"].update(
        {
            "status": "authorized",
            "method": "signed_rules_of_engagement",
            "reviewed_by": "engagement-owner",
            "reviewed_at": reviewed_at,
            "expires_at": short_expiry,
            "scope_hash": "",
        }
    )
    r4["authorization"]["scope_hash"] = authorization_scope_digest(r4)
    if not validate_scope(r4):
        failures.append("R4 without a target must fail")
    r4["scope"]["allowed_domains"] = ["example.test"]
    r4["authorization"]["scope_hash"] = authorization_scope_digest(r4)
    if validate_scope(r4):
        failures.append("authorized scoped R4 should validate")
    r4_wildcard = copy.deepcopy(r4)
    r4_wildcard["scope"]["allowed_domains"] = ["*"]
    r4_wildcard["authorization"]["scope_hash"] = authorization_scope_digest(
        r4_wildcard
    )
    if not any("unbounded" in error for error in validate_scope(r4_wildcard)):
        failures.append("R4 wildcard target must fail closed")
    r4_private = copy.deepcopy(r4)
    r4_private["subject"]["class"] = "private_person"
    r4_private["authorization"]["scope_hash"] = authorization_scope_digest(
        r4_private
    )
    if not any("organization or infrastructure" in error for error in validate_scope(r4_private)):
        failures.append("R4 private-person target must fail closed")
    r4_future = copy.deepcopy(r4)
    r4_future["authorization"]["reviewed_at"] = (
        now + timedelta(days=1)
    ).isoformat().replace("+00:00", "Z")
    r4_future["authorization"]["expires_at"] = (
        now + timedelta(days=2)
    ).isoformat().replace("+00:00", "Z")
    r4_future["authorization"]["scope_hash"] = authorization_scope_digest(
        r4_future
    )
    if not any("must not be in the future" in error for error in validate_scope(r4_future)):
        failures.append("future authorization review must fail closed")
    r4_long = copy.deepcopy(r4)
    r4_long["authorization"]["expires_at"] = (
        now + timedelta(days=366)
    ).isoformat().replace("+00:00", "Z")
    r4_long["authorization"]["scope_hash"] = authorization_scope_digest(r4_long)
    if not any("365-day maximum" in error for error in validate_scope(r4_long)):
        failures.append("overlong authorization validity must fail closed")

    parser = build_parser()
    raw_args = parser.parse_args(
        [
            "assess-source",
            "--source-access-class",
            "raw_leak_lead_only",
            "--speaker-identity",
            "anonymous",
            "--speaker-relationship",
            "unknown",
            "--origin",
            "unknown",
            "--integrity",
            "unverified",
            "--data-sensitivity",
            "personal",
            "--claim-impact",
            "high",
            "--claim-kind",
            "underlying_fact",
        ]
    )
    raw = assess_source(raw_args)
    if raw["reporting_disposition"] != "non_official_unverified_leads":
        failures.append("raw leak claim must remain a lead")

    official_args = parser.parse_args(
        [
            "assess-source",
            "--source-access-class",
            "standard_public",
            "--speaker-identity",
            "official",
            "--speaker-relationship",
            "subject",
            "--origin",
            "original",
            "--integrity",
            "live_intact",
            "--data-sensitivity",
            "public",
            "--claim-impact",
            "material",
            "--claim-kind",
            "statement_made",
        ]
    )
    official = assess_source(official_args)
    if official["reporting_disposition"] != "main_findings":
        failures.append("official firsthand statement should reach main findings")

    secret_args = parser.parse_args(
        [
            "assess-source",
            "--source-access-class",
            "prohibited_secret",
            "--speaker-identity",
            "unknown",
            "--speaker-relationship",
            "unknown",
            "--origin",
            "unknown",
            "--integrity",
            "unknown",
            "--data-sensitivity",
            "secret",
            "--claim-impact",
            "high",
            "--claim-kind",
            "underlying_fact",
        ]
    )
    if assess_source(secret_args)["reporting_disposition"] != "prohibited":
        failures.append("secret material must be prohibited")

    unreviewed_args = parser.parse_args(
        [
            "assess-source",
            "--source-access-class",
            "standard_public",
            "--speaker-identity",
            "claimed_identity",
            "--speaker-relationship",
            "secondhand",
            "--origin",
            "original",
            "--integrity",
            "live_intact",
            "--data-sensitivity",
            "public",
            "--claim-impact",
            "high",
            "--claim-kind",
            "underlying_fact",
            "--primary-corroborated",
            "--corroboration-id",
            "lineage:one",
        ]
    )
    unreviewed = assess_source(unreviewed_args)
    if unreviewed["reporting_disposition"] == "main_findings":
        failures.append("self-declared corroboration must not auto-promote a high-impact fact")

    with tempfile.TemporaryDirectory() as tmp:
        duplicate = Path(tmp) / "duplicate.json"
        duplicate.write_text('{"schema_version":"1.0","schema_version":"1.0"}', encoding="utf-8")
        try:
            load_json(duplicate)
        except ValueError:
            pass
        else:
            failures.append("duplicate JSON keys must fail")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("investigation_policy self-test ok")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate investigative research policy")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create a draft investigation scope")
    init.add_argument("--mode", choices=sorted(INIT_MODES), default="R1")
    init.add_argument("--out", default="investigation-scope.json")

    check = sub.add_parser("check", help="Validate an investigation scope")
    check.add_argument("--file", default="investigation-scope.json")

    bind = sub.add_parser(
        "bind-authorization",
        help="Record a review attestation and bind it to the exact current scope",
    )
    bind.add_argument("--file", default="investigation-scope.json")
    bind.add_argument(
        "--status",
        choices=["reviewed_public_interest", "self_verified", "authorized"],
        required=True,
    )
    bind.add_argument("--method", required=True)
    bind.add_argument("--reviewed-by", required=True)
    bind.add_argument("--reviewed-at", required=True)
    bind.add_argument("--expires-at", required=True)

    assess = sub.add_parser("assess-source", help="Classify one social or non-official source")
    assess.add_argument(
        "--source-access-class", choices=sorted(VALID_SOURCE_ACCESS_CLASSES), required=True
    )
    assess.add_argument("--speaker-identity", choices=sorted(VALID_SPEAKER_IDENTITIES), required=True)
    assess.add_argument(
        "--speaker-relationship", choices=sorted(VALID_SPEAKER_RELATIONSHIPS), required=True
    )
    assess.add_argument("--origin", choices=sorted(VALID_ORIGINS), required=True)
    assess.add_argument("--integrity", choices=sorted(VALID_INTEGRITY), required=True)
    assess.add_argument("--data-sensitivity", choices=sorted(VALID_DATA_CLASSES), required=True)
    assess.add_argument("--claim-impact", choices=sorted(VALID_IMPACTS), required=True)
    assess.add_argument("--claim-kind", choices=sorted(VALID_CLAIM_KINDS), required=True)
    assess.add_argument("--corroboration-id", action="append", default=[])
    assess.add_argument("--primary-corroborated", action="store_true")
    assess.add_argument("--human-reviewed", action="store_true")

    sub.add_parser("self-test", help="Run offline adversarial self-tests")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "init":
        return init_scope(Path(args.out), args.mode)
    if args.command == "check":
        return check_scope(Path(args.file))
    if args.command == "bind-authorization":
        return bind_authorization(
            Path(args.file),
            args.status,
            args.method,
            args.reviewed_by,
            args.reviewed_at,
            args.expires_at,
        )
    if args.command == "assess-source":
        if any(not value.strip() for value in args.corroboration_id):
            print("error: --corroboration-id values must be non-empty", file=sys.stderr)
            return 2
        print(json.dumps(assess_source(args), indent=2))
        return 0
    if args.command == "self-test":
        return self_test()
    parser.error("unhandled command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
