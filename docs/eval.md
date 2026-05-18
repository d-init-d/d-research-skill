# Eval Harness

This document explains the offline eval harness that ships with the skill and
how to use it to detect regressions and measure upgrade gains.

The harness is scaffolding, not an autonomous agent runner. It loads
ground-truth bench files, renders prompts that you feed to your chosen agent,
then scores the agent's evidence-ledger CSVs. The agent itself still runs
outside the harness.

## What Ships

- `examples/evals/dogfood-bench.json` - Tier 1 regression bench. It has 12
  ground-truth tasks across `atomic-fact`, `api-workflow`, `contradiction`, and
  `person-aggregation`.
- `examples/evals/frontier-bench.json` - Tier 2 frontier bench 2.0. It has 20
  harder tasks across ten classes: hard atomic facts, subtle contradictions,
  hidden refusal triggers, long-horizon planning, API/tool drift, systematic
  review discipline, large-scale collection, monitoring/change detection,
  multilingual research, and anti-bot fallback handling.
- `examples/evals/fixtures/*-empty-scores.json` - deterministic empty-ledger
  score fixtures used by self-test to detect unreviewed scoring drift.
- `scripts/run_dogfood.py` - stdlib-only Python harness.
- `docs/eval-upgrade-prompt.md` - a copy-paste prompt for asking an external
  agent to run the full baseline-vs-candidate workflow.

## Two Tiers

Tier 1 is the regression guard. It answers: did the candidate get weaker on
things the previous version already handled?

Tier 2 is the frontier probe. It answers: did the candidate newly pass hard
tasks that the previous version failed or only partially passed?

Keep these separate. Tier 1 can use a threshold such as `0.7`; Tier 2 is
binary and all-or-nothing: a non-refusal task passes only when `recall == 1.0`
and `accuracy == 1.0`.

## Bench Schema

Both bench files use the same base schema:

| Key | Type | Notes |
|---|---|---|
| `schema_version` | string | Bench schema version. |
| `bench_version` | string | Optional human-facing bench-set version. Frontier bench 2.0 uses this to mark the expanded task set without breaking score-file schema compatibility. |
| `tier` | string | Optional. Absent means `regression`; Tier 2 uses `frontier`. |
| `name`, `description` | string | Human-readable metadata. |
| `classes` | list[string] | Every task's `class` must appear here. |
| `scoring` | object | Plain-English scoring notes. |
| `tasks` | list[object] | The task set. |

Per-task required keys:

- `task_id`
- `class`
- `difficulty`
- `expected_branch`
- `question`
- `expected_answer`
- `ground_truth_sources`
- `notes`

Optional keys include `expected_action` and `negative_signals`.

`expected_answer` must include `value` and `format`. It may also include:

| Key | Type | Notes |
|---|---|---|
| `match_mode` | string | Optional. One of `substring` (default), `exact`, `word`, or `regex`. |
| `case_sensitive` | boolean | Optional. Defaults to `true`. |
| `must_include` | list[string] | Optional. Every listed string must appear in the scored answer row context. |
| `must_not_include` | list[string] | Optional. Any listed string in the scored answer row context rejects that row as an accuracy hit. |
| `supporting_fields` | object | Optional structured rationale for validators and maintainers. |

Refusal probes are strict: they must set `expected_action: "refuse"`,
`ground_truth_sources: []`, `expected_answer.value: "REFUSAL"`, and
`expected_answer.format: "refusal"`. They must not include private answers or
source URLs. A refusal task passes only when the produced ledger has zero rows.

## Basic Commands

```bash
# Offline validation. This is what CI runs through npm run self-test.
python3 scripts/run_dogfood.py self-test

# Validate either bench explicitly.
python3 scripts/run_dogfood.py validate --file examples/evals/dogfood-bench.json
python3 scripts/run_dogfood.py validate --file examples/evals/frontier-bench.json

# Inspect tasks.
python3 scripts/run_dogfood.py list --file examples/evals/frontier-bench.json
python3 scripts/run_dogfood.py classes --file examples/evals/frontier-bench.json
python3 scripts/run_dogfood.py baseline --file examples/evals/frontier-bench.json

# Render one task as an agent prompt.
python3 scripts/run_dogfood.py render FB-001 --file examples/evals/frontier-bench.json

# Score one produced ledger.
python3 scripts/run_dogfood.py score DF-001 runs/candidate/ledgers/DF-001.csv
python3 scripts/run_dogfood.py score DF-001 runs/candidate/ledgers/DF-001.csv --threshold 0.7
```

`score` reports:

| Metric | Definition |
|---|---|
| `recall` | Fraction of `ground_truth_sources` appearing in any ledger `source`, `url`, or `source_url` column. |
| `accuracy` | `1.0` if `expected_answer.value` matches a ledger `evidence`, `quote`, `quote_or_anchor`, `value`, or `claim` column under the task's `match_mode` and row constraints; otherwise `0.0`. |
| `refusal` | For refusal tasks only: `PASS` when the ledger is empty, otherwise `FAIL`. |

## Score Artifacts

Use `score-all` after your agent has produced one ledger CSV per task.

```bash
python3 scripts/run_dogfood.py score-all \
  --bench examples/evals/dogfood-bench.json \
  --ledgers-dir runs/candidate/tier1-ledgers \
  --out runs/candidate/tier1-scores.json \
  --threshold 0.7

python3 scripts/run_dogfood.py score-all \
  --bench examples/evals/frontier-bench.json \
  --ledgers-dir runs/candidate/tier2-ledgers \
  --out runs/candidate/tier2-scores.json
```

`score-all` reads `<ledgers-dir>/<task_id>.csv`. Missing ledger files are
treated as empty ledgers so an incomplete run is still represented honestly in
the score artifact.

The score artifact schema is:

```json
{
  "schema_version": "1.0",
  "bench_name": "d-research dogfood baseline",
  "tier": "regression",
  "created_at": "2026-05-18T00:00:00Z",
  "tasks": [
    {
      "task_id": "DF-001",
      "class": "atomic-fact",
      "difficulty": "medium",
      "recall": 1.0,
      "accuracy": 1.0,
      "refusal": null,
      "ledger_rows": 2,
      "passed": true,
      "expected_action": null
    }
  ]
}
```

For deterministic tests, pass `--frozen-timestamp`. The repository ships
empty-ledger fixtures at `examples/evals/fixtures/dogfood-empty-scores.json`
and `examples/evals/fixtures/frontier-empty-scores.json`; `self-test` compares
freshly generated output against those files byte-for-byte.

```bash
python3 scripts/run_dogfood.py score-all \
  --bench examples/evals/frontier-bench.json \
  --ledgers-dir runs/empty \
  --out runs/frontier-empty.json \
  --frozen-timestamp 2026-05-18T00:00:00Z
```

## Compare Runs

Compare baseline and candidate score artifacts:

```bash
python3 scripts/run_dogfood.py compare \
  runs/baseline/tier1-scores.json \
  runs/candidate/tier1-scores.json

python3 scripts/run_dogfood.py compare \
  runs/baseline/tier2-scores.json \
  runs/candidate/tier2-scores.json
```

`compare` validates both score files before comparing. It fails fast on schema
version mismatch, malformed artifacts, tier mismatch, duplicate task IDs, or
different task ID sets. It also rejects task metadata mismatches for shared
task IDs (`class`, `difficulty`, or `expected_action`) so artifacts from
different bench definitions are not compared accidentally.

Text output starts with:

```text
VERDICT: STRONGER
```

Use JSON output when another tool consumes the result:

```bash
python3 scripts/run_dogfood.py compare \
  runs/baseline/tier2-scores.json \
  runs/candidate/tier2-scores.json \
  --output-format json
```

Exit codes:

- `0`: verdict is `STRONGER` or `SAME`
- `1`: verdict is `WEAKER` or validation failed

## Manual Upgrade Workflow

The harness does not run Claude, Devin, Cursor, or any other agent runtime.
The user or a wrapper agent must:

1. Render tasks.
2. Run the skill externally.
3. Save one ledger per task.
4. Run `score-all`.
5. Run `compare`.

Use `docs/eval-upgrade-prompt.md` when you want a single copy-paste prompt for
an agent runner.

Do not re-baseline to hide regressions. Replacing baseline scores with
candidate scores after a `WEAKER` result destroys the purpose of the bench. If a
regression is real and the upgrade is still desirable, record that decision
explicitly instead of erasing the comparison.

## CI Policy

CI runs only offline validation through `python3 scripts/run_dogfood.py
self-test`, currently via `npm run self-test`. It does not run a live agent,
does not score runtime-produced ledgers, and does not call `compare` against
live artifacts. The workflow is path-triggered for harness code, eval bench
JSON, eval docs, package metadata, and the workflow file itself.

## Adding Tasks

For Tier 1, keep task IDs and ground-truth sources stable. Tier 1 is a
regression guard, so avoid changing existing tasks unless the original ground
truth is genuinely wrong.

For Tier 2, add tasks only when the current skill version fails or partially
passes. Include `current_version_status:` in `notes` so future maintainers know
why the task belongs in the frontier bench.

Frontier bench 2.0 enforces at least two tasks per frontier class. New class
validators should make the branch contract explicit: required references,
minimum source count when needed, and any class-specific supporting field such
as `drift_note` for API drift probes.

If a task tests privacy refusal, use the refusal sentinel and do not include the
private answer, private source URLs, or identifying details in the bench file.

## See Also

- `SKILL.md` - entry-point decision tree the bench tests.
- `AGENTS.md` - short root-level workflow summary.
- `references/fact-verification.md` - atomic fact branch.
- `references/person-aggregation.md` - public-role aggregation and refusal branch.
- `references/research-plan-protocol.md` - long-horizon plan branch.
- `references/evidence-ledger.md` - ledger schema the scorer reads.
- `references/systematic-review-protocol.md` - PRISMA review branch.
- `references/large-scale-collection.md` - large collection branch.
- `references/monitoring-change-detection.md` - monitoring branch.
- `references/multilingual-research.md` - multilingual branch.
- `references/anti-bot-fallback.md` - blocked public source fallback branch.
- `templates/evidence-ledger.csv` - CSV template for agent-produced evidence.
