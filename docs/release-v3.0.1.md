# D Research v3.0.1 Release Notes

## Overview

D Research v3.0.1 is a focused workflow-hardening release for production agent
research. It takes the strongest orchestration discipline from the MiniMax
expert workflow and folds it back into the portable skill core without tying the
project to MiniMax, any specific subagent runtime, or a single source domain.

The result is a safer pre-synthesis layer: agents now have explicit gates for
source mapping, recall, source-basin coverage, identity/date discipline,
claim-level verification, blockers, and final readiness before presenting
non-trivial research as complete.

## What Ships

- Portable execution gates in `references/execution-gates.md`.
- Optional worker-role contract for source mapping, recall auditing, public
  source hunting, data extraction, evidence verification, and report synthesis.
- Opt-in Vietnamese source discovery companion in
  `references/vietnamese-source-discovery.md`.
- Updated `SKILL.md`, `AGENTS.md`, README files, and configuration defaults.
- Version metadata bumped to `3.0.1`.

## Why It Matters

The v3.0 core already shipped a broad research stack: browser-first probing,
evidence ledgers, anti-bot fallback, frontier search, research-plan workspaces,
social archival, citation resolution, report generation, OCR, translation,
semantic retrieval, citation graphs, multi-format extraction, deduplication,
cache support, and provenance columns.

v3.0.1 does not add another heavy tool. It improves the operating discipline
around those tools. Agents are now less likely to stop after one promising
source, treat mirrors as independent evidence, overclaim completeness, infer
dates or identity from weak anchors, or synthesize before blockers and coverage
gaps are visible.

## Compatibility

- No new runtime dependencies.
- No evidence-ledger schema change.
- No CLI breaking change.
- Existing v3.0 workspaces, ledgers, reports, and eval fixtures remain valid.
- Subagents remain optional. Hosts without subagent support can run every gate
  manually from the main agent context.

## Recommended Upgrade Path

1. Pull or install `v3.0.1`.
2. Review `references/execution-gates.md`.
3. If your workflow involves Vietnamese or Vietnam-local sources, also review
   `references/vietnamese-source-discovery.md`.
4. Keep `research.executionGates.enabled` set to `true` unless you are running a
   deliberately minimal or benchmark-controlled workflow.
5. Run `npm run refs:check:decision-tree` and the usual self-tests before
   publishing a downstream package.

## Release Positioning

This is a production patch release. It is intentionally conservative: the
surface area is mostly documentation, workflow routing, and configuration. The
upgrade improves research reliability without narrowing the skill's scope or
changing its safety model.
