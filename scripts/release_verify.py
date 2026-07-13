#!/usr/bin/env python3
"""Offline validators for GitHub release-boundary API responses.

The release workflow fetches authenticated GitHub API payloads and passes the
saved JSON to this helper. Keeping validation here makes fail-closed rules
deterministic and self-testable without network access.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from datetime import datetime
from pathlib import Path

FULL_SHA_RE = re.compile(r"[0-9a-f]{40}")
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


def _load_json(path: Path):
    def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key {key!r}")
            value[key] = item
        return value

    def no_nonfinite(value: str) -> None:
        raise ValueError(f"non-finite JSON number {value!r}")

    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=no_duplicates,
        parse_constant=no_nonfinite,
    )


def _parse_rfc3339(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def validate_ci_response(
    payload: object,
    *,
    expected_sha: str,
    repository: str,
    workflow_path: str,
) -> list[str]:
    """Require a completed successful full-CI workflow for one exact SHA."""
    if not FULL_SHA_RE.fullmatch(expected_sha):
        return ["expected CI commit must be a full lowercase SHA"]
    if not REPOSITORY_RE.fullmatch(repository):
        return ["expected CI repository must be owner/name"]
    if not workflow_path.startswith(".github/workflows/") or not workflow_path.endswith(
        (".yml", ".yaml")
    ):
        return ["expected CI workflow path must be under .github/workflows/"]
    if not isinstance(payload, dict):
        return ["GitHub Actions response must be an object"]
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        return ["GitHub Actions response must contain workflow_runs"]

    matching = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        repository_data = run.get("head_repository") or run.get("repository") or {}
        if (
            run.get("head_sha") == expected_sha
            and run.get("path") == workflow_path
            and isinstance(repository_data, dict)
            and repository_data.get("full_name") == repository
        ):
            matching.append(run)
    if not matching:
        return ["no full-CI workflow run is bound to the exact release commit"]
    if not any(
        run.get("status") == "completed" and run.get("conclusion") == "success"
        for run in matching
    ):
        return ["exact-release-commit full CI is missing, pending, or failing"]
    return []


def validate_tag_response(
    payload: object,
    *,
    expected_tag_object: str,
    expected_commit: str,
) -> list[str]:
    """Validate an annotated Git tag object and GitHub signature verdict."""
    if not FULL_SHA_RE.fullmatch(expected_tag_object):
        return ["expected tag object must be a full lowercase SHA"]
    if not FULL_SHA_RE.fullmatch(expected_commit):
        return ["expected tag commit must be a full lowercase SHA"]
    if not isinstance(payload, dict):
        return ["GitHub tag response must be an object"]
    errors: list[str] = []
    if payload.get("sha") != expected_tag_object:
        errors.append("GitHub tag response does not match the local annotated tag object")
    target = payload.get("object")
    if not isinstance(target, dict):
        errors.append("GitHub tag response is missing its target object")
    else:
        if target.get("type") != "commit":
            errors.append("annotated tag target must be a commit")
        if target.get("sha") != expected_commit:
            errors.append("GitHub tag target does not match the locally resolved commit")
    verification = payload.get("verification")
    if not isinstance(verification, dict) or verification.get("verified") is not True:
        reason = verification.get("reason") if isinstance(verification, dict) else "missing"
        errors.append(f"tag signature is not GitHub-verified: {reason}")
    return errors


def validate_review_response(
    payload: object,
    *,
    expected_commit: str,
    promotion_sha256: str,
    reviewer_login: str,
    pull_request_author: str,
    promotion_generated_at: str,
) -> list[str]:
    """Require a trusted GitHub approval tied to commit and promotion hash."""
    if not FULL_SHA_RE.fullmatch(expected_commit):
        return ["expected review commit must be a full lowercase SHA"]
    if not SHA256_RE.fullmatch(promotion_sha256):
        return ["promotion hash must be sha256:<64 lowercase hex>"]
    if not isinstance(reviewer_login, str) or not reviewer_login.strip():
        return ["reviewer login must be non-empty"]
    if not isinstance(pull_request_author, str) or not pull_request_author.strip():
        return ["pull-request author login must be non-empty"]
    if reviewer_login.casefold() == pull_request_author.casefold():
        return ["reviewer must be independent from the pull-request author"]
    generated_at = _parse_rfc3339(promotion_generated_at)
    if generated_at is None:
        return ["promotion generated_at must be timezone-aware RFC3339"]
    if not isinstance(payload, list):
        return ["GitHub pull-request reviews response must be an array"]

    marker = f"D-Research-Promotion-SHA256: {promotion_sha256}"
    matching: list[dict] = []
    for review in payload:
        if not isinstance(review, dict):
            continue
        user = review.get("user") or {}
        if (
            isinstance(user, dict)
            and user.get("login") == reviewer_login
            and review.get("commit_id") == expected_commit
        ):
            matching.append(review)
    if not matching:
        return ["no GitHub review matches the declared reviewer and exact release commit"]

    # Review IDs are monotonic. An earlier approval cannot mask a later
    # request for changes or dismissal by the same reviewer on the same SHA.
    matching.sort(key=lambda item: item.get("id") if isinstance(item.get("id"), int) else -1)
    review = matching[-1]
    errors: list[str] = []
    if review.get("state") != "APPROVED":
        errors.append("latest exact-commit reviewer state is not APPROVED")
    if review.get("author_association") not in TRUSTED_ASSOCIATIONS:
        errors.append("reviewer is not an OWNER, MEMBER, or COLLABORATOR")
    if marker not in str(review.get("body") or ""):
        errors.append("GitHub review does not bind the exact promotion manifest SHA256")
    submitted_at = _parse_rfc3339(review.get("submitted_at"))
    if submitted_at is None:
        errors.append("GitHub review submitted_at must be timezone-aware RFC3339")
    elif submitted_at < generated_at:
        errors.append("GitHub review predates the promotion manifest")
    return errors


def self_test() -> int:
    commit = "1" * 40
    tag_object = "2" * 40
    digest = "sha256:" + ("a" * 64)
    repository = "d-init-d/d-research-skill"
    workflow = ".github/workflows/lint-and-self-test.yml"
    ci = {
        "workflow_runs": [
            {
                "head_sha": commit,
                "path": workflow,
                "status": "completed",
                "conclusion": "success",
                "head_repository": {"full_name": repository},
            }
        ]
    }
    tag = {
        "sha": tag_object,
        "object": {"type": "commit", "sha": commit},
        "verification": {"verified": True, "reason": "valid"},
    }
    review = [
        {
            "id": 7,
            "user": {"login": "independent-reviewer"},
            "commit_id": commit,
            "state": "APPROVED",
            "author_association": "MEMBER",
            "body": f"D-Research-Promotion-SHA256: {digest}",
            "submitted_at": "2026-07-13T00:00:00Z",
        }
    ]
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        duplicate = Path(td) / "duplicate.json"
        duplicate.write_text('{"sha": "a", "sha": "b"}', encoding="utf-8")
        nonfinite = Path(td) / "nonfinite.json"
        nonfinite.write_text('{"value": NaN}', encoding="utf-8")
        for label, path in (("duplicate-key", duplicate), ("non-finite", nonfinite)):
            try:
                _load_json(path)
            except ValueError:
                pass
            else:
                failures.append(f"{label} GitHub response JSON was accepted")
    if validate_ci_response(
        ci,
        expected_sha=commit,
        repository=repository,
        workflow_path=workflow,
    ):
        failures.append("valid exact-SHA CI response rejected")
    bad_ci = json.loads(json.dumps(ci))
    bad_ci["workflow_runs"][0]["head_sha"] = "3" * 40
    if not validate_ci_response(
        bad_ci,
        expected_sha=commit,
        repository=repository,
        workflow_path=workflow,
    ):
        failures.append("wrong-SHA CI response accepted")
    bad_ci_repo = json.loads(json.dumps(ci))
    bad_ci_repo["workflow_runs"][0]["head_repository"]["full_name"] = "attacker/fork"
    if not validate_ci_response(
        bad_ci_repo,
        expected_sha=commit,
        repository=repository,
        workflow_path=workflow,
    ):
        failures.append("wrong-repository CI response accepted")
    if validate_tag_response(tag, expected_tag_object=tag_object, expected_commit=commit):
        failures.append("valid GitHub-verified annotated tag rejected")
    bad_tag = json.loads(json.dumps(tag))
    bad_tag["verification"]["verified"] = False
    if not validate_tag_response(bad_tag, expected_tag_object=tag_object, expected_commit=commit):
        failures.append("unverified tag accepted")
    bad_tag_target = json.loads(json.dumps(tag))
    bad_tag_target["object"]["sha"] = "4" * 40
    if not validate_tag_response(
        bad_tag_target,
        expected_tag_object=tag_object,
        expected_commit=commit,
    ):
        failures.append("wrong tag target accepted")
    if validate_review_response(
        review,
        expected_commit=commit,
        promotion_sha256=digest,
        reviewer_login="independent-reviewer",
        pull_request_author="release-author",
        promotion_generated_at="2026-07-12T00:00:00Z",
    ):
        failures.append("valid GitHub review attestation rejected")
    bad_review = json.loads(json.dumps(review))
    bad_review[0]["body"] = "approved without a hash binding"
    if not validate_review_response(
        bad_review,
        expected_commit=commit,
        promotion_sha256=digest,
        reviewer_login="independent-reviewer",
        pull_request_author="release-author",
        promotion_generated_at="2026-07-12T00:00:00Z",
    ):
        failures.append("review without promotion-hash binding accepted")
    later_change_request = json.loads(json.dumps(review))
    later_change_request.append(
        {
            **later_change_request[0],
            "id": 8,
            "state": "CHANGES_REQUESTED",
        }
    )
    if not validate_review_response(
        later_change_request,
        expected_commit=commit,
        promotion_sha256=digest,
        reviewer_login="independent-reviewer",
        pull_request_author="release-author",
        promotion_generated_at="2026-07-12T00:00:00Z",
    ):
        failures.append("later change request was masked by an earlier approval")
    untrusted_review = json.loads(json.dumps(review))
    untrusted_review[0]["author_association"] = "NONE"
    if not validate_review_response(
        untrusted_review,
        expected_commit=commit,
        promotion_sha256=digest,
        reviewer_login="independent-reviewer",
        pull_request_author="release-author",
        promotion_generated_at="2026-07-12T00:00:00Z",
    ):
        failures.append("untrusted external review accepted")
    if not validate_review_response(
        review,
        expected_commit=commit,
        promotion_sha256=digest,
        reviewer_login="independent-reviewer",
        pull_request_author="independent-reviewer",
        promotion_generated_at="2026-07-12T00:00:00Z",
    ):
        failures.append("self-review was accepted as independent attestation")
    if failures:
        print("release_verify self-test FAILED:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print("release_verify self-test ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")

    ci = sub.add_parser("verify-ci-response")
    ci.add_argument("--input", required=True, type=Path)
    ci.add_argument("--expected-sha", required=True)
    ci.add_argument("--repository", required=True)
    ci.add_argument("--workflow-path", required=True)

    tag = sub.add_parser("verify-tag-response")
    tag.add_argument("--input", required=True, type=Path)
    tag.add_argument("--expected-tag-object", required=True)
    tag.add_argument("--expected-commit", required=True)

    review = sub.add_parser("verify-review-response")
    review.add_argument("--input", required=True, type=Path)
    review.add_argument("--expected-commit", required=True)
    review.add_argument("--promotion-sha256", required=True)
    review.add_argument("--reviewer-login", required=True)
    review.add_argument("--pull-request-author", required=True)
    review.add_argument("--promotion-generated-at", required=True)

    args = parser.parse_args(argv)
    if args.command == "self-test":
        return self_test()
    try:
        payload = _load_json(args.input)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"release verification response is unreadable: {exc}", file=sys.stderr)
        return 2
    if args.command == "verify-ci-response":
        errors = validate_ci_response(
            payload,
            expected_sha=args.expected_sha,
            repository=args.repository,
            workflow_path=args.workflow_path,
        )
    elif args.command == "verify-tag-response":
        errors = validate_tag_response(
            payload,
            expected_tag_object=args.expected_tag_object,
            expected_commit=args.expected_commit,
        )
    else:
        errors = validate_review_response(
            payload,
            expected_commit=args.expected_commit,
            promotion_sha256=args.promotion_sha256,
            reviewer_login=args.reviewer_login,
            pull_request_author=args.pull_request_author,
            promotion_generated_at=args.promotion_generated_at,
        )
    if errors:
        print("release verification FAILED:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"release verification ok ({args.command})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
