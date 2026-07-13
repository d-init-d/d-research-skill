# Research Plan Protocol — context-safe long-horizon research

## Contents

- [What this is for](#what-this-is-for)
- [When to use it](#when-to-use-it)
- [The five phases](#the-five-phases)
- [Workspace layout](#workspace-layout)
- [Gate definitions](#gate-definitions)
- [Failure modes and how to handle them](#failure-modes-and-how-to-handle-them)
- [Anti-patterns](#anti-patterns)
- [See also](#see-also)

## What this is for

Long, deep research tasks (a literature review, a multi-source dataset
build, a competitive technical survey) routinely outgrow an agent's
context window. Symptoms are: the agent forgets early findings,
contradicts itself in the synthesis, loops on the same source,
re-extracts the same page, or simply stops mid-flight because the
prompt got too large.

This protocol forces the agent to do five things in order so the
research can outlast any single context window:

1. **Plan** before doing.
2. **Execute** to disk, not to memory.
3. **Verify** every gate before moving on.
4. **Dispatch** independent work to sub-agents when safe.
5. **Synthesize** only from structured artefacts, not from raw extractions.

It is the discipline that turns a 200k-token research session into a
sequence of small, resumable, checkpointed sessions.

## When to use it

Use the protocol whenever the task has **any** of these properties:

- More than 5 sub-questions.
- An estimated >50 sources to read.
- An estimated runtime that will not fit in one context window.
- An audit-grade or regulated output requirement.

Do **not** use it for one-shot lookups, single-page extractions, or
quick fact checks. The overhead is not worth it.

## The five phases

## Workspace layout

Every long-horizon research run lives in exactly one workspace directory.
The workspace is the deliverable: the user can zip or tar it and hand it
to another reviewer without relying on chat history.

Use this layout:

```text
research-<slug>-<YYYY-MM-DD>/
├── research-plan.json
├── PLAN.md
├── evidence-ledger.csv
├── evidence-ledger.csv.hmac
├── reproducibility-checklist.md
└── research-output/
    ├── notes/
    │   └── <task-id>-<topic>.md
    ├── sections/
    │   └── <sub-question-id>.md
    ├── report.md
    └── report-citations.md
```

Rules:

- The plan file's parent directory is the workspace root.
- Task `outputs` must stay under `research-output/`.
- Shared audit files (`evidence-ledger.csv`, its `.hmac` signature,
  `PLAN.md`, and `reproducibility-checklist.md`) stay at the workspace
  root.
- Agents must not write outside the workspace. Every declared input/output is
  validated as a portable workspace-relative path on every host. Backslashes
  are treated as separators; absolute/drive/UNC/home paths, empty or `.`/`..`
  segments, control characters, Windows ADS/reserved characters and device
  names, and segments ending in a dot or space are rejected.
- Each output tree has exactly one owning task. Exact aliases and
  ancestor/descendant overlaps are compared case-insensitively, so declarations
  such as `notes/A.md` versus `notes/a.md`, or `notes/` versus
  `notes/source.md`, are invalid even on a case-sensitive host.

Create a workspace with:

```sh
node scripts/run_python.mjs scripts/research_plan.py init \
  --slug oai-review
```

The launcher selects `py -3`, `python3`, or `python` for the host. The
equivalent npm entry point is `npm run plan:init`.

By default this creates a fresh `research-<slug>-<YYYY-MM-DD>/` folder
in the current working directory. If that folder already exists, the
script appends a numeric suffix. This writes `research-plan.json`,
creates the standard output folders, and initialises an empty
`evidence-ledger.csv` header. It also copies the shipped, versioned
`reproducibility-checklist.md` contract into the workspace when one does not
already exist.

If `research.config.json` contains `researchPlan.workspace.baseDir`, the
new run folder is created under that configured output root instead. If
the configured output folder is not accessible and
`fallbackToCwdOnError=true`, the script falls back to the current working
directory and prints a warning. The agent must report the final workspace
path to the user in the final answer.

### 1. Plan

Output the draft plan inside the workspace as `research-plan.json`
(start from `templates/research-plan.json`). The plan must contain:

- **Scope**: the research goal, in one paragraph, framed so a
  stranger could pick up the task and finish it.
- **Sub-questions**: each numbered, each independently answerable.
- **Source map**: the classes of sources you intend to consult
  (official, primary, paper, dataset, code, filing, secondary,
  community). Use `references/source-discovery.md`.
- **Task list**: each row has `id`, `description`, `depends_on`
  (other task ids; empty = root), `parallel_safe` (true/false),
  `owner` (`main` or `sub-N`), `outputs` (paths under
  `research-output/` that the task will produce), and `status`
  (`todo` / `running` / `done` / `blocked`).
- **Execution profile**: the `execution_profile` block records the
  configured main-agent context length, sub-agent slots, per-task
  context budget ratio, and checkpoint policy. Each task has an
  `execution` object stating whether it runs on `main` or a sub-agent
  slot, how many sub-agent threads it consumes, and its context budget.
- **Gates**: the conditions that must be true before declaring the
  plan executable, and before declaring the synthesis allowed. See
  the "Gate definitions" section below.
- **Approval**: the `approval` block starts empty and must be filled by
  `research_plan.py approve` before execution. Approval records a canonical
  `plan_sha256` over the immutable plan contract; any later scope, task graph,
  execution, input/output, phase, or gate change invalidates dispatch until the
  plan is rendered and approved again. Runtime task status, blocker progress,
  free-form notes, and the final stopping-criteria flag are excluded so normal
  execution does not invalidate synthesis gates.
- **Stopping criteria**: the explicit "we are done" signal. Without
  this the agent will not know when to stop.

A good plan is small enough to fit in one context window even when
the underlying research will not.

Verify the plan with `scripts/research_plan.py check --file
research-plan.json` before doing any work. The checker validates
schema, dependency closure (no cycles, no orphan deps), and gate
consistency. Parsing is strict: duplicate object keys, non-finite numbers,
wrong-type enum values, malformed dependency entries, and non-string gate
assertions fail with diagnostics rather than being coerced or dispatched.

After editing the task graph, refresh execution annotations from config:

```sh
node scripts/run_python.mjs scripts/research_plan.py configure-execution --file research-plan.json
```

This reads `research.config.json` if present. If sub-agent slots are
configured, parallel-safe `sub-N` tasks are annotated with the assigned
slot, one consumed sub-agent thread, the slot's context length, and the
derived per-task context budget. If no sub-agent slot is configured, all
tasks are annotated for the main agent and must be split according to
the main agent's own context length.

The rendered `PLAN.md` includes an approval-contract SHA-256, an **Execution
Slots** table, and task columns for phase, parallel safety, inputs, outputs,
blocker state, `Execution`, `Threads`, `Context length`, and `Context budget`.
Users can review this division before approval and change any
task assignment with:

```sh
node scripts/run_python.mjs scripts/research_plan.py set-execution \
  --file research-plan.json \
  --id T2 \
  --agent subagent \
  --slot deep-reader \
  --parallel-threads 2
```

Use `--agent main` to move a task back to the main agent. Any execution
change revokes approval and removes stale `PLAN.md`; render and approve
again.

Render the plan for human review:

```sh
node scripts/run_python.mjs scripts/research_plan.py render --file research-plan.json
node scripts/run_python.mjs scripts/research_plan.py gate --file research-plan.json --gate plan_ready
```

The render command writes `PLAN.md`, a human-readable version of scope,
sub-questions, source classes, tasks, gates, and stopping criteria. The
agent shows `PLAN.md` to the user and asks for corrections before
execution.

After the user approves the plan:

```sh
node scripts/run_python.mjs scripts/research_plan.py approve \
  --file research-plan.json \
  --by "Reviewer Name" \
  --notes "Approved scope and task split."
```

If a host runtime is truly unattended, approval fails by default. The
agent must explicitly bypass the human gate and leave an audit trail:

```sh
node scripts/run_python.mjs scripts/research_plan.py approve \
  --file research-plan.json \
  --allow-unattended
```

This records `approved_by=agent-self-approved`, the immutable-plan digest, and
notes that the run used `--allow-unattended`. If the scope or task graph changes
before execution, run `research_plan.py revoke`, update the plan, render again,
and re-approve. Older approved schema-2.0 workspaces without `plan_sha256` fail
closed; revoke and re-approve them. Unapproved workspaces remain compatible and
receive the digest on their next approval.

Approval alone does not authorize dispatch. Run the executable gate and stop
on any failure:

```sh
node scripts/run_python.mjs scripts/research_plan.py gate \
  --file research-plan.json \
  --gate execute_ready
```

`dispatch_ready` is an alias with the same canonical assertions. Do not start a
research task or dispatch a sub-agent until one of these gates passes.

### 2. Execute

For every task in the plan, the agent does this and **only** this:

1. Re-read the plan row for the task. Do not re-read the whole plan.
2. Re-read the artefacts listed in the task's `inputs` (if any).
3. Do the work.
4. Write each useful finding to the path declared in `outputs` as soon
   as it is found. Never keep the result in chat context for the next
   task.
5. Append every claim worth keeping to the evidence ledger
   (`evidence-ledger.csv`, see `references/evidence-ledger.md`).
6. Mark the task `done` with `scripts/research_plan.py mark --id <id>
   --status done`.

**Context discipline.** Context overflow is a hard failure. The agent
must inspect each task's `execution.context_budget` before starting. If
the expected source text, inputs, or synthesis state may exceed that
budget, split the work into smaller tasks, run `configure-execution`,
render the plan again, and re-approve before execution. The agent must
never paste the contents of a raw extraction back into the chat. Raw
extractions live on disk (typically under `research-output/raw/<source>.json`
or `.md`). Only the structured rows in the evidence ledger and the
per-task summary artefact are allowed to re-enter context, and only when
needed.

A practical rule: if the artefact for one source is larger than
~4 000 tokens, the next task must re-read it via file system, not via
the chat scrollback.

### 3. Parallel dispatch

A task is **parallel-safe** when:

- It has no `depends_on` siblings still running.
- Its output paths do not overlap with any other running task.
- It does not need to read the same file another running task is
  writing.
- It does not require shared state (locks, counters, etc.) that the
  protocol does not provide.

Typical parallel-safe shapes:

- Per-source extraction (each source maps to its own output file).
- Per-database literature search (each database maps to its own
  search log).
- Per-language translation passes.
- Per-axis source scoring.

Typical **not** parallel-safe:

- Final synthesis.
- The contradiction pass (needs the full ledger present).
- Anything that writes to the same evidence ledger row.

To list ready-to-dispatch tasks, run `scripts/research_plan.py
parallelizable --file research-plan.json`. The script prints task ids
that have all dependencies satisfied, no output-tree conflicts with running or
simultaneously selected tasks, and an available sub-agent slot thread when
`execution.agent=subagent`. Output conflict checks use the same portable,
case-insensitive exact/ancestor/descendant rules as plan validation.

Sub-agent usage is controlled by `research.config.json`:

```json
{
  "researchPlan": {
    "subagents": {
      "slots": [
        {
          "id": "deep-reader",
          "agent": "explore",
          "contextLength": 32000,
          "maxParallel": 3
        }
      ]
    }
  }
}
```

The default config contains one `default` slot with `agent`,
`contextLength`, and `maxParallel` set to `null`, meaning no configured
sub-agent. Users can add more objects to `researchPlan.subagents.slots[]`.
A slot only becomes usable when all three fields are set: `agent`,
`contextLength`, and `maxParallel`. When slots are configured, the
orchestrator dispatches no more than each slot's `maxParallel` tasks
concurrently and ensures every task fits within that slot's context
budget.

Dispatch mechanism depends on the host runtime:

- **Claude / agent-native parallel tool**: spawn one sub-agent per
  parallel-safe task. Pass the task row, the plan path, the
  evidence-ledger path, and the task's allowed output paths.
- **Devin or a similar agent platform**: open one child session per
  parallel-safe task, with the same payload.
- **Plain CLI**: run the tasks under GNU `parallel` or `xargs -P` if
  the work is fully scripted.

In every case, sub-agents must:

1. Write only to the output paths declared in their task row.
2. Append (not overwrite) to the evidence ledger.
3. Return a short structured summary (path of produced artefacts,
   row count, blocker count). Never paste raw extractions.

After all dispatched tasks return, the orchestrator marks them `done`
and re-runs `scripts/research_plan.py check` to confirm the plan is
still consistent.

At the end of the research phase, validate and sign the ledger, complete the
reproducibility checklist, and run `gate --gate synthesize_ready`. Every
long-horizon workspace therefore needs `D_RESEARCH_LEDGER_KEY` before synthesis;
missing key material is a blocker, never a reason to skip verification.
The checklist gate requires every canonical `DRC-###` ID from contract `v1`
exactly once. Missing, duplicate, unknown, unchecked, or un-IDed boxes fail
closed; an item may be marked `N/A` only with a non-empty reason.

### 4. Verify (gates)

Before transitioning between phases, the orchestrator runs
`scripts/research_plan.py gate --file research-plan.json --gate <name>`.
The gate checks the assertions declared in the plan and exits non-zero
if any fail.

Four standard gates are provided. A plan can add more.

- **`gate.plan_ready`** — schema is valid; workspace layout exists;
  execution annotations are configured; `PLAN.md` exists; dependency
  graph is acyclic; all dependencies point at known task ids; no task is
  `done` yet. Passes before approval.
- **`gate.execute_ready`** — `plan_ready` assertions plus
  `plan_approved`. Passes once at the end of the approval phase.
- **`gate.synthesize_ready`** — every **research-phase** task is `done` or
  `blocked`; every blocked research task has a non-empty `blocker_reason`; every
  research output exists; the evidence ledger validates and its HMAC verifies;
  the reproducibility checklist is complete. Synthesis tasks are intentionally
  not required yet. Passes once at the end of the research phase.
- **`gate.release_ready`** — `synthesize_ready` plus: every synthesis task is
  terminal; every synthesis output exists; the exact final report validates;
  rendered citations exist; authored narrative covers 100 percent of claim
  rows; and the plan's stopping criteria are satisfied. Passes once at the end
  of synthesis.

If a gate fails, the agent fixes the failure and re-runs the gate.
The agent never advances past a failing gate.

### 5. Synthesize

The synthesis phase is the **only** phase that produces the final narrative
artefact. Enter it only after `synthesize_ready` passes. The agent does this:

1. Read the plan (just the metadata + sub-questions + gates).
2. Read the evidence ledger (full).
3. Read each per-task summary artefact (small structured
   markdown/JSON, not raw extractions).
4. Mark the applicable synthesis task `running`.
5. Initialize the report skeleton: `scripts/report_render.py init --workspace <dir>`.
6. Compose the report following
   `references/final-report-template.md` or edit `report.draft.md`.
7. Render the final report: `scripts/report_render.py render --workspace <dir>`.
8. Render citations with `scripts/citation_render.py`.
9. Lint the exact report with `scripts/report_render.py lint --workspace <dir>
   --report <declared-report-path> --strict`.
10. Mark every synthesis task terminal after its declared outputs exist.
11. Re-verify the ledger HMAC and run `gate.release_ready`.

If at any point the agent feels the urge to "go look at one more
source", it instead adds a follow-up task to the plan, marks the
current cycle's plan as complete, and starts a new cycle. Synthesis
never silently expands scope.

## Gate definitions

Gates are declared inline in `research-plan.json` under `gates`. Each
gate has a name and an ordered list of assertions. The default
template defines `plan_ready`, `execute_ready`, `synthesize_ready`, and
`release_ready` (above). Custom gates can be added for domain-specific
requirements — e.g. a PRISMA review might add:

- `gate.prisma_flow_filled` — `templates/prisma-flow.json` is
  populated and the identification/screening/included counts add up.
- `gate.dual_screened` — every row in `screening-log.csv` has a
  second-reviewer column populated.

## Failure modes and how to handle them

| Failure | Detection | Response |
|---|---|---|
| A task takes longer than its budget | `research_plan.py status` shows it `running` past budget | Split the task into smaller sub-tasks, revoke approval if scope changes, render again, re-approve, then re-run `gate.execute_ready` |
| A sub-agent returns inconsistent output | Output schema mismatch on read-back | Mark the task `blocked` with `blocker_reason`, re-dispatch with a tighter prompt |
| Two tasks declare the same or nested output tree | `check` rejects case-insensitive exact and ancestor/descendant aliases; `parallelizable` also fails closed | Assign each output tree to one task, revoke approval, render, re-approve, and re-run the dispatch gate |
| The agent runs out of context anyway | The orchestrator detects a long-input retry | Checkpoint: persist `research_plan.py status` output, then restart in a fresh session with the same plan file |
| The evidence ledger fails validation mid-run | `gate.synthesize_ready` blocks | Fix the offending row(s), re-validate, re-sign |
| A gate fails | Non-zero exit from `scripts/research_plan.py gate` | Fix the failing assertion(s), do not advance |

## Anti-patterns

- **Inline raw extraction in chat.** Always to disk first.
- **Re-reading the full plan on every task.** Re-read only the task row.
- **Hand-editing `research-plan.json` while a task is running.** Use
  the script's `mark` / `add-task` / `block` subcommands so the
  schema stays valid.
- **Skipping `PLAN.md` review or approval.** Long runs should not spend
  hours executing a scope that no human has seen. Use `--allow-unattended`
  only when a human is truly unavailable.
- **Skipping gates "because it's just a small task".** Gates are
  cheap to run. Skipping them is how regressions happen.
- **Letting sub-agents talk to each other.** They must communicate
  through artefacts on disk; never peer-to-peer.

## See also

- `templates/research-plan.json` — the starter plan with the schema
  the script enforces.
- `scripts/research_plan.py` — `init`, `render`, `approve`, `revoke`,
  `add-task`, `mark`, `block`, `check`, `parallelizable`, `gate`,
  `status`, `self-test`.
- `references/evidence-ledger.md` — the ledger schema, also the
  signing flow.
- `references/reproducibility-checklist.md` — the post-execute
  audit.
- `references/final-report-template.md` — the synthesis template.
- `examples/long-horizon-research-plan.md` — an end-to-end worked
  example.
