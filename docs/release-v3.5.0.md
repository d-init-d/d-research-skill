# D Research v3.5.0

## v3.5.0 Release Notes

## Two research tracks. One auditable answer.

D Research 3.5 introduces evidence-backed dual-track research. Every research
question is investigated through a documentary branch and a social branch from
the first round. The two branches may run concurrently or interleave on
single-slot hosts, but neither branch can silently disappear from the final
coverage decision.

This stable release promotes the signed D Research 3.5 candidate after
exact-SHA CI, signed-tag validation, deterministic archive reproduction, and
source provenance attestation completed successfully.

### Highlights

- **Mandatory documentary and social coverage.** Research plans create both
  branches for every substantive question. Scheduling records real overlap on
  multi-slot hosts and round-robin progress on single-slot hosts.
- **Human-style social exploration with Playwright.** The browser operator can
  search, open dynamic views, expand truncated posts and replies, paginate,
  scroll, and open transcript panels. Every action is bounded and recorded.
- **Execution-backed completion.** A URL, an invented identifier, a search
  snippet, or an evaluator-written counter cannot complete a branch. Source
  IDs must resolve to readable captures linked to successful execution logs,
  with byte length and SHA-256 verified from disk.
- **Deep context preservation.** Social evidence retains thread structure,
  nested replies, correction context, transcript anchors, author relationship,
  origin lineage, and extraction limits instead of flattening posts into
  isolated quotes.
- **Claim separation and reconciliation.** Official statements, verified
  community facts, unverified leads, contradictions, and blocked sources remain
  distinct. Cross-branch agreement can strengthen a finding; repetition and
  repost volume cannot manufacture corroboration.
- **Honest browser failure semantics.** Blocked navigation, login walls,
  timeouts, context replacement, empty SPA shells, and failed actions are
  persisted as limitations. They return failure status and cannot emit source
  captures.

### Why this release matters

Official and documentary sources provide authority, records, and stable
citations. Social sources often reveal first-hand reports, corrections,
specialist discussion, local context, and disputed details earlier than formal
publication. D Research 3.5 investigates both evidence basins while preserving
their different verification status.

The social branch does not override documentary evidence by popularity. It
widens discovery and exposes disagreement. Final claims still require
source-level support, lineage checks, contradiction handling, and explicit
confidence.

### Upgrade guidance

Use `d-research-3.5.0-runtime.tar.gz` for normal installation or
`d-research-3.5.0-full.tar.gz` for development and audit work. Verify
the accompanying SHA-256 file before extraction.

Existing research routes and the 14/19/22/23/37-column ledger formats remain
available. Workflows that previously treated URL discovery or parser output as
completed research may now stop at an execution gate until valid activity logs
and hash-bound captures exist. Integrations should preserve
`activity-log.json`, `capture-records.json`, and
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

The release passed 162 Python tests, Ruff, contract and skill validation,
package-closure checks, the complete Node/Python self-test suite, hostile,
fuzz, mutation, and promotion anti-spoof checks. Real Chromium smoke runs
produced hash-verified readable captures on Hacker News and Tinhte and
correctly refused to promote empty, timed-out, or failed observations from
Bluesky, Mastodon, YouTube, and Reddit in the tested environment.

These smoke observations describe one execution environment and date. They do
not promise permanent access to every platform. Login requirements, regional
controls, anti-bot systems, and site changes can still block collection.

No independent live baseline-versus-candidate agent benchmark is claimed for
this release. Synthetic fixtures and automated checks establish behavior and
fail-closed integrity; they do not establish universal factual accuracy or a
real-world quality percentage.

The existing **CC BY-NC 4.0** license is unchanged.

**Full changelog:** [v3.4.2...v3.5.0](https://github.com/d-init-d/d-research-skill/compare/v3.4.2...v3.5.0)
