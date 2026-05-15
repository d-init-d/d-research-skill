# Scientific Literature Review: Systematic Review Example

## Research Query

> "Do a systematic literature review on transformer architectures for time series forecasting, 2022-2026."

---

## Step 1: Define Research Questions and Scope

```json
{
  "primary_question": "What transformer architectures have been proposed for time-series forecasting, and how do they compare in predictive performance?",
  "secondary_questions": [
    "What attention mechanisms are used in time-series transformers?",
    "What are the computational complexity trade-offs?",
    "Which benchmark datasets are most commonly used for evaluation?"
  ],
  "scope": {
    "date_range": "2022-01-01 to 2026-12-31",
    "languages": ["en"],
    "publication_types": ["journal-article", "conference-paper", "preprint"]
  }
}
```

---

## Step 2: Build Search Strings (PICO Framework)

```json
{
  "population": "time series data",
  "intervention": "transformer architecture",
  "comparison": "traditional methods (LSTM, ARIMA)",
  "outcomes": ["forecasting accuracy", "computational efficiency"],
  "search_string": "(transformer OR 'self-attention' OR 'cross-attention') AND (time series OR temporal OR forecasting) AND (predict* OR forecast*)"
}
```

---

## Step 3: Query Academic APIs

```
Searching OpenAlex...     Found: 847 papers
Searching Semantic Scholar... Found: 612 papers  
Searching arXiv...         Found: 234 papers
Deduplicated total:        1,247 unique papers
```

---

## Step 4: Apply Inclusion/Exclusion Criteria

| Criterion | Include | Exclude |
|-----------|---------|---------|
| Date range | 2022-2026 | Pre-2022 |
| Topic match | Transformer + time-series | Non-forecasting |
| Full text available | Yes | No |
| Peer-reviewed | Yes | Preprints only (if flagged) |

**Result**: 1,247 → 312 after title/abstract screening → 89 after full-text review

---

## Step 5: Search Log Created

```yaml
search-log:
  - date: 2026-01-15
    source: openalex
    query: "(transformer AND time series AND forecast*)"
    results: 847
    filters: "year:2022-2026, type:article"
  - date: 2026-01-15
    source: semantic_scholar
    query: "\"transformer architecture\" \"time series\""
    results: 612
    filters: "from 2022 to 2026"
  - date: 2026-01-15
    source: arxiv
    query: "cs.LG transformer time series forecasting"
    results: 234
```

---

## Step 6: Screening Log Created

```yaml
screening-log:
  - paper_id: alexnet2023
    title: "Informer: Beyond Efficient Transformer for Long Sequence Time-Series Forecasting"
    decision: include
    reason: "Core transformer architecture for time series"
    screened_by: agent
  - paper_id: resnet2024
    title: "Deep Residual Learning for Image Recognition"
    decision: exclude
    reason: "Computer vision domain, not time series"
    screened_by: agent
```

---

## Step 7: Snowball Sampling

```
Backward citations from 12 key papers:  +89 papers
Forward citations (cited-by) tracked:  +156 papers
After snowball screening:               +34 papers included
```

---

## Step 8: Evidence Ledger Extracted

```yaml
evidence-ledger:
  - study: "Informer (AAAI 2021)"
    architecture: "ProbSparse Self-Attention"
    dataset: "ETT, Weather, Electricity"
    mae: 0.372
    mse: 0.241
    complexity: "O(L log L)"
  - study: "Autoformer (NeurIPS 2022)"
    architecture: "Series Decomposition + Auto-Correlation"
    dataset: "ETT, Weather, Electricity"
    mae: 0.338
    mse: 0.215
    complexity: "O(L log L)"
  - study: "PatchTST (ICLR 2023)"
    architecture: "Patch + Channel Independence"
    dataset: "ETT, Weather, M4, M5"
    mae: 0.298
    mse: 0.187
    complexity: "O(L²)"
```

---

## Step 9: Contradiction Analysis

```
⚠ CONTRADICTION DETECTED:
  - Study A (PatchTST): Claims channel independence improves over channel mixing
  - Study B (Crossformer): Reports channel mixing superior on multivariate tasks
  - Resolution: Context-dependent; channel independence better for transfer learning
```

---

## Step 10: BibTeX Export Generated

```bibtex
@article{liu2022informer,
  title={Informer: Beyond Efficient Transformer for Long Sequence Time-Series Forecasting},
  author={Zhou, Haoyi and Shang, Jiawei and others},
  journal={AAAI},
  year={2022}
}

@article{wu2023patchtst,
  title={PatchTST: A Truncate Prediction Model for Time Series},
  author={Nie, Yuqi and others},
  journal={ICLR},
  year={2023}
}
```

---

## Step 11: Thematic Synthesis

### Theme 1: Architectural Innovations
- Patch-based tokenization (PatchTST, Patch-Decomposition)
- Efficient attention mechanisms (ProbSparse, LogTrans)
- Series decomposition integration (Autoformer, FEDformer)

### Theme 2: Evaluation Practices
- ETT dataset family dominates benchmarks
- Lack of standardized cross-domain evaluation
- Inconsistent reporting of computational metrics

---

## Step 12: Final Academic Report (IMRaD)

---

# Transformer Architectures for Time-Series Forecasting: A Systematic Review (2022-2026)

## Abstract

This systematic review synthesizes 123 studies on transformer architectures for time-series forecasting published 2022-2026. Key findings: (1) Patch-based approaches consistently outperform point-wise attention; (2) Computational complexity reduced from O(L²) to O(L log L); (3) Channel independence shows superior transfer learning capability.

## Introduction

Transformers have revolutionized sequence modeling since their introduction in NLP...

## Methods

Searches conducted across OpenAlex, Semantic Scholar, and arXiv using structured queries...

## Results

### Architectural Categories
### Performance Benchmarks
### Efficiency Comparisons

## Discussion

### Limitations
### Future Directions

## References

[Full bibliography in attached `references.bib`]

---

**Report saved to**: `output/literature-review-report.md`  
**Artifacts saved to**: `output/references.bib`, `output/evidence-ledger.yaml`
