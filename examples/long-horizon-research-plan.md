# Long-horizon research with a context-safe plan

This example walks through using `references/research-plan-protocol.md`
end-to-end. The task is realistic but does not run any network code, so
you can replay it locally to learn the protocol.

**Scenario.** A scientist wants a narrative review of how three
headless-browser frameworks (Playwright, Selenium, Puppeteer) handle
crawling academic OAI-PMH endpoints. The review will produce a
PRISMA-style report with citations and a signed evidence ledger. The
expected runtime is ~12 hours and ~80 sources, comfortably bigger than
one model context window.

The protocol's job is to make this task survivable across context
resets and parallelisable where safe.

## Step 1 — Initialise the plan

```sh
python3 scripts/research_plan.py init --slug oai-review
cd ./research-oai-review-2026-05-16
python3 ../scripts/research_plan.py check --file research-plan.json
python3 ../scripts/research_plan.py configure-execution --file research-plan.json
```

The `init` command prints the actual `workspace:` path. Use that path in
the `cd` command; if the same slug/date already exists, the folder may
have a suffix such as `-02`.

On Windows, use `python` instead of `python3` if `python3` is not on
PATH, or use the matching `npm run plan:*` commands from the repo root.

The template ships with seven illustrative tasks (T1–T7) and four gates
(`plan_ready`, `execute_ready`, `synthesize_ready`, `release_ready`). The
orchestrator edits the plan to match the real research goal but keeps
the schema intact.

The very first thing the orchestrator does is read the **whole** plan
into context and then immediately swap to working off of `status` /
`parallelizable` / `mark` outputs — none of the raw plan text re-enters
context after this point.

## Step 2 — Render, review, and approve the plan

```sh
python3 ../scripts/research_plan.py render --file research-plan.json
python3 ../scripts/research_plan.py gate --file research-plan.json --gate plan_ready
```

Expected:

```
  [OK  ] schema_valid: OK
  [OK  ] workspace_layout: OK
  [OK  ] execution_configured: OK
  [OK  ] plan_rendered: rendered plan is current at .../PLAN.md
  [OK  ] no_dependency_cycles: OK
  [OK  ] no_orphan_dependencies: OK
  [OK  ] no_task_is_done: OK
GATE PASS: plan_ready
```

The orchestrator shows `PLAN.md` to the user. The user can ask for scope
changes, sub-question edits, source-class changes, task additions, or
owner/execution changes. If the user wants to move a task to a different
sub-agent slot or change its thread count, use `set-execution`, then
re-run `render` and `plan_ready`.

Once the user approves:

```sh
python3 ../scripts/research_plan.py approve \
  --file research-plan.json \
  --by "reviewer@example.org" \
  --notes "Scope, tasks, and stopping criteria approved."

python3 ../scripts/research_plan.py gate --file research-plan.json --gate execute_ready
```

Expected:

```
  [OK  ] schema_valid: OK
  [OK  ] workspace_layout: OK
  [OK  ] execution_configured: OK
  [OK  ] plan_rendered: rendered plan is current at .../PLAN.md
  [OK  ] no_dependency_cycles: OK
  [OK  ] no_orphan_dependencies: OK
  [OK  ] no_task_is_done: OK
  [OK  ] plan_approved: approved by reviewer@example.org at ...
GATE PASS: execute_ready
```

Unattended runs fail by default. If no human can review the plan, the
agent must explicitly record the bypass:

```sh
python3 ../scripts/research_plan.py approve \
  --file research-plan.json \
  --allow-unattended
```

## Step 3 — Dispatch parallel tasks

```sh
python3 ../scripts/research_plan.py parallelizable --file research-plan.json
```

This prints the task ids whose dependencies are all `done` and whose
output paths do not collide with anything currently running. For the
shipped template this returns `T1 T2 T3 T4`.

The orchestrator now does one of three things, depending on the
runtime:

- **Agent runtime with a parallel-tool primitive** — fan out one
  sub-agent per id, each constrained to write only to that task's
  declared `outputs`.
- **Devin (or similar)** — start one child session per id with the
  same constraint.
- **CLI** — `xargs -P 4 -I{} bash -c 'run-task.sh {}' <<<'T1 T2 T3 T4'`.

Before dispatching, mark each task as `running` so the
`parallelizable` query does not re-issue them:

```sh
for t in T1 T2 T3 T4; do
  python3 ../scripts/research_plan.py mark --file research-plan.json --id "$t" --status running
done
```

Each sub-agent must:

1. Re-read only its own task row from `research-plan.json` (it does
   not need anything else from the plan).
2. Read the inputs listed in its task row.
3. Do the work (read sources, extract findings).
4. Append rows to `evidence-ledger.csv` (open in append mode; the
   ledger is the shared bus between sub-agents).
5. Write its summary to its declared `outputs` path.
6. Return a short structured result: `{"task_id": "...", "outputs":
   [...], "evidence_rows_added": N, "blocker_count": M}`. **No raw
   extractions in the return.**

When a sub-agent finishes, the orchestrator marks the task `done`:

```sh
python3 ../scripts/research_plan.py mark --file research-plan.json --id T2 --status done
```

If a sub-agent gets stuck (paywalled source, captcha wall, repeated
429s), the orchestrator blocks the task with a reason instead:

```sh
python3 ../scripts/research_plan.py block \
    --file research-plan.json \
    --id T3 \
    --reason "Selenium docs site returns 429 after 5 requests; manual fetch needed"
```

The `blocker_reason` will surface in the next gate run and in any
final report. Blocking is not failure; it is honest reporting.

## Step 4 — Synthesise SQ1

Once T1–T4 are all terminal (`done` or `blocked`), T5 becomes
available:

```sh
python3 ../scripts/research_plan.py parallelizable --file research-plan.json
# (none ready — T5 has parallel_safe=false)

python3 ../scripts/research_plan.py mark --file research-plan.json --id T5 --status running
# ...orchestrator reads T1..T4 outputs from disk, writes
# research-output/sections/sq1.md...
python3 ../scripts/research_plan.py mark --file research-plan.json --id T5 --status done
```

Critically: at this point the orchestrator does **not** re-read the
raw source extractions. It re-reads only the per-task summary files
(`research-output/notes/*.md`) and the evidence ledger. This is what
keeps the synthesis pass inside one context window.

## Step 5 — Contradiction pass and reproducibility audit

T6 runs the contradiction pass over the now-complete evidence ledger.
Then the orchestrator walks through `references/reproducibility-checklist.md`
and writes the audit to `reproducibility-checklist.md` (or under
`research-output/`).

## Step 6 — Synthesize-ready gate

```sh
python3 ../scripts/evidence_ledger.py validate --file evidence-ledger.csv
python3 ../scripts/evidence_ledger.py sign \
    --file evidence-ledger.csv \
    --key-env D_RESEARCH_LEDGER_KEY

python3 ../scripts/research_plan.py gate \
    --file research-plan.json \
    --gate synthesize_ready
```

If any assertion fails (missing output, unsigned ledger, missing
checklist), the orchestrator fixes the offending artefact and re-runs
the gate. The plan does not advance past a failing gate.

## Step 7 — Final report and release

T7 composes the report from the SQ section files, renders citations
with `scripts/citation_render.py` (e.g. APA via `--style apa`), and
writes both to `research-output/`. Finally:

```sh
# Mark the stopping criteria satisfied (manual review step):
# (edit research-plan.json by hand and set
#  "stopping_criteria_satisfied": true)
python3 ../scripts/research_plan.py gate \
    --file research-plan.json \
    --gate release_ready
```

When `release_ready` is `GATE PASS`, the review is published.

## Outputs at the end

```
research-oai-review-2026-05-16/
├── research-plan.json
├── PLAN.md
├── evidence-ledger.csv
├── evidence-ledger.csv.hmac
├── reproducibility-checklist.md
└── research-output/
    ├── notes/
    │   ├── oai-pmh-spec-summary.md
    │   ├── playwright-xml-handling.md
    │   ├── selenium-xml-handling.md
    │   ├── puppeteer-xml-handling.md
    │   └── contradiction-pass.md
    ├── sections/
    │   └── sq1.md
    ├── report.md
    └── report-citations.md
```

The whole tree, plus the signed ledger, is the reproducible artefact
package. Anyone (including the original agent in a new session) can
walk into the directory, run `research_plan.py status` and
`evidence_ledger.py verify`, and pick up the work or replay the
synthesis exactly.

## What the protocol prevented

- **Context overflow.** No task pulled raw source dumps back into
  chat; everything stayed on disk and was re-read on demand.
- **Lost work.** The plan + ledger together let a fresh agent
  resume after a session restart.
- **Silent scope creep.** "One more source" became a new task with a
  dependency edge, not an inline tangent.
- **Untracked blockers.** Anything the agent could not extract was
  recorded as a blocked task with a reason, instead of being
  invisibly dropped.
- **Unsigned outputs.** `synthesize_ready` would not pass without a
  validated, signed ledger.

## See also

- `references/research-plan-protocol.md` — the protocol this example follows.
- `templates/research-plan.json` — the schema the script enforces.
- `scripts/research_plan.py` — the manager script.
- `references/reproducibility-checklist.md` — the post-execute audit.
- `examples/systematic-review-prisma.md` — a PRISMA-grade walkthrough that
  pairs naturally with this protocol.
