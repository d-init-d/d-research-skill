#!/usr/bin/env python3
"""Evidence ledger helper for D Research.

Commands:
  init --out evidence.csv
  validate --file evidence.csv
  self-test
"""
from __future__ import annotations

import argparse
import csv
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


def self_test() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "evidence.csv"
        init_ledger(path)
        if validate_ledger(path) != 0:
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
    sub.add_parser("self-test")
    args = parser.parse_args()
    if args.cmd == "init":
        init_ledger(Path(args.out))
        return 0
    if args.cmd == "validate":
        return validate_ledger(Path(args.file))
    if args.cmd == "self-test":
        return self_test()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
