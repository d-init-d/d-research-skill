# Research Intake

Use this file before choosing a research branch. Its job is to classify the
request, set the safety posture, choose the right references to load, and avoid
drifting into the wrong workflow later.

The intake is a **routing controller**, not a substitute for research. It should
be fast, conservative, and multi-label. Most real tasks have more than one
shape, for example "academic review + dataset collection" or "public-role
person + Vietnamese local sources".

## Intake Objectives

Before opening sources or running broad searches, determine:

- what object is being researched;
- what kind of output the user expects;
- which workflow branches apply;
- whether safety or privacy boundaries apply before any source access;
- whether the task is small enough for a fast path or needs the full workflow;
- which references, scripts, ledgers, and gates are required.

Do not overfit the request to the first obvious label. Use all labels that
change how the agent should search, verify, extract, or report.

## Step 0 Card

For every non-trivial research request, write or internally maintain a short
classification card:

```markdown
## Research intake

- User goal:
- Primary object: fact / URL / person / organization / product / dataset /
  paper set / policy / market / event / other
- Shape labels:
- Safety posture:
- Freshness requirement:
- Geography/language scope:
- Source expectations:
- Output artifact:
- Required references:
- Required ledgers/templates:
- Execution gates:
- Ambiguities:
- Route:
```

For simple user-facing answers, do not dump the full card unless useful. For
audit-grade work, plan files, or blocker reports, include a compact version.

## Hard-Stop Layer

Run this layer before any source access:

1. **Access boundary.** If the request asks to bypass login, paywalls, captchas,
   rate limits, robots restrictions, deleted/private content, or other access
   controls, refuse or redirect to lawful public/manual retrieval.
2. **Person/privacy boundary.** If the request targets a private individual,
   minor, home address, personal contact, family details, private accounts,
   private photos, whereabouts, sensitive status, harassment, stalking,
   doxxing, or pseudonym re-identification, apply
   `references/person-aggregation.md` and refuse if out of scope.
3. **Sensitive/high-stakes boundary.** For legal, medical, financial, safety,
   or other high-stakes topics, prioritize primary official sources and present
   evidence synthesis only; do not provide professional advice beyond the
   evidence.
4. **Credential boundary.** If credentials, API keys, database access, or logged
   in browsing are needed, use only user-provided lawful access and keep the
   operation read-only unless explicitly authorized.

If a hard stop applies, do not continue into broad source discovery just because
public snippets exist.

## Shape Labels

Assign one or more labels. Prefer the most specific labels first.

| Label | Use when | Primary route |
|---|---|---|
| `atomic_fact` | One entity + one attribute + deterministic primary source. | `references/fact-verification.md` |
| `public_url_analysis` | User gives a URL to inspect, summarize, extract, or verify. | Probe URL first, then route by content. |
| `public_social_post` | User asks to capture/archive/analyze one public social post. | `references/social-media-archival.md` |
| `person_public_role` | Named person with public-role purpose and canonical anchor. | `references/person-aggregation.md` |
| `broad_research` | Multi-source synthesis, explainer, comparison, or open-ended question. | Full deep research workflow. |
| `academic_review` | Literature review, paper discovery, thesis/project research, citations. | `references/academic-research-protocol.md` |
| `systematic_review` | Systematic, scoping, rapid, PRISMA, screening, inclusion/exclusion. | `references/systematic-review-protocol.md` |
| `dataset_collection` | Need rows/records, coverage, schema, data dictionary, exports. | Crawl/extraction + `references/data-processing-pipeline.md` |
| `structured_extraction` | Tables, JSON-LD, embedded JSON, PDFs, files, APIs, sitemaps. | `references/data-extraction-toolbox.md` |
| `api_or_database` | REST/GraphQL/SPARQL/API pagination or read-only database access. | `references/api-access-workflow.md`, adapters |
| `technical_research` | Software, specs, docs, repos, releases, changelogs, issues. | Source map + code/developer sources. |
| `market_competitor` | Vendors, pricing, product claims, market landscape. | Source map + official/secondary/contradiction pass. |
| `legal_government_financial` | Laws, regulations, filings, patents, finance, public policy. | `references/specialized-domains.md` |
| `medical_or_safety` | Health, medicine, security, safety, compliance, risk. | Primary official/high-quality sources; caveated synthesis. |
| `monitoring_change` | Track changes over time, compare snapshots, watch updates. | `references/monitoring-change-detection.md` |
| `multilingual_local` | Non-English/local sources materially affect recall or authority. | `references/multilingual-research.md` |
| `vietnamese_local` | Vietnamese or Vietnam-local sources are materially relevant. | `references/vietnamese-source-discovery.md` |
| `large_corpus_semantic` | Many documents/ledger rows; conceptual search needed. | `references/semantic-retrieval.md` |
| `long_horizon` | >5 sub-questions, >50 sources, audit-grade, or context risk. | `references/research-plan-protocol.md` |
| `visualization_report` | Charts, rendered reports, PDF/DOCX/HTML output. | `references/data-visualization.md`, `references/report-generation.md` |

If no label fits cleanly, use `broad_research` plus the closest secondary label
and state the assumption.

## Routing Priority

When labels conflict, route in this order:

1. Hard-stop safety/privacy/access checks.
2. `atomic_fact` fast path, unless the user asks for why/context/comparison.
3. `public_social_post` capture branch.
4. `person_public_role` branch with privacy boundary.
5. `public_url_analysis` probe-first branch.
6. `systematic_review` if the user requests PRISMA/screening/review protocol.
7. `academic_review` for literature/paper/citation work.
8. `dataset_collection`, `structured_extraction`, `api_or_database` when the
   deliverable is data rather than prose.
9. `long_horizon` protocol around whichever content branch applies.
10. `multilingual_local` / `vietnamese_local` as recall companions, not global
    defaults.
11. `execution-gates` before synthesis for non-trivial work.

Use multiple routes when needed. Example: a PRISMA review that extracts study
tables is `systematic_review + structured_extraction + dataset_collection`.

## Output Artifact Selection

Choose the artifact early so the workflow does not drift:

- Short answer: atomic fact, single URL, simple clarification.
- Evidence-backed synthesis: broad research, market/technical/legal comparison.
- Evidence ledger: important factual claims, audit-grade work, contested topics.
- Source map: source discovery, obscure topics, low-recall tasks.
- Dataset: rows/records with data dictionary and coverage notes.
- Screening log / PRISMA flow: systematic/scoping/rapid reviews.
- Report workspace: long-horizon or multi-agent work.
- Blocker report: important source cannot be lawfully accessed.
- Monitoring baseline: change detection over time.

If the requested artifact is incompatible with the route, pause and clarify or
state a conservative assumption.

## Safety Posture Values

Use one of these values in the intake card:

- `normal_public`: public non-sensitive sources, standard workflow.
- `person_public_role`: public-role person aggregation with privacy boundary.
- `person_refusal_risk`: likely private-person/minor/doxxing/stalking/sensitive
  request; inspect/refuse before source access.
- `access_restricted`: useful sources may require login, paywall, captcha,
  rate-limited API, or robots restrictions.
- `high_stakes`: legal, medical, financial, safety, compliance, or security
  topic; cite primary sources and caveat.
- `private_or_user_provided`: user provides files, credentials, database access,
  or private corpus; keep local/private unless explicit remote permission.

When uncertain, choose the stricter posture.

## Ambiguity Policy

Ask the user only when ambiguity changes safety, legality, scope, or deliverable.
Otherwise proceed with a stated assumption.

Ask or pause when:

- the subject may be a private person or minor;
- the user may expect login/paywall/captcha bypass;
- the requested output could be professional legal/medical/financial advice;
- the user requests "all sources" but scope/time/geography is undefined enough
  to make the result misleading;
- the deliverable could be either a prose answer or a dataset/report workspace;
- credentials or private files are needed but not provided.

Proceed without asking when:

- labels can be safely combined;
- a conservative route exists;
- the task can be marked partial with clear assumptions;
- the user explicitly prioritizes speed over completeness and the answer can be
  scoped honestly.

## Common Routing Examples

- "What is the current npm version of X?" -> `atomic_fact`; primary registry;
  one independent check.
- "Research browser automation tools for public data collection" ->
  `broad_research + technical_research`; source map, contradiction pass,
  execution gates.
- "Find public information about this maintainer" ->
  `person_public_role`; privacy boundary first; public-role-only output.
- "Collect all rows from this public dashboard" ->
  `public_url_analysis + structured_extraction + dataset_collection`;
  probe URL, discover endpoints/files, data dictionary.
- "Write a literature review with citations" -> `academic_review`; databases,
  citation export, evidence table.
- "PRISMA review of interventions for X" ->
  `systematic_review + academic_review`; screening log and PRISMA flow.
- "Compare changes on this policy page every week" ->
  `monitoring_change`; baseline snapshot and diff plan.
- "Find Vietnamese sources about this local school event" ->
  `vietnamese_local + broad_research`; Vietnamese alias/source-basin matrix,
  identity/date discipline.

## Intake Failure Modes

Watch for these mistakes:

- Treating a person task as generic broad research and missing the privacy
  boundary.
- Treating a broad research task as an atomic fact and stopping after one
  source.
- Treating snippets, mirrors, or social posts as verified primary evidence.
- Starting a PRISMA/systematic review without inclusion/exclusion criteria or a
  screening log.
- Extracting a dataset without defining rows, fields, coverage, and missingness.
- Running Vietnamese/social-source matrices on unrelated global or technical
  tasks.
- Ignoring freshness when the question asks for latest/current state.
- Synthesizing before execution gates have checked coverage, evidence, and
  contradictions.

If an intake mistake is discovered mid-run, stop, reclassify, record the route
change, and continue from the correct branch.
