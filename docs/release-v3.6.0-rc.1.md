# D Research v3.6.0-rc.1

## v3.6.0-rc.1 Release Notes

Local candidate; official upstream attestation is unavailable.

Search supports validated host-result artifacts and provider fallback with honest
blocked/error/empty statuses. Host/MCP tools are invoked by the agent host, not
by Node scripts. Every search transport uses DNS-pinned public HTTP and peer
checks, including when global fetch is wrapped. Offline fixtures explicitly use
the test connector seam.

CDP attachment is opt-in, loopback by default, with ownership limited to task
pages and descendants. RAM/latency observations are fixture-specific and are not
guaranteed percentages. This candidate has no official upstream attestation.

See [candidate contract](upgrade-completion.md) and run `npm run acceptance`.
