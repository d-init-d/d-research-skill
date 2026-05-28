# D Research v3.0.2 Release Notes

## Overview

D Research v3.0.2 introduces Step 0: Research Intake. Before an agent opens
sources or commits to a branch, it now classifies the request by research shape,
safety posture, expected artifact, freshness requirement, geography/language
scope, and required gates.

This release closes a practical failure mode in agent research: starting with
the wrong workflow. A person-related task should not begin as generic broad
research; a PRISMA request should not become a loose literature scan; a dataset
request should not end as prose; and a high-stakes topic should not lose its
primary-source posture.

## What Ships

- `references/research-intake.md`: a detailed Step 0 controller with
  multi-label routing, hard-stop safety checks, route priority, output-artifact
  selection, ambiguity policy, and failure-mode guidance.
- `SKILL.md` and `AGENTS.md` now require intake before branch selection and
  source access.
- `research.config.example.json` now exposes `research.intake` defaults.
- README and Vietnamese README now position intake as lifecycle pillar 0.
- Version metadata bumped to `3.0.2`.

## Why It Matters

v3.0.1 hardened the end of the workflow with execution gates. v3.0.2 hardens
the beginning. Together they give agents a stronger operating envelope:

- classify correctly before searching;
- apply privacy and access boundaries before touching sources;
- route academic, systematic, dataset, URL, person, high-stakes, technical, and
  multilingual tasks into the right workflow;
- verify coverage and evidence before synthesis.

The intake remains deliberately multi-label. It does not narrow D Research to a
single taxonomy; it helps the agent compose the right branches when tasks
overlap.

## Compatibility

- No new dependencies.
- No CLI changes.
- No evidence-ledger schema changes.
- Existing v3.0 and v3.0.1 artifacts remain valid.

## Recommended Upgrade Path

1. Pull or install `v3.0.2`.
2. Review `references/research-intake.md`.
3. Keep `research.intake.enabled` and `research.intake.multiLabel` set to
   `true` for normal use.
4. Use `research.intake.emitClassificationCard` for audit-grade workflows where
   the route decision should be visible to reviewers.
5. Run `npm run refs:check:decision-tree` and `npm run self-test` before
   publishing a downstream package.
