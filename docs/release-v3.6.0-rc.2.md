# D Research v3.6.0-rc.2

## v3.6.0-rc.2 Release Notes

## Search failures you can diagnose. Browser sessions you can control.

D Research 3.6 adds a search gateway with explicit failure semantics and an
optional connector for reusing a research browser over CDP. This prerelease
includes the security and integrity fixes from the upgrade review. It retains
the evidence-backed documentary and social workflows introduced in 3.5.

This is the first published 3.6 candidate. The earlier `3.6.0-rc.1` snapshot was
local and was not published as a GitHub Release. Stable 3.5.0 remains the default
release while this candidate receives operational evaluation.

### Highlights

- **Honest search outcomes.** Blocked pages, malformed provider responses,
  changed result markup, and exhausted fallback chains cannot silently become
  successful empty searches. Status, provenance, and diagnostic information
  distinguish discovery failures from genuine empty results.
- **Host search integration without hidden tool calls.** Agents can use their
  host-native or MCP search tools and import validated result artifacts. The
  Node helper verifies query, provenance, and timestamps; it does not attempt
  to invoke arbitrary host tools by name. Configured provider adapters and
  bounded HTML fallback remain available.
- **Public-network transport enforcement.** Search requests, including
  redirects, pass through DNS-pinned public HTTP and connected-peer checks.
  Wrapping global `fetch` cannot bypass this boundary. Private IPv4, IPv6,
  mapped loopback addresses, and DNS rebinding are rejected before collection.
- **Opt-in CDP browser reuse.** The connector owns task pages and their popup
  descendants, blocks unsafe task requests, and releases task pages while
  preserving existing user tabs. Loopback is the default connection boundary.
- **Measured browser resource accounting.** Benchmarks report new task
  processes, RSS, changes to existing browser processes, and surviving PIDs.
  Missing measurements and cleanup failures fail explicitly.

### Upgrade guidance

Use `d-research-3.6.0-rc.2-runtime.tar.gz` for normal installation or
`d-research-3.6.0-rc.2-full.tar.gz` for development and validation. The separate
`d-research-skill-v3.6.0-rc.2.tar.gz` is the immutable tagged Git source archive.
Verify checksums before extraction, and extract into a new directory.

Keep existing research workspaces and receipts intact. Ledger formats
14/19/22/23/37 and the existing research routes remain supported. Integrations
must handle blocked/error statuses and preserve activity logs, captures,
coverage decisions, and limitations instead of treating discovery as evidence.

For CDP, use a dedicated research browser profile. Connecting to a browser
session does not create a privacy boundary for the entire profile and does not
bypass login walls, CAPTCHAs, paywalls, or site access controls.

### Compatibility

| Component | Support |
|---|---|
| Python | 3.10 or newer |
| Node.js | 18 or newer |
| Optional browser | Playwright 1.61.1; browser binaries installed separately |
| Ledgers | Existing 14/19/22/23/37-column contracts |
| Distribution | Runtime, full, and tagged Git source archives |
| Mandatory Python dependencies | No new dependency |

### Validation and known limits

Local verification passed the complete self-test suite, 48 search checks,
34 acceptance cases with real Chromium, adversarial transport regressions,
and deterministic full/runtime build and relocated extraction checks.
GitHub Actions additionally verifies the exact source commit through the
repository's lint, Node/Python, optional-backend, and browser integration jobs.
Consult the linked workflow results for their final status.

Offline provider fixtures establish contract and failure handling. They do not
establish current availability of every live search provider. CDP latency and
RAM measurements are environment-specific; no universal savings percentage,
platform access guarantee, or factual-accuracy score is claimed. Independent
live host comparisons remain a requirement for stable promotion.

### Verify your download

Download the release assets into one directory and run:

```sh
sha256sum -c SHA256SUMS

gh attestation verify d-research-skill-v3.6.0-rc.2.tar.gz \
  --repo d-init-d/d-research-skill \
  --signer-workflow d-init-d/d-research-skill/.github/workflows/release-attest.yml
```

The source attestation binds the tagged Git source archive. Full/runtime
profiles have their own file manifests and SHA-256 checksums; the source
attestation does not attest those profile archives.

After extraction, run `npm run self-test` and `npm run acceptance` from the
full profile. Browser installation remains a separate capability step.

The existing **CC BY-NC 4.0** license is unchanged.

**Full changelog:** [v3.5.0...v3.6.0-rc.2](https://github.com/d-init-d/d-research-skill/compare/v3.5.0...v3.6.0-rc.2)
