#!/usr/bin/env python3
"""Build and verify deterministic D Research full and runtime artifacts.

The builder is standard-library-only and does not depend on Git. It therefore
works from a repository checkout, a GitHub source archive, or an extracted
full/source artifact. Every archive contains a self-describing manifest with ordered
path, per-file, and tree SHA-256 digests.
"""

from __future__ import annotations

import argparse
import fnmatch
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILES_PATH = ROOT / "templates" / "artifact-profiles.json"
HASH_PREFIX = "sha256:"
MANIFEST_SCHEMA_VERSION = 1
BUILDER_ID = "scripts/build_release_artifacts.py"
PROFILE_NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 5_000
MAX_ARCHIVE_FILE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 256 * 1024 * 1024
READ_CHUNK_BYTES = 1024 * 1024
SENSITIVE_SUFFIXES = {".key", ".p12", ".pem", ".pfx"}
SENSITIVE_BASENAMES = {".env", ".npmrc", "id_dsa", "id_ed25519", "id_rsa"}
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
RUNTIME_REMOVED_NPM_SCRIPTS = {
    "acceptance",
    "artifact:build",
    "artifact:self-test",
    "browser:smoke",
    "capability:check",
    "package:check",
    "prepack",
    "self-test",
    "self-test:node",
    "self-test:python",
    "self-test:source",
}
COMMAND_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])"
    r"((?:adapters|agents|docs|examples|references|release-evidence|scripts|templates)/"
    r"[A-Za-z0-9_./-]+)"
)
NPM_RUN_RE = re.compile(r"(?:^|\s)npm(?:\.cmd)?\s+run\s+([A-Za-z0-9:_-]+)")


class ArtifactError(RuntimeError):
    """Raised when an artifact contract or build invariant fails."""


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def sha256_bytes(data: bytes) -> str:
    return HASH_PREFIX + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(READ_CHUNK_BYTES), b""):
            digest.update(chunk)
    return HASH_PREFIX + digest.hexdigest()


def normalize_expected_sha256(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized.startswith(HASH_PREFIX):
        normalized = HASH_PREFIX + normalized
    if re.fullmatch(r"sha256:[0-9a-f]{64}", normalized) is None:
        raise ArtifactError("expected SHA-256 must be 64 lowercase hexadecimal characters")
    return normalized


def validate_relative_path(value: str) -> str:
    if "\\" in value or "\0" in value:
        raise ArtifactError(f"unsafe path separator or NUL byte: {value!r}")
    normalized = value.replace("\\", "/").removeprefix("./")
    pure = PurePosixPath(normalized)
    if (
        not normalized
        or pure.is_absolute()
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise ArtifactError(f"unsafe relative path: {value!r}")
    if normalized != pure.as_posix():
        raise ArtifactError(f"non-canonical relative path: {value!r}")
    for part in pure.parts:
        stem = part.split(".", 1)[0].upper()
        if (
            ":" in part
            or part.endswith((" ", "."))
            or stem in WINDOWS_RESERVED_NAMES
        ):
            raise ArtifactError(f"non-portable relative path: {value!r}")
    return normalized


def portable_path_key(path: str) -> str:
    return "/".join(part.casefold() for part in PurePosixPath(path).parts)


def matches(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)


def directory_matches(path: str, patterns: Iterable[str]) -> bool:
    probe = f"{path}/__artifact_probe__"
    for pattern in patterns:
        if fnmatch.fnmatchcase(path, pattern) or fnmatch.fnmatchcase(probe, pattern):
            return True
        if pattern.endswith("/**"):
            prefix = pattern[:-3].rstrip("/")
            if path == prefix or path.startswith(prefix + "/"):
                return True
    return False


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactError(f"cannot read valid JSON object from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ArtifactError(f"JSON root must be an object: {path}")
    return value


def load_profiles(path: Path) -> dict[str, Any]:
    config = load_json_object(path)
    if config.get("schema_version") != 1:
        raise ArtifactError("artifact profile schema_version must be 1")
    if not isinstance(config.get("artifact_root"), str):
        raise ArtifactError("artifact_root must be a string")
    artifact_root = validate_relative_path(config["artifact_root"])
    if len(PurePosixPath(artifact_root).parts) != 1:
        raise ArtifactError("artifact_root must be exactly one portable directory name")
    manifest_path = config.get("manifest_path")
    if not isinstance(manifest_path, str):
        raise ArtifactError("manifest_path must be a string")
    validate_relative_path(manifest_path)
    profiles = config.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ArtifactError("profiles must be a non-empty object")

    aliases: set[str] = set()
    portable_names: set[str] = set()
    for name, profile in profiles.items():
        if not isinstance(name, str) or not name or not isinstance(profile, dict):
            raise ArtifactError("profile names and definitions must be objects")
        if PROFILE_NAME_RE.fullmatch(name) is None:
            raise ArtifactError(f"invalid profile name: {name!r}")
        portable_name = name.casefold()
        if portable_name in portable_names:
            raise ArtifactError(f"case-insensitive duplicate profile name: {name!r}")
        portable_names.add(portable_name)
        for field in ("include", "required_paths"):
            values = profile.get(field)
            if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
                raise ArtifactError(f"profiles.{name}.{field} must be a string array")
        forbidden_paths = profile.get("forbidden_paths", [])
        if not isinstance(forbidden_paths, list) or not all(
            isinstance(item, str) for item in forbidden_paths
        ):
            raise ArtifactError(f"profiles.{name}.forbidden_paths must be a string array")
        categories = profile.get("exclude_categories")
        if not isinstance(categories, dict) or not all(
            isinstance(category, str)
            and isinstance(patterns, list)
            and all(isinstance(pattern, str) for pattern in patterns)
            for category, patterns in categories.items()
        ):
            raise ArtifactError(f"profiles.{name}.exclude_categories is invalid")
        profile_aliases = profile.get("aliases", [])
        if not isinstance(profile_aliases, list) or not all(
            isinstance(alias, str) and alias for alias in profile_aliases
        ):
            raise ArtifactError(f"profiles.{name}.aliases must be a string array")
        for alias in profile_aliases:
            if PROFILE_NAME_RE.fullmatch(alias) is None:
                raise ArtifactError(f"invalid profile alias: {alias!r}")
            if alias in profiles or alias in aliases:
                raise ArtifactError(f"duplicate profile alias: {alias}")
            portable_alias = alias.casefold()
            if portable_alias in portable_names:
                raise ArtifactError(f"case-insensitive duplicate profile alias: {alias!r}")
            portable_names.add(portable_alias)
            aliases.add(alias)
        for path_value in profile["required_paths"] + forbidden_paths:
            validate_relative_path(path_value)
        self_test_script = profile.get("self_test_script")
        if not isinstance(self_test_script, str) or not self_test_script:
            raise ArtifactError(f"profiles.{name}.self_test_script must be a string")
        if profile.get("package_projection") not in {"none", "runtime"}:
            raise ArtifactError(
                f"profiles.{name}.package_projection must be 'none' or 'runtime'"
            )
    if set(profiles) != {"full", "runtime"}:
        raise ArtifactError("artifact profiles must define exactly canonical full and runtime")
    return config


def resolve_profile(config: dict[str, Any], requested: str) -> tuple[str, dict[str, Any]]:
    profiles = config["profiles"]
    if requested in profiles:
        return requested, profiles[requested]
    for name, profile in profiles.items():
        if requested in profile.get("aliases", []):
            return name, profile
    choices = sorted(
        list(profiles) + [alias for profile in profiles.values() for alias in profile.get("aliases", [])]
    )
    raise ArtifactError(f"unknown profile {requested!r}; choose one of: {', '.join(choices)}")


def exclusion_category(path: str, profile: dict[str, Any]) -> str | None:
    for category, patterns in profile["exclude_categories"].items():
        if matches(path, patterns):
            return category
    return None


def excluded_directory_category(path: str, profile: dict[str, Any]) -> str | None:
    for category, patterns in profile["exclude_categories"].items():
        if directory_matches(path, patterns):
            return category
    return None


def is_sensitive_path(path: str) -> bool:
    basename = PurePosixPath(path).name.lower()
    return (
        basename in SENSITIVE_BASENAMES
        or basename.startswith(".env.")
        or PurePosixPath(basename).suffix.lower() in SENSITIVE_SUFFIXES
    )


def sorted_strings(values: Iterable[str]) -> list[str]:
    return sorted(values, key=lambda value: value.encode("utf-8"))


def verify_no_file_directory_collisions(paths: Iterable[str], label: str) -> None:
    path_set = set(paths)
    for path in sorted_strings(path_set):
        parents = PurePosixPath(path).parents
        for parent in parents:
            if parent == PurePosixPath("."):
                continue
            if parent.as_posix() in path_set:
                raise ArtifactError(
                    f"{label} contains a file/directory prefix collision: "
                    f"{parent.as_posix()!r} and {path!r}"
                )


def is_reparse_point(path: Path) -> bool:
    """Return True for Windows junctions and other filesystem reparse points."""
    try:
        attributes = path.lstat().st_file_attributes
    except (AttributeError, OSError):
        return False
    flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & flag)


def is_mount_point(path: Path) -> bool:
    try:
        return path.is_mount()
    except (NotImplementedError, OSError):
        return False


def ensure_contained(root: Path, candidate: Path, label: str) -> Path:
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ArtifactError(f"{label} escapes the canonical source root: {candidate}") from exc
    return resolved


def collect_payload(
    source_root: Path, profile: dict[str, Any]
) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    if not source_root.is_dir():
        raise ArtifactError(f"source root is not a directory: {source_root}")
    canonical_root = source_root.resolve(strict=True)

    payload: dict[str, bytes] = {}

    for current, directories, files in os.walk(source_root, topdown=True, followlinks=False):
        current_path = Path(current)
        directories.sort(key=lambda value: value.encode("utf-8"))
        files.sort(key=lambda value: value.encode("utf-8"))

        retained_directories: list[str] = []
        for directory in directories:
            candidate = current_path / directory
            relative = candidate.relative_to(source_root).as_posix()
            category = excluded_directory_category(relative, profile)
            if category is not None:
                continue
            if candidate.is_symlink() or is_reparse_point(candidate) or is_mount_point(candidate):
                raise ArtifactError(
                    f"directory links, junctions, reparse points, and mounts are not allowed: "
                    f"{relative}"
                )
            ensure_contained(canonical_root, candidate, f"artifact directory {relative!r}")
            retained_directories.append(directory)
        directories[:] = retained_directories

        for filename in files:
            candidate = current_path / filename
            relative = validate_relative_path(candidate.relative_to(source_root).as_posix())
            category = exclusion_category(relative, profile)
            if category is not None:
                continue
            if not matches(relative, profile["include"]):
                continue
            if candidate.is_symlink() or is_reparse_point(candidate) or not candidate.is_file():
                raise ArtifactError(f"only regular files are allowed in artifacts: {relative}")
            ensure_contained(canonical_root, candidate, f"artifact file {relative!r}")
            if is_sensitive_path(relative):
                raise ArtifactError(f"credential-like file selected for packaging: {relative}")
            try:
                payload[relative] = candidate.read_bytes()
            except OSError as exc:
                raise ArtifactError(f"cannot read {relative}: {exc}") from exc

    # Keep this summary declarative rather than environment-counted. If an
    # ignored node_modules, .git, cache, or output directory appears between
    # two builds, the payload and manifest must remain byte-identical.
    excluded_summary = [
        {
            "category": category,
            "patterns": list(patterns),
            "policy": "exclude",
        }
        for category, patterns in profile["exclude_categories"].items()
    ]
    excluded_summary.append(
        {
            "category": "outside_allowlist",
            "patterns": [],
            "policy": "exclude_every_path_not_selected_by_profile_include",
        }
    )
    portable_paths: dict[str, str] = {}
    for path in payload:
        key = portable_path_key(path)
        previous = portable_paths.get(key)
        if previous is not None:
            raise ArtifactError(
                f"case-insensitive artifact path collision: {previous!r} and {path!r}"
            )
        portable_paths[key] = path
    verify_no_file_directory_collisions(payload, "artifact payload")
    return payload, excluded_summary


def command_repo_paths(command: str) -> set[str]:
    return {match.group(1).rstrip(".,;:)") for match in COMMAND_PATH_RE.finditer(command)}


def project_runtime_package(payload: dict[str, bytes]) -> tuple[bytes, dict[str, Any]]:
    source = payload.get("package.json")
    if source is None:
        raise ArtifactError("runtime package projection requires package.json")
    try:
        package = json.loads(source.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactError(f"cannot project invalid package.json: {exc}") from exc
    if not isinstance(package, dict) or not isinstance(package.get("scripts"), dict):
        raise ArtifactError("runtime package projection requires package.json scripts")

    original_scripts = package["scripts"]
    scripts = {
        name: command
        for name, command in original_scripts.items()
        if isinstance(name, str) and isinstance(command, str)
    }
    if len(scripts) != len(original_scripts):
        raise ArtifactError("package.json scripts must contain only string keys and commands")

    removed = {
        name
        for name in scripts
        if name in RUNTIME_REMOVED_NPM_SCRIPTS or name.startswith("eval:")
    }
    for name, command in scripts.items():
        if any(path not in payload for path in command_repo_paths(command)):
            removed.add(name)

    changed = True
    while changed:
        changed = False
        retained = set(scripts) - removed
        for name in sorted(retained):
            dependencies = set(NPM_RUN_RE.findall(scripts[name]))
            if dependencies - retained:
                removed.add(name)
                changed = True

    package["scripts"] = {
        name: scripts[name]
        for name in original_scripts
        if name not in removed
    }
    source_package_manifest = package.pop("dResearchPackageManifest", None)
    package["dResearchArtifactProfile"] = {
        "name": "runtime",
        "projection": "runtime-package-v1",
        "source_package_manifest": source_package_manifest,
    }
    projected = canonical_json(package)
    return projected, {
        "path": "package.json",
        "transform": "runtime-package-v1",
        "source_sha256": sha256_bytes(source),
        "output_sha256": sha256_bytes(projected),
        "removed_npm_scripts": sorted_strings(removed),
    }


def apply_profile_transforms(
    payload: dict[str, bytes], profile_name: str, profile: dict[str, Any]
) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    transformed = dict(payload)
    projection = profile.get("package_projection")
    if projection == "none":
        return transformed, []
    if projection == "runtime" and profile_name == "runtime":
        package_bytes, record = project_runtime_package(transformed)
        transformed["package.json"] = package_bytes
        return transformed, [record]
    raise ArtifactError(
        f"unsupported package projection {projection!r} for profile {profile_name!r}"
    )


def verify_package_script_closure(payload: dict[str, bytes], profile_name: str) -> None:
    package_bytes = payload.get("package.json")
    if package_bytes is None:
        raise ArtifactError(f"{profile_name} artifact is missing package.json")
    try:
        package = json.loads(package_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactError(f"{profile_name} artifact package.json is invalid: {exc}") from exc
    scripts = package.get("scripts") if isinstance(package, dict) else None
    if not isinstance(scripts, dict):
        raise ArtifactError(f"{profile_name} artifact package.json scripts must be an object")
    names = set(scripts)
    failures: list[str] = []
    for name, command in scripts.items():
        if not isinstance(name, str) or not isinstance(command, str):
            failures.append(f"{name!r}: non-string npm script")
            continue
        for path in sorted_strings(command_repo_paths(command)):
            if path not in payload:
                failures.append(f"{name}: missing command path {path}")
        for dependency in sorted_strings(set(NPM_RUN_RE.findall(command))):
            if dependency not in names:
                failures.append(f"{name}: missing npm dependency {dependency}")
    if failures:
        raise ArtifactError(
            f"{profile_name} artifact has dangling npm scripts: {failures}"
        )


def canonical_profile_contract(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "include": list(profile["include"]),
        "exclude_categories": {
            category: list(patterns)
            for category, patterns in profile["exclude_categories"].items()
        },
        "required_paths": list(profile["required_paths"]),
        "forbidden_paths": list(profile.get("forbidden_paths", [])),
        "route_closure": bool(profile.get("route_closure")),
        "package_projection": profile["package_projection"],
        "self_test_script": profile["self_test_script"],
    }


def collect_routed_paths(route_manifest: dict[str, Any]) -> set[str]:
    routed = {"templates/route-manifest.json"}
    routes = route_manifest.get("routes")
    if not isinstance(routes, list):
        raise ArtifactError("route manifest routes must be an array")
    for route in routes:
        if not isinstance(route, dict):
            raise ArtifactError("route manifest contains a non-object route")
        reference = route.get("reference")
        references = route.get("references", [])
        if reference is not None:
            if not isinstance(reference, str):
                raise ArtifactError("route reference must be a string")
            routed.add(validate_relative_path(reference))
        if not isinstance(references, list) or not all(isinstance(item, str) for item in references):
            raise ArtifactError("route references must be a string array")
        routed.update(validate_relative_path(item) for item in references)

    required = route_manifest.get("required_skill_references", [])
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        raise ArtifactError("required_skill_references must be a string array")
    routed.update(validate_relative_path(item) for item in required)
    repository_contract = route_manifest.get("repository_contract")
    if not isinstance(repository_contract, dict):
        raise ArtifactError("route manifest repository_contract must be an object")
    core_paths = repository_contract.get("core_paths", [])
    if not isinstance(core_paths, list) or not all(isinstance(item, str) for item in core_paths):
        raise ArtifactError("route manifest repository_contract.core_paths must be a string array")
    routed.update(validate_relative_path(item) for item in core_paths)
    cli_contracts = repository_contract.get("cli_contracts", [])
    if not isinstance(cli_contracts, list):
        raise ArtifactError("route manifest repository_contract.cli_contracts must be an array")
    for contract in cli_contracts:
        if not isinstance(contract, dict) or not isinstance(contract.get("path"), str):
            raise ArtifactError("route manifest contains an invalid CLI contract")
        routed.add(validate_relative_path(contract["path"]))
    return routed


def verify_profile_contract(
    payload_paths: set[str],
    payload: dict[str, bytes],
    profile_name: str,
    profile: dict[str, Any],
) -> None:
    missing = sorted_strings(set(profile["required_paths"]) - payload_paths)
    if missing:
        raise ArtifactError(f"{profile_name} artifact is missing required paths: {missing}")

    forbidden = sorted_strings(set(profile.get("forbidden_paths", [])) & payload_paths)
    if forbidden:
        raise ArtifactError(f"{profile_name} artifact contains forbidden paths: {forbidden}")

    outside_allowlist = [
        path
        for path in payload_paths
        if not matches(path, profile["include"]) or exclusion_category(path, profile) is not None
    ]
    if outside_allowlist:
        raise ArtifactError(
            f"{profile_name} artifact contains paths outside its allowlist: "
            f"{sorted_strings(outside_allowlist)}"
        )

    verify_package_script_closure(payload, profile_name)

    if profile.get("route_closure"):
        route_path = "templates/route-manifest.json"
        if route_path not in payload:
            raise ArtifactError("runtime route closure cannot be checked without route-manifest.json")
        try:
            route_manifest = json.loads(payload[route_path].decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ArtifactError(f"runtime route manifest is invalid: {exc}") from exc
        if not isinstance(route_manifest, dict):
            raise ArtifactError("runtime route manifest root must be an object")
        routed = collect_routed_paths(route_manifest)
        missing_routed = sorted_strings(routed - payload_paths)
        if missing_routed:
            raise ArtifactError(
                "runtime artifact does not close over all routed references: "
                f"{missing_routed}"
            )


def aggregate_digests(payload: dict[str, bytes]) -> tuple[list[dict[str, Any]], str, str]:
    paths = sorted_strings(payload)
    file_entries: list[dict[str, Any]] = []
    tree = hashlib.sha256()
    for path in paths:
        data = payload[path]
        digest_hex = hashlib.sha256(data).hexdigest()
        file_entries.append(
            {
                "path": path,
                "sha256": HASH_PREFIX + digest_hex,
                "size": len(data),
            }
        )
        tree.update(path.encode("utf-8"))
        tree.update(b"\0")
        tree.update(digest_hex.encode("ascii"))
        tree.update(b"\0")
        tree.update(str(len(data)).encode("ascii"))
        tree.update(b"\n")
    ordered_path_bytes = ("\n".join(paths) + "\n").encode("utf-8")
    return (
        file_entries,
        sha256_bytes(ordered_path_bytes),
        HASH_PREFIX + tree.hexdigest(),
    )


def package_version(source_root: Path) -> tuple[str, str]:
    package = load_json_object(source_root / "package.json")
    name = package.get("name")
    version = package.get("version")
    if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
        raise ArtifactError("package.json must contain non-empty name and version strings")
    return name, version


def make_manifest(
    *,
    source_root: Path,
    config: dict[str, Any],
    profile_name: str,
    profile: dict[str, Any],
    payload: dict[str, bytes],
    excluded_summary: list[dict[str, Any]],
    content_transforms: list[dict[str, Any]],
) -> dict[str, Any]:
    package_name, version = package_version(source_root)
    file_entries, paths_digest, tree_digest = aggregate_digests(payload)
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "algorithm": "sha256",
        "package_name": package_name,
        "package_version": version,
        "profile": profile_name,
        "profile_aliases": list(profile.get("aliases", [])),
        "profile_description": profile.get("description", ""),
        "artifact_root": config["artifact_root"],
        "manifest_path": config["manifest_path"],
        "file_count": len(file_entries),
        "archive_member_count": len(file_entries) + 1,
        "ordered_paths_sha256": paths_digest,
        "tree_sha256": tree_digest,
        "files": file_entries,
        "excluded_categories": excluded_summary,
        "content_transforms": content_transforms,
        "profile_contract": canonical_profile_contract(profile),
        "deterministic_build_recipe": {
            "builder": BUILDER_ID,
            "archive_format": "tar+gzip",
            "path_order": "ascending UTF-8 bytes",
            "path_separator": "/",
            "tar_format": "pax",
            "tar_mtime": 0,
            "tar_uid": 0,
            "tar_gid": 0,
            "tar_uname": "",
            "tar_gname": "",
            "tar_file_mode": "0644",
            "gzip_mtime": 0,
            "gzip_original_filename": "",
            "gzip_compresslevel": 9,
            "content_transform": (
                "none" if not content_transforms else "declared-path-transforms"
            ),
        },
    }


def add_tar_file(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mtime = 0
    info.mode = 0o644
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.pax_headers = {}
    archive.addfile(info, io.BytesIO(data))


def write_archive(
    archive_path: Path,
    artifact_root: str,
    manifest_path: str,
    payload: dict[str, bytes],
    manifest_bytes: bytes,
) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = archive_path.with_name(archive_path.name + ".tmp")
    entries = dict(payload)
    entries[manifest_path] = manifest_bytes
    try:
        with temporary.open("wb") as raw:
            with gzip.GzipFile(
                filename="",
                mode="wb",
                compresslevel=9,
                fileobj=raw,
                mtime=0,
            ) as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                    for path in sorted_strings(entries):
                        add_tar_file(archive, f"{artifact_root}/{path}", entries[path])
        os.replace(temporary, archive_path)
    finally:
        temporary.unlink(missing_ok=True)


def artifact_basename(version: str, profile_name: str) -> str:
    safe_version = "".join(
        character if character.isalnum() or character in ".-" else "-" for character in version
    )
    return f"d-research-{safe_version}-{profile_name}"


def contained_output_path(output_dir: Path, filename: str) -> Path:
    output_root = output_dir.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    target = (output_root / filename).resolve()
    try:
        target.relative_to(output_root)
    except ValueError as exc:
        raise ArtifactError(f"artifact output escapes output directory: {filename!r}") from exc
    return target


def build_artifact(
    *,
    source_root: Path,
    profiles_path: Path,
    requested_profile: str,
    output_dir: Path,
) -> dict[str, Any]:
    config = load_profiles(profiles_path)
    profile_name, profile = resolve_profile(config, requested_profile)
    payload, excluded_summary = collect_payload(source_root, profile)
    payload, content_transforms = apply_profile_transforms(payload, profile_name, profile)
    verify_profile_contract(set(payload), payload, profile_name, profile)
    manifest = make_manifest(
        source_root=source_root,
        config=config,
        profile_name=profile_name,
        profile=profile,
        payload=payload,
        excluded_summary=excluded_summary,
        content_transforms=content_transforms,
    )
    manifest_bytes = canonical_json(manifest)
    _, version = package_version(source_root)
    basename = artifact_basename(version, profile_name)
    archive_path = contained_output_path(output_dir, f"{basename}.tar.gz")
    manifest_sidecar = contained_output_path(output_dir, f"{basename}.manifest.json")
    checksum_sidecar = contained_output_path(output_dir, f"{basename}.tar.gz.sha256")

    write_archive(
        archive_path,
        config["artifact_root"],
        config["manifest_path"],
        payload,
        manifest_bytes,
    )
    manifest_sidecar.write_bytes(manifest_bytes)
    archive_sha256 = sha256_bytes(archive_path.read_bytes())
    checksum_sidecar.write_text(
        f"{archive_sha256.removeprefix(HASH_PREFIX)}  {archive_path.name}\n",
        encoding="ascii",
        newline="\n",
    )
    return {
        "profile": profile_name,
        "archive": str(archive_path),
        "archive_sha256": archive_sha256,
        "manifest": str(manifest_sidecar),
        "checksum": str(checksum_sidecar),
        "file_count": manifest["file_count"],
        "ordered_paths_sha256": manifest["ordered_paths_sha256"],
        "tree_sha256": manifest["tree_sha256"],
    }


def payload_from_archive(archive_path: Path) -> tuple[str, dict[str, bytes]]:
    if not archive_path.is_file():
        raise ArtifactError(f"archive does not exist: {archive_path}")
    archive_size = archive_path.stat().st_size
    if archive_size > MAX_ARCHIVE_BYTES:
        raise ArtifactError(
            f"archive exceeds compressed-size limit: {archive_size} > {MAX_ARCHIVE_BYTES}"
        )
    with archive_path.open("rb") as raw_archive:
        header = raw_archive.read(10)
    if len(header) != 10 or header[:3] != b"\x1f\x8b\x08":
        raise ArtifactError("archive is not a canonical gzip stream")
    if header[3] & 0x08 or int.from_bytes(header[4:8], "little") != 0:
        raise ArtifactError("gzip filename and mtime must be normalized")
    members: dict[str, bytes] = {}
    portable_members: dict[str, str] = {}
    roots: set[str] = set()
    member_names: list[str] = []
    total_size = 0
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            for member_index, member in enumerate(archive, start=1):
                if member_index > MAX_ARCHIVE_MEMBERS:
                    raise ArtifactError(
                        f"archive exceeds member-count limit: {MAX_ARCHIVE_MEMBERS}"
                    )
                if not member.isfile():
                    raise ArtifactError(f"archive contains a non-file member: {member.name}")
                if (
                    member.mtime != 0
                    or member.mode != 0o644
                    or member.uid != 0
                    or member.gid != 0
                    or member.uname
                    or member.gname
                    or member.pax_headers
                ):
                    raise ArtifactError(
                        f"archive member metadata is not canonical: {member.name}"
                    )
                if member.size < 0 or member.size > MAX_ARCHIVE_FILE_BYTES:
                    raise ArtifactError(
                        f"archive member exceeds file-size limit: {member.name} ({member.size})"
                    )
                total_size += member.size
                if total_size > MAX_ARCHIVE_TOTAL_BYTES:
                    raise ArtifactError(
                        f"archive exceeds total uncompressed-size limit: {MAX_ARCHIVE_TOTAL_BYTES}"
                    )
                canonical = validate_relative_path(member.name)
                member_names.append(canonical)
                parts = PurePosixPath(canonical).parts
                if len(parts) < 2:
                    raise ArtifactError(f"archive member is not under one artifact root: {canonical}")
                roots.add(parts[0])
                relative = PurePosixPath(*parts[1:]).as_posix()
                if relative in members:
                    raise ArtifactError(f"archive contains a duplicate member: {relative}")
                portable_key = portable_path_key(relative)
                previous = portable_members.get(portable_key)
                if previous is not None:
                    raise ArtifactError(
                        "archive contains a case-insensitive path collision: "
                        f"{previous!r} and {relative!r}"
                    )
                portable_members[portable_key] = relative
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise ArtifactError(f"cannot read archive member: {canonical}")
                chunks: list[bytes] = []
                observed = 0
                while True:
                    chunk = extracted.read(min(READ_CHUNK_BYTES, member.size - observed + 1))
                    if not chunk:
                        break
                    observed += len(chunk)
                    if observed > member.size:
                        raise ArtifactError(f"archive member exceeds declared size: {canonical}")
                    chunks.append(chunk)
                data = b"".join(chunks)
                if len(data) != member.size:
                    raise ArtifactError(f"archive member size mismatch: {canonical}")
                members[relative] = data
    except (OSError, tarfile.TarError) as exc:
        raise ArtifactError(f"cannot read archive {archive_path}: {exc}") from exc
    if len(roots) != 1:
        raise ArtifactError(f"archive must contain exactly one root directory, found {sorted(roots)}")
    if member_names != sorted_strings(member_names):
        raise ArtifactError("archive members are not in canonical UTF-8 path order")
    verify_no_file_directory_collisions(members, "archive")
    return next(iter(roots)), members


def verified_profile_contract(
    manifest: dict[str, Any], trusted_profile: dict[str, Any]
) -> dict[str, Any]:
    contract = manifest.get("profile_contract")
    if not isinstance(contract, dict):
        raise ArtifactError("artifact manifest is missing profile_contract")
    expected = canonical_profile_contract(trusted_profile)
    if contract != expected:
        raise ArtifactError("embedded profile contract does not match the trusted profile contract")
    return expected


def verify_manifest_payload(manifest: dict[str, Any], payload: dict[str, bytes]) -> None:
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ArtifactError("unsupported artifact manifest schema_version")
    if manifest.get("algorithm") != "sha256":
        raise ArtifactError("artifact manifest algorithm must be sha256")
    expected_entries = manifest.get("files")
    if not isinstance(expected_entries, list):
        raise ArtifactError("artifact manifest files must be an array")
    actual_entries, actual_paths_digest, actual_tree_digest = aggregate_digests(payload)
    if expected_entries != actual_entries:
        raise ArtifactError("artifact per-file SHA-256 manifest does not match payload")
    if manifest.get("file_count") != len(actual_entries):
        raise ArtifactError("artifact manifest file_count does not match payload")
    if manifest.get("archive_member_count") != len(actual_entries) + 1:
        raise ArtifactError("artifact manifest archive_member_count is invalid")
    if manifest.get("ordered_paths_sha256") != actual_paths_digest:
        raise ArtifactError("artifact ordered path digest does not match payload")
    if manifest.get("tree_sha256") != actual_tree_digest:
        raise ArtifactError("artifact tree digest does not match payload")
    package_bytes = payload.get("package.json")
    if package_bytes is None:
        raise ArtifactError("artifact payload is missing package.json")
    try:
        package = json.loads(package_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactError(f"artifact package.json is invalid: {exc}") from exc
    if not isinstance(package, dict):
        raise ArtifactError("artifact package.json root must be an object")
    if package.get("name") != manifest.get("package_name"):
        raise ArtifactError("artifact package name does not match its manifest")
    if package.get("version") != manifest.get("package_version"):
        raise ArtifactError("artifact package version does not match its manifest")


def verify_declared_transforms(
    manifest: dict[str, Any], payload: dict[str, bytes], profile: dict[str, Any]
) -> None:
    transforms = manifest.get("content_transforms")
    projection = profile.get("package_projection")
    if projection == "none":
        if transforms != []:
            raise ArtifactError("full artifact must not declare content transforms")
        return
    if projection != "runtime" or not isinstance(transforms, list) or len(transforms) != 1:
        raise ArtifactError("runtime artifact must declare exactly one trusted package transform")
    record = transforms[0]
    expected_keys = {
        "path",
        "transform",
        "source_sha256",
        "output_sha256",
        "removed_npm_scripts",
    }
    if not isinstance(record, dict) or set(record) != expected_keys:
        raise ArtifactError("runtime package transform record has an invalid shape")
    if record.get("path") != "package.json" or record.get("transform") != "runtime-package-v1":
        raise ArtifactError("runtime package transform identity is invalid")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", str(record.get("source_sha256", ""))) is None:
        raise ArtifactError("runtime package transform source SHA-256 is invalid")
    package_bytes = payload.get("package.json")
    if package_bytes is None or record.get("output_sha256") != sha256_bytes(package_bytes):
        raise ArtifactError("runtime package transform output SHA-256 mismatch")
    removed = record.get("removed_npm_scripts")
    if (
        not isinstance(removed, list)
        or not all(isinstance(item, str) and item for item in removed)
        or removed != sorted_strings(set(removed))
    ):
        raise ArtifactError("runtime removed_npm_scripts must be a sorted unique string array")
    try:
        package = json.loads(package_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactError(f"runtime package projection is invalid JSON: {exc}") from exc
    marker = package.get("dResearchArtifactProfile") if isinstance(package, dict) else None
    if not isinstance(marker, dict) or marker.get("name") != "runtime":
        raise ArtifactError("runtime package projection marker is missing")
    scripts = package.get("scripts") if isinstance(package, dict) else None
    if not isinstance(scripts, dict) or any(name in scripts for name in removed):
        raise ArtifactError("runtime package projection still advertises a removed npm script")


def extract_verified_payload(root_name: str, payload: dict[str, bytes], destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    extraction_root = destination / root_name
    if extraction_root.exists():
        raise ArtifactError(f"extraction root already exists: {extraction_root}")
    for path in sorted_strings(payload):
        target = extraction_root.joinpath(*PurePosixPath(path).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload[path])
    if any(path.name == ".git" for path in extraction_root.rglob(".git")):
        raise ArtifactError("verified extraction unexpectedly contains .git")
    return extraction_root


def verify_artifact(
    archive_path: Path,
    *,
    profiles_path: Path = DEFAULT_PROFILES_PATH,
    expected_profile: str | None = None,
    expected_sha256: str | None = None,
    expected_version: str | None = None,
    extract_to: Path | None = None,
) -> dict[str, Any]:
    config = load_profiles(profiles_path)
    actual_archive_sha256 = sha256_file(archive_path)
    identity_verified = False
    if expected_sha256 is not None:
        normalized_expected = normalize_expected_sha256(expected_sha256)
        if actual_archive_sha256 != normalized_expected:
            raise ArtifactError(
                f"archive SHA-256 mismatch: expected {normalized_expected}, "
                f"got {actual_archive_sha256}"
            )
        identity_verified = True
    root_name, members = payload_from_archive(archive_path)
    candidate_manifest_paths = [
        path for path in members if PurePosixPath(path).name == "ARTIFACT-MANIFEST.json"
    ]
    if len(candidate_manifest_paths) != 1:
        raise ArtifactError("archive must contain exactly one ARTIFACT-MANIFEST.json")
    manifest_path = candidate_manifest_paths[0]
    manifest_bytes = members.pop(manifest_path)
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ArtifactError(f"embedded artifact manifest is invalid: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ArtifactError("embedded artifact manifest root must be an object")
    if root_name != config["artifact_root"] or manifest.get("artifact_root") != root_name:
        raise ArtifactError("archive root does not match the trusted artifact root")
    if manifest_path != config["manifest_path"] or manifest.get("manifest_path") != manifest_path:
        raise ArtifactError("embedded manifest path does not match the trusted manifest path")
    profile_name = manifest.get("profile")
    if not isinstance(profile_name, str) or profile_name not in config["profiles"]:
        raise ArtifactError("embedded artifact profile is invalid")
    profile = config["profiles"][profile_name]
    if expected_profile is not None:
        expected_canonical, _ = resolve_profile(config, expected_profile)
        if profile_name != expected_canonical:
            raise ArtifactError(
                f"expected profile {expected_profile!r} ({expected_canonical!r}), "
                f"archive contains {profile_name!r}"
            )
    if manifest.get("profile_aliases") != list(profile.get("aliases", [])):
        raise ArtifactError("embedded artifact profile aliases do not match trusted config")
    if manifest.get("profile_description") != profile.get("description", ""):
        raise ArtifactError("embedded artifact profile description does not match trusted config")
    if expected_version is not None and manifest.get("package_version") != expected_version:
        raise ArtifactError(
            f"expected package version {expected_version!r}, "
            f"archive contains {manifest.get('package_version')!r}"
        )

    verify_manifest_payload(manifest, members)
    trusted_contract = verified_profile_contract(manifest, profile)
    verify_declared_transforms(manifest, members, profile)
    verify_profile_contract(set(members), members, profile_name, profile)

    extraction_root: Path | None = None
    if extract_to is not None:
        members_with_manifest = dict(members)
        members_with_manifest[manifest_path] = manifest_bytes
        extraction_root = extract_verified_payload(root_name, members_with_manifest, extract_to)
    return {
        "profile": profile_name,
        "package_version": manifest.get("package_version"),
        "archive": str(archive_path),
        "archive_sha256": actual_archive_sha256,
        "identity_verified": identity_verified,
        "profile_contract_verified": True,
        "file_count": manifest["file_count"],
        "ordered_paths_sha256": manifest["ordered_paths_sha256"],
        "tree_sha256": manifest["tree_sha256"],
        "extracted_to": str(extraction_root) if extraction_root is not None else None,
        "self_test_script": trusted_contract["self_test_script"],
    }


def run_profile_self_test(extraction_root: Path, script_name: str) -> None:
    package = load_json_object(extraction_root / "package.json")
    scripts = package.get("scripts")
    if not isinstance(scripts, dict) or script_name not in scripts:
        raise ArtifactError(
            f"package.json does not define required extracted-artifact script {script_name!r}"
        )
    npm = "npm.cmd" if os.name == "nt" else "npm"
    commands = [[npm, "run", script_name]]
    for command in commands:
        try:
            completed = subprocess.run(command, cwd=extraction_root, check=False, text=True)
        except OSError as exc:
            raise ArtifactError(f"cannot execute npm profile self-test: {exc}") from exc
        if completed.returncode != 0:
            raise ArtifactError(
                f"extracted artifact self-test {script_name!r} exited with {completed.returncode}"
            )


def assert_identical_builds(first: dict[str, Any], second: dict[str, Any]) -> None:
    for key in ("archive_sha256", "file_count", "ordered_paths_sha256", "tree_sha256"):
        if first[key] != second[key]:
            raise ArtifactError(
                f"deterministic build mismatch for {first['profile']} field {key}: "
                f"{first[key]!r} != {second[key]!r}"
            )
    first_archive = Path(first["archive"]).read_bytes()
    second_archive = Path(second["archive"]).read_bytes()
    if first_archive != second_archive:
        raise ArtifactError(f"deterministic build bytes differ for profile {first['profile']}")
    if Path(first["manifest"]).read_bytes() != Path(second["manifest"]).read_bytes():
        raise ArtifactError(f"deterministic manifest bytes differ for profile {first['profile']}")


def builder_self_test(source_root: Path, profiles_path: Path) -> dict[str, Any]:
    config = load_profiles(profiles_path)
    _, expected_version = package_version(source_root)
    results: list[dict[str, Any]] = []
    profile_payloads: dict[str, dict[str, bytes]] = {}
    profile_builds: dict[str, dict[str, Any]] = {}
    extracted_roots: dict[str, Path] = {}
    with tempfile.TemporaryDirectory(prefix="d-research-artifact-self-test-") as temporary:
        temp_root = Path(temporary)
        for profile_name in config["profiles"]:
            profile = config["profiles"][profile_name]
            first = build_artifact(
                source_root=source_root,
                profiles_path=profiles_path,
                requested_profile=profile_name,
                output_dir=temp_root / "build-one" / profile_name,
            )
            second = build_artifact(
                source_root=source_root,
                profiles_path=profiles_path,
                requested_profile=profile_name,
                output_dir=temp_root / "build-two" / profile_name,
            )
            assert_identical_builds(first, second)
            profile_builds[profile_name] = first
            verified_aliases: list[str] = []
            for alias in profile.get("aliases", []):
                alias_build = build_artifact(
                    source_root=source_root,
                    profiles_path=profiles_path,
                    requested_profile=alias,
                    output_dir=temp_root / "alias-builds" / alias,
                )
                assert_identical_builds(first, alias_build)
                verify_artifact(
                    Path(first["archive"]),
                    profiles_path=profiles_path,
                    expected_profile=alias,
                    expected_sha256=first["archive_sha256"],
                    expected_version=expected_version,
                )
                verified_aliases.append(alias)
            extraction_dir = temp_root / "extracted" / profile_name
            verified = verify_artifact(
                Path(first["archive"]),
                profiles_path=profiles_path,
                expected_profile=profile_name,
                expected_sha256=first["archive_sha256"],
                expected_version=expected_version,
                extract_to=extraction_dir,
            )
            extracted_root = Path(verified["extracted_to"])
            extracted_roots[profile_name] = extracted_root
            if (extracted_root / ".git").exists():
                raise ArtifactError(f"{profile_name} extraction contains .git")
            run_profile_self_test(extracted_root, profile["self_test_script"])
            _, archive_members = payload_from_archive(Path(first["archive"]))
            archive_members.pop(config["manifest_path"])
            profile_payloads[profile_name] = archive_members
            results.append(
                {
                    "profile": profile_name,
                    "file_count": verified["file_count"],
                    "archive_sha256": verified["archive_sha256"],
                    "tree_sha256": verified["tree_sha256"],
                    "build_twice_identical": True,
                    "extracted_without_git": True,
                    "profile_contract_verified": True,
                    "profile_aliases_verified": verified_aliases,
                }
            )
        if set(profile_payloads) != {"full", "runtime"}:
            raise ArtifactError("self-test did not exercise both canonical artifact profiles")
        full_payload = profile_payloads["full"]
        runtime_payload = profile_payloads["runtime"]
        missing_from_full = sorted_strings(set(runtime_payload) - set(full_payload))
        changed_from_full = sorted_strings(
            path
            for path, data in runtime_payload.items()
            if path in full_payload and full_payload[path] != data and path != "package.json"
        )
        projected_package, _ = project_runtime_package(full_payload)
        if (
            missing_from_full
            or changed_from_full
            or runtime_payload.get("package.json") != projected_package
        ):
            raise ArtifactError(
                "runtime must be a content-preserving projection of full except for the "
                "declared package.json transform; "
                f"missing={missing_from_full}, changed={changed_from_full}"
            )

        full_archive_root = extracted_roots.get("full")
        if full_archive_root is None:
            raise ArtifactError("full artifact was not extracted for replay")
        replay_profiles_path = full_archive_root / "templates" / "artifact-profiles.json"
        for profile_name, original in profile_builds.items():
            replayed = build_artifact(
                source_root=full_archive_root,
                profiles_path=replay_profiles_path,
                requested_profile=profile_name,
                output_dir=temp_root / "full-archive-replay" / profile_name,
            )
            assert_identical_builds(original, replayed)

        runtime_build = profile_builds["runtime"]
        forged_root, forged_members = payload_from_archive(Path(runtime_build["archive"]))
        embedded_path = config["manifest_path"]
        forged_manifest = json.loads(forged_members.pop(embedded_path).decode("utf-8"))
        forged_manifest["profile_contract"]["forbidden_paths"] = []
        forged_path = temp_root / "forged-runtime.tar.gz"
        write_archive(
            forged_path,
            forged_root,
            embedded_path,
            forged_members,
            canonical_json(forged_manifest),
        )
        try:
            verify_artifact(
                forged_path,
                profiles_path=profiles_path,
                expected_profile="runtime",
                expected_sha256=sha256_file(forged_path),
                expected_version=expected_version,
            )
        except ArtifactError as exc:
            if "trusted profile contract" not in str(exc):
                raise ArtifactError(
                    f"forged profile contract failed for the wrong reason: {exc}"
                ) from exc
        else:
            raise ArtifactError("forged runtime profile contract was accepted")
    return {
        "status": "ok",
        "profiles": results,
        "runtime_projection_verified": True,
        "full_archive_replay_verified": True,
        "forged_profile_contract_rejected": True,
    }


def print_json(value: Any) -> None:
    sys.stdout.buffer.write(canonical_json(value))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="build one deterministic artifact profile")
    build.add_argument("--profile", required=True)
    build.add_argument("--output-dir", type=Path, required=True)
    build.add_argument(
        "--verify-determinism",
        action="store_true",
        help="build a second time in a temporary directory and compare archive bytes",
    )

    build_all = subparsers.add_parser("build-all", help="build every configured profile")
    build_all.add_argument("--output-dir", type=Path, required=True)
    build_all.add_argument("--verify-determinism", action="store_true")

    verify = subparsers.add_parser("verify", help="verify an artifact without trusting tar paths")
    verify.add_argument("archive", type=Path)
    verify.add_argument("--expected-profile")
    verify.add_argument("--expected-sha256")
    verify.add_argument("--expected-version")
    verify.add_argument("--extract-to", type=Path)
    verify.add_argument(
        "--run-profile-self-test",
        action="store_true",
        help="extract to a temporary directory if needed and run the profile's npm self-test",
    )

    subparsers.add_parser(
        "self-test",
        help="build every profile twice, compare bytes, extract outside Git, and verify contracts",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    source_root = args.source_root.resolve()
    profiles_path = args.profiles.resolve()
    try:
        if args.command == "build":
            result = build_artifact(
                source_root=source_root,
                profiles_path=profiles_path,
                requested_profile=args.profile,
                output_dir=args.output_dir.resolve(),
            )
            if args.verify_determinism:
                with tempfile.TemporaryDirectory(prefix="d-research-rebuild-") as temporary:
                    rebuilt = build_artifact(
                        source_root=source_root,
                        profiles_path=profiles_path,
                        requested_profile=args.profile,
                        output_dir=Path(temporary),
                    )
                    assert_identical_builds(result, rebuilt)
                result["deterministic_rebuild_verified"] = True
            print_json(result)
            return 0

        if args.command == "build-all":
            config = load_profiles(profiles_path)
            results = []
            for profile_name in config["profiles"]:
                result = build_artifact(
                    source_root=source_root,
                    profiles_path=profiles_path,
                    requested_profile=profile_name,
                    output_dir=args.output_dir.resolve(),
                )
                if args.verify_determinism:
                    with tempfile.TemporaryDirectory(prefix="d-research-rebuild-") as temporary:
                        rebuilt = build_artifact(
                            source_root=source_root,
                            profiles_path=profiles_path,
                            requested_profile=profile_name,
                            output_dir=Path(temporary),
                        )
                        assert_identical_builds(result, rebuilt)
                    result["deterministic_rebuild_verified"] = True
                results.append(result)
            print_json({"artifacts": results})
            return 0

        if args.command == "verify":
            if args.run_profile_self_test and (
                args.expected_sha256 is None or args.expected_version is None
            ):
                raise ArtifactError(
                    "--run-profile-self-test requires --expected-sha256 and --expected-version"
                )
            extraction_dir = args.extract_to.resolve() if args.extract_to else None
            temporary: tempfile.TemporaryDirectory[str] | None = None
            if args.run_profile_self_test and extraction_dir is None:
                temporary = tempfile.TemporaryDirectory(prefix="d-research-profile-test-")
                extraction_dir = Path(temporary.name)
            try:
                result = verify_artifact(
                    args.archive.resolve(),
                    profiles_path=profiles_path,
                    expected_profile=args.expected_profile,
                    expected_sha256=args.expected_sha256,
                    expected_version=args.expected_version,
                    extract_to=extraction_dir,
                )
                if args.run_profile_self_test:
                    extracted_to = result.get("extracted_to")
                    if not isinstance(extracted_to, str):
                        raise ArtifactError("profile self-test requires an extracted artifact")
                    run_profile_self_test(Path(extracted_to), result["self_test_script"])
                    result["profile_self_test_passed"] = True
                print_json(result)
                return 0
            finally:
                if temporary is not None:
                    temporary.cleanup()

        if args.command == "self-test":
            print_json(builder_self_test(source_root, profiles_path))
            return 0
    except ArtifactError as exc:
        print(f"build_release_artifacts FAILED: {exc}", file=sys.stderr)
        return 1
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
