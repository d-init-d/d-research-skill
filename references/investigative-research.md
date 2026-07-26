# Investigative Research

## Contents

- [Purpose](#purpose)
- [Capability tiers](#capability-tiers)
- [Minimum guardrails](#minimum-guardrails)
- [Scope manifest](#scope-manifest)
- [Autonomous investigation loop](#autonomous-investigation-loop)
- [Discovery, retention, and reporting](#discovery-retention-and-reporting)
- [Risk budget](#risk-budget)
- [Stopping criteria](#stopping-criteria)
- [Output contract](#output-contract)
- [See also](#see-also)

## Purpose

Use this route for deep OSINT, due diligence, public-interest investigation,
threat intelligence, authorized security research, entity resolution,
relationship mapping, hypothesis testing, and contradiction search.

The route maximizes research capability by replacing broad prohibitions and
fixed person/source caps with explicit scope, source-admissibility, privacy,
and output gates. It expands what the agent may discover and analyze; it never
expands the right to bypass access controls or act against a target.

Before source access, create or validate an investigation scope:

```bash
python scripts/investigation_policy.py init \
  --mode R1 \
  --out investigation-scope.json

python scripts/investigation_policy.py check \
  --file investigation-scope.json
```

For a long-horizon run, keep `investigation-scope.json` at the research
workspace root. For `R3`, `R4`, or reviewed-public-interest `R2`, first record
the review attestation and bind its canonical scope:

```bash
python scripts/investigation_policy.py bind-authorization \
  --file investigation-scope.json \
  --status self_verified \
  --method provider_native_verification \
  --reviewed-by account-owner \
  --reviewed-at <RFC3339-UTC-now> \
  --expires-at <RFC3339-UTC-expiry-within-mode-limit>
```

Then bind the exact policy bytes to the plan with `research_plan.py
bind-policy`. The command adds the scope to every research and synthesis task
input. A later
scope edit invalidates dispatch until the policy is rebound and the plan is
rendered and approved again. The hash proves scope integrity, not the truth of
the underlying authorization; keep the cited challenge, contract, case, or
review attestation outside the ordinary report workspace when it is sensitive.

## Capability tiers

| Tier | Name | Capability |
|---|---|---|
| `R0` | public research | Broad lawful public-web research with ordinary evidence gates. |
| `R1` | deep investigation | Entity and alias expansion, evidence graphs, timelines, hypotheses, contradiction search, and bounded frontier expansion. |
| `R2` | scoped person OSINT | Public-professional person research plus subject, privacy, and reporting gates. |
| `R3` | self-exposure audit | Verified user-owned identifiers and authorized breach-intelligence queries. |
| `R4` | authorized security | Threat intelligence, passive attack-surface research, and authorized assessment planning under a scope hash or Rules of Engagement. |
| `RX` | prohibited | Access bypass, stolen-secret use, minors targeting, stalking/doxxing, malware deployment, exfiltration, or unauthorized exploitation. |

Higher tiers add research capabilities. They never weaken `RX` boundaries.

Tier selection is based on the requested act and output, not the user's job
title. A security researcher without a target authorization stays in `R0` or
`R1`; a verified account owner running a self-audit uses `R3`.

## Minimum guardrails

These are method and harm boundaries, not limits on learning:

- Read-only by default; no mutation unless a separate workflow explicitly
  authorizes the exact side effect.
- Never bypass authentication, login walls, paywalls, captchas, rate limits,
  IP bans, robots restrictions, or private/gated channels.
- Never use stolen passwords, tokens, cookies, sessions, MFA material, or
  private keys for access, validation, or enrichment.
- Never target minors or support stalking, doxxing, harassment, violent
  targeting, intimate-partner searches, or real-time whereabouts tracking.
- Never deploy malware, establish persistence or C2, exfiltrate data, perform
  credential attacks, or exploit a system outside verified authorization.
- Never redistribute raw breach rows or unrelated victims' data.

When a request crosses one of these boundaries, stop the affected branch. Do
not downgrade it into a lead or hide it in an appendix.

## Scope manifest

The machine-readable scope records:

- capability tier and purpose category;
- subject class and canonical anchor;
- authorization state, method, and scope hash when required;
- allowed entities, domains, source-access classes, and data classes;
- crawl/source budgets and saturation threshold;
- read-only access invariants;
- output sections, redaction classes, retention, and audience.

`scripts/investigation_policy.py check` fails closed on:

- `read_only=false`, captcha/stealth enablement, or `respect_robots=false`;
- a minor as the research subject;
- prohibited-secret source classes;
- `R3` without verified ownership or authorization;
- `R4` without an authorization scope hash and an explicit target scope;
- a private-person scope that requests sensitive or secret data;
- missing mandatory redaction and output sections.

`R0` and `R1` cannot be used as a shortcut around person policy. Person targets
route through `R2`; owned identifiers route through `R3`. `R2` retains only
public/professional data, and private-person work requires authorization or a
time-bounded reviewed-public-interest attestation.

User-declared purpose is context, not proof of authorization. Use ownership
verification, an allowlist, a contract or case identifier, and a scope hash for
routes that require them.

## Autonomous investigation loop

1. **Intake.** Classify purpose, subject, tier, geography, time range,
   deliverable, and hard-stop risks.
2. **Scope.** Validate the scope manifest before opening sources.
3. **Resolve entities.** Build verified and tentative aliases, identifiers,
   canonical anchors, homonyms, and relationship candidates.
4. **Map sources.** Fan out official, primary, dataset, filing, code, archive,
   recent, community, social, and contradiction basins that are relevant.
5. **Probe least-invasively.** Prefer public files and APIs, then static HTML,
   then rendered browser content. Record blockers without escalation.
6. **Write evidence immediately.** File one row per claim/source pair and keep
   source lineage, speaker relationship, discovery disposition, and reporting
   disposition.
7. **Build the graph and timeline.** Mark inferred edges separately from
   directly supported relationships.
8. **Generate testable hypotheses.** State predicted evidence and a
   falsification query for each hypothesis.
9. **Search against the hypothesis.** Seek disconfirming evidence and record
   unresolved contradictions.
10. **Apply risk and saturation checks.** Expand the highest-value unresolved
    branch; stop low-value or high-risk branches.
11. **Filter before synthesis.** Remove or redact data that may have been
    encountered but is not admissible in output.
12. **Report in separate evidence sections.** Never mix verified findings and
    unverified leads.

## Discovery, retention, and reporting

Treat these as different permissions:

- **Discovery disposition** controls whether a source may open a search branch.
- **Retention disposition** controls whether a value may enter prompts, caches,
  embeddings, raw files, or the evidence ledger.
- **Reporting disposition** controls whether a claim appears in main findings,
  a lead section, a redacted form, or nowhere.

Sensitive values that are incidentally present on an otherwise lawful public
page should be classified and discarded before model context or persistence
when possible. Record `redaction_applied` or a redaction class, not the value.

## Risk budget

Evaluate every branch on five axes:

1. data sensitivity;
2. identifiability of the subject;
3. subject vulnerability;
4. aggregation scale;
5. actionability of the output.

Low-risk public-professional research may expand until evidence saturation.
Private-person, high-actionability, or sensitive-data branches consume the
risk budget quickly and require human review, scope reduction, redaction, or a
hard stop.

Do not use a fixed evidence-row count as the privacy boundary. Keep a technical
resource ceiling, but stop based on scoped saturation and risk. A configured
ceiling is never proof of completeness.

## Stopping criteria

Stop an investigation branch on the first applicable condition:

- all scoped sub-questions reach their target confidence;
- the configured number of consecutive sources adds no new verified claim;
- the branch exceeds its resource or risk budget;
- remaining sources require access-control bypass;
- an identity collision cannot be resolved with positive evidence;
- a material contradiction remains unresolved after the planned pass;
- further expansion would collect prohibited data or drift outside scope;
- the user withdraws authorization or changes the target scope.

Report reached sources, blocked sources, gaps, and why each branch stopped.

## Output contract

Investigative reports contain, in this order:

1. `Main findings`
2. `Non-official / unverified leads`
3. `Blocked / prohibited sources`
4. `Contradictions and unknowns`
5. `Confidence and stopping criteria`
6. `Next verification steps`

Main findings may use official, primary, firsthand, or independently
corroborated evidence. Leads remain visibly separate and state what evidence
would be required for promotion.

## See also

- `references/person-aggregation.md`
- `references/social-source-research.md`
- `references/self-exposure-audit.md`
- `references/leaked-data-handling.md`
- `references/source-quality-rubric.md`
- `references/evidence-ledger.md`
- `references/frontier-search.md`
- `templates/investigation-scope.json`
