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
  structuredBlocker,
} from './lib/browser_ssrf.mjs';

function parseArgs(argv) {
  const args = { headless: true, timeout: 30000, waitMs: 750, maxResponseBytes: null };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--help' || a === '-h') args.help = true;
    else if (a === '--self-test') args.selfTest = true;
    else if (a === '--url') args.url = argv[++i];
    else if (a === '--out') args.out = argv[++i];
    else if (a === '--screenshot') args.screenshot = argv[++i];
    else if (a === '--timeout') args.timeout = Number(argv[++i]);
    else if (a === '--max-response-bytes') args.maxResponseBytes = Number(argv[++i]);
    else if (a === '--wait-ms') args.waitMs = Number(argv[++i]);
    else if (a === '--headful') args.headless = false;
    else if (a === '--ignore-tls-errors') args.ignoreTlsErrors = true;
    else if (a === '--allow-loopback-fixture') args.allowLoopbackFixture = true;
    else throw new Error(`Unknown argument: ${a}`);
  }
  if (!Number.isSafeInteger(args.timeout) || args.timeout < 1) {
    throw new Error('--timeout must be a positive integer');
  }
  if (!Number.isSafeInteger(args.waitMs) || args.waitMs < 0) {
    throw new Error('--wait-ms must be a non-negative integer');
  }
  args.maxResponseBytes = resolveBrowserResponseLimit(args.maxResponseBytes);
  return args;
}

function usage() {
  return `Usage: node scripts/playwright_probe.mjs --url <url> [--out probe.json] [--screenshot page.png]\n\nOptions:\n  --url <url>              Page to probe\n  --out <path>             JSON output path\n  --screenshot <path>      Optional screenshot path\n  --timeout <ms>           Navigation timeout, default 30000\n  --max-response-bytes <n> Maximum main-document body bytes (env: D_RESEARCH_HTTP_MAX_BYTES)\n  --wait-ms <ms>           Extra wait after load, default 750\n  --headful                Run with a visible browser\n  --ignore-tls-errors      Opt in to invalid TLS certificates; recorded as limitation\n  --self-test              Run lightweight checks without Playwright\n`;
}

function classifyBlockers({ status, text, title, links }) {
  const hay = `${title || ''}\n${text || ''}`.toLowerCase();
  const blockers = [];
  if (status === 401) blockers.push('401_unauthorized');
  if (status === 403) blockers.push('403_forbidden');
  if (status === 429) blockers.push('429_rate_limited');
  if (/captcha|recaptcha|hcaptcha|verify you are human|human verification|security check/.test(hay)) blockers.push('captcha_or_bot_challenge');
  if (/log in|login|sign in|signin|create an account|authentication required/.test(hay)) blockers.push('login_required');
  if (/subscribe|subscription|paywall|premium access|members only|purchase access/.test(hay)) blockers.push('paywall_or_subscription');
  if (/access denied|forbidden|not authorized|permission denied/.test(hay)) blockers.push('access_denied');
  if (/temporarily unavailable in your region|not available in your country|geo/.test(hay)) blockers.push('geo_blocked');
  if (links.some((l) => /login|signin|account/.test(`${l.href} ${l.text}`.toLowerCase())) && (text || '').length < 1000) blockers.push('possible_login_gate');
  return [...new Set(blockers)];
}

function inferAccessStatus(blockers, status, textLength) {
  if (blockers.includes('429_rate_limited')) return 'rate_limited';
  if (blockers.includes('captcha_or_bot_challenge')) return 'captcha';
  if (blockers.includes('login_required') || blockers.includes('possible_login_gate')) return 'login_required';
  if (blockers.includes('paywall_or_subscription')) return 'paywalled';
  if (blockers.includes('403_forbidden') || blockers.includes('401_unauthorized') || blockers.includes('access_denied')) return 'forbidden';
  if (blockers.includes('geo_blocked')) return 'geo_blocked';
  if (status && status >= 500) return 'server_error';
  if (status === 404) return 'not_found';
  if (textLength < 200) return 'partial_or_empty';
  return 'accessible';
}

async function ensureDirFor(filePath) {
  if (!filePath) return;
  await fs.mkdir(path.dirname(path.resolve(filePath)), { recursive: true });
}

// Must match robots User-agent token used by playwright_crawl.mjs
const BROWSER_USER_AGENT =
  'Mozilla/5.0 (compatible; DResearchBot/3.2; +https://github.com/d-init-d/d-research-skill)';

async function run(args) {
  if (!args.url) throw new Error('Missing --url');
  // Fail-closed SSRF before launching Chromium when destination is private.
  const pre = await assertBrowserPublicUrl(args.url, {
    allowLoopback: args.allowLoopbackFixture === true,
  });
  if (!pre.ok) {
    return {
      inputUrl: args.url,
      finalUrl: args.url,
      accessStatus: 'blocked',
      blockers: ['ssrf_private_or_internal'],
      ssrfBlocker: pre.blocker,
      error: pre.blocker.message,
      limitations: [],
      timestamp: new Date().toISOString(),
    };
  }
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
  const ssrfStats = await installBrowserSsrfGuard(context, {
    allowLoopback: args.allowLoopbackFixture === true,
    ignoreTlsErrors: ignoreTls,
    maxResponseBytes: args.maxResponseBytes,
    timeoutMs: args.timeout,
  });
  let response = null;
  let responseBytes = null;
  try {
    response = await page.goto(args.url, { waitUntil: 'domcontentloaded', timeout: args.timeout });
    const routeLimit = browserResourceLimitErrorFromPayload(ssrfStats.resourceLimit);
    if (routeLimit) throw routeLimit;
    responseBytes = await enforceBrowserResponseLimit(
      response,
      args.maxResponseBytes,
      args.timeout,
    );
    await page.waitForTimeout(args.waitMs);
    const delayedRouteLimit = browserResourceLimitErrorFromPayload(ssrfStats.resourceLimit);
    if (delayedRouteLimit) throw delayedRouteLimit;
  } catch (err) {
    if (resourceLimitPayload(err)) {
      await browser.close();
      throw err;
    }
    const result = {
      inputUrl: args.url,
      finalUrl: page.url(),
      accessStatus: 'broken',
      error: String(err.message || err),
      ssrfStats,
      limitations: ignoreTls ? ['ignore_tls_errors_enabled'] : [],
      timestamp: new Date().toISOString()
    };
    await browser.close();
    return result;
  }

  const result = await page.evaluate(() => {
    const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
    const abs = (href) => {
      try { return new URL(href, document.baseURI).href; } catch { return href || ''; }
    };
    const links = Array.from(document.querySelectorAll('a[href]')).slice(0, 500).map((a) => ({
      text: clean(a.innerText || a.getAttribute('aria-label') || a.getAttribute('title') || ''),
      href: abs(a.getAttribute('href'))
    })).filter((x) => x.href);
    const headings = Array.from(document.querySelectorAll('h1,h2,h3')).slice(0, 100).map((h) => ({
      level: h.tagName.toLowerCase(),
      text: clean(h.innerText)
    })).filter((h) => h.text);
    const meta = {};
    for (const m of Array.from(document.querySelectorAll('meta'))) {
      const k = m.getAttribute('name') || m.getAttribute('property');
      const v = m.getAttribute('content');
      if (k && v) meta[k] = v;
    }
    const files = links.filter((l) => /\.(pdf|csv|xlsx?|json|xml|docx?|zip|txt)(\?|#|$)/i.test(l.href));
    const text = clean(document.body ? document.body.innerText : '');
    return {
      title: document.title || '',
      canonicalUrl: document.querySelector('link[rel="canonical"]')?.href || '',
      language: document.documentElement.lang || '',
      meta,
      headings,
      links,
      files,
      tableCount: document.querySelectorAll('table').length,
      formCount: document.querySelectorAll('form').length,
      inputCount: document.querySelectorAll('input,select,textarea').length,
      textLength: text.length,
      textSample: text.slice(0, 4000)
    };
  });

  const evaluateRouteLimit = browserResourceLimitErrorFromPayload(ssrfStats.resourceLimit);
  if (evaluateRouteLimit) {
    await browser.close();
    throw evaluateRouteLimit;
  }

  if (args.screenshot) {
    await ensureDirFor(args.screenshot);
    await page.screenshot({ path: args.screenshot, fullPage: true });
    result.screenshotPath = args.screenshot;
    const screenshotRouteLimit = browserResourceLimitErrorFromPayload(
      ssrfStats.resourceLimit,
    );
    if (screenshotRouteLimit) {
      await browser.close();
      throw screenshotRouteLimit;
    }
  }

  const status = response ? response.status() : null;
  const blockers = classifyBlockers({ status, text: result.textSample, title: result.title, links: result.links || [] });
  const output = {
    inputUrl: args.url,
    finalUrl: page.url(),
    status,
    accessStatus: inferAccessStatus(blockers, status, result.textLength),
    blockers,
    limitations: ignoreTls ? ['ignore_tls_errors_enabled'] : [],
    limits: {
      maxResponseBytes: args.maxResponseBytes,
      responseBytes,
    },
    ssrfStats,
    timestamp: new Date().toISOString(),
    ...result
  };
  try {
    output.limits.extractedBytes = enforceBrowserOutputLimit(
      output,
      args.maxResponseBytes,
      page.url(),
    );
  } catch (error) {
    await browser.close();
    throw error;
  }
  await browser.close();
  return output;
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.help) {
    console.log(usage());
    return;
  }
  if (args.selfTest) {
    const parsed = parseArgs(['node', 'script', '--url', 'https://example.com', '--out', 'out.json']);
    if (parsed.url !== 'https://example.com' || parsed.out !== 'out.json') throw new Error('arg parser failed');
    const blockers = classifyBlockers({ status: 403, text: 'Access denied', title: '', links: [] });
    if (!blockers.includes('403_forbidden')) throw new Error('blocker classification failed');
    const tlsParsed = parseArgs(['node', 'script', '--url', 'https://example.com', '--ignore-tls-errors']);
    if (!tlsParsed.ignoreTlsErrors) throw new Error('ignore-tls-errors parser failed');
    const capParsed = parseArgs(['node', 'script', '--url', 'https://example.com', '--max-response-bytes', '123']);
    if (capParsed.maxResponseBytes !== 123) throw new Error('max-response-bytes parser failed');
    selfTestBrowserLimits();
    console.log('playwright_probe self-test ok');
    return;
  }
  try {
    const result = await run(args);
    const json = JSON.stringify(result, null, 2);
    enforceBrowserOutputLimit(json, args.maxResponseBytes, result.finalUrl);
    if (args.out) {
      await ensureDirFor(args.out);
      await fs.writeFile(args.out, json + '\n');
    } else {
      console.log(json);
    }
  } catch (err) {
    const payload = resourceLimitPayload(err);
    if (payload) {
      console.error(JSON.stringify(payload));
      process.exit(3);
    } else if (/Cannot find package 'playwright'/.test(String(err))) {
      console.error('Playwright is not installed. Run: npm install && npx playwright install chromium');
    } else {
      console.error(err.stack || String(err));
    }
    process.exit(1);
  }
}

main();
