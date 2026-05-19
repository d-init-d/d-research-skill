#!/usr/bin/env python3
"""Refuse to commit PLAN-*.md roadmap docs.

Used by the ``no-plan-files`` pre-commit hook. Pre-commit passes the
list of staged files as arguments. Any file whose basename matches
``PLAN-*.md`` causes the hook to fail with a clear message.

Exits 0 on success (no PLAN files staged) and 1 if any are found.
"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    blocked: list[str] = []
    for arg in sys.argv[1:]:
        name = Path(arg).name
        if name.startswith("PLAN-") and name.endswith(".md"):
            blocked.append(arg)
    if blocked:
        print(
            "error: PLAN-*.md files must not be committed; "
            "they are local roadmap notes.",
            file=sys.stderr,
        )
        for path in blocked:
            print(f"  blocked: {path}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
