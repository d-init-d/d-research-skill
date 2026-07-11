# Independent forward-test protocol

Use this protocol when measuring live research quality for promotion decisions.
It is **not** satisfied by factory ledgers, assertion stuffing, or synthetic
dogfood packages.

## Agents

| Agent | Role | Must not receive |
|---|---|---|
| **A** | Normal research tasks from development or held-out prompts | Expected answers, bug list, intended fixes, prior scores |
| **B** | Adversarial / ambiguous / hostile tasks | Same as A; plus must not be told which cases are adversarial |
| **C** | Blind evaluator of raw artifacts from A/B | Candidate vs baseline identity, expected conclusions, bug list, intended fixes, prior scores |

## Artifact layout

```text
forward-runs/<date>/
  agent-a/
    case-<id>/
      run-result.json
      evidence-ledger.csv
      report.md            # optional
      notes.md
  agent-b/
    case-<id>/...
  agent-c/
    evaluation.json       # blind scores / free-form critique
    inputs-manifest.json  # must list files given to C (no contamination fields)
  meta.json               # skill_commit, runtime hash, suite_version
```

## Contamination checks (Agent C inputs)

`inputs-manifest.json` must **not** include:

- `expected_answer` / gold labels
- `bug_list` / finding IDs tied to intended fixes
- `candidate_sha` vs `baseline_sha` labels that reveal which side is which
- prior score files

If evaluation only passes when C is told the expected conclusion, treat the
eval as **contaminated** and discard it for promotion.

## Promotion

Only after:

1. Offline `quality_eval.py triple` is green
2. Forward artifacts for A/B/C exist with raw ledgers
3. Held-out live scores meet suite `promotion_thresholds`
4. No critical failure in any held-out run
5. Independent stable review (separate from this protocol)

…may a human claim `BEST-IN-CLASS` / `PROMOTION-READY`. The harness
`promotion-report` defaults to `RC_QUALITY_INFRA_ONLY` and
`best_in_class: false` until those flags are explicitly supplied with evidence.
