#!/usr/bin/env python3
"""Evidence ledger helper for D Research.

Commands:
  init --out evidence.csv
  validate --file evidence.csv
  sign --file evidence.csv --key-env LEDGER_KEY [--out evidence.csv.hmac]
  verify --file evidence.csv --key-env LEDGER_KEY [--sig evidence.csv.hmac]
  self-test

The `sign`/`verify` subcommands implement tamper-evident audit trails
using HMAC-SHA256 over the canonicalised CSV bytes (rewritten with a
stable field order and Unix line endings before hashing). This is *not*
the "Merkle tree + RSA-4096" sketched by an earlier README draft - HMAC
is a much simpler primitive that does not require key management
infrastructure, but it is sufficient for tamper-evidence when the
signing key is held by a single trusted party.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import io
import os
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
]

VALID_SOURCE_TYPES = {
    "primary",
    "official",
    "dataset",
    "code",
    "paper",
    "filing",
    "secondary",
    "community",
    "unknown",
}

VALID_CONFIDENCE = {"high", "medium", "low"}
VALID_CONTRADICTION = {"none", "possible", "direct", "unresolved", ""}


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
        if reader.fieldnames != FIELDS:
            errors.append(f"header mismatch: expected {FIELDS}, got {reader.fieldnames}")
            print("\n".join(errors), file=sys.stderr)
            return 1
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
    """
    with file.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != FIELDS:
            raise ValueError(
                f"header mismatch: expected {FIELDS}, got {reader.fieldnames}"
            )
        rows = list(reader)
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=FIELDS, lineterminator="\n", quoting=csv.QUOTE_MINIMAL
    )
    writer.writeheader()
    for row in rows:
        clean = {k: (row.get(k) or "").strip() for k in FIELDS}
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


def self_test() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "evidence.csv"
        init_ledger(path)
        if validate_ledger(path) != 0:
            return 1
        # Sign / verify / tamper-detection round-trip.
        os.environ["D_RESEARCH_LEDGER_KEY"] = "unit-test-key-do-not-use-in-prod"
        # Add one valid row so canonicalise has something to chew on.
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
        # Tamper with the file; verify must reject.
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace("the sky is blue", "the sky is green"),
            encoding="utf-8",
        )
        if verify_ledger(path, "D_RESEARCH_LEDGER_KEY", None) == 0:
            print("tamper not detected", file=sys.stderr)
            return 1
        sig_path.unlink(missing_ok=True)
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
    if args.cmd == "self-test":
        return self_test()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
