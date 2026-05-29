# Topic Decomposition

Use this file when the task is broad, ambiguous, academic, or multi-source.

## Goal

Convert a vague research request into a controllable research graph.

## Decomposition methods

### 1. Research scope frame

Capture:
- subject
- objective
- population or target group
- geography
- timeframe
- required freshness
- expected output
- decision the research will support

### 2. Facet tree

Split the topic into facets:
- who: people, organizations, communities, stakeholders
- what: products, concepts, technologies, variables, datasets
- where: geography, websites, repositories, institutions
- when: date range, versions, releases, policy periods
- why: motivations, causal claims, controversies
- how: mechanisms, methods, implementation details
- how much: quantities, prices, metrics, usage, impact

### 3. Entity and alias expansion

For each entity, list:
- official name
- common abbreviations
- old names
- translated names
- product names
- project names
- ticker or registry identifiers when applicable
- domain names and repository names
- register/jargon variants: lay, community, and vernacular terms for the same concept when the evidence basin uses them (see `references/register-and-jargon-expansion.md`)

### 4. Question graph

Create a graph instead of one linear list:

- root question
  - definition questions
  - factual lookup questions
  - mechanism questions
  - timeline questions
  - comparison questions
  - evidence-quality questions
  - contradiction questions
  - data-collection questions

### 5. Academic frames

Use the frame that fits the field:

- PICO: population, intervention, comparison, outcome
- PICOC: population, intervention, comparison, outcome, context
- SPIDER: sample, phenomenon of interest, design, evaluation, research type
- CIMO: context, intervention, mechanism, outcome
- 5W1H: who, what, when, where, why, how

### 6. Data target frame

When the user wants a dataset, define:
- target unit of observation
- fields to collect
- allowed sources
- expected row count
- deduplication key
- freshness requirement
- acceptable missingness
- output format

## Output template

```markdown
## Research decomposition

Root question:

Scope:
- timeframe:
- geography:
- languages:
- source types:
- exclusions:

Sub-questions:
1.
2.
3.

Facets:
- entities:
- concepts:
- metrics:
- source classes:

Synonyms and aliases:

Likely data layers:

Unknowns:

Stopping criteria:
```

## Stopping criteria

Stop searching only when one of these is true:
- the evidence ledger has enough primary evidence for every key claim
- additional searches are returning duplicates or low-quality sources
- a source is blocked and a blocker report has been produced
- the task budget set by the user is reached
- the remaining unknowns are explicitly documented
