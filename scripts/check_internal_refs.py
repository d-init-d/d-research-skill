#!/usr/bin/env python3
"""Validate internal repo cross-references inside markdown files.

This is complementary to a Markdown-link checker (e.g. lychee `--offline`):

* Lychee `--offline` validates standard Markdown link syntax `[text](path)`.
* This script validates **backticked** internal references that are common in
  this skill, e.g. `references/foo.md`, `adapters/playwright.md`,
  `scripts/api_fetch.mjs`, `templates/evidence-ledger.csv`.

The check is intentionally conservative: it only flags a backticked token as a
"reference" when the token contains a `/` AND ends in a known repo file
extension. Tokens without a `/` (bare filenames in prose) and tokens with
shell-style glob characters or whitespace are ignored.

Exit status:
    0  no broken refs
    1  one or more broken refs
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Known extensions that should always resolve to a real file on disk when
# referenced via a path with at least one `/`. Add new ones here if the repo
# starts hosting other content types.
TRACKED_EXTENSIONS = {
    ".md",
    ".csv",
    ".json",
    ".bib",
    ".mjs",
    ".py",
    ".yml",
    ".yaml",
    ".toml",
    ".sh",
    ".txt",
}

# Backticked token: anything between single backticks, no whitespace, no glob
# chars, no angle-bracket placeholders (e.g. `references/<topic>.md` in
# CONTRIBUTING.md is a docs template, not a real file). We grab the inside of
# the backticks and later filter by shape.
BACKTICK_RE = re.compile(r"`([^`\s\{\}\*<>]+)`")

# Allowlist of path roots that DO live in the repo. Any reference must start
# with one of these segments (after normalisation) for us to bother validating
# it as an internal path.
REPO_ROOTS = {
    "adapters",
    "examples",
    "references",
    "scripts",
    "templates",
    "docs",
    ".agents",
    ".github",
}


def looks_like_internal_ref(token: str) -> bool:
    """Return True if `token` looks like an in-repo file path."""
    if "/" not in token:
        return False
    suffix = "." + token.rsplit(".", 1)[-1].lower() if "." in token else ""
    if suffix not in TRACKED_EXTENSIONS:
        return False
    first_segment = token.split("/", 1)[0]
    if first_segment not in REPO_ROOTS:
        return False
    return True


# ----------------------------------------------------------------------
# Decision-tree audit
# ----------------------------------------------------------------------

# Anchor files: every references/*.md should be reachable from one of
# these. We crawl one extra hop so a reference linked only from a sibling
# reference is reachable as long as that sibling is on the tree.
DECISION_TREE_ANCHORS = (
    "SKILL.md",
    "AGENTS.md",
    "README.md",
    "CONTRIBUTING.md",
)

# Files that are intentionally supplementary (templates / i18n bundles /
# deep-dive material) and should not trigger the audit even if they are
# not directly linked from the anchor list.
DECISION_TREE_SUPPLEMENTARY = {
    "references/i18n/refusal.en.json",
    "references/i18n/refusal.vi.json",
}


def _collect_internal_links(text: str) -> set[str]:
    """Return every internal repo path referenced in `text`."""
    out: set[str] = set()
    cleaned = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    for match in BACKTICK_RE.finditer(cleaned):
        token = match.group(1).split("#", 1)[0].split("?", 1)[0]
        if looks_like_internal_ref(token):
            out.add(token)
    for match in re.finditer(r"\[[^\]]+\]\(([^)\s]+)\)", cleaned):
        token = match.group(1).split("#", 1)[0].split("?", 1)[0]
        if looks_like_internal_ref(token):
            out.add(token)
    return out


def decision_tree_audit(repo: Path) -> list[str]:
    """Return references/*.md files that are not reachable from the tree."""
    refs_dir = repo / "references"
    if not refs_dir.is_dir():
        return []
    all_refs = {
        str(p.relative_to(repo)).replace("\\", "/")
        for p in refs_dir.rglob("*.md")
    }
    if not all_refs:
        return []

    reachable: set[str] = set()
    queue: list[Path] = []
    for name in DECISION_TREE_ANCHORS:
        anchor = repo / name
        if anchor.is_file():
            queue.append(anchor)

    visited: set[Path] = set()
    while queue:
        current = queue.pop()
        if current in visited:
            continue
        visited.add(current)
        try:
            text = current.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for token in _collect_internal_links(text):
            if token.startswith("references/") and token.endswith(".md"):
                reachable.add(token)
            target = repo / token
            if (
                target.is_file()
                and target.suffix == ".md"
                and token.startswith("references/")
                and target not in visited
            ):
                queue.append(target)

    return sorted(
        ref
        for ref in all_refs
        if ref not in reachable and ref not in DECISION_TREE_SUPPLEMENTARY
    )


def scan(repo: Path) -> list[tuple[Path, str]]:
    broken: list[tuple[Path, str]] = []
    for md in repo.rglob("*.md"):
        # Don't scan vendored or git-internal files.
        if any(part.startswith(".") and part not in {".agents", ".github"} for part in md.parts):
            continue
        if ".git" in md.parts:
            continue
        # Skip PLAN-* files: these are roadmap documents that intentionally
        # reference scripts/files not yet implemented in the current version.
        if md.name.startswith("PLAN-"):
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        # Skip fenced code blocks so we don't validate references that only
        # appear inside example code.
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        for match in BACKTICK_RE.finditer(text):
            token = match.group(1)
            # Strip URL-style anchors/query strings if any sneak in.
            token = token.split("#", 1)[0].split("?", 1)[0]
            if not looks_like_internal_ref(token):
                continue
            target = (repo / token).resolve()
            if not target.exists():
                broken.append((md.relative_to(repo), token))
    return broken


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate backticked in-repo file references in markdown."
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Repository root to scan (default: current directory).",
    )
    parser.add_argument(
        "--decision-tree",
        action="store_true",
        help="Also verify that every references/*.md is reachable from SKILL.md "
        "or the workflow checklists.",
    )
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    broken = scan(repo)
    rc = 0
    if broken:
        print(f"FAIL: {len(broken)} broken internal reference(s):", file=sys.stderr)
        for md, token in broken:
            print(f"  {md}: `{token}`", file=sys.stderr)
        rc = 1
    else:
        print("OK: all backticked internal refs resolve.")

    if args.decision_tree:
        unreachable = decision_tree_audit(repo)
        if unreachable:
            print(
                f"FAIL: {len(unreachable)} reference(s) not reachable from "
                "SKILL.md or AGENTS.md:",
                file=sys.stderr,
            )
            for ref in unreachable:
                print(f"  {ref}", file=sys.stderr)
            rc = 1
        else:
            print("OK: every references/*.md is reachable from the decision tree.")

    return rc


if __name__ == "__main__":
    sys.exit(main())
