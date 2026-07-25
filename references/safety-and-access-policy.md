# Safety and Access Policy

Use this file for all data collection, crawling, browser automation, person
OSINT, social research, self-exposure audits, and authorized security research.

## Contents

- [Default mode](#default-mode)
- [Capability and hard floor](#capability-and-hard-floor)
- [Access boundaries](#access-boundaries)
- [Discovery, retention, and reporting](#discovery-retention-and-reporting)
- [Person and social research](#person-and-social-research)
- [Leak-derived material and self-exposure](#leak-derived-material-and-self-exposure)
- [Blocked and uncertain sources](#blocked-and-uncertain-sources)
- [Machine translation privacy](#machine-translation-privacy)
- [Policy artifacts](#policy-artifacts)

## Default mode

Research is read-only by default. Browser routes block page-originated HTTP
methods other than `GET` and `HEAD`; WebSockets and service workers remain
fail-closed. Do not submit forms, create accounts, make purchases, change
settings, or message people unless a separate workflow explicitly authorizes
that exact side effect.

## Capability and hard floor

`R0` through `R4` add research capability, not permission to cause harm. `RX`
always stops the affected branch:

- access-control, authentication, paywall, captcha, rate-limit, IP-ban, or
  robots bypass;
- stolen credentials, tokens, cookies, sessions, MFA material, or private keys;
- minors targeting, stalking, doxxing, harassment, real-time whereabouts, or
  weaponized dossiers;
- unauthorized pseudonym re-identification;
- malware, persistence, C2, credential attacks, exploitation, or exfiltration
  outside verified authorization.

The user's title (including “black hat,” “white hat,” journalist, investigator,
or security researcher) is not an authorization signal. Classify the requested
act, target, scope, source, and output.

## Access boundaries

Never bypass login, authentication, paywalls, captchas/bot challenges, access
controls, rate limits, IP bans, or robots restrictions when crawling. Stop on
repeated 403/429/login/captcha responses after the bounded fallback chain in
`references/anti-bot-fallback.md`.

Lawful authenticated access is allowed only when the user authorizes an
existing session or provides credentials they are entitled to use, the scope
permits that source class, and the operation remains read-only. It may not be
used to reach private messages, followers-only content, gated groups, or data
outside the user's permission.

## Discovery, retention, and reporting

Treat these as separate decisions:

1. `discovery_disposition`: may the item open a research branch?
2. retention/redaction: may any value enter prompts, caches, embeddings, files,
   or the evidence ledger?
3. `reporting_disposition`: may the claim enter main findings, a lead section,
   a redacted section, or nowhere?

Public visibility is not automatic permission to aggregate or republish. Apply
the narrowest useful retention. Personal contact, residences, government IDs,
financial/medical data, family/minors, intimate data, and precise whereabouts
are discarded or redacted unless a verified self/incident scope makes a
specific minimized field necessary.

## Person and social research

Named-person research uses `R2` and `references/person-aggregation.md`. A
private-person branch needs authorization or a time-bounded reviewed
public-interest attestation and may retain only public/professional data.

Social platforms are transport surfaces, not authority classes. Classify each
item by speaker, relationship, origin, integrity, lineage, sensitivity, and
corroboration under `references/social-source-research.md`. Reposts in one
lineage are not independent evidence.

## Leak-derived material and self-exposure

Follow `references/leaked-data-handling.md`:

- public breach reporting may be ordinary evidence;
- an authorized provider or affected-user corpus is conditional, minimized,
  audience-bound, and retention-bound;
- a publicly visible raw-leak claim is metadata-lead-only—do not fetch, quote,
  archive, link, hash, or parse the dump;
- secret material is prohibited—do not retain, echo, test, validate, transform,
  or use it for access.

Queries about a private identifier's exposure require verified `R3` ownership
or organizational authorization. Otherwise report only public incident facts
that do not confirm an individual's presence in a corpus.

## Blocked and uncertain sources

When access is blocked or custody/legality is unclear, use public summaries,
official notices, an authorized provider, or manual retrieval by an authorized
human. Record the limitation and produce a blocker report; do not escalate.

## Machine translation privacy

Remote translation services send text to third parties. They require explicit
`--allow-remote` opt-in. Do not send sensitive or conditional evidence to a
public translation service; prefer local translation and record any remote use
in ledger notes.

## Policy artifacts

For `R1`-`R4`, validate `templates/investigation-scope.json` with
`scripts/investigation_policy.py`. Planned work binds the exact file to
`research-plan.json` with `research_plan.py bind-policy`; any policy edit
invalidates `investigation_scope_valid` until the plan is rebound, rendered,
and approved again.
