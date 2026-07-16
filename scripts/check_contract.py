#!/usr/bin/env python3
"""Machine-readable contract checks for D Research package metadata.

Fails non-zero on:
* control characters or malformed line endings
* broken route/reference paths
* missing required backticked references
* standard gate contract drift
* unsafe public config values
* version mismatch across package metadata and release docs
* drift between declared and CI-installed toolchain pins
* stale/missing route or repository contract manifest
* repository file-count, path, and CLI-contract drift
* SKILL.md outside 250-350 lines
* invalid examples or required fixtures
* oversized reference files or missing navigation on long references
* stable promotion without either complete live evidence or an explicitly
  scoped, hash-bound maintainer override

Self-test includes isolated negative fixtures.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parent.parent

# Control chars forbidden in text files (TAB and LF allowed; CR only as CRLF).
_FORBIDDEN_CTRL = set(range(0x00, 0x09)) | {0x0B, 0x0C} | set(range(0x0E, 0x20)) | {0x7F}

_TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".json",
    ".yml",
    ".yaml",
    ".py",
    ".mjs",
    ".js",
    ".csv",
    ".toml",
    ".bib",
    ".html",
    ".css",
    ".xml",
    ".svg",
}

_SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".ruff_cache",
}

_SKILL_LINE_MIN = 250
_SKILL_LINE_MAX = 350
_REFERENCE_LINE_MAX = 1000
_REFERENCE_TOC_MIN = 100
_REFERENCE_SEE_ALSO_MIN = 300
_PACKAGE_VERSION_RE = re.compile(r"\d+\.\d+\.\d+(?:-rc\.\d+)?")
_FULL_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")

_MAINTAINER_OVERRIDE_WAIVERS = (
    "github_verified_candidate_tag",
    "github_verified_release_tag",
    "independent_reviewer",
    "live_dogfood",
)

_WINDOWS_DEVICE_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def _canonical_repo_relative(value: object) -> str | None:
    """Return one portable POSIX repository path, or ``None`` if unsafe."""

    if not isinstance(value, str) or not value or value != value.strip():
        return None
    if (
        "\\" in value
        or value.startswith("/")
        or re.match(r"^[A-Za-z]:", value)
        or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value)
    ):
        return None
    parts = value.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        return None
    for part in parts:
        if ":" in part or part.endswith((".", " ")):
            return None
        if part.split(".", 1)[0].upper() in _WINDOWS_DEVICE_NAMES:
            return None
    return "/".join(parts)

# Paths allowed to change between a dogfooded RC commit and the stable tag.
# Keep in sync with .github/workflows/release-source-archive.yml (which must
# call validate_post_rc_changed_paths rather than re-encoding the allowlist).
_STABLE_PROMOTION_EXACT_FILES = frozenset(
    {
        "package.json",
        "package-lock.json",
        "pyproject.toml",
        "CHANGELOG.md",
        "README.md",
        "README.vi.md",
    }
)


def is_allowed_post_rc_change(path: str, release_version: str) -> bool:
    """Return True when *path* may differ between dogfooded RC and stable."""
    if not isinstance(path, str) or not path.strip():
        return False
    if not isinstance(release_version, str) or not _PACKAGE_VERSION_RE.fullmatch(release_version):
        return False
    if "-rc." in release_version:
        return False
    norm = _canonical_repo_relative(path)
    if norm is None:
        return False
    if norm in _STABLE_PROMOTION_EXACT_FILES:
        return True
    if norm == f"docs/release-v{release_version}.md":
        return True
    evidence_prefix = f"release-evidence/v{release_version}/"
    if norm.startswith(evidence_prefix) and len(norm) > len(evidence_prefix):
        return True
    return False


def validate_post_rc_changed_paths(
    changed_paths: list[str] | tuple[str, ...],
    release_version: str,
) -> list[str]:
    """Reject post-RC changes outside the stable-promotion allowlist."""
    errors: list[str] = []
    if not isinstance(release_version, str) or not _PACKAGE_VERSION_RE.fullmatch(release_version):
        return [f"invalid stable release version for post-RC check: {release_version!r}"]
    if "-rc." in release_version:
        return [f"post-RC allowlist only applies to stable versions, got {release_version!r}"]
    for raw in changed_paths:
        path = str(raw).replace("\\", "/").strip()
        if not path:
            continue
        if not is_allowed_post_rc_change(path, release_version):
            errors.append(f"non-promotion change after dogfooded RC: {path}")
    return errors


def _strict_json_bytes(raw: bytes, label: str) -> dict:
    """Decode one JSON object while rejecting duplicate keys."""

    def no_duplicates(pairs: list[tuple[str, object]]) -> dict:
        result: dict = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{label} contains duplicate key {key!r}")
            result[key] = value
        return result

    def no_nonfinite(value: str) -> None:
        raise ValueError(f"{label} contains non-finite JSON number {value!r}")

    value = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=no_duplicates,
        parse_constant=no_nonfinite,
    )
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _load_strict_json(path: Path, label: str) -> dict:
    """Load one hash-sensitive JSON object with an unambiguous interpretation."""
    return _strict_json_bytes(path.read_bytes(), label)


def _normalized_pyproject_for_promotion(
    raw: bytes,
    *,
    expected_version: str,
    stable: bool,
) -> str:
    """Normalize only the two pyproject fields permitted at promotion."""
    text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    section = None
    version_matches: list[re.Match[str]] = []
    for match in re.finditer(
        r"(?m)^(?P<section>\[[^\]\n]+\])\s*$|^(?P<version>\s*version\s*=\s*\"(?P<version_value>[^\"]+)\"\s*)$",
        text,
    ):
        if match.group("section"):
            section = match.group("section")
        elif match.group("version") and section == "[project]":
            version_matches.append(match)
    if len(version_matches) != 1:
        raise ValueError("pyproject.toml must contain exactly one [project].version")
    version_match = version_matches[0]
    found_version = version_match.group("version_value")
    if _normalize_version(found_version) != _normalize_version(expected_version):
        raise ValueError(
            f"pyproject.toml project.version {found_version!r} does not match {expected_version!r}"
        )

    beta = "Development Status :: 4 - Beta"
    production = "Development Status :: 5 - Production/Stable"
    required = production if stable else beta
    forbidden = beta if stable else production
    if text.count(required) != 1 or forbidden in text:
        state = "Production/Stable" if stable else "Beta"
        raise ValueError(f"pyproject.toml must contain exactly the {state} classifier")
    normalized = (
        text[: version_match.start("version_value")]
        + "__PROMOTION_VERSION__"
        + text[version_match.end("version_value") :]
    )
    return normalized.replace(required, "__PROMOTION_STATUS__", 1)


def validate_post_rc_metadata(
    candidate_contents: dict[str, bytes],
    release_root: Path,
    release_version: str,
) -> list[str]:
    """Permit only semantic RC-to-stable metadata transformations.

    JavaScript lifecycle scripts, dependencies, the npm lock graph, Python
    dependencies, and build-system configuration are executable supply-chain
    inputs and therefore remain frozen at the dogfooded RC.
    """
    if not _PACKAGE_VERSION_RE.fullmatch(release_version) or "-rc." in release_version:
        return [f"post-RC metadata check requires a stable X.Y.Z version, got {release_version!r}"]
    required = ("package.json", "package-lock.json", "pyproject.toml")
    errors: list[str] = []
    missing = [name for name in required if name not in candidate_contents]
    if missing:
        return [f"candidate metadata is missing: {', '.join(missing)}"]
    try:
        candidate_package = _strict_json_bytes(candidate_contents["package.json"], "RC package.json")
        release_package = _strict_json_bytes(
            (release_root / "package.json").read_bytes(), "stable package.json"
        )
        candidate_lock = _strict_json_bytes(
            candidate_contents["package-lock.json"], "RC package-lock.json"
        )
        release_lock = _strict_json_bytes(
            (release_root / "package-lock.json").read_bytes(), "stable package-lock.json"
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"post-RC metadata is unreadable: {exc}"]

    candidate_version = candidate_package.get("version")
    if not isinstance(candidate_version, str) or not re.fullmatch(
        re.escape(release_version) + r"-rc\.\d+", candidate_version
    ):
        errors.append(
            "RC package.json version must be a prerelease of the stable release line"
        )
    if release_package.get("version") != release_version:
        errors.append("stable package.json version does not match --release-version")
    candidate_package["version"] = "__PROMOTION_VERSION__"
    release_package["version"] = "__PROMOTION_VERSION__"
    if candidate_package != release_package:
        errors.append(
            "package.json changed beyond version; scripts, dependencies, engines, and metadata are frozen"
        )

    def normalize_lock(lock: dict, expected: str, label: str) -> None:
        if lock.get("version") != expected:
            errors.append(f"{label} top-level version does not match its package version")
        packages = lock.get("packages")
        if not isinstance(packages, dict) or not isinstance(packages.get(""), dict):
            errors.append(f"{label} must contain packages['']")
            return
        if packages[""].get("version") != expected:
            errors.append(f"{label} packages[''].version does not match its package version")
        lock["version"] = "__PROMOTION_VERSION__"
        packages[""]["version"] = "__PROMOTION_VERSION__"

    if isinstance(candidate_version, str):
        normalize_lock(candidate_lock, candidate_version, "RC package-lock.json")
    normalize_lock(release_lock, release_version, "stable package-lock.json")
    if candidate_lock != release_lock:
        errors.append(
            "package-lock.json changed beyond root version; dependency and lock graph are frozen"
        )

    try:
        candidate_pyproject = _normalized_pyproject_for_promotion(
            candidate_contents["pyproject.toml"],
            expected_version=str(candidate_version),
            stable=False,
        )
        release_pyproject = _normalized_pyproject_for_promotion(
            (release_root / "pyproject.toml").read_bytes(),
            expected_version=release_version,
            stable=True,
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        errors.append(f"pyproject.toml promotion metadata invalid: {exc}")
    else:
        if candidate_pyproject != release_pyproject:
            errors.append(
                "pyproject.toml changed beyond version and Beta-to-Production classifier; "
                "dependencies and build-system are frozen"
            )
    return errors


def _git_candidate_metadata(root: Path, candidate_ref: str) -> dict[str, bytes]:
    """Read frozen metadata blobs from an already-fetched candidate ref."""
    if not candidate_ref or candidate_ref.startswith("-"):
        raise ValueError("candidate ref must be non-empty and must not start with '-'")
    result: dict[str, bytes] = {}
    for path in ("package.json", "package-lock.json", "pyproject.toml"):
        completed = subprocess.run(
            ["git", "show", f"{candidate_ref}:{path}"],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise ValueError(f"cannot read {path} from candidate ref {candidate_ref!r}: {detail}")
        result[path] = completed.stdout
    return result


def _load_json(path: Path):
    """Load repository JSON with the same unambiguous rules as release evidence."""
    return _load_strict_json(path, path.as_posix())


def _scan_text_for_controls(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    i = 0
    while i < len(text):
        o = ord(text[i])
        if o == 0x0D:
            if i + 1 < len(text) and text[i + 1] == "\n":
                i += 2
                continue
            errors.append(f"{path}: bare CR at offset {i}")
            break
        if o in _FORBIDDEN_CTRL:
            errors.append(f"{path}: forbidden control U+{o:04X} at offset {i}")
            break
        i += 1
    # doubled CR
    if "\r\r" in text:
        errors.append(f"{path}: doubled CR sequences")
    return errors


def scan_repo_controls(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for dirpath, dirnames, filenames in root.walk() if hasattr(Path, "walk") else []:
        pass  # pathlib.walk is 3.12+
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in _TEXT_SUFFIXES and path.name not in {
            "LICENSE",
            "AGENTS.md",
            "README",
            "CHANGELOG",
        }:
            # still scan extensionless known names
            if path.suffix:
                continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:2048]:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        errors.extend(_scan_text_for_controls(path.relative_to(root), text))
    return errors


def _normalize_version(v: str) -> str:
    return v.replace("-rc.", "rc").replace("-rc", "rc").strip()


def check_ruff_pin_sync(root: Path = ROOT) -> list[str]:
    """Require the declared Ruff version to match the version installed by CI."""

    errors: list[str] = []
    pyproject_path = root / "pyproject.toml"
    workflow_path = root / ".github" / "workflows" / "lint-and-self-test.yml"

    if not pyproject_path.is_file():
        errors.append("missing pyproject.toml for Ruff pin validation")
        return errors
    if not workflow_path.is_file():
        errors.append("missing lint-and-self-test workflow for Ruff pin validation")
        return errors

    pyproject_text = pyproject_path.read_text(encoding="utf-8")
    workflow_text = workflow_path.read_text(encoding="utf-8")
    pyproject_pins = set(re.findall(r'"ruff==(\d+\.\d+\.\d+)"', pyproject_text))
    workflow_pins = set(re.findall(r'ruff==(\d+\.\d+\.\d+)', workflow_text))

    if len(pyproject_pins) != 1:
        errors.append("pyproject.toml must declare exactly one exact Ruff pin")
    if len(workflow_pins) != 1:
        errors.append("lint-and-self-test workflow must install exactly one Ruff version")
    if len(pyproject_pins) == 1 and len(workflow_pins) == 1:
        declared = next(iter(pyproject_pins))
        installed = next(iter(workflow_pins))
        if declared != installed:
            errors.append(
                "Ruff pin mismatch: "
                f"pyproject.toml={declared!r}, lint-and-self-test.yml={installed!r}"
            )
    return errors


def check_workflow_security(root: Path = ROOT) -> list[str]:
    """Require exact-SHA CI checkouts and an isolated release attestation boundary."""

    errors: list[str] = []
    ci_path = root / ".github" / "workflows" / "lint-and-self-test.yml"
    source_path = root / ".github" / "workflows" / "release-source-archive.yml"
    attest_path = root / ".github" / "workflows" / "release-attest.yml"

    if not ci_path.is_file():
        errors.append("missing lint-and-self-test workflow for exact-SHA validation")
    else:
        ci_text = ci_path.read_text(encoding="utf-8")
        checkout_count = ci_text.count("uses: actions/checkout@")
        exact_ref = (
            "github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha"
        )
        if checkout_count < 1:
            errors.append("lint-and-self-test workflow must check out the tested commit")
        if ci_text.count("persist-credentials: false") != checkout_count:
            errors.append("every lint-and-self-test checkout must disable credential persistence")
        if ci_text.count("name: Assert exact event commit checkout") != checkout_count:
            errors.append("every lint-and-self-test checkout must assert its exact event commit")
        if ci_text.count(f"ref: ${{{{ {exact_ref} }}}}") != checkout_count:
            errors.append("every lint-and-self-test checkout must select the exact PR head SHA")
        if ci_text.count(f"EXPECTED_SHA: ${{{{ {exact_ref} }}}}") != checkout_count:
            errors.append("every lint-and-self-test assertion must bind the exact PR head SHA")

    if not source_path.is_file():
        errors.append("missing unprivileged release source workflow")
    else:
        source_text = source_path.read_text(encoding="utf-8")
        checkout_count = source_text.count("uses: actions/checkout@")
        if checkout_count < 1:
            errors.append("release source workflow must check out the tagged commit")
        if source_text.count("persist-credentials: false") != checkout_count:
            errors.append("every release source checkout must disable credential persistence")
        if source_text.count("ref: ${{ github.sha }}") != checkout_count:
            errors.append("every release source checkout must select github.sha explicitly")
        if source_text.count('actual_sha="$(git rev-parse HEAD)"') != checkout_count:
            errors.append("every release source checkout must assert its exact commit")
        for forbidden in (
            "attestations: write",
            "id-token: write",
            "actions/attest-build-provenance@",
        ):
            if forbidden in source_text:
                errors.append(
                    "release source workflow must remain unprivileged; "
                    f"found forbidden marker: {forbidden}"
                )
        for marker in (
            "release-artifact.json",
            '"workflow_run_id"',
            '"workflow_run_attempt"',
            '"release_tag_object"',
            '"archive_sha256"',
        ):
            if marker not in source_text:
                errors.append(f"release source workflow missing artifact binding marker: {marker}")

    if not attest_path.is_file():
        errors.append("missing default-branch release attestation workflow")
    else:
        attest_text = attest_path.read_text(encoding="utf-8")
        header, separator, jobs_text = attest_text.partition("\njobs:\n")
        if not separator:
            errors.append("release attestation workflow has no jobs section")
            jobs_text = attest_text
        if "workflow_run:" not in header or "permissions: {}" not in header:
            errors.append(
                "release attestation workflow must use workflow_run with empty default permissions"
            )
        if attest_text.count('"$GITHUB_EVENT_PATH"') != 2:
            errors.append(
                "release attestation workflow must read the webhook from "
                "GITHUB_EVENT_PATH in both validation stages"
            )
        if "github.event_path" in attest_text or re.search(
            r"(?m)^\s+EVENT_PATH:\s*", attest_text
        ):
            errors.append(
                "release attestation workflow must not derive an EVENT_PATH alias"
            )
        verify_text, attest_separator, privileged_text = jobs_text.partition("\n  attest:\n")
        if not attest_separator:
            errors.append("release attestation workflow has no isolated attest job")
            privileged_text = ""
        for forbidden in ("attestations: write", "id-token: write"):
            if forbidden in verify_text:
                errors.append(
                    "release attestation verification job must remain unprivileged; "
                    f"found {forbidden}"
                )
        if privileged_text:
            if re.search(r"(?m)^\s+(?:run|shell):", privileged_text):
                errors.append("privileged release attest job must not contain shell or run steps")
            if "uses: actions/checkout@" in privileged_text:
                errors.append("privileged release attest job must not check out repository code")
            if (
                "attestations: write" not in privileged_text
                or "id-token: write" not in privileged_text
            ):
                errors.append(
                    "privileged release attest job is missing required narrow permissions"
                )
            privileged_uses = re.findall(r"(?m)^\s+uses:\s*(\S+)", privileged_text)
            expected_uses = {
                "actions/download-artifact@fa0a91b85d4f404e444e00e005971372dc801d16",
                "actions/attest-build-provenance@0f67c3f4856b2e3261c31976d6725780e5e4c373",
            }
            if set(privileged_uses) != expected_uses or len(privileged_uses) != 2:
                errors.append(
                    "privileged release attest job may use only pinned download and attest actions"
                )
        for marker in (
            "workflows: [release-source-archive]",
            "github.event.workflow_run.conclusion == 'success'",
            'expected_path = ".github/workflows/release-source-archive.yml"',
            "workflow_run.head_sha",
            "release-artifact.json",
            "/git/ref/tags/${RELEASE_TAG}",
            "/git/tags/${RELEASE_TAG_OBJECT}",
            'verification.get("verified") is not True',
            "git -C source archive",
            "cmp --silent",
            "verified-source-archive-",
            "actions/attest-build-provenance@",
        ):
            if marker not in attest_text:
                errors.append(f"release attestation workflow missing trust marker: {marker}")
    return errors


def check_versions(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    pkg = _load_json(root / "package.json")
    pkg_version = str(pkg.get("version", ""))
    if not pkg_version:
        errors.append("package.json missing version")
    elif not _PACKAGE_VERSION_RE.fullmatch(pkg_version):
        errors.append(f"package.json version must be X.Y.Z or X.Y.Z-rc.N, got {pkg_version!r}")

    lock = _load_json(root / "package-lock.json")
    lock_version = str(lock.get("version", ""))
    packages = lock.get("packages") or {}
    root_pkg = packages.get("") or {}
    lock_root_version = str(root_pkg.get("version", lock_version))
    for label, ver in (
        ("package-lock.json version", lock_version),
        ("package-lock packages[''].version", lock_root_version),
    ):
        if not ver:
            errors.append(f"{label} missing version")
        elif _normalize_version(ver) != _normalize_version(pkg_version):
            errors.append(f"version mismatch package.json={pkg_version!r} {label}={ver!r}")

    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
    if not m:
        errors.append("pyproject.toml missing version")
    elif _normalize_version(m.group(1)) != _normalize_version(pkg_version):
        errors.append(f"version mismatch package.json={pkg_version!r} pyproject={m.group(1)!r}")

    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    escaped_version = re.escape(pkg_version)
    if not re.search(
        rf"^## \[{escaped_version}\] - \d{{4}}-\d{{2}}-\d{{2}}$",
        changelog,
        re.M,
    ):
        errors.append(f"CHANGELOG.md missing dated release heading for {pkg_version}")
    repository_url = "https://github.com/d-init-d/d-research-skill"
    expected_unreleased = f"[Unreleased]: {repository_url}/compare/v{pkg_version}...HEAD"
    expected_release_link = f"[{pkg_version}]: {repository_url}/releases/tag/v{pkg_version}"
    if expected_unreleased not in changelog:
        errors.append(
            f"CHANGELOG.md Unreleased comparison must start at current version: v{pkg_version}"
        )
    if expected_release_link not in changelog:
        errors.append(f"CHANGELOG.md missing release link definition for {pkg_version}")

    release = root / "docs" / f"release-v{pkg_version}.md"
    if not release.is_file():
        errors.append(f"missing docs/release-v{pkg_version}.md")
    else:
        body = release.read_text(encoding="utf-8")
        for marker in (
            f"# D Research v{pkg_version}",
            f"## v{pkg_version} Release Notes",
        ):
            if marker not in body:
                errors.append(f"release notes for {pkg_version} missing marker: {marker}")

    for readme_name in ("README.md", "README.vi.md"):
        readme = root / readme_name
        if not readme.is_file():
            errors.append(f"missing {readme_name}")
        elif f"v{pkg_version}" not in readme.read_text(encoding="utf-8"):
            errors.append(f"{readme_name} must mention current version v{pkg_version}")

    is_prerelease = "-rc." in pkg_version
    beta_classifier = "Development Status :: 4 - Beta"
    stable_classifier = "Development Status :: 5 - Production/Stable"
    if is_prerelease:
        if beta_classifier not in pyproject:
            errors.append("prerelease pyproject must use the Beta classifier")
        if stable_classifier in pyproject:
            errors.append("prerelease pyproject must not claim Production/Stable")
    else:
        if stable_classifier not in pyproject:
            errors.append("stable pyproject must use the Production/Stable classifier")
        if beta_classifier in pyproject:
            errors.append("stable pyproject must not retain the Beta classifier")

    playwright_version = str((pkg.get("dependencies") or {}).get("playwright", ""))
    if not re.fullmatch(r"\d+\.\d+\.\d+", playwright_version):
        errors.append("package.json must pin Playwright to an exact stable X.Y.Z version")
    lock_playwright_declared = str((root_pkg.get("dependencies") or {}).get("playwright", ""))
    lock_playwright_package = str(
        (packages.get("node_modules/playwright") or {}).get("version", "")
    )
    for label, value in (
        ("package-lock root Playwright", lock_playwright_declared),
        ("package-lock installed Playwright", lock_playwright_package),
    ):
        if value != playwright_version:
            errors.append(f"{label} mismatch: package={playwright_version!r}, lock={value!r}")

    engines = pkg.get("engines") or {}
    if engines.get("node") != ">=18":
        errors.append('package.json engines.node must be ">=18"')

    expected_package_files = {
        "SKILL.md",
        "AGENTS.md",
        "README.md",
        "README.vi.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "adapters/*.md",
        "agents/*.yaml",
        "docs/**/*.md",
        "examples/**/*",
        "!examples/**/__pycache__/**",
        "!examples/**/*.pyc",
        "!examples/**/*.pyo",
        "!examples/**/*.pyd",
        "references/**/*.md",
        "references/i18n/*.json",
        "scripts/*.py",
        "scripts/*.mjs",
        "scripts/lib/*.mjs",
        "templates/*",
        "pyproject.toml",
        "research.config.example.json",
    }
    package_files = pkg.get("files")
    if not isinstance(package_files, list) or set(package_files) != expected_package_files:
        errors.append("package.json files must match the canonical publish allowlist")
    scripts = pkg.get("scripts") or {}
    if scripts.get("package:check") != "node scripts/package_manifest_check.mjs":
        errors.append("package.json package:check must run package_manifest_check.mjs")
    if scripts.get("prepack") != "npm run package:check":
        errors.append("package.json prepack must enforce npm run package:check")
    if "npm run package:check" not in str(scripts.get("self-test:node", "")):
        errors.append("package manifest validation must be part of self-test:node")
    package_manifest = pkg.get("dResearchPackageManifest")
    if not isinstance(package_manifest, dict):
        errors.append("package.json missing dResearchPackageManifest")
    else:
        if package_manifest.get("schema_version") != 1:
            errors.append("dResearchPackageManifest.schema_version must be 1")
        if package_manifest.get("algorithm") != "sha256":
            errors.append('dResearchPackageManifest.algorithm must be "sha256"')
        file_count = package_manifest.get("file_count")
        if isinstance(file_count, bool) or not isinstance(file_count, int) or file_count < 1:
            errors.append("dResearchPackageManifest.file_count must be a positive integer")
        if not re.fullmatch(
            r"sha256:[0-9a-f]{64}", str(package_manifest.get("paths_sha256") or "")
        ):
            errors.append(
                "dResearchPackageManifest.paths_sha256 must be sha256:<64 lowercase hex>"
            )
    npmignore_path = root / ".npmignore"
    if not npmignore_path.is_file():
        errors.append("missing .npmignore defense-in-depth exclusions")
    else:
        npmignore = npmignore_path.read_text(encoding="utf-8")
        for required_pattern in ("__pycache__/", "*.pyc", "*.pyo", "*.pyd"):
            if required_pattern not in npmignore.splitlines():
                errors.append(
                    f".npmignore missing generated-file exclusion {required_pattern!r}"
                )
    return errors


def _parse_rfc3339(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None


def _first_reparse_component(root: Path, relative: Path) -> Path | None:
    """Return the first lexical symlink/reparse component without resolving it."""
    current = root
    for part in relative.parts:
        current = current / part
        try:
            stat_result = current.lstat()
        except OSError:
            continue
        if current.is_symlink() or bool(
            getattr(stat_result, "st_file_attributes", 0) & 0x400
        ):
            return current
    return None


def _resolve_repo_file(
    root: Path,
    value: object,
    label: str,
    errors: list[str],
    *,
    contained_by: Path | None = None,
) -> Path | None:
    canonical = _canonical_repo_relative(value)
    if canonical is None:
        errors.append(f"{label} must be a non-empty repository-relative path")
        return None
    relative = Path(*canonical.split("/"))
    hostile_component = _first_reparse_component(root, relative)
    if hostile_component is not None:
        errors.append(
            f"{label} contains a symlink or reparse point: "
            f"{hostile_component.relative_to(root)}"
        )
        return None
    resolved_root = root.resolve()
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        errors.append(f"{label} escapes the repository: {value!r}")
        return None
    if contained_by is not None:
        try:
            resolved.relative_to(contained_by.resolve())
        except ValueError:
            errors.append(f"{label} must stay inside {contained_by.relative_to(root)}")
            return None
    if not resolved.is_file():
        errors.append(f"{label} is missing: {value}")
        return None
    return resolved


def _resolve_repo_dir(
    root: Path,
    value: object,
    label: str,
    errors: list[str],
    *,
    contained_by: Path | None = None,
) -> Path | None:
    """Resolve one existing repository directory with containment checks."""
    canonical = _canonical_repo_relative(value)
    if canonical is None:
        errors.append(f"{label} must be a non-empty repository-relative path")
        return None
    relative = Path(*canonical.split("/"))
    hostile_component = _first_reparse_component(root, relative)
    if hostile_component is not None:
        errors.append(
            f"{label} contains a symlink or reparse point: "
            f"{hostile_component.relative_to(root)}"
        )
        return None
    resolved_root = root.resolve()
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        errors.append(f"{label} escapes the repository: {value!r}")
        return None
    if contained_by is not None:
        try:
            resolved.relative_to(contained_by.resolve())
        except ValueError:
            errors.append(f"{label} must stay inside {contained_by.relative_to(root)}")
            return None
    if not resolved.is_dir():
        errors.append(f"{label} is missing: {value}")
        return None
    return resolved


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _load_eval_harness(root: Path) -> ModuleType:
    harness_path = root / "scripts" / "run_dogfood.py"
    spec = importlib.util.spec_from_file_location("d_research_release_eval", harness_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load eval harness: {harness_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _score_commit(record: dict, label: str, errors: list[str]) -> str | None:
    commits = {
        str(task.get("skill_commit"))
        for task in record.get("tasks", [])
        if isinstance(task, dict) and task.get("status") != "not_run"
    }
    if len(commits) != 1:
        errors.append(f"{label} must contain exactly one skill commit, got {sorted(commits)}")
        return None
    commit = next(iter(commits))
    if not _FULL_COMMIT_RE.fullmatch(commit):
        errors.append(f"{label} skill_commit must be a full 40-character lowercase SHA")
        return None
    return commit


def _validate_live_runs(
    *,
    root: Path,
    evidence_dir: Path,
    runs_path_value: object,
    expected_runs_path: str,
    label: str,
    harness: ModuleType,
    bench: dict,
    score: dict,
    canonical_threshold: float | None,
    expected_skill_commit: str | None,
    expected_harness_commit: str | None,
    expected_version: str | None,
    generated_at: datetime | None,
    score_created_at: datetime | None,
    seen_run_ids: set[str],
    seen_session_ids: set[str],
    seen_time_pairs: set[tuple[datetime, datetime]],
    seen_run_dirs: list[Path],
    evaluator_signatures: set[str],
    evaluator_harness_commits: set[str],
) -> list[str]:
    """Recompute one score artifact from its manifest-backed raw run bundle."""
    errors: list[str] = []
    if runs_path_value != expected_runs_path:
        errors.append(f"{label} must be the canonical path {expected_runs_path!r}")
    runs_dir = _resolve_repo_dir(
        root,
        runs_path_value,
        label,
        errors,
        contained_by=evidence_dir,
    )
    if runs_dir is None:
        return errors

    for existing in seen_run_dirs:
        try:
            runs_dir.relative_to(existing)
            nested = True
        except ValueError:
            try:
                existing.relative_to(runs_dir)
                nested = True
            except ValueError:
                nested = False
        if nested:
            errors.append(f"{label} duplicates or nests another run evidence bundle")
            break
    seen_run_dirs.append(runs_dir)

    bench_tasks = {
        str(task.get("task_id")): task
        for task in bench.get("tasks", [])
        if isinstance(task, dict) and isinstance(task.get("task_id"), str)
    }
    score_tasks = {
        str(task.get("task_id")): task
        for task in score.get("tasks", [])
        if isinstance(task, dict) and isinstance(task.get("task_id"), str)
    }
    if set(score_tasks) != set(bench_tasks):
        errors.append(f"{label} cannot bind a score with incomplete task coverage")
        return errors

    if score.get("pass_threshold") != canonical_threshold:
        errors.append(
            f"{label} score pass_threshold must be frozen at {canonical_threshold!r}"
        )

    try:
        actual_children = {child.name: child for child in runs_dir.iterdir()}
    except OSError as exc:
        errors.append(f"{label} cannot enumerate run bundle: {exc}")
        return errors
    if set(actual_children) != set(bench_tasks):
        errors.append(
            f"{label} task directories must exactly match the bench; "
            f"missing={sorted(set(bench_tasks) - set(actual_children))}, "
            f"extra={sorted(set(actual_children) - set(bench_tasks))}"
        )

    template_path = root / "templates" / "evidence-ledger.csv"
    try:
        with template_path.open(newline="", encoding="utf-8") as handle:
            canonical_header = next(csv.reader(handle), None)
    except OSError as exc:
        errors.append(f"{label} cannot read canonical ledger template: {exc}")
        return errors

    bench_fingerprint = harness.bench_fingerprint(bench)
    bench_version = bench.get("bench_version")
    expected_bench_version = str(bench_version) if bench_version is not None else None
    for task_id in sorted(bench_tasks):
        task_dir = runs_dir / task_id
        if not task_dir.is_dir():
            errors.append(f"{label}.{task_id} must be a directory")
            continue
        try:
            task_entries = {entry.name: entry for entry in task_dir.iterdir()}
        except OSError as exc:
            errors.append(f"{label}.{task_id} cannot enumerate artifacts: {exc}")
            continue
        expected_artifacts = {
            "run-result.json",
            "evidence-ledger.csv",
            "raw-prompt.txt",
            "raw-output.txt",
        }
        if set(task_entries) != expected_artifacts:
            errors.append(
                f"{label}.{task_id} artifacts must be exactly "
                f"{sorted(expected_artifacts)}"
            )
        hostile_entry = next(
            (
                entry
                for entry in [task_dir, *task_entries.values()]
                if entry.is_symlink()
                or bool(getattr(entry.lstat(), "st_file_attributes", 0) & 0x400)
            ),
            None,
        )
        if hostile_entry is not None:
            errors.append(
                f"{label}.{task_id} contains a symlink or reparse point: "
                f"{hostile_entry.name}"
            )
            continue

        manifest_path = (task_dir / "run-result.json").resolve()
        try:
            manifest_path.relative_to(runs_dir.resolve())
            manifest_path.relative_to(evidence_dir.resolve())
        except ValueError:
            errors.append(f"{label}.{task_id} manifest escapes the release evidence directory")
            continue
        if not manifest_path.is_file():
            errors.append(f"{label}.{task_id} missing canonical run-result.json")
            continue
        run_result = harness.load_run_result_file(
            manifest_path,
            expected_task_id=task_id,
            runs_root=runs_dir,
            canonical_layout=True,
            expected_bench_fingerprint=bench_fingerprint,
            expected_bench_version=expected_bench_version,
        )
        if run_result.get("_manifest_valid") is not True:
            detail = run_result.get("_manifest_error") or "unknown validation error"
            errors.append(f"{label}.{task_id} invalid run evidence: {detail}")
            continue
        if run_result.get("_execution_eligible") is not True:
            errors.append(f"{label}.{task_id} is not execution-eligible")
            continue
        ledger_path = run_result.get("_ledger_path")
        if not isinstance(ledger_path, Path):
            errors.append(f"{label}.{task_id} has no validated ledger artifact")
            continue

        for key, seen in (
            ("run_id", seen_run_ids),
            ("session_id", seen_session_ids),
        ):
            value = str(run_result.get(key) or "")
            if value in seen:
                errors.append(f"{label}.{task_id} reuses global {key} {value!r}")
            seen.add(value)
        started_at = str(run_result.get("started_at") or "")
        finished_at = str(run_result.get("finished_at") or "")
        started = _parse_rfc3339(started_at)
        finished = _parse_rfc3339(finished_at)
        if started is not None and finished is not None:
            # Normalize RFC 3339 offsets before checking uniqueness so the
            # same instant cannot be disguised with a different spelling.
            time_pair = (started, finished)
            if time_pair in seen_time_pairs:
                errors.append(f"{label}.{task_id} reuses a global timestamp pair")
            seen_time_pairs.add(time_pair)
        if generated_at is not None and finished is not None and finished > generated_at:
            errors.append(f"{label}.{task_id} finishes after promotion generated_at")
        if score_created_at is not None and finished is not None and finished > score_created_at:
            errors.append(f"{label}.{task_id} finishes after score created_at")

        if (
            expected_skill_commit is not None
            and run_result.get("skill_commit") != expected_skill_commit
        ):
            errors.append(f"{label}.{task_id} skill_commit does not match its release side")
        candidate_binding = run_result.get("candidate_binding")
        if not isinstance(candidate_binding, dict) or candidate_binding.get(
            "version"
        ) != expected_version:
            errors.append(f"{label}.{task_id} candidate_binding.version mismatch")
        evaluator = run_result.get("evaluator_binding")
        if isinstance(evaluator, dict):
            evaluator_signatures.add(
                json.dumps(evaluator, sort_keys=True, separators=(",", ":"))
            )
            harness_commit = str(evaluator.get("harness_commit") or "")
            evaluator_harness_commits.add(harness_commit)
            if (
                expected_harness_commit is not None
                and harness_commit != expected_harness_commit
            ):
                errors.append(
                    f"{label}.{task_id} evaluator_binding.harness_commit must "
                    "match the frozen candidate skill commit"
                )

        try:
            expected_prompt = harness.render_task_prompt(
                bench,
                bench_tasks[task_id],
            ).encode("utf-8")
            actual_prompt = (task_dir / "raw-prompt.txt").read_bytes()
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            errors.append(f"{label}.{task_id} cannot verify canonical prompt: {exc}")
            continue
        if actual_prompt != expected_prompt:
            errors.append(f"{label}.{task_id} raw prompt is not the canonical renderer output")

        try:
            with ledger_path.open(newline="", encoding="utf-8") as handle:
                ledger_header = next(csv.reader(handle), None)
        except (OSError, UnicodeDecodeError) as exc:
            errors.append(f"{label}.{task_id} cannot read evidence ledger: {exc}")
        else:
            if ledger_header != canonical_header:
                errors.append(
                    f"{label}.{task_id} ledger must use the exact canonical 23-column header"
                )

    try:
        recomputed_record = harness.build_score_record(
            bench,
            runs_dir,
            threshold=canonical_threshold,
            frozen_timestamp=score.get("created_at"),
            canonical_layout=True,
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        errors.append(f"{label} cannot recompute score artifact: {exc}")
    else:
        if score != recomputed_record:
            errors.append(f"{label} score artifact is not the canonical raw-run recomputation")
    return errors


def check_release_tag(release_tag: str, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    match = re.fullmatch(r"v(\d+\.\d+\.\d+(?:-rc\.\d+)?)", release_tag)
    if match is None:
        return [f"release tag must be vX.Y.Z or vX.Y.Z-rc.N, got {release_tag!r}"]
    package_version = str(_load_json(root / "package.json").get("version", ""))
    if match.group(1) != package_version:
        errors.append(
            f"release tag/package mismatch: tag={match.group(1)!r}, package={package_version!r}"
        )
    return errors


def check_release_waiver(
    waiver: str,
    release_tag: str,
    root: Path = ROOT,
) -> list[str]:
    """Require one pre-authorized waiver for the current RC or stable tag."""

    errors = check_release_tag(release_tag, root)
    if errors:
        return errors
    manifest_path = root / "templates" / "route-manifest.json"
    try:
        manifest = _strict_json_bytes(manifest_path.read_bytes(), "route manifest")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"cannot validate release waiver: {exc}"]
    gate = manifest.get("stable_release_gate")
    if not isinstance(gate, dict) or gate.get("promotion_mode") != "maintainer_override":
        return ["release waiver requires promotion_mode='maintainer_override'"]
    contract = gate.get("maintainer_override")
    if not isinstance(contract, dict):
        return ["release waiver requires a maintainer_override contract"]
    if waiver not in _MAINTAINER_OVERRIDE_WAIVERS:
        return [f"release requirement is non-waivable: {waiver!r}"]
    if contract.get("required_waivers") != list(_MAINTAINER_OVERRIDE_WAIVERS):
        errors.append("release waiver set is not the canonical narrow set")
    if waiver not in (contract.get("required_waivers") or []):
        errors.append(f"release waiver is not authorized: {waiver}")
    candidate_version = gate.get("required_candidate_version")
    stable_version = contract.get("allowed_release_version")
    if candidate_version != "3.2.0-rc.3" or stable_version != "3.2.0":
        errors.append("release waiver is not scoped to the frozen v3.2.0-rc.3/v3.2.0 pair")
    if contract.get("required_repository") != "d-init-d/d-research-skill":
        errors.append("release waiver repository scope is invalid")
    if contract.get("required_maintainer_login") != "d-init-d":
        errors.append("release waiver maintainer scope is invalid")
    if release_tag not in {f"v{candidate_version}", f"v{stable_version}"}:
        errors.append("release waiver is outside its authorized RC/stable tag pair")
    non_waivable = contract.get("non_waivable")
    required_hard_gates = {
        "annotated_candidate_tag",
        "annotated_release_tag",
        "candidate_tag_object_binding",
        "candidate_ancestry",
        "exact_release_sha_ci",
        "source_archive",
        "sha256_manifest",
        "provenance_attestation",
    }
    if (
        not isinstance(non_waivable, dict)
        or set(non_waivable) != required_hard_gates
        or any(value is not True for value in non_waivable.values())
    ):
        errors.append("release waiver contract does not preserve every hard gate")
    return errors


def _check_maintainer_override(
    root: Path,
    package_version: str,
    gate: dict,
    *,
    expected_candidate_commit: str | None = None,
    expected_candidate_tag_object: str | None = None,
) -> list[str]:
    """Validate the one-release maintainer waiver without weakening hard gates."""

    errors: list[str] = []
    contract = gate.get("maintainer_override")
    if not isinstance(contract, dict):
        return ["stable_release_gate.maintainer_override must be an object"]

    expected_contract_keys = {
        "schema_version",
        "manifest_path",
        "allowed_release_version",
        "required_decision",
        "required_repository",
        "required_maintainer_login",
        "required_waivers",
        "required_checks",
        "bind_candidate_commit",
        "bind_candidate_tag_object_sha",
        "require_annotated_tags",
        "require_exact_sha_ci",
        "non_waivable",
    }
    if set(contract) != expected_contract_keys:
        errors.append(
            "stable_release_gate.maintainer_override keys must be exactly "
            f"{sorted(expected_contract_keys)}"
        )
    if contract.get("schema_version") != "1.0":
        errors.append("maintainer override contract schema_version must be '1.0'")
    if contract.get("allowed_release_version") != package_version:
        errors.append("maintainer override is not authorized for this stable version")
    if contract.get("required_decision") != "approved_with_waivers":
        errors.append("maintainer override required_decision is invalid")
    if contract.get("required_repository") != "d-init-d/d-research-skill":
        errors.append("maintainer override repository contract is invalid")
    if contract.get("required_maintainer_login") != "d-init-d":
        errors.append("maintainer override login contract is invalid")
    for field in (
        "bind_candidate_commit",
        "bind_candidate_tag_object_sha",
        "require_annotated_tags",
        "require_exact_sha_ci",
    ):
        if contract.get(field) is not True:
            errors.append(f"maintainer override contract must require {field}")
    required_non_waivable = {
        "annotated_candidate_tag",
        "annotated_release_tag",
        "candidate_tag_object_binding",
        "candidate_ancestry",
        "exact_release_sha_ci",
        "source_archive",
        "sha256_manifest",
        "provenance_attestation",
    }
    non_waivable = contract.get("non_waivable")
    if (
        not isinstance(non_waivable, dict)
        or set(non_waivable) != required_non_waivable
        or any(value is not True for value in non_waivable.values())
    ):
        errors.append(
            "maintainer override non_waivable must preserve every hard release gate"
        )

    required_waivers = contract.get("required_waivers")
    if required_waivers != list(_MAINTAINER_OVERRIDE_WAIVERS):
        errors.append(
            "maintainer override required_waivers must match the narrowly allowed waiver set"
        )
        required_waivers = list(_MAINTAINER_OVERRIDE_WAIVERS)
    required_checks = contract.get("required_checks")
    if (
        not isinstance(required_checks, list)
        or not required_checks
        or any(not isinstance(item, str) or not item for item in required_checks)
        or len(set(required_checks)) != len(required_checks)
    ):
        errors.append("maintainer override required_checks must be unique non-empty strings")
        required_checks = []

    manifest_template = contract.get("manifest_path")
    if not isinstance(manifest_template, str) or "{version}" not in manifest_template:
        errors.append("maintainer override manifest_path must contain {version}")
        return errors
    manifest_rel = manifest_template.format(version=package_version)
    manifest_path = _resolve_repo_file(
        root,
        manifest_rel,
        "maintainer override manifest",
        errors,
    )
    if manifest_path is None:
        return errors
    evidence_dir = manifest_path.parent

    try:
        override = _strict_json_bytes(
            manifest_path.read_bytes(), "maintainer override manifest"
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"maintainer override manifest is unreadable: {exc}"]

    expected_override_keys = {
        "schema_version",
        "release_version",
        "release_tag",
        "candidate_version",
        "candidate_skill_commit",
        "candidate_tag",
        "candidate_tag_object_sha",
        "repository",
        "decision",
        "maintainer",
        "authorized_at",
        "waivers",
        "reason",
        "risk_acceptance",
        "local_verification",
    }
    if set(override) != expected_override_keys:
        errors.append(
            "maintainer override manifest keys must be exactly "
            f"{sorted(expected_override_keys)}"
        )
    if override.get("schema_version") != contract.get("schema_version"):
        errors.append("maintainer override manifest schema_version mismatch")
    if override.get("release_version") != package_version:
        errors.append("maintainer override release_version must match package version")
    if override.get("release_tag") != f"v{package_version}":
        errors.append("maintainer override release_tag must match package version")
    candidate_version = gate.get("required_candidate_version")
    if override.get("candidate_version") != candidate_version:
        errors.append("maintainer override candidate_version mismatch")
    candidate_tag = f"v{candidate_version}" if isinstance(candidate_version, str) else None
    if override.get("candidate_tag") != candidate_tag:
        errors.append("maintainer override candidate_tag mismatch")
    if override.get("repository") != contract.get("required_repository"):
        errors.append("maintainer override repository mismatch")
    if override.get("decision") != contract.get("required_decision"):
        errors.append("maintainer override decision mismatch")

    candidate_commit = override.get("candidate_skill_commit")
    if not isinstance(candidate_commit, str) or not _FULL_COMMIT_RE.fullmatch(candidate_commit):
        errors.append("maintainer override candidate_skill_commit must be a full lowercase SHA")
    elif expected_candidate_commit is not None:
        if not _FULL_COMMIT_RE.fullmatch(expected_candidate_commit):
            errors.append("release workflow candidate commit binding must be a full SHA")
        elif candidate_commit != expected_candidate_commit:
            errors.append(
                "maintainer override candidate_skill_commit must match the annotated RC commit"
            )

    candidate_tag_object = override.get("candidate_tag_object_sha")
    if not isinstance(candidate_tag_object, str) or not _FULL_COMMIT_RE.fullmatch(
        candidate_tag_object
    ):
        errors.append(
            "maintainer override candidate_tag_object_sha must be a full lowercase SHA"
        )
    elif expected_candidate_tag_object is not None:
        if not _FULL_COMMIT_RE.fullmatch(expected_candidate_tag_object):
            errors.append("release workflow candidate tag-object binding must be a full SHA")
        elif candidate_tag_object != expected_candidate_tag_object:
            errors.append(
                "maintainer override candidate_tag_object_sha must match the annotated RC tag object"
            )

    maintainer = override.get("maintainer")
    if not isinstance(maintainer, dict) or set(maintainer) != {"login", "role"}:
        errors.append("maintainer override maintainer must contain exactly login and role")
    else:
        if maintainer.get("login") != contract.get("required_maintainer_login"):
            errors.append("maintainer override login mismatch")
        if maintainer.get("role") != "repository_owner":
            errors.append("maintainer override role must be repository_owner")

    authorized_at = _parse_rfc3339(override.get("authorized_at"))
    if authorized_at is None:
        errors.append("maintainer override authorized_at must be timezone-aware RFC3339")
    waivers = override.get("waivers")
    if waivers != required_waivers:
        errors.append("maintainer override waivers must exactly match required_waivers")
    reason = override.get("reason")
    if not isinstance(reason, str) or not 40 <= len(reason.strip()) <= 2000:
        errors.append("maintainer override reason must contain 40-2000 characters")
    risk_acceptance = override.get("risk_acceptance")
    if not isinstance(risk_acceptance, dict) or set(risk_acceptance) != set(required_waivers):
        errors.append("maintainer override risk_acceptance must explain every waiver exactly once")
    else:
        for waiver, explanation in risk_acceptance.items():
            if not isinstance(explanation, str) or len(explanation.strip()) < 20:
                errors.append(
                    f"maintainer override risk_acceptance.{waiver} must be substantive"
                )

    local_artifact = override.get("local_verification")
    if not isinstance(local_artifact, dict) or set(local_artifact) != {"path", "sha256"}:
        errors.append("maintainer override local_verification must contain path and sha256")
        return errors
    local_path = _resolve_repo_file(
        root,
        local_artifact.get("path"),
        "maintainer override local_verification.path",
        errors,
        contained_by=evidence_dir,
    )
    declared_hash = local_artifact.get("sha256")
    if not isinstance(declared_hash, str) or not _SHA256_RE.fullmatch(declared_hash):
        errors.append("maintainer override local_verification.sha256 is invalid")
    if local_path is None:
        return errors
    actual_hash = _sha256_path(local_path)
    if declared_hash != actual_hash:
        errors.append("maintainer override local verification hash mismatch")
    try:
        verification = _strict_json_bytes(
            local_path.read_bytes(), "local verification record"
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"local verification record is unreadable: {exc}")
        return errors

    expected_verification_keys = {
        "schema_version",
        "release_version",
        "candidate_version",
        "candidate_skill_commit",
        "candidate_tag_object_sha",
        "generated_at",
        "environment",
        "commands",
        "summary",
    }
    if set(verification) != expected_verification_keys:
        errors.append(
            "local verification record keys must be exactly "
            f"{sorted(expected_verification_keys)}"
        )
    for field, expected in (
        ("schema_version", "1.0"),
        ("release_version", package_version),
        ("candidate_version", candidate_version),
        ("candidate_skill_commit", candidate_commit),
        ("candidate_tag_object_sha", candidate_tag_object),
    ):
        if verification.get(field) != expected:
            errors.append(f"local verification {field} mismatch")
    generated_at = _parse_rfc3339(verification.get("generated_at"))
    if generated_at is None:
        errors.append("local verification generated_at must be timezone-aware RFC3339")
    elif authorized_at is not None and generated_at > authorized_at:
        errors.append("maintainer override authorization predates local verification")

    environment = verification.get("environment")
    if not isinstance(environment, dict) or set(environment) != {
        "os",
        "architecture",
        "python_versions",
        "node_versions",
    }:
        errors.append("local verification environment has an invalid shape")
    else:
        for field in ("os", "architecture"):
            if not isinstance(environment.get(field), str) or not environment[field].strip():
                errors.append(f"local verification environment.{field} must be non-empty")
        for field in ("python_versions", "node_versions"):
            values = environment.get(field)
            if (
                not isinstance(values, list)
                or not values
                or any(not isinstance(value, str) or not value.strip() for value in values)
            ):
                errors.append(f"local verification environment.{field} must be non-empty")

    commands = verification.get("commands")
    observed_checks: dict[str, dict] = {}
    if not isinstance(commands, list):
        errors.append("local verification commands must be a list")
        commands = []
    for index, command in enumerate(commands):
        label = f"local verification commands[{index}]"
        if not isinstance(command, dict) or set(command) != {
            "id",
            "command",
            "runtime",
            "exit_code",
            "result",
        }:
            errors.append(f"{label} has an invalid shape")
            continue
        check_id = command.get("id")
        if not isinstance(check_id, str) or not check_id:
            errors.append(f"{label}.id must be non-empty")
            continue
        if check_id in observed_checks:
            errors.append(f"local verification contains duplicate check id {check_id!r}")
            continue
        observed_checks[check_id] = command
        if not isinstance(command.get("command"), str) or not command["command"].strip():
            errors.append(f"{label}.command must be non-empty")
        if not isinstance(command.get("runtime"), str) or not command["runtime"].strip():
            errors.append(f"{label}.runtime must be non-empty")
        if command.get("exit_code") != 0 or isinstance(command.get("exit_code"), bool):
            errors.append(f"{label}.exit_code must be integer 0")
        if command.get("result") != "passed":
            errors.append(f"{label}.result must be 'passed'")
    if set(observed_checks) != set(required_checks):
        errors.append("local verification check IDs must exactly cover required_checks")

    summary = verification.get("summary")
    if not isinstance(summary, dict) or set(summary) != {"passed", "failed"}:
        errors.append("local verification summary must contain exactly passed and failed")
    else:
        if summary.get("passed") != len(required_checks):
            errors.append("local verification summary.passed mismatch")
        if summary.get("failed") != 0 or isinstance(summary.get("failed"), bool):
            errors.append("local verification summary.failed must be integer 0")
    return errors


def check_stable_release_evidence(
    root: Path = ROOT,
    *,
    expected_candidate_commit: str | None = None,
    expected_baseline_commit: str | None = None,
    expected_candidate_tag_object: str | None = None,
    expected_baseline_tag_object: str | None = None,
) -> list[str]:
    """Require the release-evidence mode frozen into the dogfooded RC.

    Release candidates intentionally skip this gate. Stable metadata must use
    either the default reviewer-approved live-evidence path or the narrowly
    scoped maintainer override declared before the RC was tagged.
    """

    errors: list[str] = []
    package_version = str(_load_json(root / "package.json").get("version", ""))
    if not package_version or "-rc." in package_version:
        return errors

    route_manifest_path = root / "templates" / "route-manifest.json"
    if not route_manifest_path.is_file():
        return ["stable release gate requires templates/route-manifest.json"]
    route_manifest = _load_json(route_manifest_path)
    gate = route_manifest.get("stable_release_gate")
    if not isinstance(gate, dict):
        return ["route-manifest missing stable_release_gate contract"]

    promotion_mode = gate.get("promotion_mode", "live_evidence")
    if promotion_mode == "maintainer_override":
        return _check_maintainer_override(
            root,
            package_version,
            gate,
            expected_candidate_commit=expected_candidate_commit,
            expected_candidate_tag_object=expected_candidate_tag_object,
        )
    if promotion_mode != "live_evidence":
        return [f"unsupported stable promotion_mode: {promotion_mode!r}"]

    promotion_template = gate.get("promotion_manifest_path")
    if not isinstance(promotion_template, str) or "{version}" not in promotion_template:
        return ["stable_release_gate.promotion_manifest_path must contain {version}"]
    promotion_rel = promotion_template.format(version=package_version)
    promotion_path = _resolve_repo_file(
        root,
        promotion_rel,
        "stable promotion manifest",
        errors,
    )
    if promotion_path is None:
        return errors
    evidence_dir = promotion_path.parent

    try:
        promotion = _load_strict_json(promotion_path, "stable promotion manifest")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"stable promotion manifest is unreadable: {exc}"]

    expected_promotion_keys = {
        "schema_version",
        "release_version",
        "baseline_version",
        "candidate_version",
        "baseline_skill_commit",
        "candidate_skill_commit",
        "baseline_tag",
        "baseline_tag_object_sha",
        "candidate_tag",
        "candidate_tag_object_sha",
        "generated_at",
        "tiers",
        "reviewer_signoff_path",
    }
    if set(promotion) != expected_promotion_keys:
        errors.append(
            "stable promotion manifest keys must be exactly "
            f"{sorted(expected_promotion_keys)}"
        )

    if promotion.get("schema_version") != "1.2":
        errors.append("stable promotion manifest schema_version must be '1.2'")
    if promotion.get("release_version") != package_version:
        errors.append("stable promotion manifest release_version must match package version")
    for field, contract_key in (
        ("baseline_version", "required_baseline_version"),
        ("candidate_version", "required_candidate_version"),
    ):
        expected = gate.get(contract_key)
        if not isinstance(expected, str) or not expected:
            errors.append(f"stable_release_gate.{contract_key} must be non-empty")
        elif promotion.get(field) != expected:
            errors.append(
                f"stable promotion {field} must be {expected!r}, got {promotion.get(field)!r}"
            )

    candidate_version = gate.get("required_candidate_version")
    baseline_version = gate.get("required_baseline_version")
    expected_baseline_tag = (
        f"v{baseline_version}" if isinstance(baseline_version, str) else None
    )
    if promotion.get("baseline_tag") != expected_baseline_tag:
        errors.append(f"stable promotion baseline_tag must be {expected_baseline_tag!r}")
    baseline_tag_object = promotion.get("baseline_tag_object_sha")
    baseline_contract = gate.get("baseline_tag")
    frozen_baseline_tag_object = (
        baseline_contract.get("expected_tag_object_sha")
        if isinstance(baseline_contract, dict)
        else None
    )
    if not isinstance(baseline_tag_object, str) or not _FULL_COMMIT_RE.fullmatch(
        baseline_tag_object
    ):
        errors.append("stable promotion baseline_tag_object_sha must be a full lowercase SHA")
    else:
        if baseline_tag_object != frozen_baseline_tag_object:
            errors.append(
                "stable promotion baseline_tag_object_sha must match the frozen baseline tag object"
            )
        if expected_baseline_tag_object is not None:
            if not _FULL_COMMIT_RE.fullmatch(expected_baseline_tag_object):
                errors.append("release workflow baseline tag object binding must be a full SHA")
            elif baseline_tag_object != expected_baseline_tag_object:
                errors.append(
                    "stable promotion baseline_tag_object_sha must match the annotated baseline tag object"
                )

    expected_candidate_tag = (
        f"v{candidate_version}" if isinstance(candidate_version, str) else None
    )
    if promotion.get("candidate_tag") != expected_candidate_tag:
        errors.append(
            f"stable promotion candidate_tag must be {expected_candidate_tag!r}"
        )
    candidate_tag_object = promotion.get("candidate_tag_object_sha")
    if not isinstance(candidate_tag_object, str) or not _FULL_COMMIT_RE.fullmatch(
        candidate_tag_object
    ):
        errors.append("stable promotion candidate_tag_object_sha must be a full lowercase SHA")
    elif expected_candidate_tag_object is not None:
        if not _FULL_COMMIT_RE.fullmatch(expected_candidate_tag_object):
            errors.append("release workflow candidate tag object binding must be a full SHA")
        elif candidate_tag_object != expected_candidate_tag_object:
            errors.append(
                "stable promotion candidate_tag_object_sha must match the annotated RC tag object"
            )

    generated_at = _parse_rfc3339(promotion.get("generated_at"))
    if generated_at is None:
        errors.append("stable promotion generated_at must be timezone-aware RFC3339")

    expected_commits: dict[str, str] = {}
    for field in ("baseline_skill_commit", "candidate_skill_commit"):
        value = promotion.get(field)
        if not isinstance(value, str) or not _FULL_COMMIT_RE.fullmatch(value):
            errors.append(f"stable promotion {field} must be a full lowercase commit SHA")
        else:
            expected_commits[field] = value

    for field, expected in (
        ("candidate_skill_commit", expected_candidate_commit),
        ("baseline_skill_commit", expected_baseline_commit),
    ):
        if expected is None:
            continue
        if not _FULL_COMMIT_RE.fullmatch(expected):
            errors.append(f"release workflow {field} binding must be a full lowercase commit SHA")
        elif expected_commits.get(field) != expected:
            errors.append(
                f"stable promotion {field} must match the release workflow commit "
                f"{expected!r}, got {expected_commits.get(field)!r}"
            )

    tier_contracts = gate.get("tiers")
    promotion_tiers = promotion.get("tiers")
    if not isinstance(tier_contracts, dict) or set(tier_contracts) != {"tier1", "tier2"}:
        errors.append("stable_release_gate.tiers must define exactly tier1 and tier2")
        tier_contracts = {}
    if not isinstance(promotion_tiers, dict) or set(promotion_tiers) != {"tier1", "tier2"}:
        errors.append("stable promotion tiers must define exactly tier1 and tier2")
        promotion_tiers = {}

    try:
        harness = _load_eval_harness(root)
    except (OSError, ImportError, RuntimeError) as exc:
        errors.append(str(exc))
        harness = None

    runtime_signatures: set[str] = set()
    evaluator_harness_commits: set[str] = set()
    seen_run_ids: set[str] = set()
    seen_session_ids: set[str] = set()
    seen_time_pairs: set[tuple[datetime, datetime]] = set()
    seen_run_dirs: list[Path] = []
    baseline_version = gate.get("required_baseline_version")
    for tier_name in ("tier1", "tier2"):
        tier_contract = tier_contracts.get(tier_name)
        tier_entry = promotion_tiers.get(tier_name)
        if not isinstance(tier_contract, dict) or not isinstance(tier_entry, dict):
            continue
        expected_tier_entry_keys = {
            "baseline_scores",
            "candidate_scores",
            "baseline_runs_path",
            "candidate_runs_path",
        }
        if set(tier_entry) != expected_tier_entry_keys:
            errors.append(
                f"stable promotion {tier_name} keys must be exactly "
                f"{sorted(expected_tier_entry_keys)}"
            )

        bench_path = _resolve_repo_file(
            root,
            tier_contract.get("bench_path"),
            f"stable_release_gate.tiers.{tier_name}.bench_path",
            errors,
        )
        if bench_path is None or harness is None:
            continue
        try:
            bench = _load_strict_json(bench_path, f"{tier_name} bench")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"{tier_name} bench is unreadable: {exc}")
            continue
        bench_errors, _bench_warnings = harness.validate_bench(bench, bench_path)
        errors.extend(f"{tier_name} bench: {error}" for error in bench_errors)
        expected_tier = tier_contract.get("expected_tier")
        if harness.bench_tier(bench) != expected_tier:
            errors.append(
                f"{tier_name} bench tier must be {expected_tier!r}, "
                f"got {harness.bench_tier(bench)!r}"
            )
        current_fingerprint = harness.bench_fingerprint(bench)
        bench_ids = {
            task.get("task_id") for task in bench.get("tasks", []) if isinstance(task, dict)
        }

        records: dict[str, dict] = {}
        tier_evaluator_signatures: set[str] = set()
        for side in ("baseline", "candidate"):
            artifact_error_start = len(errors)
            artifact = tier_entry.get(f"{side}_scores")
            label = f"stable promotion {tier_name}.{side}_scores"
            if not isinstance(artifact, dict):
                errors.append(f"{label} must be an object with path and sha256")
                continue
            if set(artifact) != {"path", "sha256"}:
                errors.append(f"{label} keys must be exactly path and sha256")
            artifact_path = _resolve_repo_file(
                root,
                artifact.get("path"),
                f"{label}.path",
                errors,
                contained_by=evidence_dir,
            )
            declared_hash = artifact.get("sha256")
            if not isinstance(declared_hash, str) or not _SHA256_RE.fullmatch(declared_hash):
                errors.append(f"{label}.sha256 must be sha256:<64 lowercase hex>")
            if artifact_path is None:
                continue
            actual_hash = _sha256_path(artifact_path)
            if declared_hash != actual_hash:
                errors.append(
                    f"{label} hash mismatch: declared={declared_hash!r}, actual={actual_hash!r}"
                )
            try:
                score = _load_strict_json(artifact_path, label)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                errors.append(f"{label} is unreadable: {exc}")
                continue
            score_validation_errors = harness.validate_score_file(score)
            errors.extend(f"{label}: {error}" for error in score_validation_errors)
            if score.get("bench_fingerprint") != current_fingerprint:
                errors.append(f"{label} does not match the committed bench fingerprint")
            if score.get("tier") != expected_tier:
                errors.append(f"{label}.tier must be {expected_tier!r}")
            score_ids = {
                task.get("task_id") for task in score.get("tasks", []) if isinstance(task, dict)
            }
            if score_ids != bench_ids:
                errors.append(f"{label} task IDs do not exactly cover the committed bench")
            counts = score.get("counts")
            if not isinstance(counts, dict) or counts.get("not_run") != 0:
                errors.append(f"{label} must have counts.not_run = 0")
            if isinstance(counts, dict) and counts.get("failed") != 0:
                errors.append(f"{label} must have counts.failed = 0")
            expected_refusals = sum(
                1 for task in bench.get("tasks", [])
                if isinstance(task, dict) and task.get("expected_action") == "refuse"
            )
            if (
                isinstance(counts, dict)
                and isinstance(counts.get("passed"), int)
                and counts.get("passed") <= expected_refusals
            ):
                errors.append(
                    f"{label} must pass at least one factual task in addition to "
                    "the expected refusal probes"
                )
            score_created_at = _parse_rfc3339(score.get("created_at"))
            if score_created_at is None:
                errors.append(f"{label}.created_at must be timezone-aware RFC3339")
            elif generated_at is not None and score_created_at > generated_at:
                errors.append(f"{label}.created_at must not follow promotion generated_at")

            metadata_errors, runtime_signature = harness.comparable_run_metadata(
                score,
                f"{tier_name}.{side}",
            )
            errors.extend(metadata_errors)
            if runtime_signature is None:
                errors.append(f"{label} has no verifiable runtime signature")
            else:
                # The harness signature also binds the tier-specific evaluator
                # fingerprint. Stable promotion requires one runtime across
                # tiers, while each tier necessarily has a different bench.
                try:
                    signature_data = json.loads(runtime_signature)
                except json.JSONDecodeError:
                    runtime_signatures.add(runtime_signature)
                else:
                    runtime_only = (
                        signature_data.get("runtime")
                        if isinstance(signature_data, dict)
                        else signature_data
                    )
                    runtime_signatures.add(
                        json.dumps(runtime_only, sort_keys=True, separators=(",", ":"))
                    )

            commit = _score_commit(score, label, errors)
            expected_commit = expected_commits.get(f"{side}_skill_commit")
            if commit is not None and expected_commit is not None and commit != expected_commit:
                errors.append(
                    f"{label} skill commit {commit!r} does not match promotion "
                    f"{side}_skill_commit {expected_commit!r}"
                )
            errors.extend(
                _validate_live_runs(
                    root=root,
                    evidence_dir=evidence_dir,
                    runs_path_value=tier_entry.get(f"{side}_runs_path"),
                    expected_runs_path=(
                        evidence_dir / "runs" / f"{tier_name}-{side}"
                    )
                    # Windows may spell the same temporary root as RUNNER~1
                    # before resolve() and runneradmin afterwards.
                    .relative_to(root.resolve())
                    .as_posix(),
                    label=f"stable promotion {tier_name}.{side}_runs_path",
                    harness=harness,
                    bench=bench,
                    score=score,
                    canonical_threshold=tier_contract.get("pass_threshold"),
                    expected_skill_commit=expected_commits.get(
                        f"{side}_skill_commit"
                    ),
                    expected_harness_commit=expected_commits.get(
                        "candidate_skill_commit"
                    ),
                    expected_version=(
                        gate.get("required_baseline_version")
                        if side == "baseline"
                        else gate.get("required_candidate_version")
                    ),
                    generated_at=generated_at,
                    score_created_at=score_created_at,
                    seen_run_ids=seen_run_ids,
                    seen_session_ids=seen_session_ids,
                    seen_time_pairs=seen_time_pairs,
                    seen_run_dirs=seen_run_dirs,
                    evaluator_signatures=tier_evaluator_signatures,
                    evaluator_harness_commits=evaluator_harness_commits,
                )
            )
            if len(errors) == artifact_error_start:
                records[side] = score

        baseline = records.get("baseline")
        candidate = records.get("candidate")
        if len(tier_evaluator_signatures) > 1:
            errors.append(
                f"{tier_name} baseline/candidate runs must use one identical "
                "evaluator binding"
            )
        if baseline is None or candidate is None:
            continue
        for key in ("bench_schema_version", "bench_version", "bench_fingerprint"):
            if baseline.get(key) != candidate.get(key):
                errors.append(f"{tier_name} score pair mismatch for {key}")
        base_ids = {
            task.get("task_id") for task in baseline.get("tasks", []) if isinstance(task, dict)
        }
        candidate_ids = {
            task.get("task_id") for task in candidate.get("tasks", []) if isinstance(task, dict)
        }
        if base_ids != candidate_ids:
            errors.append(f"{tier_name} baseline/candidate task IDs differ")
            continue
        comparison = harness.compare_score_records(
            baseline,
            candidate,
            harness.DEFAULT_REGRESSION_DELTA,
        )
        if tier_name == "tier1" and comparison.get("verdict") == "WEAKER":
            errors.append(f"tier1 live dogfood regressed versus v{baseline_version}")
        if tier_name == "tier2":
            if comparison.get("counts", {}).get("safety_regressions") != 0:
                errors.append("tier2 live dogfood contains a safety regression")
            baseline_passed = baseline.get("counts", {}).get("passed")
            candidate_passed = candidate.get("counts", {}).get("passed")
            if not isinstance(baseline_passed, int) or not isinstance(candidate_passed, int):
                errors.append("tier2 score artifacts must contain integer passed counts")
            elif candidate_passed < baseline_passed:
                errors.append(
                    f"tier2 candidate pass count is lower than v{baseline_version}"
                )

    if len(runtime_signatures) > 1:
        errors.append(
            "stable live dogfood must use one identical runtime/model/tool "
            "configuration across Tier 1 and Tier 2 baseline/candidate runs"
        )
    if len(evaluator_harness_commits) > 1:
        errors.append(
            "stable live dogfood must use one identical evaluator harness commit "
            "across Tier 1 and Tier 2 baseline/candidate runs"
        )

    signoff_path = _resolve_repo_file(
        root,
        promotion.get("reviewer_signoff_path"),
        "stable promotion reviewer_signoff_path",
        errors,
        contained_by=evidence_dir,
    )
    if signoff_path is not None:
        try:
            signoff = _load_strict_json(signoff_path, "stable reviewer sign-off")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            errors.append(f"stable reviewer sign-off is unreadable: {exc}")
        else:
            expected_signoff_keys = {
                "schema_version",
                "release_version",
                "decision",
                "reviewer",
                "reviewed_at",
                "promotion_manifest_sha256",
                "attestation",
                "review_scope",
            }
            if set(signoff) != expected_signoff_keys:
                errors.append(
                    "stable reviewer sign-off keys must be exactly "
                    f"{sorted(expected_signoff_keys)}"
                )
            if signoff.get("schema_version") != "1.2":
                errors.append("stable reviewer sign-off schema_version must be '1.2'")
            if signoff.get("release_version") != package_version:
                errors.append("stable reviewer sign-off release_version mismatch")
            if signoff.get("decision") != "approved":
                errors.append("stable reviewer sign-off decision must be 'approved'")
            reviewer = signoff.get("reviewer")
            if not isinstance(reviewer, dict) or any(
                not isinstance(reviewer.get(field), str) or not reviewer.get(field).strip()
                for field in ("name", "role")
            ):
                errors.append("stable reviewer sign-off requires reviewer.name and reviewer.role")
            elif set(reviewer) != {"name", "role"}:
                errors.append("stable reviewer sign-off reviewer keys are invalid")
            reviewed_at = _parse_rfc3339(signoff.get("reviewed_at"))
            if reviewed_at is None:
                errors.append("stable reviewer sign-off reviewed_at must be RFC3339")
            elif generated_at is not None and reviewed_at < generated_at:
                errors.append("stable reviewer sign-off predates the promotion manifest")
            manifest_hash = _sha256_path(promotion_path)
            if signoff.get("promotion_manifest_sha256") != manifest_hash:
                errors.append(
                    "stable reviewer sign-off must bind the exact promotion manifest SHA256"
                )
            expected_review_scope = {
                "live_run_origin_verified": True,
                "raw_artifacts_reviewed": True,
                "score_recomputation_reviewed": True,
            }
            if signoff.get("review_scope") != expected_review_scope:
                errors.append(
                    "stable reviewer sign-off must attest live run origin, raw artifacts, "
                    "and score recomputation"
                )
            attestation = signoff.get("attestation")
            attestation_contract = gate.get("reviewer_attestation")
            if not isinstance(attestation_contract, dict):
                errors.append("stable_release_gate.reviewer_attestation must be an object")
            elif not isinstance(attestation, dict):
                errors.append("stable reviewer sign-off requires a verifiable attestation")
            else:
                expected_attestation_keys = {
                    "type",
                    "repository",
                    "pull_request_number",
                    "reviewer_login",
                }
                if set(attestation) != expected_attestation_keys:
                    errors.append("stable reviewer attestation keys are invalid")
                expected_type = attestation_contract.get("type")
                expected_repository = attestation_contract.get("repository")
                if attestation.get("type") != expected_type:
                    errors.append(
                        f"stable reviewer attestation type must be {expected_type!r}"
                    )
                if attestation.get("repository") != expected_repository:
                    errors.append(
                        "stable reviewer attestation repository must match the release contract"
                    )
                pull_request = attestation.get("pull_request_number")
                if not isinstance(pull_request, int) or isinstance(pull_request, bool) or pull_request < 1:
                    errors.append(
                        "stable reviewer attestation pull_request_number must be a positive integer"
                    )
                reviewer_login = attestation.get("reviewer_login")
                if not isinstance(reviewer_login, str) or not reviewer_login.strip():
                    errors.append(
                        "stable reviewer attestation reviewer_login must be non-empty"
                    )

    return errors


def check_config_safety() -> list[str]:
    errors: list[str] = []
    cfg = _load_json(ROOT / "research.config.example.json")
    access = cfg.get("access") or {}
    for key in ("allowCaptchaSolving", "allowStealthEvasion"):
        if key not in access:
            errors.append(f"research.config.example.json missing access.{key}")
        elif access.get(key) is not False:
            errors.append(
                f"research.config.example.json access.{key} must be false (never allowed)"
            )
    if access.get("defaultMode") not in (None, "read-only"):
        errors.append("access.defaultMode must be read-only when present")
    return errors


def _parse_skill_route_table(skill: str) -> list[tuple[str, str]]:
    match = re.search(
        r"^### Route table\s*$\n(?P<body>.*?)(?=^##\s)",
        skill,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        return []
    rows: list[tuple[str, str]] = []
    for line in match.group("body").splitlines():
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 2 or cells[0] == "Route" or set(cells[0]) <= {"-", ":"}:
            continue
        rows.append((cells[0], cells[1]))
    return rows


def _parse_intake_shape_labels(intake: str) -> list[str]:
    """Return canonical labels from the Research Intake shape table."""
    match = re.search(
        r"^## Shape Labels\s*$\n(?P<body>.*?)(?=^##\s)",
        intake,
        flags=re.MULTILINE | re.DOTALL,
    )
    if match is None:
        return []
    labels: list[str] = []
    for line in match.group("body").splitlines():
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        label_match = re.fullmatch(r"`([a-z0-9_]+)`", cells[0])
        if label_match:
            labels.append(label_match.group(1))
    return labels


def check_skill_and_routes(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    skill_path = root / "SKILL.md"
    skill = skill_path.read_text(encoding="utf-8")
    lines = skill.count("\n") + (0 if skill.endswith("\n") and skill else 1)
    if not skill.endswith("\n"):
        lines = skill.count("\n") + 1
    else:
        lines = skill.count("\n")  # trailing newline: count lines as non-empty convention
        # Prefer exact: number of lines when splitlines(keepends=False)
        lines = len(skill.splitlines())
    if lines < _SKILL_LINE_MIN or lines > _SKILL_LINE_MAX:
        errors.append(
            f"SKILL.md has {lines} lines; PLAN requires {_SKILL_LINE_MIN}-{_SKILL_LINE_MAX}"
        )
    if "name: d-research" not in skill:
        errors.append("SKILL.md frontmatter must declare name: d-research")
    for phrase in (
        "never allowed",
        "allowCaptchaSolving",
        "allowStealthEvasion",
        "research-intake.md",
        "research-plan-protocol.md",
        "execution-gates.md",
    ):
        if phrase not in skill:
            errors.append(f"SKILL.md missing required phrase/path: {phrase}")

    # Soft-ban "disabled by default" for captcha/stealth
    soft = re.findall(
        r"(?i)(captcha|stealth).{0,40}disabled by default|disabled by default.{0,40}(captcha|stealth)",
        skill,
    )
    if soft:
        errors.append("SKILL.md must not say captcha/stealth are merely disabled by default")

    manifest_path = root / "templates" / "route-manifest.json"
    if not manifest_path.is_file():
        errors.append("missing templates/route-manifest.json")
        return errors
    manifest = _load_json(manifest_path)
    for ref in manifest.get("required_skill_references") or []:
        if f"`{ref}`" not in skill and ref not in skill:
            # allow without backticks if path appears
            if ref not in skill:
                errors.append(f"SKILL.md missing required reference {ref}")
        path = root / ref
        if not path.exists():
            errors.append(f"route-manifest required path missing: {ref}")

    routes = manifest.get("routes") or []
    route_ids: set[str] = set()
    mapped_intake_labels: dict[str, str] = {}
    expected_skill_rows: list[tuple[str, str]] = []
    for route in routes:
        if not isinstance(route, dict):
            errors.append("route-manifest routes must contain only objects")
            continue
        route_id = route.get("id")
        if not isinstance(route_id, str) or not route_id:
            errors.append("route-manifest route missing non-empty id")
        elif route_id in route_ids:
            errors.append(f"route-manifest duplicate route id: {route_id}")
        else:
            route_ids.add(route_id)
        intake_labels = route.get("intake_labels")
        if not isinstance(intake_labels, list) or any(
            not isinstance(label, str) or not label for label in intake_labels
        ):
            errors.append(
                f"route-manifest route {route_id!r} intake_labels must be a string list"
            )
        else:
            for label in intake_labels:
                previous = mapped_intake_labels.get(label)
                if previous is not None:
                    errors.append(
                        f"route-manifest intake label {label!r} maps to both "
                        f"{previous!r} and {route_id!r}"
                    )
                else:
                    mapped_intake_labels[label] = str(route_id)
        refs = []
        if route.get("reference"):
            refs.append(route["reference"])
        refs.extend(route.get("references") or [])
        for ref in refs:
            if not (root / ref).exists():
                errors.append(f"route-manifest path missing: {ref}")

        skill_surface = route.get("skill_surface")
        if not isinstance(skill_surface, dict):
            errors.append(f"route-manifest route {route_id!r} missing skill_surface")
            continue
        kind = skill_surface.get("kind")
        if kind == "table_row":
            label = skill_surface.get("label")
            target = skill_surface.get("target")
            if not isinstance(label, str) or not isinstance(target, str):
                errors.append(f"route-manifest route {route_id!r} table_row needs label/target")
            else:
                expected_skill_rows.append((label, target))
        elif kind == "text_anchor":
            anchor = skill_surface.get("anchor")
            if not isinstance(anchor, str) or not anchor:
                errors.append(f"route-manifest route {route_id!r} text_anchor needs anchor")
            elif anchor not in skill:
                errors.append(f"SKILL.md route drift: route {route_id!r} missing anchor {anchor!r}")
        else:
            errors.append(
                f"route-manifest route {route_id!r} has invalid skill_surface.kind {kind!r}"
            )

    actual_skill_rows = _parse_skill_route_table(skill)
    if actual_skill_rows != expected_skill_rows:
        errors.append(
            "SKILL.md route table drift: expected manifest rows "
            f"{expected_skill_rows!r}, got {actual_skill_rows!r}"
        )

    intake_path = root / "references" / "research-intake.md"
    if not intake_path.is_file():
        errors.append("missing references/research-intake.md")
    else:
        intake_labels = _parse_intake_shape_labels(
            intake_path.read_text(encoding="utf-8")
        )
        if not intake_labels:
            errors.append("research-intake.md has no parseable Shape Labels table")
        else:
            intake_set = set(intake_labels)
            mapped_set = set(mapped_intake_labels)
            missing = sorted(intake_set - mapped_set)
            unknown = sorted(mapped_set - intake_set)
            if missing:
                errors.append(
                    f"route-manifest intake mapping missing labels: {missing}"
                )
            if unknown:
                errors.append(
                    f"route-manifest intake mapping has unknown labels: {unknown}"
                )

    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    if "templates/route-manifest.json" not in agents:
        errors.append("AGENTS.md must identify templates/route-manifest.json as canonical")
    for route in routes:
        if not isinstance(route, dict):
            continue
        route_refs = []
        if route.get("reference"):
            route_refs.append(route["reference"])
        route_refs.extend(route.get("references") or [])
        for ref in route_refs:
            if ref not in agents:
                errors.append(f"AGENTS.md route drift: missing {ref}")
    if "never allowed" not in agents:
        errors.append("AGENTS.md must keep captcha/stealth as never allowed")

    docs_contract = manifest.get("documentation_contract")
    if not isinstance(docs_contract, dict):
        errors.append("route-manifest missing documentation_contract")
    else:
        protocol_path = root / "references" / "research-plan-protocol.md"
        readme_vi_path = root / "README.vi.md"
        openai_yaml_path = root / "agents" / "openai.yaml"
        for document_name, document_text, key in (
            ("SKILL.md", skill, "skill_required_statements"),
            ("AGENTS.md", agents, "agents_required_statements"),
            (
                "references/research-plan-protocol.md",
                protocol_path.read_text(encoding="utf-8")
                if protocol_path.is_file()
                else "",
                "protocol_required_statements",
            ),
            (
                "README.vi.md",
                readme_vi_path.read_text(encoding="utf-8")
                if readme_vi_path.is_file()
                else "",
                "readme_vi_required_statements",
            ),
            (
                "agents/openai.yaml",
                openai_yaml_path.read_text(encoding="utf-8")
                if openai_yaml_path.is_file()
                else "",
                "openai_yaml_required_statements",
            ),
        ):
            statements = docs_contract.get(key)
            if not isinstance(statements, list) or not statements:
                errors.append(f"route-manifest documentation_contract.{key} must be non-empty")
                continue
            for statement in statements:
                if not isinstance(statement, str) or not statement:
                    errors.append(
                        f"route-manifest documentation_contract.{key} contains invalid text"
                    )
                elif statement not in document_text:
                    errors.append(
                        f"{document_name} semantic drift: missing manifest statement {statement!r}"
                    )

    gates = manifest.get("canonical_gates") or {}
    for gname in (
        "plan_ready",
        "execute_ready",
        "dispatch_ready",
        "synthesize_ready",
        "release_ready",
    ):
        if gname not in gates or not gates[gname]:
            errors.append(f"route-manifest missing canonical gate set: {gname}")
        if gname not in agents:
            errors.append(f"AGENTS.md gate drift: missing {gname}")
    return errors


def _repository_contract_version_matches(package_version: str, manifest: dict) -> bool:
    """Accept an exact version or a stable release frozen to its dogfooded RC.

    The route manifest is part of the executable candidate contract and is not
    allowed to change after dogfood. Stable promotion therefore keeps its
    ``repository_contract.version`` at the exact RC declared by
    ``stable_release_gate.required_candidate_version`` while package metadata
    advances from ``X.Y.Z-rc.N`` to ``X.Y.Z``.
    """

    contract = manifest.get("repository_contract")
    if not isinstance(contract, dict):
        return False
    contract_version = contract.get("version")
    if contract_version == package_version:
        return True
    if not isinstance(package_version, str) or not re.fullmatch(
        r"\d+\.\d+\.\d+", package_version
    ):
        return False
    gate = manifest.get("stable_release_gate")
    if not isinstance(gate, dict):
        return False
    candidate_version = gate.get("required_candidate_version")
    return (
        isinstance(candidate_version, str)
        and candidate_version == contract_version
        and re.fullmatch(
            re.escape(package_version) + r"-rc\.\d+", candidate_version
        )
        is not None
    )


def _check_live_tag_contracts(stable_gate: dict) -> list[str]:
    """Require an immutable legacy baseline and verified candidate/release tags."""

    errors: list[str] = []
    baseline_contract = stable_gate.get("baseline_tag")
    baseline_expected_keys = {
        "annotated",
        "github_verified",
        "bind_tag_object_sha",
        "expected_tag_object_sha",
        "verification_mode",
    }
    if (
        not isinstance(baseline_contract, dict)
        or set(baseline_contract) != baseline_expected_keys
        or baseline_contract.get("annotated") is not True
        or baseline_contract.get("github_verified") is not False
        or baseline_contract.get("bind_tag_object_sha") is not True
        or not isinstance(baseline_contract.get("expected_tag_object_sha"), str)
        or not _FULL_COMMIT_RE.fullmatch(baseline_contract["expected_tag_object_sha"])
        or baseline_contract.get("verification_mode") != "annotated_tag_object_sha"
    ):
        errors.append(
            "stable_release_gate.baseline_tag must pin the exact annotated legacy "
            "tag object and explicitly record its historical verification status"
        )

    expected_keys = {
        "annotated",
        "github_verified",
        "bind_tag_object_sha",
        "verification_mode",
    }
    for field in ("candidate_tag", "release_tag"):
        tag_contract = stable_gate.get(field)
        if (
            not isinstance(tag_contract, dict)
            or set(tag_contract) != expected_keys
            or tag_contract.get("annotated") is not True
            or tag_contract.get("github_verified") is not True
            or tag_contract.get("bind_tag_object_sha") is not True
            or tag_contract.get("verification_mode")
            != "github_verified_tag_object_sha"
        ):
            errors.append(
                f"stable_release_gate.{field} must require an annotated, "
                "GitHub-verified, tag-object-bound tag"
            )
    return errors


def check_repository_contract(root: Path = ROOT) -> list[str]:
    """Validate machine-readable repository counts, paths, docs, and CLI flags."""
    errors: list[str] = []
    manifest_path = root / "templates" / "route-manifest.json"
    if not manifest_path.is_file():
        return ["missing templates/route-manifest.json"]
    manifest = _load_json(manifest_path)
    contract = manifest.get("repository_contract")
    if not isinstance(contract, dict):
        return ["route-manifest missing repository_contract"]

    package_version = str(_load_json(root / "package.json").get("version", ""))
    if not _repository_contract_version_matches(package_version, manifest):
        errors.append(
            "repository_contract.version mismatch: "
            f"manifest={contract.get('version')!r}, package={package_version!r}"
        )

    references_count = len(list((root / "references").glob("*.md")))
    adapters_count = len(list((root / "adapters").glob("*.md")))
    examples_count = len(list((root / "examples").glob("*.md")))
    python_scripts = len(list((root / "scripts").glob("*.py")))
    node_top_level = len(list((root / "scripts").glob("*.mjs")))
    node_lib = len(list((root / "scripts" / "lib").glob("*.mjs")))
    template_files = len([path for path in (root / "templates").iterdir() if path.is_file()])
    ledger_header = (
        (root / "templates" / "evidence-ledger.csv").read_text(encoding="utf-8").splitlines()[0]
    )
    ledger_columns = len(ledger_header.split(","))
    actual_counts = {
        "references_markdown": references_count,
        "adapters_markdown": adapters_count,
        "examples_markdown": examples_count,
        "scripts_python": python_scripts,
        "scripts_node_top_level": node_top_level,
        "scripts_node_lib": node_lib,
        "scripts_total": python_scripts + node_top_level + node_lib,
        "templates_files": template_files,
        "evidence_ledger_columns": ledger_columns,
    }
    expected_counts = contract.get("counts")
    if not isinstance(expected_counts, dict):
        errors.append("repository_contract.counts must be an object")
    else:
        for name, actual in actual_counts.items():
            expected = expected_counts.get(name)
            if expected != actual:
                errors.append(
                    f"repository count drift for {name}: expected={expected!r}, actual={actual}"
                )

    for rel in contract.get("core_paths") or []:
        rel_path = Path(str(rel))
        if rel_path.is_absolute() or ".." in rel_path.parts:
            errors.append(f"repository_contract core path is unsafe: {rel!r}")
            continue
        if not (root / rel_path).exists():
            errors.append(f"repository_contract core path missing: {rel}")

    readme = (root / "README.md").read_text(encoding="utf-8")
    for marker in contract.get("readme_markers") or []:
        if str(marker) not in readme:
            errors.append(f"README.md missing repository marker: {marker}")

    readme_vi = (root / "README.vi.md").read_text(encoding="utf-8")
    installation = contract.get("installation_contract")
    if not isinstance(installation, dict):
        errors.append("repository_contract missing installation_contract")
    else:
        final_directory = installation.get("final_directory")
        if final_directory != manifest.get("skill_name") or final_directory != "d-research":
            errors.append(
                "installation_contract.final_directory must equal skill_name 'd-research'"
            )
        entrypoint_suffix = installation.get("entrypoint_suffix")
        if entrypoint_suffix != "d-research/SKILL.md":
            errors.append("installation_contract.entrypoint_suffix must be d-research/SKILL.md")
        elif entrypoint_suffix not in readme or entrypoint_suffix not in readme_vi:
            errors.append("README.md and README.vi.md must require the d-research/SKILL.md suffix")
        runtime_markers = installation.get("runtime_markers")
        if not isinstance(runtime_markers, list) or len(runtime_markers) != 5:
            errors.append("installation_contract.runtime_markers must list five runtimes")
        else:
            for marker in runtime_markers:
                if not isinstance(marker, str) or marker not in readme or marker not in readme_vi:
                    errors.append(f"installation matrix missing runtime marker: {marker!r}")
        canonical_paths = installation.get("canonical_paths")
        if not isinstance(canonical_paths, list) or len(canonical_paths) != 5:
            errors.append("installation_contract.canonical_paths must list five paths")
        else:
            for path_marker in canonical_paths:
                if not isinstance(path_marker, str) or not path_marker:
                    errors.append("installation_contract contains an invalid canonical path")
                    continue
                normalized = path_marker.replace("\\", "/").rstrip("/")
                if normalized.rsplit("/", 1)[-1] != "d-research":
                    errors.append(f"installation path must end in d-research: {path_marker!r}")
                if path_marker not in readme or path_marker not in readme_vi:
                    errors.append(f"installation path missing from README matrix: {path_marker!r}")

    for cli_contract in contract.get("cli_contracts") or []:
        if not isinstance(cli_contract, dict):
            errors.append("repository_contract cli_contract entry must be an object")
            continue
        rel = Path(str(cli_contract.get("path", "")))
        if not rel.parts or rel.is_absolute() or ".." in rel.parts:
            errors.append(f"repository_contract CLI path is unsafe: {str(rel)!r}")
            continue
        path = root / rel
        if not path.is_file():
            errors.append(f"repository_contract CLI path missing: {rel.as_posix()}")
            continue
        source = path.read_text(encoding="utf-8")
        for flag in cli_contract.get("canonical_flags") or []:
            if str(flag) not in source:
                errors.append(f"CLI contract drift: {rel.as_posix()} missing canonical flag {flag}")

    stable_gate = manifest.get("stable_release_gate")
    if not isinstance(stable_gate, dict):
        errors.append("route-manifest missing stable_release_gate")
    else:
        promotion_mode = stable_gate.get("promotion_mode", "live_evidence")
        if promotion_mode not in {"live_evidence", "maintainer_override"}:
            errors.append("stable_release_gate.promotion_mode is invalid")
        promotion_path = stable_gate.get("promotion_manifest_path")
        if (
            not isinstance(promotion_path, str)
            or "{version}" not in promotion_path
            or Path(promotion_path).is_absolute()
            or ".." in Path(promotion_path).parts
        ):
            errors.append(
                "stable_release_gate.promotion_manifest_path must be safe and contain {version}"
            )
        for key in ("required_baseline_version", "required_candidate_version"):
            value = stable_gate.get(key)
            if not isinstance(value, str) or not _PACKAGE_VERSION_RE.fullmatch(value):
                errors.append(f"stable_release_gate.{key} must be a release version")
        full_ci = stable_gate.get("full_ci")
        if not isinstance(full_ci, dict):
            errors.append("stable_release_gate.full_ci must be an object")
        else:
            if full_ci.get("workflow_path") != ".github/workflows/lint-and-self-test.yml":
                errors.append("stable_release_gate.full_ci.workflow_path is invalid")
            if full_ci.get("exact_candidate_sha") is not True:
                errors.append("stable_release_gate.full_ci must require exact_candidate_sha")
            if full_ci.get("exact_release_sha") is not True:
                errors.append("stable_release_gate.full_ci must require exact_release_sha")
            if full_ci.get("required_conclusion") != "success":
                errors.append("stable_release_gate.full_ci must require conclusion success")
        candidate_tag_contract = stable_gate.get("candidate_tag")
        if promotion_mode == "maintainer_override":
            if (
                not isinstance(candidate_tag_contract, dict)
                or set(candidate_tag_contract)
                != {"annotated", "github_verified", "bind_tag_object_sha", "verification_mode"}
                or candidate_tag_contract.get("annotated") is not True
                or candidate_tag_contract.get("github_verified") is not False
                or candidate_tag_contract.get("bind_tag_object_sha") is not True
                or candidate_tag_contract.get("verification_mode")
                != "annotated_tag_object_sha"
            ):
                errors.append(
                    "maintainer-override candidate_tag must require an annotated, "
                    "tag-object-bound tag with explicit GitHub-verification waiver"
                )
            release_tag_contract = stable_gate.get("release_tag")
            if (
                not isinstance(release_tag_contract, dict)
                or set(release_tag_contract)
                != {"annotated", "github_verified", "verification_mode"}
                or release_tag_contract.get("annotated") is not True
                or release_tag_contract.get("github_verified") is not False
                or release_tag_contract.get("verification_mode")
                != "annotated_tag_object_sha"
            ):
                errors.append(
                    "maintainer-override release_tag must remain annotated with an "
                    "explicit GitHub-verification waiver"
                )

            override_contract = stable_gate.get("maintainer_override")
            expected_override_keys = {
                "schema_version",
                "manifest_path",
                "allowed_release_version",
                "required_decision",
                "required_repository",
                "required_maintainer_login",
                "required_waivers",
                "required_checks",
                "bind_candidate_commit",
                "bind_candidate_tag_object_sha",
                "require_annotated_tags",
                "require_exact_sha_ci",
                "non_waivable",
            }
            if not isinstance(override_contract, dict) or set(override_contract) != expected_override_keys:
                errors.append(
                    "stable_release_gate.maintainer_override has an invalid contract shape"
                )
            else:
                if override_contract.get("schema_version") != "1.0":
                    errors.append("maintainer_override schema_version must be '1.0'")
                override_path = override_contract.get("manifest_path")
                if (
                    not isinstance(override_path, str)
                    or "{version}" not in override_path
                    or _canonical_repo_relative(
                        override_path.replace("{version}", "3.2.0")
                    )
                    is None
                ):
                    errors.append("maintainer_override manifest_path is invalid")
                if override_contract.get("allowed_release_version") != "3.2.0":
                    errors.append("maintainer_override must be scoped exactly to v3.2.0")
                if override_contract.get("required_decision") != "approved_with_waivers":
                    errors.append("maintainer_override required_decision is invalid")
                if override_contract.get("required_repository") != "d-init-d/d-research-skill":
                    errors.append("maintainer_override repository is invalid")
                if override_contract.get("required_maintainer_login") != "d-init-d":
                    errors.append("maintainer_override login is invalid")
                if override_contract.get("required_waivers") != list(
                    _MAINTAINER_OVERRIDE_WAIVERS
                ):
                    errors.append("maintainer_override waiver set is invalid")
                checks = override_contract.get("required_checks")
                if (
                    not isinstance(checks, list)
                    or not checks
                    or any(not isinstance(item, str) or not item for item in checks)
                    or len(checks) != len(set(checks))
                ):
                    errors.append("maintainer_override required_checks is invalid")
                for key in (
                    "bind_candidate_commit",
                    "bind_candidate_tag_object_sha",
                    "require_annotated_tags",
                    "require_exact_sha_ci",
                ):
                    if override_contract.get(key) is not True:
                        errors.append(f"maintainer_override must require {key}")
                required_hard_gates = {
                    "annotated_candidate_tag",
                    "annotated_release_tag",
                    "candidate_tag_object_binding",
                    "candidate_ancestry",
                    "exact_release_sha_ci",
                    "source_archive",
                    "sha256_manifest",
                    "provenance_attestation",
                }
                hard_gates = override_contract.get("non_waivable")
                if (
                    not isinstance(hard_gates, dict)
                    or set(hard_gates) != required_hard_gates
                    or any(value is not True for value in hard_gates.values())
                ):
                    errors.append("maintainer_override non_waivable gates are invalid")
        else:
            errors.extend(_check_live_tag_contracts(stable_gate))
            run_evidence = stable_gate.get("run_evidence")
            expected_run_evidence = {
                "canonical_layout": True,
                "manifest_name": "run-result.json",
                "run_result_schema_version": "2.1",
                "bind_raw_artifacts": True,
                "recompute_scores": True,
            }
            if run_evidence != expected_run_evidence:
                errors.append(
                    "stable_release_gate.run_evidence must require canonical schema-2.1 "
                    "manifests, raw artifact hashes, and score recomputation"
                )
        reviewer_attestation = stable_gate.get("reviewer_attestation")
        if not isinstance(reviewer_attestation, dict):
            errors.append("stable_release_gate.reviewer_attestation must be an object")
        else:
            if reviewer_attestation.get("type") != "github_verified_pull_request_review":
                errors.append("stable_release_gate reviewer attestation type is invalid")
            if reviewer_attestation.get("repository") != "d-init-d/d-research-skill":
                errors.append("stable_release_gate reviewer attestation repository is invalid")
            if reviewer_attestation.get("bind_exact_release_sha") is not True:
                errors.append("reviewer attestation must bind the exact release SHA")
            if reviewer_attestation.get("bind_promotion_sha256") is not True:
                errors.append("reviewer attestation must bind the promotion SHA256")
            if reviewer_attestation.get("trusted_associations") != [
                "OWNER",
                "MEMBER",
                "COLLABORATOR",
            ]:
                errors.append("reviewer attestation trusted associations are invalid")
        stable_tiers = stable_gate.get("tiers")
        if not isinstance(stable_tiers, dict) or set(stable_tiers) != {"tier1", "tier2"}:
            errors.append("stable_release_gate.tiers must define exactly tier1 and tier2")
        else:
            for tier_name, expected_tier, expected_threshold in (
                ("tier1", "regression", 0.7),
                ("tier2", "frontier", None),
            ):
                tier = stable_tiers.get(tier_name)
                if not isinstance(tier, dict):
                    errors.append(f"stable_release_gate.tiers.{tier_name} must be an object")
                    continue
                if set(tier) != {"bench_path", "expected_tier", "pass_threshold"}:
                    errors.append(
                        f"stable_release_gate.tiers.{tier_name} keys are invalid"
                    )
                bench = tier.get("bench_path")
                if (
                    not isinstance(bench, str)
                    or Path(bench).is_absolute()
                    or ".." in Path(bench).parts
                    or not (root / bench).is_file()
                ):
                    errors.append(f"stable_release_gate.tiers.{tier_name}.bench_path is invalid")
                if tier.get("expected_tier") != expected_tier:
                    errors.append(
                        f"stable_release_gate.tiers.{tier_name}.expected_tier "
                        f"must be {expected_tier!r}"
                    )
                if tier.get("pass_threshold") != expected_threshold:
                    errors.append(
                        f"stable_release_gate.tiers.{tier_name}.pass_threshold "
                        f"must be {expected_threshold!r}"
                    )

    release_workflow = root / ".github" / "workflows" / "release-source-archive.yml"
    if not release_workflow.is_file():
        errors.append("missing stable release workflow")
    else:
        workflow_text = release_workflow.read_text(encoding="utf-8")
        for marker in (
            "required_candidate_version",
            "--candidate-commit",
            'git merge-base --is-ancestor "$baseline_commit" "$candidate_commit"',
            'git merge-base --is-ancestor "$candidate_commit" "$release_commit"',
            "git diff --name-only",
            "validate-post-rc-paths",
            "validate_post_rc_changed_paths",
            "validate-post-rc-metadata",
            "--candidate-tag-object",
            "--baseline-tag-object",
            "frozen_baseline_tag_object",
            'commits=("$candidate_commit")',
            "verify-ci-response",
            "verify-tag-response",
            "verify-review-response",
            "--require-release-waiver",
            "git cat-file -t",
            "sha256sum --check",
        ):
            if marker not in workflow_text:
                errors.append(f"stable release workflow missing RC binding marker: {marker}")
        if "--release-commit" in workflow_text:
            errors.append(
                "stable release workflow must bind evidence to the dogfooded RC, "
                "not the self-referential stable commit"
            )
        # Workflow must not re-encode the allowlist in bash; Python is source of truth.
        if "release-evidence/v${release_version}/" in workflow_text and "case " in workflow_text:
            # Accept only when the Python validator is still invoked.
            if "validate-post-rc-paths" not in workflow_text:
                errors.append(
                    "stable release workflow must invoke validate-post-rc-paths "
                    "for post-RC path allowlisting"
                )
    return errors


def check_example_metadata(root: Path = ROOT) -> list[str]:
    """Require explicit truth-status metadata on every top-level example."""
    errors: list[str] = []
    allowed = {"verified", "illustrative", "fixture"}
    for path in sorted((root / "examples").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if len(lines) < 3 or lines[0].strip() != "---":
            errors.append(f"{path.relative_to(root)} missing YAML metadata block")
            continue
        try:
            closing = lines.index("---", 1)
        except ValueError:
            errors.append(f"{path.relative_to(root)} has unterminated metadata block")
            continue
        metadata: dict[str, str] = {}
        for line in lines[1:closing]:
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            metadata[key.strip()] = value.strip().strip("\"'")
        status = metadata.get("example_status")
        if status not in allowed:
            errors.append(
                f"{path.relative_to(root)} example_status {status!r} not in {sorted(allowed)}"
            )
        if status == "verified":
            fixture = metadata.get("fixture_path")
            if not fixture:
                errors.append(f"{path.relative_to(root)} verified example missing fixture_path")
                continue
            fixture_rel = Path(fixture)
            if fixture_rel.is_absolute() or ".." in fixture_rel.parts:
                errors.append(f"{path.relative_to(root)} has unsafe fixture_path {fixture!r}")
            elif not (root / fixture_rel).is_file():
                errors.append(f"{path.relative_to(root)} fixture_path does not exist: {fixture}")
    return errors


def check_canonical_examples(root: Path = ROOT) -> list[str]:
    """Protect the three replayable examples from fabricated-result drift."""
    errors: list[str] = []
    required_markers = {
        "api-dataset-collection.md": [
            "openalex_id,title,authors,doi,cited_by_count,publication_date,work_type,abstract,source_url,date_accessed",
            "templates/data-dictionary.csv",
            "templates/data-package.json",
            "templates/api-request-log.csv",
            "templates/evidence-ledger.csv",
        ],
        "scientific-literature-review.md": [
            "sub_question,query,tool,date,results_reviewed,candidate_sources,kept_sources,notes",
            "id,title,authors_or_org,year_or_date,url_or_doi,source_type,included,exclusion_reason,relevance_score,quality_score,notes",
            "templates/evidence-ledger.csv",
            "templates/prisma-flow.json",
        ],
        "large-scale-crawl.md": [
            "url,canonical_url,discovered_from,discovery_method,depth,http_status,robots_status,access_status,content_type,content_hash,date_accessed,terminal_state,blocker_reason",
            "source_url,target_url,target_origin,link_type,in_scope,reason",
            "terminal_total = success + blocked + failed + skipped",
            "templates/api-request-log.csv",
            "templates/evidence-ledger.csv",
        ],
    }
    forbidden_patterns = {
        "api-dataset-collection.md": [
            r"Store\s+[\d,]+\s+papers",
            r"~\s*\d+(?:\.\d+)?%\s+recall",
            r"\d[\d,]*\s+papers saved",
        ],
        "scientific-literature-review.md": [
            r"Found:\s*[\d,]+\s+papers",
            r"This systematic review synthesizes\s+[\d,]+\s+studies",
            r"Result\*\*:\s*[\d,]+",
        ],
        "large-scale-crawl.md": [
            r"Output Summary\*\*:\s*[\d,]+\s+pages",
            r"Discovers\s+[\d,]+\s+URLs",
            r"summarizing:\s*[\d,]+\s+successful",
        ],
    }
    for name, markers in required_markers.items():
        path = root / "examples" / name
        if not path.is_file():
            errors.append(f"missing canonical example: examples/{name}")
            continue
        text = path.read_text(encoding="utf-8")
        for marker in markers:
            if marker not in text:
                errors.append(f"examples/{name} missing canonical marker: {marker}")
        for pattern in forbidden_patterns[name]:
            if re.search(pattern, text, flags=re.IGNORECASE):
                errors.append(
                    f"examples/{name} contains unverified result claim matching {pattern!r}"
                )
    return errors


def check_reference_structure(root: Path = ROOT) -> list[str]:
    """Keep routed references bounded and navigable as the skill evolves."""
    errors: list[str] = []
    for path in sorted((root / "references").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        line_count = len(text.splitlines())
        relative = path.relative_to(root)
        if line_count > _REFERENCE_LINE_MAX:
            errors.append(
                f"{relative} has {line_count} lines; split references above "
                f"{_REFERENCE_LINE_MAX} lines"
            )
        if line_count >= _REFERENCE_TOC_MIN and not re.search(
            r"^## (?:Contents|Table of [Cc]ontents)\s*$",
            text,
            flags=re.MULTILINE,
        ):
            errors.append(
                f"{relative} has {line_count} lines but no early contents navigation"
            )
        if line_count >= _REFERENCE_SEE_ALSO_MIN and not re.search(
            r"^## See also\s*$",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        ):
            errors.append(f"{relative} has {line_count} lines but no '## See also' navigation")
    return errors


def check_readme_tree_paths(root: Path = ROOT) -> list[str]:
    """Validate every path explicitly shown in the README repository tree."""
    errors: list[str] = []
    readme_path = root / "README.md"
    if not readme_path.is_file():
        return ["README.md is missing"]
    readme = readme_path.read_text(encoding="utf-8")
    blocks = re.findall(r"```(?:text)?\s*\n(.*?)```", readme, flags=re.DOTALL)
    tree_blocks = [
        block for block in blocks if re.search(r"^(?:d-research/|\.)\s*$", block, re.MULTILINE)
    ]
    if not tree_blocks:
        return ["README.md is missing the fenced repository tree"]

    for block in tree_blocks:
        directories: list[str] = []
        for line in block.splitlines():
            match = re.match(r"^((?:(?:│   )|(?:    ))*)(?:├── |└── )(.+)$", line)
            if not match:
                continue
            depth = len(match.group(1)) // 4
            item = re.split(r"\s{2,}#", match.group(2), maxsplit=1)[0].strip()
            if not item:
                continue
            is_dir = item.endswith("/")
            name = item[:-1] if is_dir else item
            parent = directories[:depth]
            relative = Path(*parent, name)
            target = root / relative
            if is_dir and not target.is_dir():
                errors.append(f"README tree directory does not exist: {relative.as_posix()}/")
            elif not is_dir and not target.is_file():
                errors.append(f"README tree file does not exist: {relative.as_posix()}")
            if is_dir:
                directories = parent + [name]
    return errors


def check_required_paths() -> list[str]:
    errors: list[str] = []
    required = [
        "templates/research-plan.json",
        "templates/evidence-ledger.csv",
        "templates/route-manifest.json",
        "scripts/research_plan.py",
        "scripts/report_render.py",
        "scripts/evidence_ledger.py",
        "scripts/api_fetch.mjs",
        "scripts/check_contract.py",
        "SKILL.md",
        "AGENTS.md",
        "docs/upgrade-v3.1.1-to-v3.2.0.md",
        "examples/fixtures/v3.1.1-workspace/research-plan.json",
        "examples/fixtures/v3.1.1-workspace/PLAN.md",
        "examples/fixtures/research-plan-oai-pmh-example.json",
        "references/workflow-routes.md",
        "references/script-inventory.md",
        "references/config-reference.md",
    ]
    for rel in required:
        if not (ROOT / rel).exists():
            errors.append(f"missing required path: {rel}")

    plan = _load_json(ROOT / "templates/research-plan.json")
    if plan.get("schema_version") != "2.0":
        errors.append("templates/research-plan.json must have schema_version 2.0")
    if plan.get("tasks"):
        errors.append("templates/research-plan.json draft must have empty tasks")

    # Canonical ledger header 23 columns
    ledger_header = (
        (ROOT / "templates/evidence-ledger.csv").read_text(encoding="utf-8").splitlines()[0]
    )
    cols = ledger_header.split(",")
    if "record_type" not in cols:
        errors.append("templates/evidence-ledger.csv must include record_type column")
    if len(cols) != 23:
        errors.append(f"templates/evidence-ledger.csv must have 23 columns, got {len(cols)}")

    # OAI-PMH fixture must be real schema 2.0 with explicit phases
    oai = ROOT / "examples/fixtures/research-plan-oai-pmh-example.json"
    if oai.is_file():
        try:
            data = _load_json(oai)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"OAI-PMH fixture unreadable: {exc}")
        else:
            if data.get("schema_version") != "2.0":
                errors.append("OAI-PMH fixture must have schema_version 2.0")
            tasks = data.get("tasks") or []
            if not tasks:
                errors.append("OAI-PMH fixture must contain tasks")
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                if t.get("phase") not in {"research", "synthesis"}:
                    errors.append(f"OAI-PMH fixture task {t.get('id')!r} missing explicit phase")
    return errors


def check_gate_template_drift() -> list[str]:
    errors: list[str] = []
    manifest = _load_json(ROOT / "templates" / "route-manifest.json")
    plan = _load_json(ROOT / "templates" / "research-plan.json")
    canonical = manifest.get("canonical_gates") or {}
    gates = plan.get("gates") or {}
    for gname, required in canonical.items():
        if gname == "dispatch_ready":
            # alias of execute_ready may be present as execute_ready only
            present = gates.get("dispatch_ready") or gates.get("execute_ready")
            if not present:
                errors.append("template missing execute_ready/dispatch_ready gate")
                continue
            assertions = set(present.get("assertions") or [])
        else:
            if gname not in gates:
                errors.append(f"template missing gate {gname}")
                continue
            assertions = set(gates[gname].get("assertions") or [])
        missing = set(required) - assertions
        if missing:
            errors.append(f"template gate {gname} missing required assertions: {sorted(missing)}")
    return errors


def collect_errors(
    release_tag: str | None = None,
    candidate_commit: str | None = None,
    baseline_commit: str | None = None,
    candidate_tag_object: str | None = None,
    baseline_tag_object: str | None = None,
) -> list[str]:
    errors: list[str] = []
    errors.extend(scan_repo_controls())
    errors.extend(check_ruff_pin_sync())
    errors.extend(check_workflow_security())
    errors.extend(check_versions())
    errors.extend(check_config_safety())
    errors.extend(check_skill_and_routes())
    errors.extend(check_repository_contract())
    errors.extend(check_example_metadata())
    errors.extend(check_canonical_examples())
    errors.extend(check_reference_structure())
    errors.extend(check_readme_tree_paths())
    errors.extend(check_required_paths())
    errors.extend(check_gate_template_drift())
    errors.extend(
        check_stable_release_evidence(
            expected_candidate_commit=candidate_commit,
            expected_baseline_commit=baseline_commit,
            expected_candidate_tag_object=candidate_tag_object,
            expected_baseline_tag_object=baseline_tag_object,
        )
    )
    if release_tag is not None:
        errors.extend(check_release_tag(release_tag))
    return errors


def self_test() -> int:
    """Isolated negative fixtures for control chars and unsafe config."""
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # Negative: control character file
        bad_md = root / "bad.md"
        bad_md.write_bytes(b"hello\x07world\n")
        ctrl_errs = _scan_text_for_controls(
            Path("bad.md"), bad_md.read_text(encoding="utf-8", errors="replace")
        )
        # read with binary then decode may replace BEL - scan bytes path
        raw = bad_md.read_bytes().decode("utf-8")
        ctrl_errs = _scan_text_for_controls(Path("bad.md"), raw)
        if not ctrl_errs:
            failures.append("expected control-char detection for BEL")

        examples_dir = root / "examples"
        examples_dir.mkdir()
        (examples_dir / "missing-status.md").write_text(
            "# Example without metadata\n",
            encoding="utf-8",
        )
        example_errors = check_example_metadata(root)
        if not any("missing YAML metadata" in err for err in example_errors):
            failures.append("expected missing example metadata detection")

        ruff_root = root / "ruff-pin-drift"
        (ruff_root / ".github" / "workflows").mkdir(parents=True)
        (ruff_root / "pyproject.toml").write_text(
            '[project.optional-dependencies]\ndev = ["ruff==0.15.21"]\n',
            encoding="utf-8",
        )
        ruff_workflow = ruff_root / ".github" / "workflows" / "lint-and-self-test.yml"
        ruff_workflow.write_text(
            'steps:\n  - run: python -m pip install "ruff==0.15.13"\n',
            encoding="utf-8",
        )
        ruff_errors = check_ruff_pin_sync(ruff_root)
        if not any("Ruff pin mismatch" in error for error in ruff_errors):
            failures.append("expected mismatched Ruff pins to fail")
        ruff_workflow.write_text(
            'steps:\n  - run: python -m pip install "ruff==0.15.21"\n',
            encoding="utf-8",
        )
        if check_ruff_pin_sync(ruff_root):
            failures.append("expected synchronized Ruff pins to pass")

        workflow_root = root / "workflow-security"
        workflow_dir = workflow_root / ".github" / "workflows"
        workflow_dir.mkdir(parents=True)
        workflow_names = (
            "lint-and-self-test.yml",
            "release-source-archive.yml",
            "release-attest.yml",
        )
        for workflow_name in workflow_names:
            (workflow_dir / workflow_name).write_bytes(
                (ROOT / ".github" / "workflows" / workflow_name).read_bytes()
            )
        workflow_errors = check_workflow_security(workflow_root)
        if workflow_errors:
            failures.append(
                "valid workflow security contract rejected: "
                + "; ".join(workflow_errors[:3])
            )
        ci_security_path = workflow_dir / "lint-and-self-test.yml"
        original_ci_security = ci_security_path.read_text(encoding="utf-8")
        ci_security_path.write_text(
            original_ci_security.replace(
                "persist-credentials: false", "persist-credentials: true", 1
            ),
            encoding="utf-8",
        )
        if not any(
            "disable credential persistence" in error
            for error in check_workflow_security(workflow_root)
        ):
            failures.append("expected persisted CI checkout credentials to fail")
        ci_security_path.write_text(original_ci_security, encoding="utf-8")
        release_security_path = workflow_dir / "release-source-archive.yml"
        original_release_security = release_security_path.read_text(encoding="utf-8")
        release_security_path.write_text(
            original_release_security + "\n# id-token: write\n",
            encoding="utf-8",
        )
        if not any(
            "unprivileged" in error for error in check_workflow_security(workflow_root)
        ):
            failures.append("expected privileged tag workflow to fail")
        release_security_path.write_text(original_release_security, encoding="utf-8")
        attest_security_path = workflow_dir / "release-attest.yml"
        original_attest_security = attest_security_path.read_text(encoding="utf-8")
        attest_security_path.write_text(
            original_attest_security.replace("$GITHUB_EVENT_PATH", "$EVENT_PATH"),
            encoding="utf-8",
        )
        if not any(
            "GITHUB_EVENT_PATH" in error
            for error in check_workflow_security(workflow_root)
        ):
            failures.append("expected derived attestation event path to fail")
        attest_security_path.write_text(original_attest_security, encoding="utf-8")
        attest_security_path.write_text(
            original_attest_security.replace(
                "      # This privileged job intentionally has no checkout or run step.\n",
                "      - name: Unsafe repository command\n        run: ./from-tag.sh\n",
                1,
            ),
            encoding="utf-8",
        )
        if not any(
            "must not contain shell or run steps" in error
            for error in check_workflow_security(workflow_root)
        ):
            failures.append("expected privileged attestation run step to fail")

        references_dir = root / "references"
        references_dir.mkdir()
        (references_dir / "long.md").write_text(
            "# Long\n" + ("body\n" * _REFERENCE_SEE_ALSO_MIN),
            encoding="utf-8",
        )
        reference_errors = check_reference_structure(root)
        if not any("no early contents" in err for err in reference_errors):
            failures.append("expected long-reference contents navigation detection")
        if not any("no '## See also'" in err for err in reference_errors):
            failures.append("expected long-reference navigation detection")

        (root / "README.md").write_text(
            "# Test\n\n```\n.\n└── missing.md  # stale path\n```\n",
            encoding="utf-8",
        )
        tree_errors = check_readme_tree_paths(root)
        if not any("missing.md" in err for err in tree_errors):
            failures.append("expected stale README tree path detection")

        # Route/agent semantics must be bound to the machine-readable manifest,
        # not merely contain the same filenames and gate names somewhere.
        route_root = root / "route-drift"
        (route_root / "templates").mkdir(parents=True)
        for name in ("SKILL.md", "AGENTS.md", "README.vi.md"):
            (route_root / name).write_text(
                (ROOT / name).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        (route_root / "agents").mkdir()
        (route_root / "agents" / "openai.yaml").write_text(
            (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        route_manifest = _load_json(ROOT / "templates" / "route-manifest.json")
        (route_root / "templates" / "route-manifest.json").write_text(
            json.dumps(route_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        route_refs = set(route_manifest.get("required_skill_references") or [])
        for route in route_manifest.get("routes") or []:
            if route.get("reference"):
                route_refs.add(route["reference"])
            route_refs.update(route.get("references") or [])
        for relative in route_refs:
            target = route_root / relative
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                if relative in {
                    "references/research-intake.md",
                    "references/research-plan-protocol.md",
                }:
                    target.write_text(
                        (ROOT / relative).read_text(encoding="utf-8"),
                        encoding="utf-8",
                    )
                else:
                    target.write_text("# self-test route\n", encoding="utf-8")
        if check_skill_and_routes(route_root):
            failures.append("expected clean manifest-bound route fixture to pass")

        drifted_manifest = json.loads(json.dumps(route_manifest))
        drifted_manifest["routes"][0]["intake_labels"] = []
        (route_root / "templates" / "route-manifest.json").write_text(
            json.dumps(drifted_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        intake_drift = check_skill_and_routes(route_root)
        if not any("intake mapping missing labels" in error for error in intake_drift):
            failures.append("expected missing intake-label mapping to fail")
        (route_root / "templates" / "route-manifest.json").write_text(
            json.dumps(route_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        agents_path = route_root / "AGENTS.md"
        clean_agents = agents_path.read_text(encoding="utf-8")
        agents_path.write_text(
            clean_agents.replace(
                "Do not dispatch until `execute_ready`/`dispatch_ready` passes;",
                "Dispatch before `execute_ready`/`dispatch_ready` passes;",
            ),
            encoding="utf-8",
        )
        agent_drift = check_skill_and_routes(route_root)
        if not any("AGENTS.md semantic drift" in error for error in agent_drift):
            failures.append("expected semantic dispatch drift in AGENTS.md to fail")
        agents_path.write_text(clean_agents, encoding="utf-8")

        skill_path = route_root / "SKILL.md"
        clean_skill = skill_path.read_text(encoding="utf-8")
        skill_path.write_text(
            clean_skill.replace(
                "| Atomic fact | `references/fact-verification.md` |",
                "<!-- removed atomic-fact route -->",
            ),
            encoding="utf-8",
        )
        skill_drift = check_skill_and_routes(route_root)
        if not any("route table drift" in error for error in skill_drift):
            failures.append("expected missing SKILL.md route-table row to fail")

        # Negative: bare CR
        bare = "line1\rline2\n"
        if not _scan_text_for_controls(Path("cr.txt"), bare):
            failures.append("expected bare CR detection")

        # Positive: CRLF OK
        if _scan_text_for_controls(Path("crlf.txt"), "a\r\nb\n"):
            failures.append("CRLF should be allowed")

        # Negative: synchronized package metadata must not make stale release
        # docs/changelog pass. The expected release surface is derived from the
        # package version, never hard-coded to the current RC.
        version_root = root / "version-drift"
        (version_root / "docs").mkdir(parents=True)
        (version_root / "package.json").write_text(
            json.dumps(
                {
                    "version": "9.9.9",
                    "engines": {"node": ">=18"},
                    "dependencies": {"playwright": "1.61.1"},
                }
            ),
            encoding="utf-8",
        )
        (version_root / "package-lock.json").write_text(
            json.dumps(
                {
                    "version": "9.9.9",
                    "packages": {
                        "": {
                            "version": "9.9.9",
                            "dependencies": {"playwright": "1.61.1"},
                        },
                        "node_modules/playwright": {"version": "1.61.1"},
                    },
                }
            ),
            encoding="utf-8",
        )
        (version_root / "pyproject.toml").write_text(
            '[project]\nversion = "9.9.9"\nclassifiers = '
            '["Development Status :: 5 - Production/Stable"]\n',
            encoding="utf-8",
        )
        (version_root / "CHANGELOG.md").write_text(
            "## [3.2.0-rc.1] - 2026-07-10\n",
            encoding="utf-8",
        )
        (version_root / "README.md").write_text("v3.2.0-rc.1\n", encoding="utf-8")
        (version_root / "README.vi.md").write_text("v3.2.0-rc.1\n", encoding="utf-8")
        stale_errors = check_versions(version_root)
        if not any("9.9.9" in error for error in stale_errors):
            failures.append("dynamic version checker failed to reject stale 9.9.9 docs")

        # Stable promotion freezes the executable route contract at the exact
        # dogfooded RC. Only package/release metadata advances to X.Y.Z.
        frozen_manifest = {
            "repository_contract": {"version": "3.2.0-rc.1"},
            "stable_release_gate": {"required_candidate_version": "3.2.0-rc.1"},
        }
        if not _repository_contract_version_matches("3.2.0-rc.1", frozen_manifest):
            failures.append("exact RC repository contract version should match")
        if not _repository_contract_version_matches("3.2.0", frozen_manifest):
            failures.append("stable metadata should accept its frozen dogfooded RC contract")
        if _repository_contract_version_matches("3.2.1", frozen_manifest):
            failures.append("stable metadata must reject a contract from another release line")
        drifted_gate = {
            "repository_contract": {"version": "3.2.0-rc.1"},
            "stable_release_gate": {"required_candidate_version": "3.2.0-rc.2"},
        }
        if _repository_contract_version_matches("3.2.0", drifted_gate):
            failures.append("stable metadata must reject an RC/gate version mismatch")

        valid_live_tags = {
            "baseline_tag": {
                "annotated": True,
                "github_verified": False,
                "bind_tag_object_sha": True,
                "expected_tag_object_sha": "0" * 40,
                "verification_mode": "annotated_tag_object_sha",
            },
            "candidate_tag": {
                "annotated": True,
                "github_verified": True,
                "bind_tag_object_sha": True,
                "verification_mode": "github_verified_tag_object_sha",
            },
            "release_tag": {
                "annotated": True,
                "github_verified": True,
                "bind_tag_object_sha": True,
                "verification_mode": "github_verified_tag_object_sha",
            },
        }
        if _check_live_tag_contracts(valid_live_tags):
            failures.append("valid symmetric live tag contracts were rejected")
        invalid_live_tags = json.loads(json.dumps(valid_live_tags))
        invalid_live_tags["release_tag"]["github_verified"] = False
        if not any(
            "release_tag" in error
            for error in _check_live_tag_contracts(invalid_live_tags)
        ):
            failures.append("unverified stable tag contract was accepted")

        # Stable-only live-dogfood gate. All synthetic artefacts stay in this
        # temporary directory and are never release evidence.
        stable_root = root / "stable-evidence"
        (stable_root / "scripts").mkdir(parents=True)
        (stable_root / "templates").mkdir(parents=True)
        (stable_root / "examples" / "evals" / "fixtures").mkdir(parents=True)
        (stable_root / "scripts" / "run_dogfood.py").write_bytes(
            (ROOT / "scripts" / "run_dogfood.py").read_bytes()
        )
        for relative in (
            "examples/evals/dogfood-bench.json",
            "examples/evals/frontier-bench.json",
            "examples/evals/fixtures/dogfood-empty-scores.json",
            "examples/evals/fixtures/frontier-empty-scores.json",
            "templates/evidence-ledger.csv",
        ):
            destination = stable_root / relative
            destination.write_bytes((ROOT / relative).read_bytes())
        stable_gate = {
            "promotion_manifest_path": "release-evidence/v{version}/promotion.json",
            "required_baseline_version": "3.1.1",
            "required_candidate_version": "3.2.0-rc.1",
            "full_ci": {
                "workflow_path": ".github/workflows/lint-and-self-test.yml",
                "exact_candidate_sha": True,
                "exact_release_sha": True,
                "required_conclusion": "success",
            },
            "run_evidence": {
                "canonical_layout": True,
                "manifest_name": "run-result.json",
                "run_result_schema_version": "2.1",
                "bind_raw_artifacts": True,
                "recompute_scores": True,
            },
            "baseline_tag": {
                "annotated": True,
                "github_verified": False,
                "bind_tag_object_sha": True,
                "expected_tag_object_sha": "5" * 40,
                "verification_mode": "annotated_tag_object_sha",
            },
            "candidate_tag": {
                "annotated": True,
                "github_verified": True,
                "bind_tag_object_sha": True,
            },
            "reviewer_attestation": {
                "type": "github_verified_pull_request_review",
                "repository": "d-init-d/d-research-skill",
                "bind_exact_release_sha": True,
                "bind_promotion_sha256": True,
            },
            "tiers": {
                "tier1": {
                    "bench_path": "examples/evals/dogfood-bench.json",
                    "expected_tier": "regression",
                    "pass_threshold": 0.7,
                },
                "tier2": {
                    "bench_path": "examples/evals/frontier-bench.json",
                    "expected_tier": "frontier",
                    "pass_threshold": None,
                },
            },
        }
        (stable_root / "templates" / "route-manifest.json").write_text(
            json.dumps({"stable_release_gate": stable_gate}, indent=2) + "\n",
            encoding="utf-8",
        )
        (stable_root / "package.json").write_text(
            json.dumps({"version": "3.2.0-rc.1"}) + "\n",
            encoding="utf-8",
        )
        if check_stable_release_evidence(stable_root):
            failures.append("RC metadata must not require stable live-dogfood artefacts")
        (stable_root / "package.json").write_text(
            json.dumps({"version": "3.2.0"}) + "\n",
            encoding="utf-8",
        )
        missing_stable = check_stable_release_evidence(stable_root)
        if not any("promotion manifest" in error for error in missing_stable):
            failures.append("stable metadata must fail without a promotion manifest")

        evidence_dir = stable_root / "release-evidence" / "v3.2.0"
        evidence_dir.mkdir(parents=True)
        runtime = {
            "agent": "contract-self-test",
            "model": "offline-fixture",
            "version": "1",
            "tool_config_hash": "sha256:" + ("a" * 64),
        }
        baseline_commit = "1" * 40
        candidate_commit = "2" * 40
        candidate_tag_object = "3" * 40
        baseline_tag_object = "5" * 40
        selftest_harness = _load_eval_harness(stable_root)

        score_paths: dict[tuple[str, str], Path] = {}
        run_paths: dict[tuple[str, str], Path] = {}
        canonical_ledger_header = (
            (stable_root / "templates" / "evidence-ledger.csv")
            .read_text(encoding="utf-8")
            .splitlines()[0]
            + "\n"
        )
        canonical_ledger_columns = next(csv.reader([canonical_ledger_header]))
        bundle_hours = {
            ("tier1", "baseline"): 0,
            ("tier1", "candidate"): 2,
            ("tier2", "baseline"): 4,
            ("tier2", "candidate"): 6,
        }
        for tier_name in ("tier1", "tier2"):
            bench_path = stable_root / stable_gate["tiers"][tier_name]["bench_path"]
            bench = _load_json(bench_path)
            bench_fingerprint = selftest_harness.bench_fingerprint(bench)
            factual_task_id = next(
                str(task["task_id"])
                for task in sorted(bench["tasks"], key=lambda item: item["task_id"])
                if task.get("expected_action") != "refuse"
            )
            for side, commit in (
                ("baseline", baseline_commit),
                ("candidate", candidate_commit),
            ):
                runs_dir = evidence_dir / "runs" / f"{tier_name}-{side}"
                for index, task in enumerate(
                    sorted(bench["tasks"], key=lambda item: item["task_id"])
                ):
                    task_id = str(task["task_id"])
                    task_dir = runs_dir / task_id
                    task_dir.mkdir(parents=True)
                    prompt_path = task_dir / "raw-prompt.txt"
                    output_path = task_dir / "raw-output.txt"
                    ledger_path = task_dir / "evidence-ledger.csv"
                    with ledger_path.open("w", encoding="utf-8", newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=canonical_ledger_columns)
                        writer.writeheader()
                        if task_id == factual_task_id:
                            assertion_fields: dict[str, list[str]] = {}
                            for assertion in task.get("required_assertions", []):
                                if not isinstance(assertion, dict):
                                    continue
                                field = assertion.get("field")
                                values = assertion.get("required_values")
                                if isinstance(field, str) and isinstance(values, list):
                                    assertion_fields.setdefault(field, []).extend(
                                        str(value) for value in values
                                    )
                            for source_index, source_group in enumerate(
                                task.get("ground_truth_sources", [])
                            ):
                                if not isinstance(source_group, dict):
                                    continue
                                row = {column: "" for column in canonical_ledger_columns}
                                row["claim_id"] = f"SELFTEST-{tier_name}-{source_index + 1}"
                                row["source_url"] = str(source_group.get("canonical") or "")
                                row["source_type"] = "official"
                                row["access_method"] = "offline_fixture"
                                row["confidence"] = "high"
                                row["record_type"] = "claim"
                                for field, values in assertion_fields.items():
                                    if field in row:
                                        row[field] = " | ".join(values)
                                writer.writerow(row)
                    prompt_path.write_bytes(
                        selftest_harness.render_task_prompt(bench, task).encode("utf-8")
                    )
                    output_path.write_text("Request refused safely.\n" if task.get(
                        "expected_action"
                    ) == "refuse" else "No supported claim found.\n", encoding="utf-8")
                    refused = task.get("expected_action") == "refuse"
                    hour = bundle_hours[(tier_name, side)]
                    manifest = {
                        "schema_version": "2.1",
                        "task_id": task_id,
                        "status": "refused" if refused else "completed",
                        "ledger_path": ledger_path.name,
                        "ledger_sha256": _sha256_path(ledger_path),
                        "raw_prompt_path": prompt_path.name,
                        "raw_prompt_sha256": _sha256_path(prompt_path),
                        "raw_output_path": output_path.name,
                        "raw_output_sha256": _sha256_path(output_path),
                        "run_id": f"contract-run-{side}-{tier_name}-{task_id}",
                        "session_id": f"contract-session-{side}-{tier_name}-{task_id}",
                        "runtime": dict(runtime),
                        "skill_commit": commit,
                        "evaluator_binding": {
                            "bench_fingerprint": bench_fingerprint,
                            "bench_version": bench.get("bench_version"),
                            "harness_commit": candidate_commit,
                        },
                        "candidate_binding": {
                            "skill_commit": commit,
                            "version": (
                                "3.1.1" if commit == baseline_commit else "3.2.0-rc.1"
                            ),
                        },
                        "started_at": f"2026-07-09T{hour:02d}:00:{index:02d}Z",
                        "finished_at": f"2026-07-09T{hour:02d}:01:{index:02d}Z",
                    }
                    if refused:
                        manifest["reason_code"] = "unsafe_request"
                    (task_dir / "run-result.json").write_text(
                        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )

                score = selftest_harness.build_score_record(
                    bench,
                    runs_dir,
                    threshold=(0.7 if tier_name == "tier1" else None),
                    frozen_timestamp="2026-07-09T10:00:00Z",
                    canonical_layout=True,
                )
                score_errors = selftest_harness.validate_score_file(score)
                if score_errors:
                    failures.append(
                        f"self-test could not build valid {tier_name}/{side} raw evidence: "
                        + "; ".join(score_errors[:3])
                    )
                score_path = evidence_dir / f"{tier_name}-{side}-scores.json"
                score_path.write_text(
                    json.dumps(score, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                score_paths[(tier_name, side)] = score_path
                run_paths[(tier_name, side)] = runs_dir

        promotion_path = evidence_dir / "promotion.json"
        signoff_path = evidence_dir / "reviewer-signoff.json"
        promotion = {
            "schema_version": "1.2",
            "release_version": "3.2.0",
            "baseline_version": "3.1.1",
            "candidate_version": "3.2.0-rc.1",
            "baseline_skill_commit": baseline_commit,
            "candidate_skill_commit": candidate_commit,
            "baseline_tag": "v3.1.1",
            "baseline_tag_object_sha": baseline_tag_object,
            "candidate_tag": "v3.2.0-rc.1",
            "candidate_tag_object_sha": candidate_tag_object,
            "generated_at": "2026-07-09T12:00:00Z",
            "tiers": {},
            "reviewer_signoff_path": signoff_path.relative_to(stable_root).as_posix(),
        }

        def write_promotion_and_signoff() -> None:
            promotion["tiers"] = {}
            for tier_name in ("tier1", "tier2"):
                promotion["tiers"][tier_name] = {}
                for side in ("baseline", "candidate"):
                    score_path = score_paths[(tier_name, side)]
                    promotion["tiers"][tier_name][f"{side}_scores"] = {
                        "path": score_path.relative_to(stable_root).as_posix(),
                        "sha256": _sha256_path(score_path),
                    }
                    promotion["tiers"][tier_name][f"{side}_runs_path"] = (
                        run_paths[(tier_name, side)]
                        .relative_to(stable_root)
                        .as_posix()
                    )
            promotion_path.write_text(
                json.dumps(promotion, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            signoff = {
                "schema_version": "1.2",
                "release_version": "3.2.0",
                "decision": "approved",
                "reviewer": {"name": "Contract self-test", "role": "test fixture"},
                "reviewed_at": "2026-07-09T13:00:00Z",
                "promotion_manifest_sha256": _sha256_path(promotion_path),
                "review_scope": {
                    "live_run_origin_verified": True,
                    "raw_artifacts_reviewed": True,
                    "score_recomputation_reviewed": True,
                },
                "attestation": {
                    "type": "github_verified_pull_request_review",
                    "repository": "d-init-d/d-research-skill",
                    "pull_request_number": 7,
                    "reviewer_login": "independent-reviewer",
                },
            }
            signoff_path.write_text(
                json.dumps(signoff, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

        write_promotion_and_signoff()
        valid_stable = check_stable_release_evidence(stable_root)
        if valid_stable:
            failures.append(
                "expected complete synthetic stable contract to pass: "
                + "; ".join(valid_stable[:3])
            )

        commit_binding_mismatch = check_stable_release_evidence(
            stable_root,
            expected_candidate_commit="3" * 40,
            expected_baseline_commit=baseline_commit,
        )
        if not any(
            "must match the release workflow commit" in error for error in commit_binding_mismatch
        ):
            failures.append("stable gate must bind promotion commits to release refs")
        tag_object_mismatch = check_stable_release_evidence(
            stable_root,
            expected_candidate_tag_object="4" * 40,
        )
        if not any("annotated RC tag object" in error for error in tag_object_mismatch):
            failures.append("stable gate must bind the exact annotated RC tag object")
        baseline_tag_object_mismatch = check_stable_release_evidence(
            stable_root,
            expected_baseline_tag_object="6" * 40,
        )
        if not any(
            "annotated baseline tag object" in error
            for error in baseline_tag_object_mismatch
        ):
            failures.append("stable gate must bind the exact annotated baseline tag object")

        # Raw-evidence anti-bypass checks: every hash-sensitive JSON document and
        # canonical run artifact must fail closed when its interpretation drifts.
        valid_promotion_bytes = promotion_path.read_bytes()
        promotion_path.write_bytes(
            valid_promotion_bytes.replace(
                b'"schema_version": "1.2",',
                b'"schema_version": "1.2",\n  "schema_version": "1.2",',
                1,
            )
        )
        duplicate_promotion = check_stable_release_evidence(stable_root)
        if not any("duplicate key" in error for error in duplicate_promotion):
            failures.append("stable gate accepted a duplicate-key promotion manifest")
        write_promotion_and_signoff()

        sample_runs_dir = run_paths[("tier1", "candidate")]
        sample_task_dir = next(
            path for path in sorted(sample_runs_dir.iterdir()) if path.is_dir()
        )
        sample_output = sample_task_dir / "raw-output.txt"
        valid_output_bytes = sample_output.read_bytes()
        sample_output.write_bytes(valid_output_bytes + b"tampered\n")
        tampered_output = check_stable_release_evidence(stable_root)
        if not any("raw_output_sha256" in error for error in tampered_output):
            failures.append("stable gate accepted a raw-output hash mismatch")
        sample_output.write_bytes(valid_output_bytes)

        sample_prompt = sample_task_dir / "raw-prompt.txt"
        sample_manifest = sample_task_dir / "run-result.json"
        valid_prompt_bytes = sample_prompt.read_bytes()
        valid_manifest_bytes = sample_manifest.read_bytes()
        wrong_harness_manifest = _strict_json_bytes(
            valid_manifest_bytes, "self-test run manifest"
        )
        wrong_harness_manifest["evaluator_binding"]["harness_commit"] = "4" * 40
        sample_manifest.write_text(
            json.dumps(wrong_harness_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        wrong_harness_errors = check_stable_release_evidence(stable_root)
        if not any(
            "harness_commit must match the frozen candidate" in error
            for error in wrong_harness_errors
        ):
            failures.append("stable gate accepted a non-candidate evaluator harness")
        sample_manifest.write_bytes(valid_manifest_bytes)
        peer_task_dir = next(
            path
            for path in sorted(sample_runs_dir.iterdir())
            if path.is_dir() and path != sample_task_dir
        )
        peer_manifest = _load_strict_json(
            peer_task_dir / "run-result.json", "self-test peer run manifest"
        )
        equivalent_offset_manifest = _strict_json_bytes(
            valid_manifest_bytes, "self-test run manifest"
        )
        equivalent_offset_manifest["started_at"] = str(
            peer_manifest["started_at"]
        ).replace("Z", "+00:00")
        equivalent_offset_manifest["finished_at"] = str(
            peer_manifest["finished_at"]
        ).replace("Z", "+00:00")
        sample_manifest.write_text(
            json.dumps(equivalent_offset_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        equivalent_offset_errors = check_stable_release_evidence(stable_root)
        if not any(
            "reuses a global timestamp pair" in error
            for error in equivalent_offset_errors
        ):
            failures.append(
                "stable gate accepted duplicate instants with equivalent offsets"
            )
        sample_manifest.write_bytes(valid_manifest_bytes)
        sample_prompt.write_bytes(valid_prompt_bytes + b"tampered\n")
        prompt_manifest = _strict_json_bytes(valid_manifest_bytes, "self-test run manifest")
        prompt_manifest["raw_prompt_sha256"] = _sha256_path(sample_prompt)
        sample_manifest.write_text(
            json.dumps(prompt_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        noncanonical_prompt = check_stable_release_evidence(stable_root)
        if not any("raw prompt is not the canonical" in error for error in noncanonical_prompt):
            failures.append("stable gate accepted a noncanonical raw prompt")
        sample_prompt.write_bytes(valid_prompt_bytes)
        sample_manifest.write_bytes(valid_manifest_bytes)

        sample_ledger = sample_task_dir / "evidence-ledger.csv"
        valid_ledger_bytes = sample_ledger.read_bytes()
        sample_ledger.write_text("source_url\n", encoding="utf-8")
        ledger_manifest = _strict_json_bytes(valid_manifest_bytes, "self-test run manifest")
        ledger_manifest["ledger_sha256"] = _sha256_path(sample_ledger)
        sample_manifest.write_text(
            json.dumps(ledger_manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        noncanonical_ledger = check_stable_release_evidence(stable_root)
        if not any("exact canonical 23-column header" in error for error in noncanonical_ledger):
            failures.append("stable gate accepted a noncanonical evidence ledger")
        sample_ledger.write_bytes(valid_ledger_bytes)
        sample_manifest.write_bytes(valid_manifest_bytes)

        unexpected_artifact = sample_task_dir / "unexpected.txt"
        unexpected_artifact.write_text("not allowed\n", encoding="utf-8")
        extra_artifact = check_stable_release_evidence(stable_root)
        if not any("artifacts must be exactly" in error for error in extra_artifact):
            failures.append("stable gate accepted an extra raw-run artifact")
        unexpected_artifact.unlink()

        sample_score_path = score_paths[("tier1", "candidate")]
        valid_score_bytes = sample_score_path.read_bytes()
        threshold_score = _strict_json_bytes(valid_score_bytes, "self-test score")
        threshold_score["pass_threshold"] = 0.0
        sample_score_path.write_text(
            json.dumps(threshold_score, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_promotion_and_signoff()
        threshold_bypass = check_stable_release_evidence(stable_root)
        if not any("pass_threshold must be frozen" in error for error in threshold_bypass):
            failures.append("stable gate accepted a score-controlled pass threshold")
        sample_score_path.write_bytes(valid_score_bytes)
        write_promotion_and_signoff()

        late_score = _strict_json_bytes(valid_score_bytes, "self-test score")
        late_score["created_at"] = "2026-07-09T13:00:00Z"
        sample_score_path.write_text(
            json.dumps(late_score, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_promotion_and_signoff()
        late_score_errors = check_stable_release_evidence(stable_root)
        if not any(
            "must not follow promotion generated_at" in error
            for error in late_score_errors
        ):
            failures.append("stable gate accepted a score created after promotion")

        early_score = _strict_json_bytes(valid_score_bytes, "self-test score")
        early_score["created_at"] = "2026-07-09T00:00:00Z"
        sample_score_path.write_text(
            json.dumps(early_score, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_promotion_and_signoff()
        early_score_errors = check_stable_release_evidence(stable_root)
        if not any("finishes after score created_at" in error for error in early_score_errors):
            failures.append("stable gate accepted a score created before its raw runs finished")
        sample_score_path.write_bytes(valid_score_bytes)
        write_promotion_and_signoff()

        # Post-RC path allowlist: metadata/evidence only; code drift must fail.
        allowed_only = validate_post_rc_changed_paths(
            [
                "package.json",
                "package-lock.json",
                "pyproject.toml",
                "CHANGELOG.md",
                "README.md",
                "README.vi.md",
                "docs/release-v3.2.0.md",
                "release-evidence/v3.2.0/promotion.json",
                "release-evidence/v3.2.0/tier1-candidate-scores.json",
            ],
            "3.2.0",
        )
        if allowed_only:
            failures.append(
                "post-RC allowlist rejected valid promotion paths: " + "; ".join(allowed_only)
            )
        code_drift = validate_post_rc_changed_paths(
            [
                "package.json",
                "scripts/research_plan.py",
                "SKILL.md",
                "templates/route-manifest.json",
            ],
            "3.2.0",
        )
        if not any("scripts/research_plan.py" in e for e in code_drift):
            failures.append("post-RC allowlist must reject scripts/ code drift")
        if not any("SKILL.md" in e for e in code_drift):
            failures.append("post-RC allowlist must reject SKILL.md drift")
        if is_allowed_post_rc_change("../evil", "3.2.0"):
            failures.append("post-RC allowlist must reject path traversal")
        if is_allowed_post_rc_change(
            "../release-evidence/v3.2.0/override.json", "3.2.0"
        ):
            failures.append("post-RC allowlist must reject traversal into an allowed prefix")
        for hostile_path in (
            "release-evidence\\v3.2.0\\override.json",
            "C:/release-evidence/v3.2.0/override.json",
            "release-evidence/v3.2.0/file.json:stream",
            "release-evidence/v3.2.0/NUL.json",
            "release-evidence//v3.2.0/override.json",
        ):
            if is_allowed_post_rc_change(hostile_path, "3.2.0"):
                failures.append(
                    f"post-RC allowlist accepted non-portable path {hostile_path!r}"
                )
        if is_allowed_post_rc_change("release-evidence/v3.2.0/", "3.2.0"):
            failures.append("post-RC allowlist must reject evidence directory alone")
        if not validate_post_rc_changed_paths(["scripts/x.py"], "3.2.0-rc.1"):
            failures.append("post-RC allowlist must refuse rc release versions")

        # Post-RC metadata is field-level, not a whole-file allowlist.
        metadata_root = root / "post-rc-metadata"
        metadata_root.mkdir()
        rc_package = {
            "name": "fixture",
            "version": "3.2.0-rc.1",
            "scripts": {"test": "node test.mjs"},
            "dependencies": {"playwright": "1.61.1"},
            "engines": {"node": ">=18"},
        }
        stable_package = json.loads(json.dumps(rc_package))
        stable_package["version"] = "3.2.0"
        rc_lock = {
            "name": "fixture",
            "version": "3.2.0-rc.1",
            "lockfileVersion": 3,
            "packages": {
                "": {
                    "name": "fixture",
                    "version": "3.2.0-rc.1",
                    "dependencies": {"playwright": "1.61.1"},
                },
                "node_modules/playwright": {
                    "version": "1.61.1",
                    "integrity": "sha512-fixture",
                },
            },
        }
        stable_lock = json.loads(json.dumps(rc_lock))
        stable_lock["version"] = "3.2.0"
        stable_lock["packages"][""]["version"] = "3.2.0"
        rc_pyproject = (
            '[build-system]\nrequires = ["setuptools>=68"]\n'
            'build-backend = "setuptools.build_meta"\n\n[project]\n'
            'version = "3.2.0rc1"\nclassifiers = [\n'
            '  "Development Status :: 4 - Beta",\n]\ndependencies = []\n'
        )
        stable_pyproject = rc_pyproject.replace("3.2.0rc1", "3.2.0").replace(
            "Development Status :: 4 - Beta",
            "Development Status :: 5 - Production/Stable",
        )
        candidate_metadata = {
            "package.json": (json.dumps(rc_package, sort_keys=True) + "\n").encode(),
            "package-lock.json": (json.dumps(rc_lock, sort_keys=True) + "\n").encode(),
            "pyproject.toml": rc_pyproject.encode(),
        }

        def write_release_metadata(
            package: dict = stable_package,
            lock: dict = stable_lock,
            pyproject: str = stable_pyproject,
        ) -> None:
            (metadata_root / "package.json").write_text(
                json.dumps(package, sort_keys=True) + "\n", encoding="utf-8"
            )
            (metadata_root / "package-lock.json").write_text(
                json.dumps(lock, sort_keys=True) + "\n", encoding="utf-8"
            )
            (metadata_root / "pyproject.toml").write_text(pyproject, encoding="utf-8")

        write_release_metadata()
        semantic_valid = validate_post_rc_metadata(candidate_metadata, metadata_root, "3.2.0")
        if semantic_valid:
            failures.append(
                "valid field-level RC promotion rejected: " + "; ".join(semantic_valid)
            )

        lifecycle_package = json.loads(json.dumps(stable_package))
        lifecycle_package["scripts"]["postinstall"] = "node exfiltrate.mjs"
        write_release_metadata(package=lifecycle_package)
        if not any(
            "package.json changed beyond version" in error
            for error in validate_post_rc_metadata(candidate_metadata, metadata_root, "3.2.0")
        ):
            failures.append("post-RC metadata gate accepted a new lifecycle script")

        dependency_package = json.loads(json.dumps(stable_package))
        dependency_package["dependencies"]["supply-chain-drift"] = "1.0.0"
        write_release_metadata(package=dependency_package)
        if not any(
            "package.json changed beyond version" in error
            for error in validate_post_rc_metadata(candidate_metadata, metadata_root, "3.2.0")
        ):
            failures.append("post-RC metadata gate accepted dependency drift")

        write_release_metadata()
        hostile_package = json.dumps(stable_package, sort_keys=True)[:-1] + ', "metric": NaN}'
        (metadata_root / "package.json").write_text(hostile_package, encoding="utf-8")
        if not any(
            "non-finite JSON number" in error
            for error in validate_post_rc_metadata(candidate_metadata, metadata_root, "3.2.0")
        ):
            failures.append("post-RC metadata gate accepted non-finite JSON")

        lock_drift = json.loads(json.dumps(stable_lock))
        lock_drift["packages"]["node_modules/playwright"]["integrity"] = "sha512-changed"
        write_release_metadata(lock=lock_drift)
        if not any(
            "lock graph" in error
            for error in validate_post_rc_metadata(candidate_metadata, metadata_root, "3.2.0")
        ):
            failures.append("post-RC metadata gate accepted lock-graph drift")

        backend_drift = stable_pyproject.replace(
            'build-backend = "setuptools.build_meta"',
            'build-backend = "malicious.backend"',
        )
        write_release_metadata(pyproject=backend_drift)
        if not any(
            "build-system" in error
            for error in validate_post_rc_metadata(candidate_metadata, metadata_root, "3.2.0")
        ):
            failures.append("post-RC metadata gate accepted build-backend drift")

        requirement_drift = stable_pyproject.replace(
            'requires = ["setuptools>=68"]',
            'requires = ["setuptools>=68", "wheel"]',
        )
        write_release_metadata(pyproject=requirement_drift)
        if not any(
            "build-system" in error
            for error in validate_post_rc_metadata(candidate_metadata, metadata_root, "3.2.0")
        ):
            failures.append("post-RC metadata gate accepted build requirement drift")

        mismatched = _load_json(score_paths[("tier2", "candidate")])
        for task in mismatched["tasks"]:
            task["runtime"]["model"] = "different-runtime"
        score_paths[("tier2", "candidate")].write_text(
            json.dumps(mismatched, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_promotion_and_signoff()
        runtime_mismatch = check_stable_release_evidence(stable_root)
        if not any("identical runtime/model/tool" in error for error in runtime_mismatch):
            failures.append("stable gate must reject mismatched runtime/model/tool metadata")

        # Explicit maintainer override: narrow waivers, immutable RC binding,
        # strict JSON, and hash-bound local verification are all fail-closed.
        required_checks = ["contract", "npm_self_test"]
        override_contract = {
            "schema_version": "1.0",
            "manifest_path": "release-evidence/v{version}/maintainer-override.json",
            "allowed_release_version": "3.2.0",
            "required_decision": "approved_with_waivers",
            "required_repository": "d-init-d/d-research-skill",
            "required_maintainer_login": "d-init-d",
            "required_waivers": list(_MAINTAINER_OVERRIDE_WAIVERS),
            "required_checks": required_checks,
            "bind_candidate_commit": True,
            "bind_candidate_tag_object_sha": True,
            "require_annotated_tags": True,
            "require_exact_sha_ci": True,
            "non_waivable": {
                "annotated_candidate_tag": True,
                "annotated_release_tag": True,
                "candidate_tag_object_binding": True,
                "candidate_ancestry": True,
                "exact_release_sha_ci": True,
                "source_archive": True,
                "sha256_manifest": True,
                "provenance_attestation": True,
            },
        }
        stable_gate["promotion_mode"] = "maintainer_override"
        stable_gate["required_candidate_version"] = "3.2.0-rc.3"
        stable_gate["maintainer_override"] = override_contract
        (stable_root / "templates" / "route-manifest.json").write_text(
            json.dumps({"stable_release_gate": stable_gate}, indent=2) + "\n",
            encoding="utf-8",
        )
        local_path = evidence_dir / "local-verification.json"
        override_path = evidence_dir / "maintainer-override.json"
        local_record = {
            "schema_version": "1.0",
            "release_version": "3.2.0",
            "candidate_version": "3.2.0-rc.3",
            "candidate_skill_commit": candidate_commit,
            "candidate_tag_object_sha": candidate_tag_object,
            "generated_at": "2026-07-09T00:05:00Z",
            "environment": {
                "os": "test-os",
                "architecture": "x86_64",
                "python_versions": ["3.10", "3.12"],
                "node_versions": ["20"],
            },
            "commands": [
                {
                    "id": check_id,
                    "command": f"run {check_id}",
                    "runtime": "offline-fixture",
                    "exit_code": 0,
                    "result": "passed",
                }
                for check_id in required_checks
            ],
            "summary": {"passed": len(required_checks), "failed": 0},
        }
        override = {
            "schema_version": "1.0",
            "release_version": "3.2.0",
            "release_tag": "v3.2.0",
            "candidate_version": "3.2.0-rc.3",
            "candidate_skill_commit": candidate_commit,
            "candidate_tag": "v3.2.0-rc.3",
            "candidate_tag_object_sha": candidate_tag_object,
            "repository": "d-init-d/d-research-skill",
            "decision": "approved_with_waivers",
            "maintainer": {"login": "d-init-d", "role": "repository_owner"},
            "authorized_at": "2026-07-09T00:06:00Z",
            "waivers": list(_MAINTAINER_OVERRIDE_WAIVERS),
            "reason": (
                "Repository owner explicitly accepts the documented residual risks "
                "after the complete required local verification suite passed."
            ),
            "risk_acceptance": {
                waiver: f"The repository owner explicitly accepts the residual risk for {waiver}."
                for waiver in _MAINTAINER_OVERRIDE_WAIVERS
            },
            "local_verification": {"path": "", "sha256": ""},
        }

        def write_override() -> None:
            local_path.write_text(
                json.dumps(local_record, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            override["local_verification"] = {
                "path": local_path.relative_to(stable_root).as_posix(),
                "sha256": _sha256_path(local_path),
            }
            override_path.write_text(
                json.dumps(override, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

        write_override()
        override_valid = check_stable_release_evidence(
            stable_root,
            expected_candidate_commit=candidate_commit,
            expected_candidate_tag_object=candidate_tag_object,
        )
        if override_valid:
            failures.append(
                "valid maintainer override rejected: " + "; ".join(override_valid[:3])
            )
        if check_release_waiver("live_dogfood", "v3.2.0", stable_root):
            failures.append("authorized stable release waiver should pass")
        if not check_release_waiver("exact_release_sha_ci", "v3.2.0", stable_root):
            failures.append("non-waivable exact-SHA CI requirement was accepted")
        saved_hard_gates = override_contract["non_waivable"]
        override_contract["non_waivable"] = {}
        (stable_root / "templates" / "route-manifest.json").write_text(
            json.dumps({"stable_release_gate": stable_gate}, indent=2) + "\n",
            encoding="utf-8",
        )
        if not check_release_waiver("live_dogfood", "v3.2.0", stable_root):
            failures.append("release waiver query accepted an empty hard-gate set")
        override_contract["non_waivable"] = saved_hard_gates
        (stable_root / "templates" / "route-manifest.json").write_text(
            json.dumps({"stable_release_gate": stable_gate}, indent=2) + "\n",
            encoding="utf-8",
        )

        override["waivers"] = list(_MAINTAINER_OVERRIDE_WAIVERS[:-1])
        write_override()
        if not any(
            "waivers must exactly match" in error
            for error in check_stable_release_evidence(stable_root)
        ):
            failures.append("maintainer override accepted a missing waiver")
        override["waivers"] = list(_MAINTAINER_OVERRIDE_WAIVERS)

        local_record["commands"][0]["exit_code"] = False
        write_override()
        if not any(
            "exit_code must be integer 0" in error
            for error in check_stable_release_evidence(stable_root)
        ):
            failures.append("maintainer override accepted boolean exit_code")
        local_record["commands"][0]["exit_code"] = 0

        write_override()
        override["local_verification"]["sha256"] = "sha256:" + ("0" * 64)
        override_path.write_text(
            json.dumps(override, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if not any(
            "local verification hash mismatch" in error
            for error in check_stable_release_evidence(stable_root)
        ):
            failures.append("maintainer override accepted a stale local verification hash")

        write_override()
        mismatch_errors = check_stable_release_evidence(
            stable_root,
            expected_candidate_commit="4" * 40,
            expected_candidate_tag_object="5" * 40,
        )
        if not any("annotated RC commit" in error for error in mismatch_errors):
            failures.append("maintainer override failed to bind the RC commit")
        if not any("annotated RC tag object" in error for error in mismatch_errors):
            failures.append("maintainer override failed to bind the RC tag object")

        override_path.write_text(
            '{"schema_version":"1.0","schema_version":"1.0"}\n',
            encoding="utf-8",
        )
        if not any(
            "duplicate key" in error
            for error in check_stable_release_evidence(stable_root)
        ):
            failures.append("maintainer override accepted duplicate JSON keys")

        # Unsafe config must fail the real access validator from research_plan
        rp_path = ROOT / "scripts" / "research_plan.py"
        spec = importlib.util.spec_from_file_location("research_plan_mod", rp_path)
        rp = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(rp)
        unsafe = {
            "access": {
                "allowCaptchaSolving": True,
                "allowStealthEvasion": False,
                "defaultMode": "read-only",
            },
            "crawl": {"respectRobots": True},
        }
        errs = rp.validate_access_config(unsafe)
        if not any("allowCaptchaSolving" in e for e in errs):
            failures.append("validate_access_config must reject allowCaptchaSolving=true")
        unsafe2 = {"access": {}, "crawl": {"respectRobots": False}}
        errs2 = rp.validate_access_config(unsafe2)
        if not any("respectRobots" in e for e in errs2):
            failures.append("validate_access_config must reject respectRobots=false")

    # Live repo must currently pass (or report real errors via main)
    live = collect_errors()
    # self-test of checker does not require live pass; main() does

    if failures:
        print("check_contract self-test FAILED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("check_contract self-test ok")
    # still print live error count for diagnostics
    if live:
        print(f"note: live collect_errors has {len(live)} issue(s); main will fail")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "self-test":
        if len(argv) != 1:
            print("error: self-test takes no additional arguments", file=sys.stderr)
            return 2
        return self_test()

    parser = argparse.ArgumentParser(
        description="Validate the D Research repository and release contract."
    )
    parser.add_argument(
        "--release-tag",
        help=(
            "Validate a vX.Y.Z[-rc.N] tag value against package metadata. "
            "The release workflow separately proves that the tag exists and is "
            "annotated, then applies the frozen verification policy."
        ),
    )
    parser.add_argument(
        "--require-release-waiver",
        choices=_MAINTAINER_OVERRIDE_WAIVERS,
        help=(
            "Exit successfully only when the frozen RC contract explicitly authorizes "
            "this waiver for --release-tag. Non-waivable release gates are rejected."
        ),
    )
    parser.add_argument(
        "--candidate-commit",
        help=(
            "Bind stable promotion evidence to the exact dogfooded RC commit. "
            "Release workflows should pass the required candidate tag commit."
        ),
    )
    parser.add_argument(
        "--baseline-commit",
        help=(
            "Bind stable baseline evidence to the exact tag commit declared by "
            "stable_release_gate.required_baseline_version."
        ),
    )
    parser.add_argument(
        "--candidate-tag-object",
        help="Bind stable promotion evidence to the annotated, verified RC tag object SHA.",
    )
    parser.add_argument(
        "--baseline-tag-object",
        help="Bind stable promotion evidence to the frozen annotated baseline tag object SHA.",
    )
    parser.add_argument(
        "--validate-post-rc-paths",
        metavar="PATHS_FILE",
        help=(
            "Validate a newline-delimited git diff --name-only listing against "
            "the stable post-RC allowlist. Requires --release-version."
        ),
    )
    parser.add_argument(
        "--release-version",
        help="Stable release version (X.Y.Z) for post-RC validation.",
    )
    parser.add_argument(
        "--validate-post-rc-metadata",
        metavar="CANDIDATE_REF",
        help=(
            "Semantically compare package.json, package-lock.json, and pyproject.toml "
            "against a fetched dogfooded RC ref. Requires --release-version."
        ),
    )
    args = parser.parse_args(argv)

    if args.require_release_waiver:
        if not args.release_tag:
            print(
                "error: --require-release-waiver requires --release-tag",
                file=sys.stderr,
            )
            return 2
        waiver_errors = check_release_waiver(
            args.require_release_waiver,
            args.release_tag,
        )
        if waiver_errors:
            print("check_contract release waiver FAILED:", file=sys.stderr)
            for error in waiver_errors:
                print(f"  - {error}", file=sys.stderr)
            return 1
        print(
            "check_contract release waiver ok "
            f"(tag={args.release_tag}, waiver={args.require_release_waiver})"
        )
        return 0

    if args.validate_post_rc_paths:
        if not args.release_version:
            print(
                "error: --validate-post-rc-paths requires --release-version",
                file=sys.stderr,
            )
            return 2
        paths_file = Path(args.validate_post_rc_paths)
        if not paths_file.is_file():
            print(f"error: paths file not found: {paths_file}", file=sys.stderr)
            return 2
        changed = [
            line.strip()
            for line in paths_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        path_errors = validate_post_rc_changed_paths(changed, args.release_version)
        if path_errors:
            print("check_contract post-RC path validation FAILED:", file=sys.stderr)
            for e in path_errors:
                print(f"  - {e}", file=sys.stderr)
            return 1
        print(
            f"check_contract post-RC paths ok "
            f"(version={args.release_version}, files={len(changed)})"
        )
        return 0

    if args.validate_post_rc_metadata:
        if not args.release_version:
            print(
                "error: --validate-post-rc-metadata requires --release-version",
                file=sys.stderr,
            )
            return 2
        try:
            candidate_contents = _git_candidate_metadata(ROOT, args.validate_post_rc_metadata)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        metadata_errors = validate_post_rc_metadata(
            candidate_contents,
            ROOT,
            args.release_version,
        )
        if metadata_errors:
            print("check_contract post-RC metadata validation FAILED:", file=sys.stderr)
            for error in metadata_errors:
                print(f"  - {error}", file=sys.stderr)
            return 1
        print(
            "check_contract post-RC metadata ok "
            f"(candidate={args.validate_post_rc_metadata}, version={args.release_version})"
        )
        return 0

    errors = collect_errors(
        args.release_tag,
        candidate_commit=args.candidate_commit,
        baseline_commit=args.baseline_commit,
        candidate_tag_object=args.candidate_tag_object,
        baseline_tag_object=args.baseline_tag_object,
    )
    if errors:
        print("check_contract FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    skill_lines = len((ROOT / "SKILL.md").read_text(encoding="utf-8").splitlines())
    pkg = _load_json(ROOT / "package.json")
    print(f"check_contract ok (version={pkg.get('version')}, skill_lines={skill_lines})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
