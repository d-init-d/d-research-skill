# Final Report Template

Use this template for non-academic deep research outputs.

```markdown
# Research report: [topic]

## Direct answer

[Answer the user's question directly.]

## Key findings

1. **Finding:**
   - Evidence:
   - Confidence:

2. **Finding:**
   - Evidence:
   - Confidence:

3. **Finding:**
   - Evidence:
   - Confidence:

## Evidence summary

| Claim | Best source | Source type | Date | Confidence |
|---|---|---|---|---|

## Data collected

- Sources accessed:
- Pages/files extracted:
- Rows/items collected:
- Fields collected:
- Coverage:

## Sources reached

| Source | URL | Access method | What was extracted |
|---|---|---|---|

## Sources blocked or partial

| Source | URL | Blocker | Manual action needed |
|---|---|---|---|

## Contradictions and caveats

- Contradiction:
- Caveat:
- Unresolved issue:

## Confidence

Overall confidence: high / medium / low

Why:

## Next research steps

1.
2.
3.
```

## Compact answer format

Use for small tasks:

```markdown
## Answer

## Evidence

## Caveats

## Confidence
```

## Dataset delivery format

```markdown
# Dataset extraction report

## Summary

Unit of observation:
Rows collected:
Fields:
Source domains:
Extraction date:
Coverage:

## Files produced

- raw data:
- cleaned data:
- evidence ledger:
- blocker report:

## Data dictionary

| Field | Type | Description | Example | Source |
|---|---|---|---|---|

## Quality checks

## Blocked sources

## Reproduction steps
```

## Report with data visualization

Use when the research includes quantitative data that benefits from visual representation.

```markdown
# Research report: [topic]

## Direct answer

## Key findings with visualizations

### Finding 1
- Evidence:
- Chart: ![description](path/to/chart1.png)
- Confidence:

### Finding 2
- Evidence:
- Chart: ![description](path/to/chart2.png)
- Confidence:

## Data summary dashboard

See: research-output/dashboard.html

## Evidence summary table

## Sources

## Methodology notes
- Chart generation: matplotlib/plotly
- Data source and date range noted on each chart
```

See references/data-visualization.md for chart type selection and generation guidelines.

## LaTeX academic report template

Use for academic papers, theses, and formal publications.

```latex
\documentclass[12pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage{hyperref}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{natbib}

\title{[Research Title]}
\author{[Author]}
\date{\today}

\begin{document}
\maketitle
\begin{abstract}
[Abstract text]
\end{abstract}

\section{Introduction}
\section{Methodology}
\section{Results}
\section{Discussion}
\section{Conclusion}

\bibliographyle{apalike}
\bibliography{references}
\end{document}
```

Pair with exported BibTeX file from references/citation-management.md.

## Citation list format

Append to any report that uses academic sources:

```markdown
## References

### Formatted reference list (APA 7)

1. Author, A. A. (Year). Title of work. *Journal Name*, Volume(Issue), pages. https://doi.org/xxx

### Machine-readable exports

- BibTeX: research-output/references.bib
- RIS: research-output/references.ris

### Citation statistics

- Total unique sources cited: N
- Source types: journal articles (X), conference papers (Y), reports (Z), web (W)
- Date range: YYYY - YYYY
- Sources with DOI: N/M (percentage)
```
