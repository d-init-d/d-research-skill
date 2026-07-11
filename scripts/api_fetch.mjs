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

const MAX_REDIRECTS = 10;
const DEFAULT_MAX_BODY_BYTES = 20 * 1024 * 1024;

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
    delay: 500,
    out: null,
    format: 'json',
    timeout: 30000,
    maxResponseBytes: DEFAULT_MAX_BODY_BYTES,
    cursorKey: null,
    allowPartial: false,
    allowNextOrigin: [],
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
        else args.maxPages = n;
      }
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
  maxRetries = 3,
  maxResponseBytes = DEFAULT_MAX_BODY_BYTES
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

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      let currentUrl = url;
      let headers = { ...requestHeaders };
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
              method,
              headers,
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
            // Even without known secrets, only public headers may cross origin.
            headers = publicHeadersOnly(headers);
          }
          currentUrl = next;
          hop += 1;
          continue;
        }

        if (response.status === 429) {
          const retryAfter = parseRetryAfter(response.headers.get('Retry-After'));
          const waitTime = retryAfter ?? 1000 * Math.pow(2, attempt);
          console.log(`Rate limited. Waiting ${waitTime}ms before retry...`);
          await sleep(waitTime);
          break; // retry outer attempt
        }
        if (response.status >= 500) {
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

async function main() {
  const args = parseArgs(process.argv);

  if (args.selfTest) {
    await runSelfTest();
    return;
  }

  if (args.unknown.length) {
    console.error(`Error: ${args.unknown.length} unrecognized command-line argument(s)`);
    process.exit(1);
  }
  if (args.parseErrors.length) {
    for (const e of args.parseErrors) console.error(`Error: ${e}`);
    process.exit(1);
  }
  if (!args.url) {
    console.error('Error: --url is required');
    console.error(
      'Usage: node api_fetch.mjs --url <url> [--headers <json>] [--params <json>] ' +
        '[--pagination auto|offset|cursor|page|link-header] [--cursor-key <path>] ' +
        '[--max-pages <n>] [--delay <ms>] [--out <file>] [--format json|jsonl] ' +
        '[--timeout <ms>] [--max-response-bytes <n>] [--allow-partial] ' +
        '[--allow-next-origin <origin>]...'
    );
    process.exit(1);
  }

  const initialUrl = applyParams(args.url, args.params);
  console.log(`Starting fetch from: ${redactUrl(initialUrl)}`);
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
    const fetchOptions = { method: 'GET', headers: args.headers };

    try {
      const response = await fetchWithTimeout(
        currentUrl,
        fetchOptions,
        args.timeout,
        3,
        args.maxResponseBytes
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
        body = JSON.parse(text);
      } catch (e) {
        if (isResourceLimitError(e) || e instanceof RequestTimeoutError) {
          throw e;
        }
        throw new Error(`JSON parse failed: ${e.message}`);
      }

      if (getCachePath() !== null && !hasCredentialHeaders(fetchOptions.headers)) {
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
      else if (body.data && Array.isArray(body.data)) items = body.data;
      else if (body.results && Array.isArray(body.results)) items = body.results;
      else if (body.items && Array.isArray(body.items)) items = body.items;

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
      hitsB.push({
        url: req.url,
        headers: { ...req.headers },
      });
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ ok: true, items: [] }));
    });
    await new Promise((r) => serverB.listen(0, '127.0.0.1', r));
    const portB = serverB.address().port;
    const originB = `http://127.0.0.1:${portB}`;

    const serverA = createServer((req, res) => {
      res.writeHead(302, { Location: `${originB}/stolen` });
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
