#!/usr/bin/env python3
"""Cross-platform wrapper that runs ``node --check`` on every .mjs file.

Pre-commit hooks pass changed files as arguments; if no .mjs files were
passed (e.g. when the hook is invoked manually with no files), the
script falls back to scanning ``scripts/*.mjs`` and ``scripts/lib/*.mjs``.

Exits 0 on success, 1 on any syntax error or if ``node`` is missing.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def _candidates(args: list[str]) -> list[Path]:
    if args:
        return [Path(a) for a in args if a.endswith(".mjs")]
    repo = Path(__file__).resolve().parent.parent
    out: list[Path] = []
    for sub in (repo / "scripts", repo / "scripts" / "lib"):
        if sub.is_dir():
            out.extend(sorted(sub.glob("*.mjs")))
    return out


def main() -> int:
    targets = _candidates(sys.argv[1:])
    if not targets:
        print("no .mjs files to check")
        return 0
    node = shutil.which("node")
    if node is None:
        print("error: node executable not found on PATH", file=sys.stderr)
        return 1
    failed = 0
    for path in targets:
        if not path.is_file():
            continue
        print(f"node --check {path}")
        result = subprocess.run([node, "--check", str(path)], check=False)
        if result.returncode != 0:
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
