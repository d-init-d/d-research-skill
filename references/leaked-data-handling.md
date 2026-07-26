# Leaked-Data Handling

## Contents

- [Principle](#principle)
- [Decision matrix](#decision-matrix)
- [Labeling is not authorization](#labeling-is-not-authorization)
- [Lead handling](#lead-handling)
- [Authorized corpus handling](#authorized-corpus-handling)
- [Output controls](#output-controls)
- [Incident response](#incident-response)
- [See also](#see-also)

## Principle

Public availability does not by itself establish lawful custody, permission to
process, reliability, or permission to redistribute. Preserve research value
by separating breach reporting, authorized corpora, affected-user data, raw
leak claims, and stolen secrets.

This route never authorizes access-control bypass or acquisition of a leak. It
governs material encountered through otherwise lawful, read-only research or
provided under a verified incident-response/self-audit scope.

## Decision matrix

| Source class | Discovery | Evidence | Reporting |
|---|---|---|---|
| `public_reporting` | permitted | permitted with ordinary source-quality checks | cite the reporting source and provenance chain |
| `authorized_provider` | permitted inside scope | conditional evidence | summarize or aggregate; no bulk export |
| `user_provided_private` | permitted for affected user/organization | conditional evidence | scoped confidential output only |
| `raw_leak_lead_only` | metadata lead only | not admissible alone | state that a claim exists; do not link or quote raw material |
| `prohibited_secret` | prohibited | prohibited | prohibited |

Examples of `prohibited_secret` include passwords, tokens, cookies, sessions,
MFA seeds, private keys, and other material that can directly authorize an
action. Do not retain, test, validate, transform for later recovery, or place
it in model context.

## Labeling is not authorization

A `leaked source` label is required when relevant but never sufficient. Every
admissible leak-derived claim also needs:

- source-access class and provenance lineage;
- lawful/authorization basis and scope when not ordinary public reporting;
- acquisition method and access date;
- data-minimization decision;
- discovery and reporting disposition;
- confidence and contradiction state;
- redaction class and retention deadline;
- intended audience and redistribution limits.

Unknown legality or custody means do not acquire or extract the corpus. Seek an
official notification, reputable reporting, an authorized provider, or a
manual legal/privacy review.

## Lead handling

A raw leak claim may create a lead only when:

- the claim is publicly visible without login or bypass;
- the agent does not fetch the linked dump or secret material;
- the lead identifies a lawful verification target, such as an affected
  organization, regulator notice, incident advisory, or authorized provider;
- the ledger records `raw_leak_lead_only`, `lead_only`, and
  `non_official_lead` or `blocked` dispositions;
- no raw row, victim identifier, secret, or direct download location appears in
  the report.

Search snippets and reposts may locate the lead but do not verify its contents.
If no lawful verification source is reachable, report an unresolved lead and
stop.

## Authorized corpus handling

An authorized corpus can be used only when:

1. the user or organization has lawful custody or provider access;
2. the research purpose is within that authorization;
3. the target scope is explicit and auditable;
4. read-only and minimum-disclosure queries are available;
5. unrelated records can be excluded before model context or persistence;
6. retention and output controls are documented.

Prefer provider record IDs, aggregate counts, match booleans, and exposed data
classes over raw field values. Do not copy a provider corpus into the research
workspace unless the provider contract and scope explicitly require it; even
then, use an approved secure data environment rather than an ordinary report
workspace.

## Output controls

Leak-derived output must:

- cite the public report or authorized provider, not a raw dump URL;
- distinguish incident date, reporting date, and access date;
- state which data classes were reportedly exposed without reproducing values;
- redact or omit personal identifiers unless the verified self-audit requires
  a redacted identifier for clarity;
- exclude unrelated victims;
- separate unresolved raw-leak leads from verified findings;
- include retention, confidence, and blocker notes.

## Incident response

For an affected organization, use tier `R4` with an authorization scope hash
or `R3` for an owned-identifier audit. The skill may analyze lawfully supplied
incident evidence, public threat intelligence, and remediation options. It may
not test credentials, access attacker or victim accounts, deploy payloads, or
take down infrastructure.

## See also

- `references/self-exposure-audit.md`
- `references/investigative-research.md`
- `references/evidence-ledger.md`
- `references/source-quality-rubric.md`
- `references/safety-and-access-policy.md`
