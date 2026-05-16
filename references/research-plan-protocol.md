# Research Plan Protocol — context-safe long-horizon research

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

- More than 5 sub-questions or 5 distinct extraction targets.
- An estimated >50 sources to read.
- An estimated runtime that will not fit in one model call.
- A reproducibility requirement (PRISMA review, audit, regulated report).
- Multiple agents or humans collaborating.

Do **not** use it for one-shot lookups, single-page extractions, or
quick fact checks. The overhead is not worth it.

## The five phases

### 1. Plan

Output a single artefact: `research-plan.json` (start from
`templates/research-plan.json`). The plan must contain:

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
- **Gates**: the conditions that must be true before declaring the
  plan executable, and before declaring the synthesis allowed. See
  the "Gate definitions" section below.
- **Stopping criteria**: the explicit "we are done" signal. Without
  this the agent will not know when to stop.

A good plan is small enough to fit in one context window even when
the underlying research will not.

Verify the plan with `scripts/research_plan.py check --file
research-plan.json` before doing any work. The checker validates
schema, dependency closure (no cycles, no orphan deps), and gate
consistency.

### 2. Execute

For every task in the plan, the agent does this and **only** this:

1. Re-read the plan row for the task. Do not re-read the whole plan.
2. Re-read the artefacts listed in the task's `inputs` (if any).
3. Do the work.
4. Write the result to the path declared in `outputs`. Never keep the
   result in chat context for the next task.
5. Append every claim worth keeping to the evidence ledger
   (`evidence-ledger.csv`, see `references/evidence-ledger.md`).
6. Mark the task `done` with `scripts/research_plan.py mark --id <id>
   --status done`.

**Context discipline.** The agent must never paste the contents of a
raw extraction back into the chat. Raw extractions live on disk
(typically under `research-output/raw/<source>.json` or `.md`). Only
the structured rows in the evidence ledger and the per-task summary
artefact are allowed to re-enter context, and only when needed.

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
that have all dependencies satisfied and no output-path conflicts.

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

### 4. Verify (gates)

Before transitioning between phases, the orchestrator runs
`scripts/research_plan.py gate --file research-plan.json --gate <name>`.
The gate checks the assertions declared in the plan and exits non-zero
if any fail.

Three standard gates are provided. A plan can add more.

- **`gate.execute_ready`** — every task has `id`, `description`,
  `outputs`; dependency graph is acyclic; no task is `done` yet.
  Passes once at the end of the plan phase.
- **`gate.synthesize_ready`** — every task is `done` or `blocked`;
  every blocked task has a non-empty `blocker_reason`; every
  declared `outputs` path exists on disk; the evidence ledger
  validates (`scripts/evidence_ledger.py validate`) and is signed
  (`scripts/evidence_ledger.py verify`); the reproducibility
  checklist file exists. Passes once at the end of the execute
  phase.
- **`gate.release_ready`** — `synthesize_ready` plus: the final
  report exists, the citation render exists, and the plan's
  `stopping_criteria` are marked satisfied. Passes once at the end
  of synthesis.

If a gate fails, the agent fixes the failure and re-runs the gate.
The agent never advances past a failing gate.

### 5. Synthesize

The synthesis phase is the **only** phase that produces a
narrative artefact (the final report). The agent does this:

1. Read the plan (just the metadata + sub-questions + gates).
2. Read the evidence ledger (full).
3. Read each per-task summary artefact (small structured
   markdown/JSON, not raw extractions).
4. Compose the report following
   `references/final-report-template.md`.
5. Render citations with `scripts/citation_render.py`.
6. Sign the ledger with `scripts/evidence_ledger.py sign`.
7. Run `gate.release_ready`.

If at any point the agent feels the urge to "go look at one more
source", it instead adds a follow-up task to the plan, marks the
current cycle's plan as complete, and starts a new cycle. Synthesis
never silently expands scope.

## Gate definitions

Gates are declared inline in `research-plan.json` under `gates`. Each
gate has a name and an ordered list of assertions. The default
template defines `execute_ready`, `synthesize_ready`, and
`release_ready` (above). Custom gates can be added for domain-specific
requirements — e.g. a PRISMA review might add:

- `gate.prisma_flow_filled` — `templates/prisma-flow.json` is
  populated and the identification/screening/included counts add up.
- `gate.dual_screened` — every row in `screening-log.csv` has a
  second-reviewer column populated.

## Failure modes and how to handle them

| Failure | Detection | Response |
|---|---|---|
| A task takes longer than its budget | `research_plan.py status` shows it `running` past budget | Split the task into smaller sub-tasks, update the plan, re-run `gate.execute_ready` |
| A sub-agent returns inconsistent output | Output schema mismatch on read-back | Mark the task `blocked` with `blocker_reason`, re-dispatch with a tighter prompt |
| Two tasks accidentally write to the same file | `parallelizable` would have caught it; if it slipped, the second write overwrites the first | Treat as data loss; re-run the task; tighten the plan to fix the conflict |
| The agent runs out of context anyway | The orchestrator detects a long-input retry | Checkpoint: persist `research_plan.py status` output, then restart in a fresh session with the same plan file |
| The evidence ledger fails validation mid-run | `gate.synthesize_ready` blocks | Fix the offending row(s), re-validate, re-sign |
| A gate fails | Non-zero exit from `scripts/research_plan.py gate` | Fix the failing assertion(s), do not advance |

## Anti-patterns

- **Inline raw extraction in chat.** Always to disk first.
- **Re-reading the full plan on every task.** Re-read only the task row.
- **Hand-editing `research-plan.json` while a task is running.** Use
  the script's `mark` / `add-task` / `block` subcommands so the
  schema stays valid.
- **Skipping gates "because it's just a small task".** Gates are
  cheap to run. Skipping them is how regressions happen.
- **Letting sub-agents talk to each other.** They must communicate
  through artefacts on disk; never peer-to-peer.

## See also

- `templates/research-plan.json` — the starter plan with the schema
  the script enforces.
- `scripts/research_plan.py` — `init`, `add-task`, `mark`, `block`,
  `check`, `parallelizable`, `gate`, `status`, `self-test`.
- `references/evidence-ledger.md` — the ledger schema, also the
  signing flow.
- `references/reproducibility-checklist.md` — the post-execute
  audit.
- `references/final-report-template.md` — the synthesis template.
- `examples/long-horizon-research-plan.md` — an end-to-end worked
  example.
