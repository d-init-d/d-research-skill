// Browser network boundary for arbitrary seed URLs.
// Fail-closed: private / link-local / loopback / metadata destinations never
// reach Chromium's network stack. Public HTTP(S) requests are fulfilled through
// the Node SSRF helper, which validates DNS and binds the TCP peer.

import {
  HttpResourceLimitError,
  fetchPublicHttp,
  isNonPublicIp,
  resolvePublicIps,
} from './ssrf_guards.mjs';
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
  const allowLoopback = opts.allowLoopback === true;
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

function routeTarget(target) {
  if (target && typeof target.route === 'function' && typeof target.newPage === 'function') {
    return target;
  }
  const context = target?.context?.();
  if (context && typeof context.route === 'function') return context;
  throw new Error('installBrowserSsrfGuard requires a BrowserContext or Page');
}

function requestHeadersForNode(request) {
  const headers = { ...request.headers() };
  for (const key of Object.keys(headers)) {
    const lower = key.toLowerCase();
    if (
      lower === 'host' ||
      lower === 'connection' ||
      lower === 'content-length' ||
      lower === 'proxy-authorization' ||
      lower === 'proxy-authenticate' ||
      lower === 'upgrade'
    ) {
      delete headers[key];
    }
  }
  headers['accept-encoding'] = 'identity';
  return headers;
}

function responseHeadersForBrowser(response) {
  const headers = {};
  response.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (
      lower === 'connection' ||
      lower === 'content-length' ||
      lower === 'keep-alive' ||
      lower === 'proxy-authenticate' ||
      lower === 'proxy-authorization' ||
      lower === 'te' ||
      lower === 'trailer' ||
      lower === 'transfer-encoding' ||
      lower === 'upgrade'
    ) {
      return;
    }
    headers[key] = value;
  });
  return headers;
}

async function responseBodyBuffer(response) {
  const arrayBuffer = await response.arrayBuffer();
  return Buffer.from(arrayBuffer);
}

function asResourceLimitPayload(error) {
  if (
    error instanceof HttpResourceLimitError ||
    error?.code === 'http_max_bytes' ||
    error?.code === 'invalid_http_max_bytes'
  ) {
    return {
      error: 'resource_limit',
      code: error.code || 'http_max_bytes',
      message: error.message || 'browser response exceeded byte limit',
      ...(error.details || {}),
      incomplete: true,
      complete: false,
    };
  }
  return null;
}

function positiveIntegerOr(value, fallback) {
  return Number.isSafeInteger(value) && value > 0 ? value : fallback;
}

function recordResourceLimit(stats, url, payload, reason) {
  const recorded = { url, ...payload };
  if (!stats.resourceLimit) stats.resourceLimit = recorded;
  stats.blocked += 1;
  stats.blockedUrls.push({ url, reason, ...payload });
}

/**
 * Install a context-level network guard. HTTP(S) requests are fulfilled via
 * fetchPublicHttp so Chromium never performs its own destination DNS/connect.
 * WebSockets are fail-closed because Playwright's server bridge is not pinned.
 *
 * @param {import('playwright').BrowserContext|import('playwright').Page} target
 * @param {{
 *   allowLoopback?: boolean,
 *   ignoreTlsErrors?: boolean,
 *   maxResponseBytes?: number|null,
 *   maxTotalResponseBytes?: number|null,
 *   maxRequests?: number|null,
 *   timeoutMs?: number,
 *   onAllowed?: Function
 * }} opts
 */
export async function installBrowserSsrfGuard(target, opts = {}) {
  const perResponseLimit = positiveIntegerOr(opts.maxResponseBytes, 20 * 1024 * 1024);
  const maxTotalResponseBytes = positiveIntegerOr(
    opts.maxTotalResponseBytes,
    perResponseLimit,
  );
  const maxRequests = positiveIntegerOr(opts.maxRequests, 100);
  const stats = {
    requests: 0,
    allowed: 0,
    fulfilled: 0,
    responseBytes: 0,
    maxRequests,
    maxTotalResponseBytes,
    blocked: 0,
    blockedUrls: [],
    zeroRequestDenials: [],
    resourceLimit: null,
    websocketBlocked: 0,
  };
  const context = routeTarget(target);

  if (typeof context.routeWebSocket === 'function') {
    await context.routeWebSocket(() => true, async (ws) => {
      const rawUrl = ws.url();
      const httpUrl = rawUrl.replace(/^ws:/i, 'http:').replace(/^wss:/i, 'https:');
      const check = await assertBrowserPublicUrl(httpUrl, opts);
      stats.websocketBlocked += 1;
      stats.blocked += 1;
      stats.blockedUrls.push({
        url: rawUrl,
        reason: check.ok ? 'websocket_guard_fail_closed' : check.reason,
      });
      await ws.close({ code: 1008, reason: 'D Research browser network guard' });
    });
  }

  await context.route('**/*', async (route) => {
    const request = route.request();
    const url = request.url();
    // Allow browser-internal non-network documents.
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

    const method = String(request.method() || '').toUpperCase();
    if (method !== 'GET' && method !== 'HEAD') {
      stats.blocked += 1;
      stats.blockedUrls.push({ url, reason: 'read_only_method_required', method });
      await route.abort('blockedbyclient');
      return;
    }

    stats.requests += 1;
    if (stats.requests > maxRequests) {
      const payload = asResourceLimitPayload(
        new HttpResourceLimitError(
          'browser_max_requests',
          `browser request count exceeds ${maxRequests}`,
          { limit: maxRequests, actual: stats.requests },
        ),
      );
      recordResourceLimit(stats, url, payload, 'request_count_resource_limit');
      await route.fulfill({
        status: 429,
        headers: { 'content-type': 'text/plain; charset=utf-8' },
        body: `D Research resource limit: ${payload.message}`,
      });
      return;
    }

    if (typeof opts.onAllowed === 'function') {
      const decision = await opts.onAllowed(route, request, stats);
      if (decision && decision.action === 'abort') {
        stats.blocked += 1;
        stats.blockedUrls.push({ url, reason: decision.reason || 'policy_blocked' });
        await route.abort(decision.errorCode || 'blockedbyclient');
        return;
      }
    }

    stats.allowed += 1;
    let timer = null;
    try {
      const timeoutMs =
        Number.isSafeInteger(opts.timeoutMs) && opts.timeoutMs > 0 ? opts.timeoutMs : 30000;
      const controller = new AbortController();
      timer = setTimeout(() => controller.abort(), timeoutMs);
      const response = await fetchPublicHttp(
        url,
        {
          method,
          headers: requestHeadersForNode(request),
          body: request.postDataBuffer?.() || undefined,
          signal: controller.signal,
          maxResponseBytes: opts.maxResponseBytes ?? null,
          bodyTimeoutMs: timeoutMs,
        },
        {
          allowHttp: true,
          allowLoopback: opts.allowLoopback === true,
          ignoreTlsErrors: opts.ignoreTlsErrors === true,
        },
      );
      try {
        const body = await responseBodyBuffer(response);
        const totalAfterResponse = stats.responseBytes + body.length;
        if (totalAfterResponse > maxTotalResponseBytes) {
          throw new HttpResourceLimitError(
            'browser_total_max_bytes',
            `browser aggregate response bytes exceed ${maxTotalResponseBytes}`,
            {
              limit: maxTotalResponseBytes,
              actual: totalAfterResponse,
            },
          );
        }
        stats.responseBytes = totalAfterResponse;
        await route.fulfill({
          status: response.status,
          headers: responseHeadersForBrowser(response),
          body,
        });
        stats.fulfilled += 1;
      } finally {
        if (timer) clearTimeout(timer);
        timer = null;
      }
    } catch (error) {
      if (timer) clearTimeout(timer);
      const limitPayload = asResourceLimitPayload(error);
      if (limitPayload) {
        recordResourceLimit(
          stats,
          url,
          limitPayload,
          request.isNavigationRequest()
            ? 'navigation_resource_limit'
            : 'subresource_resource_limit',
        );
        await route.fulfill({
          status: 413,
          headers: { 'content-type': 'text/plain; charset=utf-8' },
          body: `D Research resource limit: ${limitPayload.message}`,
        });
        return;
      }
      stats.blocked += 1;
      stats.blockedUrls.push({
        url,
        reason: 'guard_fetch_failed',
        error: String(error?.message || error),
      });
      await route.abort('failed');
    }
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
  const savedLoopbackEnv = process.env.D_RESEARCH_SSRF_ALLOW_LOOPBACK;
  process.env.D_RESEARCH_SSRF_ALLOW_LOOPBACK = '1';
  const envBypass = await assertBrowserPublicUrl('http://127.0.0.1/x');
  if (envBypass.ok) errors.push('loopback env must not bypass browser SSRF guard');
  if (savedLoopbackEnv === undefined) delete process.env.D_RESEARCH_SSRF_ALLOW_LOOPBACK;
  else process.env.D_RESEARCH_SSRF_ALLOW_LOOPBACK = savedLoopbackEnv;
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
