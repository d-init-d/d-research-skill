// Verify that wrapping native fetch does not disable pre-socket DNS policy.
// Only an audit-owned loopback server and process-local DNS hooks are used.
import dns from 'node:dns';
import http from 'node:http';
import path from 'node:path';
import { syncBuiltinESMExports } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const { fetchWithManualRedirects } = await import(pathToFileURL(path.join(root, 'scripts/web_search.mjs')));
const { setTestDnsResolver } = await import(pathToFileURL(path.join(root, 'scripts/lib/ssrf_guards.mjs')));
const originalFetch = globalThis.fetch;
const originalLookup = dns.lookup;
const hostname = 'audit-round5-controlled.example';
let hits = 0;
const checks = [];
const server = http.createServer((_request, response) => {
  hits += 1;
  response.end('Audit-owned fixture; no personal or external data.');
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
try {
  const control = await originalFetch(`http://127.0.0.1:${server.address().port}/control`);
  await control.text();
  checks.push({ check: 'owned_fixture_available', passed: control.status === 200 && hits === 1 });
  dns.lookup = function lookup(host, options, callback) {
    if (host !== hostname) return originalLookup.apply(this, arguments);
    if (typeof options === 'function') { callback = options; options = {}; }
    queueMicrotask(() => options?.all
      ? callback(null, [{ address: '127.0.0.1', family: 4 }])
      : callback(null, '127.0.0.1', 4));
  };
  syncBuiltinESMExports();
  setTestDnsResolver(async host => {
    if (host === hostname) return ['127.0.0.1'];
    throw new Error(`Unexpected fixture host: ${host}`);
  });
  const url = `http://${hostname}:${server.address().port}/private`;
  for (const wrapped of [false, true]) {
    // A transparent native-fetch wrapper models logging/instrumentation, not a mock response.
    globalThis.fetch = wrapped ? (...args) => originalFetch(...args) : originalFetch;
    const before = hits;
    let error = null;
    let status = null;
    try {
      const response = await fetchWithManualRedirects(url, { method: 'GET' }, 3000);
      status = response.status;
      await response.text();
    } catch (caught) { error = caught.message; }
    checks.push({
      check: wrapped ? 'wrapped_native_fetch_keeps_private_dns_guard' : 'native_fetch_private_dns_guard_control',
      plan: 'FX07.08/FX07.10/FX07.15',
      passed: Boolean(error) && hits === before,
      private_requests_received: hits - before,
      actual_status: status,
      actual_error: error,
    });
  }
} finally {
  globalThis.fetch = originalFetch;
  dns.lookup = originalLookup;
  syncBuiltinESMExports();
  setTestDnsResolver(null);
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
}
const passed = checks.filter(check => check.passed).length;
console.log(JSON.stringify({ ok: passed === checks.length, passed, failed: checks.length - passed, checks }, null, 2));
process.exitCode = passed === checks.length ? 0 : 1;
