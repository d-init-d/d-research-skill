# D Research Agent Instructions

Use D Research for deep or multi-source research, lawful public-data collection,
source discovery, literature/market/technical research, due diligence,
policy/standards analysis, cultural research, and the narrow lookup routes below.
Default browser automation is Playwright; access is read-only unless the user
explicitly authorizes an in-scope archival submission.

Treat `templates/route-manifest.json` as the canonical route/gate contract shared with `SKILL.md`.
Use `references/workflow-routes.md` as the narrative decision tree. Do not dispatch until `execute_ready`/`dispatch_ready` passes; preserve the canonical
`plan_ready`, `synthesize_ready`, and `release_ready` assertion sets.

## Mandatory flow

1. Classify with `references/research-intake.md` before opening sources. Resolve
   hard-stop safety, privacy, legality, and access issues first. Ask only when an
   ambiguity changes safety, scope, or deliverable.
2. Select the narrowest matching route. Atomic fact, social-post, public-role
   person, and single-URL branches override the broad workflow when their entry
   conditions hold; follow their branch-specific output contracts.
3. For broad work, restate the goal; decompose questions/entities/aliases;
   create the source map; fan out official, primary, dataset, recent, and
   contradiction queries; probe browser-first; extract least-invasively; expand
   within limits; maintain the evidence ledger; and search for contradictions.
4. For more than 5 sub-questions, more than 50 sources, multi-context runtime,
   or audit-grade output, wrap the route in `references/research-plan-protocol.md`.
   Create one schema-2.0 workspace, configure execution, render, pass
   `plan_ready`, approve, then pass `execute_ready` before any task starts.
   `synthesize_ready` applies to research-phase tasks only and requires a real
   HMAC via `D_RESEARCH_LEDGER_KEY`; `release_ready` additionally requires
   terminal synthesis tasks/outputs, exact report and citations, 100% authored
   claim coverage, and satisfied stopping criteria. Report the workspace path.
5. Before non-trivial synthesis, apply `references/execution-gates.md`. Do not claim completeness unless the relevant execution gates passed.
6. Finish with `references/reproducibility-checklist.md`; render/lint planned
   reports with `scripts/report_render.py` and score important sources with
   `scripts/score_source.py`.

## Canonical route index

- Atomic fact: `references/fact-verification.md`
- Public social post: `references/social-media-archival.md`
- Named public-role person: `references/person-aggregation.md`
- Semantic corpus: `references/semantic-retrieval.md`
- Broad, due-diligence, policy, and cultural routing: `references/workflow-routes.md`, `references/research-intake.md`
- Technical/market: `references/source-discovery.md`, `references/source-quality-rubric.md`
- Legal/government/financial and medical/safety: `references/specialized-domains.md`
- Dataset/structured extraction: `references/data-extraction-toolbox.md`, `references/data-processing-pipeline.md`
- Academic/citations: `references/academic-research-protocol.md`, `references/citation-management.md`
- Systematic/PRISMA: `references/systematic-review-protocol.md`
- Single URL: `references/browser-first-crawl.md`, `references/anti-bot-fallback.md`
- API/database: `references/api-access-workflow.md`
- Large-scale collection: `references/large-scale-collection.md`
- Monitoring: `references/monitoring-change-detection.md`
- Visualization/rendered report: `references/data-visualization.md`, `references/report-generation.md`
- Multilingual/Vietnamese: `references/multilingual-research.md`, `references/vietnamese-source-discovery.md`
- Thin recall/jargon: `references/register-and-jargon-expansion.md`
- Broad-work evidence gaps only: `references/frontier-search.md`

## Safety invariants

- Read only by default; use only lawfully provided credentials.
- Never bypass login, paywalls, captchas, rate limits, robots restrictions, or
  access controls; captcha solving and stealth/anti-detection plugins are never allowed.
- Refuse private-person profiling, minors, harassment, stalking, doxxing,
  pseudonym re-identification, and collection of sensitive personal details.
- Stop after the bounded fallback chain fails on repeated 403/429/captcha/login
  walls. Record blocked attempts and resource-limit truncation explicitly.
- Never turn a configured crawl or resource limit into a claim of completeness.

Broad/non-trivial outputs include the direct answer, findings, evidence,
collected data, reached/blocked sources, gaps, caveats, confidence, and next
steps. Narrow fast paths include only what their reference requires. Academic
outputs include formatted citations.
