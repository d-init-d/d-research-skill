# Research Intake

Use this file before choosing a research branch. Its job is to classify the
request, set the safety posture, choose the right references to load, and avoid
drifting into the wrong workflow later.

The intake is a **routing controller**, not a substitute for research. It should
be conservative and multi-label. It may stay lightweight for ordinary tasks, but
when the user asks for maximum rigor, audit-grade work, due diligence, red-flag
review, or says speed is less important than accuracy, switch to
completeness-first mode. Most real tasks have more than one shape, for example
"academic review + dataset collection", "policy standard + technical
implementation", or "public-role person + Vietnamese local sources".

## Intake Objectives

Before opening sources or running broad searches, determine:

- what object is being researched;
- what kind of output the user expects;
- which workflow branches apply;
- whether safety or privacy boundaries apply before any source access;
- whether the task is small enough for a fast path, needs the standard workflow,
  or needs completeness-first depth;
- which authority model and source basins apply for the domain;
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
- Research depth: fast / standard / completeness-first
- Safety posture:
- Freshness requirement:
- Geography/language scope:
- Authority model / source basins:
- Source expectations:
- Output artifact:
- Required references:
- Required ledgers/templates:
- Execution gates:
- Red-flag or contradiction focus:
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
| `due_diligence_or_investigation` | Check a company, project, vendor, package, team, claim, risk, provenance, credibility, or red flags. | Full workflow + source-quality scoring + contradiction/red-flag pass + execution gates. |
| `policy_or_standards_analysis` | Standards, RFCs, policies, governance docs, compliance rules, implementation guidance, or versioned norms. | Canonical text/version history + clause evidence + `references/specialized-domains.md` when legal/government applies. |
| `creative_or_cultural_research` | Creative works, media, culture, trends, reception history, fandom/public discourse, archives, or cultural context. | Broad workflow with primary-work, creator/publisher, archive, criticism, and reception source basins. |
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
| `register_jargon_recall` | A clinical/legal/standards/academic query under-recalls because the evidence basin uses lay terms, community jargon, or vernacular slang. | `references/register-and-jargon-expansion.md` |
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
6. `policy_or_standards_analysis` when canonical clauses, version status,
   standards language, or implementation guidance are the authority layer.
7. `systematic_review` if the user requests PRISMA/screening/review protocol.
8. `academic_review` for literature/paper/citation work.
9. `dataset_collection`, `structured_extraction`, `api_or_database` when the
   deliverable is data rather than prose.
10. `due_diligence_or_investigation` when the task is about verifying claims,
    trustworthiness, risk, provenance, or red flags rather than describing a
    market landscape.
11. `creative_or_cultural_research` when authority comes from primary works,
    archives, criticism, reception, or cultural records rather than scientific
    or technical consensus.
12. `long_horizon` protocol around whichever content branch applies.
13. `multilingual_local` / `vietnamese_local` / `register_jargon_recall` as recall
    companions, not global defaults. Activate `register_jargon_recall` only when
    the evidence basin demonstrably uses vernacular, subculture, or domain
    jargon — never on ordinary technical or global tasks.
14. `execution-gates` before synthesis for non-trivial work.

Use multiple routes when needed. Example: a PRISMA review that extracts study
tables is `systematic_review + structured_extraction + dataset_collection`.

## Research Depth Selection

Use the shallowest depth that can be honest, but never optimize speed over the
user's requested confidence.

- `fast`: only for `atomic_fact`, a single public URL, or a user-explicit quick
  answer where the source of truth is narrow and deterministic.
- `standard`: default for ordinary broad research, source-backed synthesis,
  technical research, and market scans.
- `completeness-first`: use when the user asks for maximum rigor, "deep",
  "thorough", "audit", "red flags", "due diligence", "risk", "verify all
  claims", "speed is not important", or the task has high downstream cost.

Completeness-first mode requires:

- a source map before extraction;
- a search log for reproducibility;
- an evidence ledger for key claims and red flags;
- at least one independent recall expansion pass after the first synthesis
  outline;
- a contradiction pass that actively searches for disconfirming evidence;
- no "complete" claim from a single source basin;
- execution gates before final synthesis;
- explicit remaining gaps and blocker notes when evidence cannot be reached
  lawfully.

## Label-Specific Research Playbooks

### `due_diligence_or_investigation`

Use this label when the user wants to know whether an organization, project,
claim, product, package, vendor, investment, partnership, or public-facing team
is trustworthy. Do not treat it as generic market research: the center of
gravity is verification, provenance, contradictions, and red flags.

Minimum source basins:

- official site, documentation, whitepaper, product pages, and archived changes;
- legal/entity registries, filings, procurement records, or public licenses
  when available;
- regulatory notices, sanctions, enforcement actions, court records, patents,
  or consumer-protection records when relevant;
- code repositories, package registries, releases, issues, security advisories,
  and dependency metadata for software projects;
- credible news, analyst reports, reviews, community reports, and independent
  third-party commentary;
- public team/leadership claims only when tied to public professional roles;
- domain, archive, ownership, or timeline evidence when provenance is disputed
  and lawfully public.

Red-flag classes:

- unverifiable or inconsistent identity, ownership, dates, locations, team
  claims, funding, customers, partners, or certifications;
- copied, recycled, deleted, or materially changed claims without disclosure;
- unresolved security issues, abandoned repositories, suspicious releases, or
  dependency risk;
- regulatory, legal, sanctions, fraud, consumer-protection, or safety issues;
- one-basin evidence, synthetic-looking social proof, stale claims, missing
  methodology, or undisclosed conflicts of interest.

Output should separate verified facts, red flags, unresolved risks, benign
unknowns, source coverage, confidence, and recommended manual checks. Phrase
findings as evidence-backed risk signals, not accusations beyond the evidence.
Do not collect private personal data, doxx people, or bypass access controls.

### `policy_or_standards_analysis`

Use this label when the source of authority is a canonical rule text, standards
body, RFC, policy, governance document, implementation guide, compliance rule,
or versioned normative document.

Minimum source basins:

- canonical full text from the issuing body;
- version history, errata, changelog, status page, effective date, and adoption
  notes;
- official implementation guidance, FAQs, interpretation memos, examples, and
  conformance test material;
- related standards, superseded versions, public comments, and compatibility
  notes;
- legal/government sources only when the policy is legally binding or
  jurisdiction-specific.

Verification requirements:

- cite exact clause, section, version, date, and status;
- distinguish normative from informative language;
- preserve `MUST`, `SHOULD`, `MAY`, prohibited, permitted, and optional
  language accurately;
- distinguish draft/proposed/final/superseded/withdrawn text;
- state applicability boundaries, jurisdiction, actor, system, timeframe, and
  exceptions.

Output should include a clause map, obligations, permissions, prohibitions,
implementation implications, changes from prior versions, and caveats. Do not
turn a blog summary into the authority layer.

### `creative_or_cultural_research`

Use this label when the task is about a creative work, artist, genre, media
history, cultural trend, reception, fandom/public discourse, aesthetics,
influence, or historical context. Authority is not the same as scientific or
technical consensus.

Minimum source basins:

- primary work, official release, creator/publisher/studio/label/gallery page,
  liner notes, credits, catalog entries, or official archives;
- interviews, statements, production notes, and contemporaneous records;
- reviews, criticism, scholarly/cultural studies, retrospectives, trade press,
  and reputable media histories;
- public metrics when relevant and available, such as charts, box office,
  circulation, festival records, awards, catalogs, or platform-visible counts;
- fan/community/social sources only as reception evidence, not as verified fact
  about creators or private people;
- local-language and era-specific archives when they materially affect recall.

Verification requirements:

- distinguish primary text, creator statement, critical interpretation,
  reception signal, trend signal, and later mythmaking;
- cite release dates, editions, versions, translations, remasters, region, and
  platform when they change the claim;
- avoid "popular", "influential", "first", or "widely regarded" claims without
  source-basin support;
- preserve uncertainty for cultural interpretations and contested histories.

Output should separate primary evidence, critical reception, cultural context,
trend signals, contested interpretations, and confidence. Treat community
discussion as a map of reception, not as factual authority by itself.

## Output Artifact Selection

Choose the artifact early so the workflow does not drift:

- Short answer: atomic fact, single URL, simple clarification.
- Evidence-backed synthesis: broad research, market/technical/legal comparison.
- Evidence ledger: important factual claims, audit-grade work, contested topics.
- Due-diligence brief: verified facts, red flags, unresolved risks, manual
  checks, and confidence.
- Policy/standards brief: clause map, version/status, obligations, exceptions,
  implementation implications, and caveats.
- Cultural research brief: primary evidence, reception, cultural context, trend
  signals, contested interpretations, and confidence.
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
- "Check whether this AI startup is legitimate and list red flags" ->
  `due_diligence_or_investigation + market_competitor`; completeness-first,
  source map, evidence ledger, contradiction/red-flag pass.
- "Explain what RFC 9110 requires for this HTTP behavior" ->
  `policy_or_standards_analysis + technical_research`; canonical RFC clauses,
  normative/informative distinction, implementation notes.
- "Research why this film became a cult classic" ->
  `creative_or_cultural_research`; primary release/creator sources,
  criticism, reception, archives, and caveats.

## Intake Failure Modes

Watch for these mistakes:

- Treating a person task as generic broad research and missing the privacy
  boundary.
- Treating a broad research task as an atomic fact and stopping after one
  source.
- Treating snippets, mirrors, or social posts as verified primary evidence.
- Treating due diligence as a generic market overview and missing provenance,
  ownership, risk, contradiction, or red-flag checks.
- Treating policy/standards analysis as a blog-summary task and failing to
  quote canonical clauses, version status, or normative language.
- Treating creative/cultural trend research as a social-only popularity scrape
  instead of separating primary work, criticism, reception, and metrics.
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
