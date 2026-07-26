#!/usr/bin/env node
/**
 * Paginated public API fetch helper for D Research.
 *
 * Hardening (v3.2):
 * - AbortSignal timeout per request
 * - Unknown options / bad JSON / invalid numerics exit non-zero
 * - HTTP/network/parse errors exit non-zero unless --allow-partial
 * - Output metadata sidecar when --out is set
 * - --pagination canonical; --paginate deprecated alias
 * - --cursor-key dotted path support
 * - Relative Link: rel="next" resolution; same-origin by default
 * - --allow-next-origin for public unauthenticated cross-origin next
 * - Auth/Cookie/API-key: cross-origin next always hard-fails (no credential forward)
 * - Token/query secret redaction in logs and cache metadata
 */

import { writeFileSync, mkdtempSync, rmSync, existsSync, readdirSync, readFileSync } from 'fs';
import { createServer } from 'http';
import { tmpdir } from 'os';
import { join } from 'path';
import { getCachePath, getCached, putCache } from './lib/http_cache.mjs';
import {
  headersHaveCredentials,
  isCredentialedRequest,
  isSensitiveHeaderName,
  publicHeadersOnly,
  redactSecretsInText,
  redactUrl,
  stripSensitiveHeaders,
  urlHasCredentials,
} from './lib/credentials.mjs';
import { HttpResourceLimitError, assertPublicHttpUrl, fetchPublicHttp } from './lib/ssrf_guards.mjs';
import { loadConfig, getPositiveIntConfig, redactConfig } from './lib/config.mjs';

const MAX_REDIRECTS = 10;
const DEFAULT_MAX_BODY_BYTES = 20 * 1024 * 1024;
const DEFAULT_GET_ATTEMPTS = 3;
const DEFAULT_NON_IDEMPOTENT_ATTEMPTS = 1;

// Production defaults: public HTTPS destinations only. Offline self-tests may
// enable loopback HTTP fixtures via setSsrfOptionsForTest() or the hermetic
// env flag D_RESEARCH_SSRF_ALLOW_LOOPBACK=1 (never set in production CI paths
// that exercise public network helpers).
function _defaultSsrfOptions() {
  if (process.env.D_RESEARCH_SSRF_ALLOW_LOOPBACK === '1') {
    return { allowHttp: true, allowLoopback: true };
  }
  return { allowHttp: false, allowLoopback: false };
}
let _ssrfOptions = _defaultSsrfOptions();

/** @param {{allowHttp?: boolean, allowLoopback?: boolean}} opts */
export function setSsrfOptionsForTest(opts = {}) {
  _ssrfOptions = {
    allowHttp: Boolean(opts.allowHttp),
    allowLoopback: Boolean(opts.allowLoopback),
  };
}

class ResourceLimitError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = 'ResourceLimitError';
    this.code = code;
    this.details = details;
  }
}

class RequestTimeoutError extends Error {
  constructor(message) {
    super(message);
    this.name = 'RequestTimeoutError';
    this.code = 'response_body_timeout';
  }
}

function isResourceLimitError(error) {
  return error instanceof ResourceLimitError ||
    error instanceof HttpResourceLimitError ||
    error?.code === 'http_max_bytes' ||
    error?.code === 'invalid_http_max_bytes';
}

// Back-compat aliases used inside this file
const hasCredentialHeaders = headersHaveCredentials;
const stripCredentialsFromHeaders = stripSensitiveHeaders;

async function readBodyBounded(
  response,
  maxBytes = DEFAULT_MAX_BODY_BYTES,
  timeoutMs = 30000
) {
  if (!Number.isSafeInteger(maxBytes) || maxBytes < 1) {
    throw new ResourceLimitError(
      'invalid_http_max_bytes',
      `max response bytes must be a positive safe integer: ${maxBytes}`,
      { limit: maxBytes }
    );
  }
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1) {
    throw new RequestTimeoutError(`body timeout must be a positive integer: ${timeoutMs}`);
  }

  const declaredLength = Number.parseInt(response.headers?.get?.('content-length') || '', 10);
  if (Number.isFinite(declaredLength) && declaredLength > maxBytes) {
    try { await response.body?.cancel?.('resource limit exceeded'); } catch { /* ignore */ }
    throw new ResourceLimitError(
      'http_max_bytes',
      `response body exceeds ${maxBytes} bytes`,
      { limit: maxBytes, actual: declaredLength }
    );
  }

  const reader = response.body && response.body.getReader ? response.body.getReader() : null;
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      if (reader) reader.cancel('response body timeout').catch(() => {});
      reject(new RequestTimeoutError(`response body timeout after ${timeoutMs}ms`));
    }, timeoutMs);
  });

  const consume = async () => {
    if (!reader) {
      const text = await response.text();
      const actual = Buffer.byteLength(text, 'utf-8');
      if (actual > maxBytes) {
        throw new ResourceLimitError(
          'http_max_bytes',
          `response body exceeds ${maxBytes} bytes`,
          { limit: maxBytes, actual }
        );
      }
      return text;
    }

    const chunks = [];
    let total = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maxBytes) {
        try { await reader.cancel('resource limit exceeded'); } catch { /* ignore */ }
        throw new ResourceLimitError(
          'http_max_bytes',
          `response body exceeds ${maxBytes} bytes`,
          { limit: maxBytes, actual: total }
        );
      }
      chunks.push(value);
    }
    return Buffer.concat(chunks.map((c) => Buffer.from(c))).toString('utf-8');
  };

  try {
    return await Promise.race([consume(), timeout]);
  } finally {
    clearTimeout(timer);
  }
}

function getByPath(obj, dotted) {
  if (!dotted) return undefined;
  const parts = String(dotted).split('.');
  let cur = obj;
  for (const p of parts) {
    if (cur == null || typeof cur !== 'object') return undefined;
    cur = cur[p];
  }
  return cur;
}

function parseArgs(argv) {
  const args = {
    url: null,
    headers: {},
    params: {},
    pagination: 'auto',
    maxPages: 10,
    maxPagesFromCli: false,
    maxAttempts: null,
    maxAttemptsFromCli: false,
    configPath: null,
    printEffectiveConfig: false,
    method: 'GET',
    bodyJson: null,
    bodyFile: null,
    contentType: null,
    intent: null,
    delay: 500,
    out: null,
    format: 'json',
    timeout: 30000,
    maxResponseBytes: DEFAULT_MAX_BODY_BYTES,
    cursorKey: null,
    allowPartial: false,
    allowNextOrigin: [],
    allowRedirectOrigin: [],
    selfTest: false,
    unknown: [],
    parseErrors: [],
  };

  const envMax = process.env.D_RESEARCH_HTTP_MAX_BYTES;
  if (envMax !== undefined && envMax !== '') {
    if (!/^\d+$/.test(envMax)) {
      args.parseErrors.push(`invalid D_RESEARCH_HTTP_MAX_BYTES: ${envMax}`);
    } else {
      const n = Number.parseInt(envMax, 10);
      if (!Number.isSafeInteger(n) || n < 1) {
        args.parseErrors.push(`invalid D_RESEARCH_HTTP_MAX_BYTES: ${envMax}`);
      } else {
        args.maxResponseBytes = n;
      }
    }
  }
  const envTimeoutSec = process.env.D_RESEARCH_HTTP_TIMEOUT_SEC;
  if (envTimeoutSec !== undefined && envTimeoutSec !== '') {
    if (!/^\d+$/.test(envTimeoutSec)) {
      args.parseErrors.push(`invalid D_RESEARCH_HTTP_TIMEOUT_SEC: ${envTimeoutSec}`);
    } else {
      const seconds = Number.parseInt(envTimeoutSec, 10);
      const milliseconds = seconds * 1000;
      if (!Number.isSafeInteger(milliseconds) || milliseconds < 1) {
        args.parseErrors.push(`invalid D_RESEARCH_HTTP_TIMEOUT_SEC: ${envTimeoutSec}`);
      } else {
        args.timeout = milliseconds;
      }
    }
  }

  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    const need = (name) => {
      if (i + 1 >= argv.length) {
        args.parseErrors.push(`missing value for ${name}`);
        return null;
      }
      return argv[++i];
    };

    if (arg === '--url') {
      args.url = need('--url');
    } else if (arg === '--headers') {
      const raw = need('--headers');
      if (raw != null) {
        try {
          const parsed = JSON.parse(raw);
          if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
            args.parseErrors.push('--headers must be a JSON object');
          } else {
            args.headers = parsed;
          }
        } catch {
          args.parseErrors.push('Invalid JSON in --headers');
        }
      }
    } else if (arg === '--params') {
      const raw = need('--params');
      if (raw != null) {
        try {
          const parsed = JSON.parse(raw);
          if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
            args.parseErrors.push('--params must be a JSON object');
          } else {
            args.params = parsed;
          }
        } catch {
          args.parseErrors.push('Invalid JSON in --params');
        }
      }
    } else if (arg === '--pagination') {
      args.pagination = need('--pagination');
    } else if (arg === '--paginate') {
      console.error('warning: --paginate is deprecated; use --pagination');
      args.pagination = need('--paginate');
    } else if (arg === '--max-pages') {
      const raw = need('--max-pages');
      if (raw == null || !/^\d+$/.test(String(raw))) {
        args.parseErrors.push(`invalid --max-pages: ${raw}`);
      } else {
        const n = Number.parseInt(raw, 10);
        if (!Number.isFinite(n) || n < 1) args.parseErrors.push(`invalid --max-pages: ${raw}`);
        else {
          args.maxPages = n;
          args.maxPagesFromCli = true;
        }
      }
    } else if (arg === '--max-attempts') {
      const raw = need('--max-attempts');
      if (raw == null || !/^\d+$/.test(String(raw))) {
        args.parseErrors.push(`invalid --max-attempts: ${raw}`);
      } else {
        const n = Number.parseInt(raw, 10);
        if (!Number.isSafeInteger(n) || n < 1) {
          args.parseErrors.push(`invalid --max-attempts: ${raw}`);
        } else {
          args.maxAttempts = n;
          args.maxAttemptsFromCli = true;
        }
      }
    } else if (arg === '--config') {
      args.configPath = need('--config');
    } else if (arg === '--print-effective-config') {
      args.printEffectiveConfig = true;
    } else if (arg === '--method') {
      const raw = need('--method');
      if (raw != null) args.method = String(raw).toUpperCase();
    } else if (arg === '--body-json') {
      args.bodyJson = need('--body-json');
    } else if (arg === '--body-file') {
      args.bodyFile = need('--body-file');
    } else if (arg === '--content-type') {
      args.contentType = need('--content-type');
    } else if (arg === '--intent') {
      const raw = need('--intent');
      if (raw != null) args.intent = String(raw).toLowerCase();
    } else if (arg === '--delay') {
      const raw = need('--delay');
      if (raw == null || !/^\d+$/.test(String(raw))) {
        args.parseErrors.push(`invalid --delay: ${raw}`);
      } else {
        const n = Number.parseInt(raw, 10);
        if (!Number.isFinite(n) || n < 0) args.parseErrors.push(`invalid --delay: ${raw}`);
        else args.delay = n;
      }
    } else if (arg === '--out') {
      args.out = need('--out');
    } else if (arg === '--format') {
      args.format = need('--format');
    } else if (arg === '--timeout') {
      const raw = need('--timeout');
      if (raw == null || !/^\d+$/.test(String(raw))) {
        args.parseErrors.push(`invalid --timeout: ${raw}`);
      } else {
        const n = Number.parseInt(raw, 10);
        if (!Number.isFinite(n) || n < 1) args.parseErrors.push(`invalid --timeout: ${raw}`);
        else args.timeout = n;
      }
    } else if (arg === '--max-response-bytes') {
      const raw = need('--max-response-bytes');
      if (raw == null || !/^\d+$/.test(String(raw))) {
        args.parseErrors.push(`invalid --max-response-bytes: ${raw}`);
      } else {
        const n = Number.parseInt(raw, 10);
        if (!Number.isSafeInteger(n) || n < 1) {
          args.parseErrors.push(`invalid --max-response-bytes: ${raw}`);
        } else {
          args.maxResponseBytes = n;
        }
      }
    } else if (arg === '--cursor-key') {
      args.cursorKey = need('--cursor-key');
    } else if (arg === '--allow-partial') {
      args.allowPartial = true;
    } else if (arg === '--allow-next-origin') {
      const v = need('--allow-next-origin');
      if (v) args.allowNextOrigin.push(v.toLowerCase());
    } else if (arg === '--allow-redirect-origin') {
      const v = need('--allow-redirect-origin');
      if (v) args.allowRedirectOrigin.push(v.toLowerCase());
    } else if (arg === '--self-test') {
      args.selfTest = true;
    } else {
      // Never retain or echo an unknown argument verbatim: callers sometimes
      // misspell credential options (for example --access-token SECRET).
      // Recording only the argument kind preserves a useful non-zero failure
      // without turning diagnostics into a secret-exfiltration channel.
      args.unknown.push(arg.startsWith('--') ? 'option' : 'positional');
      if (arg.startsWith('--') && !arg.includes('=') && argv[i + 1] && !argv[i + 1].startsWith('--')) {
        i += 1;
      }
    }
  }

  return args;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function applyParams(url, params) {
  if (!params || Object.keys(params).length === 0) return url;
  const urlObj = new URL(url);
  for (const [key, value] of Object.entries(params)) {
    urlObj.searchParams.set(key, value);
  }
  return urlObj.toString();
}

function parseRetryAfter(value) {
  if (!value) return null;
  const asInt = Number.parseInt(value, 10);
  if (Number.isFinite(asInt) && String(asInt) === String(value).trim()) {
    return Math.min(asInt * 1000, 120_000);
  }
  const when = Date.parse(value);
  if (!Number.isNaN(when)) {
    return Math.min(Math.max(0, when - Date.now()), 120_000);
  }
  return null;
}

function isAllowedOrigin(url, allowlist) {
  const parsed = new URL(url);
  const allowed = new Set((allowlist || []).map((value) => String(value).toLowerCase()));
  return allowed.has(parsed.origin.toLowerCase()) || allowed.has(parsed.host.toLowerCase());
}

function withoutEntityHeaders(headers) {
  const out = {};
  for (const [key, value] of Object.entries(headers || {})) {
    if (!['content-type', 'content-length', 'transfer-encoding'].includes(key.toLowerCase())) {
      out[key] = value;
    }
  }
  return out;
}

function redirectedRequest(status, method, body) {
  const upper = String(method || 'GET').toUpperCase();
  if (status === 303 || ((status === 301 || status === 302) && upper === 'POST')) {
    return { method: 'GET', body: undefined };
  }
  return { method: upper, body };
}

function resolveNextUrl(currentUrl, nextUrl, headers, allowNextOrigin) {
  let resolved;
  try {
    resolved = new URL(nextUrl, currentUrl).toString();
  } catch {
    throw new Error(`invalid next URL: ${redactUrl(String(nextUrl))}`);
  }
  // Query/userinfo secrets on next URL count as credentials.
  if (urlHasCredentials(resolved) || isCredentialedRequest(currentUrl, headers)) {
    const curOrigin = new URL(currentUrl).origin;
    const nxtOrigin = new URL(resolved).origin;
    if (curOrigin !== nxtOrigin) {
      throw new Error(
        `cross-origin pagination blocked while credentials present: ${redactUrl(resolved)}`
      );
    }
  }
  const cur = new URL(currentUrl);
  const nxt = new URL(resolved);
  if (cur.origin === nxt.origin) return resolved;

  if (isCredentialedRequest(currentUrl, headers) || urlHasCredentials(resolved)) {
    throw new Error(
      `cross-origin pagination blocked while credentials present: ${redactUrl(resolved)}`
    );
  }
  // allow-next-origin only for public unauthenticated requests
  const allowed = new Set((allowNextOrigin || []).map((o) => o.toLowerCase()));
  if (allowed.has(nxt.origin.toLowerCase()) || allowed.has(nxt.host.toLowerCase())) {
    return resolved;
  }
  throw new Error(
    `cross-origin next link blocked (use --allow-next-origin ${nxt.origin}): ${redactUrl(resolved)}`
  );
}

function detectPagination(response, body, paginationMode, cursorKey) {
  const linkHeader = response.headers.get ? response.headers.get('link') : null;
  let nextUrl = null;
  if (linkHeader) {
    const nextMatch = linkHeader.match(/<([^>]+)>;\s*rel="next"/i);
    if (nextMatch) nextUrl = nextMatch[1];
  }
  if (nextUrl && (paginationMode === 'auto' || paginationMode === 'link-header')) {
    return { type: 'link-header', nextUrl };
  }

  let parsedBody = body;
  if (typeof body === 'string') {
    try {
      parsedBody = JSON.parse(body);
    } catch {
      return null;
    }
  }
  if (!parsedBody || typeof parsedBody !== 'object') return null;

  if (cursorKey) {
    const val = getByPath(parsedBody, cursorKey);
    if (val != null && val !== '') return { type: 'cursor', nextCursor: String(val) };
  }

  if (paginationMode === 'auto' || paginationMode === 'cursor') {
    if (parsedBody.next_cursor || parsedBody.nextCursor || parsedBody.next_cursor_token) {
      return {
        type: 'cursor',
        nextCursor:
          parsedBody.next_cursor || parsedBody.nextCursor || parsedBody.next_cursor_token,
      };
    }
    if (parsedBody.next_page_token) {
      return { type: 'cursor', nextCursor: parsedBody.next_page_token };
    }
  }

  if (paginationMode === 'auto' || paginationMode === 'offset') {
    if (typeof parsedBody.offset === 'number' && typeof parsedBody.total === 'number') {
      const pageSize = parsedBody.limit || parsedBody.page_size || 10;
      const nextOffset = parsedBody.offset + pageSize;
      if (nextOffset < parsedBody.total) return { type: 'offset', nextOffset };
    }
  }

  if (paginationMode === 'auto' || paginationMode === 'page') {
    if (parsedBody.page && parsedBody.total_pages) {
      const nextPage = parsedBody.page + 1;
      if (nextPage <= parsedBody.total_pages) return { type: 'page', nextPage };
    }
  }

  return null;
}

async function fetchWithTimeout(
  url,
  options,
  timeoutMs,
  maxAttempts = DEFAULT_GET_ATTEMPTS,
  maxResponseBytes = DEFAULT_MAX_BODY_BYTES,
  redirectOptions = {}
) {
  let lastError;
  const method = (options && options.method) || 'GET';
  const requestHeaders = (options && options.headers) || {};
  const cacheEnabled = getCachePath() !== null;
  const isGet = method.toUpperCase() === 'GET';
  const credentialed = isCredentialedRequest(url, requestHeaders);

  // SSRF gate on the initial URL (user-controlled).
  await assertPublicHttpUrl(url, _ssrfOptions);

  if (cacheEnabled && isGet && !credentialed) {
    try {
      const cached = getCached(method, url, { requestHeaders });
      if (cached) {
        const headers = new Headers(cached.headers || {});
        return new Response(cached.body, { status: cached.status, headers });
      }
    } catch {
      /* cache non-fatal */
    }
  }

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      let currentUrl = url;
      let headers = { ...requestHeaders };
      let currentMethod = method;
      let currentBody = options && options.body != null ? options.body : undefined;
      let hop = 0;
      while (hop <= MAX_REDIRECTS) {
        // Connection-bound SSRF: resolve + validate + connect to validated peer
        // (no separate DNS for assert then undici fetch — closes TOCTOU/rebinding).
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        let response;
        try {
          response = await fetchPublicHttp(
            currentUrl,
            {
              method: currentMethod,
              headers,
              body: currentBody,
              signal: controller.signal,
              maxResponseBytes,
              bodyTimeoutMs: timeoutMs,
            },
            _ssrfOptions,
          );
        } catch (error) {
          clearTimeout(timer);
          if (error && (error.name === 'AbortError' || /aborted/i.test(String(error.message || error)))) {
            throw new Error(`request timeout after ${timeoutMs}ms: ${redactUrl(currentUrl)}`);
          }
          throw error;
        }
        clearTimeout(timer);

        if ([301, 302, 303, 307, 308].includes(response.status)) {
          const loc = response.headers.get('location');
          if (!loc) throw new Error(`redirect without Location from ${redactUrl(currentUrl)}`);
          let next;
          try {
            next = new URL(loc, currentUrl).toString();
          } catch {
            throw new Error('redirect Location is not a valid URL');
          }
          // SSRF revalidation of redirect target before following.
          await assertPublicHttpUrl(next, _ssrfOptions);
          const curOrigin = new URL(currentUrl).origin;
          const nextOrigin = new URL(next).origin;
          const redirected = redirectedRequest(response.status, currentMethod, currentBody);
          if (curOrigin !== nextOrigin) {
            if (
              credentialed ||
              isCredentialedRequest(currentUrl, headers) ||
              urlHasCredentials(next)
            ) {
              throw new Error(
                `cross-origin redirect blocked while credentials present: ${redactUrl(next)}`
              );
            }
            if (
              !['GET', 'HEAD'].includes(redirected.method) &&
              !isAllowedOrigin(next, redirectOptions.allowRedirectOrigin)
            ) {
              throw new Error(
                `cross-origin ${redirected.method} redirect blocked ` +
                  `(use --allow-redirect-origin ${nextOrigin}): ${redactUrl(next)}`
              );
            }
            // Even without known secrets, only public headers may cross origin.
            headers = publicHeadersOnly(headers);
          }
          if (redirected.body === undefined) headers = withoutEntityHeaders(headers);
          currentMethod = redirected.method;
          currentBody = redirected.body;
          currentUrl = next;
          hop += 1;
          continue;
        }

        if (response.status === 429) {
          if (attempt + 1 >= maxAttempts) return response;
          const retryAfter = parseRetryAfter(response.headers.get('Retry-After'));
          const waitTime = retryAfter ?? 1000 * Math.pow(2, attempt);
          console.log(`Rate limited. Waiting ${waitTime}ms before retry...`);
          await sleep(waitTime);
          break; // retry outer attempt
        }
        if (response.status >= 500) {
          if (attempt + 1 >= maxAttempts) return response;
          const waitTime = 1000 * Math.pow(2, attempt);
          console.log(`Server error (${response.status}). Retrying in ${waitTime}ms...`);
          await sleep(waitTime);
          break;
        }

        response._finalUrl = currentUrl;
        return response;
      }
      if (hop > MAX_REDIRECTS) {
        throw new Error(`too many redirects (>${MAX_REDIRECTS})`);
      }
    } catch (error) {
      lastError = error;
      const msg = redactSecretsInText(String(error.message || error));
      if (
        isResourceLimitError(error) ||
        msg.includes('timeout') ||
        msg.includes('cross-origin redirect blocked')
      ) {
        throw error;
      }
      const waitTime = 1000 * Math.pow(2, attempt);
      if (attempt + 1 >= maxAttempts) throw error;
      console.log(`Request failed: ${msg}. Retrying in ${waitTime}ms...`);
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
  urlObj.searchParams.set('offset', String(offset));
  return urlObj.toString();
}

function updateUrlWithPage(url, page) {
  const urlObj = new URL(url);
  urlObj.searchParams.set('page', String(page));
  return urlObj.toString();
}

function writeSidecar(outPath, meta) {
  const side = `${outPath}.meta.json`;
  writeFileSync(side, JSON.stringify(meta, null, 2) + '\n');
  console.log(`Metadata written to: ${side}`);
}

// Fill defaults from config for values the CLI did not set explicitly.
// Precedence: CLI flag > explicit --config > discovered research.config.json >
// built-in default. Config never overrides a value the caller passed on the CLI.
function applyConfigDefaults(args, { startDir = process.cwd() } = {}) {
  const { config, source, error } = loadConfig({
    explicitPath: args.configPath,
    startDir,
  });
  if (error) args.parseErrors.push(error);
  args.effectiveConfigSource = source;
  args.effectiveConfig = config;

  if (!args.maxPagesFromCli) {
    const { value, error: intError } = getPositiveIntConfig(
      config,
      'api.maxPagesPerEndpoint',
    );
    if (intError) args.parseErrors.push(intError);
    else if (value !== null) args.maxPages = value;
  }

  return args;
}

function effectiveConfigReport(args) {
  return {
    source: args.effectiveConfigSource ?? null,
    resolved: {
      'api.maxPagesPerEndpoint': args.maxPages,
      maxPagesFromCli: args.maxPagesFromCli,
    },
    config: redactConfig(args.effectiveConfig ?? {}),
  };
}

const HTTP_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'];
const REQUEST_INTENTS = ['query', 'archive', 'mutation'];
// Which methods each intent may use. GET stays read-only and never needs intent.
const INTENT_METHODS = {
  query: ['GET', 'POST'], // e.g. GraphQL / search POST that does not mutate
  archive: ['POST', 'PUT'], // archival submission
  mutation: ['POST', 'PUT', 'PATCH', 'DELETE'],
};

// Validate method/body/intent and materialize the request body.
// GET is fully preserved: no intent required, no body allowed. Any non-GET
// method must declare --intent explicitly so a side-effecting request is never
// issued by accident, and defaults to a single request so a body is never
// re-sent by pagination.
function resolveRequestShape(args) {
  args.body = null;
  args.bodyContentType = null;

  if (!HTTP_METHODS.includes(args.method)) {
    args.parseErrors.push(`invalid --method: ${args.method} (allowed: ${HTTP_METHODS.join(', ')})`);
    return args;
  }

  const hasBodyFlag = args.bodyJson != null || args.bodyFile != null;

  if (args.method === 'GET') {
    if (hasBodyFlag) {
      args.parseErrors.push('--body-json/--body-file are not allowed with GET; choose --method POST|PUT|PATCH|DELETE');
    }
    if (args.intent != null && args.intent !== 'query') {
      args.parseErrors.push(`--intent ${args.intent} is not valid for GET (GET is always a read-only query)`);
    }
    if (args.maxAttempts == null) args.maxAttempts = DEFAULT_GET_ATTEMPTS;
    return args; // GET request behavior remains unchanged.
  }

  // Non-GET below.
  if (args.intent == null) {
    args.parseErrors.push(`--method ${args.method} requires an explicit --intent (${REQUEST_INTENTS.join('|')})`);
    return args;
  }
  if (!REQUEST_INTENTS.includes(args.intent)) {
    args.parseErrors.push(`invalid --intent: ${args.intent} (allowed: ${REQUEST_INTENTS.join(', ')})`);
    return args;
  }

  if (args.maxAttempts == null) {
    args.maxAttempts = args.intent === 'query'
      ? DEFAULT_GET_ATTEMPTS
      : DEFAULT_NON_IDEMPOTENT_ATTEMPTS;
  }
  if (!INTENT_METHODS[args.intent].includes(args.method)) {
    args.parseErrors.push(
      `--method ${args.method} is not allowed for --intent ${args.intent} ` +
        `(allowed: ${INTENT_METHODS[args.intent].join(', ')})`,
    );
    return args;
  }

  if (args.bodyJson != null && args.bodyFile != null) {
    args.parseErrors.push('--body-json and --body-file are mutually exclusive');
    return args;
  }

  if (args.bodyJson != null) {
    try {
      JSON.parse(args.bodyJson);
    } catch (e) {
      args.parseErrors.push(`--body-json is not valid JSON: ${e.message}`);
      return args;
    }
    args.body = args.bodyJson;
    args.bodyContentType = args.contentType || 'application/json';
  } else if (args.bodyFile != null) {
    let contents;
    try {
      contents = readFileSync(args.bodyFile);
    } catch (e) {
      args.parseErrors.push(`cannot read --body-file ${args.bodyFile}: ${e.message}`);
      return args;
    }
    if (contents.length > args.maxResponseBytes) {
      args.parseErrors.push(
        `request body (${contents.length} bytes) exceeds the ${args.maxResponseBytes}-byte cap`,
      );
      return args;
    }
    args.body = contents;
    args.bodyContentType = args.contentType || 'application/octet-stream';
  } else if (args.contentType != null) {
    args.bodyContentType = args.contentType; // header without a body is allowed
  }

  if (args.body != null && Buffer.byteLength(args.body) > args.maxResponseBytes) {
    args.parseErrors.push(
      `request body exceeds the ${args.maxResponseBytes}-byte cap`,
    );
    return args;
  }

  // A mutation must be a single request; pagination must never re-send a body.
  if (args.intent === 'mutation') {
    if (args.maxPagesFromCli && args.maxPages > 1) {
      args.parseErrors.push('mutations must be a single request; --max-pages must be 1');
      return args;
    }
    args.maxPages = 1;
  } else if (!args.maxPagesFromCli) {
    // Non-GET query/archive default to a single request unless the caller
    // explicitly opts into pagination with --max-pages.
    args.maxPages = 1;
  }

  return args;
}

// Build the request headers, injecting the resolved body content-type without
// clobbering a caller-supplied Content-Type.
function buildRequestHeaders(args) {
  const headers = { ...args.headers };
  if (args.bodyContentType) {
    const hasContentType = Object.keys(headers).some(
      (k) => k.toLowerCase() === 'content-type',
    );
    if (!hasContentType) headers['Content-Type'] = args.bodyContentType;
  }
  return headers;
}

async function fetchAllPages(args) {
  const initialUrl = applyParams(args.url, args.params);
  const method = args.method || 'GET';
  const maxAttempts = Number.isSafeInteger(args.maxAttempts) && args.maxAttempts > 0
    ? args.maxAttempts
    : method === 'GET'
      ? DEFAULT_GET_ATTEMPTS
      : DEFAULT_NON_IDEMPOTENT_ATTEMPTS;
  const requestHeaders = buildRequestHeaders(args);
  console.log(`Starting fetch from: ${redactUrl(initialUrl)}`);
  if (method !== 'GET') console.log(`Request method: ${method}`);
  console.log(`Pagination mode: ${args.pagination}`);
  console.log(`Max pages: ${args.maxPages}`);

  const allItems = [];
  const errors = [];
  let currentUrl = initialUrl;
  let page = 1;
  let hasMorePages = true;
  let stoppingReason = 'completed';
  let complete = true;
  let resourceLimitFailure = null;

  while (hasMorePages && page <= args.maxPages) {
    console.log(`Fetching page ${page}...`);
    const fetchOptions = { method, headers: requestHeaders };
    if (args.body != null) fetchOptions.body = args.body;

    try {
      const response = await fetchWithTimeout(
        currentUrl,
        fetchOptions,
        args.timeout,
        maxAttempts,
        args.maxResponseBytes,
        { allowRedirectOrigin: args.allowRedirectOrigin }
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      let body;
      try {
        const text = await readBodyBounded(
          response,
          args.maxResponseBytes,
          args.timeout
        );
        body = text.trim() === '' ? null : JSON.parse(text);
      } catch (e) {
        if (isResourceLimitError(e) || e instanceof RequestTimeoutError) {
          throw e;
        }
        throw new Error(`JSON parse failed: ${e.message}`);
      }

      if (method === 'GET' && getCachePath() !== null && !hasCredentialHeaders(fetchOptions.headers)) {
        try {
          const headersObj = {};
          response.headers.forEach((v, k) => {
            if (!isSensitiveHeaderName(k) && k.toLowerCase() !== 'set-cookie') {
              headersObj[k] = v;
            }
          });
          putCache('GET', currentUrl, response.status, headersObj, JSON.stringify(body), {
            requestHeaders: fetchOptions.headers,
          });
        } catch {
          /* non-fatal */
        }
      }

      const paginationInfo = detectPagination(
        response,
        body,
        args.pagination,
        args.cursorKey
      );

      let items = [];
      if (Array.isArray(body)) items = body;
      else if (body && body.data && Array.isArray(body.data)) items = body.data;
      else if (body && body.results && Array.isArray(body.results)) items = body.results;
      else if (body && body.items && Array.isArray(body.items)) items = body.items;
      else if (body && typeof body === 'object') items = [body];

      allItems.push(...items);

      if (paginationInfo) {
        switch (paginationInfo.type) {
          case 'link-header':
            currentUrl = resolveNextUrl(
              currentUrl,
              paginationInfo.nextUrl,
              args.headers,
              args.allowNextOrigin
            );
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
        stoppingReason = 'no_more_pages';
      }

      if (args.delay > 0 && page < args.maxPages && hasMorePages) {
        await sleep(args.delay);
      }
      page++;
    } catch (error) {
      const msg = redactSecretsInText(error.message || String(error));
      const errorRecord = {
        page,
        error: msg,
        code: error.code || 'fetch_error',
        url: redactUrl(currentUrl),
      };
      if (error.details) errorRecord.details = error.details;
      if (isResourceLimitError(error)) {
        resourceLimitFailure = errorRecord;
        console.error(
          JSON.stringify({
            error: 'resource_limit',
            code: error.code,
            message: msg,
            ...error.details,
            incomplete: true,
          })
        );
      } else {
        console.error(`Error fetching page ${page}: ${msg}`);
      }
      errors.push(errorRecord);
      complete = false;
      stoppingReason = isResourceLimitError(error)
        ? 'resource_limit'
        : error instanceof RequestTimeoutError
          ? 'timeout'
          : page === 1
            ? 'first_page_failed'
            : 'page_failed';
      break;
    }
  }

  if (page > args.maxPages && hasMorePages) {
    stoppingReason = 'max_pages_reached';
    complete = false;
  }

  return {
    initialUrl,
    allItems,
    errors,
    page,
    complete,
    stoppingReason,
    resourceLimitFailure,
  };
}


async function main() {
  const args = parseArgs(process.argv);

  if (args.selfTest) {
    await runSelfTest();
    return;
  }

  applyConfigDefaults(args);

  if (args.unknown.length) {
    console.error(`Error: ${args.unknown.length} unrecognized command-line argument(s)`);
    process.exit(1);
  }

  if (args.printEffectiveConfig) {
    if (args.parseErrors.length) {
      for (const e of args.parseErrors) console.error(`Error: ${e}`);
      process.exit(1);
    }
    process.stdout.write(JSON.stringify(effectiveConfigReport(args), null, 2) + '\n');
    return;
  }

  resolveRequestShape(args);

  if (args.parseErrors.length) {
    for (const e of args.parseErrors) console.error(`Error: ${e}`);
    process.exit(1);
  }
  if (!args.url) {
    console.error('Error: --url is required');
    console.error(
      'Usage: node api_fetch.mjs --url <url> [--headers <json>] [--params <json>] ' +
        '[--method GET|POST|PUT|PATCH|DELETE] [--intent query|archive|mutation] ' +
        '[--body-json <json>] [--body-file <path>] [--content-type <mime>] ' +
        '[--pagination auto|offset|cursor|page|link-header] [--cursor-key <path>] ' +
        '[--max-pages <n>] [--max-attempts <n>] [--config <path>] [--print-effective-config] ' +
        '[--delay <ms>] [--out <file>] [--format json|jsonl] ' +
        '[--timeout <ms>] [--max-response-bytes <n>] [--allow-partial] ' +
        '[--allow-next-origin <origin>]... [--allow-redirect-origin <origin>]...'
    );
    process.exit(1);
  }

  const {
    initialUrl,
    allItems,
    errors,
    page,
    complete,
    stoppingReason,
    resourceLimitFailure,
  } = await fetchAllPages(args);
  const pagesFetched = Math.max(0, page - 1);
  console.log(`Fetched ${allItems.length} total items across ${pagesFetched} pages.`);

  const meta = {
    complete,
    incomplete: !complete,
    status: complete ? 'complete' : 'incomplete',
    pages: pagesFetched,
    items: allItems.length,
    errors,
    stopping_reason: stoppingReason,
    timestamp: new Date().toISOString(),
    url: redactUrl(initialUrl),
    limits: { max_response_bytes: args.maxResponseBytes, timeout_ms: args.timeout },
  };

  if (args.out) {
    const output =
      args.format === 'jsonl'
        ? allItems.map((item) => JSON.stringify(item)).join('\n')
        : JSON.stringify(allItems, null, 2);
    writeFileSync(args.out, output);
    console.log(`Results written to: ${args.out}`);
    writeSidecar(args.out, meta);
  } else {
    console.log(JSON.stringify(allItems, null, 2));
  }

  if (resourceLimitFailure) {
    process.exitCode = 3;
  } else if (!complete && !args.allowPartial) {
    process.exitCode = 1;
  }
}

async function runSelfTest() {
  console.log('Running self-tests...');
  const errors = [];
  // Local HTTP fixtures need loopback; production path remains deny-by-default.
  setSsrfOptionsForTest({ allowHttp: true, allowLoopback: true });
  process.env.D_RESEARCH_SSRF_ALLOW_LOOPBACK = '1';

  const testArgs = parseArgs([
    'node',
    'api_fetch.mjs',
    '--url',
    'https://api.example.com/data',
    '--headers',
    '{"Authorization": "Bearer token123"}',
    '--params',
    '{"limit": 100}',
    '--pagination',
    'cursor',
    '--max-pages',
    '5',
    '--delay',
    '1000',
    '--out',
    'output.json',
    '--format',
    'jsonl',
    '--timeout',
    '15000',
    '--cursor-key',
    'meta.next',
  ]);
  if (testArgs.url !== 'https://api.example.com/data') errors.push('parseArgs URL mismatch');
  if (testArgs.headers.Authorization !== 'Bearer token123') errors.push('parseArgs headers mismatch');
  if (testArgs.params.limit !== 100) errors.push('parseArgs params mismatch');
  if (testArgs.cursorKey !== 'meta.next') errors.push('parseArgs cursor-key mismatch');

  const bad = parseArgs(['node', 'api_fetch.mjs', '--max-pages', 'nope', '--unknown-flag']);
  if (!bad.parseErrors.length) errors.push('invalid max-pages should error');
  if (bad.unknown.length !== 1) errors.push('unknown option not captured');

  const secretUnknownEquals = parseArgs([
    'node',
    'api_fetch.mjs',
    '--access-token=SUPERSECRET',
  ]);
  const secretUnknownPair = parseArgs([
    'node',
    'api_fetch.mjs',
    '--mystery-token',
    'SUPERSECRET',
  ]);
  if (JSON.stringify(secretUnknownEquals).includes('SUPERSECRET')) {
    errors.push('unknown --name=value must not retain the supplied secret');
  }
  if (JSON.stringify(secretUnknownPair).includes('SUPERSECRET')) {
    errors.push('unknown --name value must not retain the supplied secret');
  }

  const u1 = applyParams('https://api.example.com/data', { limit: 100, q: 'foo' });
  if (!u1.includes('limit=100') || !u1.includes('q=foo')) errors.push('applyParams missing params');

  const mockResponse1 = {
    headers: {
      get: (n) =>
        n.toLowerCase() === 'link'
          ? '</v1/next>; rel="next"'
          : null,
    },
  };
  const p1 = detectPagination(mockResponse1, {}, 'auto', null);
  if (!p1 || p1.type !== 'link-header') errors.push('Link header pagination not detected');

  try {
    resolveNextUrl(
      'https://api.example.com/v1/items',
      '/v1/next',
      {},
      []
    );
  } catch (e) {
    errors.push(`relative same-origin next should resolve: ${e.message}`);
  }
  const rel = resolveNextUrl('https://api.example.com/v1/items', '/v1/next', {}, []);
  if (rel !== 'https://api.example.com/v1/next') errors.push('relative next resolve mismatch');

  let blocked = false;
  try {
    resolveNextUrl(
      'https://api.example.com/v1',
      'https://other.example.com/next',
      { Authorization: 'Bearer x' },
      ['https://other.example.com']
    );
  } catch {
    blocked = true;
  }
  if (!blocked) errors.push('credential cross-origin next must hard-fail');

  const allowed = resolveNextUrl(
    'https://api.example.com/v1',
    'https://other.example.com/next',
    {},
    ['https://other.example.com']
  );
  if (!allowed.includes('other.example.com')) errors.push('allow-next-origin should permit public next');

  const mockResponse2 = { headers: { get: () => null } };
  const p2 = detectPagination(
    mockResponse2,
    { next_cursor: 'abc123', data: [1, 2, 3] },
    'auto',
    null
  );
  if (!p2 || p2.type !== 'cursor') errors.push('Cursor pagination not detected');

  const pCursorKey = detectPagination(
    mockResponse2,
    { meta: { next: 'tok' } },
    'auto',
    'meta.next'
  );
  if (!pCursorKey || pCursorKey.nextCursor !== 'tok') errors.push('cursor-key path failed');

  const p3 = detectPagination(
    mockResponse2,
    { offset: 0, total: 100, limit: 10, data: [1] },
    'auto',
    null
  );
  if (!p3 || p3.type !== 'offset') errors.push('Offset pagination not detected');

  if (redactUrl('https://x.test/?access_token=secret&q=1').includes('secret')) {
    errors.push('redactUrl failed to redact access_token');
  }

  // Credentialed request detection
  if (!isCredentialedRequest('https://a.test/', { 'X-API-Key': 'SUPERSECRET' })) {
    errors.push('X-API-Key should count as credentialed');
  }
  if (!isCredentialedRequest('https://a.test/', { 'X-Token': 'TOPSECRET' })) {
    errors.push('X-Token should count as credentialed');
  }
  if (!isCredentialedRequest('https://a.test/?api_key=QUERYSECRET', {})) {
    errors.push('api_key query should count as credentialed');
  }
  if (redactSecretsInText('X-Token: TOPSECRET').includes('TOPSECRET')) {
    errors.push('redactSecretsInText must redact X-Token value');
  }
  if (redactUrl('not a url access_token=SUPERSECRET').includes('SUPERSECRET')) {
    errors.push('redactUrl must redact even when URL parse fails');
  }

  // X-Token cross-origin next hard-fails even with allow-next-origin
  let xTokenBlocked = false;
  try {
    resolveNextUrl(
      'https://api.example.com/v1',
      'https://other.example.com/next',
      { 'X-Token': 'TOPSECRET' },
      ['https://other.example.com']
    );
  } catch (e) {
    xTokenBlocked = true;
    if (String(e.message).includes('TOPSECRET')) {
      errors.push('error message must not contain TOPSECRET');
    }
  }
  if (!xTokenBlocked) errors.push('X-Token cross-origin next must hard-fail');

  // malformed Link with secret
  let malformedBlocked = false;
  try {
    resolveNextUrl(
      'https://api.example.com/v1',
      'https://evil.example/next?access_token=SUPERSECRET',
      {},
      ['https://evil.example']
    );
  } catch (e) {
    malformedBlocked = true;
    if (String(e.message).includes('SUPERSECRET')) {
      errors.push('malformed/secret next error must redact SUPERSECRET');
    }
  }
  if (!malformedBlocked) {
    // same-origin? evil.example is cross-origin without credentials headers but URL has secret
    // must block because urlHasCredentials
    errors.push('secret-bearing next URL must hard-fail cross-origin');
  }

  // invalid numeric
  const badNum = parseArgs(['node', 'api_fetch.mjs', '--max-pages', '1abc']);
  if (!badNum.parseErrors.length) errors.push('max-pages 1abc should fail parse');

  const mutationAttempts = parseArgs([
    'node', 'api_fetch.mjs', '--method', 'DELETE', '--intent', 'mutation',
  ]);
  resolveRequestShape(mutationAttempts);
  if (mutationAttempts.maxAttempts !== DEFAULT_NON_IDEMPOTENT_ATTEMPTS) {
    errors.push('mutation default must use one network attempt');
  }
  const explicitAttempts = parseArgs([
    'node', 'api_fetch.mjs', '--method', 'POST', '--intent', 'mutation', '--max-attempts', '3',
  ]);
  resolveRequestShape(explicitAttempts);
  if (explicitAttempts.parseErrors.length || explicitAttempts.maxAttempts !== 3) {
    errors.push('explicit mutation max-attempts must be accepted');
  }
  const unknownPrint = parseArgs([
    'node', 'api_fetch.mjs', '--print-effective-config', '--not-a-real-option',
  ]);
  if (unknownPrint.unknown.length !== 1) errors.push('unknown option must be retained for print-config validation');

  const maxBytesArgs = parseArgs([
    'node',
    'api_fetch.mjs',
    '--max-response-bytes',
    '4096',
  ]);
  if (maxBytesArgs.maxResponseBytes !== 4096 || maxBytesArgs.parseErrors.length) {
    errors.push('max-response-bytes parsing failed');
  }

  const savedMaxBytesEnv = process.env.D_RESEARCH_HTTP_MAX_BYTES;
  process.env.D_RESEARCH_HTTP_MAX_BYTES = '-1';
  const badEnvLimit = parseArgs(['node', 'api_fetch.mjs']);
  if (!badEnvLimit.parseErrors.some((e) => e.includes('D_RESEARCH_HTTP_MAX_BYTES'))) {
    errors.push('negative D_RESEARCH_HTTP_MAX_BYTES must fail validation');
  }
  if (savedMaxBytesEnv === undefined) delete process.env.D_RESEARCH_HTTP_MAX_BYTES;
  else process.env.D_RESEARCH_HTTP_MAX_BYTES = savedMaxBytesEnv;

  const savedTimeoutEnv = process.env.D_RESEARCH_HTTP_TIMEOUT_SEC;
  process.env.D_RESEARCH_HTTP_TIMEOUT_SEC = '0';
  const badTimeoutEnv = parseArgs(['node', 'api_fetch.mjs', '--self-test']);
  if (!badTimeoutEnv.parseErrors.some((e) => e.includes('D_RESEARCH_HTTP_TIMEOUT_SEC'))) {
    errors.push('zero D_RESEARCH_HTTP_TIMEOUT_SEC must fail validation');
  }
  if (savedTimeoutEnv === undefined) delete process.env.D_RESEARCH_HTTP_TIMEOUT_SEC;
  else process.env.D_RESEARCH_HTTP_TIMEOUT_SEC = savedTimeoutEnv;

  let bodyCapBlocked = false;
  try {
    await readBodyBounded(new Response('12345'), 4, 1000);
  } catch (e) {
    bodyCapBlocked = e instanceof ResourceLimitError && e.code === 'http_max_bytes';
  }
  if (!bodyCapBlocked) errors.push('bounded body reader must reject oversized response');

  let bodyTimeoutBlocked = false;
  const slowBody = new ReadableStream({
    start(controller) {
      setTimeout(() => {
        try {
          controller.enqueue(new TextEncoder().encode('[]'));
          controller.close();
        } catch {
          // The reader is expected to be cancelled by the timeout.
        }
      }, 75);
    },
  });
  try {
    await readBodyBounded(new Response(slowBody), 1024, 10);
  } catch (e) {
    bodyTimeoutBlocked = e instanceof RequestTimeoutError;
  }
  if (!bodyTimeoutBlocked) errors.push('bounded body reader must enforce body timeout');

  const raSec = parseRetryAfter('2');
  if (raSec !== 2000) errors.push('Retry-After seconds parse failed');
  const raDate = parseRetryAfter(new Date(Date.now() + 5000).toUTCString());
  if (raDate == null || raDate > 120_000) errors.push('Retry-After HTTP-date parse failed');

  // SSRF: production options must reject cloud-metadata / private targets
  {
    const saved = { ..._ssrfOptions };
    setSsrfOptionsForTest({ allowHttp: false, allowLoopback: false });
    let metaBlocked = false;
    try {
      await fetchWithTimeout(
        'https://169.254.169.254/latest/meta-data/',
        { method: 'GET', headers: {} },
        1000,
        1
      );
    } catch (e) {
      metaBlocked = /non-public|not allowed|blocked|SSRF|private/i.test(String(e.message || e));
      if (!metaBlocked) metaBlocked = true; // any throw is fail-closed
    }
    if (!metaBlocked) errors.push('SSRF guard must block link-local metadata IP');
    setSsrfOptionsForTest(saved);
  }

  // Dual-origin HTTP fixture: A redirects to B with X-Token
  await (async () => {
    const hitsB = [];
    const serverB = createServer((req, res) => {
      const hit = {
        url: req.url,
        method: req.method,
        headers: { ...req.headers },
        body: '',
      };
      hitsB.push(hit);
      req.on('data', (chunk) => { hit.body += chunk.toString(); });
      req.on('end', () => {
        res.writeHead(200, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ ok: true, items: [] }));
      });
    });
    await new Promise((r) => serverB.listen(0, '127.0.0.1', r));
    const portB = serverB.address().port;
    const originB = `http://127.0.0.1:${portB}`;

    const serverA = createServer((req, res) => {
      const status = req.url === '/mutation-303' ? 303 : req.url === '/mutation-307' ? 307 : 302;
      res.writeHead(status, { Location: `${originB}/stolen` });
      res.end();
    });
    await new Promise((r) => serverA.listen(0, '127.0.0.1', r));
    const portA = serverA.address().port;
    const originA = `http://127.0.0.1:${portA}`;

    const outDir = mkdtempSync(join(tmpdir(), 'api_redir_'));
    const outFile = join(outDir, 'out.json');
    let exitCode = 0;
    let combined = '';
    try {
      const { spawnSync } = await import('node:child_process');
      const proc = spawnSync(
        process.execPath,
        [
          new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'),
          '--url',
          `${originA}/start`,
          '--headers',
          JSON.stringify({ 'X-Token': 'TOPSECRET' }),
          '--out',
          outFile,
          '--max-pages',
          '1',
          '--timeout',
          '5000',
        ],
        { encoding: 'utf-8', env: { ...process.env } }
      );
      exitCode = proc.status ?? 1;
      combined = `${proc.stdout || ''}\n${proc.stderr || ''}`;
    } catch (e) {
      // Fallback: call fetchWithTimeout directly
      try {
        await fetchWithTimeout(
          `${originA}/start`,
          { method: 'GET', headers: { 'X-Token': 'TOPSECRET' } },
          5000,
          1
        );
        exitCode = 0;
      } catch (err) {
        exitCode = 1;
        combined = String(err.message || err);
      }
    }

    // Direct unit-level call (more reliable than spawn path on Windows)
    try {
      await fetchWithTimeout(
        `${originA}/start`,
        { method: 'GET', headers: { 'X-Token': 'TOPSECRET' } },
        5000,
        1
      );
      errors.push('credentialed cross-origin redirect should throw');
    } catch (err) {
      const msg = String(err.message || err);
      if (msg.includes('TOPSECRET')) errors.push('redirect error leaked TOPSECRET');
      if (!msg.toLowerCase().includes('credential') && !msg.toLowerCase().includes('cross-origin')) {
        errors.push(`unexpected redirect error: ${msg}`);
      }
    }

    // A credential-free 303 must become a GET and drop the mutation body.
    hitsB.length = 0;
    await fetchWithTimeout(
      `${originA}/mutation-303`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"x":1}' },
      5000,
      1,
      DEFAULT_MAX_BODY_BYTES,
      { allowRedirectOrigin: [] },
    );
    if (hitsB.length !== 1 || hitsB[0].method !== 'GET' || hitsB[0].body) {
      errors.push('303 redirect must rewrite mutation to GET without body');
    }

    // A 307 state-changing cross-origin redirect is blocked unless explicitly
    // allowlisted, and the opt-in must preserve the method/body when allowed.
    hitsB.length = 0;
    let mutationRedirectBlocked = false;
    try {
      await fetchWithTimeout(
        `${originA}/mutation-307`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"x":1}' },
        5000,
        1,
        DEFAULT_MAX_BODY_BYTES,
        { allowRedirectOrigin: [] },
      );
    } catch (err) {
      mutationRedirectBlocked = /cross-origin.*redirect.*blocked/i.test(String(err.message || err));
    }
    if (!mutationRedirectBlocked || hitsB.length !== 0) {
      errors.push('307 cross-origin mutation redirect must block before target');
    }
    await fetchWithTimeout(
      `${originA}/mutation-307`,
      { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"x":1}' },
      5000,
      1,
      DEFAULT_MAX_BODY_BYTES,
      { allowRedirectOrigin: [originB] },
    );
    if (hitsB.length !== 1 || hitsB[0].method !== 'POST' || hitsB[0].body !== '{"x":1}') {
      errors.push('allowlisted 307 redirect must preserve method/body');
    }

    // B must not receive X-Token
    for (const hit of hitsB) {
      const h = hit.headers || {};
      for (const [k, v] of Object.entries(h)) {
        if (String(v).includes('TOPSECRET') || normalizeLooksSensitive(k, v)) {
          errors.push(`origin B received sensitive header ${k}`);
        }
      }
    }
    // Prefer zero requests to B when blocked before follow
    // (manual redirect may not connect to B at all)

    serverA.close();
    serverB.close();
    try {
      rmSync(outDir, { recursive: true, force: true });
    } catch {
      /* ignore */
    }

    function normalizeLooksSensitive(k, v) {
      return isSensitiveHeaderName(k) && String(v || '').length > 0 && k.toLowerCase() === 'x-token';
    }
  })();

  // Cache integration tests with isolated cache dir
  const savedEnv = process.env.D_RESEARCH_HTTP_CACHE_PATH;
  delete process.env.D_RESEARCH_HTTP_CACHE_PATH;
  const tmpDir = mkdtempSync(join(tmpdir(), 'api_fetch_test_'));
  const cacheDir = join(tmpDir, 'cache');
  process.env.D_RESEARCH_HTTP_CACHE_PATH = cacheDir;

  try {
    const url = 'https://example.invalid/api?q=alpha';
    putCache('GET', url, 200, { 'content-type': 'application/json' }, '{"who":"alice"}', {
      requestHeaders: { Authorization: 'Bearer A' },
      allowPrivate: true,
    });
    putCache('GET', url, 200, { 'content-type': 'application/json' }, '{"who":"bob"}', {
      requestHeaders: { Authorization: 'Bearer B' },
      allowPrivate: true,
    });
    putCache('GET', url, 200, { 'content-type': 'application/json' }, '{"who":"public"}');

    const ga = getCached('GET', url, { requestHeaders: { Authorization: 'Bearer A' } });
    if (!ga || ga.body.toString('utf-8') !== '{"who":"alice"}') {
      errors.push('cache: Bearer A should return alice');
    }
    const gb = getCached('GET', url, { requestHeaders: { Authorization: 'Bearer B' } });
    if (!gb || gb.body.toString('utf-8') !== '{"who":"bob"}') {
      errors.push('cache: Bearer B should return bob');
    }
    const gn = getCached('GET', url);
    if (!gn || gn.body.toString('utf-8') !== '{"who":"public"}') {
      errors.push('cache: no-auth should return public entry');
    }
    const gc = getCached('GET', url, { requestHeaders: { Authorization: 'Bearer C' } });
    if (gc !== null) errors.push('cache: Bearer C should be a miss');

    const entriesDir = join(cacheDir, 'entries');
    if (existsSync(entriesDir)) {
      for (const name of readdirSync(entriesDir)) {
        if (!name.endsWith('.json')) continue;
        const meta = JSON.parse(readFileSync(join(entriesDir, name), 'utf-8'));
        const headers = meta.headers || {};
        for (const k of Object.keys(headers)) {
          if (isSensitiveHeaderName(k)) {
            errors.push(`cache metadata leaks request header ${k}`);
          }
        }
      }
    }
  } finally {
    delete process.env.D_RESEARCH_HTTP_CACHE_PATH;
    if (savedEnv !== undefined) process.env.D_RESEARCH_HTTP_CACHE_PATH = savedEnv;
    try {
      rmSync(tmpDir, { recursive: true, force: true });
    } catch {
      /* ignore */
    }
  }

  // --- D2: config-driven maxPages precedence matrix (real on-disk config) ---
  {
    const withConfigDir = (configObj, fn) => {
      const dir = mkdtempSync(join(tmpdir(), 'api_cfg_unit_'));
      try {
        if (configObj !== null) {
          writeFileSync(join(dir, 'research.config.json'), JSON.stringify(configObj), 'utf8');
        }
        return fn(dir);
      } finally {
        rmSync(dir, { recursive: true, force: true });
      }
    };
    const resolvedMaxPages = (cliArgs, configObj) =>
      withConfigDir(configObj, (dir) => {
        const a = parseArgs(['node', 'api_fetch.mjs', ...cliArgs]);
        applyConfigDefaults(a, { startDir: dir });
        return a;
      });

    // absent CLI, absent config -> default 10.
    let a = resolvedMaxPages([], null);
    if (a.maxPages !== 10 || a.parseErrors.length) {
      errors.push(`precedence[absent,absent] expected 10, got ${a.maxPages}`);
    }
    // absent CLI, config 50 -> 50.
    a = resolvedMaxPages([], { api: { maxPagesPerEndpoint: 50 } });
    if (a.maxPages !== 50 || a.parseErrors.length) {
      errors.push(`precedence[absent,50] expected 50, got ${a.maxPages}`);
    }
    // CLI 7, absent config -> 7.
    a = resolvedMaxPages(['--max-pages', '7'], null);
    if (a.maxPages !== 7 || a.parseErrors.length) {
      errors.push(`precedence[7,absent] expected 7, got ${a.maxPages}`);
    }
    // CLI 7, config 50 -> 7 (CLI wins).
    a = resolvedMaxPages(['--max-pages', '7'], { api: { maxPagesPerEndpoint: 50 } });
    if (a.maxPages !== 7 || a.parseErrors.length) {
      errors.push(`precedence[7,50] expected 7 (CLI wins), got ${a.maxPages}`);
    }
    // invalid CLI, config 50 -> parse error (must NOT silently proceed).
    a = resolvedMaxPages(['--max-pages', 'nope'], { api: { maxPagesPerEndpoint: 50 } });
    if (!a.parseErrors.some((e) => e.includes('--max-pages'))) {
      errors.push('precedence[invalid,50] must record a --max-pages parse error');
    }
    // absent CLI, config invalid type -> structured config error, default retained.
    a = resolvedMaxPages([], { api: { maxPagesPerEndpoint: 'lots' } });
    if (!a.parseErrors.some((e) => e.includes('maxPagesPerEndpoint')) || a.maxPages !== 10) {
      errors.push('precedence[absent,invalid] must record a structured config error');
    }
    // Missing explicit --config path is a structured error.
    const missingCfg = parseArgs(['node', 'api_fetch.mjs', '--config', join(tmpdir(), 'no_such_dir_x', 'research.config.json')]);
    applyConfigDefaults(missingCfg);
    if (!missingCfg.parseErrors.some((e) => e.includes('config file not found'))) {
      errors.push('explicit missing --config must error');
    }
    // --print-effective-config must never echo secret header/config values.
    const secretCfgDir = mkdtempSync(join(tmpdir(), 'api_cfg_secret_'));
    try {
      writeFileSync(
        join(secretCfgDir, 'research.config.json'),
        JSON.stringify({ api: { maxPagesPerEndpoint: 3 }, headers: { Authorization: 'Bearer SUPERSECRET' } }),
        'utf8',
      );
      const sa = parseArgs(['node', 'api_fetch.mjs', '--print-effective-config']);
      applyConfigDefaults(sa, { startDir: secretCfgDir });
      const report = JSON.stringify(effectiveConfigReport(sa));
      if (report.includes('SUPERSECRET')) {
        errors.push('--print-effective-config must redact secret values');
      }
      if (sa.maxPages !== 3) errors.push('effective config should reflect discovered maxPages');
    } finally {
      rmSync(secretCfgDir, { recursive: true, force: true });
    }
  }

  // --- D2: real page-count integration (config value actually caps pagination) ---
  // Drives the real fetchAllPages loop in-process against an offset-paginated
  // mock server that always advertises more pages, so only maxPages can stop it.
  // Loopback is reachable here because runSelfTest enabled the SSRF test options.
  await (async () => {
    let hits = 0;
    const server = createServer((req, res) => {
      hits++;
      const u = new URL(req.url, 'http://127.0.0.1');
      const offset = Number(u.searchParams.get('offset') || '0');
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ offset, total: 100000, limit: 10, data: [offset] }));
    });
    await new Promise((r) => server.listen(0, '127.0.0.1', r));
    const port = server.address().port;
    const cfgDir = mkdtempSync(join(tmpdir(), 'api_cfg_int_'));
    const emptyDir = mkdtempSync(join(tmpdir(), 'api_cfg_empty_'));
    writeFileSync(
      join(cfgDir, 'research.config.json'),
      JSON.stringify({ api: { maxPagesPerEndpoint: 3 } }),
      'utf8',
    );
    const savedCachePath = process.env.D_RESEARCH_HTTP_CACHE_PATH;
    const cacheDirs = [];
    const runPages = async (cliArgs, startDir) => {
      hits = 0;
      // Fresh cache per run so every page is a real server hit (no cross-run reuse).
      const cacheDir = mkdtempSync(join(tmpdir(), 'api_int_cache_'));
      cacheDirs.push(cacheDir);
      process.env.D_RESEARCH_HTTP_CACHE_PATH = cacheDir;
      const a = parseArgs([
        'node', 'api_fetch.mjs',
        '--url', `http://127.0.0.1:${port}/data`,
        '--pagination', 'offset',
        '--delay', '0',
        '--timeout', '5000',
        ...cliArgs,
      ]);
      applyConfigDefaults(a, { startDir });
      const res = await fetchAllPages(a);
      return { pages: res.page - 1, hits };
    };
    try {
      // Config maxPages=3 (discovered), no CLI flag -> exactly 3 real pages.
      let r = await runPages([], cfgDir);
      if (r.pages !== 3 || r.hits !== 3) {
        errors.push(`config maxPages=3 should fetch 3 pages, got pages=${r.pages} hits=${r.hits}`);
      }
      // CLI --max-pages=2 overrides config -> exactly 2 real pages.
      r = await runPages(['--max-pages', '2'], cfgDir);
      if (r.pages !== 2 || r.hits !== 2) {
        errors.push(`CLI --max-pages=2 must win, got pages=${r.pages} hits=${r.hits}`);
      }
      // No config, no flag -> built-in default 10 real pages.
      r = await runPages([], emptyDir);
      if (r.pages !== 10 || r.hits !== 10) {
        errors.push(`default maxPages should fetch 10 pages, got pages=${r.pages} hits=${r.hits}`);
      }
    } finally {
      await new Promise((r) => server.close(r));
      if (savedCachePath === undefined) delete process.env.D_RESEARCH_HTTP_CACHE_PATH;
      else process.env.D_RESEARCH_HTTP_CACHE_PATH = savedCachePath;
      for (const d of cacheDirs) rmSync(d, { recursive: true, force: true });
      rmSync(cfgDir, { recursive: true, force: true });
      rmSync(emptyDir, { recursive: true, force: true });
    }
  })();

  // --- D3: additive HTTP method / body / intent validation ---
  {
    const shape = (cli) => {
      const a = parseArgs(['node', 'api_fetch.mjs', '--url', 'https://api.example.com/x', ...cli]);
      resolveRequestShape(a);
      return a;
    };
    let a = shape([]);
    if (a.method !== 'GET' || a.body !== null || a.parseErrors.length) {
      errors.push('GET default must stay a read-only no-body request');
    }
    a = shape(['--body-json', '{"x":1}']);
    if (!a.parseErrors.some((e) => e.includes('not allowed with GET'))) {
      errors.push('GET with a body must error');
    }
    a = shape(['--method', 'POST']);
    if (!a.parseErrors.some((e) => e.includes('requires an explicit --intent'))) {
      errors.push('POST without --intent must error');
    }
    a = shape(['--method', 'BOGUS', '--intent', 'query']);
    if (!a.parseErrors.some((e) => e.includes('invalid --method'))) {
      errors.push('invalid --method must error');
    }
    a = shape(['--method', 'PUT', '--intent', 'query']);
    if (!a.parseErrors.some((e) => e.includes('not allowed for --intent query'))) {
      errors.push('query intent must forbid PUT');
    }
    a = shape(['--method', 'DELETE', '--intent', 'mutation']);
    if (a.parseErrors.length || a.method !== 'DELETE' || a.maxPages !== 1) {
      errors.push('DELETE mutation should be a valid single request');
    }
    a = shape(['--method', 'POST', '--intent', 'mutation', '--max-pages', '3']);
    if (!a.parseErrors.some((e) => e.includes('single request'))) {
      errors.push('mutation with --max-pages>1 must error');
    }
    a = shape(['--method', 'POST', '--intent', 'query', '--body-json', '{}', '--body-file', 'x']);
    if (!a.parseErrors.some((e) => e.includes('mutually exclusive'))) {
      errors.push('body-json + body-file must error');
    }
    a = shape(['--method', 'POST', '--intent', 'query', '--body-json', '{bad']);
    if (!a.parseErrors.some((e) => e.includes('not valid JSON'))) {
      errors.push('invalid --body-json must error');
    }
    a = shape(['--method', 'POST', '--intent', 'query', '--body-json', '{"q":"x"}']);
    if (a.parseErrors.length || a.bodyContentType !== 'application/json' || a.maxPages !== 1) {
      errors.push('POST query body should default content-type and be a single request');
    }
    a = shape(['--method', 'POST', '--intent', 'query', '--max-response-bytes', '4', '--body-json', '{"q":"toolong"}']);
    if (!a.parseErrors.some((e) => e.includes('cap'))) {
      errors.push('oversize request body must be blocked');
    }
    a = shape(['--method', 'POST', '--intent', 'query', '--body-json', '{}', '--max-pages', '4']);
    if (a.parseErrors.length || a.maxPages !== 4) {
      errors.push('POST query with explicit --max-pages should keep pagination');
    }
  }

  // --- D3: real method + body integration (echo server) ---
  await (async () => {
    const seen = [];
    let retryHits = 0;
    const server = createServer((req, res) => {
      let body = '';
      req.on('data', (c) => {
        body += c;
      });
      req.on('end', () => {
        seen.push({ method: req.method, contentType: req.headers['content-type'] || null, body });
        if (req.url === '/retry-mutation') {
          retryHits += 1;
          res.writeHead(retryHits < 3 ? 500 : 200, { 'content-type': 'application/json' });
          res.end(JSON.stringify({ items: [] }));
        } else if (req.url === '/empty') {
          res.writeHead(204);
          res.end();
        } else if (req.url === '/graphql') {
          res.writeHead(200, { 'content-type': 'application/json' });
          res.end(JSON.stringify({ data: { viewer: { id: 'viewer-1' } } }));
        } else {
          res.writeHead(200, { 'content-type': 'application/json' });
          res.end(JSON.stringify({ ok: true, items: [] }));
        }
      });
    });
    await new Promise((r) => server.listen(0, '127.0.0.1', r));
    const port = server.address().port;
    const savedCache = process.env.D_RESEARCH_HTTP_CACHE_PATH;
    delete process.env.D_RESEARCH_HTTP_CACHE_PATH;
    const bodyDir = mkdtempSync(join(tmpdir(), 'api_body_'));
    const run = async (cli, path = '/x') => {
      const a = parseArgs([
        'node', 'api_fetch.mjs',
        '--url', `http://127.0.0.1:${port}${path}`,
        '--delay', '0', '--timeout', '5000',
        ...cli,
      ]);
      resolveRequestShape(a);
      if (a.parseErrors.length) return { err: a.parseErrors };
      const result = await fetchAllPages(a);
      return { last: seen[seen.length - 1], result };
    };
    try {
      // GraphQL-style POST query -> POST, JSON body, application/json.
      seen.length = 0;
      let r = await run(['--method', 'POST', '--intent', 'query', '--body-json', '{"query":"{ me }"}']);
      if (r.err) errors.push(`POST query should be valid: ${r.err}`);
      else if (r.last.method !== 'POST' || !r.last.body.includes('me') || r.last.contentType !== 'application/json') {
        errors.push(`POST query method/body/content-type mismatch: ${JSON.stringify(r.last)}`);
      }
      // PUT mutation.
      seen.length = 0;
      r = await run(['--method', 'PUT', '--intent', 'mutation', '--body-json', '{"v":1}']);
      if (r.err) errors.push(`PUT mutation should be valid: ${r.err}`);
      else if (r.last.method !== 'PUT' || !r.last.body.includes('"v"')) errors.push('PUT mutation method/body mismatch');
      // DELETE mutation is exactly one request.
      seen.length = 0;
      r = await run(['--method', 'DELETE', '--intent', 'mutation']);
      if (r.err) errors.push(`DELETE mutation should be valid: ${r.err}`);
      else if (r.last.method !== 'DELETE' || seen.length !== 1) errors.push('DELETE mutation must be a single request');
      // body-file with explicit content-type.
      const bf = join(bodyDir, 'b.json');
      writeFileSync(bf, '{"file":true}', 'utf8');
      seen.length = 0;
      r = await run(['--method', 'POST', '--intent', 'archive', '--body-file', bf, '--content-type', 'application/json']);
      if (r.err) errors.push(`POST archive body-file should be valid: ${r.err}`);
      else if (!r.last.body.includes('file') || r.last.contentType !== 'application/json') errors.push('body-file contents/content-type not sent');

      // An explicitly supplied Content-Type is honored even without a body.
      seen.length = 0;
      r = await run(['--method', 'DELETE', '--intent', 'mutation', '--content-type', 'application/json']);
      if (r.err || r.last.contentType !== 'application/json') errors.push('bodyless content-type must be sent');

      // Empty successful mutation responses (204/205) are valid and do not
      // trigger a misleading JSON parse failure.
      seen.length = 0;
      r = await run(['--method', 'DELETE', '--intent', 'mutation'], '/empty');
      if (r.err || !r.result.complete || r.result.errors.length || r.result.allItems.length) {
        errors.push('204 mutation response should complete with no items');
      }

      // Preserve a GraphQL/object response instead of silently converting it
      // to an empty array.
      seen.length = 0;
      r = await run(['--method', 'POST', '--intent', 'query', '--body-json', '{"query":"{ viewer { id } }"}'], '/graphql');
      if (r.err || !r.result.allItems[0]?.data?.viewer?.id) {
        errors.push('GraphQL object response must be preserved');
      }

      // Non-idempotent requests are one attempt by default; a caller may opt
      // into more attempts explicitly.
      retryHits = 0;
      seen.length = 0;
      r = await run(['--method', 'POST', '--intent', 'mutation'], '/retry-mutation');
      if (retryHits !== 1 || r.result.complete) errors.push('mutation default retry policy must be single-attempt');
      retryHits = 0;
      seen.length = 0;
      r = await run(['--method', 'POST', '--intent', 'mutation', '--max-attempts', '3'], '/retry-mutation');
      if (retryHits !== 3 || !r.result.complete) errors.push('explicit mutation retries must be honored');
    } finally {
      await new Promise((r) => server.close(r));
      if (savedCache === undefined) delete process.env.D_RESEARCH_HTTP_CACHE_PATH;
      else process.env.D_RESEARCH_HTTP_CACHE_PATH = savedCache;
      rmSync(bodyDir, { recursive: true, force: true });
    }
  })();

  if (errors.length) {
    console.error('api_fetch self-test FAILED:');
    for (const e of errors) console.error(`  - ${e}`);
    process.exit(1);
  }
  console.log('api_fetch self-test ok');
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
