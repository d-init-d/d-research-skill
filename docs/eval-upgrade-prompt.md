# Eval Upgrade Prompt

Copy the block below into the agent runtime that will run the skill. The eval
harness itself does not run an agent; the external agent must produce the ledger
CSVs first, then call the harness.

```text
Run the d-research two-tier eval suite and compare this candidate run against a baseline.

Scope and safety:
- Do not modify CI files.
- Do not push to remote.
- Do not edit files outside temporary run directories unless I explicitly ask.
- Do not touch `scripts/run_dogfood.py`, `examples/evals/*`, or `docs/eval.md` while running the eval.
- Follow the skill safety boundaries. Refusal tasks must refuse before fetching and should produce an empty ledger.
- Some frontier tasks cite in-repo files. The runner must have repository read access and should cite those paths in `source_url`.

Bench files:
- Tier 1 regression bench: `examples/evals/dogfood-bench.json`
- Tier 2 frontier bench 2.2: `examples/evals/frontier-bench.json` (52 tasks, 26 classes covering all v3.0 frontier capabilities — hard atomic facts, subtle contradictions, hidden refusal triggers, long-horizon planning, API drift, systematic review, large-scale collection, monitoring, multilingual research, anti-bot fallback, PDF extraction, Wayback archive, Wikidata disambiguation, social-tier-a, social-tier-b, social-refusal, citation resolution, report generation, OCR extraction, translation, semantic retrieval, citation-graph, multi-format extraction, dedup-and-cache, provenance-compliance, register-jargon-recall)

Output layout:
- Put baseline ledgers under `runs/baseline/tier1-ledgers/` and `runs/baseline/tier2-ledgers/`.
- Put candidate ledgers under `runs/candidate/tier1-ledgers/` and `runs/candidate/tier2-ledgers/`.
- Use one ledger per task named `<task_id>.csv`.

Process:
1. Validate the harness:
   `python3 scripts/run_dogfood.py self-test`

2. If I provided git refs or worktrees, run the baseline first from the baseline ref/worktree, then run the candidate from the candidate ref/worktree. Keep their ledgers and score artifacts separate. If I did not provide refs, ask me which baseline and candidate states to compare before running live tasks.

3. For every task in `examples/evals/dogfood-bench.json`, render the task, run the skill, and save the ledger as:
   `runs/baseline/tier1-ledgers/<task_id>.csv`
   or, for the candidate run:
   `runs/candidate/tier1-ledgers/<task_id>.csv`

4. For every task in `examples/evals/frontier-bench.json`, render the task, run the skill, and save the ledger as:
   `runs/baseline/tier2-ledgers/<task_id>.csv`
   or, for the candidate run:
   `runs/candidate/tier2-ledgers/<task_id>.csv`

5. Score Tier 1:
   `python3 scripts/run_dogfood.py score-all --bench examples/evals/dogfood-bench.json --ledgers-dir runs/baseline/tier1-ledgers --out runs/baseline/tier1-scores.json --threshold 0.7`
   `python3 scripts/run_dogfood.py score-all --bench examples/evals/dogfood-bench.json --ledgers-dir runs/candidate/tier1-ledgers --out runs/candidate/tier1-scores.json --threshold 0.7`

6. Score Tier 2:
   `python3 scripts/run_dogfood.py score-all --bench examples/evals/frontier-bench.json --ledgers-dir runs/baseline/tier2-ledgers --out runs/baseline/tier2-scores.json`
   `python3 scripts/run_dogfood.py score-all --bench examples/evals/frontier-bench.json --ledgers-dir runs/candidate/tier2-ledgers --out runs/candidate/tier2-scores.json`

7. Compare:
   `python3 scripts/run_dogfood.py compare runs/baseline/tier1-scores.json runs/candidate/tier1-scores.json`
   `python3 scripts/run_dogfood.py compare runs/baseline/tier2-scores.json runs/candidate/tier2-scores.json`

8. Report:
   - Tier 1 regressions
   - Tier 2 newly passing tasks
   - Tier 2 newly failing tasks
   - Important caveats, including incomplete ledgers
   - Final one-line summary:
     `OVERALL: <STRONGER|SAME|WEAKER> (tier1=<verdict>, tier2=<verdict>)`
```
