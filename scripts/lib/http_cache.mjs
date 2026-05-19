// Node ESM helper for shared HTTP cache.
// Enables only when D_RESEARCH_HTTP_CACHE_PATH is set.
// Uses same on-disk layout as scripts/http_cache.py for cross-runtime compat.
//
// Cache key inputs:
//   - method (uppercased)
//   - URL (final, including all query params)
//   - requestKey: canonical string of request-shaping inputs that may change
//     the response (Authorization, Cookie, X-API-Key, API-Key, Accept,
//     Accept-Language, request-body for POST). Hashed into the key only —
//     never stored in metadata.
//   - bodyKey: optional explicit body key material for POST requests
//
// Headers stored in metadata are RESPONSE headers, not request headers.

import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, readdirSync, unlinkSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const CACHE_ENV = 'D_RESEARCH_HTTP_CACHE_PATH';
export const DEFAULT_MAX_AGE_SECONDS = 7 * 24 * 3600;

// Headers that affect response shape and must be hashed into the cache key.
// Listed in lowercase for case-insensitive comparison.
export const KEY_AFFECTING_HEADERS = [
  'authorization',
  'cookie',
  'x-api-key',
  'api-key',
  'accept',
  'accept-language',
];

export function getCachePath() {
  const val = (process.env[CACHE_ENV] || '').trim();
  return val || null;
}

/**
 * Build a canonical string of key-affecting headers from a headers object.
 * Headers are lowercased, sorted, and joined as "name:value" lines.
 * Only KEY_AFFECTING_HEADERS are included.
 */
export function canonicalHeaderKey(headers) {
  if (!headers) return '';
  const normalized = {};
  // Accept either a plain object or a Headers instance
  if (typeof headers.forEach === 'function' && typeof headers.get === 'function') {
    headers.forEach((v, k) => { normalized[k.toLowerCase()] = String(v); });
  } else {
    for (const [k, v] of Object.entries(headers)) {
      normalized[k.toLowerCase()] = String(v);
    }
  }
  const lines = [];
  for (const name of KEY_AFFECTING_HEADERS) {
    if (name in normalized) {
      lines.push(`${name}:${normalized[name]}`);
    }
  }
  return lines.sort().join('\n');
}

export function cacheKey(method, url, opts = {}) {
  const h = createHash('sha256');
  h.update(method.toUpperCase());
  h.update('\n');
  h.update(url);
  if (opts.requestKey) {
    h.update('\n');
    h.update(opts.requestKey);
  }
  if (opts.bodyKey !== undefined && opts.bodyKey !== null) {
    h.update('\n');
    h.update(typeof opts.bodyKey === 'string' ? opts.bodyKey : Buffer.from(opts.bodyKey));
  }
  return h.digest('hex');
}

function ensureCacheDir(cacheDir) {
  if (!existsSync(cacheDir)) mkdirSync(cacheDir, { recursive: true });
  const entries = join(cacheDir, 'entries');
  if (!existsSync(entries)) mkdirSync(entries, { recursive: true });
}

/**
 * Look up a cached response.
 * @param {string} method
 * @param {string} url - Final URL with query string applied
 * @param {object} opts - { requestHeaders, bodyKey, maxAge, cacheDir }
 */
export function getCached(method, url, opts = {}) {
  const cacheDir = opts.cacheDir || getCachePath();
  if (!cacheDir) return null;
  const requestKey = opts.requestKey ?? canonicalHeaderKey(opts.requestHeaders);
  const key = cacheKey(method, url, { requestKey, bodyKey: opts.bodyKey });
  const metaPath = join(cacheDir, 'entries', `${key}.json`);
  const bodyPath = join(cacheDir, 'entries', `${key}.body`);
  if (!existsSync(metaPath)) return null;
  let meta;
  try {
    meta = JSON.parse(readFileSync(metaPath, 'utf-8'));
  } catch {
    return null;
  }
  const maxAge = opts.maxAge ?? DEFAULT_MAX_AGE_SECONDS;
  const age = Date.now() / 1000 - (meta.created_at || 0);
  if (age > maxAge) return null;

  let bodyBytes = Buffer.alloc(0);
  if (existsSync(bodyPath)) {
    bodyBytes = readFileSync(bodyPath);
  }
  return {
    key,
    url: meta.url || url,
    method: meta.method || method,
    status: meta.status || 200,
    headers: meta.headers || {},
    created_at: meta.created_at || 0,
    body: bodyBytes,
  };
}

/**
 * Store a response in the cache.
 * @param {string} method
 * @param {string} url
 * @param {number} status
 * @param {object} responseHeaders - Response headers to persist in metadata
 * @param {Buffer|string} body - Response body bytes
 * @param {object} opts - { requestHeaders|requestKey, bodyKey, cacheDir }
 *
 * Note: request headers are NEVER stored in metadata. They are only hashed
 * into the cache key via requestKey. This prevents leaking auth tokens.
 */
export function putCache(method, url, status, responseHeaders, body, opts = {}) {
  const cacheDir = opts.cacheDir || getCachePath();
  if (!cacheDir) return null;
  ensureCacheDir(cacheDir);
  const requestKey = opts.requestKey ?? canonicalHeaderKey(opts.requestHeaders);
  const key = cacheKey(method, url, { requestKey, bodyKey: opts.bodyKey });
  const meta = {
    key,
    url,
    method: method.toUpperCase(),
    status,
    headers: responseHeaders || {},
    created_at: Math.floor(Date.now() / 1000),
  };
  const metaPath = join(cacheDir, 'entries', `${key}.json`);
  const bodyPath = join(cacheDir, 'entries', `${key}.body`);
  writeFileSync(metaPath, JSON.stringify(meta, null, 2), 'utf-8');
  writeFileSync(bodyPath, typeof body === 'string' ? Buffer.from(body, 'utf-8') : body);
  return key;
}

export function purgeCache(opts = {}) {
  const cacheDir = opts.cacheDir || getCachePath();
  if (!cacheDir) return 0;
  const entriesDir = join(cacheDir, 'entries');
  if (!existsSync(entriesDir)) return 0;
  const purgeAll = opts.all === true;
  const maxAge = opts.maxAge ?? DEFAULT_MAX_AGE_SECONDS;
  const now = Date.now() / 1000;
  let purged = 0;
  for (const name of readdirSync(entriesDir)) {
    if (!name.endsWith('.json')) continue;
    const metaPath = join(entriesDir, name);
    const bodyPath = metaPath.replace(/\.json$/, '.body');
    let shouldPurge = purgeAll;
    if (!shouldPurge) {
      try {
        const meta = JSON.parse(readFileSync(metaPath, 'utf-8'));
        const age = now - (meta.created_at || 0);
        if (age > maxAge) shouldPurge = true;
      } catch {
        shouldPurge = true;
      }
    }
    if (shouldPurge) {
      try { unlinkSync(metaPath); } catch {}
      try { unlinkSync(bodyPath); } catch {}
      purged++;
    }
  }
  return purged;
}

// ---------------------------------------------------------------------------
// Self-test
// ---------------------------------------------------------------------------

async function selfTest() {
  const { mkdtempSync, rmSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const errors = [];

  const tmpDir = mkdtempSync(join(tmpdir(), 'http_cache_test_'));
  const cd = join(tmpDir, 'cache');

  try {
    // Test 1: getCachePath returns null when env not set
    delete process.env[CACHE_ENV];
    if (getCachePath() !== null) errors.push('getCachePath should be null when env not set');

    // Test 2: cacheKey deterministic
    const k1 = cacheKey('GET', 'https://example.com/api');
    const k2 = cacheKey('GET', 'https://example.com/api');
    if (k1 !== k2) errors.push('cacheKey not deterministic');

    // Test 3: different URLs → different keys
    const k3 = cacheKey('GET', 'https://example.com/other');
    if (k1 === k3) errors.push('cacheKey collision');

    // Test 4: same URL different Authorization → different keys
    const kA = cacheKey('GET', 'https://example.com/api', {
      requestKey: canonicalHeaderKey({ Authorization: 'Bearer A' }),
    });
    const kB = cacheKey('GET', 'https://example.com/api', {
      requestKey: canonicalHeaderKey({ Authorization: 'Bearer B' }),
    });
    if (kA === kB) errors.push('different Authorization should produce different cache keys');
    if (kA === k1) errors.push('Authorization should differ from no-auth key');

    // Test 5: cookie also affects key
    const kCookie = cacheKey('GET', 'https://example.com/api', {
      requestKey: canonicalHeaderKey({ Cookie: 'session=abc' }),
    });
    if (kCookie === k1) errors.push('Cookie should affect cache key');

    // Test 6: non-key headers (User-Agent) do not affect key
    const kUA = cacheKey('GET', 'https://example.com/api', {
      requestKey: canonicalHeaderKey({ 'User-Agent': 'test' }),
    });
    if (kUA !== k1) errors.push('User-Agent should not affect cache key');

    // Test 7: getCached miss
    process.env[CACHE_ENV] = cd;
    const miss = getCached('GET', 'https://example.com/missing');
    if (miss !== null) errors.push('getCached should return null on miss');

    // Test 8: putCache + getCached round-trip (no auth)
    const key = putCache('GET', 'https://example.com/api', 200, { 'content-type': 'application/json' }, '{"hello":"world"}');
    if (!key) errors.push('putCache returned null');
    const hit = getCached('GET', 'https://example.com/api');
    if (!hit) {
      errors.push('getCached returned null after putCache');
    } else {
      if (hit.status !== 200) errors.push(`cached status wrong: ${hit.status}`);
      if (hit.body.toString('utf-8') !== '{"hello":"world"}') errors.push('cached body wrong');
    }

    // Test 9: putCache with Authorization stores under different key
    putCache('GET', 'https://example.com/api', 200,
      { 'content-type': 'application/json' }, '{"auth":"A"}',
      { requestHeaders: { Authorization: 'Bearer A' } });

    // Get with Authorization A → hits the auth-A entry
    const hitA = getCached('GET', 'https://example.com/api', {
      requestHeaders: { Authorization: 'Bearer A' },
    });
    if (!hitA || hitA.body.toString('utf-8') !== '{"auth":"A"}') {
      errors.push('cache hit with Authorization A should return auth-A response');
    }

    // Get with no Authorization → hits the no-auth entry (different body)
    const hitNoAuth = getCached('GET', 'https://example.com/api');
    if (!hitNoAuth || hitNoAuth.body.toString('utf-8') !== '{"hello":"world"}') {
      errors.push('cache hit without Authorization should return the no-auth entry, not Bearer A response');
    }

    // Get with Authorization B → cache miss (no entry stored for B)
    const hitB = getCached('GET', 'https://example.com/api', {
      requestHeaders: { Authorization: 'Bearer B' },
    });
    if (hitB !== null) {
      errors.push('cache hit with Authorization B should be null (not Bearer A response)');
    }

    // Test 10: response headers stored in metadata, not request headers
    const metaRaw = readFileSync(join(cd, 'entries', `${key}.json`), 'utf-8');
    const meta = JSON.parse(metaRaw);
    if ('Authorization' in (meta.headers || {}) || 'authorization' in (meta.headers || {})) {
      errors.push('metadata must not store request Authorization header');
    }

    // Test 11: TTL expiry
    const expired = getCached('GET', 'https://example.com/api', { maxAge: 0 });
    if (expired !== null) errors.push('getCached should return null when maxAge=0');

    // Test 12: purgeCache
    const purged = purgeCache({ all: true });
    if (purged < 1) errors.push(`purgeCache should remove >= 1 entry, got ${purged}`);
    const afterPurge = getCached('GET', 'https://example.com/api');
    if (afterPurge !== null) errors.push('entry still exists after purge --all');

    delete process.env[CACHE_ENV];
  } finally {
    try { rmSync(tmpDir, { recursive: true, force: true }); } catch {}
  }

  if (errors.length) {
    console.error('http_cache.mjs self-test FAILED:');
    for (const e of errors) console.error(`  - ${e}`);
    process.exit(1);
  }
  console.log('http_cache.mjs self-test ok');
}

// Only run self-test when this file is invoked directly with --self-test,
// not when imported by another script.
const isMainModule = process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1]);
if (isMainModule && process.argv.includes('--self-test')) {
  selfTest();
}
