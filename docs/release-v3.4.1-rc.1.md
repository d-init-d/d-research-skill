# D Research v3.4.1-rc.1

## v3.4.1-rc.1 Release Notes

D Research v3.4.1-rc.1 is a focused compatibility candidate that makes the
public contract match the product's existing capability surface. D Research is
read-only by default, while explicit, user-authorized archival and API mutation
operations remain available through dedicated commands or
`--intent archive|mutation`.

The executable network behavior is unchanged from v3.4.0. This candidate
corrects stale absolute read-only wording and makes that correction
machine-enforced so downstream agents can reliably discover the full supported
surface.

## Product impact

### Accurate capability discovery

- `SKILL.md`, `AGENTS.md`, `README.md`, and `README.vi.md` now state one
  consistent access model: read-only by default, with explicit archival and
  authorized API mutation available.
- Existing GET/query behavior, Wayback save behavior, POST/PUT/PATCH/DELETE
  construction, intent labels, redirect controls, retry defaults, and
  credential handling remain unchanged.
- Downstream consumers no longer need to choose between contradictory product
  prose and the executable API/archival interfaces.

### Contract-level regression protection

- `scripts/check_contract.py` now verifies the access-model statement across
  all public entry documents.
- Negative self-tests reject both historical absolute read-only assertions and
  future wording that omits `--intent archive|mutation`.
- The social snapshot self-test now uses a bounded resolver seam for known
  mocked fixture hosts, so filtered DNS cannot turn an offline test into a false
  failure; private-target SSRF cases still exercise the production resolver.
- The v3.4.0 capability baseline remains active, so commands, flags, routes,
  references, scripts, templates, ledger widths, record types, and recorded
  defaults must remain a superset.

## Compatibility

| Surface | v3.4.1-rc.1 contract |
|---|---|
| Python | 3.10 or newer |
| Node.js | 18 or newer |
| Playwright | 1.61.1, unchanged |
| Existing API GET usage | Preserved, including default max pages `10` |
| Authorized API mutation | Existing POST/PUT/PATCH/DELETE surface preserved |
| Archival commands | Existing explicit save/submission surface preserved |
| Evidence ledgers | Exact 14/19/22/23/37-column formats remain supported |
| Record types | `claim`, `lead`, `process`, and `blocker` remain supported |
| Artifact profiles | Capability-complete `full` plus additive `runtime` |
| Mandatory Python dependencies | None added |

## Upgrade guidance

No migration is required. Existing configuration and command lines continue to
work unchanged. Integrators that previously treated the prose phrase
"read-only" as a capability prohibition should instead follow the explicit
command/intent contract and require clear user authorization for archival or API
mutation operations.

## Candidate verification

The signed candidate must pass the complete source and runtime self-tests,
contract negative fixtures, documentation examples, internal routing checks,
package allowlist, deterministic dual-artifact build, acceptance suite,
dependency audit, and the v3.4.0 monotonic-capability baseline.

Stable v3.4.1 promotion remains restricted to lifecycle metadata, documentation,
the generated interop package version, and version-scoped release evidence. No
executable or policy-code change is permitted after the candidate is frozen.

## Scope assurance

- No capability or supported content category is removed.
- No new network restriction or opt-in requirement is introduced.
- No no-config default changes.
- No historical tag or release is rewritten.
