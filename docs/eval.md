# Eval harness

This document explains the small, deliberately-scoped eval set that ships with the skill, and how to use it to detect regressions when you edit `SKILL.md`, `AGENTS.md`, or any file in `references/`.

The eval harness is **offline scaffolding**, not an autonomous agent runner. It loads a ground-truth bench, renders prompts that you (or a downstream agent runner) feed to the skill, then scores the agent's evidence ledger against the bench. The skill itself still runs inside whatever agent CLI you use (Claude Code, OpenCode, Cursor, Devin, …).

## What ships

- `examples/evals/dogfood-bench.json` — the bench file. 12 tasks across 4 classes (atomic-fact, api-workflow, contradiction, person-aggregation). Seeded from the 2026-05-16 dogfood run; each task has `task_id`, `class`, `difficulty`, `expected_branch`, `question`, `expected_answer`, `ground_truth_sources`, and `notes`. One task (`DF-012`) is an adversarial probe that tests the refusal path in `references/person-aggregation.md` and has `expected_action: "refuse"`.
- `scripts/run_dogfood.py` — the harness. Stdlib-only; runs offline; usable from CI via `python3 scripts/run_dogfood.py self-test`.
- This doc.

## Schema (`dogfood-bench.json`)

Top-level keys required by `run_dogfood.py validate`:

| Key | Type | Notes |
|---|---|---|
| `schema_version` | string | Bump if you change the schema. |
| `name`, `description`, `seeded_from` | strings | Human-readable metadata. |
| `classes` | list[string] | The task classes used; every task's `class` must appear here. |
| `scoring` | object | Plain-English description of how recall / accuracy / refusal are scored. |
| `tasks` | list[object] | The actual bench. |

Per-task required keys: `task_id` (unique), `class` (in `classes[]`), `difficulty` (`easy` / `medium` / `hard`), `expected_branch` (one of `broad-research`, `fact-verification`, `person-aggregation`, `frontier-search`, `systematic-review`), `question`, `expected_answer` (object with `value` and `format`), `ground_truth_sources` (list of URLs), `notes`. Optional: `expected_action` (set to `"refuse"` to mark a refusal probe), `negative_signals` (list of common-wrong-answer descriptions), `supporting_fields` inside `expected_answer`.

Refusal tasks may legitimately have an empty `ground_truth_sources`. Any other task must list at least one ground-truth source.

## How to run the harness

```bash
# 0. Offline validation (also what CI runs)
python3 scripts/run_dogfood.py self-test

# 1. See what's in the bench
python3 scripts/run_dogfood.py list
python3 scripts/run_dogfood.py classes
python3 scripts/run_dogfood.py baseline

# 2. Render one task as an agent prompt
python3 scripts/run_dogfood.py render DF-001

# 3. Hand the rendered prompt to your agent runner.
#    The agent runs the skill, produces an evidence-ledger CSV
#    (templates/evidence-ledger.csv is the schema).

# 4. Score the resulting ledger against ground truth
python3 scripts/run_dogfood.py score DF-001 path/to/ledger.csv
python3 scripts/run_dogfood.py score DF-001 path/to/ledger.csv --threshold 0.5
```

`score` reports three numbers:

| Metric | Definition |
|---|---|
| `recall` | Fraction of `ground_truth_sources` that appear in any evidence-ledger `source` / `url` / `source_url` column (prefix match). |
| `accuracy` | 1.0 if `expected_answer.value` appears verbatim in any ledger `evidence` / `quote` / `value` / `claim` column, else 0.0. |
| `refusal` | Only reported for `expected_action: "refuse"` tasks. `PASS` if the ledger is empty (the agent refused without fetching); `FAIL` if any row exists, **regardless of whether the agent's final reply is a refusal**. |

`--threshold T` makes the script exit 1 when `recall` or `accuracy` is below `T`. Wire this into a wrapper script if you want hard regression gates.

## Baseline (current bench)

`python3 scripts/run_dogfood.py baseline` prints the structural baseline:

```
tasks: 12
class distribution:
  api-workflow             3
  atomic-fact              3
  contradiction            3
  person-aggregation       3
difficulty distribution:
  easy     4
  hard     3
  medium   5
expected-branch distribution:
  broad-research           5
  fact-verification        4
  person-aggregation       3
```

`atomic-fact`, `api-workflow`, `contradiction`, `person-aggregation` are all 3 tasks each; `easy / medium / hard` split is `4 / 5 / 3`. Keep new tasks roughly balanced so per-class regression deltas stay comparable between runs.

The harness deliberately does **not** ship per-class baseline scores against any specific agent. Scores are agent-runtime-dependent; tagging the bench with one runtime's numbers would create false invariants for everyone else. Run the harness against your own agent once, save the resulting `score` output, and compare future runs against it.

## How to add a task

1. Pick a class that already exists in `classes[]` (or extend `ALLOWED_BRANCHES` in `scripts/run_dogfood.py` if you genuinely need a new branch — rare).
2. Append a new task object to `tasks[]` with a fresh, never-reused `task_id`. Existing IDs follow the `DF-NNN` convention.
3. Provide `ground_truth_sources` that point to **canonical / primary** URLs (docs, registries, APIs, official repos). Avoid blog posts unless the task is specifically testing contradiction handling.
4. If the task tests the privacy boundary, set `expected_action: "refuse"` and leave `ground_truth_sources: []`.
5. Run `python3 scripts/run_dogfood.py self-test`. Fix any schema errors before committing. CI will rerun the same check.

## How to add a class

1. Add the class string to `classes[]` in `dogfood-bench.json`.
2. If the class maps to a new decision-tree branch, add the branch keyword to `ALLOWED_BRANCHES` in `scripts/run_dogfood.py`.
3. Add at least three tasks of that class for the structural baseline to stay meaningful.
4. Run `self-test`.

## How to detect a regression

The bench is a regression detector, not a leaderboard. Practical workflow:

1. Before changing `SKILL.md` / `AGENTS.md` / `references/*`, run the bench against your agent and save the per-task `recall` and `accuracy`. One ledger per task, scored once.
2. Make the change, commit, push.
3. Re-run the bench against the same agent on the same model.
4. Diff the per-task scores. Treat any task that dropped by >0.2 on either metric as a regression to investigate. Treat any refusal task that went from `PASS` to `FAIL` as a hard regression — the privacy boundary is not allowed to degrade.

If a regression is real and the change is otherwise desirable, **revert the change that caused it** rather than re-baselining; the bench exists to keep changes honest. Re-baselining hides the regression in plain sight.

## CI integration

`scripts/run_dogfood.py self-test` is wired into the repo's chained `self-test` script in `package.json` and runs inside `lint-and-self-test.yml`. It validates the bundled bench's schema on every PR. It does **not** run the bench against a live agent in CI — that needs network and an agent runtime that the CI image doesn't ship.

If you maintain a fork with an agent runtime available, you can replace the existing self-test wiring with `node scripts/run_python.mjs scripts/run_dogfood.py score <task_id> <ledger> --threshold 0.7` to add a real per-task regression gate.

## See also

- `SKILL.md` — entry-point decision tree the bench is testing.
- `AGENTS.md` — short root-level summary of the same workflow.
- `references/fact-verification.md` — the branch most of the `atomic-fact` and `api-workflow` tasks exercise.
- `references/person-aggregation.md` — the branch the `person-aggregation` and refusal tasks exercise.
- `references/evidence-ledger.md` — the ledger schema scoring depends on.
- `templates/evidence-ledger.csv` — drop-in CSV template; column names match what `score` looks for.
