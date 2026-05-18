# Person Aggregation (public-info search about a named person)

Use this file when the user asks for **scattered public information about a single named person** — usually a maintainer, author, speaker, journalist, scientist, public figure, or someone they want to identify or reach for a legitimate, public reason. This task class has its own branch because (a) the value is in *cross-source aggregation*, not in any one source, (b) name collisions ("two trường Marie Curie", "three Vu Anh on GitHub") have to be resolved with positive evidence before answering, and (c) the privacy boundary in this file is **not optional** — it is a hard stop on what may be aggregated, regardless of whether the data is technically public somewhere on the open web.

This is **not** a license to build a dossier. It is a focused workflow for a narrowly-defined task class with explicit limits.

## When this branch applies

All four must be true:

1. The user is asking about **one named person** (or one named pair / small group when the request is naturally joint, e.g. "co-authors of paper X").
2. The information they want is **the kind a public-facing professional would be expected to publish themselves** — current role and affiliation, public projects/maintained repos, public talks, public papers, public press coverage, an authored book, an actively advertised contact channel for that public role.
3. There is at least one **canonical or authoritative starting point** (a GitHub profile, an ORCID record, a package author field, an academic faculty page, a verified press byline). If there is no canonical starting point, this is a person-discovery task, not person-aggregation — fall back to the broad research workflow.
4. The request has a **publicly legitimate purpose**: contributing to an OSS project, citing a paper, reaching out for press/work, verifying a public claim, disambiguating a name. If the request is clearly investigative on a private individual, refuse — see "Hard stops" below.

If any condition is false, do not use this branch.

## Privacy boundary (explicit list — not abstract)

The agent **must not** aggregate, infer, link, or report any of the following, even if individual pieces appear on the open web:

- **Home/residential address, neighbourhood, or precise geographic location** beyond a publicly-stated city of work or country of residence.
- **Family members, relatives, partners, or children** — names, schools, ages, photos, social handles — unless the person themselves has publicly tied the family member to their public role (e.g. a co-authored book, a jointly-run company) **and** the family member is a public figure in their own right.
- **Private social media accounts.** A profile is "private" if it is set to friends-only, is a non-public Facebook account, a personal-vs-professional Instagram, a locked Twitter/X, etc. Public verified accounts of the person's public role (e.g. their `@handle` on the OSS repo, their LinkedIn, their professional website) are fine.
- **Personal phone numbers or personal email addresses.** Role-based contacts that the person publishes themselves for that role (`maintainer@project.org`, `press@…`, a clearly-advertised speaker booking address on a personal site) are fine. Email addresses harvested from leaked databases, scraped from non-public forms, or constructed from guessing patterns are not.
- **Photos or personal images** beyond the person's own public profile photo on a professional context.
- **Medical, mental-health, financial, legal, immigration, or sexual-orientation information.**
- **Religious or political affiliation** unless the person is a public political figure where the affiliation is part of the public role itself.
- **Real-time location, calendar, travel pattern, or whereabouts.**
- **Re-identification of pseudonymous accounts.** If a person publishes under a pseudonym (e.g. an anonymous blog, a pseudonymous code maintainer), do not link the pseudonym back to a real-name identity unless the person has done so themselves.
- **Anything the person has explicitly asked not to publish**, on the same page where it would otherwise be aggregated.

The above is the floor, not the ceiling. If something feels in-scope but adjacent to one of these categories, treat it as out-of-scope.

## Hard stops (refuse before starting)

Refuse the task and explain the refusal if any of these is true:

- The subject is a private individual (not a public-role figure) and the request is not the subject's own self-research.
- The subject is a minor.
- The framing suggests harassment, stalking, doxxing, debt-collection on a person hiding from a creditor, intimate-partner search, ex-partner search, or "find where someone lives."
- The request specifically asks for any item in the privacy-boundary list above.
- The request asks the agent to bypass an access control (a private profile, a paywall, a captcha, a robots-disallowed area) in order to find personal information.

A refusal is short, polite, and points to what *would* be in-scope (e.g. "I can pull this OSS maintainer's public repos, talks, and the maintainer email they list on the project page — I won't aggregate private accounts, family, or non-public contact information.").

## Workflow (9 steps)

```
0. Anchor resolution via Wikidata. Before fanning out to web sources, attempt to resolve the person to a Wikidata Q-ID using:
   scripts/wikidata.py disambiguate --term "<name>" --context "<context>"
   where <context> is the role, affiliation, or domain the user mentioned. If a high-confidence match is returned (score ≥ 0.5), adopt the Q-ID as the canonical anchor and use `scripts/wikidata.py entity --id <Q-ID>` to seed the alias set, affiliation, and known works. If no match or low confidence, proceed to step 1 without a Wikidata anchor.
1. Restate. Write one sentence: "aggregate public-role info about <person> for <purpose>." Apply the privacy boundary and hard stops before doing anything else.
2. Identify the canonical anchor. Pick the single most authoritative starting point — usually the artifact tying the person to the public role (a GitHub profile, an ORCID, a package `author` field, a journal byline, a verified site). Capture URL, access date, and a content hash if possible. If step 0 returned a Q-ID, the Wikidata entity page is a valid canonical anchor.
3. Build the alias set. Collect spellings and handles the person actually uses (`Vu Anh` / `Vũ Anh` / `vuanhle`), tied to the anchor. Mark each alias `verified` or `tentative`. Do not include aliases whose link to the anchor is purely circumstantial. See `references/multilingual-research.md` for diacritic / transliteration handling.
4. Disambiguate. Before fanning out, enumerate the homonyms (GitHub will list every `Vu Anh`; "Marie Curie" school exists in HCMC and Hà Nội). For each candidate match found later, require at least one positive disambiguator (same project, same publication, same affiliation, same handle, same time period) before adopting it.
5. Source map. For *this* public role, pick the source classes that apply: code-host profile, package registries, ORCID/Scholar/Crossref, official affiliation page, conference/talk pages, public press coverage, the person's own site/blog. Skip social-platform deep-dives unless the platform handle is verified-public and on-topic for the role.
6. Fetch and cross-link. For each source, capture: (a) the exact URL, (b) what claim about the person it supports, (c) which other source independently confirms the same claim, (d) what alias it uses. File one ledger row per (claim, source) pair. Stop a source class as soon as it adds no new verified claims.
7. Privacy filter. Before synthesising, walk every aggregated claim past the privacy-boundary list. Drop anything that violates the boundary, even if it was cited by an otherwise-on-topic source. Do not silently keep "interesting-but-out-of-scope" claims for context.
8. Synthesize. Produce a structured profile: public role + verified aliases + role-bound contact + public works + public press, each with at least one source and a confidence tag. List unverified claims separately. State explicitly which homonym variants you considered and which you ruled out.
```

That is the whole loop. The ledger ends up with 5–25 rows for a typical OSS maintainer / public figure, not hundreds.

## Saturation criteria (when to stop)

Stop on the first of:

- Three consecutive new sources add **no new verified claims** for the open public-role attributes. The role is *saturated*; further fetching is not "more thorough", it is scope creep into the privacy boundary.
- 25 ledger rows. If the question genuinely needs more, the user is asking for a dossier — re-scope with them before continuing.
- A homonym cannot be disambiguated with a positive signal. Report the ambiguity to the user with a one-line description of each candidate, ask which one they mean, then resume.
- Any source attempts to push the agent past the privacy boundary (a profile aggregator, a "people search" site, a data-broker domain, a leaked-database mirror). Stop, do not extract, do not cite.

Never escalate to `references/frontier-search.md` to chase a person across the long tail. Frontier search exists for evidence gaps in *broad research*; "I want one more piece of personal info" is exactly the kind of gap this branch deliberately leaves open.

## Examples in scope

- "Who maintains the underthesea Vietnamese NLP library, and what's the best public channel to reach them about a contribution?" → GitHub profile + PyPI author + project README + maintainer email if published on the repo.
- "I'm writing a press piece — who is the lead author of this 2024 paper on dataset X, and what's their public affiliation?" → ORCID + the paper's correspondence-author footnote + the affiliation's faculty page.
- "Disambiguate the two Marie Curie schools in Vietnam in the context of a 1992 alumnus." → school official sites + verified press references that distinguish the HCMC and Hà Nội campuses, including the public-relations channel of each.

## Examples out of scope (refuse or redirect)

- "Find <name>'s home address / phone / family." → refuse.
- "Where does <maintainer> live now?" → refuse; offer city-of-work from their public bio if they list one.
- "Who is the real identity behind <pseudonymous handle>?" → refuse unless the person has self-disclosed.
- "Pull every photo of <name> from the open web." → refuse.
- "Build a profile of my ex-classmate from social media." → refuse.

## What this branch deliberately does not do

- It does not produce a "dossier" — the output is a structured public-role profile, capped at saturation.
- It does not skip the evidence ledger or the source-quality rubric. Every claim is sourced and scored.
- It does not relax the access-control rules. Login walls, paywalls, captchas, rate limits, and `robots.txt` still stop the agent; produce a blocker report.
- It does not cross-link pseudonymous identities to real-name identities.
- It does not replace `references/frontier-search.md`, the contradiction pass, or the multilingual-research workflow — it composes them under a privacy constraint.

## See also

- `SKILL.md` — entry point and decision tree.
- `references/source-discovery.md` — finding the canonical anchor for a public role.
- `references/source-quality-rubric.md` — scoring applies to every aggregated source.
- `references/multilingual-research.md` — name spellings, diacritics, transliteration, and cross-language alias handling.
- `references/evidence-ledger.md` — schema for the per-claim rows this branch produces.
- `references/blocker-report.md` — what to record when a source requires login or otherwise refuses access.
- `references/fact-verification.md` — for "verify *one* atomic fact about this person" (a single SHA, a single paper DOI), use that branch instead.
- `templates/evidence-ledger.csv` — claim template.
