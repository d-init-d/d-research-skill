// Node ESM helper for shared HTTP cache.
// Enables only when D_RESEARCH_HTTP_CACHE_PATH is set.
// Uses same on-disk layout as scripts/http_cache.py for cross-runtime compat.
//
// Atomic generation protocol (must match Python http_cache.py):
//   - unique per-writer temp files: {key}.{gen}.body.tmp / {key}.{gen}.json.tmp
//   - publish body to generation-scoped {key}.{gen}.body (no shared body path)
//   - atomically publish meta pointing at body_file
//   - re-read live meta after publish:
//       * winner (live gen == ours): delete superseded generation bodies + legacy
//       * loser (live gen != ours): delete only our unreferenced body
//   - never delete the body currently referenced by live meta
//   - readers validate hash/size and never mix generations
//   - body_file is basename-only <key>.<32-hex-gen>.body inside entries/

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
  statSync,
  lstatSync,
  realpathSync,
} from 'node:fs';
import { join, resolve, basename, isAbsolute, sep, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { isSensitiveHeaderName, urlHasCredentials } from './credentials.mjs';

const CACHE_ENV = 'D_RESEARCH_HTTP_CACHE_PATH';
export const DEFAULT_MAX_AGE_SECONDS = 7 * 24 * 3600;
const GENERATION_ID_RE = /^[0-9a-f]{32}$/;

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

function isGenerationId(value) {
  return typeof value === 'string' && GENERATION_ID_RE.test(value);
}

function isUnsafeBodyFileName(name) {
  if (!name || typeof name !== 'string') return true;
  if (name.startsWith('/') || name.startsWith('\\')) return true;
  if (name.length >= 2 && name[1] === ':') return true;
  if (name.includes('/') || name.includes('\\')) return true;
  if (name.includes('..')) return true;
  if (isAbsolute(name)) return true;
  if (basename(name) !== name) return true;
  return false;
}

function canonicalGenerationBodyName(key, generationId) {
  return `${key}.${generationId}.body`;
}

function isCanonicalBodyFile(name, key, generationId) {
  if (isUnsafeBodyFileName(name)) return false;
  if (!name.endsWith('.body')) return false;
  const prefix = `${key}.`;
  if (!name.startsWith(prefix)) return false;
  const genPart = name.slice(prefix.length, -'.body'.length);
  if (!isGenerationId(genPart)) return false;
  if (generationId !== undefined && generationId !== null && generationId !== '') {
    if (!isGenerationId(generationId)) return false;
    if (genPart !== generationId) return false;
  }
  return true;
}

function pathContainedInEntries(entriesDir, candidatePath) {
  try {
    const entriesReal = realpathSync(entriesDir);
    let candReal;
    try {
      candReal = realpathSync(candidatePath);
    } catch {
      // Target may not exist yet / broken symlink.
      return false;
    }
    const rel = candReal.startsWith(entriesReal + sep) || candReal === entriesReal;
    return rel;
  } catch {
    return false;
  }
}

function metaReferencedBodyName(key, meta) {
  const bodyRel = meta.body_file;
  const gen = meta.generation_id;
  if (typeof bodyRel === 'string' && bodyRel) {
    if (isCanonicalBodyFile(bodyRel, key, gen)) return bodyRel;
    return null;
  }
  if (isGenerationId(gen)) return canonicalGenerationBodyName(key, gen);
  return `${key}.body`;
}

function resolveBodyPath(entriesDir, key, meta) {
  const bodyRel = meta.body_file;
  const gen = meta.generation_id;

  if (typeof bodyRel === 'string' && bodyRel) {
    // Invalid new-format body_file → hard miss, no fallback.
    if (!isCanonicalBodyFile(bodyRel, key, gen)) return null;
    const candidate = join(entriesDir, bodyRel);
    if (!pathContainedInEntries(entriesDir, candidate)) return null;
    if (!existsSync(candidate)) return null;
    // Symlink escape: realpath must remain inside entries.
    try {
      if (lstatSync(candidate).isSymbolicLink()) {
        if (!pathContainedInEntries(entriesDir, candidate)) return null;
      }
    } catch {
      return null;
    }
    if (!pathContainedInEntries(entriesDir, candidate)) return null;
    return candidate;
  }

  // True legacy metadata (no body_file).
  if (isGenerationId(gen)) {
    const genPath = join(entriesDir, canonicalGenerationBodyName(key, gen));
    if (existsSync(genPath) && pathContainedInEntries(entriesDir, genPath)) return genPath;
  }
  const legacy = join(entriesDir, `${key}.body`);
  if (existsSync(legacy) && pathContainedInEntries(entriesDir, legacy)) return legacy;
  return null;
}

const unlinkWaitBuffer = new Int32Array(new SharedArrayBuffer(4));

function sleepSync(ms) {
  Atomics.wait(unlinkWaitBuffer, 0, 0, ms);
}

function safeUnlink(path, attempts = 8) {
  const boundedAttempts = Math.max(1, attempts);
  for (let attempt = 0; attempt < boundedAttempts; attempt += 1) {
    try {
      unlinkSync(path);
      return true;
    } catch (error) {
      if (error?.code === 'ENOENT') return true;
      if (attempt + 1 < boundedAttempts) sleepSync(10 * (attempt + 1));
    }
  }
  return false;
}

function readLiveBodyRef(entriesDir, key) {
  const metaPath = join(entriesDir, `${key}.json`);
  if (!existsSync(metaPath)) return { bodyName: null, gen: null };
  let liveMeta;
  try {
    liveMeta = JSON.parse(readFileSync(metaPath, 'utf-8'));
  } catch {
    return { bodyName: null, gen: null };
  }
  const bodyName = metaReferencedBodyName(key, liveMeta);
  const gen = isGenerationId(liveMeta.generation_id) ? liveMeta.generation_id : null;
  return { bodyName, gen };
}

function gcUnreferencedBodiesForKey(entriesDir, key) {
  const live = readLiveBodyRef(entriesDir, key);
  let removed = 0;
  let names;
  try {
    names = readdirSync(entriesDir);
  } catch {
    return 0;
  }
  for (const name of names) {
    if (!name.endsWith('.body')) continue;
    if (name === `${key}.body`) {
      if (live.bodyName === name) continue;
      if (safeUnlink(join(entriesDir, name))) removed += 1;
      continue;
    }
    const prefix = `${key}.`;
    if (!name.startsWith(prefix)) continue;
    const mid = name.slice(prefix.length, -'.body'.length);
    if (!isGenerationId(mid)) continue;
    if (live.bodyName === name) continue;
    if (safeUnlink(join(entriesDir, name))) removed += 1;
  }
  return removed;
}

function cleanupWriterGeneration(entriesDir, key, genId, publishedMeta, prevBodyName = null) {
  // Winner only deletes the previously observed live body. Deleting every
  // unreferenced generation races with in-flight writers that published a
  // body but have not yet swapped meta. Losers delete only their own body.
  // Orphans are collected by age-based / purge-all GC.
  const ourName = canonicalGenerationBodyName(key, genId);
  const ourBody = join(entriesDir, ourName);
  let live = readLiveBodyRef(entriesDir, key);

  if (!publishedMeta) {
    if (live.bodyName !== ourName) safeUnlink(ourBody);
    return;
  }

  if (live.gen === genId && live.bodyName === ourName) {
    if (prevBodyName && prevBodyName !== ourName && !isUnsafeBodyFileName(prevBodyName)) {
      live = readLiveBodyRef(entriesDir, key);
      if (live.gen === genId && live.bodyName === ourName && live.bodyName !== prevBodyName) {
        const candidate = join(entriesDir, prevBodyName);
        if (pathContainedInEntries(entriesDir, candidate)) safeUnlink(candidate);
      }
    }
    return;
  }

  live = readLiveBodyRef(entriesDir, key);
  if (live.bodyName !== ourName) safeUnlink(ourBody);
}

function renameWithRetry(from, to, attempts = 12) {
  let lastErr;
  for (let i = 0; i < attempts; i++) {
    try {
      renameSync(from, to);
      return;
    } catch (e) {
      lastErr = e;
      // Windows EPERM/EACCES under concurrent meta replace — back off.
      const start = Date.now();
      while (Date.now() - start < 20 * (i + 1)) {
        /* spin */
      }
    }
  }
  throw lastErr;
}

export function getCached(method, url, opts = {}) {
  const cacheDir = opts.cacheDir || getCachePath();
  if (!cacheDir) return null;
  const extra = opts.extraKeyHeaders || [];
  const requestKey = opts.requestKey ?? canonicalHeaderKey(opts.requestHeaders, extra);
  const key = cacheKey(method, url, { requestKey, bodyKey: opts.bodyKey });
  const entriesDir = join(cacheDir, 'entries');
  const metaPath = join(entriesDir, `${key}.json`);
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
  const bodyPath = resolveBodyPath(entriesDir, key, meta);
  if (!bodyPath) return null;
  let bodyBytes;
  try {
    bodyBytes = readFileSync(bodyPath);
  } catch {
    return null;
  }
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
  const bodyFile = canonicalGenerationBodyName(key, genId);
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
    body_file: bodyFile,
  };
  const entries = join(cacheDir, 'entries');
  const metaPath = join(entries, `${key}.json`);
  const bodyPath = join(entries, bodyFile);
  const prev = readLiveBodyRef(entries, key);
  const prevBodyName = prev.bodyName;
  const tmpBody = join(entries, `${key}.${genId}.body.tmp`);
  const tmpMeta = join(entries, `${key}.${genId}.json.tmp`);
  try {
    writeFileSync(tmpBody, bodyBuf);
    writeFileSync(tmpMeta, JSON.stringify(meta, null, 2), 'utf-8');
    renameWithRetry(tmpBody, bodyPath);
    try {
      renameWithRetry(tmpMeta, metaPath);
    } catch (e) {
      safeUnlink(tmpMeta);
      cleanupWriterGeneration(entries, key, genId, false, prevBodyName);
      throw e;
    }
    try {
      chmodSync(metaPath, 0o600);
      chmodSync(bodyPath, 0o600);
    } catch {
      /* windows */
    }
    cleanupWriterGeneration(entries, key, genId, true, prevBodyName);
  } catch (e) {
    try {
      safeUnlink(tmpBody);
    } catch {
      /* ignore */
    }
    try {
      safeUnlink(tmpMeta);
    } catch {
      /* ignore */
    }
    throw e;
  }
  return key;
}

export function countCacheFiles(entriesDir) {
  let meta = 0;
  let body = 0;
  let temp = 0;
  if (!existsSync(entriesDir)) return { meta, body, temp };
  for (const name of readdirSync(entriesDir)) {
    const lowerName = name.toLowerCase();
    if (lowerName.endsWith('.tmp')) {
      temp += 1;
    } else if (lowerName.endsWith('.json')) {
      meta += 1;
    } else if (lowerName.endsWith('.body')) {
      body += 1;
    }
  }
  return { meta, body, temp };
}

function cacheArtifactNames(entriesDir) {
  if (!existsSync(entriesDir)) return [];
  try {
    return readdirSync(entriesDir).filter((name) => {
      const lowerName = name.toLowerCase();
      const managed = (
        lowerName.endsWith('.body') ||
        lowerName.endsWith('.tmp') ||
        lowerName.endsWith('.json')
      );
      if (!managed) return false;
      try {
        return statSync(join(entriesDir, name)).isFile();
      } catch (error) {
        // NTFS can briefly enumerate a stale case-normalized name after a
        // concurrent rename/unlink. ENOENT is a ghost; other failures are a
        // real locked artifact and remain fail-closed.
        return error?.code !== 'ENOENT';
      }
    });
  } catch {
    return [];
  }
}

function unlinkMetaAndBody(entriesDir, metaPath, key) {
  let bodyName = null;
  try {
    const meta = JSON.parse(readFileSync(metaPath, 'utf-8'));
    bodyName = metaReferencedBodyName(key, meta);
  } catch {
    bodyName = null;
  }
  let deleted = safeUnlink(metaPath);
  if (bodyName && !isUnsafeBodyFileName(bodyName)) {
    const candidate = join(entriesDir, bodyName);
    if (pathContainedInEntries(entriesDir, candidate)) {
      deleted = safeUnlink(candidate) || deleted;
    }
  }
  const legacy = join(entriesDir, `${key}.body`);
  if (existsSync(legacy) && (!bodyName || basename(legacy) !== bodyName)) {
    if (pathContainedInEntries(entriesDir, legacy)) {
      deleted = safeUnlink(legacy) || deleted;
    }
  }
  return deleted;
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
  const referencedBodies = new Set();
  const removedNames = new Set();
  const names = readdirSync(entriesDir);

  for (const name of names) {
    const lowerName = name.toLowerCase();
    if (!lowerName.endsWith('.json') || lowerName.includes('.tmp')) continue;
    const metaPath = join(entriesDir, name);
    const key = name.slice(0, -'.json'.length);
    let shouldPurge = purgeAll;
    let meta = null;
    if (!shouldPurge) {
      try {
        meta = JSON.parse(readFileSync(metaPath, 'utf-8'));
        if (now - (meta.created_at || 0) > maxAge) shouldPurge = true;
      } catch {
        shouldPurge = true;
      }
    }
    if (shouldPurge) {
      if (unlinkMetaAndBody(entriesDir, metaPath, key)) purged += 1;
    } else {
      if (!meta) {
        try {
          meta = JSON.parse(readFileSync(metaPath, 'utf-8'));
        } catch {
          meta = null;
        }
      }
      if (meta) {
        const ref = metaReferencedBodyName(key, meta);
        if (ref) referencedBodies.add(ref.toLowerCase());
      }
    }
  }

  if (purgeAll) {
    const deadline = Date.now() + 2000;
    let cleanSnapshots = 0;
    while (true) {
      for (const name of cacheArtifactNames(entriesDir)) {
        const normalizedName = name.toLowerCase();
        if (removedNames.has(normalizedName)) continue;
        const p = join(entriesDir, name);
        if (safeUnlink(p)) {
          purged += 1;
          // NTFS may retain a stale case-normalized directory entry after a
          // successful unlink/ENOENT. Purge assumes no concurrent writers.
          removedNames.add(normalizedName);
        }
      }
      const remaining = cacheArtifactNames(entriesDir).filter(
        (name) => !removedNames.has(name.toLowerCase())
      );
      if (remaining.length === 0) {
        cleanSnapshots += 1;
        if (cleanSnapshots >= 2) break;
      } else {
        cleanSnapshots = 0;
      }
      if (Date.now() >= deadline) break;
      sleepSync(25);
    }
  } else {
    for (const name of readdirSync(entriesDir)) {
      const p = join(entriesDir, name);
      const lowerName = name.toLowerCase();
      let age;
      try {
        age = now - statSync(p).mtimeMs / 1000;
      } catch {
        continue;
      }
      if (lowerName.endsWith('.tmp')) {
        if (age > maxAge && safeUnlink(p)) purged += 1;
        continue;
      }
      if (!lowerName.endsWith('.body')) continue;
      if (referencedBodies.has(lowerName)) continue;
      if (age > maxAge && safeUnlink(p)) purged += 1;
    }
  }

  if (purgeAll) {
    const remaining = cacheArtifactNames(entriesDir).filter(
      (name) => !removedNames.has(name.toLowerCase())
    );
    if (remaining.length > 0) {
      const left = remaining.reduce(
        (counts, name) => {
          const lowerName = name.toLowerCase();
          if (lowerName.endsWith('.tmp')) counts.temp += 1;
          else if (lowerName.endsWith('.json')) counts.meta += 1;
          else if (lowerName.endsWith('.body')) counts.body += 1;
          return counts;
        },
        { meta: 0, body: 0, temp: 0 }
      );
      if (left.meta || left.body) {
        throw new Error(
          `purge --all incomplete (meta=${left.meta} body=${left.body} temp=${left.temp} ` +
          `remaining=${JSON.stringify(remaining.sort())})`
        );
      }
    }
  }

  return purged;
}

async function selfTest() {
  const { mkdtempSync, rmSync, symlinkSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const { Worker } = await import('node:worker_threads');
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

    // Sequential 5 overwrites → one body
    const url5 = 'https://example.com/five';
    for (let i = 0; i < 5; i++) {
      putCache('GET', url5, 200, {}, `body-${i}`);
    }
    const hit5 = getCached('GET', url5);
    if (!hit5 || hit5.body.toString() !== 'body-4') errors.push('5 overwrites latest miss');
    const key5 = cacheKey('GET', url5);
    const entriesDir = join(cd, 'entries');
    const bodies5 = readdirSync(entriesDir).filter((n) => n.startsWith(key5) && n.endsWith('.body'));
    const metas5 = readdirSync(entriesDir).filter((n) => n === `${key5}.json`);
    if (metas5.length !== 1 || bodies5.length !== 1) {
      errors.push(`after 5 overwrites meta=${metas5.length} body=${bodies5.length}`);
    }

    // F-08 containment
    const secretPath = join(tmpDir, 'outside-secret.txt');
    writeFileSync(secretPath, 'TOPSECRET-OUTSIDE-BYTES');
    const poisonUrl = 'https://example.com/poison';
    const poisonKey = putCache('GET', poisonUrl, 200, {}, 'legit-inside');
    const poisonMetaPath = join(entriesDir, `${poisonKey}.json`);
    const poisonMeta = JSON.parse(readFileSync(poisonMetaPath, 'utf-8'));

    function poisonAndGet(bodyFile, bodyStr) {
      const m = { ...poisonMeta, body_file: bodyFile, body_sha256: bodySha256(Buffer.from(bodyStr)), body_size: Buffer.byteLength(bodyStr) };
      writeFileSync(poisonMetaPath, JSON.stringify(m), 'utf-8');
      return getCached('GET', poisonUrl);
    }

    if (poisonAndGet(secretPath, 'TOPSECRET-OUTSIDE-BYTES') !== null) {
      errors.push('absolute body_file must miss');
    }
    writeFileSync(join(cd, 'secret2.txt'), 'TRAVERSAL');
    if (poisonAndGet('../secret2.txt', 'TRAVERSAL') !== null) {
      errors.push('traversal body_file must miss');
    }
    if (poisonAndGet('subdir/file.body', 'NESTED') !== null) {
      errors.push('nested body_file must miss');
    }
    if (poisonAndGet('C:\\Windows\\win.ini', 'WIN') !== null) {
      errors.push('drive path body_file must miss');
    }
    if (poisonAndGet('\\\\server\\share\\x.body', 'UNC') !== null) {
      errors.push('UNC body_file must miss');
    }
    writeFileSync(poisonMetaPath, JSON.stringify(poisonMeta), 'utf-8');
    const canon = getCached('GET', poisonUrl);
    if (!canon || canon.body.toString() !== 'legit-inside') errors.push('canonical body must hit');

    // Legacy without body_file
    const legKey = cacheKey('GET', 'https://example.com/legacy');
    const legMeta = {
      key: legKey,
      url: 'https://example.com/legacy',
      method: 'GET',
      status: 200,
      headers: {},
      created_at: Math.floor(Date.now() / 1000),
      body_sha256: bodySha256(Buffer.from('legacy-body')),
      body_size: Buffer.byteLength('legacy-body'),
    };
    writeFileSync(join(entriesDir, `${legKey}.json`), JSON.stringify(legMeta), 'utf-8');
    writeFileSync(join(entriesDir, `${legKey}.body`), 'legacy-body');
    const legHit = getCached('GET', 'https://example.com/legacy');
    if (!legHit || legHit.body.toString() !== 'legacy-body') errors.push('legacy round-trip failed');

    // Symlink escape
    try {
      const target = join(tmpDir, 'symlink-target.txt');
      writeFileSync(target, 'SYMLINK-SECRET');
      const linkName = `${poisonKey}.${'c'.repeat(32)}.body`;
      const linkPath = join(entriesDir, linkName);
      symlinkSync(target, linkPath);
      const m = {
        ...poisonMeta,
        body_file: linkName,
        generation_id: 'c'.repeat(32),
        body_sha256: bodySha256(Buffer.from('SYMLINK-SECRET')),
        body_size: Buffer.byteLength('SYMLINK-SECRET'),
      };
      writeFileSync(poisonMetaPath, JSON.stringify(m), 'utf-8');
      const sym = getCached('GET', poisonUrl);
      if (sym && sym.body.toString() === 'SYMLINK-SECRET') {
        errors.push('symlink escape must miss');
      }
    } catch {
      /* symlink may require privileges on Windows */
    }

    // Corrupt meta
    const badKey = cacheKey('GET', 'https://example.com/corrupt');
    writeFileSync(join(entriesDir, `${badKey}.json`), '{not-json', 'utf-8');
    if (getCached('GET', 'https://example.com/corrupt') !== null) {
      errors.push('corrupt meta must miss');
    }

    // True multi-process concurrency via worker_threads (not Promise.resolve sync fakes)
    const urlC = 'https://example.com/concurrent';
    const workerSrc = `
      const { parentPort, workerData } = require('node:worker_threads');
      const path = require('node:path');
      const { pathToFileURL } = require('node:url');
      (async () => {
        const mod = await import(pathToFileURL(workerData.modulePath).href);
        process.env.D_RESEARCH_HTTP_CACHE_PATH = workerData.cacheDir;
        const errors = [];
        try {
          for (const i of workerData.indices) {
            mod.putCache('GET', workerData.url, 200, { 'content-type': 'text/plain' }, 'body-' + i);
          }
        } catch (e) {
          errors.push(String(e && e.message ? e.message : e));
        }
        parentPort.postMessage({ errors });
      })();
    `;
    const modulePath = fileURLToPath(import.meta.url);
    const workers = [];
    const perWorker = 10;
    const workerCount = 10;
    for (let w = 0; w < workerCount; w++) {
      const indices = [];
      for (let i = 0; i < perWorker; i++) indices.push(w * perWorker + i);
      workers.push(
        new Promise((resolvePromise, reject) => {
          const worker = new Worker(workerSrc, {
            eval: true,
            workerData: { modulePath, cacheDir: cd, url: urlC, indices },
          });
          worker.on('message', resolvePromise);
          worker.on('error', reject);
          worker.on('exit', (code) => {
            if (code !== 0) reject(new Error(`worker exit ${code}`));
          });
        })
      );
    }
    try {
      const results = await Promise.all(workers);
      for (const r of results) {
        if (r.errors && r.errors.length) {
          errors.push(`worker error: ${r.errors[0]}`);
          break;
        }
      }
    } catch (e) {
      errors.push(`concurrent workers failed: ${e.message || e}`);
    }
    const ck = cacheKey('GET', urlC);
    gcUnreferencedBodiesForKey(entriesDir, ck);
    const finalHit = getCached('GET', urlC);
    if (!finalHit) errors.push('concurrent final miss');
    else if (bodySha256(finalHit.body) !== finalHit.body_sha256) {
      errors.push('concurrent body/meta hash mismatch');
    }
    const orphanN = readdirSync(entriesDir).filter((n) => n.startsWith(ck) && n.endsWith('.body')).length;
    if (orphanN !== 1) errors.push(`after concurrent settle expected 1 body, got ${orphanN}`);

    const refused = putCache('GET', 'https://example.com/api', 200, {}, 'x', {
      requestHeaders: { 'X-Token': 'TOPSECRET' },
    });
    if (refused !== null) errors.push('X-Token must not cache without allowPrivate');
    const refusedSession = putCache('GET', 'https://example.com/session', 200, {}, 'x', {
      requestHeaders: { 'X-Session-ID': 'SESSIONSECRET' },
    });
    if (refusedSession !== null) errors.push('X-Session-ID must not cache without allowPrivate');

    // purge --all must clear everything
    writeFileSync(join(entriesDir, 'UPPER.BODY.TMP'), 'orphan', 'utf-8');
    purgeCache({ all: true, cacheDir: cd });
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
