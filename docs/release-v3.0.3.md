# D Research v3.0.3: Classification-First Research Depth

D Research v3.0.3 hardens the earliest and most important decision in an
agentic research run: choosing the right research shape before opening sources.
This release expands Step 0 intake into a stronger classification controller for
teams that prefer auditability, recall, and correct routing over raw speed.

## What's New

- First-class `due_diligence_or_investigation` routing for companies, projects,
  vendors, packages, public claims, provenance, trustworthiness, risk, and
  red-flag checks.
- First-class `policy_or_standards_analysis` routing for standards, RFCs,
  governance policies, compliance rules, and versioned normative texts.
- First-class `creative_or_cultural_research` routing for creative works, media,
  cultural history, trend analysis, archives, reception, and public discourse.
- Completeness-first depth selection for audit-grade, high-risk, due diligence,
  red-flag, and "speed is not important" requests.
- Intake cards now capture research depth, authority model/source basins, and
  red-flag or contradiction focus before discovery begins.
- `research.config.example.json` now exposes depth-control defaults under
  `research.intake`.

## Why It Matters

Many research failures start before the first search query: the agent picks the
wrong authority model. A company risk check becomes a generic market overview, a
standards question becomes a blog-summary task, or a cultural trend question is
treated like a scientific consensus problem.

v3.0.3 fixes that failure mode at the routing layer. The new labels are
multi-label and composable, so they do not narrow the skill. A task can still be
`due_diligence_or_investigation + technical_research + multilingual_local`, or
`policy_or_standards_analysis + public_url_analysis + monitoring_change`, or
`creative_or_cultural_research + dataset_collection`.

## Completeness-First Mode

When completeness-first mode is triggered, agents must use source maps, search
logs, evidence ledgers for key claims, independent recall expansion,
contradiction search, no single-basin completion claims, execution gates, and
explicit gap/blocker notes. This is the right default for risk-heavy research
where confidence matters more than speed.

## Compatibility

- No new runtime dependencies.
- No evidence-ledger schema changes.
- No script CLI changes.
- Existing v3.0, v3.0.1, and v3.0.2 workspaces remain valid.

## Upgrade Notes

Pull the new release and continue using the skill normally. Existing workflows
will behave the same unless the request benefits from the new routing labels or
completeness-first depth. For project-specific behavior, copy
`research.config.example.json` to `research.config.json` and tune the
`research.intake` depth settings.
