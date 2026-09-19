# D Research v3.5.0-rc.2

## v3.5.0-rc.2 Release Notes

## Two research tracks. One auditable answer.

D Research 3.5 introduces evidence-backed dual-track research. Every substantive
research question is investigated through documentary and social branches from
the first round. The branches may run concurrently or interleave on single-slot
hosts, while coverage gates prevent either branch from silently disappearing.

RC2 supersedes RC1 as the candidate eligible for stable promotion. The research
runtime and social-depth implementation are unchanged from RC1. This refresh
places the final v3.5.0 release document inside the frozen package closure and
rebinds candidate metadata, manifests, and promotion checks to RC2.

### Highlights

- **Mandatory dual-track coverage.** Plans create documentary and social work
  for each substantive question, with concurrent or round-robin scheduling and
  explicit anti-starvation checks.
- **Human-style Playwright exploration.** Bounded browser actions cover search,
  dynamic views, truncated content, replies, pagination, scrolling, and
  transcript panels while recording observed state.
- **Execution-backed completion.** Branches require readable captures linked to
  successful activity records. URLs, snippets, evaluator counters, invented
  identifiers, empty captures, and failed actions cannot satisfy coverage.
- **Context and lineage preservation.** Thread structure, replies, corrections,
  author relationships, origin lineage, transcript anchors, contradictions,
  access blockers, and extraction limits remain available for reconciliation.
- **Explicit claim status.** Official evidence, supported community facts,
  unverified leads, contradictions, and blocked sources remain separate in the
  final report.
- **Promotion-safe package closure.** The stable release notes are part of the
  candidate package, so promotion can change metadata without introducing an
  unverified packaged file.

### Upgrade guidance

Use `d-research-3.5.0-rc.2-runtime.tar.gz` for installation testing or
`d-research-3.5.0-rc.2-full.tar.gz` for development and audit work. Verify the
accompanying SHA-256 file before extraction.

Existing routes and the 14/19/22/23/37-column ledger formats remain available.
Workflows that previously treated discovery or parser output as completed
research may now stop at an execution gate until activity logs and hash-bound
captures exist. Preserve `activity-log.json`, `capture-records.json`, and
`research-coverage.json` with the research workspace.

### Compatibility

| Component | Support |
|---|---|
| Python | 3.10 or newer |
| Node.js | 18 or newer |
| Browser integration | Playwright 1.61.1; browser installation remains separate |
| Evidence ledgers | Existing 14/19/22/23/37-column contracts |
| Dual-track evidence | Activity log, capture record, and research coverage schemas |
| Distribution | Full/source and runtime profiles |
| Mandatory Python dependencies | No new dependency |

### Validation and assurance

RC2 must pass the same complete validation set as RC1: Python tests, Ruff,
contract and skill validation, package-closure checks, Node/Python self-tests,
hostile, fuzz, mutation, promotion anti-spoof, real Chromium smoke testing,
exact-SHA CI, deterministic artifact checks, signed-tag validation, source
archive reproduction, and provenance attestation.

Browser observations remain environment- and date-specific. Login
requirements, regional controls, anti-bot systems, and site changes can block
collection. A blocked source is recorded as a limitation and cannot be promoted
as supporting evidence.

No independent live baseline-versus-candidate agent benchmark is claimed.
Automated checks and fixtures establish contract behavior and fail-closed
integrity; they do not establish universal factual accuracy or a real-world
quality percentage.

The existing **CC BY-NC 4.0** license is unchanged.

**Full changelog:** [v3.4.2...v3.5.0-rc.2](https://github.com/d-init-d/d-research-skill/compare/v3.4.2...v3.5.0-rc.2)
