#!/usr/bin/env python3
"""Syntax-check runnable Python and JavaScript fenced examples.

The check is dependency-free: Python examples are compiled without execution,
and JavaScript examples are passed to the installed Node runtime with
``--check``.  It scans the skill entry point plus routed references/adapters,
not historical release notes or intentionally hostile evaluation fixtures.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


FENCE_RE = re.compile(
    r"^```(?P<lang>python|py|javascript|js|mjs)\s*$\n(?P<body>.*?)^```\s*$",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)
MOJIBAKE_MARKERS = ("\ufffd", "â€", "â†", "Ã¡", "Ã¢", "Ä‘", "Æ°", "Â ")


def documentation_files(root: Path) -> list[Path]:
    paths = [root / "SKILL.md"]
    paths.extend(sorted((root / "references").rglob("*.md")))
    paths.extend(sorted((root / "adapters").rglob("*.md")))
    return [path for path in paths if path.is_file()]


def check_examples(root: Path) -> tuple[int, list[str]]:
    checked = 0
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="d-research-doc-examples-") as temporary:
        temp_root = Path(temporary)
        for path in documentation_files(root):
            text = path.read_text(encoding="utf-8", errors="strict")
            for marker in MOJIBAKE_MARKERS:
                if marker in text:
                    line = text[: text.index(marker)].count("\n") + 1
                    errors.append(
                        f"{path.relative_to(root).as_posix()}:{line}: probable mojibake marker {marker!r}"
                    )
            for index, match in enumerate(FENCE_RE.finditer(text), start=1):
                checked += 1
                language = match.group("lang").lower()
                body = textwrap.dedent(match.group("body"))
                label = f"{path.relative_to(root).as_posix()} fenced {language} #{index}"
                if language in {"python", "py"}:
                    try:
                        compile(body, label, "exec")
                    except SyntaxError as exc:
                        errors.append(f"{label}: {exc.msg} at line {exc.lineno}")
                    continue
                snippet = temp_root / f"snippet-{checked}.mjs"
                snippet.write_text(body, encoding="utf-8", newline="\n")
                try:
                    result = subprocess.run(
                        ["node", "--check", str(snippet)],
                        check=False,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=15,
                    )
                except (OSError, subprocess.SubprocessError) as exc:
                    errors.append(f"{label}: cannot run Node syntax check: {exc}")
                    continue
                if result.returncode != 0:
                    diagnostic = next(
                        (line.strip() for line in result.stderr.splitlines() if "SyntaxError" in line),
                        "Node syntax check failed",
                    )
                    errors.append(f"{label}: {diagnostic}")
    return checked, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    checked, errors = check_examples(args.root.resolve())
    if errors:
        print(f"doc example check FAILED ({len(errors)} error(s), {checked} checked):", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"doc example check ok ({checked} fenced Python/JavaScript examples)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
