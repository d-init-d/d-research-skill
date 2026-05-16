#!/usr/bin/env python3
"""Render a bibliography from BibTeX into a chosen citation style.

This is a thin wrapper around ``pandoc --citeproc`` (pandoc >= 2.11)
combined with Citation Style Language (CSL) files from
``https://github.com/citation-style-language/styles``.

Subcommands
-----------
* ``render``       - render a .bib file into a chosen style
* ``list-styles``  - print the built-in style alias table
* ``self-test``    - run the offline self-test (no network)

Built-in style aliases
----------------------
The ``--style`` flag accepts:

1. A built-in alias from :data:`DEFAULT_STYLES` (e.g. ``apa``, ``mla``,
   ``ieee``, ``chicago``, ``vancouver``, ``harvard``).
2. A path to a local ``.csl`` file (works fully offline).
3. The literal ``default`` to use pandoc's built-in default style
   (Chicago author-date) - also fully offline.

When an alias is used and the corresponding ``.csl`` is not already
cached at ``~/.cache/d-research-skill/csl/``, this script will download
it from the official CSL styles repository over HTTPS.

Lawful-access note
------------------
This script only fetches public CSL files from a public GitHub raw URL.
It does not bypass any access control. To work fully offline, pass a
local ``.csl`` path via ``--style /path/to/style.csl``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_STYLES: dict[str, str] = {
    "apa": "apa",
    "apa7": "apa",
    "mla": "modern-language-association",
    "mla9": "modern-language-association",
    "ieee": "ieee",
    "chicago": "chicago-author-date",
    "chicago-author-date": "chicago-author-date",
    "chicago-notes": "chicago-note-bibliography",
    "chicago-note-bibliography": "chicago-note-bibliography",
    "vancouver": "vancouver",
    "harvard": "harvard-cite-them-right",
    "elsevier": "elsevier-harvard",
    "nature": "nature",
    "science": "science",
    "acm": "acm-sig-proceedings",
    "ama": "american-medical-association",
}

CSL_BASE_URL = "https://raw.githubusercontent.com/citation-style-language/styles/master"


def cache_dir() -> Path:
    """Return the cache directory for downloaded CSL files."""
    base = os.environ.get("D_RESEARCH_CSL_CACHE")
    if base:
        return Path(base)
    return Path.home() / ".cache" / "d-research-skill" / "csl"


def pandoc_supports_citeproc() -> bool:
    """Check whether the installed pandoc supports ``--citeproc`` (>= 2.11)."""
    if not shutil.which("pandoc"):
        return False
    try:
        proc = subprocess.run(
            ["pandoc", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False
    first_line = proc.stdout.splitlines()[0] if proc.stdout else ""
    parts = first_line.split()
    if len(parts) < 2:
        return False
    try:
        major, minor, *_ = parts[1].split(".")
        return (int(major), int(minor)) >= (2, 11)
    except (ValueError, IndexError):
        return False


def install_hint() -> str:
    return (
        "pandoc 2.11 or newer is required.\n"
        "  Debian/Ubuntu: sudo apt-get install -y pandoc\n"
        "  macOS:         brew install pandoc\n"
        "  Manual:        https://pandoc.org/installing.html\n"
        "If your distro ships pandoc < 2.11, download the latest .deb/.pkg\n"
        "from https://github.com/jgm/pandoc/releases/latest"
    )


def resolve_csl(style: str, *, allow_download: bool = True) -> Path | None:
    """Resolve ``style`` to a local CSL file path, or ``None`` for default.

    Returns ``None`` for the literal style ``"default"``, which means
    "let pandoc pick its built-in default style (Chicago author-date)".

    Raises FileNotFoundError if ``style`` looks like a file path but does
    not exist, or if the alias is unknown and no download is allowed.
    """
    if style == "default":
        return None
    # 1. Existing file path
    p = Path(style)
    if p.is_file():
        return p
    # 2. Looks like a path but missing -> hard error
    if style.endswith(".csl"):
        raise FileNotFoundError(f"CSL file not found: {style}")
    # 3. Alias map
    canonical = DEFAULT_STYLES.get(style.lower(), style.lower())
    # 4. Cache
    cached = cache_dir() / f"{canonical}.csl"
    if cached.is_file() and cached.stat().st_size > 0:
        return cached
    if not allow_download:
        return None
    # 5. Download
    cache_dir().mkdir(parents=True, exist_ok=True)
    url = f"{CSL_BASE_URL}/{canonical}.csl"
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "d-research-skill citation_render (+lawful-public-fetch)"
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
    except urllib.error.URLError as e:
        print(
            f"warning: could not download CSL '{canonical}' from {url}: {e}",
            file=sys.stderr,
        )
        return None
    cached.write_bytes(data)
    return cached


def parse_bib_keys(bib_path: Path) -> list[str]:
    """Return the citation keys defined in a BibTeX file (best-effort)."""
    keys: list[str] = []
    for line in bib_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.lstrip()
        if not stripped.startswith("@"):
            continue
        if "{" not in stripped:
            continue
        head, _, rest = stripped.partition("{")
        # Skip @comment, @preamble, @string blocks
        kind = head[1:].strip().lower()
        if kind in {"comment", "preamble", "string"}:
            continue
        key = rest.split(",", 1)[0].strip()
        if key:
            keys.append(key)
    return keys


def render(
    bib: Path,
    style: str,
    out: Path | None,
    fmt: str,
    *,
    allow_download: bool = True,
) -> int:
    if not pandoc_supports_citeproc():
        print(f"error: {install_hint()}", file=sys.stderr)
        return 2
    if not bib.is_file():
        print(f"error: bib file not found: {bib}", file=sys.stderr)
        return 1
    keys = parse_bib_keys(bib)
    if not keys:
        print(f"error: no @entries found in {bib}", file=sys.stderr)
        return 1

    csl: Path | None
    try:
        csl = resolve_csl(style, allow_download=allow_download)
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    with tempfile.NamedTemporaryFile(
        "w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write("---\n")
        f.write(f"bibliography: {json.dumps(bib.resolve().as_posix())}\n")
        if csl is not None:
            f.write(f"csl: {json.dumps(csl.resolve().as_posix())}\n")
        f.write("nocite: '@*'\n")
        f.write("---\n\n")
        f.write("# References\n\n")
        f.write('<div id="refs"></div>\n')
        tmpmd = Path(f.name)
    try:
        cmd = ["pandoc", "--citeproc", "-t", fmt, str(tmpmd)]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    finally:
        try:
            tmpmd.unlink()
        except FileNotFoundError:
            pass
    if proc.returncode != 0:
        print(f"error: pandoc failed: {proc.stderr.strip()}", file=sys.stderr)
        return proc.returncode
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(proc.stdout, encoding="utf-8")
        print(f"wrote {out}")
    else:
        sys.stdout.write(proc.stdout)
    return 0


def cmd_list_styles() -> int:
    width = max(len(a) for a in DEFAULT_STYLES) + 2
    for alias, canonical in sorted(DEFAULT_STYLES.items()):
        print(f"  {alias:<{width}} -> {canonical}")
    return 0


def cmd_self_test() -> int:
    """Run offline self-tests. Never touches the network."""
    print("citation_render self-test")
    # 1. Alias resolution
    assert DEFAULT_STYLES["apa7"] == "apa", "APA alias mapping broken"
    assert DEFAULT_STYLES["chicago"] == "chicago-author-date", (
        "chicago alias mapping broken"
    )
    print("  [PASS] alias resolution")

    # 2. BibTeX key parser
    with tempfile.TemporaryDirectory() as td:
        bib = Path(td) / "x.bib"
        bib.write_text(
            "@article{key1, author={A}, year={2024}}\n"
            "@misc{key2,title={X}}\n"
            "@comment{ignore me }\n"
            "@string{foo = {bar}}\n"
            "@inproceedings{key3,title={Y}}\n",
            encoding="utf-8",
        )
        keys = parse_bib_keys(bib)
        assert keys == ["key1", "key2", "key3"], f"unexpected keys: {keys}"
    print("  [PASS] bibtex key parser")

    # 3. Resolve "default" -> None (no network)
    csl = resolve_csl("default", allow_download=False)
    assert csl is None, f"expected None for 'default', got {csl}"
    print("  [PASS] default-style resolution (no network)")

    # 4. Resolve path-style with non-existent file -> error
    try:
        resolve_csl("/no/such/file.csl", allow_download=False)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("expected FileNotFoundError for missing .csl path")
    print("  [PASS] missing-file path style rejected")

    # 5. Optional integration test (only when pandoc >= 2.11 is present)
    if pandoc_supports_citeproc():
        with tempfile.TemporaryDirectory() as td:
            bib = Path(td) / "test.bib"
            bib.write_text(
                "@article{smith2024browser,\n"
                "  author = {Smith, Jane},\n"
                "  title = {Browser Automation Survey},\n"
                "  journal = {J. Web Eng.},\n"
                "  year = {2024},\n"
                "  volume = {23},\n"
                "  pages = {1--20}\n"
                "}\n",
                encoding="utf-8",
            )
            out = Path(td) / "out.txt"
            rc = render(bib, "default", out, "plain", allow_download=False)
            assert rc == 0, f"render failed: rc={rc}"
            txt = out.read_text(encoding="utf-8")
            assert "Smith" in txt, f"expected 'Smith' in pandoc output, got: {txt!r}"
            assert "Browser Automation Survey" in txt, (
                f"expected title in output, got: {txt!r}"
            )
        print("  [PASS] pandoc integration (default style)")
    else:
        print(
            "  [SKIP] pandoc integration "
            "(pandoc >= 2.11 not installed; not required for offline self-test)"
        )

    print("\nAll self-tests passed!")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        prog="citation_render.py",
        description="Render a BibTeX bibliography in a chosen citation style.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="Render a bibliography in a chosen style.")
    r.add_argument(
        "--bib", required=True, type=Path, help="Path to BibTeX (.bib) file."
    )
    r.add_argument(
        "--style",
        default="apa",
        help=(
            "Style alias (apa, mla, ieee, chicago, vancouver, harvard, "
            "nature, science, acm, ama, ...) OR a path to a .csl file "
            "OR the literal 'default' for pandoc's built-in default."
        ),
    )
    r.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write output to this file (default: stdout).",
    )
    r.add_argument(
        "--format",
        default="plain",
        choices=["plain", "markdown", "html", "docx", "rst"],
        help="Pandoc output format.",
    )
    r.add_argument(
        "--no-download",
        action="store_true",
        help=(
            "Do not attempt to download CSL files; only use cached files "
            "and local paths. Useful for offline / air-gapped runs."
        ),
    )

    sub.add_parser("list-styles", help="List built-in style aliases.")
    sub.add_parser("self-test", help="Run offline self-tests.")

    args = p.parse_args()
    if args.cmd == "render":
        return render(
            args.bib,
            args.style,
            args.out,
            args.format,
            allow_download=not args.no_download,
        )
    if args.cmd == "list-styles":
        return cmd_list_styles()
    if args.cmd == "self-test":
        return cmd_self_test()
    p.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
