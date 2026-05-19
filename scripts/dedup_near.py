#!/usr/bin/env python3
"""Near-duplicate detection via SimHash + Hamming distance.

Subcommands
-----------
* ``fingerprint`` - compute SimHash fingerprint for a single text
* ``scan``        - scan CSV for near-duplicate rows
* ``ledger``      - find near-duplicate claims in evidence-ledger.csv
* ``self-test``   - run offline self-tests

SimHash uses 64-bit hashes over normalized token shingles. Default Hamming
distance threshold is 3 (conservative for "near duplicate").
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from pathlib import Path

SHINGLE_SIZE = 3
HASH_BITS = 64
DEFAULT_THRESHOLD = 3


def _normalize(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _shingles(text: str, size: int = SHINGLE_SIZE) -> list[str]:
    """Generate k-token shingles."""
    tokens = _normalize(text).split()
    if len(tokens) < size:
        return [" ".join(tokens)] if tokens else []
    return [" ".join(tokens[i:i + size]) for i in range(len(tokens) - size + 1)]


def simhash(text: str) -> int:
    """Compute 64-bit SimHash fingerprint."""
    shingles = _shingles(text)
    if not shingles:
        return 0
    bits = [0] * HASH_BITS
    for shingle in shingles:
        h = int(hashlib.sha256(shingle.encode("utf-8")).hexdigest()[:16], 16)
        for i in range(HASH_BITS):
            if (h >> i) & 1:
                bits[i] += 1
            else:
                bits[i] -= 1
    fingerprint = 0
    for i in range(HASH_BITS):
        if bits[i] > 0:
            fingerprint |= (1 << i)
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    """Number of differing bits between two 64-bit integers."""
    return bin(a ^ b).count("1")


def cmd_fingerprint(args: argparse.Namespace) -> int:
    """Print SimHash fingerprint for input text."""
    if args.input:
        text = Path(args.input).read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        text = sys.stdin.read()
    fp = simhash(text)
    print(f"{fp:016x}")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    """Scan CSV for near-duplicate rows by text column."""
    in_path = Path(args.input)
    if not in_path.is_file():
        print(f"error: file not found: {in_path}", file=sys.stderr)
        return 1
    text_col = args.text_column
    threshold = args.threshold

    rows: list[dict[str, str]] = []
    with in_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        print("error: no rows in input", file=sys.stderr)
        return 1
    if text_col not in rows[0]:
        print(f"error: column '{text_col}' not in CSV (have: {list(rows[0].keys())})", file=sys.stderr)
        return 1

    fingerprints = [simhash(row.get(text_col, "")) for row in rows]
    duplicates: list[dict[str, str]] = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            dist = hamming_distance(fingerprints[i], fingerprints[j])
            if dist <= threshold:
                duplicates.append({
                    "left_id": str(i),
                    "right_id": str(j),
                    "distance": str(dist),
                    "left_text": (rows[i].get(text_col, "") or "")[:200],
                    "right_text": (rows[j].get(text_col, "") or "")[:200],
                })

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["left_id", "right_id", "distance", "left_text", "right_text"])
        writer.writeheader()
        for dup in duplicates:
            writer.writerow(dup)
    print(f"found {len(duplicates)} duplicate pair(s) -> {out_path}")
    return 0


def cmd_ledger(args: argparse.Namespace) -> int:
    """Find near-duplicate claims in an evidence-ledger CSV."""
    in_path = Path(args.input)
    if not in_path.is_file():
        print(f"error: file not found: {in_path}", file=sys.stderr)
        return 1
    threshold = args.threshold

    rows: list[dict[str, str]] = []
    with in_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    if not rows:
        print("error: empty ledger", file=sys.stderr)
        return 1

    # Combine claim + evidence as fingerprint text
    fingerprints: list[int] = []
    for row in rows:
        text = f"{row.get('claim', '')} {row.get('evidence', '')}"
        fingerprints.append(simhash(text))

    duplicates: list[dict[str, str]] = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            dist = hamming_distance(fingerprints[i], fingerprints[j])
            if dist <= threshold:
                duplicates.append({
                    "left_id": rows[i].get("claim_id", str(i)),
                    "right_id": rows[j].get("claim_id", str(j)),
                    "distance": str(dist),
                    "left_text": (rows[i].get("claim", "") or "")[:200],
                    "right_text": (rows[j].get("claim", "") or "")[:200],
                })

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["left_id", "right_id", "distance", "left_text", "right_text"])
        writer.writeheader()
        for dup in duplicates:
            writer.writerow(dup)
    print(f"found {len(duplicates)} duplicate pair(s) -> {out_path}")
    return 0


def cmd_self_test(_args: argparse.Namespace) -> int:
    """Offline self-test."""
    import tempfile

    errors: list[str] = []

    # Test 1: identical text → distance 0
    fp1 = simhash("The quick brown fox jumps over the lazy dog")
    fp2 = simhash("The quick brown fox jumps over the lazy dog")
    if hamming_distance(fp1, fp2) != 0:
        errors.append(f"identical text should have distance 0, got {hamming_distance(fp1, fp2)}")

    # Test 2: near duplicates → relatively low distance (compared to different text)
    fp3 = simhash("The quick brown fox jumps over the lazy dog and the cat")
    fp4 = simhash("The quick brown fox jumps over the lazy dog and a cat")  # one word changed
    dist_near = hamming_distance(fp3, fp4)

    # Test 3: clearly different text → higher distance
    fp5 = simhash("The quick brown fox jumps over the lazy dog and the cat")
    fp6 = simhash("Climate change is affecting global weather patterns significantly worldwide today")
    dist_diff = hamming_distance(fp5, fp6)

    # Test 4: near < different (relative comparison is what matters)
    if dist_near >= dist_diff:
        errors.append(f"near distance ({dist_near}) should be less than different distance ({dist_diff})")

    # Test 5: scan command end-to-end
    with tempfile.TemporaryDirectory() as tmpdir:
        td = Path(tmpdir)
        csv_path = td / "rows.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "claim"])
            writer.writeheader()
            writer.writerow({"id": "A", "claim": "Machine learning is a subset of artificial intelligence"})
            writer.writerow({"id": "B", "claim": "Machine learning is a subset of artificial intelligence."})  # near dup
            writer.writerow({"id": "C", "claim": "The Eiffel Tower is located in Paris France"})

        out_path = td / "dups.csv"
        ns = argparse.Namespace(input=str(csv_path), text_column="claim", out=str(out_path), threshold=DEFAULT_THRESHOLD)
        rc = cmd_scan(ns)
        if rc != 0:
            errors.append("scan command failed")
        elif out_path.is_file():
            with out_path.open(newline="", encoding="utf-8") as f:
                dups = list(csv.DictReader(f))
            if len(dups) != 1:
                errors.append(f"scan should find 1 duplicate pair, got {len(dups)}")
            elif dups[0]["left_id"] != "0" or dups[0]["right_id"] != "1":
                errors.append(f"scan duplicate IDs wrong: {dups[0]}")

        # Test 6: ledger command
        ledger_path = td / "ledger.csv"
        with ledger_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["claim_id", "claim", "evidence"])
            writer.writeheader()
            writer.writerow({"claim_id": "C001", "claim": "Python is a programming language", "evidence": "Used widely in data science"})
            writer.writerow({"claim_id": "C002", "claim": "Python is a programming language.", "evidence": "Used widely in data science!"})
            writer.writerow({"claim_id": "C003", "claim": "Bananas are yellow fruits", "evidence": "Grow in tropical climates"})

        out_ledger = td / "ledger_dups.csv"
        ns = argparse.Namespace(input=str(ledger_path), out=str(out_ledger), threshold=DEFAULT_THRESHOLD)
        rc = cmd_ledger(ns)
        if rc != 0:
            errors.append("ledger command failed")
        elif out_ledger.is_file():
            with out_ledger.open(newline="", encoding="utf-8") as f:
                dups = list(csv.DictReader(f))
            if len(dups) != 1:
                errors.append(f"ledger should find 1 duplicate pair, got {len(dups)}")
            elif "C001" not in (dups[0]["left_id"], dups[0]["right_id"]):
                errors.append(f"ledger duplicate IDs wrong: {dups[0]}")

    if errors:
        print("dedup_near self-test FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("dedup_near self-test ok")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="dedup_near.py", description="Near-duplicate detection via SimHash.")
    sub = p.add_subparsers(dest="cmd", required=True)

    fp_p = sub.add_parser("fingerprint", help="Compute SimHash fingerprint.")
    fp_p.add_argument("--text", default=None)
    fp_p.add_argument("--in", dest="input", default=None)

    sc_p = sub.add_parser("scan", help="Scan CSV for near-duplicates.")
    sc_p.add_argument("--in", dest="input", required=True)
    sc_p.add_argument("--text-column", required=True)
    sc_p.add_argument("--out", required=True)
    sc_p.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)

    le_p = sub.add_parser("ledger", help="Find near-duplicate claims in evidence-ledger.csv.")
    le_p.add_argument("--in", dest="input", required=True)
    le_p.add_argument("--out", required=True)
    le_p.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)

    sub.add_parser("self-test", help="Run offline self-tests.")

    args = p.parse_args()
    if args.cmd == "fingerprint":
        return cmd_fingerprint(args)
    if args.cmd == "scan":
        return cmd_scan(args)
    if args.cmd == "ledger":
        return cmd_ledger(args)
    if args.cmd == "self-test":
        return cmd_self_test(args)
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
