#!/usr/bin/env python3
"""Capability baseline capture + monotonic superset checker for D Research.

This tool freezes the public capability surface of the skill (npm scripts,
ledger contract, route ids, key defaults, and the reference/script/template
inventories) into a machine-readable JSON snapshot, and verifies that a
candidate tree is a *superset* of a frozen baseline.

It exists to enforce the monotonic-capability invariant of the v3.4.0 upgrade:
every command, route, ledger schema, reference, script, and template that used
to exist must still exist, and every recorded default must be unchanged unless
a caller opts into a new value. Adding capability is always allowed; removing or
narrowing it fails the check.

Pure standard library. Runs on Python >= 3.10. It is intentionally kept under
release-evidence/ so it does not alter the counted scripts/ or templates/
inventories that the repository contract validates.

Usage:
  python capability_baseline.py capture [--root <repo>] [--out <file>]
  python capability_baseline.py check --baseline <file> [--root <repo>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _repo_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    # release-evidence/v3.4.0/baseline/capability_baseline.py -> repo root is 3 up.
    return Path(__file__).resolve().parents[3]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _ledger_contract(root: Path) -> dict:
    """Read the ledger contract straight from evidence_ledger.py constants."""
    scripts_dir = root / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        import evidence_ledger as el  # type: ignore
    finally:
        # Leave sys.path clean for repeated in-process calls (tests).
        try:
            sys.path.remove(str(scripts_dir))
        except ValueError:
            pass
    header_sizes = sorted({len(fields) for fields in el.ACCEPTED_FIELD_SETS})
    record_types = sorted(t for t in el.VALID_RECORD_TYPES if t)
    return {
        "header_sizes": header_sizes,
        "record_types": record_types,
        "signature": el.SIG_VERSION,
        "canonicalization": getattr(
            el, "CANON_VERSION", "d-research-skill/csv/v1"
        ),
    }


def _api_fetch_default_max_pages(root: Path) -> int | None:
    text = (root / "scripts" / "api_fetch.mjs").read_text(encoding="utf-8")
    match = re.search(r"maxPages:\s*(\d+)", text)
    return int(match.group(1)) if match else None


def _default_from_source(root: Path, relative: str, pattern: str) -> int | None:
    """Read a simple numeric public default without importing optional runtimes."""
    text = (root / relative).read_text(encoding="utf-8")
    match = re.search(pattern, text)
    return int(match.group(1)) if match else None


def _cli_options(root: Path) -> dict[str, list[str]]:
    """Capture option names exposed by bundled Python/Node entrypoints.

    This is intentionally lexical: invoking every command's help can perform
    imports, discover credentials, or require optional binaries.  It still
    catches removal of an advertised flag and permits additive new flags.
    """
    result: dict[str, list[str]] = {}
    paths = sorted(
        list((root / "scripts").glob("*.py"))
        + list((root / "scripts").glob("*.mjs"))
        + list((root / "scripts" / "lib").glob("*.mjs"))
    )
    option_re = re.compile(r"(?<![A-Za-z0-9_])--[A-Za-z][A-Za-z0-9-]*")
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        options = sorted(set(option_re.findall(text)))
        if options:
            result[path.relative_to(root).as_posix()] = options
    return result


def _package_surface(root: Path) -> dict:
    """Capture the published path list and its deterministic digest."""
    try:
        proc = subprocess.run(
            ["npm.cmd" if os.name == "nt" else "npm", "pack", "--dry-run", "--json", "--ignore-scripts"],
            cwd=root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        payload = json.loads(proc.stdout)
        manifest = payload[0] if isinstance(payload, list) else payload
        paths = sorted(
            str(entry.get("path", "")).replace("\\", "/")
            for entry in manifest.get("files", [])
            if isinstance(entry, dict) and entry.get("path")
        )
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        paths = []
    canonical = json.dumps(paths, ensure_ascii=False, separators=(",", ":"))
    return {
        "file_count": len(paths),
        "paths_sha256": "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "paths": paths,
    }


def _rel_sorted(paths: list[Path], root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in paths)


def capture(root: Path) -> dict:
    package = _load_json(root / "package.json")
    manifest = _load_json(root / "templates" / "route-manifest.json")
    routes = sorted(str(r.get("id")) for r in manifest.get("routes", []) if r.get("id"))
    references = _rel_sorted(list((root / "references").rglob("*.md")), root)
    scripts = _rel_sorted(
        list((root / "scripts").glob("*.py"))
        + list((root / "scripts").glob("*.mjs"))
        + list((root / "scripts" / "lib").glob("*.mjs")),
        root,
    )
    templates = _rel_sorted(
        [p for p in (root / "templates").iterdir() if p.is_file()], root
    )
    return {
        "schema_version": 1,
        "package_version": package.get("version"),
        "npm_scripts": sorted(package.get("scripts", {}).keys()),
        "ledger": _ledger_contract(root),
        "routes": routes,
        "defaults": {
            "api_fetch.maxPages": _api_fetch_default_max_pages(root),
            "api_fetch.delay": _default_from_source(root, "scripts/api_fetch.mjs", r"delay:\s*(\d+)"),
            "api_fetch.timeout": _default_from_source(root, "scripts/api_fetch.mjs", r"timeout:\s*(\d+)"),
            "crawl.maxDepth": _default_from_source(root, "scripts/playwright_crawl.mjs", r"maxDepth\s*:\s*(\d+)"),
            "crawl.maxPages": _default_from_source(root, "scripts/playwright_crawl.mjs", r"maxPages\s*:\s*(\d+)"),
            "crawl.maxPagesPerDomain": _default_from_source(root, "scripts/playwright_crawl.mjs", r"maxPagesPerDomain\s*:\s*(\d+)"),
            "crawl.delayMs": _default_from_source(root, "scripts/playwright_crawl.mjs", r"delayMs\s*:\s*(\d+)"),
            "crawl.timeout": _default_from_source(root, "scripts/playwright_crawl.mjs", r"timeout\s*:\s*(\d+)"),
        },
        "cli_options": _cli_options(root),
        "package_surface": _package_surface(root),
        "references": references,
        "scripts": scripts,
        "templates": templates,
    }


def _superset_errors(name: str, baseline: list, candidate: list) -> list[str]:
    missing = [item for item in baseline if item not in set(candidate)]
    return [f"{name}: removed {item!r}" for item in missing]


def check(baseline: dict, current: dict) -> list[str]:
    errors: list[str] = []

    for name in ("npm_scripts", "routes", "references", "scripts", "templates"):
        errors.extend(
            _superset_errors(name, baseline.get(name, []), current.get(name, []))
        )

    # CLI options are a per-entrypoint superset: new flags are allowed, but an
    # existing advertised flag may not disappear.
    baseline_options = baseline.get("cli_options", {})
    current_options = current.get("cli_options", {})
    for path, required in baseline_options.items():
        errors.extend(_superset_errors(f"cli_options[{path}]", required, current_options.get(path, [])))

    # Full/source package paths are also monotonic.  The digest is retained as
    # evidence, while the check compares the path set so additive files remain
    # valid in a candidate.
    baseline_surface = baseline.get("package_surface", {})
    current_surface = current.get("package_surface", {})
    errors.extend(
        _superset_errors(
            "package_surface.paths",
            baseline_surface.get("paths", []),
            current_surface.get("paths", []),
        )
    )

    b_ledger = baseline.get("ledger", {})
    c_ledger = current.get("ledger", {})
    errors.extend(
        _superset_errors(
            "ledger.header_sizes",
            b_ledger.get("header_sizes", []),
            c_ledger.get("header_sizes", []),
        )
    )
    errors.extend(
        _superset_errors(
            "ledger.record_types",
            b_ledger.get("record_types", []),
            c_ledger.get("record_types", []),
        )
    )
    for field in ("signature", "canonicalization"):
        if b_ledger.get(field) and b_ledger.get(field) != c_ledger.get(field):
            errors.append(
                f"ledger.{field} changed: {b_ledger.get(field)!r} -> "
                f"{c_ledger.get(field)!r} (breaks existing signatures)"
            )

    b_defaults = baseline.get("defaults", {})
    c_defaults = current.get("defaults", {})
    for key, value in b_defaults.items():
        if c_defaults.get(key) != value:
            errors.append(
                f"default {key} changed without opt-in: "
                f"{value!r} -> {c_defaults.get(key)!r}"
            )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_cap = sub.add_parser("capture", help="Emit a capability snapshot as JSON.")
    p_cap.add_argument("--root", default=None)
    p_cap.add_argument("--out", default=None, help="Output file (default: stdout).")

    p_chk = sub.add_parser("check", help="Fail if the tree regresses the baseline.")
    p_chk.add_argument("--root", default=None)
    p_chk.add_argument("--baseline", required=True)

    args = parser.parse_args(argv)
    root = _repo_root(args.root)

    if args.cmd == "capture":
        snapshot = capture(root)
        text = json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n"
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"wrote capability baseline -> {args.out}")
        else:
            sys.stdout.write(text)
        return 0

    if args.cmd == "check":
        baseline = _load_json(Path(args.baseline))
        current = capture(root)
        errors = check(baseline, current)
        if errors:
            print("capability regression detected:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 1
        print(
            "capability check ok: candidate is a superset of "
            f"{baseline.get('package_version')} "
            f"({len(current['npm_scripts'])} scripts, {len(current['routes'])} routes, "
            f"{len(current['references'])} references)"
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
