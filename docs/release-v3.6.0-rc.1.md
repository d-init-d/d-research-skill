# D Research v3.6.0-rc.1

## v3.6.0-rc.1 Release Notes

## Host-Native Search Gateway and Chrome DevTools Protocol Connectivity

D Research 3.6-rc.1 introduces host-native search gateway abstractions and Chrome DevTools Protocol (CDP) connectivity, enabling high-performance research execution across agent environments.

### Highlights

- **Host-Native / MCP Search Gateway.** Flexible multi-provider gateway supporting native host integrations, MCP search tools, SearXNG, and direct web search with resilient fallback handling.
- **Chrome DevTools Protocol (CDP) Connector.** Enables reuse of existing user browser instances, reducing RAM consumption and navigating dynamic single-page applications without standalone headless browser overhead.
- **Strict Network & Loopback SSRF Guarding.** Robust endpoint validation blocking private IP ranges, cloud metadata services, and unverified loopback access.
- **Full Evidence Ledger Integrity.** Seamless integration with the 37-column evidence ledger schema, preserving full provenance, hash bindings, and execution receipts.
