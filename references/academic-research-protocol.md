# Academic Research Protocol

Use this file for theses, school projects, literature reviews, research reports, and systematic or rapid reviews.

## Academic modes

Choose the mode that fits the user's need:

- exploratory review: broad learning and source discovery
- rapid review: faster synthesis with explicit shortcuts
- systematic-lite review: reproducible search, screening, and evidence table
- full systematic review: formal protocol, inclusion/exclusion, screening flow, quality assessment
- technical survey: methods, tools, benchmarks, limitations, future work
- data collection project: dataset design, extraction, cleaning, analysis plan

## Research question setup

Define:
- research objective
- primary research question
- secondary questions
- scope and exclusions
- disciplines/databases/web sources
- source date range
- languages
- inclusion criteria
- exclusion criteria
- expected output format

## Search protocol

For reproducibility, log:
- search tool or database
- exact query string
- date searched
- filters used
- number of results reviewed
- candidate sources kept
- exclusion reasons

## Screening protocol

For each candidate source, record:
- title
- author or organization
- year/date
- URL/DOI
- source type
- included/excluded
- exclusion reason
- relevance score
- quality score

## Evidence extraction

Extract:
- research question answered
- method used
- dataset or sample
- key findings
- limitations
- metrics
- assumptions
- citations to primary data
- notes for synthesis

## Quality appraisal

Assess:
- source authority
- methodological clarity
- data transparency
- recency
- reproducibility
- bias and conflicts
- peer review status
- relevance to the question

## Synthesis methods

Use one or more:
- thematic synthesis
- method taxonomy
- timeline synthesis
- comparison matrix
- evidence strength grading
- gap analysis
- contradiction analysis
- future work map

## Academic final report template

```markdown
# Title

## Abstract or executive summary

## 1. Introduction
- background
- problem statement
- research questions
- scope

## 2. Methodology
- search strategy
- sources/databases/tools
- inclusion/exclusion criteria
- screening process
- extraction fields
- quality assessment

## 3. Findings
- finding 1
- finding 2
- finding 3

## 4. Evidence table

## 5. Discussion
- interpretation
- contradictions
- limitations
- research gaps

## 6. Conclusion

## References

## Appendix
- search log
- screening log
- blocked sources
```

## Database search workflow

For systematic reviews and literature reviews, supplement web searches with academic database APIs:

1. **OpenAlex** (recommended first): search /works with topic query + year filter + concept filter. Use cursor pagination. Returns DOI, title, abstract, citation count, referenced works.
2. **CrossRef**: enrich metadata for papers found via DOI lookup. Get full author lists, journal info, funding data.
3. **Semantic Scholar**: find related papers, citation graphs, and influential citations.
4. **PubMed**: required for biomedical/clinical topics. Use MeSH terms for precise searches.
5. **arXiv**: for CS, physics, math, quantitative biology/finance preprints.

Workflow:
- Run the same query across multiple databases
- Deduplicate results by DOI
- Record which databases yielded which sources in search-log
- Cross-reference citation lists between databases
- Use snowballing on highly-cited papers

See `references/academic-databases.md` for endpoint details and rate limits.

## Citation export

After evidence extraction is complete:

1. Collect all unique sources from the evidence ledger
2. Enrich source metadata via CrossRef DOI lookup
3. Deduplicate by DOI or exact title match
4. Export in user's preferred format:
   - BibTeX (.bib) for LaTeX workflows
   - RIS (.ris) for Zotero/Mendeley/EndNote import
   - Formatted reference list (APA 7, IEEE, Chicago, Vancouver)
5. Include citation in final report

Use `scripts/citation_export.py` for automated export.
See `references/citation-management.md` for full workflow.

## Academic integrity

Never invent citations. Mark inaccessible papers, uncertain claims, and sources requiring manual retrieval.
