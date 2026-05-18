# Synthesis Patterns — Choosing a Review Type

Use this file when the user asks for a research **review** but has not
named the specific kind, or when they have named one and you need to
sanity-check the fit.

## Decision tree

```
Is the research question narrow enough to enumerate eligible studies?
├── No  → Narrative or scoping review
│   ├── Question is "what is known about X?"          → Narrative review
│   └── Question is "what is the scope of X research?" → Scoping review (PRISMA-ScR)
└── Yes → Is reproducibility critical (publication, policy)?
    ├── No  → Rapid review (PRISMA with documented shortcuts)
    └── Yes → Is the outcome quantitatively comparable across studies?
        ├── No  → Systematic review with narrative synthesis (PRISMA 2020)
        └── Yes → Systematic review with meta-analysis (PRISMA 2020 + MOOSE/Cochrane)
```

## Review types at a glance

| Type | Goal | Search | Screening | Synthesis | Reporting std |
|------|------|--------|-----------|-----------|---------------|
| **Narrative review** | Broad orientation in a field | Iterative, no formal protocol | Author judgement | Prose, thematic | None (light) |
| **Scoping review** | Map the breadth of a research area | Formal protocol, but inclusive | Stage 1 only (title/abstract) | Categorical mapping | PRISMA-ScR |
| **Rapid review** | Time-bounded synthesis for decision support | Formal but limited (fewer databases) | Single screener acceptable | Narrative | PRISMA + Cochrane Rapid Reviews |
| **Systematic review (narrative)** | Reproducible answer to a focused question | Pre-registered protocol; ≥2 databases + grey lit | Dual screener | Narrative grouped by sub-question | PRISMA 2020 |
| **Systematic review (meta-analysis)** | Pooled quantitative effect estimate | As above | As above | Statistical pooling + heterogeneity analysis | PRISMA 2020 + MOOSE/Cochrane |
| **Umbrella review** | Synthesize existing reviews | Search for reviews only | Dual screener | Tabular summary of prior reviews | PRISMA 2020 + Aromataris |
| **Realist review** | Theory-driven explanation of *why* X works | Iterative, theory-led | Theory-fit | Programme theory → CMO triples | RAMESES |

## How this skill supports each type

| Type | Key references | Key templates | Key scripts |
|------|----------------|---------------|-------------|
| Narrative | `references/academic-research-protocol.md` | `templates/evidence-ledger.csv` | `citation_render.py`, `evidence_ledger.py` |
| Scoping | `references/systematic-review-protocol.md` (steps 1–6) | `templates/screening-log.csv`, `templates/prisma-flow.json` | as above |
| Rapid | `references/systematic-review-protocol.md` | as above | as above |
| Systematic (narrative) | `references/systematic-review-protocol.md` | all the above + `templates/data-dictionary.csv` | as above + `score_source.py` |
| Systematic (meta-analysis) | as above; meta-analysis arithmetic done in R/Stata/RevMan, not in this skill | as above | as above |
| Umbrella | `references/systematic-review-protocol.md` adapted | as above | as above |
| Realist | `references/synthesis-patterns.md` (this file); RAMESES guidance | freeform | as above |

## Synthesis structure (narrative reviews)

Independent of review type, narrative synthesis sections should follow
this structure:

1. **Sub-question** — the question the section answers.
2. **Body of evidence** — number of studies, year range, populations.
3. **Findings** — what the evidence says, grouped by themes.
4. **Convergent findings** — what multiple studies agree on, with cites.
5. **Divergent findings** — disagreements and possible reasons.
6. **Quality of evidence** — overall confidence band (e.g. GRADE: high
   / moderate / low / very low) with justification.
7. **Gaps** — what we still don't know.

Each numbered claim in the prose must link to a `claim_id` in the
evidence ledger.

## Common pitfalls

- **Calling a narrative review "systematic"** — only call it systematic
  if there is a pre-registered protocol with reproducible eligibility
  criteria and a documented screening process.
- **Skipping the protocol** — without a protocol, screening decisions
  become unconscious bias.
- **Filtering by language without saying so** — bias by exclusion. If
  you filtered to English, say so and discuss the implications.
- **Citing the abstract** — extract from the full text whenever
  possible; abstracts misrepresent.
- **Confusing "number of papers" with "evidence" — quality and
  independence matter more than count.

## Output stage

After synthesis is complete, produce the final deliverable using `scripts/report_render.py`:

```bash
python scripts/report_render.py render --workspace <dir>
python scripts/report_render.py lint --workspace <dir>
```

This generates a structured Markdown report from the workspace's plan, evidence ledger, and screening log. See `references/report-generation.md` for full details.

## Pre-synthesis retrieval

Before composing each section, retrieve the top-k semantically related claims from the evidence ledger:

```bash
python scripts/embed_corpus.py query-ledger --ledger evidence-ledger.csv --q "sub-question text" --k 10
```

This surfaces relevant evidence even when keyword overlap is low. See `references/semantic-retrieval.md`.

## See also

- `references/systematic-review-protocol.md` — full PRISMA 2020 protocol
- `references/academic-research-protocol.md` — general academic workflow
- `references/source-quality-rubric.md` — quality scoring
- `references/report-generation.md` — final report generation
- `examples/systematic-review-prisma.md` — worked example
