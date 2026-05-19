#!/usr/bin/env node

import { writeFileSync } from 'fs';
import { getCachePath, getCached, putCache } from './lib/http_cache.mjs';

// parseArgs function
function parseArgs(argv) {
  const args = {
    url: null,
    headers: {},
    params: {},
    pagination: 'auto',
    maxPages: 10,
    delay: 500,
    out: null,
    format: 'json',
    timeout: 30000,
    selfTest: false
  };

  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--url' && i + 1 < argv.length) {
      args.url = argv[++i];
    } else if (arg === '--headers' && i + 1 < argv.length) {
      try {
        args.headers = JSON.parse(argv[++i]);
      } catch {
        console.error('Invalid JSON in --headers');
      }
    } else if (arg === '--params' && i + 1 < argv.length) {
      try {
        args.params = JSON.parse(argv[++i]);
      } catch {
        console.error('Invalid JSON in --params');
      }
    } else if (arg === '--pagination' && i + 1 < argv.length) {
      args.pagination = argv[++i];
    } else if (arg === '--max-pages' && i + 1 < argv.length) {
      args.maxPages = parseInt(argv[++i], 10);
    } else if (arg === '--delay' && i + 1 < argv.length) {
      args.delay = parseInt(argv[++i], 10);
    } else if (arg === '--out' && i + 1 < argv.length) {
      args.out = argv[++i];
    } else if (arg === '--format' && i + 1 < argv.length) {
      args.format = argv[++i];
    } else if (arg === '--timeout' && i + 1 < argv.length) {
      args.timeout = parseInt(argv[++i], 10);
    } else if (arg === '--self-test') {
      args.selfTest = true;
    }
  }

  return args;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function applyParams(url, params) {
  if (!params || Object.keys(params).length === 0) return url;
  const urlObj = new URL(url);
  for (const [key, value] of Object.entries(params)) {
    urlObj.searchParams.set(key, value);
  }
  return urlObj.toString();
}

function detectPagination(response, body, _paginationMode) {
  // Check Link header for 'next' relation
  const linkHeader = response.headers.get ? response.headers.get('link') : null;
  let nextUrl = null;

  if (linkHeader) {
    const nextMatch = linkHeader.match(/<([^>]+)>;\s*rel="next"/);
    if (nextMatch) {
      nextUrl = nextMatch[1];
    }
  }

  if (nextUrl) {
    return { type: 'link-header', nextUrl };
  }

  let parsedBody;
  if (typeof body === 'string') {
    try {
      parsedBody = JSON.parse(body);
    } catch {
      return null;
    }
  } else {
    parsedBody = body;
  }

  if (parsedBody && typeof parsedBody === 'object') {
    if (parsedBody.next_cursor || parsedBody.nextCursor || parsedBody.next_cursor_token) {
      return {
        type: 'cursor',
        nextCursor: parsedBody.next_cursor || parsedBody.nextCursor || parsedBody.next_cursor_token,
      };
    }

    if (parsedBody.next_page_token) {
      return { type: 'cursor', nextCursor: parsedBody.next_page_token };
    }

    if (typeof parsedBody.offset === 'number' && typeof parsedBody.total === 'number') {
      const currentOffset = parsedBody.offset;
      const pageSize = parsedBody.limit || parsedBody.page_size || 10;
      const nextOffset = currentOffset + pageSize;

      if (nextOffset < parsedBody.total) {
        return { type: 'offset', nextOffset };
      }
    }

    if (parsedBody.page && parsedBody.total_pages) {
      const nextPage = parsedBody.page + 1;
      if (nextPage <= parsedBody.total_pages) {
        return { type: 'page', nextPage };
      }
    }
  }

  return null;
}

async function fetchWithCache(url, options, maxRetries = 3) {
  let lastError;
  const method = (options && options.method) || 'GET';
  const requestHeaders = (options && options.headers) || {};
  const cacheEnabled = getCachePath() !== null;
  const isGet = method.toUpperCase() === 'GET';

  // Cache lookup (GET only). Cache key includes auth-affecting headers.
  if (cacheEnabled && isGet) {
    try {
      const cached = getCached(method, url, { requestHeaders });
      if (cached) {
        const headers = new Headers(cached.headers || {});
        return new Response(cached.body, { status: cached.status, headers });
      }
    } catch {
      // Cache failures are non-fatal
    }
  }

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      const response = await fetch(url, options);

      if (response.status === 429) {
        const retryAfter = response.headers.get('Retry-After');
        const rateLimitReset = response.headers.get('X-RateLimit-Reset');

        let waitTime = 1000 * Math.pow(2, attempt);

        if (retryAfter) {
          waitTime = parseInt(retryAfter, 10) * 1000;
        } else if (rateLimitReset) {
          const resetTime = parseInt(rateLimitReset, 10) * 1000;
          waitTime = Math.max(waitTime, resetTime - Date.now());
        }

        console.log(`Rate limited. Waiting ${waitTime}ms before retry...`);
        await sleep(waitTime);
        continue;
      }

      if (response.status >= 500) {
        const waitTime = 1000 * Math.pow(2, attempt);
        console.log(`Server error (${response.status}). Retrying in ${waitTime}ms...`);
        await sleep(waitTime);
        continue;
      }

      return response;
    } catch (error) {
      lastError = error;
      const waitTime = 1000 * Math.pow(2, attempt);
      console.log(`Request failed: ${error.message}. Retrying in ${waitTime}ms...`);
      await sleep(waitTime);
    }
  }

  throw lastError || new Error('Max retries exceeded');
}

function updateUrlWithCursor(url, cursor) {
  const urlObj = new URL(url);
  urlObj.searchParams.set('cursor', cursor);
  return urlObj.toString();
}

function updateUrlWithOffset(url, offset) {
  const urlObj = new URL(url);
  urlObj.searchParams.set('offset', offset);
  return urlObj.toString();
}

function updateUrlWithPage(url, page) {
  const urlObj = new URL(url);
  urlObj.searchParams.set('page', page);
  return urlObj.toString();
}

async function main() {
  const args = parseArgs(process.argv);

  if (args.selfTest) {
    await runSelfTest();
    return;
  }

  if (!args.url) {
    console.error('Error: --url is required');
    console.error('Usage: node api_fetch.mjs --url <url> [--headers <json>] [--params <json>] [--pagination auto|offset|cursor|page|link-header] [--max-pages <n>] [--delay <ms>] [--out <file>] [--format json|jsonl] [--timeout <ms>]');
    process.exit(1);
  }

  // Apply params to the initial URL before cache lookup so the cache key
  // reflects the final URL including all query parameters.
  const initialUrl = applyParams(args.url, args.params);

  console.log(`Starting fetch from: ${initialUrl}`);
  console.log(`Pagination mode: ${args.pagination}`);
  console.log(`Max pages: ${args.maxPages}`);

  const allItems = [];
  let currentUrl = initialUrl;
  let page = 1;
  let hasMorePages = true;

  while (hasMorePages && page <= args.maxPages) {
    console.log(`Fetching page ${page}...`);

    const fetchOptions = {
      method: 'GET',
      headers: args.headers,
    };

    try {
      const response = await fetchWithCache(currentUrl, fetchOptions, 3);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const body = await response.json();

      // Store in cache (GET only, when enabled). Auth headers are hashed
      // into the key but never persisted in cache metadata.
      if (getCachePath() !== null) {
        try {
          const headersObj = {};
          response.headers.forEach((v, k) => { headersObj[k] = v; });
          putCache('GET', currentUrl, response.status, headersObj, JSON.stringify(body), {
            requestHeaders: fetchOptions.headers,
          });
        } catch {
          // Non-fatal
        }
      }

      const paginationInfo = detectPagination(response, body, args.pagination);

      let items = [];
      if (Array.isArray(body)) {
        items = body;
      } else if (body.data && Array.isArray(body.data)) {
        items = body.data;
      } else if (body.results && Array.isArray(body.results)) {
        items = body.results;
      } else if (body.items && Array.isArray(body.items)) {
        items = body.items;
      }

      allItems.push(...items);

      if (paginationInfo) {
        switch (paginationInfo.type) {
          case 'link-header':
            currentUrl = paginationInfo.nextUrl;
            break;
          case 'cursor':
            currentUrl = updateUrlWithCursor(initialUrl, paginationInfo.nextCursor);
            break;
          case 'offset':
            currentUrl = updateUrlWithOffset(initialUrl, paginationInfo.nextOffset);
            break;
          case 'page':
            currentUrl = updateUrlWithPage(initialUrl, paginationInfo.nextPage);
            break;
        }
      } else {
        hasMorePages = false;
      }

      if (args.delay > 0 && page < args.maxPages) {
        await sleep(args.delay);
      }

      page++;
    } catch (error) {
      console.error(`Error fetching page ${page}: ${error.message}`);
      break;
    }
  }

  console.log(`Fetched ${allItems.length} total items across ${page - 1} pages.`);

  if (args.out) {
    const output = args.format === 'jsonl'
      ? allItems.map(item => JSON.stringify(item)).join('\n')
      : JSON.stringify(allItems, null, 2);

    writeFileSync(args.out, output);
    console.log(`Results written to: ${args.out}`);
  } else {
    console.log(JSON.stringify(allItems, null, 2));
  }
}

async function runSelfTest() {
  const { mkdtempSync, rmSync, existsSync, readdirSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const { join } = await import('node:path');

  console.log('Running self-tests...');
  const errors = [];

  // Test parseArgs
  const testArgs = parseArgs([
    'node', 'api_fetch.mjs',
    '--url', 'https://api.example.com/data',
    '--headers', '{"Authorization": "Bearer token123"}',
    '--params', '{"limit": 100}',
    '--pagination', 'cursor',
    '--max-pages', '5',
    '--delay', '1000',
    '--out', 'output.json',
    '--format', 'jsonl',
    '--timeout', '15000',
  ]);
  if (testArgs.url !== 'https://api.example.com/data') errors.push('parseArgs URL mismatch');
  if (testArgs.headers.Authorization !== 'Bearer token123') errors.push('parseArgs headers mismatch');
  if (testArgs.params.limit !== 100) errors.push('parseArgs params mismatch');

  // Test applyParams
  const u1 = applyParams('https://api.example.com/data', { limit: 100, q: 'foo' });
  if (!u1.includes('limit=100') || !u1.includes('q=foo')) errors.push('applyParams missing params');

  // Test detectPagination Link header
  const mockResponse1 = { headers: { get: (n) => n.toLowerCase() === 'link' ? '<https://api.example.com/next>; rel="next"' : null } };
  const p1 = detectPagination(mockResponse1, {}, 'auto');
  if (!p1 || p1.type !== 'link-header') errors.push('Link header pagination not detected');

  const mockResponse2 = { headers: { get: () => null } };
  const p2 = detectPagination(mockResponse2, { next_cursor: 'abc123', data: [1, 2, 3] }, 'auto');
  if (!p2 || p2.type !== 'cursor') errors.push('Cursor pagination not detected');

  const p3 = detectPagination(mockResponse2, { offset: 0, total: 100, limit: 10, data: [1] }, 'auto');
  if (!p3 || p3.type !== 'offset') errors.push('Offset pagination not detected');

  // Cache integration tests with isolated cache dir
  const savedEnv = process.env.D_RESEARCH_HTTP_CACHE_PATH;
  delete process.env.D_RESEARCH_HTTP_CACHE_PATH;
  const tmpDir = mkdtempSync(join(tmpdir(), 'api_fetch_test_'));
  const cacheDir = join(tmpDir, 'cache');
  process.env.D_RESEARCH_HTTP_CACHE_PATH = cacheDir;

  try {
    const url = 'https://example.invalid/api?q=alpha';

    // Stash entries with different Authorization headers
    putCache('GET', url, 200, { 'content-type': 'application/json' }, '{"who":"alice"}', {
      requestHeaders: { Authorization: 'Bearer A' },
    });
    putCache('GET', url, 200, { 'content-type': 'application/json' }, '{"who":"bob"}', {
      requestHeaders: { Authorization: 'Bearer B' },
    });
    putCache('GET', url, 200, { 'content-type': 'application/json' }, '{"who":"public"}');

    // Get with Bearer A returns alice
    const ga = getCached('GET', url, { requestHeaders: { Authorization: 'Bearer A' } });
    if (!ga || ga.body.toString('utf-8') !== '{"who":"alice"}') {
      errors.push('cache: Bearer A should return alice');
    }
    // Get with Bearer B returns bob
    const gb = getCached('GET', url, { requestHeaders: { Authorization: 'Bearer B' } });
    if (!gb || gb.body.toString('utf-8') !== '{"who":"bob"}') {
      errors.push('cache: Bearer B should return bob');
    }
    // Get with no auth returns public
    const gn = getCached('GET', url);
    if (!gn || gn.body.toString('utf-8') !== '{"who":"public"}') {
      errors.push('cache: no-auth should return public entry');
    }
    // Get with Bearer C is a miss (not aliased to Bearer A)
    const gc = getCached('GET', url, { requestHeaders: { Authorization: 'Bearer C' } });
    if (gc !== null) errors.push('cache: Bearer C should be a miss');

    // params change cache key (different URL = different key)
    const urlBeta = 'https://example.invalid/api?q=beta';
    const gBeta = getCached('GET', urlBeta);
    if (gBeta !== null) errors.push('cache: changing params should miss');

    // Verify metadata never stores Authorization
    const entriesDir = join(cacheDir, 'entries');
    if (existsSync(entriesDir)) {
      const { readFileSync } = await import('node:fs');
      for (const name of readdirSync(entriesDir)) {
        if (!name.endsWith('.json')) continue;
        const meta = JSON.parse(readFileSync(join(entriesDir, name), 'utf-8'));
        const headers = meta.headers || {};
        for (const k of Object.keys(headers)) {
          if (k.toLowerCase() === 'authorization' || k.toLowerCase() === 'cookie') {
            errors.push(`cache metadata leaks request header ${k}`);
          }
        }
      }
    }
  } finally {
    delete process.env.D_RESEARCH_HTTP_CACHE_PATH;
    if (savedEnv !== undefined) process.env.D_RESEARCH_HTTP_CACHE_PATH = savedEnv;
    try { rmSync(tmpDir, { recursive: true, force: true }); } catch { /* ignore */ }
  }

  if (errors.length) {
    console.error('api_fetch self-test FAILED:');
    for (const e of errors) console.error(`  - ${e}`);
    process.exit(1);
  }
  console.log('api_fetch self-test ok');
}

// Run the main function
main().catch((err) => {
  console.error(err);
  process.exit(1);
});
