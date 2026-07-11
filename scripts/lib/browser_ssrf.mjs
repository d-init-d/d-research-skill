// Browser network boundary for arbitrary seed URLs.
// Fail-closed: private / link-local / loopback / metadata destinations are
// blocked before route.continue() so Chromium never issues the request.
// Local fixture tests may set D_RESEARCH_SSRF_ALLOW_LOOPBACK=1.

import { isNonPublicIp, resolvePublicIps } from './ssrf_guards.mjs';
import net from 'node:net';
import { pathToFileURL } from 'node:url';

const BLOCKED_HOSTNAMES = new Set([
  'localhost',
  'localhost.localdomain',
  'metadata.google.internal',
  'metadata',
  'instance-data',
]);

function normalizeHost(host) {
  let h = String(host || '')
    .toLowerCase()
    .replace(/\.$/, '')
    .trim();
  if (h.startsWith('[') && h.endsWith(']')) h = h.slice(1, -1);
  return h;
}

function isLoopbackHost(host) {
  const h = normalizeHost(host);
  if (h === 'localhost' || h.endsWith('.localhost')) return true;
  if (h === '::1') return true;
  if (net.isIPv4(h) && h.startsWith('127.')) return true;
  if (h === '0.0.0.0') return true;
  return false;
}

/**
 * Validate a browser-destined URL is public (or allowed loopback fixture).
 * @returns {Promise<{ok: true}|{ok: false, reason: string, blocker: object}>}
 */
export async function assertBrowserPublicUrl(url, opts = {}) {
  const allowLoopback =
    opts.allowLoopback === true || process.env.D_RESEARCH_SSRF_ALLOW_LOOPBACK === '1';
  let parsed;
  try {
    parsed = new URL(String(url || '').trim());
  } catch {
    return {
      ok: false,
      reason: 'invalid_url',
      blocker: structuredBlocker('invalid_url', `invalid browser URL: ${url}`),
    };
  }
  const scheme = (parsed.protocol || '').replace(/:$/, '').toLowerCase();
  if (scheme !== 'http' && scheme !== 'https') {
    return {
      ok: false,
      reason: 'scheme_not_allowed',
      blocker: structuredBlocker('scheme_not_allowed', `scheme not allowed: ${scheme}`),
    };
  }
  if (parsed.username || parsed.password) {
    return {
      ok: false,
      reason: 'userinfo_not_allowed',
      blocker: structuredBlocker('userinfo_not_allowed', 'URL userinfo is not allowed'),
    };
  }
  const host = normalizeHost(parsed.hostname);
  if (!host) {
    return {
      ok: false,
      reason: 'host_required',
      blocker: structuredBlocker('host_required', 'URL host is required'),
    };
  }
  if (BLOCKED_HOSTNAMES.has(host) || host.endsWith('.localhost')) {
    if (allowLoopback && isLoopbackHost(host)) {
      return { ok: true };
    }
    return {
      ok: false,
      reason: 'blocked_hostname',
      blocker: structuredBlocker('blocked_hostname', `blocked hostname: ${host}`, { host }),
    };
  }
  if (allowLoopback && isLoopbackHost(host)) {
    return { ok: true };
  }
  if (net.isIP(host)) {
    if (isNonPublicIp(host)) {
      return {
        ok: false,
        reason: 'non_public_ip',
        blocker: structuredBlocker('non_public_ip', `non-public IP not allowed: ${host}`, {
          host,
        }),
      };
    }
    return { ok: true };
  }
  try {
    await resolvePublicIps(host);
    return { ok: true };
  } catch (e) {
    return {
      ok: false,
      reason: 'ssrf_dns_or_private',
      blocker: structuredBlocker(
        'ssrf_dns_or_private',
        String(e.message || e),
        { host },
      ),
    };
  }
}

export function structuredBlocker(code, message, extra = {}) {
  return {
    status: 'blocked',
    blocker: true,
    code,
    message,
    incomplete: true,
    complete: false,
    silent_skip: false,
    ...extra,
  };
}

/**
 * Install page.route handler that denies non-public destinations for every
 * request class (navigation, iframe, subresource, xhr, websocket upgrade).
 * Returns a stats object mutated as requests are seen/blocked.
 */
export async function installBrowserSsrfGuard(page, opts = {}) {
  const stats = {
    allowed: 0,
    blocked: 0,
    blockedUrls: [],
    zeroRequestDenials: [],
  };
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = request.url();
    // Allow data:/blob:/about: for empty documents
    if (/^(data:|blob:|about:)/i.test(url)) {
      await route.continue();
      return;
    }
    const check = await assertBrowserPublicUrl(url, opts);
    if (!check.ok) {
      stats.blocked += 1;
      stats.blockedUrls.push({ url, reason: check.reason });
      stats.zeroRequestDenials.push(url);
      await route.abort('blockedbyclient');
      return;
    }
    stats.allowed += 1;
    // Caller may wrap additional robots policy; this guard only does SSRF.
    if (typeof opts.onAllowed === 'function') {
      await opts.onAllowed(route, request);
      return;
    }
    await route.continue();
  });
  return stats;
}

export async function selfTest() {
  const errors = [];
  for (const bad of [
    'http://127.0.0.1/x',
    'https://169.254.169.254/latest/',
    'https://192.168.0.1/',
    'https://[::1]/',
  ]) {
    const r = await assertBrowserPublicUrl(bad, { allowLoopback: false });
    if (r.ok) errors.push(`should block ${bad}`);
  }
  // Public literal should pass
  const good = await assertBrowserPublicUrl('https://8.8.8.8/', { allowLoopback: false });
  if (!good.ok) errors.push('public IP should be allowed');
  // Loopback fixture only when allowed
  const lb = await assertBrowserPublicUrl('http://127.0.0.1/x', { allowLoopback: true });
  if (!lb.ok) errors.push('loopback should pass when allowLoopback');
  if (errors.length) {
    console.error('browser_ssrf.mjs self-test FAILED:');
    for (const e of errors) console.error(`  - ${e}`);
    process.exitCode = 1;
    return 1;
  }
  console.log('browser_ssrf.mjs self-test ok');
  return 0;
}

const _isMain =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (_isMain && process.argv.includes('--self-test')) {
  selfTest();
}
