# Frontier Search (gap-driven follow-up research)

Use this file when a first-pass run of the deep research workflow leaves real evidence gaps and the answer is obscure, long-tail, or scattered across many sources. It adds a lightweight controller on top of `references/source-discovery.md`, `references/query-patterns.md`, and `references/evidence-ledger.md` so the agent can decide *which* node to expand next, *what* it still does not know, and *when* to stop. It does not replace the 12-step workflow in `SKILL.md`; it only kicks in when the standard pass left documented gaps.

This is **not** a literal pathfinding algorithm (no A*, no Dijkstra). It is a single best-first priority queue over candidate research nodes, scored against the unresolved gaps in the evidence ledger. Treat the word "frontier" as bookkeeping, not as a promise of exhaustive Internet coverage. Stay inside `references/safety-and-access-policy.md` — frontier search never bypasses login, paywall, captcha, rate limit, or `robots.txt`.

## When to escalate

Escalate to frontier search only when at least one trigger is true. Otherwise the standard workflow is faster and cheaper.

1. The user explicitly asks for exhaustive, obscure, or hard-to-find facts.
2. After the first pass, the evidence ledger has key claims at `confidence: low` and no primary source.
3. A `sub_question` in the coverage map has `missing` entries after the standard pass.
4. The contradiction pass found a direct or unresolved conflict that no current source settles.
5. The entity has many aliases, old names, subsidiaries, or local-language variants that were not all searched.
6. Promising file/sitemap/API/citation/repo paths were observed but not opened due to depth limits.

If none of the triggers fire, stop here. Synthesize from the evidence ledger as usual.

## The two ledgers and the gap map

Frontier search uses three artefacts. Two already exist; one is new.

| Artefact | Granularity | Already in skill | Purpose |
|---|---|---|---|
| `templates/evidence-ledger.csv` | one row per atomic claim | yes — see `references/evidence-ledger.md` | what is known and how confident |
| `templates/coverage-map.json` | one entry per sub-question | new | what is still missing and what to do about it |
| `templates/frontier-ledger.csv` | one row per candidate node visited or queued | new | the actual search trace (queries, URLs, files, APIs, citations) and why each path stopped |

Keep the three in sync. A frontier node that produced evidence must list the resulting `claim_ids`. A claim added to the evidence ledger must point back to the frontier node it came from. The coverage map summarises the gap-level state and drives expansion decisions.

## Node types

A frontier node is anything that can be opened, searched, or fetched. Use one of these `node_type` values in `templates/frontier-ledger.csv`:

- `query` — a search query for a search engine or API.
- `url` — a specific public page (HTML, JSON, XML, RSS, sitemap).
- `file` — a public downloadable file (PDF, CSV, XLSX, JSON, DOCX, XML).
- `api` — a REST/GraphQL/SPARQL endpoint (see `references/api-access-workflow.md`).
- `citation` — a paper / DOI / arXiv ID / dataset to chase (see `references/academic-databases.md`). Use `scripts/citation_graph.py to-frontier` to convert a citation graph into frontier candidates.
- `repo` — a code repository, release, changelog, issue, or discussion thread.
- `alias` — a renaming/alias/old-name/local-language form of an entity to re-search.
- `archive` — an archived or historical copy (see `references/monitoring-change-detection.md`).
- `semantic_neighbor` — a document or claim found via embedding similarity to an unresolved sub-question (see `references/semantic-retrieval.md`). Use `scripts/embed_corpus.py query` to find candidates from an indexed corpus.

## Priority score

Score each candidate node with a small, transparent formula. **Do not** invent extra factors; more variables make the score noisier, not better. Use 0–5 for each component and weight in this order:

```
priority = 2 * gap_priority
         + 2 * relevance
         + 1 * novelty
         + 1 * authority
         - 1 * access_cost
```

Where:

- `gap_priority` (0–5) — how important is the sub-question this node could close? Pull from `templates/coverage-map.json` (`required_evidence` minus `found_claim_ids`).
- `relevance` (0–5) — how likely this node answers that gap. Reuse the rubric in `references/source-quality-rubric.md` and `references/source-discovery.md`.
- `novelty` (0–5) — does the node add evidence beyond the current ledger, or just restate it? Penalise duplicates of already-cited sources.
- `authority` (0–5) — primary/official/government/repository upstream beats secondary aggregators. Same scale as `scripts/score_source.py`.
- `access_cost` (0–5) — extra cost to reach the node: dynamic JavaScript, large or scanned PDFs, login-required mirrors, deep pagination, rate-limited APIs. Login/paywall/captcha walls go straight to a blocker report, not a high `access_cost`.

If the same source can be reached two ways, prefer the path with lower `access_cost` and higher `authority`.

## Loop

```
1. Read evidence-ledger.csv and coverage-map.json.
2. If no sub-question has `missing` entries, stop. Synthesize.
3. Otherwise build the frontier:
   - for each gap, list candidate query, url, file, api, citation, repo, alias, archive nodes
   - score each node with the formula above
   - drop nodes already in `visited` or `blocked` state in the frontier ledger
4. Pop the highest-priority node.
5. Probe it using the existing tool priority (`SKILL.md` "Tool priority").
6. Update both ledgers:
   - frontier-ledger row: visited / extracted / blocked / dead_end / deferred
   - evidence-ledger rows for any new claims
   - coverage-map: move claim ids from `missing` to `found_claim_ids` when satisfied
7. Re-score the remaining frontier whenever a gap closes or a new node is discovered.
8. Stop on any saturation condition below.
```

## Stopping criteria

Stop frontier expansion as soon as one of these is true. Saturation matters more than node count.

- All `sub_questions` in `templates/coverage-map.json` have `missing: []` or confidence is at least `medium` with primary sources.
- No remaining frontier node has `priority` above the configured threshold (default: `priority >= 5`).
- Three consecutive expansions add no new claims to the evidence ledger.
- The frontier budget is exhausted (`crawl.maxTotalPages` from `research.config.example.json`, or an explicit per-run cap).
- Every promising remaining node is blocked by login/paywall/captcha/rate limit/robots — record each one with `references/blocker-report.md` instead of forcing access.
- The contradiction pass converged: no source contradicts another at high confidence.

Never claim total Internet coverage. Report only reachable-evidence coverage, as in `SKILL.md` "Output standards".

## Integration with the rest of the skill

- **First pass**: run `SKILL.md` steps 1–11 normally. Frontier search is step 11.5, not a replacement.
- **Long-horizon tasks**: when `scripts/research_plan.py` is in use, treat `coverage-map.json` and `frontier-ledger.csv` as additional workspace artefacts. They sit alongside `research-plan.json` and the evidence ledger inside the run folder. Do not merge them with `research-plan.json`; they answer different questions (gap vs. task status).
- **Multilingual research**: feed alias and local-language variants in as `alias`-type frontier nodes. See `references/multilingual-research.md`.
- **Register/jargon gaps**: when a gap persists because the basin uses lay, community, or vernacular terms, feed confirmed register variants in as `alias`-type frontier nodes (no new node type needed). See `references/register-and-jargon-expansion.md`.
- **Time-sensitive claims**: use `archive`-type nodes to chase changelogs, release notes, and prior versions. See `references/monitoring-change-detection.md`.
- **Academic gaps**: prefer `citation`-type nodes via OpenAlex / CrossRef / Semantic Scholar. See `references/academic-databases.md`.
- **API-shaped data**: prefer `api`-type nodes when a page exposes a network endpoint. See `references/api-access-workflow.md`.

## What this layer deliberately does not do

- It does not promise to find every fact. Some sources are unreachable.
- It does not bypass any access control. Blocked nodes go to a blocker report.
- It does not implement A*, Dijkstra, beam search, iterative deepening, or any other named graph algorithm — just a best-first priority queue over candidate nodes.
- It does not replace the contradiction pass, the evidence ledger, the source-quality rubric, or the research-plan protocol.

## See also

- `SKILL.md` — entry point and decision tree.
- `references/source-discovery.md` — how to build the initial source map.
- `references/query-patterns.md` — query fanout for `query`-type frontier nodes.
- `references/register-and-jargon-expansion.md` — register variants for `alias`-type nodes when the basin uses vernacular terms.
- `references/evidence-ledger.md` — claim-level evidence schema.
- `references/source-quality-rubric.md` — scoring rubric reused for `authority` and `relevance`.
- `references/blocker-report.md` — what to record when a node is blocked.
- `references/research-plan-protocol.md` — long-horizon workspace this layer sits inside.
- `references/safety-and-access-policy.md` — non-negotiable access boundaries.
- `templates/frontier-ledger.csv` — frontier trace template.
- `templates/coverage-map.json` — evidence-gap template.
- `templates/evidence-ledger.csv` — claim-level evidence template.
