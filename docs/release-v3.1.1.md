# Skill Metadata Compatibility Patch

v3.1.1 Release Notes

D Research v3.1.1 is a focused metadata-compatibility patch for the skill
entrypoint. It does not change the research workflow, routing logic, helper
scripts, evidence-ledger schema, or trigger wording. The release makes the
`SKILL.md` frontmatter more robust for YAML parsers by converting the long
description from a single plain scalar into folded block scalar syntax.

## What's New

- `SKILL.md` now uses `description: >-` for the long skill description. This
  preserves the exact trigger language while avoiding ambiguity around
  colon-bearing text such as `Triggers:`.
- `README.md` and `README.vi.md` now include v3.1.1 in the v3.x release sequence
  so users can distinguish the metadata-hardening patch from the broader v3.1.0
  documentation-polish release.
- Package metadata now reports version `3.1.1` in `pyproject.toml`,
  `package.json`, and `package-lock.json`.

## Why It Matters

The skill entrypoint is the first file a runtime reads when deciding whether and
how to load D Research. The previous one-line description was valid in many YAML
parsers, but long plain scalars containing colon-bearing phrases can be brittle
across stricter or less forgiving parser implementations. v3.1.1 removes that
parser ambiguity without narrowing the skill, changing trigger intent, or
touching the operational research instructions.

## Compatibility

- No workflow behavior changes.
- No trigger text changes.
- No new dependencies.
- No evidence-ledger schema changes.
- No script CLI changes.
- Existing v3.1.0 workspaces, ledgers, reports, eval fixtures, and release tags
  remain valid.

## Upgrade Notes

Pull v3.1.1 if you want the safest public skill metadata surface. No migration is
required from v3.1.0; this release only hardens the YAML frontmatter format while
preserving the same D Research behavior.
