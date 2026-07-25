# Self-Exposure Audit

## Contents

- [Purpose](#purpose)
- [Entry conditions](#entry-conditions)
- [Ownership and authorization](#ownership-and-authorization)
- [Source order](#source-order)
- [Audit workflow](#audit-workflow)
- [Output and retention](#output-and-retention)
- [Hard stops](#hard-stops)
- [See also](#see-also)

## Purpose

Use this route when a user wants to learn where identifiers, accounts, or
domains they own have appeared in public breach reporting or in a breach
intelligence service they are authorized to query.

The route returns exposure metadata and remediation. It is not a credential
recovery, secret-validation, data-broker, or third-party lookup service.

## Entry conditions

All must pass before any authorized breach-corpus query:

1. The requested identifiers belong to the user, an organization they control,
   or a client covered by explicit authorization.
2. Ownership or authorization is verified with an appropriate method.
3. The provider or corpus is lawfully available to the user for this purpose.
4. The scope lists tokenized identifiers or owned domains; raw identifiers may
   be supplied only to the verified provider query and must not be persisted in
   the ordinary workspace. Bulk victim discovery is not allowed.
5. Output, retention, and redaction controls are declared.

If verification fails, fall back to public breach reporting that does not
confirm whether a private identifier appears in a corpus.

## Ownership and authorization

Choose the least-invasive suitable proof:

| Identifier | Example proof |
|---|---|
| email address | signed challenge delivered to the address or provider-native verification |
| domain | DNS TXT challenge or file on an owned origin |
| public handle | platform OAuth or a nonce posted on the canonical profile |
| organization | administrator proof plus an owned-domain or provider contract anchor |
| incident-response corpus | case/contract identifier and authorization scope hash |

Do not ask a user to submit a password, token, cookie, session, MFA seed, or
private key as proof.

The scope manifest uses tier `R3`, subject `self` or an authorized
organization, authorization status `self_verified` or `authorized`, an allowed
tokenized entity or owned domain, and a non-empty scope hash. Use
`investigation_policy.py bind-authorization` so changes to targets, source
classes, access, retention, or audience invalidate the binding.

## Source order

Use sources in this order:

1. official incident or breach notifications;
2. public breach reporting and metadata services;
3. authorized provider APIs with identifier-minimizing queries;
4. data the affected user or organization lawfully supplies;
5. raw leak claims only as metadata leads to a lawful verification source.

Do not fetch or parse raw dumps from paste or leak forums. Do not test whether
stolen credentials still work.

## Audit workflow

1. **Restate scope.** List identifier classes and the intended recipient.
2. **Verify ownership.** Record method, timestamp, and authorization scope hash;
   do not store the challenge secret after verification.
3. **Run public-reporting pass.** Collect breach name, incident date, reporting
   date, affected organization, reported data classes, and source authority.
4. **Run authorized-provider pass.** Query only verified identifiers. Prefer
   k-anonymity, prefix, blinded, or provider-native minimum-disclosure paths.
5. **Minimize immediately.** Keep match status, breach identifier, exposed data
   classes, source record ID, and confidence. Drop raw values and unrelated
   records before persistence or model context.
6. **Cross-check.** Resolve stale breach names, duplicate incidents, conflicting
   dates, and provider/reporting discrepancies.
7. **Assess risk.** Base risk on exposed data class and recency, not on access to
   the secret value.
8. **Report remediation.** Recommend password rotation where reused, MFA,
   session revocation through the legitimate service, provider contact, or
   organization-specific incident response.
9. **Purge.** Delete temporary identifier material and enforce the declared
   retention deadline.

## Output and retention

The user-facing report may include:

- redacted identifier or owned domain;
- breach/incident name and dates;
- exposed data classes such as email, password hash, phone, address, or IP;
- source and verification status;
- confidence, caveats, and remediation.

It must not include:

- plaintext secrets, reusable hashes, tokens, cookies, sessions, or keys;
- raw breach rows or download locations;
- unrelated victims' records;
- enough data to reconstruct the underlying corpus.

Default the audit report to a named recipient and three-day retention. The
validator caps `R3` retention at 30 days; use the shortest period the incident
or provider contract permits.
Provider-side logs follow the provider contract, and that limitation belongs in
the report.

## Hard stops

Stop and refuse when:

- the user cannot verify ownership or authorization;
- the request targets another person's email, phone, account, or credentials;
- the only path requires a raw leak dump or stolen-secret processing;
- the user asks to reveal, recover, validate, or try a secret;
- the request expands from an owned domain to unrelated people;
- the output would expose other victims.

## See also

- `references/leaked-data-handling.md`
- `references/investigative-research.md`
- `references/safety-and-access-policy.md`
- `templates/investigation-scope.json`
