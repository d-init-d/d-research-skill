#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';

function parseArgs(argv) {
  const args = { headless: true, timeout: 30000, waitMs: 750 };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--help' || a === '-h') args.help = true;
    else if (a === '--self-test') args.selfTest = true;
    else if (a === '--url') args.url = argv[++i];
    else if (a === '--out') args.out = argv[++i];
    else if (a === '--screenshot') args.screenshot = argv[++i];
    else if (a === '--timeout') args.timeout = Number(argv[++i]);
    else if (a === '--wait-ms') args.waitMs = Number(argv[++i]);
    else if (a === '--headful') args.headless = false;
    else throw new Error(`Unknown argument: ${a}`);
  }
  return args;
}

function usage() {
  return `Usage: node scripts/playwright_probe.mjs --url <url> [--out probe.json] [--screenshot page.png]\n\nOptions:\n  --url <url>          Page to probe\n  --out <path>         JSON output path\n  --screenshot <path>  Optional screenshot path\n  --timeout <ms>       Navigation timeout, default 30000\n  --wait-ms <ms>       Extra wait after load, default 750\n  --headful            Run with a visible browser\n  --self-test          Run lightweight checks without Playwright\n`;
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

async function run(args) {
  if (!args.url) throw new Error('Missing --url');
  const { chromium } = await import('playwright');
  const browser = await chromium.launch({ headless: args.headless });
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();
  page.setDefaultTimeout(args.timeout);
  let response = null;
  try {
    response = await page.goto(args.url, { waitUntil: 'domcontentloaded', timeout: args.timeout });
    await page.waitForTimeout(args.waitMs);
  } catch (err) {
    const result = {
      inputUrl: args.url,
      finalUrl: page.url(),
      accessStatus: 'broken',
      error: String(err.message || err),
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

  if (args.screenshot) {
    await ensureDirFor(args.screenshot);
    await page.screenshot({ path: args.screenshot, fullPage: true });
    result.screenshotPath = args.screenshot;
  }

  const status = response ? response.status() : null;
  const blockers = classifyBlockers({ status, text: result.textSample, title: result.title, links: result.links || [] });
  const output = {
    inputUrl: args.url,
    finalUrl: page.url(),
    status,
    accessStatus: inferAccessStatus(blockers, status, result.textLength),
    blockers,
    timestamp: new Date().toISOString(),
    ...result
  };
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
    console.log('playwright_probe self-test ok');
    return;
  }
  try {
    const result = await run(args);
    const json = JSON.stringify(result, null, 2);
    if (args.out) {
      await ensureDirFor(args.out);
      await fs.writeFile(args.out, json + '\n');
    } else {
      console.log(json);
    }
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
