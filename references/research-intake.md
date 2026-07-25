# Research Intake

## Contents

- [Intake Objectives](#intake-objectives)
- [Step 0 Card](#step-0-card)
- [Hard-Stop Layer](#hard-stop-layer)
- [Shape Labels](#shape-labels)
- [Routing Priority](#routing-priority)
- [Research Depth Selection](#research-depth-selection)
- [Label-Specific Research Playbooks](#label-specific-research-playbooks)
- [Output Artifact Selection](#output-artifact-selection)
- [Safety Posture Values](#safety-posture-values)
- [Ambiguity Policy](#ambiguity-policy)
- [Common Routing Examples](#common-routing-examples)
- [Intake Failure Modes](#intake-failure-modes)
- [See also](#see-also)

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
- Capability tier: R0 / R1 / R2 / R3 / R4 / RX
- Subject class:
- Source-access and data classes:
- Authorization status / review / expiry:
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
   doxxing, or pseudonym re-identification, classify it as `R2` or `RX` before
   searching. Refuse `RX`; otherwise validate the scope under
   `references/person-aggregation.md` and `references/investigative-research.md`.
3. **Sensitive/high-stakes boundary.** For legal, medical, financial, safety,
   or other high-stakes topics, prioritize primary official sources and present
   evidence synthesis only; do not provide professional advice beyond the
   evidence.
4. **Credential boundary.** If credentials, API keys, database access, or logged
   in browsing are needed, use only user-provided lawful access and keep the
   operation read-only unless explicitly authorized.
5. **Leak/secret boundary.** Never acquire a raw dump or retain, validate, or
   report passwords, tokens, cookies, sessions, MFA material, or private keys.
   A publicly visible raw-leak claim may be a metadata-only lead under
   `references/leaked-data-handling.md`; it is not evidence by itself.
6. **Self-exposure boundary.** Queries about an identifier's breach exposure
   require verified ownership or organizational authorization, a bounded `R3`
   scope, minimum disclosure, and a named recipient. Otherwise use only public
   incident reporting that does not confirm a private identifier.

If a hard stop applies, do not continue into broad source discovery just because
public snippets exist.

## Shape Labels

Assign one or more labels. Prefer the most specific labels first.

| Label | Use when | Primary route |
|---|---|---|
| `atomic_fact` | One entity + one attribute + deterministic primary source. | `references/fact-verification.md` |
| `public_url_analysis` | User gives a URL to inspect, summarize, extract, or verify. | Probe URL first, then route by content. |
| `public_social_post` | User asks to capture/archive/analyze one public social post. | `references/social-media-archival.md` |
| `social_cross_platform` | Claims, reception, statements, or discourse across multiple public platforms. | `references/social-source-research.md`; platform-neutral item classification. |
| `person_osint_scoped` | Named-person OSINT with a public/professional or reviewed public-interest purpose. | `references/person-aggregation.md` + `R2` scope; stop on risk/saturation, not a fixed row cap. |
| `person_public_role` | Compatibility label for a narrow public-role lookup; route through `person_osint_scoped`. | `references/person-aggregation.md` |
| `investigative_osint` | Deep OSINT, entity/alias expansion, evidence graphs, timelines, hypotheses, threat intelligence, or authorized security research. | `references/investigative-research.md`; select `R1`, `R2`, or `R4` and validate scope. |
| `self_exposure_audit` | User-owned identifiers/domains or an authorized organization's exposure metadata. | `references/self-exposure-audit.md`; verified `R3` scope. |
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
3. `self_exposure_audit` only after ownership/authorization checks.
4. `public_social_post` capture branch for one post.
5. `social_cross_platform` for multi-platform claims/reception.
6. `person_osint_scoped` with `R2` subject/privacy/output gates.
7. `investigative_osint` with a validated `R1`-`R4` scope.
8. `public_url_analysis` probe-first branch.
9. `policy_or_standards_analysis` when canonical clauses, version status,
   standards language, or implementation guidance are the authority layer.
10. `systematic_review` if the user requests PRISMA/screening/review protocol.
11. `academic_review` for literature/paper/citation work.
12. `dataset_collection`, `structured_extraction`, `api_or_database` when the
   deliverable is data rather than prose.
13. `due_diligence_or_investigation` when the task is about verifying claims,
    trustworthiness, risk, provenance, or red flags rather than describing a
    market landscape.
14. `creative_or_cultural_research` when authority comes from primary works,
    archives, criticism, reception, or cultural records rather than scientific
    or technical consensus.
15. `long_horizon` protocol around whichever content branch applies.
16. `multilingual_local` / `vietnamese_local` / `register_jargon_recall` as recall
    companions, not global defaults. Activate `register_jargon_recall` only when
    the evidence basin demonstrably uses vernacular, subculture, or domain
    jargon — never on ordinary technical or global tasks.
17. `execution-gates` before synthesis for non-trivial work.

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

Use `investigative_osint`/`R1` when entity and alias expansion, timelines,
relationship graphs, hypotheses, or contradiction-driven frontier search are
material. Use `R2` for a named person and `R4` only for a verified authorized
security scope. Validate `investigation-scope.json` before source access; for a
planned run, bind its exact bytes with `research_plan.py bind-policy` before
approval and dispatch.

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
Put community, anonymous, reposted, raw-leak, or otherwise unverified material
in `Non-official / unverified leads`, with its missing promotion evidence.
Do not collect private personal data, doxx people, or bypass access controls.
Stop on scoped saturation and resource/risk budgets, not a fixed ledger-row cap.

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
- Investigative brief: main findings, non-official/unverified leads, blocked or
  prohibited sources, contradictions/unknowns, confidence/stopping criteria,
  and next verification steps.
- Self-exposure report: redacted owned identifier/domain, incident metadata,
  exposed data classes, verification state, remediation, and short retention;
  never secrets, raw rows, or unrelated victims.
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
- `investigative_scoped`: validated `R1` investigation with risk/saturation gates.
- `person_osint_scoped`: `R2` person research limited to public/professional
  data and a named-recipient/reporting boundary.
- `self_exposure_verified`: `R3` owned-identifier or authorized-organization
  audit with bound authorization and minimum disclosure.
- `authorized_security`: `R4` defensive scope with explicit targets, review,
  expiry, and an authorization hash.
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
  `person_osint_scoped`; `R2` privacy boundary first; public/professional output
  and saturation/risk stopping.
- "Compare claims about this event across Reddit, X, YouTube, and HN" ->
  `social_cross_platform`; classify each item and deduplicate repost lineages.
- "Check whether my owned email appears in breach intelligence" ->
  `self_exposure_audit`; verify ownership, bind `R3`, minimize and redact.
- "Investigate this vendor's ownership and contradictory public claims" ->
  `investigative_osint + due_diligence_or_investigation`; validate `R1`, build
  evidence graph/timeline, search contradictions, separate leads.
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
- Treating a platform as uniformly official/unofficial instead of classifying
  the item, speaker relationship, origin, integrity, and lineage.
- Mixing non-official/unverified leads into main findings or counting `lead`
  rows toward authored claim coverage.
- Treating a raw leak claim as evidence, retaining its URL/content, or using a
  label as proof of lawful authorization.
- Running `R3` without verified ownership, or failing to re-bind policy and
  re-approve after scope bytes change.
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

## See also

- `references/workflow-routes.md`
- `references/execution-gates.md`
- `references/safety-and-access-policy.md`
- `references/investigative-research.md`
- `references/social-source-research.md`
- `references/self-exposure-audit.md`
- `references/leaked-data-handling.md`
