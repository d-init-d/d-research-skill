#!/usr/bin/env python3
"""Resolve D Research package identity from the canonical package.json.

Network helpers use this module instead of embedding release numbers in each
User-Agent. A copied standalone helper remains usable and reports an `unknown`
version when package.json is unavailable; repository and packaged executions
resolve the exact current version.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "d-research-skill-tools"
PRODUCT_NAME = "d-research-skill"
REPOSITORY_URL = "https://github.com/d-init-d/d-research-skill"
VERSION_RE = re.compile(r"\d+\.\d+\.\d+(?:-rc\.\d+)?")


class PackageMetadataError(ValueError):
    """Raised when canonical package metadata is missing or malformed."""


def package_version(root: Path = ROOT, *, strict: bool = False) -> str:
    path = root / "package.json"
    try:
        package = json.loads(path.read_text(encoding="utf-8"))
        name = package.get("name") if isinstance(package, dict) else None
        version = package.get("version") if isinstance(package, dict) else None
        if name != PACKAGE_NAME or not isinstance(version, str) or VERSION_RE.fullmatch(version) is None:
            raise PackageMetadataError(f"invalid D Research package identity in {path}")
        return version
    except (OSError, UnicodeError, json.JSONDecodeError, PackageMetadataError) as exc:
        if strict:
            if isinstance(exc, PackageMetadataError):
                raise
            raise PackageMetadataError(f"cannot read canonical package metadata from {path}: {exc}") from exc
        return "unknown"


def package_user_agent(
    *,
    component: str | None = None,
    contact: str | None = None,
    root: Path = ROOT,
) -> str:
    details = [REPOSITORY_URL]
    if component:
        details.append(component.strip())
    if contact:
        details.append(contact.strip())
    return f"{PRODUCT_NAME}/{package_version(root)} ({'; '.join(details)})"


def self_test() -> int:
    errors: list[str] = []
    actual = package_version(strict=True)
    if actual not in package_user_agent(component="self-test"):
        errors.append("User-Agent does not contain the canonical package version")
    with tempfile.TemporaryDirectory(prefix="d-research-package-metadata-") as temporary:
        root = Path(temporary)
        (root / "package.json").write_text(
            json.dumps({"name": PACKAGE_NAME, "version": "9.8.7-rc.6"}),
            encoding="utf-8",
        )
        if package_version(root, strict=True) != "9.8.7-rc.6":
            errors.append("valid prerelease version was not resolved")
        (root / "package.json").write_text("{}", encoding="utf-8")
        if package_version(root) != "unknown":
            errors.append("non-strict malformed metadata must fall back to unknown")
        try:
            package_version(root, strict=True)
        except PackageMetadataError:
            pass
        else:
            errors.append("strict malformed metadata did not fail closed")
    if errors:
        for error in errors:
            print(f"package_metadata self-test FAILED: {error}", file=sys.stderr)
        return 1
    print("package_metadata self-test ok")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("version")
    user_agent = subparsers.add_parser("user-agent")
    user_agent.add_argument("--component")
    user_agent.add_argument("--contact")
    subparsers.add_parser("self-test")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "version":
        print(package_version(strict=True))
        return 0
    if args.command == "user-agent":
        print(package_user_agent(component=args.component, contact=args.contact))
        return 0
    if args.command == "self-test":
        return self_test()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
