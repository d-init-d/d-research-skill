#!/usr/bin/env python3
"""
Data cleaning helper for D Research skill.
Commands: clean, stats, dedup, validate, merge, self-test
"""

import argparse
import csv
import json
import sys
from pathlib import Path
import tempfile
from typing import Any, TypedDict


class ColumnStats(TypedDict):
    types: list[str]
    missing: int
    samples: list[str]


def read_csv(file_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    """Read CSV file and return headers and rows."""
    with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        rows = [
            {
                str(k): "" if v is None else str(v)
                for k, v in row.items()
                if k is not None
            }
            for row in reader
        ]
    return headers, rows


def write_csv(file_path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    """Write CSV file from headers and rows."""
    with open(file_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def normalize_value(value: str) -> str:
    """Normalize value: trim whitespace, normalize encoding, standardize empty."""
    if value is None:
        return ""
    value = value.strip()
    # Normalize unicode whitespace
    value = value.replace("\u00a0", " ")
    value = value.replace("\u200b", "")
    # Standardize empty variations to empty string
    if value.lower() in ("null", "na", "n/a", "none", "-", "."):
        return ""
    return value


def clean_data(input_path: Path, output_path: Path) -> int:
    """Remove exact duplicate rows, trim whitespace, normalize encoding, standardize empty values."""
    headers, rows = read_csv(input_path)

    # Normalize all values
    normalized_rows = []
    for row in rows:
        normalized_row = {k: normalize_value(v) for k, v in row.items()}
        normalized_rows.append(normalized_row)

    # Remove exact duplicates (keep first occurrence)
    seen = set()
    unique_rows = []
    for row in normalized_rows:
        row_key = tuple(sorted(row.items()))
        if row_key not in seen:
            seen.add(row_key)
            unique_rows.append(row)

    write_csv(output_path, headers, unique_rows)
    return len(unique_rows)


def infer_type(value: str) -> str:
    """Infer the type of a value."""
    if value == "" or value is None:
        return "empty"
    try:
        int(value)
        return "integer"
    except ValueError:
        pass
    try:
        float(value)
        return "float"
    except ValueError:
        pass
    if value.lower() in ("true", "false"):
        return "boolean"
    return "string"


def get_stats(input_path: Path) -> dict[str, Any]:
    """Calculate statistics for CSV file."""
    headers, rows = read_csv(input_path)
    col_stats: dict[str, ColumnStats] = {
        header: {"types": [], "missing": 0, "samples": []} for header in headers
    }

    for row in rows:
        for header in headers:
            value = row.get(header, "")
            stats = col_stats[header]
            if value.strip() == "":
                stats["missing"] += 1
            stats["types"].append(infer_type(value))
            if len(stats["samples"]) < 3:
                stats["samples"].append(value)

    return {
        "row_count": len(rows),
        "column_count": len(headers),
        "columns": [
            {
                "name": header,
                "type": max(set(stats["types"]), key=stats["types"].count)
                if stats["types"]
                else "unknown",
                "missing": stats["missing"],
                "samples": stats["samples"],
            }
            for header, stats in col_stats.items()
        ],
    }


def print_stats(input_path: Path) -> None:
    """Print formatted statistics table."""
    stats = get_stats(input_path)

    print(f"\n{'=' * 60}")
    print(f"File: {input_path}")
    print(f"{'=' * 60}")
    print(f"Rows: {stats['row_count']}")
    print(f"Columns: {stats['column_count']}")
    print(f"\n{'=' * 60}")
    print(f"{'Column Name':<20} {'Type':<10} {'Missing':<10} {'Sample Values':<25}")
    print(f"{'-' * 60}")

    for col in stats["columns"]:
        samples = ", ".join(repr(s[:15]) for s in col["samples"][:2])
        print(f"{col['name']:<20} {col['type']:<10} {col['missing']:<10} {samples:<25}")

    print(f"{'=' * 60}\n")


def dedup_data(input_path: Path, key_field: str, output_path: Path) -> int:
    """Remove duplicates based on key field, keeping first occurrence."""
    headers, rows = read_csv(input_path)

    if key_field not in headers:
        raise ValueError(f"Key field '{key_field}' not found in CSV columns")

    seen_keys = set()
    unique_rows = []

    for row in rows:
        key_value = row.get(key_field, "")
        if key_value not in seen_keys:
            seen_keys.add(key_value)
            unique_rows.append(row)

    write_csv(output_path, headers, unique_rows)
    return len(unique_rows)


def validate_data(input_path: Path, schema_path: Path) -> list[str]:
    """Validate CSV against JSON schema."""
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    headers, rows = read_csv(input_path)
    errors = []

    expected_fields = schema.get("fields", {})
    required_fields = schema.get("required", [])

    # Check required fields
    for field in required_fields:
        if field not in headers:
            errors.append(f"Missing required field: '{field}'")

    # Check field types for each row
    for i, row in enumerate(rows, 1):
        for field, expected_type in expected_fields.items():
            if field not in headers:
                continue

            value = row.get(field, "")
            actual_type = infer_type(value) if value.strip() else "empty"

            # Skip if value is empty and field is not required
            if actual_type == "empty" and field not in required_fields:
                continue

            if actual_type != expected_type:
                errors.append(
                    f"Row {i}: Field '{field}' has type '{actual_type}', expected '{expected_type}'"
                )

    return errors


def merge_data(file_paths: list[Path], key: str, output_path: Path) -> int:
    """Left join multiple CSV files on key field."""
    if len(file_paths) < 2:
        raise ValueError("At least two files required for merge")

    # Read first file (leftmost)
    headers1, rows1 = read_csv(file_paths[0])
    if key not in headers1:
        raise ValueError(f"Key field '{key}' not found in first file")

    # Collect all headers, excluding key duplicates
    all_headers = [h for h in headers1 if h != key]
    all_headers_set = set(all_headers)

    # Read remaining files and build lookup tables
    lookup_tables = []
    for file_path in file_paths[1:]:
        headers_n, rows_n = read_csv(file_path)
        if key not in headers_n:
            raise ValueError(f"Key field '{key}' not found in {file_path}")

        lookup = {row[key]: row for row in rows_n if row[key]}
        lookup_tables.append((headers_n, lookup))

        for h in headers_n:
            if h != key and h not in all_headers_set:
                all_headers.append(h)
                all_headers_set.add(h)

    # Prepend key as first column
    final_headers = [key] + all_headers

    # Merge rows
    merged_rows = []
    for row in rows1:
        key_value = row.get(key, "")
        new_row = {key: key_value}

        for h in headers1:
            if h != key:
                new_row[h] = row.get(h, "")

        # Join with other tables
        for headers_n, lookup in lookup_tables:
            if key_value in lookup:
                right_row = lookup[key_value]
                for h in headers_n:
                    if h != key:
                        new_row[h] = right_row.get(h, "")

        merged_rows.append(new_row)

    write_csv(output_path, final_headers, merged_rows)
    return len(merged_rows)


def run_self_test() -> bool:
    """Run all commands on temp data to verify they work."""
    print("\n" + "=" * 60)
    print("RUNNING SELF-TEST")
    print("=" * 60 + "\n")

    success = True
    temp_dir = Path(tempfile.gettempdir())

    # Create test data files
    test_data_a = temp_dir / "test_a.csv"
    test_data_b = temp_dir / "test_b.csv"
    test_output = temp_dir / "test_output.csv"

    try:
        # Test data with duplicates, whitespace, empty values
        with open(test_data_a, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerows(
                [
                    ["id", "name", "value"],
                    ["1", "  Alice  ", "100"],
                    ["2", "Bob", "200"],
                    ["1", "  Alice  ", "100"],  # Duplicate
                    ["3", "Charlie", ""],  # Empty value
                    ["4", "  ", "N/A"],  # Whitespace and NA
                ]
            )

        with open(test_data_b, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerows(
                [
                    ["id", "extra"],
                    ["1", "Yes"],
                    ["2", "No"],
                    ["5", "Maybe"],  # Not in left file
                ]
            )

        # Test 1: Clean command
        print("Test 1: clean command")
        clean_out = temp_dir / "test_cleaned.csv"
        count = clean_data(test_data_a, clean_out)
        assert count == 4, f"Expected 4 rows, got {count}"
        print("  [PASS] clean command passed (4 unique rows)")

        # Verify cleaned data
        headers, rows = read_csv(clean_out)
        assert len(rows) == 4
        for row in rows:
            assert row["name"] == row["name"].strip()
        print("  [PASS] whitespace trimmed correctly")

        # Test 2: Stats command
        print("\nTest 2: stats command")
        stats = get_stats(test_data_a)
        assert stats["row_count"] == 5
        assert stats["column_count"] == 3
        assert len(stats["columns"]) == 3
        print("  [PASS] stats command passed (5 rows, 3 columns)")

        # Test 3: Dedup command
        print("\nTest 3: dedup command")
        dedup_out = temp_dir / "test_deduped.csv"
        count = dedup_data(test_data_a, "id", dedup_out)
        assert count == 4, f"Expected 4 unique rows, got {count}"
        print("  [PASS] dedup command passed")

        # Test 4: Validate command
        print("\nTest 4: validate command")
        schema = {
            "fields": {"id": "integer", "name": "string", "value": "integer"},
            "required": ["id"],
        }
        schema_file = temp_dir / "test_schema.json"
        with open(schema_file, "w") as f:
            json.dump(schema, f)

        errors = validate_data(clean_out, schema_file)
        assert len(errors) == 0, f"Expected no errors, got {errors}"
        print("  [PASS] validate command passed (validates cleaned output)")

        # Test with schema that should produce errors (name expected as integer but is string)
        bad_schema = {"fields": {"id": "integer", "name": "integer"}}
        with open(schema_file, "w") as f:
            json.dump(bad_schema, f)

        errors = validate_data(test_data_a, schema_file)
        assert len(errors) > 0, "Expected validation errors"
        print("  [PASS] validate command detected type mismatch")

        # Test 5: Merge command
        print("\nTest 5: merge command")
        merge_out = temp_dir / "test_merged.csv"
        count = merge_data([test_data_a, test_data_b], "id", merge_out)
        assert count == 5, f"Expected 5 rows after merge, got {count}"

        headers, rows = read_csv(merge_out)
        assert "extra" in headers, "Missing 'extra' column"
        print("  [PASS] merge command passed (left join successful)")

        # Verify merge results
        lookup = {row["id"]: row for row in rows}
        assert lookup["1"]["extra"] == "Yes"
        assert lookup["2"]["extra"] == "No"
        assert lookup["3"]["extra"] == ""  # Not in right file
        print("  [PASS] merge values correct")

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n  [FAIL] TEST FAILED: {e}")
        success = False
        import traceback

        traceback.print_exc()

    finally:
        # Cleanup temp files
        for f in [test_data_a, test_data_b, test_output]:
            if f.exists():
                f.unlink()

    return success


def main() -> int:
    """Main entry point with argparse subparsers."""
    parser = argparse.ArgumentParser(
        prog="data_clean.py",
        description="Data cleaning helper for D Research skill.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="command", required=True, help="Commands")

    # clean command
    clean_parser = subparsers.add_parser(
        "clean", help="Clean CSV: remove duplicates, trim whitespace, normalize"
    )
    clean_parser.add_argument("--file", required=True, type=Path, help="Input CSV file")
    clean_parser.add_argument("--out", required=True, type=Path, help="Output CSV file")

    # stats command
    stats_parser = subparsers.add_parser(
        "stats", help="Print CSV statistics as formatted table"
    )
    stats_parser.add_argument("--file", required=True, type=Path, help="Input CSV file")

    # dedup command
    dedup_parser = subparsers.add_parser(
        "dedup", help="Remove duplicates by key field (keep first)"
    )
    dedup_parser.add_argument("--file", required=True, type=Path, help="Input CSV file")
    dedup_parser.add_argument(
        "--key", required=True, help="Key field name for deduplication"
    )
    dedup_parser.add_argument("--out", required=True, type=Path, help="Output CSV file")

    # validate command
    validate_parser = subparsers.add_parser(
        "validate", help="Validate CSV against JSON schema"
    )
    validate_parser.add_argument(
        "--file", required=True, type=Path, help="Input CSV file"
    )
    validate_parser.add_argument(
        "--schema", required=True, type=Path, help="JSON schema file"
    )

    # merge command
    merge_parser = subparsers.add_parser("merge", help="Left join CSVs on key field")
    merge_parser.add_argument(
        "--files",
        required=True,
        nargs=2,
        type=Path,
        metavar="FILE",
        help="Input CSV files",
    )
    merge_parser.add_argument("--key", required=True, help="Key field for join")
    merge_parser.add_argument("--out", required=True, type=Path, help="Output CSV file")

    # self-test command
    subparsers.add_parser("self-test", help="Run self-test on all commands")

    args = parser.parse_args()

    try:
        if args.command == "clean":
            count = clean_data(args.file, args.out)
            print(f"[PASS] Cleaned data written to {args.out}: {count} rows")
            return 0

        elif args.command == "stats":
            print_stats(args.file)
            return 0

        elif args.command == "dedup":
            count = dedup_data(args.file, args.key, args.out)
            print(
                f"[PASS] Deduplicated by '{args.key}' written to {args.out}: {count} rows"
            )
            return 0

        elif args.command == "validate":
            errors = validate_data(args.file, args.schema)
            if errors:
                print("[FAIL] Validation errors found:")
                for error in errors:
                    print(f"  - {error}")
                return 1
            else:
                print("[PASS] CSV validates against schema")
                return 0

        elif args.command == "merge":
            count = merge_data(args.files, args.key, args.out)
            print(f"[PASS] Merged on '{args.key}' written to {args.out}: {count} rows")
            return 0

        elif args.command == "self-test":
            return 0 if run_self_test() else 1

    except FileNotFoundError as e:
        print(f"[FAIL] Error: File not found - {e}")
        return 1
    except ValueError as e:
        print(f"[FAIL] Error: {e}")
        return 1
    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
