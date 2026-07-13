#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import {
  browserResourceLimitErrorFromPayload,
  enforceBrowserOutputLimit,
  enforceBrowserResponseLimit,
  resolveBrowserResponseLimit,
  resourceLimitPayload,
  selfTestBrowserLimits,
} from './lib/browser_limits.mjs';
import {
  assertBrowserPublicUrl,
  installBrowserSsrfGuard,
} from './lib/browser_ssrf.mjs';
import { fetchPublicHttp } from './lib/ssrf_guards.mjs';

function parseArgs(argv) {
  const args = {
    seeds: [],
    outDir: 'research-output/crawl',
    maxDepth: 2,
    maxPages: 100,
    maxPagesPerDomain: 30,
    delayMs: 1000,
    timeout: 30000,
    maxResponseBytes: null,
    headless: true,
    respectRobots: true,
    followExternalLinks: false
  };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--help' || a === '-h') args.help = true;
    else if (a === '--self-test') args.selfTest = true;
    else if (a === '--seed') args.seeds.push(argv[++i]);
    else if (a === '--seeds') args.seedFile = argv[++i];
    else if (a === '--outDir') args.outDir = argv[++i];
    else if (a === '--maxDepth') args.maxDepth = Number(argv[++i]);
    else if (a === '--maxPages') args.maxPages = Number(argv[++i]);
    else if (a === '--maxPagesPerDomain') args.maxPagesPerDomain = Number(argv[++i]);
    else if (a === '--delayMs') args.delayMs = Number(argv[++i]);
    else if (a === '--timeout') args.timeout = Number(argv[++i]);
    else if (a === '--max-response-bytes') args.maxResponseBytes = Number(argv[++i]);
    else if (a === '--headful') args.headless = false;
    else if (a === '--no-respect-robots') {
      // Accepted only so we can explain the policy hard-fail.
      args.respectRobots = false;
      args.noRespectRobotsRequested = true;
    } else if (a === '--ignore-tls-errors') {
      args.ignoreTlsErrors = true;
    } else if (a === '--allow-loopback-fixture') {
      args.allowLoopbackFixture = true;
    } else if (a === '--follow-external-links') args.followExternalLinks = true;
    else throw new Error(`Unknown argument: ${a}`);
  }
  for (const [name, value, minimum] of [
    ['--maxDepth', args.maxDepth, 0],
    ['--maxPages', args.maxPages, 1],
    ['--maxPagesPerDomain', args.maxPagesPerDomain, 1],
    ['--delayMs', args.delayMs, 0],
    ['--timeout', args.timeout, 1],
  ]) {
    if (!Number.isSafeInteger(value) || value < minimum) {
      throw new Error(`${name} must be an integer >= ${minimum}`);
    }
  }
  args.maxResponseBytes = resolveBrowserResponseLimit(args.maxResponseBytes);
  return args;
}

function usage() {
  return `Usage: node scripts/playwright_crawl.mjs --seed <url> [--outDir crawl] [--maxDepth 2] [--maxPages 100]\n\nOptions:\n  --seed <url>              Seed URL, can be repeated\n  --seeds <file>            Newline-delimited seed URLs\n  --outDir <dir>            Output directory, default research-output/crawl\n  --maxDepth <n>            Max crawl depth, default 2\n  --maxPages <n>            Max total pages, default 100\n  --maxPagesPerDomain <n>   Max pages per domain, default 30\n  --delayMs <ms>            Delay between pages, default 1000\n  --timeout <ms>            Navigation timeout, default 30000\n  --max-response-bytes <n>  Maximum main-document body bytes (env: D_RESEARCH_HTTP_MAX_BYTES)\n  --headful                 Run with a visible browser\n  --ignore-tls-errors       Opt in to invalid TLS; recorded as a limitation\n  --no-respect-robots       Forbidden compatibility flag; always hard-fails\n  --follow-external-links   Allow external links in crawl queue\n  --self-test               Run lightweight checks without Playwright\n`;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function normalizeUrl(raw) {
  try {
    const u = new URL(raw);
    if (!['http:', 'https:'].includes(u.protocol)) return null;
    u.hash = '';
    return u.href;
  } catch {
    return null;
  }
}

function sameDomain(a, b) {
  try { return new URL(a).hostname === new URL(b).hostname; } catch { return false; }
}

function isLikelyBinary(url) {
  return /\.(pdf|csv|xlsx?|json|xml|docx?|zip|png|jpe?g|gif|webp|svg|mp4|mp3|avi|mov)(\?|#|$)/i.test(url);
}

async function loadSeeds(args) {
  const seeds = [...args.seeds];
  if (args.seedFile) {
    const text = await fs.readFile(args.seedFile, 'utf8');
    for (const line of text.split(/\r?\n/)) {
      const s = line.trim();
      if (s && !s.startsWith('#')) seeds.push(s);
    }
  }
  return [...new Set(seeds.map(normalizeUrl).filter(Boolean))];
}

// Product token used for browser context, robots.txt fetch, and rule selection.
const ROBOTS_UA_TOKEN = 'DResearchBot';
const ROBOTS_UA = 'dresearchbot';
const BROWSER_USER_AGENT =
  'Mozilla/5.0 (compatible; DResearchBot/3.2; +https://github.com/d-init-d/d-research-skill)';
const REDIRECT_STATUSES = new Set([301, 302, 303, 307, 308]);
const MAX_ROBOTS_BYTES = 1024 * 1024;

async function requestHeadersOnly(url, timeoutMs, ignoreTlsErrors, ssrfOpts = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchPublicHttp(
      url,
      {
        method: 'GET',
        headers: { 'User-Agent': BROWSER_USER_AGENT },
        signal: controller.signal,
      },
      {
        allowHttp: true,
        allowLoopback: ssrfOpts.allowLoopback === true,
        ignoreTlsErrors,
      },
    );
    try {
      await response.body?.cancel?.('headers-only preflight complete');
    } catch {
      /* ignore */
    }
    return {
      status: response.status || 0,
      location: response.headers.get('location'),
    };
  } catch (error) {
    if (error?.name === 'AbortError' || /aborted/i.test(String(error?.message || error))) {
      throw new Error(`redirect preflight timeout after ${timeoutMs}ms`);
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function requestTextBounded(
  startUrl,
  timeoutMs,
  ignoreTlsErrors,
  maxBytes,
  maxRedirects = 5,
  ssrfOpts = {}
) {
  let current = startUrl;
  for (let hop = 0; hop <= maxRedirects; hop++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    let result;
    try {
      const response = await fetchPublicHttp(
        current,
        {
          method: 'GET',
          headers: { 'User-Agent': BROWSER_USER_AGENT },
          signal: controller.signal,
          maxResponseBytes: maxBytes,
        },
        {
          allowHttp: true,
          allowLoopback: ssrfOpts.allowLoopback === true,
          ignoreTlsErrors,
        },
      );
      const status = response.status || 0;
      const location = response.headers.get('location');
      if (REDIRECT_STATUSES.has(status) && location) {
        try {
          await response.body?.cancel?.('robots redirect');
        } catch {
          /* ignore */
        }
        result = { status, location, text: '' };
      } else {
        result = { status, location: null, text: await response.text() };
      }
    } catch (error) {
      if (error?.code === 'http_max_bytes') {
        throw new Error(`robots.txt exceeds ${maxBytes} bytes`);
      }
      if (error?.name === 'AbortError' || /aborted/i.test(String(error?.message || error))) {
        throw new Error(`robots request timeout after ${timeoutMs}ms`);
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
    if (REDIRECT_STATUSES.has(result.status) && result.location) {
      current = new URL(result.location, current).href;
      continue;
    }
    return result;
  }
  throw new Error(`robots.txt exceeded ${maxRedirects} redirects`);
}

function parseRobots(text) {
  const groups = [];
  let current = null;
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.split('#')[0].trim();
    if (!line || !line.includes(':')) continue;
    const [kRaw, ...rest] = line.split(':');
    const key = kRaw.trim().toLowerCase();
    const value = rest.join(':').trim();
    if (key === 'user-agent') {
      const agent = value.toLowerCase();
      // Consecutive User-agent lines share one rule group.
      if (current && current.disallow.length === 0 && current.allow.length === 0) {
        current.agents.push(agent);
      } else {
        current = { agents: [agent], disallow: [], allow: [], sitemaps: [] };
        groups.push(current);
      }
    } else if (key === 'disallow' && current) current.disallow.push(value);
    else if (key === 'allow' && current) current.allow.push(value);
    else if (key === 'sitemap') {
      if (!current) {
        current = { agents: ['*'], disallow: [], allow: [], sitemaps: [] };
        groups.push(current);
      }
      current.sitemaps.push(value);
    }
  }
  return groups;
}

/**
 * Normalize URI octets for RFC 9309 matching.
 *
 * Percent-encoded ASCII unreserved octets compare as their decoded form;
 * reserved octets stay encoded (with canonical hex case), and raw non-ASCII
 * characters become their percent-encoded UTF-8 octets.
 */
function normalizeRobotsOctets(value) {
  const encodedUnicode = [...String(value || '')].map((character) => {
    if (character.codePointAt(0) <= 0x7f) return character;
    return [...Buffer.from(character, 'utf8')]
      .map((byte) => `%${byte.toString(16).toUpperCase().padStart(2, '0')}`)
      .join('');
  }).join('');
  return encodedUnicode.replace(/%([0-9a-f]{2})/gi, (_match, hex) => {
    const byte = Number.parseInt(hex, 16);
    const decoded = String.fromCharCode(byte);
    return /[A-Za-z0-9\-._~]/.test(decoded)
      ? decoded
      : `%${hex.toUpperCase()}`;
  });
}

function robotsRuleSpecificity(rule) {
  let normalized = normalizeRobotsOctets(rule);
  if (normalized.endsWith('$')) normalized = normalized.slice(0, -1);
  normalized = normalized.replace(/\*/g, '');
  return (normalized.match(/%[0-9A-F]{2}|[\s\S]/g) || []).length;
}

/** Match robots path rule with * wildcards and $ end-anchor (longest match). */
function robotsPathMatch(rule, pathName) {
  if (!rule) return false;
  let pattern = normalizeRobotsOctets(rule);
  let endAnchor = false;
  if (pattern.endsWith('$')) {
    endAnchor = true;
    pattern = pattern.slice(0, -1);
  }
  // Escape regex specials except *
  const escaped = pattern.replace(/[.+?^{}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*');
  const re = new RegExp('^' + escaped + (endAnchor ? '$' : ''));
  return re.test(normalizeRobotsOctets(pathName));
}

function robotsAllows(groups, targetUrl) {
  if (!groups || groups.status === 'disallow_all') return false;
  if (!groups || groups.status === 'unknown' || groups.status === 'rate_limited') return false;
  const list = Array.isArray(groups) ? groups : groups.rules || [];
  if (!list.length) return true; // no rules (404/410) => allow
  const u = new URL(targetUrl);
  const pathName = (u.pathname || '/') + (u.search || '');
  // Prefer DResearchBot group, then *
  let relevant = list.filter((g) => g.agents.includes(ROBOTS_UA));
  if (!relevant.length) relevant = list.filter((g) => g.agents.includes('*'));
  if (!relevant.length) return true;
  let matchedAllow = -1;
  let matchedDisallow = -1;
  for (const g of relevant) {
    for (const rule of g.allow) {
      const specificity = robotsRuleSpecificity(rule);
      if (rule && robotsPathMatch(rule, pathName) && specificity > matchedAllow) {
        matchedAllow = specificity;
      }
    }
    for (const rule of g.disallow) {
      const specificity = robotsRuleSpecificity(rule);
      if (rule && robotsPathMatch(rule, pathName) && specificity > matchedDisallow) {
        matchedDisallow = specificity;
      }
    }
  }
  if (matchedDisallow < 0) return true;
  return matchedAllow >= matchedDisallow;
}

async function getRobots(cache, url, ignoreTlsErrors = false, ssrfOpts = {}) {
  const origin = new URL(url).origin;
  if (cache.has(origin)) return cache.get(origin);
  try {
    const res = await requestTextBounded(
      `${origin}/robots.txt`,
      15000,
      ignoreTlsErrors,
      MAX_ROBOTS_BYTES,
      5,
      ssrfOpts
    );
    // 404/410: no robots rules
    if (res.status === 404 || res.status === 410) {
      const empty = { status: 'absent', rules: [] };
      cache.set(origin, empty);
      return empty;
    }
    // 401/403: treat as disallow
    if (res.status === 401 || res.status === 403) {
      const blocked = { status: 'disallow_all', rules: [] };
      cache.set(origin, blocked);
      return blocked;
    }
    // 429 / 5xx: unknown/rate_limited — stop crawl for domain
    if (res.status === 429 || res.status >= 500) {
      const limited = {
        status: res.status === 429 ? 'rate_limited' : 'unknown',
        rules: [],
      };
      cache.set(origin, limited);
      return limited;
    }
    if (res.status < 200 || res.status >= 300) {
      const limited = { status: 'unknown', rules: [] };
      cache.set(origin, limited);
      return limited;
    }
    const parsed = { status: 'ok', rules: parseRobots(res.text) };
    cache.set(origin, parsed);
    return parsed;
  } catch {
    const limited = { status: 'unknown', rules: [] };
    cache.set(origin, limited);
    return limited;
  }
}

async function robotsBlockReason(
  cache,
  domainStopped,
  url,
  ignoreTlsErrors = false,
  ssrfOpts = {}
) {
  const host = new URL(url).hostname;
  if (domainStopped.has(host)) return 'domain_stopped_robots_unknown';
  const groups = await getRobots(cache, url, ignoreTlsErrors, ssrfOpts);
  const status = groups && groups.status;
  if (status === 'rate_limited' || status === 'unknown') {
    domainStopped.add(host);
    return status === 'rate_limited' ? 'robots_rate_limited' : 'robots_unknown';
  }
  if (!robotsAllows(groups, url)) {
    return status === 'disallow_all' ? 'robots_auth_disallow' : 'robots_disallow';
  }
  return null;
}

async function resolveRedirectsBeforeNavigation(
  startUrl,
  robotsCache,
  domainStopped,
  timeoutMs,
  ignoreTlsErrors,
  ssrfOpts = {}
) {
  let current = startUrl;
  const seen = new Set();
  for (let hop = 0; hop <= 10; hop++) {
    if (seen.has(current)) {
      return { blocked: { url: current, reason: 'redirect_loop' } };
    }
    seen.add(current);

    const reason = await robotsBlockReason(
      robotsCache,
      domainStopped,
      current,
      ignoreTlsErrors,
      ssrfOpts
    );
    if (reason) return { blocked: { url: current, reason } };

    const response = await requestHeadersOnly(current, timeoutMs, ignoreTlsErrors, ssrfOpts);
    if (!REDIRECT_STATUSES.has(response.status) || !response.location) {
      return { url: current };
    }
    const next = normalizeUrl(new URL(response.location, current).href);
    if (!next) {
      return { blocked: { url: current, reason: 'invalid_redirect_location' } };
    }
    current = next;
  }
  return { blocked: { url: current, reason: 'too_many_redirects' } };
}

async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true });
}

async function writeJson(file, value) {
  await ensureDir(path.dirname(file));
  await fs.writeFile(file, JSON.stringify(value, null, 2) + '\n');
}

async function extractPage(page, url, response) {
  return await page.evaluate(() => {
    const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
    const abs = (href) => {
      try { return new URL(href, document.baseURI).href; } catch { return href || ''; }
    };
    const links = Array.from(document.querySelectorAll('a[href]')).slice(0, 1000).map((a) => ({
      text: clean(a.innerText || a.getAttribute('aria-label') || a.getAttribute('title') || ''),
      href: abs(a.getAttribute('href'))
    })).filter((x) => x.href);
    const headings = Array.from(document.querySelectorAll('h1,h2,h3')).slice(0, 100).map((h) => ({ level: h.tagName.toLowerCase(), text: clean(h.innerText) })).filter((h) => h.text);
    const files = links.filter((l) => /\.(pdf|csv|xlsx?|json|xml|docx?|zip|txt)(\?|#|$)/i.test(l.href));
    const text = clean(document.body ? document.body.innerText : '');
    return {
      title: document.title || '',
      canonicalUrl: document.querySelector('link[rel="canonical"]')?.href || '',
      language: document.documentElement.lang || '',
      headings,
      links,
      files,
      tableCount: document.querySelectorAll('table').length,
      textLength: text.length,
      textSample: text.slice(0, 3000)
    };
  });
}

async function run(args) {
  if (args.noRespectRobotsRequested || args.respectRobots === false) {
    throw new Error(
      'policy hard-fail: --no-respect-robots violates D Research safety policy ' +
        '(robots must be respected; the flag is accepted only to explain this error)'
    );
  }
  const seeds = await loadSeeds(args);
  if (!seeds.length) throw new Error('Provide at least one --seed URL');
  await ensureDir(args.outDir);
  await ensureDir(path.join(args.outDir, 'pages'));

  const { chromium } = await import('playwright');
  const browser = await chromium.launch({ headless: args.headless });
  const ignoreTls = Boolean(args.ignoreTlsErrors);
  const context = await browser.newContext({
    ignoreHTTPSErrors: ignoreTls,
    serviceWorkers: 'block',
    userAgent: BROWSER_USER_AGENT,
  });
  const page = await context.newPage();
  page.setDefaultTimeout(args.timeout);

  const queue = seeds.map((url) => ({ url, depth: 0, seed: url }));
  const seen = new Set();
  const perDomain = new Map();
  const robotsCache = new Map();
  const domainStopped = new Set();
  const manifest = [];
  const limitations = [];
  if (ignoreTls) {
    limitations.push('ignore_tls_errors_enabled');
  }
  const blocked = [];
  const limitReasons = new Set();
  const deferredByDepth = new Map();
  let navigationPolicyBlock = null;
  let resourceLimitExceeded = false;
  let pagesAttempted = 0;

  // Intercept every request at context scope:
  // 1) SSRF public-destination check + Node-pinned HTTP(S) fulfillment
  // 2) robots policy for main-frame navigations when --respect-robots
  const ssrfStats = await installBrowserSsrfGuard(context, {
    allowLoopback: args.allowLoopbackFixture === true,
    ignoreTlsErrors: ignoreTls,
    maxResponseBytes: args.maxResponseBytes,
    maxTotalResponseBytes: Math.min(
      args.maxResponseBytes * Math.max(1, args.maxPages),
      256 * 1024 * 1024,
    ),
    maxRequests: Math.min(Math.max(100, args.maxPages * 100), 10_000),
    timeoutMs: args.timeout,
    onAllowed: async (_route, request) => {
      if (
        !args.respectRobots ||
        !request.isNavigationRequest() ||
        request.frame() !== page.mainFrame()
      ) {
        return null;
      }

      const requestUrl = normalizeUrl(request.url());
      if (!requestUrl) {
        navigationPolicyBlock = { url: request.url(), reason: 'invalid_navigation_url' };
        return { action: 'abort', reason: 'invalid_navigation_url' };
      }
      const requestHost = new URL(requestUrl).hostname;
      let reason = null;
      if (domainStopped.has(requestHost)) {
        reason = 'domain_stopped_robots_unknown';
      } else {
        const groups = await getRobots(robotsCache, requestUrl, ignoreTls, {
          allowLoopback: args.allowLoopbackFixture === true,
        });
        const status = groups && groups.status;
        if (status === 'rate_limited' || status === 'unknown') {
          domainStopped.add(requestHost);
          reason = status === 'rate_limited' ? 'robots_rate_limited' : 'robots_unknown';
        } else if (!robotsAllows(groups, requestUrl)) {
          reason = status === 'disallow_all' ? 'robots_auth_disallow' : 'robots_disallow';
        }
      }

      if (reason) {
        navigationPolicyBlock = { url: requestUrl, reason };
        return { action: 'abort', reason };
      }
      return null;
    },
  });

  while (queue.length && pagesAttempted < args.maxPages) {
    const item = queue.shift();
    const url = normalizeUrl(item.url);
    if (!url || seen.has(url)) continue;
    seen.add(url);
    const host = new URL(url).hostname;
    const count = perDomain.get(host) || 0;
    if (count >= args.maxPagesPerDomain) {
      limitReasons.add('max_pages_per_domain');
      blocked.push({ url, reason: 'max_pages_per_domain', depth: item.depth });
      continue;
    }
    perDomain.set(host, count + 1);
    pagesAttempted++;
    const seedSsrf = await assertBrowserPublicUrl(url, {
      allowLoopback: args.allowLoopbackFixture === true,
    });
    if (!seedSsrf.ok) {
      blocked.push({
        url,
        reason: seedSsrf.reason || 'ssrf_private_or_internal',
        blocker: seedSsrf.blocker,
        depth: item.depth,
      });
      continue;
    }
    let navigationUrl = url;
    if (args.respectRobots) {
      let resolved;
      try {
        resolved = await resolveRedirectsBeforeNavigation(
          url,
          robotsCache,
          domainStopped,
          args.timeout,
          ignoreTls,
          { allowLoopback: args.allowLoopbackFixture === true }
        );
      } catch (error) {
        blocked.push({
          url,
          reason: 'redirect_preflight_error',
          error: String(error.message || error),
          depth: item.depth,
        });
        continue;
      }
      if (resolved.blocked) {
        blocked.push({
          ...resolved.blocked,
          depth: item.depth,
          via_redirect_from: resolved.blocked.url !== url ? url : undefined,
        });
        continue;
      }
      navigationUrl = resolved.url;
    }
    await sleep(args.delayMs);
    let response = null;
    navigationPolicyBlock = null;
    ssrfStats.resourceLimit = null;
    try {
      response = await page.goto(navigationUrl, {
        waitUntil: 'domcontentloaded',
        timeout: args.timeout,
        // Manual control is limited in Playwright; re-check final URL robots.
      });
      const routeLimit = browserResourceLimitErrorFromPayload(ssrfStats.resourceLimit);
      if (routeLimit) throw routeLimit;
      await enforceBrowserResponseLimit(
        response,
        args.maxResponseBytes,
        args.timeout,
      );
      const finalUrl = page.url();
      if (args.respectRobots && finalUrl && finalUrl !== navigationUrl) {
        const finalHost = new URL(finalUrl).hostname;
        if (domainStopped.has(finalHost)) {
          blocked.push({
            url: finalUrl,
            reason: 'domain_stopped_robots_unknown',
            depth: item.depth,
            via_redirect_from: url,
          });
          continue;
        }
        const finalGroups = await getRobots(robotsCache, finalUrl, ignoreTls, {
          allowLoopback: args.allowLoopbackFixture === true,
        });
        const finalStatus = finalGroups && finalGroups.status;
        if (finalStatus === 'rate_limited' || finalStatus === 'unknown') {
          domainStopped.add(finalHost);
          blocked.push({
            url: finalUrl,
            reason:
              finalStatus === 'rate_limited'
                ? 'robots_rate_limited'
                : 'robots_unknown',
            depth: item.depth,
            via_redirect_from: url,
          });
          continue;
        }
        if (!robotsAllows(finalGroups, finalUrl)) {
          blocked.push({
            url: finalUrl,
            reason:
              finalStatus === 'disallow_all'
                ? 'robots_auth_disallow'
                : 'robots_disallow',
            depth: item.depth,
            via_redirect_from: url,
          });
          continue;
        }
      }
      await page.waitForTimeout(500);
      const delayedRouteLimit = browserResourceLimitErrorFromPayload(
        ssrfStats.resourceLimit,
      );
      if (delayedRouteLimit) throw delayedRouteLimit;
      const data = await extractPage(page, url, response);
      const extractionRouteLimit = browserResourceLimitErrorFromPayload(
        ssrfStats.resourceLimit,
      );
      if (extractionRouteLimit) throw extractionRouteLimit;
      const record = {
        id: manifest.length + 1,
        inputUrl: url,
        finalUrl: page.url(),
        status: response ? response.status() : null,
        depth: item.depth,
        seed: item.seed,
        timestamp: new Date().toISOString(),
        ...data
      };
      enforceBrowserOutputLimit(record, args.maxResponseBytes, page.url());
      manifest.push(record);
      await writeJson(path.join(args.outDir, 'pages', `${String(record.id).padStart(4, '0')}.json`), record);
      for (const link of data.links) {
        const next = normalizeUrl(link.href);
        if (!next || seen.has(next) || isLikelyBinary(next)) continue;
        if (!args.followExternalLinks && !sameDomain(next, item.seed)) continue;
        if (item.depth < args.maxDepth) {
          queue.push({ url: next, depth: item.depth + 1, seed: item.seed });
        } else if (!deferredByDepth.has(next)) {
          deferredByDepth.set(next, {
            url: next,
            reason: 'max_depth',
            depth: item.depth + 1,
            discoveredFrom: page.url(),
          });
        }
      }
    } catch (err) {
      const limitPayload = resourceLimitPayload(err);
      if (limitPayload) {
        resourceLimitExceeded = true;
        blocked.push({
          url,
          reason: 'resource_limit',
          depth: item.depth,
          ...limitPayload,
        });
        if (
          limitPayload.code === 'browser_total_max_bytes' ||
          limitPayload.code === 'browser_max_requests'
        ) {
          break;
        }
      } else if (navigationPolicyBlock) {
        blocked.push({
          ...navigationPolicyBlock,
          depth: item.depth,
          via_redirect_from:
            navigationPolicyBlock.url !== url ? url : undefined,
        });
      } else {
        blocked.push({
          url,
          reason: 'navigation_error',
          error: String(err.message || err),
          depth: item.depth,
        });
      }
    }
  }

  await browser.close();
  const pendingByPageLimit = new Map();
  for (const item of queue) {
    const pendingUrl = normalizeUrl(item.url);
    if (!pendingUrl || seen.has(pendingUrl) || pendingByPageLimit.has(pendingUrl)) continue;
    pendingByPageLimit.set(pendingUrl, {
      url: pendingUrl,
      reason: 'max_pages',
      depth: item.depth,
    });
  }
  if (pendingByPageLimit.size > 0) {
    limitReasons.add('max_pages');
    blocked.push(...pendingByPageLimit.values());
  }

  const unresolvedDepth = [...deferredByDepth.values()].filter((row) => !seen.has(row.url));
  if (unresolvedDepth.length > 0) {
    limitReasons.add('max_depth');
    blocked.push(...unresolvedDepth);
  }
  if (resourceLimitExceeded) limitReasons.add('resource_limit');
  const limitsReached = [...limitReasons].sort();
  const stoppingReason = limitsReached.length === 0
    ? 'queue_exhausted'
    : limitsReached.length === 1
      ? limitsReached[0]
      : 'multiple_limits';
  const summary = {
    seeds,
    config: {
      maxDepth: args.maxDepth,
      maxPages: args.maxPages,
      maxPagesPerDomain: args.maxPagesPerDomain,
      delayMs: args.delayMs,
      respectRobots: true,
      followExternalLinks: args.followExternalLinks,
      ignoreTlsErrors: ignoreTls,
      maxResponseBytes: args.maxResponseBytes,
    },
    limitations,
    pagesAttempted,
    pagesVisited: manifest.length,
    blockedCount: blocked.length,
    complete: limitsReached.length === 0,
    resourceLimitExceeded,
    limitsReached,
    remainingQueueCount: pendingByPageLimit.size,
    deferredByDepthCount: unresolvedDepth.length,
    stoppingReason,
    generatedAt: new Date().toISOString()
  };
  await writeJson(path.join(args.outDir, 'manifest.json'), manifest);
  await writeJson(path.join(args.outDir, 'blocked.json'), blocked);
  await writeJson(path.join(args.outDir, 'summary.json'), summary);
  return summary;
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.help) {
    console.log(usage());
    return;
  }
  if (args.selfTest) {
    const u = normalizeUrl('https://example.com/a#b');
    if (u !== 'https://example.com/a') throw new Error('normalize failed');
    const robots = {
      status: 'ok',
      rules: parseRobots(
        'User-agent: *\nDisallow: /private\nAllow: /private/public\nSitemap: https://example.com/sitemap.xml'
      ),
    };
    if (robotsAllows(robots, 'https://example.com/private/x')) throw new Error('robots disallow failed');
    if (robotsAllows(robots, 'https://example.com/%70rivate/x')) {
      throw new Error('robots percent-encoded unreserved disallow failed');
    }
    if (!robotsAllows(robots, 'https://example.com/private/public/x')) throw new Error('robots allow failed');
    // wildcard + end anchor
    const wild = {
      status: 'ok',
      rules: parseRobots('User-agent: DResearchBot\nDisallow: /*.pdf$\nUser-agent: *\nDisallow: /tmp'),
    };
    if (robotsAllows(wild, 'https://example.com/a.pdf')) throw new Error('wildcard $ disallow failed');
    if (!robotsAllows(wild, 'https://example.com/ok')) throw new Error('DResearchBot group allow failed');
    if (robotsAllows({ status: 'disallow_all', rules: [] }, 'https://example.com/x')) {
      throw new Error('401/403 robots should disallow');
    }
    if (robotsAllows({ status: 'rate_limited', rules: [] }, 'https://example.com/x')) {
      throw new Error('429 robots should stop domain');
    }
    try {
      parseArgs(['node', 'playwright_crawl.mjs', '--no-respect-robots', '--seed', 'https://example.com']);
      await run({
        seeds: ['https://example.com'],
        outDir: 'research-output/crawl',
        maxDepth: 0,
        maxPages: 1,
        maxPagesPerDomain: 1,
        delayMs: 0,
        timeout: 1000,
        headless: true,
        respectRobots: false,
        noRespectRobotsRequested: true,
        followExternalLinks: false,
      });
      throw new Error('expected policy hard-fail for --no-respect-robots');
    } catch (e) {
      if (!String(e.message || e).includes('policy hard-fail')) throw e;
    }
    const capParsed = parseArgs([
      'node',
      'playwright_crawl.mjs',
      '--seed',
      'https://example.com',
      '--max-response-bytes',
      '123',
    ]);
    if (capParsed.maxResponseBytes !== 123) throw new Error('max-response-bytes parser failed');
    selfTestBrowserLimits();
    console.log('playwright_crawl self-test ok');
    return;
  }
  try {
    const summary = await run(args);
    console.log(JSON.stringify(summary, null, 2));
    if (summary.resourceLimitExceeded) process.exitCode = 3;
  } catch (err) {
    if (/Cannot find package 'playwright'/.test(String(err))) {
      console.error('Playwright is not installed. Run: npm install && npx playwright install chromium');
    } else {
      console.error(err.stack || String(err));
    }
    process.exit(1);
  }
}

main();
