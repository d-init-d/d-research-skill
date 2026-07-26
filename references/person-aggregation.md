# Scoped Person OSINT

## Contents

- [Purpose](#purpose)
- [Subject and purpose classes](#subject-and-purpose-classes)
- [Permitted public-professional facts](#permitted-public-professional-facts)
- [Redact or discard](#redact-or-discard)
- [Hard stops](#hard-stops)
- [Workflow](#workflow)
- [Social and non-official sources](#social-and-non-official-sources)
- [Saturation and expansion](#saturation-and-expansion)
- [Output contract](#output-contract)
- [Examples](#examples)
- [See also](#see-also)

## Purpose

Use this route for evidence-backed research about one named person or a small
joint group. The route supports deep public-professional OSINT, name and handle
disambiguation, authored-work discovery, public relationship mapping, event
timelines, and contradiction search.

It is not a promise to find everything and not a license to create a private
life dossier. Name the deliverable `person_osint_scoped` and declare the
purpose, subject class, source classes, data classes, reporting audience, and
stopping criteria before source access.

Validate an `R2` investigation scope for non-trivial runs:

```bash
python scripts/investigation_policy.py init --mode R2 --out investigation-scope.json
python scripts/investigation_policy.py check --file investigation-scope.json
```

## Subject and purpose classes

### Public-role person

Research public-professional facts broadly when they are relevant to the role,
work, public claim, accountability question, due diligence, journalism,
scholarship, or public-interest purpose.

### Private person

Allow only a bounded route when one of these applies:

- the subject is the user;
- the user has verifiable authorization to act for the subject;
- the request is a low-risk factual lookup;
- the task has a documented public-interest, fraud-prevention, incident-
  response, or due-diligence purpose and the output remains public-record-only.

Do not accept user-declared purpose as the only control. Restrict data classes,
aggregation scale, and output actionability.

### Minor

Hard-stop the person route. Do not collect, link, or profile a minor even when
individual facts are public.

## Permitted public-professional facts

- name, verified aliases, and self-disclosed handles;
- current and historical public roles and organizations;
- authored works, papers, books, patents, public code, releases, and filings;
- interviews, speeches, conference appearances, and official statements;
- awards, licenses, public board seats, and public professional affiliations;
- reported-event timelines with exact allegation/charge/judgment status;
- public professional relationships such as co-author, founder, director,
  maintainer, or disclosed business partner;
- role-bound contact explicitly advertised for that role.

Every relationship must state what the evidence proves. Do not infer motive,
intimacy, control, or guilt by association.

## Redact or discard

Do not report these values in ordinary person OSINT, even when incidentally
visible on a public page:

- home or residential address and precise neighbourhood;
- personal phone, personal email, government identifiers, or license plates;
- family, partners, relatives, children, or private-life images;
- medical, mental-health, personal-financial, immigration, sexual-orientation,
  or other sensitive status;
- exact schedule, travel pattern, calendar, or real-time whereabouts;
- leaked credentials, tokens, sessions, or other secrets.

Where possible, classify and discard such values before prompts, caches,
embeddings, raw notes, or ledger persistence. Record only the redaction class
and reason. A public city of work, official financial disclosure, or political
affiliation may be reported only when directly relevant to a public role and
anchored to the authoritative disclosure.

## Hard stops

Refuse or terminate the branch when:

- the subject is a minor;
- the framing suggests stalking, harassment, doxxing, violence, coercive debt
  collection, intimate-partner search, ex-partner search, or finding a home;
- the request seeks a full-life dossier on a private person for curiosity or a
  weaponizable purpose;
- the user requests real-time location or sensitive personal fields;
- the task asks to re-identify a pseudonym the subject has not self-disclosed;
- useful evidence requires private accounts, DMs, gated groups, paywall/login
  bypass, captcha evasion, leaked credentials, or raw leak dumps.

A source being publicly reachable does not override these hard stops.

## Workflow

1. **Restate.** Define subject, purpose, timeframe, geography, language,
   audience, and prohibited data classes.
2. **Classify.** Assign subject class and `R2` scope; run hard stops.
3. **Resolve a canonical anchor.** Prefer official bio, ORCID, organization
   page, verified public profile, authored artifact, or Wikidata Q-ID.
4. **Build aliases.** Mark names, transliterations, handles, domains, and IDs as
   verified or tentative with their anchor evidence.
5. **Disambiguate.** Enumerate homonyms and require positive signals such as
   the same work, affiliation, handle, location context, or time period.
6. **Decompose.** Split role, works, statements, relationships, timeline, and
   contradiction questions.
7. **Map sources.** Use official pages, filings, registries, publications,
   code/package records, public social accounts, reputable reporting,
   archives, and relevant community leads.
8. **Fan out.** Search exact aliases, unique phrases, dates, organizations,
   authored artifacts, relationship anchors, and disconfirming evidence.
9. **Record evidence.** File one row per claim/source pair with subject class,
   speaker relation, source lineage, discovery disposition, reporting
   disposition, confidence, and contradiction.
10. **Build timeline and relationship graph.** Mark inferred links and disputed
    dates explicitly.
11. **Privacy filter.** Discard or redact inadmissible fields before synthesis.
12. **Synthesize.** Separate verified findings, non-official leads, identity
    ambiguities, contradictions, gaps, and confidence.

## Social and non-official sources

Public social research is permitted across relevant platforms. Apply
`references/social-source-research.md`; do not classify a platform as a whole.

An official account's own statement can be primary evidence. A stable
pseudonymous maintainer can be primary for their own public code decision but
not automatically linked to a real identity. Anonymous tips, reposts, gossip,
and screenshot-only claims remain in `Non-official / unverified leads`.

Never use a non-official source alone for identity, criminality, medical or
financial status, security exposure, precise location, a minor, or a
leak-derived claim.

## Saturation and expansion

Stop on scoped evidence saturation, not an absolute 25-row privacy cap. Default
to stopping after three consecutive independent sources add no new verified
claim, then apply the configured resource and risk budgets.

Frontier search may be used for unresolved **public-professional** evidence
gaps. It may not be used to chase personal contact, family, whereabouts,
sensitive status, private accounts, or a pseudonym's real identity.

If expansion crosses multiple life domains for a private person or increases
output actionability, pause for scope review. A technical source cap remains a
resource ceiling and never establishes completeness.

## Output contract

1. subject identity and disambiguation status;
2. verified public roles and aliases;
3. public works, statements, filings, and professional relationships;
4. event timeline with status and contradictions;
5. `Non-official / unverified leads`;
6. redaction and blocked-source summary;
7. remaining identity risks, gaps, confidence, and stopping reason.

Do not call the output a complete profile. Call it a scoped public-evidence
report.

## Examples

In scope:

- verify an OSS maintainer's public projects, talks, and role-bound contact;
- map a public executive's board roles and filing-backed timeline;
- identify a paper author and their public affiliation;
- help a user audit their own public footprint, with sensitive fields redacted;
- investigate conflicting public claims about a spokesperson's role.

Out of scope:

- find an ex-partner's address, phone, family, schedule, or private accounts;
- identify the real person behind a non-self-disclosed pseudonym;
- compile every image or social interaction of a private person;
- monitor a person's live location;
- use a leaked database to enrich a private-person profile.

## See also

- `references/investigative-research.md`
- `references/social-source-research.md`
- `references/self-exposure-audit.md`
- `references/leaked-data-handling.md`
- `references/multilingual-research.md`
- `references/source-quality-rubric.md`
- `references/evidence-ledger.md`
