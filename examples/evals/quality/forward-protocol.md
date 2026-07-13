# Independent forward-test protocol

Use this protocol when measuring live research quality for promotion decisions.
Factory ledgers, assertion stuffing, copied sessions, and synthetic dogfood do
not satisfy it.

## Roles and isolation

| Role | Work | Must not receive |
|---|---|---|
| **A** | Normal development or held-out research prompts | Expected answers, bug list, intended fixes, prior scores |
| **B** | Adversarial, ambiguous, and hostile prompts | The same material as A, plus labels revealing which prompts are adversarial |
| **C** | Blind evaluation of raw A/B artifacts | Candidate/baseline identity, expected conclusions, bug list, intended fixes, prior scores |

Run each role in a fresh session. Do not reuse run IDs, raw outputs, ledgers, or
timestamps. Record the actual runtime, model, tool availability, start/end
times, and source of the run. `provenance.live: true` is a declaration that the
run was executed live; it is not cryptographic proof of independence. The final
stable gate therefore also requires an authenticated, exact-commit GitHub
approval from a trusted reviewer who is not the PR author.

## Canonical artifact layout

Every manifest path is relative to the shared artifact root. Every consumed
artifact must be listed once in both `artifact_paths` and `integrity_hashes`.

```text
forward-runs/<date>/
  forward-a/
    prompt.txt
    output.txt
    evaluation.json
    triple-run-1.json
    triple-run-1.log
    triple-run-2.json
    triple-run-2.log
    triple-run-3.json
    triple-run-3.log
    run-manifest.json
  forward-b/
    prompt.txt
    output.txt
    evaluation.json
    run-manifest.json
  forward-c/
    prompt.txt
    output.txt
    evaluation.json
    run-manifest.json
  held-out-<id>/...
  dogfood-<id>/...
  ci-evidence.json
  findings.json
```

The run manifest schema is `1.1` and requires:

- unique `run_id` and `session_id`, plus `role`, `run_kind`, `candidate_sha`,
  and `skill_version`;
- `agent_runtime`, `model`, and `tool_availability`;
- `prompt_path`, `raw_output_path`, required `evaluation_path`, and optional
  `triple_run_results`;
- timezone-aware RFC3339 `started_at` and `completed_at` plus `exit_status`;
- relative `artifact_paths`, matching `integrity_hashes`, and
  `provenance: {"source": "...", "live": true}`.

JSON duplicate keys and non-finite numbers (`NaN`, `Infinity`) are invalid.
Every evaluation must provide all seven rate fields as finite numbers in
`[0, 1]`. A `held_out` evaluation also requires non-negative integer
`fabricated_citations`; a `dogfood` evaluation also requires finite
`quality_gain_vs_baseline`. The promotion gate calculates metrics only from
complete evaluation documents that pass these checks.

## Blind-evaluator contamination checks

Role C inputs and output must not reveal:

- `expected_answer` or gold labels;
- finding IDs or a bug list tied to intended fixes;
- candidate/baseline SHA labels or branch/build labels;
- prior score files or the desired promotion conclusion.

If evaluation passes only after C sees the expected conclusion, discard it as
contaminated. The harness rejects common candidate/baseline label leakage, but
the independent reviewer must still inspect the actual C input manifest and
raw artifacts.

## Promotion sequence

Promotion is eligible only after:

1. `python scripts/quality_eval.py triple` exits green three times.
2. Hashed A/B/C forward artifacts and live held-out/dogfood artifacts validate.
3. Every threshold in `quality-suite.json` is met with no critical failure.
4. CI evidence is bound to the exact candidate SHA and no critical/high/medium
   finding remains unresolved; malformed or unknown ledger values fail closed.
5. `promotion-report` emits `PROMOTION_READY_CANDIDATE` without compatibility
   flags; flags never grant promotion.
6. The stable release workflow verifies the signed candidate/stable tags,
   exact-SHA full CI, and independent exact-commit GitHub review.

Until all six conditions pass, report `RC_QUALITY_INFRA_ONLY`; do not claim
best-in-class, complete, or stable-ready.
