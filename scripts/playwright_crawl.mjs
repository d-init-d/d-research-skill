#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';

function parseArgs(argv) {
  const args = {
    seeds: [],
    outDir: 'research-output/crawl',
    maxDepth: 2,
    maxPages: 100,
    maxPagesPerDomain: 30,
    delayMs: 1000,
    timeout: 30000,
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
    else if (a === '--headful') args.headless = false;
    else if (a === '--no-respect-robots') args.respectRobots = false;
    else if (a === '--follow-external-links') args.followExternalLinks = true;
    else throw new Error(`Unknown argument: ${a}`);
  }
  return args;
}

function usage() {
  return `Usage: node scripts/playwright_crawl.mjs --seed <url> [--outDir crawl] [--maxDepth 2] [--maxPages 100]\n\nOptions:\n  --seed <url>              Seed URL, can be repeated\n  --seeds <file>            Newline-delimited seed URLs\n  --outDir <dir>            Output directory, default research-output/crawl\n  --maxDepth <n>            Max crawl depth, default 2\n  --maxPages <n>            Max total pages, default 100\n  --maxPagesPerDomain <n>   Max pages per domain, default 30\n  --delayMs <ms>            Delay between pages, default 1000\n  --timeout <ms>            Navigation timeout, default 30000\n  --headful                 Run with a visible browser\n  --no-respect-robots       Disable basic robots checks\n  --follow-external-links   Allow external links in crawl queue\n  --self-test               Run lightweight checks without Playwright\n`;
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
      current = { agents: [value.toLowerCase()], disallow: [], allow: [], sitemaps: [] };
      groups.push(current);
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

function robotsAllows(groups, targetUrl) {
  if (!groups.length) return true;
  const u = new URL(targetUrl);
  const pathName = u.pathname || '/';
  const relevant = groups.filter((g) => g.agents.includes('*'));
  if (!relevant.length) return true;
  let matchedAllow = '';
  let matchedDisallow = '';
  for (const g of relevant) {
    for (const rule of g.allow) if (rule && pathName.startsWith(rule) && rule.length > matchedAllow.length) matchedAllow = rule;
    for (const rule of g.disallow) if (rule && pathName.startsWith(rule) && rule.length > matchedDisallow.length) matchedDisallow = rule;
  }
  if (!matchedDisallow) return true;
  return matchedAllow.length >= matchedDisallow.length;
}

async function getRobots(cache, url) {
  const origin = new URL(url).origin;
  if (cache.has(origin)) return cache.get(origin);
  try {
    const res = await fetch(`${origin}/robots.txt`, { redirect: 'follow' });
    if (!res.ok) {
      cache.set(origin, []);
      return [];
    }
    const text = await res.text();
    const parsed = parseRobots(text);
    cache.set(origin, parsed);
    return parsed;
  } catch {
    cache.set(origin, []);
    return [];
  }
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
  const seeds = await loadSeeds(args);
  if (!seeds.length) throw new Error('Provide at least one --seed URL');
  await ensureDir(args.outDir);
  await ensureDir(path.join(args.outDir, 'pages'));

  const { chromium } = await import('playwright');
  const browser = await chromium.launch({ headless: args.headless });
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();
  page.setDefaultTimeout(args.timeout);

  const queue = seeds.map((url) => ({ url, depth: 0, seed: url }));
  const seen = new Set();
  const perDomain = new Map();
  const robotsCache = new Map();
  const manifest = [];
  const blocked = [];

  while (queue.length && manifest.length < args.maxPages) {
    const item = queue.shift();
    const url = normalizeUrl(item.url);
    if (!url || seen.has(url)) continue;
    seen.add(url);
    const host = new URL(url).hostname;
    const count = perDomain.get(host) || 0;
    if (count >= args.maxPagesPerDomain) {
      blocked.push({ url, reason: 'max_pages_per_domain', depth: item.depth });
      continue;
    }
    if (args.respectRobots) {
      const groups = await getRobots(robotsCache, url);
      if (!robotsAllows(groups, url)) {
        blocked.push({ url, reason: 'robots_disallow', depth: item.depth });
        continue;
      }
    }
    perDomain.set(host, count + 1);
    await sleep(args.delayMs);
    let response = null;
    try {
      response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: args.timeout });
      await page.waitForTimeout(500);
      const data = await extractPage(page, url, response);
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
      manifest.push(record);
      await writeJson(path.join(args.outDir, 'pages', `${String(record.id).padStart(4, '0')}.json`), record);
      if (item.depth < args.maxDepth) {
        for (const link of data.links) {
          const next = normalizeUrl(link.href);
          if (!next || seen.has(next) || isLikelyBinary(next)) continue;
          if (!args.followExternalLinks && !sameDomain(next, item.seed)) continue;
          queue.push({ url: next, depth: item.depth + 1, seed: item.seed });
        }
      }
    } catch (err) {
      blocked.push({ url, reason: 'navigation_error', error: String(err.message || err), depth: item.depth });
    }
  }

  await browser.close();
  const summary = {
    seeds,
    config: {
      maxDepth: args.maxDepth,
      maxPages: args.maxPages,
      maxPagesPerDomain: args.maxPagesPerDomain,
      delayMs: args.delayMs,
      respectRobots: args.respectRobots,
      followExternalLinks: args.followExternalLinks
    },
    pagesVisited: manifest.length,
    blockedCount: blocked.length,
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
    const robots = parseRobots('User-agent: *\nDisallow: /private\nAllow: /private/public\nSitemap: https://example.com/sitemap.xml');
    if (robotsAllows(robots, 'https://example.com/private/x')) throw new Error('robots disallow failed');
    if (!robotsAllows(robots, 'https://example.com/private/public/x')) throw new Error('robots allow failed');
    console.log('playwright_crawl self-test ok');
    return;
  }
  try {
    const summary = await run(args);
    console.log(JSON.stringify(summary, null, 2));
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
