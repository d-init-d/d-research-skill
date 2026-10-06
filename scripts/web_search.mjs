#!/usr/bin/env node

import crypto from 'node:crypto';
import fs from 'node:fs';
import net from 'node:net';
import {
  headersHaveCredentials,
  publicHeadersOnly,
  urlHasCredentials,
} from './lib/credentials.mjs';
import { packageUserAgent } from './lib/package_metadata.mjs';
import { fetchPublicHttp, isNonPublicIp, setTestDnsResolver, setTestConnectFactory } from './lib/ssrf_guards.mjs';
import { EventEmitter } from 'node:events';
import { Readable } from 'node:stream';

export const USER_AGENT = packageUserAgent('web-search');
export const DEFAULT_MAX_RESPONSE_BYTES = 20 * 1024 * 1024;
export const DEFAULT_TIMEOUT_MS = 30_000;
export const MAX_REDIRECTS = 5;
export const REDIRECT_STATUSES = new Set([301, 302, 303, 307, 308]);

export const CHALLENGE_REGEX = /(?:verify you are human|captcha|recaptcha|hcaptcha|cf-turnstile|cf-challenge|challenge-running|bot detection|unusual traffic|automated requests|checking your browser|attention required|access denied|security check)/i;

const BLOCKED_HOSTNAMES = new Set([
  'localhost',
  'localhost.localdomain',
  'metadata.google.internal',
  'metadata',
  'instance-data',
]);

let requestOverrides = {};

export class ResourceLimitError extends Error {
  constructor(message, limit, observed = null) {
    super(message);
    this.name = 'ResourceLimitError';
    this.exitCode = 3;
    this.limit = limit;
    this.observed = observed;
  }
}

export class SearchProviderError extends Error {
  constructor(message, statusKind = 'provider_error', details = {}) {
    super(message);
    this.name = 'SearchProviderError';
    this.statusKind = statusKind; // 'success' | 'no_results' | 'blocked' | 'provider_error' | 'resource_limit'
    this.provider = details.provider || null;
    this.httpStatus = details.httpStatus || null;
    this.retryAfter = details.retryAfter || null;
    this.details = details;
  }
}

export function parsePositiveInteger(value, label) {
  const raw = String(value ?? '').trim();
  if (!/^\d+$/.test(raw)) throw new Error(`${label} must be a positive integer`);
  const parsed = Number(raw);
  if (!Number.isSafeInteger(parsed) || parsed <= 0) {
    throw new Error(`${label} must be a positive safe integer`);
  }
  return parsed;
}

export function redactSecrets(value) {
  let text = String(value ?? '');
  for (const name of ['BRAVE_API_KEY', 'GOOGLE_CSE_KEY', 'GOOGLE_CSE_ID']) {
    const secret = process.env[name];
    if (secret) text = text.split(secret).join('[REDACTED]');
  }
  text = text.replace(/([?&](?:key|cx|token|api_key)=)[^&\s]+/gi, '$1[REDACTED]');
  return text;
}

export function isPrivateIpOrBlockedHost(hostname) {
  const h = String(hostname || '').toLowerCase().replace(/^\[|\]$/g, '');
  if (BLOCKED_HOSTNAMES.has(h) || h.endsWith('.localhost')) return true;
  if (h === '::1' || h === '0.0.0.0') return true;
  if (/^127\.\d+\.\d+\.\d+$/.test(h)) return true;
  if (/^10\.\d+\.\d+\.\d+$/.test(h)) return true;
  if (/^192\.168\.\d+\.\d+$/.test(h)) return true;
  if (/^172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+$/.test(h)) return true;
  if (/^169\.254\.\d+\.\d+$/.test(h)) return true;
  if (/^100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d+\.\d+$/.test(h)) return true;
  if (net.isIP(h) && isNonPublicIp(h)) return true;
  return false;
}

export function validateHttpUrl(value, base = undefined) {
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

export function assertNotPrivateOrBlocked(parsedUrl) {
  if (process.env.D_RESEARCH_SSRF_ALLOW_LOOPBACK === '1') return;
  if (isPrivateIpOrBlockedHost(parsedUrl.hostname)) {
    throw new Error(`blocked or private destination not allowed: ${parsedUrl.hostname}`);
  }
}

export function activeLimits(overrides = {}) {
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

export async function readResponseTextBounded(response, maxBytes) {
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

export async function fetchWithManualRedirects(url, options = {}, timeoutMs = DEFAULT_TIMEOUT_MS) {
  let current = validateHttpUrl(url);
  assertNotPrivateOrBlocked(current);
  let headers = { ...(options.headers || {}) };
  let credentialed = headersHaveCredentials(headers) || urlHasCredentials(current.href);

  for (let hop = 0; hop <= MAX_REDIRECTS; hop++) {
    const signal = timeoutMs ? AbortSignal.timeout(timeoutMs) : options?.signal;
    const response = await fetchPublicHttp(current.href, {
      ...options,
      headers,
      redirect: 'manual',
      signal,
    }, { allowHttp: true });
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
    assertNotPrivateOrBlocked(next);
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

export async function fetchTextBounded(url, options = {}, overrides = requestOverrides) {
  const limits = activeLimits(overrides);
  const response = await fetchWithManualRedirects(url, options, limits.timeoutMs);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }
  return readResponseTextBounded(response, limits.maxBytes);
}

export async function fetchJsonBounded(url, options = {}, overrides = requestOverrides) {
  const text = await fetchTextBounded(url, options, overrides);
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`Invalid JSON response: ${error.message}`);
  }
}

export function isValidResultUrl(rawUrl) {
  try {
    const parsed = new URL(rawUrl);
    return ['http:', 'https:'].includes(parsed.protocol) && !parsed.username && !parsed.password;
  } catch {
    return false;
  }
}

export function isValidIsoTimestamp(value) {
  if (typeof value !== 'string' || !value.trim()) return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})$/.exec(value.trim());
  if (!match) return false;
  const [, yStr, mStr, dStr, hStr, minStr, sStr] = match;
  const year = parseInt(yStr, 10);
  const month = parseInt(mStr, 10);
  const day = parseInt(dStr, 10);
  const hour = parseInt(hStr, 10);
  const minute = parseInt(minStr, 10);
  const second = parseInt(sStr, 10);
  if (month < 1 || month > 12) return false;
  if (hour > 23 || minute > 59 || second > 59) return false;
  const isLeap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const daysInMonth = [31, isLeap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (day < 1 || day > daysInMonth[month - 1]) return false;
  const d = new Date(value);
  return !Number.isNaN(d.getTime());
}

export function loadHostResultsArtifact(artifactPath, expectedQuery = null, maxBytes = DEFAULT_MAX_RESPONSE_BYTES) {
  if (!fs.existsSync(artifactPath)) {
    throw new SearchProviderError(`Host results file not found: ${artifactPath}`, 'provider_error', {
      provider: 'host',
    });
  }
  const stat = fs.statSync(artifactPath);
  if (stat.size > maxBytes) {
    throw new ResourceLimitError(`Host results file size ${stat.size} exceeds limit ${maxBytes}`, maxBytes, stat.size);
  }

  const rawBytes = fs.readFileSync(artifactPath);
  const fileHash = crypto.createHash('sha256').update(rawBytes).digest('hex');
  let data;
  try {
    data = JSON.parse(rawBytes.toString('utf8'));
  } catch (error) {
    throw new SearchProviderError(`Host results file contains invalid JSON: ${error.message}`, 'provider_error', {
      provider: 'host',
    });
  }

  let artifactQuery = null;
  let rawList = [];

  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    throw new SearchProviderError('Host results file must be an object with provider and retrieval metadata', 'provider_error', {
      provider: 'host',
    });
  }

  artifactQuery = data.query || null;
  if (Array.isArray(data.results)) {
    rawList = data.results;
  } else if (Array.isArray(data.search_results)) {
    rawList = data.search_results;
  } else if (Array.isArray(data.items)) {
    rawList = data.items;
  } else {
    throw new SearchProviderError('Host results file schema invalid: missing results array', 'provider_error', {
      provider: 'host',
    });
  }

  if (expectedQuery) {
    if (!artifactQuery) {
      throw new SearchProviderError(
        `Host results artifact missing query binding: expected '${expectedQuery}'`,
        'provider_error',
        { provider: 'host', expectedQuery }
      );
    }
    if (artifactQuery.trim().toLowerCase() !== expectedQuery.trim().toLowerCase()) {
      throw new SearchProviderError(
        `Host results artifact query mismatch: expected '${expectedQuery}', got '${artifactQuery}'`,
        'provider_error',
        { provider: 'host', artifactQuery, expectedQuery }
      );
    }
  }

  if (data.status === 'blocked') {
    return {
      status: 'blocked',
      results: [],
      artifact_hash: fileHash,
      tool_call_id: data.tool_call_id || null,
      message: data.message || 'Host search results blocked',
      blocker: data.blocker || { code: 'host_blocked', message: 'Host search blocked' },
    };
  }

  if (!data.provider || typeof data.provider !== 'string' || !data.provider.trim()) {
    throw new SearchProviderError(
      'Host results artifact missing required provider',
      'provider_error',
      { provider: 'host' }
    );
  }

  const retrievedAt = data.retrieved_at;
  if (!isValidIsoTimestamp(retrievedAt)) {
    throw new SearchProviderError(
      `Host results artifact missing or invalid retrieved_at timestamp: '${retrievedAt}'`,
      'provider_error',
      { provider: data.provider, retrieved_at: retrievedAt }
    );
  }

  const defaultProvider = data.provider.trim();
  const defaultEngine = String(data.source_engine || data.engine || defaultProvider).trim();

  const normalized = [];
  for (const item of rawList) {
    if (!item || typeof item !== 'object') continue;
    const url = item.url || item.link || '';
    if (!isValidResultUrl(url)) continue;

    const itemRetrievedAt = item.retrieved_at || retrievedAt;
    if (item.retrieved_at && !isValidIsoTimestamp(item.retrieved_at)) {
      throw new SearchProviderError(
        `Host result item has invalid retrieved_at timestamp: '${item.retrieved_at}'`,
        'provider_error',
        { provider: defaultProvider, retrieved_at: item.retrieved_at }
      );
    }

    normalized.push({
      title: String(item.title || '').trim(),
      url: String(url).trim(),
      snippet: String(item.snippet || item.content || item.description || '').trim(),
      provider: String(item.provider || defaultProvider).trim(),
      source_engine: String(item.source_engine || item.engine || defaultEngine).trim(),
      retrieved_at: itemRetrievedAt,
    });
  }

  return {
    status: normalized.length > 0 ? 'success' : 'no_results',
    results: normalized,
    artifact_hash: fileHash,
    tool_call_id: data?.tool_call_id || null,
  };
}

export async function searchDuckDuckGo(query, limit, overrides = requestOverrides) {
  const url = `https://html.duckduckgo.com/html/?q=${encodeURIComponent(query)}`;
  const limits = activeLimits(overrides);
  let response;
  try {
    response = await fetchWithManualRedirects(url, {
      headers: { 'User-Agent': USER_AGENT }
    }, limits.timeoutMs);
  } catch (err) {
    if (err instanceof ResourceLimitError) throw err;
    throw new SearchProviderError(`DuckDuckGo network error: ${err.message}`, 'provider_error', {
      provider: 'duckduckgo',
    });
  }

  const status = response.status;
  if (status === 429) {
    const retryAfter = response.headers?.get?.('retry-after') || null;
    throw new SearchProviderError(`HTTP 429: Too Many Requests${retryAfter ? ` (Retry-After: ${retryAfter})` : ''}`, 'blocked', {
      provider: 'duckduckgo',
      httpStatus: 429,
      retryAfter,
    });
  }
  if (status === 403) {
    throw new SearchProviderError('HTTP 403: Forbidden (bot detection or IP blocked)', 'blocked', {
      provider: 'duckduckgo',
      httpStatus: 403,
    });
  }
  if (status === 202) {
    throw new SearchProviderError('HTTP 202: Bot verification challenge page', 'blocked', {
      provider: 'duckduckgo',
      httpStatus: 202,
    });
  }
  if (!response.ok) {
    throw new SearchProviderError(`HTTP ${status}: ${response.statusText || 'request failed'}`, 'provider_error', {
      provider: 'duckduckgo',
      httpStatus: status,
    });
  }

  const html = await readResponseTextBounded(response, limits.maxBytes);

  if (CHALLENGE_REGEX.test(html)) {
    throw new SearchProviderError('Anti-bot challenge detected in HTML body', 'blocked', {
      provider: 'duckduckgo',
      httpStatus: status,
    });
  }

  const results = [];
  const nowIso = new Date().toISOString();
  const resultBlocks = html.split(/class="result__body"/);
  for (let i = 1; i < resultBlocks.length && results.length < limit; i++) {
    const block = resultBlocks[i];
    const linkMatch = block.match(/class="result__a"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/);
    if (!linkMatch) continue;

    let href = linkMatch[1];
    const titleHtml = linkMatch[2];
    const uddgMatch = href.match(/uddg=([^&]+)/);
    if (uddgMatch) {
      href = decodeURIComponent(uddgMatch[1]);
    }
    const title = titleHtml.replace(/<[^>]+>/g, '').trim();
    const snippetMatch = block.match(/class="result__snippet"[^>]*>([\s\S]*?)<\/(?:a|span|div)/);
    const snippet = snippetMatch ? snippetMatch[1].replace(/<[^>]+>/g, '').trim() : '';

    if (title && href && isValidResultUrl(href)) {
      results.push({
        title,
        url: href,
        snippet,
        provider: 'duckduckgo',
        source_engine: 'duckduckgo',
        retrieved_at: nowIso,
      });
    }
  }

  if (results.length === 0) {
    const isGenuineNoResults =
      /(?:no-results|no results found|no results for|did not match any documents|zero_click_wrapper|results--message|no-results-message|no_results)/i.test(html);
    if (!isGenuineNoResults) {
      throw new SearchProviderError('DuckDuckGo HTML malformed or markup changed', 'provider_error', {
        provider: 'duckduckgo',
        httpStatus: status,
      });
    }
    return [];
  }

  return results.slice(0, limit);
}

export async function searchSearXNG(query, limit, overrides = requestOverrides) {
  const instance = process.env.SEARXNG_INSTANCE || 'https://searx.be';
  const parsed = validateHttpUrl(instance);
  assertNotPrivateOrBlocked(parsed);

  const url = `${instance.replace(/\/+$/, '')}/search?q=${encodeURIComponent(query)}&format=json`;
  const limits = activeLimits(overrides);
  let response;
  try {
    response = await fetchWithManualRedirects(url, {
      headers: { 'User-Agent': USER_AGENT }
    }, limits.timeoutMs);
  } catch (err) {
    if (err instanceof ResourceLimitError) throw err;
    throw new SearchProviderError(`SearXNG network error: ${err.message}`, 'provider_error', {
      provider: 'searxng',
    });
  }

  const status = response.status;
  if (status === 429) {
    const retryAfter = response.headers?.get?.('retry-after') || null;
    throw new SearchProviderError(`HTTP 429: Rate limited${retryAfter ? ` (Retry-After: ${retryAfter})` : ''}`, 'blocked', {
      provider: 'searxng',
      httpStatus: 429,
      retryAfter,
    });
  }
  if (status === 403) {
    throw new SearchProviderError('HTTP 403: Forbidden', 'blocked', {
      provider: 'searxng',
      httpStatus: 403,
    });
  }
  if (!response.ok) {
    throw new SearchProviderError(`HTTP ${status}: ${response.statusText}`, 'provider_error', {
      provider: 'searxng',
      httpStatus: status,
    });
  }

  const text = await readResponseTextBounded(response, limits.maxBytes);
  let data;
  try {
    data = JSON.parse(text);
  } catch (error) {
    throw new SearchProviderError(`Invalid JSON response: ${error.message}`, 'provider_error', {
      provider: 'searxng',
    });
  }

  if (!data || !Array.isArray(data.results)) {
    throw new SearchProviderError('Unexpected response format: missing results array', 'provider_error', {
      provider: 'searxng',
    });
  }

  const nowIso = new Date().toISOString();
  return data.results
    .filter(r => isValidResultUrl(r.url))
    .slice(0, limit)
    .map(r => ({
      title: r.title || '',
      url: r.url || '',
      snippet: r.content || '',
      provider: 'searxng',
      source_engine: 'searxng',
      retrieved_at: nowIso,
    }));
}

export async function searchBrave(query, limit, overrides = requestOverrides) {
  const apiKey = process.env.BRAVE_API_KEY;
  if (!apiKey) {
    throw new SearchProviderError('BRAVE_API_KEY environment variable is required for Brave engine', 'provider_error', {
      provider: 'brave',
    });
  }

  const url = `https://api.search.brave.com/res/v1/web/search?q=${encodeURIComponent(query)}&count=${limit}`;
  const limits = activeLimits(overrides);
  let response;
  try {
    response = await fetchWithManualRedirects(url, {
      headers: {
        'User-Agent': USER_AGENT,
        'X-Subscription-Token': apiKey
      }
    }, limits.timeoutMs);
  } catch (err) {
    if (err instanceof ResourceLimitError) throw err;
    throw new SearchProviderError(`Brave network error: ${err.message}`, 'provider_error', {
      provider: 'brave',
    });
  }

  const status = response.status;
  if (status === 429) {
    const retryAfter = response.headers?.get?.('retry-after') || null;
    throw new SearchProviderError(`HTTP 429: Too Many Requests${retryAfter ? ` (Retry-After: ${retryAfter})` : ''}`, 'blocked', {
      provider: 'brave',
      httpStatus: 429,
      retryAfter,
    });
  }
  if (status === 403 || status === 401) {
    throw new SearchProviderError(`HTTP ${status}: Authentication/Access Denied`, 'blocked', {
      provider: 'brave',
      httpStatus: status,
    });
  }
  if (!response.ok) {
    throw new SearchProviderError(`HTTP ${status}: ${response.statusText}`, 'provider_error', {
      provider: 'brave',
      httpStatus: status,
    });
  }

  const text = await readResponseTextBounded(response, limits.maxBytes);
  let data;
  try {
    data = JSON.parse(text);
  } catch (error) {
    throw new SearchProviderError(`Invalid JSON response: ${error.message}`, 'provider_error', {
      provider: 'brave',
    });
  }

  if (!data || !data.web || !Array.isArray(data.web.results)) {
    throw new SearchProviderError('Unexpected response format: missing web.results array', 'provider_error', {
      provider: 'brave',
    });
  }

  const nowIso = new Date().toISOString();
  return data.web.results
    .filter(r => isValidResultUrl(r.url))
    .slice(0, limit)
    .map(r => ({
      title: r.title || '',
      url: r.url || '',
      snippet: r.description || '',
      provider: 'brave',
      source_engine: 'brave',
      retrieved_at: nowIso,
    }));
}

export async function searchGoogleCSE(query, limit, overrides = requestOverrides) {
  const cseKey = process.env.GOOGLE_CSE_KEY;
  const cseId = process.env.GOOGLE_CSE_ID;

  if (!cseKey || !cseId) {
    throw new SearchProviderError('GOOGLE_CSE_KEY and GOOGLE_CSE_ID environment variables are required', 'provider_error', {
      provider: 'google-cse',
    });
  }

  const num = Math.min(limit, 10);
  const url = `https://www.googleapis.com/customsearch/v1?q=${encodeURIComponent(query)}&key=${encodeURIComponent(cseKey)}&cx=${encodeURIComponent(cseId)}&num=${num}`;
  const limits = activeLimits(overrides);
  let response;
  try {
    response = await fetchWithManualRedirects(url, {
      headers: { 'User-Agent': USER_AGENT }
    }, limits.timeoutMs);
  } catch (err) {
    if (err instanceof ResourceLimitError) throw err;
    throw new SearchProviderError(`Google CSE network error: ${err.message}`, 'provider_error', {
      provider: 'google-cse',
    });
  }

  const status = response.status;
  if (status === 429) {
    const retryAfter = response.headers?.get?.('retry-after') || null;
    throw new SearchProviderError(`HTTP 429: Too Many Requests${retryAfter ? ` (Retry-After: ${retryAfter})` : ''}`, 'blocked', {
      provider: 'google-cse',
      httpStatus: 429,
      retryAfter,
    });
  }
  if (status === 403 || status === 401) {
    throw new SearchProviderError(`HTTP ${status}: Authentication/Access Denied`, 'blocked', {
      provider: 'google-cse',
      httpStatus: status,
    });
  }
  if (!response.ok) {
    throw new SearchProviderError(`HTTP ${status}: ${response.statusText}`, 'provider_error', {
      provider: 'google-cse',
      httpStatus: status,
    });
  }

  const text = await readResponseTextBounded(response, limits.maxBytes);
  let data;
  try {
    data = JSON.parse(text);
  } catch (error) {
    throw new SearchProviderError(`Invalid JSON response: ${error.message}`, 'provider_error', {
      provider: 'google-cse',
    });
  }

  if (!data || !Array.isArray(data.items)) {
    if (data && data.searchInformation && data.searchInformation.totalResults === '0') {
      return [];
    }
    throw new SearchProviderError('Unexpected response format: missing items array', 'provider_error', {
      provider: 'google-cse',
    });
  }

  const nowIso = new Date().toISOString();
  return data.items
    .filter(r => isValidResultUrl(r.link))
    .slice(0, limit)
    .map(r => ({
      title: r.title || '',
      url: r.link || '',
      snippet: r.snippet || '',
      provider: 'google-cse',
      source_engine: 'google-cse',
      retrieved_at: nowIso,
    }));
}

export class SearchGateway {
  constructor(options = {}) {
    this.overrides = options.overrides || {};
  }

  async execute({ query, limit = 10, engine = null, gateway = null, hostResultsPath = null, format = 'legacy' }) {
    if (!query && !hostResultsPath) {
      throw new Error('--query or --host-results is required');
    }

    if (gateway) {
      const gw = String(gateway).toLowerCase().trim();
      if (!['auto', 'host', 'mcp', 'direct'].includes(gw)) {
        throw new Error(`Invalid gateway mode: ${gw}. Must be one of auto, host, mcp, direct.`);
      }
      if (gw === 'host' || gw === 'mcp') {
        if (engine && engine !== 'host') {
          throw new Error(`Conflicting options: --engine ${engine} cannot be combined with gateway mode "${gw}".`);
        }
        engine = 'host';
      } else if (gw === 'direct') {
        if (engine === 'host') {
          throw new Error(`Conflicting options: --engine host cannot be combined with gateway mode "direct".`);
        }
      }
    }

    const attempts = [];
    const blockers = [];
    let finalResults = null;
    let finalStatus = 'error';

    // 1. Direct Engine Mode if specified
    if (engine) {
      const startTime = Date.now();
      try {
        let items = [];
        switch (engine) {
          case 'duckduckgo':
            items = await searchDuckDuckGo(query, limit, this.overrides);
            break;
          case 'searxng':
            items = await searchSearXNG(query, limit, this.overrides);
            break;
          case 'brave':
            items = await searchBrave(query, limit, this.overrides);
            break;
          case 'google-cse':
            items = await searchGoogleCSE(query, limit, this.overrides);
            break;
          case 'host': {
            if (!hostResultsPath) throw new SearchProviderError('--host-results path required for host engine', 'provider_error', { provider: 'host' });
            const hostArtifact = loadHostResultsArtifact(hostResultsPath, query, this.overrides.maxResponseBytes);
            if (hostArtifact.status === 'blocked') {
              throw new SearchProviderError(hostArtifact.message || 'Host results blocked', 'blocked', {
                provider: 'host',
                blocker: hostArtifact.blocker,
              });
            }
            items = hostArtifact.results.slice(0, limit);
            break;
          }
          default:
            throw new Error(`Unknown engine "${engine}". Valid: duckduckgo, searxng, brave, google-cse, host`);
        }
        finalResults = items;
        finalStatus = items.length > 0 ? 'success' : 'no_results';
        attempts.push({
          provider: engine,
          status: finalStatus,
          duration_ms: Date.now() - startTime,
          result_count: items.length,
        });
      } catch (err) {
        if (err instanceof ResourceLimitError) throw err;
        const statusKind = err instanceof SearchProviderError ? err.statusKind : 'provider_error';
        attempts.push({
          provider: engine,
          status: statusKind,
          duration_ms: Date.now() - startTime,
          result_count: 0,
          error: redactSecrets(err.message),
        });
        if (err instanceof SearchProviderError && err.retryAfter) {
          blockers.push({ code: 'rate_limited', message: redactSecrets(err.message), retry_after: err.retryAfter });
        } else {
          blockers.push({ code: statusKind, message: redactSecrets(err.message) });
        }
        finalStatus = statusKind;
      }
    } else {
      // 2. Multi-tier Provider Chain
      // Order: Host results -> Brave -> Google CSE -> Configured SearXNG -> DuckDuckGo -> Default SearXNG
      const chain = [];
      if (gateway !== 'direct' && (hostResultsPath || process.env.D_RESEARCH_HOST_SEARCH_FILE)) {
        chain.push({
          name: 'host',
          run: () => {
            const hostArtifact = loadHostResultsArtifact(hostResultsPath || process.env.D_RESEARCH_HOST_SEARCH_FILE, query, this.overrides.maxResponseBytes);
            if (hostArtifact.status === 'blocked') {
              throw new SearchProviderError(hostArtifact.message || 'Host results blocked', 'blocked', {
                provider: 'host',
                blocker: hostArtifact.blocker,
              });
            }
            return hostArtifact.results.slice(0, limit);
          }
        });
      }
      if (process.env.BRAVE_API_KEY) {
        chain.push({ name: 'brave', run: () => searchBrave(query, limit, this.overrides) });
      }
      if (process.env.GOOGLE_CSE_KEY && process.env.GOOGLE_CSE_ID) {
        chain.push({ name: 'google-cse', run: () => searchGoogleCSE(query, limit, this.overrides) });
      }
      if (process.env.SEARXNG_INSTANCE) {
        chain.push({ name: 'searxng', run: () => searchSearXNG(query, limit, this.overrides) });
      }
      chain.push({ name: 'duckduckgo', run: () => searchDuckDuckGo(query, limit, this.overrides) });
      if (!process.env.SEARXNG_INSTANCE) {
        chain.push({ name: 'searxng', run: () => searchSearXNG(query, limit, this.overrides) });
      }

      for (const provider of chain) {
        let attemptSucceeded = false;
        // At most 1 retry for transport or 5xx error
        for (let retry = 0; retry <= 1; retry++) {
          const startTime = Date.now();
          try {
            const items = await provider.run();
            finalResults = items;
            finalStatus = items.length > 0 ? 'success' : 'no_results';
            attempts.push({
              provider: provider.name,
              status: finalStatus,
              duration_ms: Date.now() - startTime,
              result_count: items.length,
            });
            attemptSucceeded = true;
            break;
          } catch (err) {
            if (err instanceof ResourceLimitError) throw err;
            const statusKind = err instanceof SearchProviderError ? err.statusKind : 'provider_error';
            const durationMs = Date.now() - startTime;
            const redactedErr = redactSecrets(err.message);
            console.error(`[${provider.name}] ${redactedErr}`);
            attempts.push({
              provider: provider.name,
              status: statusKind,
              duration_ms: durationMs,
              result_count: 0,
              error: redactedErr,
            });
            if (err instanceof SearchProviderError && err.retryAfter) {
              blockers.push({ code: 'rate_limited', message: redactedErr, retry_after: err.retryAfter });
            } else {
              blockers.push({ code: statusKind, message: redactedErr });
            }

            if (statusKind === 'blocked' || (err instanceof SearchProviderError && (err.httpStatus === 202 || err.httpStatus === 403 || err.httpStatus === 429))) {
              break;
            }
            if (retry === 0) continue;
          }
        }
        if (attemptSucceeded) {
          break;
        }
      }
    }

    const envelope = {
      schema_version: '1.0.0',
      query: query || '',
      status: finalResults !== null ? finalStatus : 'error',
      results: finalResults || [],
      attempts,
      blockers,
    };

    return {
      envelope,
      legacy: (finalResults || []).map(r => ({
        title: r.title,
        url: r.url,
        snippet: r.snippet,
        source_engine: r.source_engine || r.provider,
      })),
      exitCode: (finalResults !== null && finalStatus !== 'blocked' && finalStatus !== 'error') ? 0 : (finalStatus === 'blocked' ? 2 : 1),
    };
  }
}

export async function runFallbackChain(query, limit) {
  const gateway = new SearchGateway({ overrides: requestOverrides });
  const result = await gateway.execute({ query, limit, format: 'legacy' });
  if (result.exitCode !== 0) {
    console.error('Error: All search engines failed:');
    for (const a of result.envelope.attempts) {
      if (a.error) console.error(`  [${a.provider}] ${a.error}`);
    }
    process.exit(1);
  }
  return result.legacy;
}

// ─── CLI Parser ──────────────────────────────────────────────────────────────

function parseArgs(argv) {
  const args = {
    engine: null,
    query: null,
    limit: 10,
    out: null,
    format: 'legacy',
    hostResults: null,
    searchGateway: null,
    maxResponseBytes: null,
    timeoutMs: null,
    selfTest: false,
  };

  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--engine' && i + 1 < argv.length) {
      const eng = argv[++i].toLowerCase().trim();
      if (!['duckduckgo', 'searxng', 'brave', 'google-cse', 'host'].includes(eng)) {
        throw new Error(`Invalid --engine: ${eng}. Must be one of duckduckgo, searxng, brave, google-cse, host.`);
      }
      args.engine = eng;
    } else if ((arg === '--search-gateway' || arg === '--gateway') && i + 1 < argv.length) {
      const val = argv[++i];
      const gw = String(val).toLowerCase().trim();
      if (!['auto', 'host', 'mcp', 'direct'].includes(gw)) {
        throw new Error(`Invalid --search-gateway: ${val}. Must be one of auto, host, mcp, direct.`);
      }
      args.searchGateway = gw;
    } else if (arg === '--query' && i + 1 < argv.length) {
      args.query = argv[++i];
    } else if (arg === '--limit' && i + 1 < argv.length) {
      args.limit = parsePositiveInteger(argv[++i], '--limit');
    } else if (arg === '--out' && i + 1 < argv.length) {
      args.out = argv[++i];
    } else if (arg === '--format' && i + 1 < argv.length) {
      const fmt = argv[++i];
      if (!['legacy', 'envelope'].includes(fmt)) {
        throw new Error(`Invalid --format: ${fmt}. Must be 'legacy' or 'envelope'.`);
      }
      args.format = fmt;
    } else if (arg === '--host-results' && i + 1 < argv.length) {
      args.hostResults = argv[++i];
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

// ─── Self-Test ───────────────────────────────────────────────────────────────

/** Explicit offline fixture seam; URL, DNS and peer checks still run in the guard. */
export function setSearchTestResponse(provider) {
  if (typeof provider !== 'function') {
    setTestDnsResolver(null);
    setTestConnectFactory(null);
    return;
  }
  setTestDnsResolver(async () => ['8.8.8.8']);
  setTestConnectFactory((options, onResponse) => {
    const request = new EventEmitter();
    const chunks = [];
    let destroyed = false;
    request.write = (chunk) => { chunks.push(Buffer.from(chunk)); return true; };
    request.destroy = (error) => {
      if (!destroyed && error) queueMicrotask(() => request.emit('error', error));
      destroyed = true;
      return request;
    };
    request.end = () => {
      queueMicrotask(async () => {
        if (destroyed) return;
        const socket = new EventEmitter();
        socket.remoteAddress = options.ip;
        socket.connecting = false;
        socket.destroy = () => { destroyed = true; };
        request.emit('socket', socket);
        if (destroyed) return;
        try {
          const response = await provider(options.url, {
            method: options.method, headers: options.headers, redirect: 'manual',
            body: chunks.length ? Buffer.concat(chunks).toString() : undefined,
          });
          const body = typeof response.text === 'function' ? await response.text() : '';
          if (destroyed) return;
          const stream = Readable.from([Buffer.from(body)]);
          stream.statusCode = response.status;
          stream.statusMessage = response.statusText || '';
          stream.headers = {};
          for (const name of ['location', 'content-type', 'content-length', 'retry-after']) {
            const value = response.headers?.get?.(name);
            if (value != null) stream.headers[name] = value;
          }
          onResponse(stream);
        } catch (error) { request.emit('error', error); }
      });
      return request;
    };
    return request;
  });
}

export async function runSelfTest() {
  let passed = 0;
  let failed = 0;
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

  process.env.BRAVE_API_KEY = 'brave-redirect-secret';
  let redirectCalls = [];
  setSearchTestResponse(async (url, options) => {
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
  });
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
  setSearchTestResponse(async (url, options) => {
    redirectCalls.push({ url: String(url), headers: { ...(options.headers || {}) } });
    return {
      ok: false,
      status: 302,
      headers: { get: (name) => name.toLowerCase() === 'location' ? 'https://redirect.invalid/stolen' : null },
      body: { cancel: async () => {} },
    };
  });
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
  setSearchTestResponse(async () => {
    loopCalls++;
    return {
      ok: false,
      status: 302,
      headers: { get: (name) => name.toLowerCase() === 'location' ? '/loop' : null },
      body: { cancel: async () => {} },
    };
  });
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

  const mockSearxJson = {
    results: [
      { title: 'SearX Result 1', url: 'https://example.com/1', content: 'First result snippet' },
      { title: 'SearX Result 2', url: 'https://example.com/2', content: 'Second result snippet' }
    ]
  };

  const mockBraveJson = {
    web: {
      results: [
        { title: 'Brave Result 1', url: 'https://brave.com/1', description: 'Brave snippet 1' },
        { title: 'Brave Result 2', url: 'https://brave.com/2', description: 'Brave snippet 2' }
      ]
    }
  };

  const mockGcseJson = {
    items: [
      { title: 'Google Result 1', link: 'https://google.com/1', snippet: 'Google snippet 1' },
      { title: 'Google Result 2', link: 'https://google.com/2', snippet: 'Google snippet 2' }
    ]
  };

  setSearchTestResponse(async (url) => {
    const urlStr = typeof url === 'string' ? url : url.toString();
    if (urlStr.includes('html.duckduckgo.com')) {
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        text: async () => mockDdgHtml,
        headers: { get: () => null },
        json: async () => { throw new Error('Not JSON'); }
      };
    }
    if (urlStr.includes('/search?') && urlStr.includes('format=json')) {
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        text: async () => JSON.stringify(mockSearxJson),
        headers: { get: () => null },
        json: async () => mockSearxJson
      };
    }
    if (urlStr.includes('api.search.brave.com')) {
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        text: async () => JSON.stringify(mockBraveJson),
        headers: { get: () => null },
        json: async () => mockBraveJson
      };
    }
    if (urlStr.includes('googleapis.com/customsearch')) {
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        text: async () => JSON.stringify(mockGcseJson),
        headers: { get: () => null },
        json: async () => mockGcseJson
      };
    }
    return {
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      headers: { get: () => null },
      text: async () => 'error',
      json: async () => ({ error: 'unknown' })
    };
  });

  // Test 1: DDG parser
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

  // Test 2: SearXNG parser
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

  // Test 3: Brave parser
  console.log('  Test 3: Brave engine');
  try {
    process.env.BRAVE_API_KEY = 'test-key-123';
    const results = await searchBrave('test', 10);
    assert(Array.isArray(results), 'results is array');
    assert(results.length === 2, `got 2 results (got ${results.length})`);
    assert(results[0].source_engine === 'brave', 'source_engine is brave');
    assert(results[0].title === 'Brave Result 1', 'title matches');
    assert(results[0].url === 'https://brave.com/1', 'url matches');
  } catch (err) {
    failed++;
    console.error(`  FAIL: Brave test threw: ${err.message}`);
  }

  // Test 4: Google CSE parser
  console.log('  Test 4: Google CSE engine');
  try {
    process.env.GOOGLE_CSE_KEY = 'test-cse-key';
    process.env.GOOGLE_CSE_ID = 'test-cse-id';
    const results = await searchGoogleCSE('test', 10);
    assert(Array.isArray(results), 'results is array');
    assert(results.length === 2, `got 2 results (got ${results.length})`);
    assert(results[0].source_engine === 'google-cse', 'source_engine is google-cse');
  } catch (err) {
    failed++;
    console.error(`  FAIL: Google CSE test threw: ${err.message}`);
  }

  // Test 5: Fallback chain (DDG fail -> SearXNG success)
  console.log('  Test 5: Fallback chain (DDG fail -> SearXNG success)');
  setSearchTestResponse(async (url) => {
    const urlStr = typeof url === 'string' ? url : url.toString();
    if (urlStr.includes('html.duckduckgo.com')) {
      return { ok: false, status: 503, statusText: 'Service Unavailable', headers: { get: () => null } };
    }
    if (urlStr.includes('/search?') && urlStr.includes('format=json')) {
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        text: async () => JSON.stringify(mockSearxJson),
        headers: { get: () => null },
        json: async () => mockSearxJson
      };
    }
    return { ok: false, status: 500, statusText: 'Internal Server Error', headers: { get: () => null } };
  });

  try {
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

  // Test 6: All engines fail
  console.log('  Test 6: All engines fail (exit non-zero)');
  setSearchTestResponse(async () => {
    return { ok: false, status: 500, statusText: 'Internal Server Error', headers: { get: () => null } };
  });

  let exitCode = null;
  const originalExit = process.exit;
  process.exit = (code) => { exitCode = code; };
  try {
    delete process.env.BRAVE_API_KEY;
    delete process.env.GOOGLE_CSE_KEY;
    delete process.env.GOOGLE_CSE_ID;
    delete process.env.SEARXNG_INSTANCE;
    await runFallbackChain('test', 10);
  } catch {
    /* expected */
  }
  assert(exitCode === 1, `all-fail exits with code 1 (got ${exitCode})`);
  process.exit = originalExit;

  // ─── Regression Tests (P1.A10 & P2 Gateway) ────────────────────────────────

  // Regression 7: DDG HTTP 202 challenge triggers fallback
  console.log('  Test 7: DDG HTTP 202 challenge triggers fallback');
  let calls = [];
  setSearchTestResponse(async (url) => {
    const s = String(url);
    calls.push(s);
    if (s.includes('duckduckgo.com')) {
      return {
        ok: true,
        status: 202,
        statusText: 'Accepted',
        headers: { get: () => null },
        text: async () => '<html><body>Verify you are human</body></html>',
      };
    }
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      headers: { get: () => null },
      text: async () => JSON.stringify(mockSearxJson),
      json: async () => mockSearxJson,
    };
  });
  try {
    const gw = new SearchGateway();
    const res = await gw.execute({ query: 'challenge 202 test', limit: 5 });
    assert(res.exitCode === 0, 'challenge 202 fallback succeeds with exitCode 0');
    assert(calls.length >= 2, 'calls next provider in chain');
    assert(res.legacy.length === 2, 'gets results from fallback provider');
  } catch (err) {
    failed++;
    console.error(`  FAIL: Test 7 threw: ${err.message}`);
  }

  // Regression 8: DDG HTTP 200 with challenge body triggers fallback
  console.log('  Test 8: DDG HTTP 200 body challenge triggers fallback');
  calls = [];
  setSearchTestResponse(async (url) => {
    const s = String(url);
    calls.push(s);
    if (s.includes('duckduckgo.com')) {
      return {
        ok: true,
        status: 200,
        statusText: 'OK',
        headers: { get: () => null },
        text: async () => '<html><title>bot detection</title><body>Please complete the captcha</body></html>',
      };
    }
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      headers: { get: () => null },
      text: async () => JSON.stringify(mockSearxJson),
      json: async () => mockSearxJson,
    };
  });
  try {
    const gw = new SearchGateway();
    const res = await gw.execute({ query: 'challenge 200 test', limit: 5 });
    assert(res.exitCode === 0, 'challenge 200 body triggers fallback');
    assert(calls.length >= 2, 'calls next provider in chain');
  } catch (err) {
    failed++;
    console.error(`  FAIL: Test 8 threw: ${err.message}`);
  }

  // Regression 9: HTTP 429 records Retry-After and does not loop
  console.log('  Test 9: HTTP 429 rate limit recorded');
  calls = [];
  setSearchTestResponse(async (url) => {
    const s = String(url);
    calls.push(s);
    if (s.includes('duckduckgo.com')) {
      return {
        ok: false,
        status: 429,
        statusText: 'Too Many Requests',
        headers: { get: (k) => k.toLowerCase() === 'retry-after' ? '30' : null },
        text: async () => 'rate limited',
      };
    }
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      headers: { get: () => null },
      text: async () => JSON.stringify(mockSearxJson),
      json: async () => mockSearxJson,
    };
  });
  try {
    const gw = new SearchGateway();
    const res = await gw.execute({ query: 'rate limit test', limit: 5 });
    assert(res.exitCode === 0, 'rate limited provider bypassed to fallback');
    const ddgAttempt = res.envelope.attempts.find(a => a.provider === 'duckduckgo');
    assert(ddgAttempt && ddgAttempt.status === 'blocked', 'ddg attempt marked blocked');
    const rlBlocker = res.envelope.blockers.find(b => b.code === 'rate_limited');
    assert(rlBlocker && rlBlocker.retry_after === '30', 'retry_after recorded in blocker');
  } catch (err) {
    failed++;
    console.error(`  FAIL: Test 9 threw: ${err.message}`);
  }

  // Regression 10: Envelope output format
  console.log('  Test 10: Envelope output format');
  try {
    const gw = new SearchGateway();
    const res = await gw.execute({ query: 'envelope test', limit: 5, format: 'envelope' });
    assert(res.envelope.schema_version === '1.0.0', 'envelope schema_version is 1.0.0');
    assert(Array.isArray(res.envelope.results), 'envelope results is array');
    assert(Array.isArray(res.envelope.attempts), 'envelope attempts is array');
  } catch (err) {
    failed++;
    console.error(`  FAIL: Test 10 threw: ${err.message}`);
  }

  // Regression 11: Gateway arg parsing and conflict rejection
  console.log('  Test 11: Gateway arg parsing and conflict rejection');
  try {
    const parsedValid = parseArgs(['node', 'web_search.mjs', '--query', 'test', '--search-gateway', 'direct']);
    assert(parsedValid.searchGateway === 'direct', 'parseArgs accepts --search-gateway direct');

    let threwInvalidGateway = false;
    try {
      parseArgs(['node', 'web_search.mjs', '--query', 'test', '--gateway', 'bogus']);
    } catch {
      threwInvalidGateway = true;
    }
    assert(threwInvalidGateway, 'parseArgs rejects invalid --gateway bogus');

    let threwInvalidEngine = false;
    try {
      parseArgs(['node', 'web_search.mjs', '--query', 'test', '--engine', 'bogus']);
    } catch {
      threwInvalidEngine = true;
    }
    assert(threwInvalidEngine, 'parseArgs rejects invalid --engine bogus');

    let threwConflict = false;
    try {
      const gw = new SearchGateway();
      await gw.execute({ query: 'test', engine: 'duckduckgo', gateway: 'host' });
    } catch {
      threwConflict = true;
    }
    assert(threwConflict, 'SearchGateway.execute rejects conflicting engine and gateway');
  } catch (err) {
    failed++;
    console.error(`  FAIL: Test 11 threw: ${err.message}`);
  }

  } finally {
    // Explicit test transport hooks and environment never survive this runner.
    setSearchTestResponse(null);
    for (const key of Object.keys(process.env)) {
      if (!(key in originalEnv)) delete process.env[key];
    }
    Object.assign(process.env, originalEnv);
  }

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
    timeoutMs: args.timeoutMs,
  };

  if (args.selfTest) {
    await runSelfTest();
    return;
  }

  if (!args.query && !args.hostResults) {
    console.error('Error: --query or --host-results is required');
    console.error('Usage: web_search.mjs --query "<q>" [--engine duckduckgo|searxng|brave|google-cse|host] [--limit N] [--format legacy|envelope] [--host-results <path>] [--out <file>]');
    console.error('       web_search.mjs --self-test');
    process.exit(1);
  }

  const gateway = new SearchGateway({ overrides: requestOverrides });
  const result = await gateway.execute({
    query: args.query,
    limit: args.limit,
    engine: args.engine,
    gateway: args.searchGateway,
    hostResultsPath: args.hostResults,
    format: args.format,
  });

  const outputData = args.format === 'envelope' ? result.envelope : result.legacy;
  const output = JSON.stringify(outputData, null, 2);

  if (args.out) {
    fs.writeFileSync(args.out, output);
    console.error(`Results written to: ${args.out}`);
  } else {
    console.log(output);
  }

  if (result.exitCode !== 0) {
    process.exit(result.exitCode);
  }
}

// Ensure execution when invoked directly
const _isDirectCli = process.argv[1] && (
  process.argv[1].endsWith('web_search.mjs') ||
  process.argv[1].endsWith('web_search')
);

if (_isDirectCli) {
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
}
