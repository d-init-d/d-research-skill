# Register Recall, Tooled and Benched

v3.0.6 Release Notes

D Research v3.0.6 finishes the register- and jargon-aware recall work introduced
in v3.0.5. v3.0.5 shipped the *method* — a bidirectional register ladder and a
guardrails-first companion. v3.0.6 makes that method **runnable** and
**regression-protected**: the cross-source recurrence rule is now a deterministic
helper script, and the capability is covered by the frontier eval bench.

This is a purely additive release. No existing behavior, evidence-ledger schema,
or script CLI changes.

## What's New

- **`scripts/harvest_terms.py`** turns the "keep only terms recurring across two
  or more independent community sources" rule into a deterministic, offline,
  stdlib-only tool. Feed it tagged `source<delimiter>term` occurrences and it
  counts the distinct sources behind each candidate term, then labels each one
  `confirmed` (at or above the threshold) or `candidate` (below it). It never
  invents vocabulary — it only scores what the agent already harvested from
  fresh results. Run it via `npm run terms:harvest` or
  `python3 scripts/harvest_terms.py harvest --threshold 2`.
- **A `register-jargon-recall` frontier eval class** with two ground-truth tasks
  (FB-051, FB-052). One probes whether the agent can name and apply the
  bidirectional register ladder; the other probes the non-negotiable boundary
  that harvested vocabulary is a discovery layer, never evidence. The frontier
  bench moves from `2.1` (50 tasks / 25 classes) to `2.2` (52 tasks / 26
  classes) under its additive bench-version policy, with matching empty-score
  fixtures regenerated deterministically.

## Why It Matters

A method that lives only in prose is easy to drift away from. v3.0.6 closes that
gap from both ends. The helper script makes the filtering rule executable and
auditable, so "recurs across at least two independent sources" is a command, not
a hopeful guideline. The new bench class makes the capability a tracked
regression target, so a future change that quietly weakens register-aware recall
shows up as a FAIL instead of slipping by unnoticed.

## Determinism and Discovery-Only Discipline

`harvest_terms.py` is intentionally boring: same input, same output, no network,
no model calls. It groups terms case-insensitively, counts distinct source
labels, and applies a threshold. That determinism is the point — the tool
enforces the recurrence filter without becoming a new source of hallucinated
vocabulary. And the boundary from v3.0.5 still holds end to end: confirmed terms
are a discovery layer that opens recall, never evidence; every claim still
passes the source-quality rubric and the contradiction pass.

## Also in This Release

- Removed three stale `placeholder for task 2.x` comments in
  `scripts/pdf_extract.py`. The subcommands they annotated (`tables`,
  `to-ledger`, `self-test`) were already fully implemented; only the misleading
  comments remained.

## Compatibility

- No new runtime dependencies.
- No evidence-ledger schema changes.
- No CLI changes to existing scripts.
- Frontier bench `2.2` is additive; `2.1` score artifacts remain comparable on
  the shared task subset.
- Existing v3.0.x workspaces, ledgers, reports, and eval fixtures remain valid.

## Upgrade Notes

Pull the new release and continue using the skill normally. To exercise the new
helper, pipe tagged occurrences into it:

```bash
printf 'forum-a\tbrain fog\nforum-b\tbrain fog\nblog-c\tbrain fog\n' \
  | python3 scripts/harvest_terms.py harvest --threshold 2
```

Run `npm run self-test` to confirm the full chain — including the new
`harvest_terms` self-test and the bench-harness consistency check — passes.
