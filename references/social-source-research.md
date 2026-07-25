# Cross-Platform Social Source Research

## Contents

- [Purpose](#purpose)
- [Platform-neutral classification](#platform-neutral-classification)
- [Source roles](#source-roles)
- [Promotion rules](#promotion-rules)
- [Cross-platform workflow](#cross-platform-workflow)
- [Lineage and coordination](#lineage-and-coordination)
- [Output sections](#output-sections)
- [Boundaries](#boundaries)
- [See also](#see-also)

## Purpose

Use this route for multi-platform research across public Reddit, X, Facebook,
Instagram, Hacker News, Mastodon, Bluesky, Lemmy, YouTube, TikTok, LinkedIn,
GitHub, public forums, and other lawfully reachable community surfaces.

This route researches claims, reception, statements, and public discourse. Use
`references/social-media-archival.md` when the deliverable is a snapshot of one
specific post.

## Platform-neutral classification

Do not label an entire platform official or unofficial. Classify every item by:

| Axis | Example values |
|---|---|
| speaker identity | official, verified public role, claimed identity, stable pseudonym, anonymous, unknown |
| relationship to claim | subject, authorized representative, firsthand witness, journalist, secondhand, commentary, repost |
| origin | original, firsthand, quote, repost, screenshot |
| integrity | live/intact, edited, deleted, archive snapshot, screenshot-only, unverified |
| corroboration | independent source IDs, not raw repost count |
| contradiction | none, possible, direct, unresolved |
| data sensitivity | public, professional, personal, sensitive, secret, minor |

A company's official Facebook post is primary evidence that the company made
the statement; it does not automatically prove every underlying factual claim
inside it. An anonymous X post can be a lead. A maintainer's Hacker News comment
can be primary for the maintainer's own decision and only commentary for
another person's motive.

## Source roles

### Official or primary social evidence

Use in main findings for the fact that a statement was made when the speaker is
the subject or an authorized representative and the item has a stable original
or archive anchor. Treat the statement's underlying factual claims separately;
material/high-impact facts require reviewed primary corroboration.

### Credible independent social evidence

Use as corroboration when identity, firsthand relationship, and independence
are established. Preserve uncertainty when identity or timing remains partial.

### Community, anonymous, or reposted material

Use as discovery leads, reception evidence, jargon discovery, or contradiction
signals. Do not count a repost chain as multiple independent sources.

### Prohibited material

Do not retain or report private messages, gated-group content, stolen secrets,
minor-targeting content, precise whereabouts, or doxxing material even when a
public post links to it.

## Promotion rules

Use `scripts/investigation_policy.py assess-source` for a deterministic first
pass. Declare `--claim-kind statement_made` or `underlying_fact`, use distinct
`--corroboration-id` lineage values, and reserve `--human-reviewed` for a real
review. A boolean corroboration assertion alone cannot promote a material fact.
Human review remains responsible for context, identity, and independence.

Promote an item to main findings when one of these is true:

- it is an official or verified-public-role original statement about the
  speaker's own act, position, product, organization, or announcement;
- it is firsthand, intact or archived, and independently corroborated;
- it embeds or links a primary document whose authenticity is verified;
- a non-social official or primary source independently supports the same
  material claim.

The ledger promotion path is stricter than this narrative guidance: a social
row under `main_findings` must carry `claim_kind=statement_made`, an intact
hash-matched direct/API or archive capture, and an official/verified subject or
authorized representative with original content. If any of those fields is
missing, emit a lead and keep the item out of the main evidence summary.

Keep an item in `Non-official / unverified leads` when:

- identity is claimed, pseudonymous, anonymous, or unresolved;
- the content is secondhand, commentary, a repost, or a screenshot;
- archive/integrity cannot be checked;
- the claim concerns a third party without independent corroboration;
- direct contradictions remain unresolved.

Low-impact descriptive conclusions may use multiple independent community
sources when no stronger evidence exists and uncertainty is explicit. Never
use this exception for identity, criminality, medical/financial status,
security exposure, precise location, minors, or leak-derived claims.

## Cross-platform workflow

1. Define the claim or reception question before selecting platforms.
2. Identify authoritative handles and canonical platform anchors.
3. Search exact claims, aliases, dates, unique phrases, and contradictions
   across relevant platforms.
4. Capture stable URLs, author handles, timestamps, thread context, and
   archive/hash status.
5. Build a lineage ID for reposts, screenshots, mirrors, and quoted posts.
6. Disambiguate same-name and impersonation risks with positive evidence.
7. Record each item once per independent origin; attach reposts to its lineage.
8. Actively search for corrections, edits, deletions, community notes, and
   contrary firsthand accounts.
9. Route the item to main findings, leads, redaction, or blocked output.
10. Stop when new platforms add no independent evidence, not merely when they
    add no new URLs.

Respect platform terms, public visibility, robots where crawling applies, and
rate limits. Logged-in access is permitted only when the user lawfully
authorizes an existing session and the route remains read-only; never use it to
reach private or followers-only content.

## Lineage and coordination

Use one `lineage_id` for content that traces to the same origin. Ten reposts of
one anonymous claim are one source lineage, not ten corroborations.

Possible coordination or astroturfing is a pattern claim. Support it with
transparent timing, account, and content-similarity evidence; do not infer a
controller or motive without direct evidence.

## Output sections

### Main findings

Include verified social claims with speaker role, claim relationship, date,
integrity status, corroboration, contradiction, and confidence.

### Non-official / unverified leads

For each lead include:

- stable source or archive URL;
- speaker/handle and identity status;
- relationship to the claim;
- lineage ID and repost status;
- the lead it creates;
- verification attempts and missing evidence;
- contradictions and confidence;
- the condition required for promotion.

### Reception signals

Separate public reaction or community sentiment from factual claims about a
person or event. Describe sampling and platform bias; do not call it public
opinion without a defensible sampling method.

## Boundaries

- Never scrape DMs, private groups, followers-only posts, or private profiles.
- Never re-identify a pseudonym unless the subject self-disclosed the link.
- Never aggregate a private person's behavior across platforms into a dossier.
- Never report minors, personal contact, home address, sensitive schedules, or
  stolen secrets found in social content.
- A deleted post may be researched through a lawful public archive, but its
  deletion, archive date, and limited context must be explicit.

## See also

- `references/social-media-archival.md`
- `references/investigative-research.md`
- `references/person-aggregation.md`
- `references/source-quality-rubric.md`
- `references/evidence-ledger.md`
