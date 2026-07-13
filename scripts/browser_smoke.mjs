#!/usr/bin/env node
/**
 * Real Chromium browser smoke tests against local fixtures.
 * Installing Chromium is NOT enough — this launches Chromium and exercises:
 *   probe, extract, crawl, robots redirect, credential redirect,
 *   TLS default failure + opt-in limitation, bounded browser responses,
 *   local-only navigation.
 *
 * Usage:
 *   node scripts/browser_smoke.mjs
 *   node scripts/browser_smoke.mjs --self-test
 */
import http from 'node:http';
import https from 'node:https';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { generateKeyPairSync, randomBytes, sign } from 'node:crypto';
import { chromium } from 'playwright';
import { installBrowserSsrfGuard } from './lib/browser_ssrf.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

const UA = 'DResearchBot/3.2 (+https://github.com/d-init-d/d-research-skill)';

// Minimal DER builder used only to create an ephemeral self-signed localhost
// certificate. No private key is committed and no external network/tool is used.
function derLength(length) {
  if (length < 0x80) return Buffer.from([length]);
  const bytes = [];
  let value = length;
  while (value > 0) {
    bytes.unshift(value & 0xff);
    value >>>= 8;
  }
  return Buffer.from([0x80 | bytes.length, ...bytes]);
}

function der(tag, ...parts) {
  const content = Buffer.concat(parts.map((part) => Buffer.from(part)));
  return Buffer.concat([Buffer.from([tag]), derLength(content.length), content]);
}

const derSequence = (...parts) => der(0x30, ...parts);
const derSet = (...parts) => der(0x31, ...parts);
const derNull = () => der(0x05);
const derUtf8 = (value) => der(0x0c, Buffer.from(value, 'utf8'));
const derUtcTime = (date) => {
  const iso = date.toISOString().replace(/[-:T]/g, '').replace(/\.\d{3}Z$/, 'Z');
  return der(0x17, Buffer.from(iso.slice(2), 'ascii'));
};
const derInteger = (input) => {
  let value = Buffer.isBuffer(input) ? Buffer.from(input) : Buffer.from([input]);
  while (value.length > 1 && value[0] === 0) value = value.subarray(1);
  if (value[0] & 0x80) value = Buffer.concat([Buffer.from([0]), value]);
  return der(0x02, value);
};
const derOid = (value) => {
  const numbers = value.split('.').map(Number);
  const bytes = [numbers[0] * 40 + numbers[1]];
  for (const number of numbers.slice(2)) {
    const encoded = [number & 0x7f];
    let remaining = Math.floor(number / 128);
    while (remaining > 0) {
      encoded.unshift(0x80 | (remaining & 0x7f));
      remaining = Math.floor(remaining / 128);
    }
    bytes.push(...encoded);
  }
  return der(0x06, Buffer.from(bytes));
};

function toPem(label, value) {
  const body = value.toString('base64').match(/.{1,64}/g).join('\n');
  return `-----BEGIN ${label}-----\n${body}\n-----END ${label}-----\n`;
}

function createEphemeralTlsFixture() {
  const { privateKey, publicKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
  const signatureAlgorithm = derSequence(
    derOid('1.2.840.113549.1.1.11'),
    derNull(),
  );
  const commonName = derSequence(
    derSet(derSequence(derOid('2.5.4.3'), derUtf8('localhost'))),
  );
  const now = Date.now();
  const serial = randomBytes(16);
  serial[0] &= 0x7f;
  if (serial.every((byte) => byte === 0)) serial[serial.length - 1] = 1;
  const subjectPublicKeyInfo = publicKey.export({ type: 'spki', format: 'der' });
  const tbsCertificate = derSequence(
    der(0xa0, derInteger(2)),
    derInteger(serial),
    signatureAlgorithm,
    commonName,
    derSequence(
      derUtcTime(new Date(now - 60_000)),
      derUtcTime(new Date(now + 24 * 60 * 60 * 1000)),
    ),
    commonName,
    subjectPublicKeyInfo,
  );
  const signature = sign('RSA-SHA256', tbsCertificate, privateKey);
  const certificate = derSequence(
    tbsCertificate,
    signatureAlgorithm,
    der(0x03, Buffer.concat([Buffer.from([0]), signature])),
  );
  return {
    key: privateKey.export({ type: 'pkcs8', format: 'pem' }),
    cert: toPem('CERTIFICATE', certificate),
  };
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

function runNode(script, args, env = {}) {
  return new Promise((resolve) => {
    // Local API fixtures still need loopback for api_fetch. Browser helpers use
    // the explicit --allow-loopback-fixture test hook instead of env inheritance.
    const child = spawn(process.execPath, [script, ...args], {
      cwd: ROOT,
      env: {
        ...process.env,
        D_RESEARCH_SSRF_ALLOW_LOOPBACK: process.env.D_RESEARCH_SSRF_ALLOW_LOOPBACK || '1',
        ...env,
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (d) => { stdout += d.toString(); });
    child.stderr.on('data', (d) => { stderr += d.toString(); });
    child.on('close', (code) => resolve({ code, stdout, stderr }));
  });
}

function startFixtureServer() {
  return new Promise((resolve) => {
    const hits = [];
    const server = http.createServer((req, res) => {
      const url = new URL(req.url || '/', 'http://127.0.0.1');
      const hit = {
        path: url.pathname,
        method: req.method || 'GET',
        headers: { ...req.headers },
        body: '',
      };
      hits.push(hit);
      if (url.pathname === '/robots.txt') {
        res.writeHead(200, { 'Content-Type': 'text/plain' });
        res.end('User-agent: DResearchBot\nDisallow: /private/\n');
        return;
      }
      if (url.pathname === '/ok') {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end('<html><body><h1>OK Page</h1><p>fixture content</p><a href="/ok2">next</a></body></html>');
        return;
      }
      if (url.pathname === '/ok2') {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end('<html><body><h1>OK2</h1></body></html>');
        return;
      }
      if (url.pathname === '/sw-page') {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end('<html><body><h1>SW Page</h1></body></html>');
        return;
      }
      if (url.pathname === '/sw.js') {
        res.writeHead(200, { 'Content-Type': 'application/javascript' });
        res.end(
          "self.addEventListener('fetch', event => event.respondWith(new Response('SW INTERCEPTED')));",
        );
        return;
      }
      if (url.pathname === '/sw-controlled') {
        res.writeHead(200, { 'Content-Type': 'text/plain' });
        res.end('SERVER RESPONSE');
        return;
      }
      if (url.pathname === '/large') {
        const body = Buffer.from(`<html><body>${'x'.repeat(256 * 1024)}</body></html>`);
        res.writeHead(200, {
          'Content-Type': 'text/html',
          'Content-Length': String(body.length),
        });
        res.end(body);
        return;
      }
      if (url.pathname === '/private/secret') {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end('<html><body>SECRET SHOULD NOT BE EXTRACTED</body></html>');
        return;
      }
      if (url.pathname === '/post-page') {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(
          '<html><body><h1>read only</h1><script>' +
          "fetch('/mutate',{method:'POST',body:'changed-by-page'}).catch(()=>{});" +
          '</script></body></html>',
        );
        return;
      }
      if (url.pathname === '/mutate') {
        const chunks = [];
        req.on('data', (chunk) => chunks.push(Buffer.from(chunk)));
        req.on('end', () => {
          hit.body = Buffer.concat(chunks).toString('utf8');
          res.writeHead(200, { 'Content-Type': 'text/plain' });
          res.end('mutation received');
        });
        return;
      }
      if (url.pathname === '/dom-expand') {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(
          '<html><body><script>' +
          "document.body.textContent='D'.repeat(5*1024*1024);" +
          '</script></body></html>',
        );
        return;
      }
      if (url.pathname === '/oversized-subresource') {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(
          '<html><body><h1>subresource cap</h1>' +
          '<img src="/subresource-large"></body></html>',
        );
        return;
      }
      if (url.pathname === '/subresource-large') {
        const body = Buffer.alloc(4096, 120);
        res.writeHead(200, {
          'Content-Type': 'application/octet-stream',
          'Content-Length': String(body.length),
        });
        res.end(body);
        return;
      }
      if (url.pathname === '/aggregate-page') {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(
          '<html><body><h1>aggregate cap</h1><script>' +
          "Promise.allSettled(Array.from({length:20},(_,i)=>fetch('/aggregate-chunk?i='+i)));" +
          '</script></body></html>',
        );
        return;
      }
      if (url.pathname === '/aggregate-chunk') {
        const body = Buffer.alloc(128, 97);
        res.writeHead(200, {
          'Content-Type': 'application/octet-stream',
          'Content-Length': String(body.length),
        });
        res.end(body);
        return;
      }
      if (url.pathname === '/request-fanout') {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(
          '<html><body><h1>request cap</h1><script>' +
          "Promise.allSettled(Array.from({length:105},(_,i)=>fetch('/tiny?i='+i)));" +
          '</script></body></html>',
        );
        return;
      }
      if (url.pathname === '/tiny') {
        res.writeHead(204);
        res.end();
        return;
      }
      if (url.pathname === '/%70rivate/secret') {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end('<html><body>ENCODED SECRET SHOULD NOT BE EXTRACTED</body></html>');
        return;
      }
      if (url.pathname === '/redir-private') {
        res.writeHead(302, { Location: '/private/secret' });
        res.end();
        return;
      }
      if (url.pathname === '/cred-bounce') {
        // Redirect that must not forward custom secret headers cross-hop
        res.writeHead(302, { Location: '/ok' });
        res.end();
        return;
      }
      res.writeHead(404);
      res.end('not found');
    });
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      resolve({ server, port, base: `http://127.0.0.1:${port}`, hits });
    });
  });
}

function startTrapServer() {
  return new Promise((resolve) => {
    const hits = [];
    const upgrades = [];
    const server = http.createServer((req, res) => {
      const url = new URL(req.url || '/', 'http://127.0.0.1');
      hits.push({ path: url.pathname, headers: { ...req.headers } });
      res.writeHead(200, { 'Content-Type': 'text/plain' });
      res.end('trap hit');
    });
    server.on('upgrade', (req, socket) => {
      upgrades.push({ url: req.url, headers: { ...req.headers } });
      socket.destroy();
    });
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      resolve({ server, port, base: `http://127.0.0.1:${port}`, hits, upgrades });
    });
  });
}

function startRobotsStatusServer(robotsStatus) {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const url = new URL(req.url || '/', 'http://127.0.0.1');
      if (url.pathname === '/robots.txt') {
        res.writeHead(robotsStatus, { 'Content-Type': 'text/plain' });
        res.end(robotsStatus === 404 ? 'not found' : 'robots unavailable');
        return;
      }
      if (url.pathname === '/ok') {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end('<html><body><h1>robots status fixture</h1></body></html>');
        return;
      }
      res.writeHead(404);
      res.end('not found');
    });
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      resolve({ server, base: `http://127.0.0.1:${port}` });
    });
  });
}

function startTlsFixtureServer() {
  return new Promise((resolve) => {
    const tls = createEphemeralTlsFixture();
    const server = https.createServer(tls, (req, res) => {
      const url = new URL(req.url || '/', 'https://127.0.0.1');
      if (url.pathname === '/robots.txt') {
        res.writeHead(404, { 'Content-Type': 'text/plain' });
        res.end('not found');
        return;
      }
      if (url.pathname === '/ok') {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end('<html><body><h1>TLS fixture</h1><p>self-signed local content</p></body></html>');
        return;
      }
      res.writeHead(404);
      res.end('not found');
    });
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      resolve({ server, base: `https://127.0.0.1:${port}` });
    });
  });
}

async function testRealChromiumLaunch() {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ userAgent: UA });
    await page.setContent('<html><body>local-only</body></html>');
    const text = await page.locator('body').innerText();
    assert(text.includes('local-only'), 'local content navigation failed');
  } finally {
    await browser.close();
  }
  return 'chromium_launch';
}

function ensureSmokeTmp(prefix) {
  const base = path.join(ROOT, 'research-output');
  fs.mkdirSync(base, { recursive: true });
  return fs.mkdtempSync(path.join(base, prefix));
}

async function testProbeExtractCrawl(base) {
  const probe = path.join(ROOT, 'scripts', 'playwright_probe.mjs');
  const extract = path.join(ROOT, 'scripts', 'playwright_extract.mjs');
  const crawl = path.join(ROOT, 'scripts', 'playwright_crawl.mjs');
  const tmp = ensureSmokeTmp('smoke-');
  try {
    const probeOut = path.join(tmp, 'probe.json');
    const extractOut = path.join(tmp, 'extract.json');
    const crawlDir = path.join(tmp, 'crawl');

    const p = await runNode(probe, [
      '--url', `${base}/ok`,
      '--out', probeOut,
      '--allow-loopback-fixture',
    ]);
    assert(p.code === 0, `probe failed: ${p.stderr || p.stdout}`);
    assert(fs.existsSync(probeOut), 'probe did not write output');

    const e = await runNode(extract, [
      '--url', `${base}/ok`,
      '--format', 'json',
      '--out', extractOut,
      '--allow-loopback-fixture',
    ]);
    assert(e.code === 0, `extract failed: ${e.stderr || e.stdout}`);
    const extractBody = fs.readFileSync(extractOut, 'utf8');
    assert(
      /OK Page|fixture content/i.test(extractBody),
      'extract missing fixture content',
    );

    const c = await runNode(crawl, [
      '--seed', `${base}/ok`,
      '--outDir', crawlDir,
      '--maxPages', '2',
      '--maxDepth', '1',
      '--delayMs', '50',
      '--allow-loopback-fixture',
    ]);
    assert(c.code === 0, `crawl failed: ${c.stderr || c.stdout}`);
  } finally {
    try { fs.rmSync(tmp, { recursive: true, force: true }); } catch { /* ignore */ }
  }
  return 'probe_extract_crawl';
}

async function testRobotsRedirect(fixture) {
  // A disallowed redirect target must be blocked before the HTTP request, not
  // merely omitted from the written extraction.
  const { base, hits } = fixture;
  const crawl = path.join(ROOT, 'scripts', 'playwright_crawl.mjs');
  const tmp = ensureSmokeTmp('smoke-robots-');
  const hitStart = hits.length;
  try {
    const crawlDir = path.join(tmp, 'crawl');
    const c = await runNode(crawl, [
      '--seed', `${base}/redir-private`,
      '--outDir', crawlDir,
      '--maxPages', '5',
      '--maxDepth', '2',
      '--delayMs', '50',
      '--allow-loopback-fixture',
    ]);
    const combined = `${c.stdout}\n${c.stderr}`;
    // Should not write a page body for /private/secret as successful extract
    let leaked = false;
    if (fs.existsSync(crawlDir)) {
      for (const f of fs.readdirSync(crawlDir, { recursive: true })) {
        const fp = path.join(crawlDir, String(f));
        try {
          if (fs.statSync(fp).isFile()) {
            const t = fs.readFileSync(fp, 'utf8');
            if (t.includes('SECRET SHOULD NOT BE EXTRACTED')) leaked = true;
          }
        } catch { /* ignore */ }
      }
    }
    assert(!leaked, 'robots-disallowed destination was extracted via crawl');
    const newHits = hits.slice(hitStart);
    assert(
      !newHits.some((hit) => hit.path === '/private/secret'),
      'robots-disallowed redirect destination received an HTTP request',
    );
    assert(c.code === 0 || /robots|disallow|blocked/i.test(combined), `unexpected crawl status: ${combined.slice(0, 300)}`);
  } finally {
    try { fs.rmSync(tmp, { recursive: true, force: true }); } catch { /* ignore */ }
  }
  return 'robots_redirect';
}

async function testRobotsPercentEncoding(fixture) {
  const { base, hits } = fixture;
  const crawl = path.join(ROOT, 'scripts', 'playwright_crawl.mjs');
  const tmp = ensureSmokeTmp('smoke-robots-percent-');
  const hitStart = hits.length;
  try {
    const result = await runNode(crawl, [
      '--seed', `${base}/%70rivate/secret`,
      '--outDir', tmp,
      '--maxPages', '1',
      '--delayMs', '0',
      '--allow-loopback-fixture',
    ]);
    assert(result.code === 0, `encoded robots crawl failed: ${result.stderr}`);
    const summary = JSON.parse(fs.readFileSync(path.join(tmp, 'summary.json'), 'utf8'));
    const blocked = JSON.parse(fs.readFileSync(path.join(tmp, 'blocked.json'), 'utf8'));
    assert(summary.pagesVisited === 0, 'percent-encoded disallowed path was visited');
    assert(
      blocked.some((row) => row.reason === 'robots_disallow'),
      'percent-encoded disallowed path did not record robots_disallow',
    );
    const newHits = hits.slice(hitStart);
    assert(
      !newHits.some((hit) => hit.path === '/%70rivate/secret'),
      'percent-encoded robots-disallowed destination received an HTTP request',
    );
  } finally {
    try { fs.rmSync(tmp, { recursive: true, force: true }); } catch { /* ignore */ }
  }
  return 'robots_percent_encoding';
}

async function testCrawlCompletenessBounds(base) {
  const crawl = path.join(ROOT, 'scripts', 'playwright_crawl.mjs');
  const tmp = ensureSmokeTmp('smoke-crawl-bounds-');
  const cases = [
    {
      name: 'max_pages',
      args: ['--maxPages', '1', '--maxDepth', '1', '--maxPagesPerDomain', '5'],
      expectedReason: 'max_pages',
      expectedBlocked: 'max_pages',
    },
    {
      name: 'max_pages_counts_blocked_attempts',
      seedArgs: [
        '--seed', `${base}/%70rivate/secret`,
        '--seed', `${base}/ok`,
      ],
      args: ['--maxPages', '1', '--maxDepth', '1', '--maxPagesPerDomain', '5'],
      expectedReason: 'max_pages',
      expectedBlocked: 'max_pages',
      expectedAttempts: 1,
    },
    {
      name: 'max_depth',
      args: ['--maxPages', '5', '--maxDepth', '0', '--maxPagesPerDomain', '5'],
      expectedReason: 'max_depth',
      expectedBlocked: 'max_depth',
    },
    {
      name: 'max_pages_per_domain',
      args: ['--maxPages', '5', '--maxDepth', '1', '--maxPagesPerDomain', '1'],
      expectedReason: 'max_pages_per_domain',
      expectedBlocked: 'max_pages_per_domain',
    },
  ];
  try {
    for (const item of cases) {
      const outDir = path.join(tmp, item.name);
      const result = await runNode(crawl, [
        ...(item.seedArgs || ['--seed', `${base}/ok`]),
        '--outDir', outDir,
        '--delayMs', '0',
        '--allow-loopback-fixture',
        ...item.args,
      ]);
      assert(result.code === 0, `${item.name} crawl failed: ${result.stderr}`);
      const summary = JSON.parse(fs.readFileSync(path.join(outDir, 'summary.json'), 'utf8'));
      const blocked = JSON.parse(fs.readFileSync(path.join(outDir, 'blocked.json'), 'utf8'));
      assert(summary.complete === false, `${item.name} must mark crawl incomplete`);
      if (item.expectedAttempts != null) {
        assert(
          summary.pagesAttempted === item.expectedAttempts,
          `${item.name} pagesAttempted mismatch: ${summary.pagesAttempted}`,
        );
      }
      assert(
        summary.stoppingReason === item.expectedReason,
        `${item.name} stoppingReason mismatch: ${summary.stoppingReason}`,
      );
      assert(
        summary.limitsReached.includes(item.expectedReason),
        `${item.name} missing limitsReached entry`,
      );
      assert(
        blocked.some((row) => row.reason === item.expectedBlocked),
        `${item.name} missing structured blocked row`,
      );
    }
  } finally {
    try { fs.rmSync(tmp, { recursive: true, force: true }); } catch { /* ignore */ }
  }
  return 'crawl_completeness_bounds';
}

async function testBrowserResponseLimits(base) {
  const probe = path.join(ROOT, 'scripts', 'playwright_probe.mjs');
  const extract = path.join(ROOT, 'scripts', 'playwright_extract.mjs');
  const crawl = path.join(ROOT, 'scripts', 'playwright_crawl.mjs');
  const tmp = ensureSmokeTmp('smoke-limits-');
  const assertStructuredLimit = (result, label) => {
    assert(result.code === 3, `${label} must exit 3, got ${result.code}: ${result.stderr}`);
    assert(
      /"error":"resource_limit"/.test(result.stderr) &&
        /"code":"http_max_bytes"/.test(result.stderr),
      `${label} did not emit a structured resource-limit blocker`,
    );
  };
  try {
    const probeOut = path.join(tmp, 'probe.json');
    const probeRun = await runNode(probe, [
      '--url', `${base}/large`,
      '--out', probeOut,
      '--wait-ms', '0',
      '--max-response-bytes', '1024',
      '--allow-loopback-fixture',
    ]);
    assertStructuredLimit(probeRun, 'probe');
    assert(!fs.existsSync(probeOut), 'probe wrote a successful output after a limit failure');

    const extractOut = path.join(tmp, 'extract.json');
    const extractRun = await runNode(extract, [
      '--url', `${base}/large`,
      '--out', extractOut,
      '--wait-ms', '0',
      '--max-response-bytes', '1024',
      '--allow-loopback-fixture',
    ]);
    assertStructuredLimit(extractRun, 'extract');
    assert(!fs.existsSync(extractOut), 'extract wrote a successful output after a limit failure');

    const crawlDir = path.join(tmp, 'crawl');
    const crawlRun = await runNode(crawl, [
      '--seed', `${base}/large`,
      '--outDir', crawlDir,
      '--maxPages', '1',
      '--delayMs', '0',
      '--max-response-bytes', '1024',
      '--allow-loopback-fixture',
    ]);
    assert(crawlRun.code === 3, `crawl must exit 3, got ${crawlRun.code}: ${crawlRun.stderr}`);
    const summary = JSON.parse(fs.readFileSync(path.join(crawlDir, 'summary.json'), 'utf8'));
    const blocked = JSON.parse(fs.readFileSync(path.join(crawlDir, 'blocked.json'), 'utf8'));
    assert(summary.complete === false, 'crawl limit failure must mark the run incomplete');
    assert(summary.resourceLimitExceeded === true, 'crawl did not record limit state');
    assert(
      blocked.some((row) => row.reason === 'resource_limit' && row.code === 'http_max_bytes'),
      'crawl did not write a structured resource-limit blocker',
    );
  } finally {
    try { fs.rmSync(tmp, { recursive: true, force: true }); } catch { /* ignore */ }
  }
  return 'browser_response_limits';
}

async function testBrowserReadOnlyMethods(fixture) {
  const { base, hits } = fixture;
  const extract = path.join(ROOT, 'scripts', 'playwright_extract.mjs');
  const tmp = ensureSmokeTmp('smoke-read-only-');
  const hitStart = hits.length;
  try {
    const out = path.join(tmp, 'extract.json');
    const result = await runNode(extract, [
      '--url', `${base}/post-page`,
      '--out', out,
      '--wait-ms', '500',
      '--allow-loopback-fixture',
    ]);
    assert(result.code === 0, `read-only extract failed: ${result.stderr}`);
    const output = JSON.parse(fs.readFileSync(out, 'utf8'));
    const newHits = hits.slice(hitStart);
    assert(
      !newHits.some((row) => row.path === '/mutate'),
      'page-originated POST reached the fixture server',
    );
    assert(
      output.ssrfStats?.blockedUrls?.some(
        (row) => row.reason === 'read_only_method_required' && row.method === 'POST',
      ),
      'blocked POST was not recorded in browser network accounting',
    );
  } finally {
    try { fs.rmSync(tmp, { recursive: true, force: true }); } catch { /* ignore */ }
  }
  return 'browser_read_only_methods';
}

async function testBrowserDynamicLimits(base) {
  const probe = path.join(ROOT, 'scripts', 'playwright_probe.mjs');
  const extract = path.join(ROOT, 'scripts', 'playwright_extract.mjs');
  const tmp = ensureSmokeTmp('smoke-dynamic-limits-');
  const expectLimit = async (script, endpoint, limit, expectedCode, label) => {
    const out = path.join(tmp, `${label}.json`);
    const result = await runNode(script, [
      '--url', `${base}${endpoint}`,
      '--out', out,
      '--wait-ms', '750',
      '--max-response-bytes', String(limit),
      '--allow-loopback-fixture',
    ]);
    assert(result.code === 3, `${label} must exit 3, got ${result.code}: ${result.stderr}`);
    assert(
      result.stderr.includes('"error":"resource_limit"') &&
        result.stderr.includes(`"code":"${expectedCode}"`),
      `${label} emitted the wrong structured limit: ${result.stderr}`,
    );
    assert(!fs.existsSync(out), `${label} wrote output after a limit failure`);
  };
  try {
    await expectLimit(
      extract,
      '/dom-expand',
      1024,
      'browser_output_max_bytes',
      'dom_output',
    );
    await expectLimit(
      probe,
      '/oversized-subresource',
      1024,
      'http_max_bytes',
      'subresource',
    );
    await expectLimit(
      probe,
      '/aggregate-page',
      1024,
      'browser_total_max_bytes',
      'aggregate',
    );
    await expectLimit(
      probe,
      '/request-fanout',
      1024 * 1024,
      'browser_max_requests',
      'request_count',
    );
  } finally {
    try { fs.rmSync(tmp, { recursive: true, force: true }); } catch { /* ignore */ }
  }
  return 'browser_dynamic_limits';
}

async function testRobotsStatuses() {
  const crawl = path.join(ROOT, 'scripts', 'playwright_crawl.mjs');
  const cases = [
    { status: 404, pages: 1, reason: null },
    { status: 403, pages: 0, reason: 'robots_auth_disallow' },
    { status: 429, pages: 0, reason: 'robots_rate_limited' },
    { status: 500, pages: 0, reason: 'robots_unknown' },
  ];
  for (const item of cases) {
    const fixture = await startRobotsStatusServer(item.status);
    const tmp = ensureSmokeTmp(`smoke-robots-${item.status}-`);
    try {
      const result = await runNode(crawl, [
        '--seed', `${fixture.base}/ok`,
        '--outDir', tmp,
        '--maxPages', '1',
        '--delayMs', '0',
        '--timeout', '5000',
        '--allow-loopback-fixture',
      ]);
      assert(result.code === 0, `robots ${item.status} crawl failed: ${result.stderr}`);
      const summary = JSON.parse(fs.readFileSync(path.join(tmp, 'summary.json'), 'utf8'));
      const blocked = JSON.parse(fs.readFileSync(path.join(tmp, 'blocked.json'), 'utf8'));
      assert(summary.pagesVisited === item.pages, `robots ${item.status} pages mismatch`);
      if (item.reason) {
        assert(blocked.some((row) => row.reason === item.reason), `robots ${item.status} reason mismatch`);
      }
    } finally {
      await new Promise((resolve) => fixture.server.close(resolve));
      try { fs.rmSync(tmp, { recursive: true, force: true }); } catch { /* ignore */ }
    }
  }
  return 'robots_status_mapping';
}

async function testCredentialRedirect() {
  // Two origins: A redirects to B. A credentialed fetch must hard-fail before
  // B receives any request or secret-bearing header.
  const api = path.join(ROOT, 'scripts', 'api_fetch.mjs');
  const sinkHits = [];
  const sink = http.createServer((req, res) => {
    sinkHits.push({ path: req.url, headers: { ...req.headers } });
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end('[]');
  });
  await new Promise((resolve) => sink.listen(0, '127.0.0.1', resolve));
  const sinkPort = sink.address().port;
  const source = http.createServer((_req, res) => {
    res.writeHead(302, { Location: `http://127.0.0.1:${sinkPort}/stolen` });
    res.end();
  });
  await new Promise((resolve) => source.listen(0, '127.0.0.1', resolve));
  const sourcePort = source.address().port;
  try {
    const r = await runNode(api, [
      '--url', `http://127.0.0.1:${sourcePort}/start`,
      '--headers', JSON.stringify({ 'X-Token': 'TOPSECRET' }),
      '--max-pages', '1',
      '--timeout', '5000',
    ]);
    const combined = `${r.stdout}\n${r.stderr}`;
    assert(r.code !== 0, 'credentialed cross-origin redirect unexpectedly succeeded');
    assert(!combined.includes('TOPSECRET'), 'credential leaked into output');
    assert(sinkHits.length === 0, 'cross-origin redirect destination received a request');
  } finally {
    await Promise.all([
      new Promise((resolve) => source.close(resolve)),
      new Promise((resolve) => sink.close(resolve)),
    ]);
  }
  return 'credential_redirect_zero_request';
}

async function testTlsDefaultFailureAndOptIn() {
  const extract = path.join(ROOT, 'scripts', 'playwright_extract.mjs');
  const probe = path.join(ROOT, 'scripts', 'playwright_probe.mjs');
  const crawl = path.join(ROOT, 'scripts', 'playwright_crawl.mjs');
  const tmp = ensureSmokeTmp('smoke-tls-');
  const fixture = await startTlsFixtureServer();
  try {
    const defaultOut = path.join(tmp, 'default.json');
    const defaultRun = await runNode(extract, [
      '--url', `${fixture.base}/ok`,
      '--format', 'json',
      '--out', defaultOut,
      '--timeout', '5000',
      '--wait-ms', '0',
      '--allow-loopback-fixture',
    ]);
    assert(defaultRun.code !== 0, 'self-signed TLS unexpectedly succeeded by default');
    assert(!fs.existsSync(defaultOut), 'default TLS failure wrote a successful extract');

    const extractOut = path.join(tmp, 'extract-opt-in.json');
    const extractRun = await runNode(extract, [
      '--url', `${fixture.base}/ok`,
      '--format', 'json',
      '--out', extractOut,
      '--timeout', '5000',
      '--wait-ms', '0',
      '--ignore-tls-errors',
      '--allow-loopback-fixture',
    ]);
    assert(extractRun.code === 0, `TLS extract opt-in failed: ${extractRun.stderr}`);
    const extractJson = JSON.parse(fs.readFileSync(extractOut, 'utf8'));
    assert(
      extractJson.limitations?.includes('ignore_tls_errors_enabled'),
      'TLS extract opt-in did not record limitation',
    );

    const probeOut = path.join(tmp, 'probe-opt-in.json');
    const probeRun = await runNode(probe, [
      '--url', `${fixture.base}/ok`,
      '--out', probeOut,
      '--timeout', '5000',
      '--wait-ms', '0',
      '--ignore-tls-errors',
      '--allow-loopback-fixture',
    ]);
    assert(probeRun.code === 0, `TLS probe opt-in failed: ${probeRun.stderr}`);
    const probeJson = JSON.parse(fs.readFileSync(probeOut, 'utf8'));
    assert(
      probeJson.limitations?.includes('ignore_tls_errors_enabled'),
      'TLS probe opt-in did not record limitation',
    );

    const crawlDir = path.join(tmp, 'crawl-opt-in');
    const crawlRun = await runNode(crawl, [
      '--seed', `${fixture.base}/ok`,
      '--outDir', crawlDir,
      '--maxPages', '1',
      '--delayMs', '0',
      '--timeout', '5000',
      '--ignore-tls-errors',
      '--allow-loopback-fixture',
    ]);
    assert(crawlRun.code === 0, `TLS crawl opt-in failed: ${crawlRun.stderr}`);
    const crawlSummary = JSON.parse(
      fs.readFileSync(path.join(crawlDir, 'summary.json'), 'utf8'),
    );
    assert(crawlSummary.pagesVisited === 1, 'TLS crawl opt-in did not visit fixture');
    assert(
      crawlSummary.limitations?.includes('ignore_tls_errors_enabled'),
      'TLS crawl opt-in did not record limitation',
    );
  } finally {
    await new Promise((resolve) => fixture.server.close(resolve));
    try { fs.rmSync(tmp, { recursive: true, force: true }); } catch { /* ignore */ }
  }
  return 'tls_default_failure_and_opt_in_limitation';
}

async function testLocalOnlyNavigation() {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ userAgent: UA });
    const page = await context.newPage();
    await page.goto('data:text/html,<html><body>local-nav-ok</body></html>');
    const t = await page.innerText('body');
    assert(t.includes('local-nav-ok'), 'local-only navigation failed');
  } finally {
    await browser.close();
  }
  return 'local_only_navigation';
}

async function testBrowserGuardAdversarial() {
  const trap = await startTrapServer();
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({
      userAgent: UA,
      serviceWorkers: 'block',
    });
    const stats = await installBrowserSsrfGuard(context, { timeoutMs: 5000 });
    const page = await context.newPage();
    page.on('pageerror', () => {});
    await page.setContent('<html><body><button id="popup">popup</button></body></html>');
    await page.evaluate((base) => {
      const img = document.createElement('img');
      img.src = `${base}/img`;
      document.body.appendChild(img);
      fetch(`${base}/fetch`).catch(() => {});
      try {
        const ws = new WebSocket(base.replace(/^http:/, 'ws:') + '/ws');
        ws.onerror = () => {};
      } catch {
        // blocked before construction is also acceptable.
      }
    }, trap.base);
    await Promise.all([
      context.waitForEvent('page', { timeout: 2000 }).catch(() => null),
      page.evaluate((url) => window.open(url), `${trap.base}/popup`),
    ]);
    await page.waitForTimeout(750);
    assert(trap.hits.length === 0, `private HTTP trap received ${trap.hits.length} request(s)`);
    assert(trap.upgrades.length === 0, 'private WebSocket trap received an upgrade');
    assert(stats.blocked >= 3, `expected browser guard blocks, got ${stats.blocked}`);
    assert(stats.websocketBlocked >= 1, 'websocket route was not fail-closed');
  } finally {
    await browser.close();
    await new Promise((resolve) => trap.server.close(resolve));
  }
  return 'browser_guard_adversarial';
}

async function testServiceWorkersBlocked(base) {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({
      userAgent: UA,
      serviceWorkers: 'block',
    });
    await installBrowserSsrfGuard(context, {
      allowLoopback: true,
      timeoutMs: 5000,
    });
    const page = await context.newPage();
    await page.goto(`${base}/sw-page`, { waitUntil: 'domcontentloaded', timeout: 5000 });
    const outcome = await page.evaluate(async () => {
      if (!('serviceWorker' in navigator)) return 'missing';
      try {
        await navigator.serviceWorker.register('/sw.js');
        await Promise.race([
          navigator.serviceWorker.ready,
          new Promise((resolve) => setTimeout(resolve, 500)),
        ]);
      } catch {
        // Registration rejection is an acceptable blocked outcome.
      }
      const response = await fetch('/sw-controlled');
      return response.text();
    });
    assert(outcome !== 'SW INTERCEPTED', 'service worker intercepted a request');
    assert(context.serviceWorkers().length === 0, 'context retained a service worker');
  } finally {
    await browser.close();
  }
  return 'service_workers_blocked';
}

async function main() {
  // API fixture servers are loopback-only. Browser fixture access is passed
  // explicitly with --allow-loopback-fixture in each browser helper call.
  if (process.env.D_RESEARCH_SSRF_ALLOW_LOOPBACK == null) {
    process.env.D_RESEARCH_SSRF_ALLOW_LOOPBACK = '1';
  }
  const results = [];
  const errors = [];

  try {
    results.push(await testRealChromiumLaunch());
  } catch (e) {
    errors.push(`chromium_launch: ${e.message}`);
  }

  try {
    results.push(await testLocalOnlyNavigation());
  } catch (e) {
    errors.push(`local_only: ${e.message}`);
  }

  try {
    results.push(await testBrowserGuardAdversarial());
  } catch (e) {
    errors.push(`browser_guard_adversarial: ${e.message}`);
  }

  let fixture;
  try {
    fixture = await startFixtureServer();
    try {
      results.push(await testProbeExtractCrawl(fixture.base));
    } catch (e) {
      errors.push(`probe_extract_crawl: ${e.message}`);
    }
    try {
      results.push(await testRobotsRedirect(fixture));
    } catch (e) {
      errors.push(`robots_redirect: ${e.message}`);
    }
    try {
      results.push(await testRobotsPercentEncoding(fixture));
    } catch (e) {
      errors.push(`robots_percent_encoding: ${e.message}`);
    }
    try {
      results.push(await testCrawlCompletenessBounds(fixture.base));
    } catch (e) {
      errors.push(`crawl_completeness_bounds: ${e.message}`);
    }
    try {
      results.push(await testBrowserResponseLimits(fixture.base));
    } catch (e) {
      errors.push(`browser_response_limits: ${e.message}`);
    }
    try {
      results.push(await testBrowserReadOnlyMethods(fixture));
    } catch (e) {
      errors.push(`browser_read_only_methods: ${e.message}`);
    }
    try {
      results.push(await testBrowserDynamicLimits(fixture.base));
    } catch (e) {
      errors.push(`browser_dynamic_limits: ${e.message}`);
    }
    try {
      results.push(await testServiceWorkersBlocked(fixture.base));
    } catch (e) {
      errors.push(`service_workers_blocked: ${e.message}`);
    }
    try {
      results.push(await testCredentialRedirect());
    } catch (e) {
      errors.push(`credential_redirect: ${e.message}`);
    }
  } finally {
    if (fixture?.server) fixture.server.close();
  }

  try {
    results.push(await testRobotsStatuses());
  } catch (e) {
    errors.push(`robots_statuses: ${e.message}`);
  }

  try {
    results.push(await testTlsDefaultFailureAndOptIn());
  } catch (e) {
    errors.push(`tls_contract: ${e.message}`);
  }

  if (errors.length) {
    console.error('browser_smoke FAILED:');
    for (const e of errors) console.error('  -', e);
    console.error('passed:', results.join(', '));
    process.exit(1);
  }
  console.log('browser_smoke ok:', results.join(', '));
  process.exit(0);
}

main().catch((e) => {
  console.error('browser_smoke FATAL:', e);
  process.exit(1);
});
