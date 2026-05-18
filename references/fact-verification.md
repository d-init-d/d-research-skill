# Fact Verification (atomic-fact fast path)

Use this file when the user asks to verify, look up, or report **one named atomic fact** about **one named entity**: a commit SHA, a package version, an API pagination limit, the date of a release, a single clause from a license, a single field on a registry record. The full 12-step deep-research workflow is over-engineered for this task class — most of the cost (decompose, fanout, crawl) returns no new information for one-entity-one-attribute questions.

This is **not** a license to skip verification. It is a license to skip *over-verification*. Every claim in the fast path still ends up in the evidence ledger with a primary source, a quote, and a contradiction check.

## When this branch applies

All five must be true:

1. The question targets exactly **one entity** (one repo, one package, one license, one record, one person, one URL).
2. The question targets exactly **one attribute** of that entity (one SHA, one version, one quote, one date, one number).
3. There exists a **deterministic primary source** for that attribute (an API, an official registry, the canonical text). If no such source exists, this branch does not apply — fall back to the broad research workflow.
4. The user has **not** asked for trends, comparisons, history, opinions, or context beyond the bare fact.
5. The bare answer fits in a sentence or short quote.

If any condition is false, fall back to `SKILL.md` "If the user asks for a broad research answer." When in doubt, do not use this branch — the cost of the full workflow is small; the cost of a wrong fast answer is high.

## Tool priority for atomic facts

The general `SKILL.md` tool priority list is correct for broad research. For atomic facts, **prefer a deterministic primary source over web search**, in this order:

1. **Wikidata canonical-entity short-circuit.** When verifying a fact about a known entity (a person, organisation, place, or concept with a Q-ID), check `scripts/wikidata.py entity --id <Q-ID>` first. Wikidata claims are sourced and versioned; if the attribute you need is present in the entity's claims, use it as the primary source and cross-check with one independent source. This avoids a full web search for facts that Wikidata already structures (birth/death dates, affiliations, identifiers, official websites).
2. **Citation resolver for academic identifiers.** When the fact involves a DOI, PMID, arXiv ID, or ISBN, use `scripts/citation_resolver.py` to resolve it in one request. This returns canonical metadata (title, authors, year, journal) without a full search loop. See `adapters/citation-resolver.md`.
3. **Public API of the canonical source.** Git commit → GitHub/GitLab/Gitea API. Package version → PyPI/npm/crates.io JSON. Standards body → its registry/IANA/SPDX. DOI → CrossRef.
4. **Canonical static file.** A license text on the OSI page, an RFC on the IETF page, a release notes page on the project's own site.
5. **Repository file on the upstream remote.** A `LICENSE` file, a `CHANGELOG.md`, a `package.json`, etc., fetched at a specific ref.
6. **Web search** only if 1–5 do not exist for this fact class. Then prefer the first result that is an *official* domain; never trust a paraphrased fact from an aggregator blog for the final claim.

Skip Playwright and bounded crawl. There is no page to render, no link graph to expand.

## Loop (4 steps, not 12)

```
1. Restate. Write one sentence: "verify <attribute> of <entity>." If you can't, the task isn't atomic — bail to broad research.
2. Fetch. Hit the deterministic primary source once. Capture the exact response (status, body, hash if possible).
3. Verify. Quote the raw value verbatim in the evidence ledger with source URL, access method, and date. Run a single independent re-check — see "Contradiction check" below.
4. Report. One direct sentence + verbatim quote + source. If anything looked off, fall back to the full workflow before reporting.
```

That's the whole loop. No decompose, no source map, no query fanout, no crawl, no synthesis section. The evidence ledger has 1–3 rows, not 20.

## Contradiction check (1-shot)

Atomic facts get a single contradiction check, not the full contradiction pass.

Pick one of these, the first that applies:

- **Independent primary mirror**: a second canonical source for the same value (GitHub API ↔ git CLI clone; PyPI JSON ↔ the package's own `__version__`).
- **Adjacent attribute on the same record** that should be self-consistent (a commit SHA's `parents` array confirms it is or isn't a root commit; a release's `prerelease` flag confirms it is or isn't stable).
- **Error response shape** when querying out-of-range values (request `per_page=201` to see what the API itself enforces — see `templates/frontier-ledger.csv` row N004 for an example of why this matters).

If the two sources agree → confidence: `high`. If they disagree → escalate to the broad research workflow and treat the discrepancy as the new research question. Do **not** silently pick one.

## When to escalate back to the full workflow

Bail to the broad research workflow if any of these is true after step 2 or 3:

- Primary source returned a non-2xx status, a stale value, or a redirect chain you don't fully understand.
- Primary source returned 403, 429, captcha, or a JavaScript challenge: run `references/anti-bot-fallback.md` once before producing `references/blocker-report.md`.
- Two independent primary sources contradict.
- The user follows up with a "why" or "how" question — those are no longer atomic.
- The answer requires interpretation, not just transcription (e.g., "does this license grant a patent right" — quoting the text is atomic, *concluding* the legal implication is not).

## Stopping criteria

Stop after one of these:

- One primary-source claim is filed at confidence `high` with a verbatim quote and the independent re-check agreed.
- Three fetches in a row failed to load the primary source — produce a `references/blocker-report.md` instead of a synthesised answer.
- The question turned out not to be atomic — switch branches.

Never escalate to `references/frontier-search.md` from this branch. Frontier search is for *gap-driven* follow-up when the broad workflow already left holes; atomic facts don't have holes to gap-fill, they have a single answer that either fetched cleanly or didn't.

## What this branch deliberately does not do

- It does not skip the evidence ledger. The ledger still records the single claim and its source.
- It does not skip the safety boundary. Login walls, paywalls, captchas, rate limits, and `robots.txt` restrictions still stop the agent — produce a blocker report.
- It does not skip verbatim quoting. A paraphrased "yes/no" without the quote is not a fact-verification answer.
- It does not replace `references/frontier-search.md`, the contradiction pass in `SKILL.md` step 9, or the source-quality rubric. It is a faster path *for one task class*, not a relaxation of the standards.

## See also

- `SKILL.md` — entry point and decision tree.
- `references/source-discovery.md` — how to identify the canonical primary source for a fact class.
- `references/source-quality-rubric.md` — scoring rubric still applies to the single source.
- `references/api-access-workflow.md` — pagination, rate-limit, and retry patterns for API-backed primary sources.
- `references/anti-bot-fallback.md` — lawful fallback chain when the deterministic primary source is blocked by anti-bot, 403, 429, captcha, or JavaScript challenge.
- `references/evidence-ledger.md` — schema for the 1–3 ledger rows this branch produces.
- `references/blocker-report.md` — what to record when the primary source itself is unreachable.
- `references/frontier-search.md` — what to use *instead* when the task is broad research with gaps, not a single fact.
- `templates/evidence-ledger.csv` — claim template.
