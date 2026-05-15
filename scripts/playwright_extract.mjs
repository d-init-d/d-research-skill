#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';

function parseArgs(argv) {
  const args = { headless: true, timeout: 30000, waitMs: 750, format: 'json' };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--help' || a === '-h') args.help = true;
    else if (a === '--self-test') args.selfTest = true;
    else if (a === '--url') args.url = argv[++i];
    else if (a === '--out') args.out = argv[++i];
    else if (a === '--format') args.format = argv[++i];
    else if (a === '--selector') args.selector = argv[++i];
    else if (a === '--screenshot') args.screenshot = argv[++i];
    else if (a === '--timeout') args.timeout = Number(argv[++i]);
    else if (a === '--wait-ms') args.waitMs = Number(argv[++i]);
    else if (a === '--headful') args.headless = false;
    else throw new Error(`Unknown argument: ${a}`);
  }
  return args;
}

function usage() {
  return `Usage: node scripts/playwright_extract.mjs --url <url> [--format json|md] [--out output.json]\n\nOptions:\n  --url <url>          Page to extract\n  --out <path>         Output file\n  --format json|md     Output format, default json\n  --selector <css>     Extract text under a CSS selector when available\n  --screenshot <path>  Optional screenshot path\n  --timeout <ms>       Navigation timeout, default 30000\n  --wait-ms <ms>       Extra wait after load, default 750\n  --headful            Run with a visible browser\n  --self-test          Run lightweight checks without Playwright\n`;
}

async function ensureDirFor(filePath) {
  if (!filePath) return;
  await fs.mkdir(path.dirname(path.resolve(filePath)), { recursive: true });
}

function toMarkdown(data) {
  const lines = [];
  lines.push(`# ${data.title || data.finalUrl}`);
  lines.push('');
  lines.push(`Source: ${data.finalUrl}`);
  lines.push(`Accessed: ${data.timestamp}`);
  lines.push('');
  if (data.headings.length) {
    lines.push('## Headings');
    for (const h of data.headings) lines.push(`- ${h.level}: ${h.text}`);
    lines.push('');
  }
  lines.push('## Text');
  lines.push('');
  lines.push(data.text || '');
  lines.push('');
  if (data.tables.length) {
    lines.push('## Tables');
    data.tables.forEach((t, idx) => {
      lines.push(`### Table ${idx + 1}`);
      lines.push('');
      lines.push('```json');
      lines.push(JSON.stringify(t, null, 2));
      lines.push('```');
      lines.push('');
    });
  }
  if (data.files.length) {
    lines.push('## Files');
    for (const f of data.files) lines.push(`- [${f.text || f.href}](${f.href})`);
    lines.push('');
  }
  return lines.join('\n');
}

async function run(args) {
  if (!args.url) throw new Error('Missing --url');
  if (!['json', 'md'].includes(args.format)) throw new Error('--format must be json or md');
  const { chromium } = await import('playwright');
  const browser = await chromium.launch({ headless: args.headless });
  const context = await browser.newContext({ ignoreHTTPSErrors: true });
  const page = await context.newPage();
  page.setDefaultTimeout(args.timeout);
  const response = await page.goto(args.url, { waitUntil: 'domcontentloaded', timeout: args.timeout });
  await page.waitForTimeout(args.waitMs);

  const data = await page.evaluate((selector) => {
    const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
    const abs = (href) => {
      try { return new URL(href, document.baseURI).href; } catch { return href || ''; }
    };
    const root = selector ? document.querySelector(selector) : document.body;
    const scope = root || document.body || document.documentElement;
    const links = Array.from(scope.querySelectorAll('a[href]')).slice(0, 1000).map((a) => ({
      text: clean(a.innerText || a.getAttribute('aria-label') || a.getAttribute('title') || ''),
      href: abs(a.getAttribute('href'))
    })).filter((x) => x.href);
    const files = links.filter((l) => /\.(pdf|csv|xlsx?|json|xml|docx?|zip|txt)(\?|#|$)/i.test(l.href));
    const headings = Array.from(scope.querySelectorAll('h1,h2,h3,h4')).slice(0, 200).map((h) => ({
      level: h.tagName.toLowerCase(),
      text: clean(h.innerText)
    })).filter((h) => h.text);
    const tables = Array.from(scope.querySelectorAll('table')).slice(0, 50).map((table) => {
      return Array.from(table.querySelectorAll('tr')).map((tr) => {
        return Array.from(tr.querySelectorAll('th,td')).map((cell) => clean(cell.innerText));
      }).filter((row) => row.length);
    });
    const structured = Array.from(document.querySelectorAll('script[type="application/ld+json"]')).slice(0, 20).map((s) => clean(s.textContent));
    const meta = {};
    for (const m of Array.from(document.querySelectorAll('meta'))) {
      const k = m.getAttribute('name') || m.getAttribute('property');
      const v = m.getAttribute('content');
      if (k && v) meta[k] = v;
    }
    return {
      title: document.title || '',
      canonicalUrl: document.querySelector('link[rel="canonical"]')?.href || '',
      language: document.documentElement.lang || '',
      meta,
      headings,
      links,
      files,
      tables,
      structuredData: structured,
      text: clean(scope.innerText || '')
    };
  }, args.selector || null);

  if (args.screenshot) {
    await ensureDirFor(args.screenshot);
    await page.screenshot({ path: args.screenshot, fullPage: true });
    data.screenshotPath = args.screenshot;
  }

  const result = {
    inputUrl: args.url,
    finalUrl: page.url(),
    status: response ? response.status() : null,
    selector: args.selector || null,
    timestamp: new Date().toISOString(),
    ...data
  };
  await browser.close();
  return result;
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.help) {
    console.log(usage());
    return;
  }
  if (args.selfTest) {
    const parsed = parseArgs(['node', 'script', '--url', 'https://example.com', '--format', 'md']);
    if (parsed.format !== 'md') throw new Error('arg parser failed');
    const md = toMarkdown({ title: 'T', finalUrl: 'u', timestamp: 'now', headings: [], text: 'body', tables: [], files: [] });
    if (!md.includes('# T') || !md.includes('body')) throw new Error('markdown conversion failed');
    console.log('playwright_extract self-test ok');
    return;
  }
  try {
    const result = await run(args);
    const output = args.format === 'md' ? toMarkdown(result) : JSON.stringify(result, null, 2) + '\n';
    if (args.out) {
      await ensureDirFor(args.out);
      await fs.writeFile(args.out, output);
    } else {
      console.log(output);
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
