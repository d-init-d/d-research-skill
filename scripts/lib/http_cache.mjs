// Node ESM helper for shared HTTP cache.
// Enables only when D_RESEARCH_HTTP_CACHE_PATH is set.
// Uses same on-disk layout as scripts/http_cache.py for cross-runtime compat.
//
// Atomic generation protocol:
//   - unique per-writer temp files: {key}.{gen}.body.tmp / {key}.{gen}.json.tmp
//   - publish body then meta via rename
//   - metadata carries body_sha256 + body_size + generation_id
//   - readers validate hash/size and never mix generations

import { createHash, randomBytes } from 'node:crypto';
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  unlinkSync,
  writeFileSync,
  chmodSync,
} from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { isSensitiveHeaderName, urlHasCredentials } from './credentials.mjs';

const CACHE_ENV = 'D_RESEARCH_HTTP_CACHE_PATH';
export const DEFAULT_MAX_AGE_SECONDS = 7 * 24 * 3600;

export const KEY_AFFECTING_HEADERS = [
  'authorization',
  'proxy-authorization',
  'cookie',
  'x-api-key',
  'api-key',
  'x-auth-token',
  'x-access-token',
  'x-token',
  'accept',
  'accept-language',
  'range',
];

export function getCachePath() {
  const val = (process.env[CACHE_ENV] || '').trim();
  return val || null;
}

export function canonicalHeaderKey(headers, extraKeyHeaders = []) {
  if (!headers) return '';
  const normalized = {};
  if (typeof headers.forEach === 'function' && typeof headers.get === 'function') {
    headers.forEach((v, k) => {
      normalized[k.toLowerCase()] = String(v);
    });
  } else {
    for (const [k, v] of Object.entries(headers)) {
      normalized[k.toLowerCase()] = String(v);
    }
  }
  const names = [...KEY_AFFECTING_HEADERS];
  for (const n of extraKeyHeaders || []) {
    const ln = String(n).toLowerCase();
    if (!names.includes(ln)) names.push(ln);
  }
  const lines = [];
  for (const name of names) {
    if (name in normalized) lines.push(`${name}:${normalized[name]}`);
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

function bodySha256(buf) {
  return createHash('sha256').update(buf).digest('hex');
}

function isAuthSecretHeader(name) {
  const n = String(name || '').toLowerCase();
  if (
    [
      'authorization',
      'proxy-authorization',
      'cookie',
      'set-cookie',
      'x-api-key',
      'api-key',
      'x-auth-token',
      'x-access-token',
      'x-token',
    ].includes(n)
  ) {
    return true;
  }
  return /(token|secret|credential|authori[sz]ation|authentication|api-?key|password|session|csrf|xsrf)/i.test(n);
}

function hasCredentialHeaders(headers) {
  if (!headers) return false;
  const keys =
    typeof headers.forEach === 'function'
      ? (() => {
          const out = [];
          headers.forEach((_, k) => out.push(k));
          return out;
        })()
      : Object.keys(headers);
  // Only auth secrets block caching — not Range/Accept representation headers.
  return keys.some((k) => isAuthSecretHeader(k));
}

function sanitizeResponseHeaders(headers) {
  const out = {};
  if (!headers) return out;
  for (const [k, v] of Object.entries(headers)) {
    if (isSensitiveHeaderName(k) || k.toLowerCase() === 'set-cookie') continue;
    out[k] = v;
  }
  return out;
}

function redactUrl(url) {
  try {
    const u = new URL(url);
    for (const key of [...u.searchParams.keys()]) {
      if (/^(access_token|api_key|apikey|token|key|auth|password|secret|credential)$/i.test(key)) {
        u.searchParams.set(key, '[REDACTED]');
      }
    }
    return u.toString();
  } catch {
    return String(url).replace(
      /([?&#]?(?:access_token|api_key|apikey|token|key|auth|password|secret)=)([^&#\s]*)/gi,
      '$1[REDACTED]'
    );
  }
}

export function getCached(method, url, opts = {}) {
  const cacheDir = opts.cacheDir || getCachePath();
  if (!cacheDir) return null;
  const extra = opts.extraKeyHeaders || [];
  const requestKey = opts.requestKey ?? canonicalHeaderKey(opts.requestHeaders, extra);
  const key = cacheKey(method, url, { requestKey, bodyKey: opts.bodyKey });
  const metaPath = join(cacheDir, 'entries', `${key}.json`);
  const bodyPath = join(cacheDir, 'entries', `${key}.body`);
  if (!existsSync(metaPath) || !existsSync(bodyPath)) return null;
  let meta;
  try {
    meta = JSON.parse(readFileSync(metaPath, 'utf-8'));
  } catch {
    return null;
  }
  const maxAge = opts.maxAge ?? DEFAULT_MAX_AGE_SECONDS;
  const age = Date.now() / 1000 - (meta.created_at || 0);
  if (age > maxAge) return null;
  const bodyBytes = readFileSync(bodyPath);
  if (meta.body_sha256 && meta.body_sha256 !== bodySha256(bodyBytes)) return null;
  if (meta.body_size != null && Number(meta.body_size) !== bodyBytes.length) return null;
  return {
    key,
    url: meta.url || url,
    method: meta.method || method,
    status: meta.status || 200,
    headers: meta.headers || {},
    created_at: meta.created_at || 0,
    body: bodyBytes,
    body_sha256: meta.body_sha256 || bodySha256(bodyBytes),
    generation_id: meta.generation_id,
  };
}

export function putCache(method, url, status, responseHeaders, body, opts = {}) {
  const cacheDir = opts.cacheDir || getCachePath();
  if (!cacheDir) return null;
  const requestHeaders = opts.requestHeaders || null;
  if (hasCredentialHeaders(requestHeaders) && !opts.allowPrivate) return null;
  if (urlHasCredentials(url) && !opts.allowPrivate) return null;

  const resp = {};
  for (const [k, v] of Object.entries(responseHeaders || {})) {
    resp[k.toLowerCase()] = String(v);
  }
  if ((resp.vary || '').trim() === '*') return null;

  const extra = [...(opts.extraKeyHeaders || [])];
  if (resp.vary) {
    for (const part of resp.vary.split(',')) {
      const name = part.trim().toLowerCase();
      if (name && !extra.includes(name)) extra.push(name);
    }
  }

  ensureCacheDir(cacheDir);
  const requestKey = opts.requestKey ?? canonicalHeaderKey(requestHeaders, extra);
  const key = cacheKey(method, url, { requestKey, bodyKey: opts.bodyKey });
  const bodyBuf = typeof body === 'string' ? Buffer.from(body, 'utf-8') : Buffer.from(body);
  const genId = randomBytes(16).toString('hex');
  const hash = bodySha256(bodyBuf);
  const meta = {
    key,
    url: redactUrl(url),
    method: method.toUpperCase(),
    status,
    headers: sanitizeResponseHeaders(responseHeaders || {}),
    created_at: Math.floor(Date.now() / 1000),
    body_sha256: hash,
    body_size: bodyBuf.length,
    generation_id: genId,
  };
  const entries = join(cacheDir, 'entries');
  const metaPath = join(entries, `${key}.json`);
  const bodyPath = join(entries, `${key}.body`);
  const tmpBody = join(entries, `${key}.${genId}.body.tmp`);
  const tmpMeta = join(entries, `${key}.${genId}.json.tmp`);
  try {
    writeFileSync(tmpBody, bodyBuf);
    writeFileSync(tmpMeta, JSON.stringify(meta, null, 2), 'utf-8');
    renameSync(tmpBody, bodyPath);
    renameSync(tmpMeta, metaPath);
    try {
      chmodSync(metaPath, 0o600);
      chmodSync(bodyPath, 0o600);
    } catch {
      /* windows */
    }
  } catch (e) {
    try {
      unlinkSync(tmpBody);
    } catch {
      /* ignore */
    }
    try {
      unlinkSync(tmpMeta);
    } catch {
      /* ignore */
    }
    throw e;
  }
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
    if (!name.endsWith('.json') || name.includes('.tmp')) continue;
    const metaPath = join(entriesDir, name);
    const bodyPath = metaPath.replace(/\.json$/, '.body');
    let shouldPurge = purgeAll;
    if (!shouldPurge) {
      try {
        const meta = JSON.parse(readFileSync(metaPath, 'utf-8'));
        if (now - (meta.created_at || 0) > maxAge) shouldPurge = true;
      } catch {
        shouldPurge = true;
      }
    }
    if (shouldPurge) {
      try {
        unlinkSync(metaPath);
      } catch {
        /* ignore */
      }
      try {
        unlinkSync(bodyPath);
      } catch {
        /* ignore */
      }
      purged++;
    }
  }
  return purged;
}

async function selfTest() {
  const { mkdtempSync, rmSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const errors = [];
  const tmpDir = mkdtempSync(join(tmpdir(), 'http_cache_test_'));
  const cd = join(tmpDir, 'cache');
  try {
    delete process.env[CACHE_ENV];
    if (getCachePath() !== null) errors.push('getCachePath should be null when env not set');

    const k1 = cacheKey('GET', 'https://example.com/api');
    if (k1 !== cacheKey('GET', 'https://example.com/api')) errors.push('cacheKey not deterministic');

    process.env[CACHE_ENV] = cd;
    const key = putCache('GET', 'https://example.com/api', 200, { 'content-type': 'application/json' }, '{"hello":"world"}');
    if (!key) errors.push('putCache returned null');
    const hit = getCached('GET', 'https://example.com/api');
    if (!hit || hit.body.toString('utf-8') !== '{"hello":"world"}') errors.push('round-trip failed');
    if (!hit.body_sha256) errors.push('missing body_sha256');

    // Range isolation
    putCache('GET', 'https://example.com/r', 206, {}, 'aaaa', { requestHeaders: { Range: 'bytes=0-3' } });
    putCache('GET', 'https://example.com/r', 206, {}, 'bbbb', { requestHeaders: { Range: 'bytes=4-7' } });
    const r0 = getCached('GET', 'https://example.com/r', { requestHeaders: { Range: 'bytes=0-3' } });
    const r1 = getCached('GET', 'https://example.com/r', { requestHeaders: { Range: 'bytes=4-7' } });
    if (!r0 || r0.body.toString() !== 'aaaa') errors.push('range 0-3 collision');
    if (!r1 || r1.body.toString() !== 'bbbb') errors.push('range 4-7 collision');

    // Vary:*
    if (putCache('GET', 'https://example.com/star', 200, { Vary: '*' }, 'x') !== null) {
      errors.push('Vary:* must not cache');
    }

    // Concurrent writers
    const { Worker, isMainThread, workerData, parentPort } = await import('node:worker_threads');
    // Use Promise.all of putCache calls (same process, concurrent async is single-threaded but
    // we can still stress rename races with many sequential+parallel promises).
    const urlC = 'https://example.com/concurrent';
    const jobs = [];
    for (let i = 0; i < 100; i++) {
      jobs.push(
        Promise.resolve().then(() =>
          putCache('GET', urlC, 200, { 'content-type': 'text/plain' }, `body-${i}`)
        )
      );
    }
    try {
      await Promise.all(jobs);
    } catch (e) {
      errors.push(`concurrent put exception: ${e.message || e}`);
    }
    const finalHit = getCached('GET', urlC);
    if (!finalHit) errors.push('concurrent final miss');
    else if (bodySha256(finalHit.body) !== finalHit.body_sha256) {
      errors.push('concurrent body/meta hash mismatch');
    }

    const refused = putCache('GET', 'https://example.com/api', 200, {}, 'x', {
      requestHeaders: { 'X-Token': 'TOPSECRET' },
    });
    if (refused !== null) errors.push('X-Token must not cache without allowPrivate');
    const refusedSession = putCache('GET', 'https://example.com/session', 200, {}, 'x', {
      requestHeaders: { 'X-Session-ID': 'SESSIONSECRET' },
    });
    if (refusedSession !== null) errors.push('X-Session-ID must not cache without allowPrivate');
  } finally {
    delete process.env[CACHE_ENV];
    try {
      rmSync(tmpDir, { recursive: true, force: true });
    } catch {
      /* ignore */
    }
  }
  if (errors.length) {
    console.error('http_cache.mjs self-test FAILED:');
    for (const e of errors) console.error(`  - ${e}`);
    process.exit(1);
  }
  console.log('http_cache.mjs self-test ok');
}

if (process.argv.includes('--self-test')) {
  selfTest();
}
