#!/usr/bin/env node

import { writeFileSync } from 'fs';
import {
  headersHaveCredentials,
  publicHeadersOnly,
  urlHasCredentials,
} from './lib/credentials.mjs';

const USER_AGENT = 'd-research-skill/0.3.0 (https://github.com/d-init-d/d-research-skill)';
const DEFAULT_MAX_RESPONSE_BYTES = 20 * 1024 * 1024;
const DEFAULT_TIMEOUT_MS = 30_000;
const MAX_REDIRECTS = 5;
const REDIRECT_STATUSES = new Set([301, 302, 303, 307, 308]);
let requestOverrides = {};

class ResourceLimitError extends Error {
  constructor(message, limit, observed = null) {
    super(message);
    this.name = 'ResourceLimitError';
    this.exitCode = 3;
    this.limit = limit;
    this.observed = observed;
  }
}

function parsePositiveInteger(value, label) {
  const raw = String(value ?? '').trim();
  if (!/^\d+$/.test(raw)) throw new Error(`${label} must be a positive integer`);
  const parsed = Number(raw);
  if (!Number.isSafeInteger(parsed) || parsed <= 0) {
    throw new Error(`${label} must be a positive safe integer`);
  }
  return parsed;
}

function redactSecrets(value) {
  let text = String(value ?? '');
  for (const name of ['BRAVE_API_KEY', 'GOOGLE_CSE_KEY', 'GOOGLE_CSE_ID']) {
    const secret = process.env[name];
    if (secret) text = text.split(secret).join('[REDACTED]');
  }
  text = text.replace(/([?&](?:key|cx|token|api_key)=)[^&\s]+/gi, '$1[REDACTED]');
  return text;
}

function activeLimits(overrides = {}) {
  return {
    maxBytes: overrides.maxResponseBytes ?? parsePositiveInteger(
      process.env.D_RESEARCH_HTTP_MAX_BYTES || DEFAULT_MAX_RESPONSE_BYTES,
      'D_RESEARCH_HTTP_MAX_BYTES'
    ),
    timeoutMs: overrides.timeoutMs ?? (
      parsePositiveInteger(
        process.env.D_RESEARCH_HTTP_TIMEOUT_SEC || (DEFAULT_TIMEOUT_MS / 1000),
        'D_RESEARCH_HTTP_TIMEOUT_SEC'
      ) * 1000
    )
  };
}

async function readResponseTextBounded(response, maxBytes) {
  const contentLength = response.headers?.get?.('content-length');
  if (contentLength && /^\d+$/.test(contentLength) && Number(contentLength) > maxBytes) {
    throw new ResourceLimitError(
      `HTTP response Content-Length ${contentLength} exceeds limit ${maxBytes}`,
      maxBytes,
      Number(contentLength)
    );
  }

  if (!response.body?.getReader) {
    const text = await response.text();
    const observed = Buffer.byteLength(text, 'utf8');
    if (observed > maxBytes) {
      throw new ResourceLimitError(
        `HTTP response body exceeds limit ${maxBytes}`,
        maxBytes,
        observed
      );
    }
    return text;
  }

  const reader = response.body.getReader();
  const chunks = [];
  let observed = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      observed += value.byteLength;
      if (observed > maxBytes) {
        await reader.cancel().catch(() => {});
        throw new ResourceLimitError(
          `HTTP response body exceeds limit ${maxBytes}`,
          maxBytes,
          observed
        );
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock?.();
  }
  const body = Buffer.concat(chunks.map(chunk => Buffer.from(chunk)));
  return body.toString('utf8');
}

function validateHttpUrl(value, base = undefined) {
  let parsed;
  try {
    parsed = base ? new URL(value, base) : new URL(value);
  } catch {
    throw new Error('redirect Location is not a valid URL');
  }
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error(`redirect scheme is not allowed: ${parsed.protocol}`);
  }
  if (parsed.username || parsed.password) {
    throw new Error('URL userinfo is not allowed');
  }
  return parsed;
}

async function fetchWithManualRedirects(url, options, timeoutMs) {
  let current = validateHttpUrl(url);
  let headers = { ...(options.headers || {}) };
  let credentialed = headersHaveCredentials(headers) || urlHasCredentials(current.href);

  for (let hop = 0; hop <= MAX_REDIRECTS; hop++) {
    const response = await fetch(current.href, {
      ...options,
      headers,
      redirect: 'manual',
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!REDIRECT_STATUSES.has(response.status)) return response;

    const location = response.headers?.get?.('location');
    try {
      await response.body?.cancel?.('manual redirect');
    } catch {
      /* ignore response cleanup failure */
    }
    if (!location) {
      throw new Error(`redirect without Location from ${current.origin}`);
    }
    if (hop >= MAX_REDIRECTS) {
      throw new Error(`too many redirects (>${MAX_REDIRECTS})`);
    }

    const next = validateHttpUrl(location, current.href);
    const crossOrigin = current.origin !== next.origin;
    if (
      crossOrigin &&
      (credentialed || headersHaveCredentials(headers) || urlHasCredentials(next.href))
    ) {
      throw new Error(`credentialed cross-origin redirect blocked: ${next.origin}`);
    }
    if (current.protocol === 'https:' && next.protocol !== 'https:') {
      throw new Error('HTTPS redirect downgrade blocked');
    }
    if (crossOrigin) headers = publicHeadersOnly(headers);
    credentialed = credentialed || urlHasCredentials(next.href);
    current = next;
  }
  throw new Error(`too many redirects (>${MAX_REDIRECTS})`);
}

async function fetchTextBounded(url, options = {}, overrides = requestOverrides) {
  const limits = activeLimits(overrides);
  const response = await fetchWithManualRedirects(url, options, limits.timeoutMs);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }
  return readResponseTextBounded(response, limits.maxBytes);
}

async function fetchJsonBounded(url, options = {}, overrides = requestOverrides) {
  const text = await fetchTextBounded(url, options, overrides);
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`Invalid JSON response: ${error.message}`);
  }
}

// ─── CLI Parser ──────────────────────────────────────────────────────────────

function parseArgs(argv) {
  const args = {
    engine: null,
    query: null,
    limit: 10,
    out: null,
    maxResponseBytes: null,
    timeoutMs: null,
    selfTest: false
  };

  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--engine' && i + 1 < argv.length) {
      args.engine = argv[++i];
    } else if (arg === '--query' && i + 1 < argv.length) {
      args.query = argv[++i];
    } else if (arg === '--limit' && i + 1 < argv.length) {
      args.limit = parsePositiveInteger(argv[++i], '--limit');
    } else if (arg === '--out' && i + 1 < argv.length) {
      args.out = argv[++i];
    } else if (arg === '--self-test') {
      args.selfTest = true;
    } else if (arg === '--max-response-bytes' && i + 1 < argv.length) {
      args.maxResponseBytes = parsePositiveInteger(argv[++i], '--max-response-bytes');
    } else if (arg === '--timeout-ms' && i + 1 < argv.length) {
      args.timeoutMs = parsePositiveInteger(argv[++i], '--timeout-ms');
    } else {
      throw new Error(`Unknown or incomplete option: ${arg}`);
    }
  }

  return args;
}

// ─── DuckDuckGo Engine ───────────────────────────────────────────────────────

async function searchDuckDuckGo(query, limit) {
  const url = `https://html.duckduckgo.com/html/?q=${encodeURIComponent(query)}`;
  const html = await fetchTextBounded(url, {
    headers: { 'User-Agent': USER_AGENT }
  });
  const results = [];

  // Parse result links: look for class="result__a" href and text
  const resultBlocks = html.split(/class="result__body"/);
  for (let i = 1; i < resultBlocks.length && results.length < limit; i++) {
    const block = resultBlocks[i];

    // Extract URL from result__a href
    const linkMatch = block.match(/class="result__a"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/);
    if (!linkMatch) continue;

    let href = linkMatch[1];
    const titleHtml = linkMatch[2];

    // DuckDuckGo wraps URLs in a redirect; extract the actual URL
    const uddgMatch = href.match(/uddg=([^&]+)/);
    if (uddgMatch) {
      href = decodeURIComponent(uddgMatch[1]);
    }

    // Strip HTML tags from title
    const title = titleHtml.replace(/<[^>]+>/g, '').trim();

    // Extract snippet from result__snippet
    const snippetMatch = block.match(/class="result__snippet"[^>]*>([\s\S]*?)<\/(?:a|span|div)/);
    const snippet = snippetMatch
      ? snippetMatch[1].replace(/<[^>]+>/g, '').trim()
      : '';

    if (title && href) {
      results.push({ title, url: href, snippet, source_engine: 'duckduckgo' });
    }
  }

  return results.slice(0, limit);
}

// ─── SearXNG Engine ──────────────────────────────────────────────────────────

async function searchSearXNG(query, limit) {
  const instance = process.env.SEARXNG_INSTANCE || 'https://searx.be';
  const url = `${instance}/search?q=${encodeURIComponent(query)}&format=json`;
  const data = await fetchJsonBounded(url, {
    headers: { 'User-Agent': USER_AGENT }
  });
  if (!data || !Array.isArray(data.results)) {
    throw new Error('Unexpected response format: missing results array');
  }

  return data.results.slice(0, limit).map(r => ({
    title: r.title || '',
    url: r.url || '',
    snippet: r.content || '',
    source_engine: 'searxng'
  }));
}

// ─── Brave Engine ────────────────────────────────────────────────────────────

async function searchBrave(query, limit) {
  const apiKey = process.env.BRAVE_API_KEY;
  if (!apiKey) {
    throw new Error('BRAVE_API_KEY environment variable is required for Brave engine');
  }

  const url = `https://api.search.brave.com/res/v1/web/search?q=${encodeURIComponent(query)}&count=${limit}`;
  const data = await fetchJsonBounded(url, {
    headers: {
      'User-Agent': USER_AGENT,
      'X-Subscription-Token': apiKey
    }
  });
  if (!data || !data.web || !Array.isArray(data.web.results)) {
    throw new Error('Unexpected response format: missing web.results array');
  }

  return data.web.results.slice(0, limit).map(r => ({
    title: r.title || '',
    url: r.url || '',
    snippet: r.description || '',
    source_engine: 'brave'
  }));
}

// ─── Google CSE Engine ───────────────────────────────────────────────────────

async function searchGoogleCSE(query, limit) {
  const cseKey = process.env.GOOGLE_CSE_KEY;
  const cseId = process.env.GOOGLE_CSE_ID;

  if (!cseKey && !cseId) {
    throw new Error('GOOGLE_CSE_KEY and GOOGLE_CSE_ID environment variables are required for Google CSE engine');
  }
  if (!cseKey) {
    throw new Error('GOOGLE_CSE_KEY environment variable is required for Google CSE engine');
  }
  if (!cseId) {
    throw new Error('GOOGLE_CSE_ID environment variable is required for Google CSE engine');
  }

  const num = Math.min(limit, 10); // Google CSE max 10 per request
  const url = `https://www.googleapis.com/customsearch/v1?q=${encodeURIComponent(query)}&key=${encodeURIComponent(cseKey)}&cx=${encodeURIComponent(cseId)}&num=${num}`;
  const data = await fetchJsonBounded(url, {
    headers: { 'User-Agent': USER_AGENT }
  });
  if (!data || !Array.isArray(data.items)) {
    // Google CSE returns no items array when there are zero results
    if (data && data.searchInformation && data.searchInformation.totalResults === '0') {
      return [];
    }
    throw new Error('Unexpected response format: missing items array');
  }

  return data.items.slice(0, limit).map(r => ({
    title: r.title || '',
    url: r.link || '',
    snippet: r.snippet || '',
    source_engine: 'google-cse'
  }));
}

// ─── Fallback Chain ──────────────────────────────────────────────────────────

async function runFallbackChain(query, limit) {
  const failures = [];

  // 1. DuckDuckGo (always available)
  try {
    const results = await searchDuckDuckGo(query, limit);
    return results;
  } catch (err) {
    if (err instanceof ResourceLimitError) throw err;
    const msg = `[duckduckgo] ${redactSecrets(err.message)}`;
    console.error(msg);
    failures.push(msg);
  }

  // 2. SearXNG (always available)
  try {
    const results = await searchSearXNG(query, limit);
    return results;
  } catch (err) {
    if (err instanceof ResourceLimitError) throw err;
    const msg = `[searxng] ${redactSecrets(err.message)}`;
    console.error(msg);
    failures.push(msg);
  }

  // 3. Brave (only if key is set)
  if (process.env.BRAVE_API_KEY) {
    try {
      const results = await searchBrave(query, limit);
      return results;
    } catch (err) {
      if (err instanceof ResourceLimitError) throw err;
      const msg = `[brave] ${redactSecrets(err.message)}`;
      console.error(msg);
      failures.push(msg);
    }
  }

  // 4. Google CSE (only if both keys are set)
  if (process.env.GOOGLE_CSE_KEY && process.env.GOOGLE_CSE_ID) {
    try {
      const results = await searchGoogleCSE(query, limit);
      return results;
    } catch (err) {
      if (err instanceof ResourceLimitError) throw err;
      const msg = `[google-cse] ${redactSecrets(err.message)}`;
      console.error(msg);
      failures.push(msg);
    }
  }

  // All engines failed
  console.error('Error: All search engines failed:');
  for (const f of failures) {
    console.error(`  ${f}`);
  }
  process.exit(1);
}

// ─── Self-Test ───────────────────────────────────────────────────────────────

async function runSelfTest() {
  let passed = 0;
  let failed = 0;
  const originalFetch = globalThis.fetch;
  const originalEnv = { ...process.env };

  function assert(condition, label) {
    if (condition) {
      passed++;
    } else {
      failed++;
      console.error(`  FAIL: ${label}`);
    }
  }

  try {
    parsePositiveInteger('12x', '--limit');
    assert(false, 'strict integer parser rejects trailing junk');
  } catch {
    assert(true, 'strict integer parser rejects trailing junk');
  }

  try {
    await readResponseTextBounded(
      { headers: { get: () => '20' }, text: async () => 'small' },
      10
    );
    assert(false, 'Content-Length cap is enforced');
  } catch (error) {
    assert(error instanceof ResourceLimitError, 'Content-Length cap is enforced');
  }

  process.env.GOOGLE_CSE_KEY = 'self-test-secret';
  assert(
    !redactSecrets('https://example.test/?key=self-test-secret').includes('self-test-secret'),
    'query secrets are redacted'
  );

  // Credential headers are retained only for same-origin hops. A cross-origin
  // redirect is rejected before the destination receives a request.
  process.env.BRAVE_API_KEY = 'brave-redirect-secret';
  let redirectCalls = [];
  globalThis.fetch = async (url, options) => {
    redirectCalls.push({ url: String(url), headers: { ...(options.headers || {}) }, redirect: options.redirect });
    if (redirectCalls.length === 1) {
      return {
        ok: false,
        status: 302,
        headers: { get: (name) => name.toLowerCase() === 'location' ? '/same-origin' : null },
        body: { cancel: async () => {} },
      };
    }
    return {
      ok: true,
      status: 200,
      headers: { get: () => null },
      text: async () => JSON.stringify({ web: { results: [] } }),
    };
  };
  try {
    await searchBrave('redirect test', 1);
    assert(redirectCalls.length === 2, 'same-origin redirect is followed manually');
    assert(
      redirectCalls.every((call) => call.redirect === 'manual'),
      'every redirect hop uses manual mode'
    );
    assert(
      redirectCalls[1]?.headers?.['X-Subscription-Token'] === 'brave-redirect-secret',
      'credential header is preserved on same-origin redirect'
    );
  } catch (error) {
    assert(false, `same-origin credential redirect succeeds: ${error.message}`);
  }

  redirectCalls = [];
  globalThis.fetch = async (url, options) => {
    redirectCalls.push({ url: String(url), headers: { ...(options.headers || {}) } });
    return {
      ok: false,
      status: 302,
      headers: { get: (name) => name.toLowerCase() === 'location' ? 'https://redirect.invalid/stolen' : null },
      body: { cancel: async () => {} },
    };
  };
  try {
    await searchBrave('redirect test', 1);
    assert(false, 'credentialed cross-origin redirect is blocked');
  } catch (error) {
    assert(
      redirectCalls.length === 1 && /credentialed cross-origin redirect blocked/.test(error.message),
      'credentialed cross-origin redirect is blocked before destination request'
    );
    assert(
      !error.message.includes('brave-redirect-secret'),
      'cross-origin redirect error does not expose credential'
    );
  }

  let loopCalls = 0;
  globalThis.fetch = async () => {
    loopCalls++;
    return {
      ok: false,
      status: 302,
      headers: { get: (name) => name.toLowerCase() === 'location' ? '/loop' : null },
      body: { cancel: async () => {} },
    };
  };
  try {
    await fetchTextBounded('https://loop.example/start');
    assert(false, 'redirect loop is bounded');
  } catch (error) {
    assert(
      loopCalls === MAX_REDIRECTS + 1 && /too many redirects/.test(error.message),
      'redirect loop is bounded'
    );
  }

  // Mock HTML for DuckDuckGo
  const mockDdgHtml = `
    <html><body>
    <div class="result__body">
      <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FNode.js&amp;rut=abc">
        <b>Node.js</b> - Wikipedia
      </a>
      <span class="result__snippet">Node.js is a cross-platform runtime environment.</span>
    </div>
    <div class="result__body">
      <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fnodejs.org&amp;rut=def">
        Node.js Official Site
      </a>
      <span class="result__snippet">Node.js is a JavaScript runtime built on V8.</span>
    </div>
    </body></html>
  `;

  // Mock JSON for SearXNG
  const mockSearxJson = {
    results: [
      { title: 'SearX Result 1', url: 'https://example.com/1', content: 'First result snippet' },
      { title: 'SearX Result 2', url: 'https://example.com/2', content: 'Second result snippet' }
    ]
  };

  // Mock JSON for Brave
  const mockBraveJson = {
    web: {
      results: [
        { title: 'Brave Result 1', url: 'https://brave.com/1', description: 'Brave snippet 1' },
        { title: 'Brave Result 2', url: 'https://brave.com/2', description: 'Brave snippet 2' }
      ]
    }
  };

  // Mock JSON for Google CSE
  const mockGcseJson = {
    items: [
      { title: 'Google Result 1', link: 'https://google.com/1', snippet: 'Google snippet 1' },
      { title: 'Google Result 2', link: 'https://google.com/2', snippet: 'Google snippet 2' }
    ]
  };

  // Install mock fetch
  globalThis.fetch = async (url, opts) => {
    const urlStr = typeof url === 'string' ? url : url.toString();

    if (urlStr.includes('html.duckduckgo.com')) {
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        text: async () => mockDdgHtml,
        json: async () => { throw new Error('Not JSON'); }
      };
    }

    if (urlStr.includes('/search?') && urlStr.includes('format=json')) {
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        text: async () => JSON.stringify(mockSearxJson),
        json: async () => mockSearxJson
      };
    }

    if (urlStr.includes('api.search.brave.com')) {
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        text: async () => JSON.stringify(mockBraveJson),
        json: async () => mockBraveJson
      };
    }

    if (urlStr.includes('googleapis.com/customsearch')) {
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        text: async () => JSON.stringify(mockGcseJson),
        json: async () => mockGcseJson
      };
    }

    // Default: return 500 for unknown URLs
    return {
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      text: async () => 'error',
      json: async () => ({ error: 'unknown' })
    };
  };

  // ── Test 1: DuckDuckGo parser ──
  console.log('  Test 1: DuckDuckGo engine');
  try {
    const results = await searchDuckDuckGo('node.js', 10);
    assert(Array.isArray(results), 'results is array');
    assert(results.length === 2, `got 2 results (got ${results.length})`);
    assert(results[0].source_engine === 'duckduckgo', 'source_engine is duckduckgo');
    assert(results[0].title.includes('Node.js'), 'title contains Node.js');
    assert(results[0].url === 'https://en.wikipedia.org/wiki/Node.js', 'url decoded correctly');
    assert(typeof results[0].snippet === 'string', 'snippet is string');
  } catch (err) {
    failed++;
    console.error(`  FAIL: DuckDuckGo test threw: ${err.message}`);
  }

  // ── Test 2: SearXNG parser ──
  console.log('  Test 2: SearXNG engine');
  try {
    process.env.SEARXNG_INSTANCE = 'https://mock-searx.example.com';
    const results = await searchSearXNG('test', 10);
    assert(Array.isArray(results), 'results is array');
    assert(results.length === 2, `got 2 results (got ${results.length})`);
    assert(results[0].source_engine === 'searxng', 'source_engine is searxng');
    assert(results[0].title === 'SearX Result 1', 'title matches');
    assert(results[0].url === 'https://example.com/1', 'url matches');
    assert(results[0].snippet === 'First result snippet', 'snippet matches');
  } catch (err) {
    failed++;
    console.error(`  FAIL: SearXNG test threw: ${err.message}`);
  }

  // ── Test 3: Brave parser ──
  console.log('  Test 3: Brave engine');
  try {
    process.env.BRAVE_API_KEY = 'test-key-123';
    const results = await searchBrave('test', 10);
    assert(Array.isArray(results), 'results is array');
    assert(results.length === 2, `got 2 results (got ${results.length})`);
    assert(results[0].source_engine === 'brave', 'source_engine is brave');
    assert(results[0].title === 'Brave Result 1', 'title matches');
    assert(results[0].url === 'https://brave.com/1', 'url matches');
    assert(results[0].snippet === 'Brave snippet 1', 'snippet matches');
  } catch (err) {
    failed++;
    console.error(`  FAIL: Brave test threw: ${err.message}`);
  }

  // ── Test 4: Google CSE parser ──
  console.log('  Test 4: Google CSE engine');
  try {
    process.env.GOOGLE_CSE_KEY = 'test-cse-key';
    process.env.GOOGLE_CSE_ID = 'test-cse-id';
    const results = await searchGoogleCSE('test', 10);
    assert(Array.isArray(results), 'results is array');
    assert(results.length === 2, `got 2 results (got ${results.length})`);
    assert(results[0].source_engine === 'google-cse', 'source_engine is google-cse');
    assert(results[0].title === 'Google Result 1', 'title matches');
    assert(results[0].url === 'https://google.com/1', 'url matches');
    assert(results[0].snippet === 'Google snippet 1', 'snippet matches');
  } catch (err) {
    failed++;
    console.error(`  FAIL: Google CSE test threw: ${err.message}`);
  }

  // ── Test 5: Fallback chain (DDG fails, SearXNG succeeds) ──
  console.log('  Test 5: Fallback chain (DDG fail → SearXNG success)');
  globalThis.fetch = async (url) => {
    const urlStr = typeof url === 'string' ? url : url.toString();

    if (urlStr.includes('html.duckduckgo.com')) {
      return { ok: false, status: 503, statusText: 'Service Unavailable' };
    }

    if (urlStr.includes('/search?') && urlStr.includes('format=json')) {
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        text: async () => JSON.stringify(mockSearxJson),
        json: async () => mockSearxJson
      };
    }

    return { ok: false, status: 500, statusText: 'Internal Server Error' };
  };

  try {
    // Clear keys so only DDG and SearXNG are tried
    delete process.env.BRAVE_API_KEY;
    delete process.env.GOOGLE_CSE_KEY;
    delete process.env.GOOGLE_CSE_ID;
    process.env.SEARXNG_INSTANCE = 'https://mock-searx.example.com';

    const results = await runFallbackChain('test', 10);
    assert(Array.isArray(results), 'results is array');
    assert(results.length === 2, `got 2 results (got ${results.length})`);
    assert(results[0].source_engine === 'searxng', 'fell back to searxng');
  } catch (err) {
    failed++;
    console.error(`  FAIL: Fallback chain test threw: ${err.message}`);
  }

  // ── Test 6: All engines fail ──
  console.log('  Test 6: All engines fail (exit non-zero)');
  globalThis.fetch = async () => {
    return { ok: false, status: 500, statusText: 'Internal Server Error' };
  };

  // Override process.exit to capture the call
  let exitCode = null;
  const originalExit = process.exit;
  process.exit = (code) => { exitCode = code; };

  try {
    delete process.env.BRAVE_API_KEY;
    delete process.env.GOOGLE_CSE_KEY;
    delete process.env.GOOGLE_CSE_ID;
    process.env.SEARXNG_INSTANCE = 'https://mock-searx.example.com';

    await runFallbackChain('test', 10);
    // If we get here without exit being called, that's also acceptable
    // since process.exit was mocked
  } catch (err) {
    // Expected path if process.exit throws
  }

  assert(exitCode === 1, `all-fail exits with code 1 (got ${exitCode})`);
  process.exit = originalExit;

  // ── Restore ──
  globalThis.fetch = originalFetch;
  // Restore env
  for (const key of Object.keys(process.env)) {
    if (!(key in originalEnv)) delete process.env[key];
  }
  Object.assign(process.env, originalEnv);

  // ── Summary ──
  console.log(`  ${passed} passed, ${failed} failed`);
  if (failed > 0) {
    console.error('web_search self-test FAILED');
    process.exit(1);
  }
  console.log('web_search self-test ok');
}

// ─── Main ────────────────────────────────────────────────────────────────────

async function main() {
  const args = parseArgs(process.argv);
  requestOverrides = {
    maxResponseBytes: args.maxResponseBytes,
    timeoutMs: args.timeoutMs
  };

  if (args.selfTest) {
    await runSelfTest();
    return;
  }

  if (!args.query) {
    console.error('Error: --query is required');
    console.error('Usage: web_search.mjs --query "<q>" [--engine duckduckgo|searxng|brave|google-cse] [--limit N] [--max-response-bytes N] [--timeout-ms N] [--out <file>]');
    console.error('       web_search.mjs --self-test');
    process.exit(1);
  }

  let results;

  if (args.engine) {
    try {
      switch (args.engine) {
        case 'duckduckgo':
          results = await searchDuckDuckGo(args.query, args.limit);
          break;
        case 'searxng':
          results = await searchSearXNG(args.query, args.limit);
          break;
        case 'brave':
          results = await searchBrave(args.query, args.limit);
          break;
        case 'google-cse':
          results = await searchGoogleCSE(args.query, args.limit);
          break;
        default:
          console.error(`Error: Unknown engine "${args.engine}". Valid: duckduckgo, searxng, brave, google-cse`);
          process.exit(1);
      }
    } catch (err) {
      if (err instanceof ResourceLimitError) throw err;
      console.error(`[${args.engine}] ${redactSecrets(err.message)}`);
      process.exit(1);
    }
  } else {
    results = await runFallbackChain(args.query, args.limit);
  }

  const output = JSON.stringify(results, null, 2);

  if (args.out) {
    writeFileSync(args.out, output);
    console.error(`Results written to: ${args.out}`);
  } else {
    console.log(output);
  }
}

main().catch(err => {
  if (err instanceof ResourceLimitError) {
    console.error(JSON.stringify({
      error: 'resource_limit',
      code: 'http_response_bytes',
      message: redactSecrets(err.message),
      limit: err.limit,
      observed: err.observed,
      incomplete: true,
      complete: false
    }));
    process.exit(3);
  }
  console.error(`Error: ${redactSecrets(err.message)}`);
  process.exit(1);
});
