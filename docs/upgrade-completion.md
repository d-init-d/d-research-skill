# Search and browser candidate contract

Version `3.6.0-rc.2` is a prerelease candidate for evaluation before stable promotion.
Published release assets are bound to its immutable tag; this does not establish
live-provider availability or stable-release readiness.
Host search tools are called by the agent host. The Node search helper consumes
validated host-result artifacts or configured search engines; it cannot invoke
an arbitrary host/MCP tool by name. No API credentials are required for offline
contract tests, and those tests do not establish live provider availability.

All production search HTTP requests use `fetchPublicHttp`, including redirects,
DNS pinning and connected-peer checks. Replacing or wrapping global `fetch`
does not select a different transport. Offline tests explicitly use
`setSearchTestResponse(provider)` and reset it in cleanup; test DNS/connect
hooks exercise URL/address/peer validation and are not runtime fallback logic.

Browser CDP attachment is opt-in, loopback by default, and owns only task pages
and their descendants. Existing user tabs are not task inputs. CDP does not
bypass access controls or provide a privacy boundary for an entire personal
profile. Use a dedicated research profile/context where appropriate.

The benchmark reports new task-child RSS separately from total browser RSS and
growth of already-running browser processes. Measurement failures fail visibly;
missing measurements never become zero. Startup ratios and RAM savings depend
on the measured fixture/environment and have no guaranteed percentage.

```bash
node scripts/web_search.mjs --self-test
npm run self-test
npm run acceptance
node tests/test_browser_cdp_bench.mjs
python3 scripts/build_release_artifacts.py self-test
```
