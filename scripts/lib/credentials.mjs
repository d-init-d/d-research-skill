/**
 * Shared credential classification for D Research network helpers.
 * Used by api_fetch.mjs and http_cache.mjs.
 *
 * Policy (v3.2):
 * - All user-supplied custom headers are sensitive by default.
 * - Only an explicit allowlist of public request-shaping headers may cross origin.
 * - Query/userinfo secrets count as credentials.
 * - Redact secrets before any log/exception/sidecar/cache metadata.
 */

export const PUBLIC_HEADER_ALLOWLIST = new Set([
  'accept',
  'accept-language',
  'accept-encoding',
  'content-type',
  'user-agent',
  'cache-control',
  'pragma',
  'if-none-match',
  'if-modified-since',
]);

const EXPLICIT_SECRET_HEADERS = new Set([
  'authorization',
  'proxy-authorization',
  'cookie',
  'set-cookie',
  'x-api-key',
  'api-key',
  'x-auth-token',
  'x-access-token',
  'x-token',
]);

const SECRET_NAME_RE = /(token|secret|credential|authorization|api-?key|password|passwd|auth)/i;

export const SECRET_QUERY_KEYS = new Set([
  'api_key',
  'apikey',
  'access_token',
  'token',
  'key',
  'auth',
  'password',
  'secret',
  'credential',
  'client_secret',
  'refresh_token',
]);

export function normalizeHeaderName(name) {
  return String(name || '').trim().toLowerCase();
}

export function isSensitiveHeaderName(name) {
  const n = normalizeHeaderName(name);
  if (!n) return false;
  if (PUBLIC_HEADER_ALLOWLIST.has(n)) return false;
  if (EXPLICIT_SECRET_HEADERS.has(n)) return true;
  if (SECRET_NAME_RE.test(n)) return true;
  // Custom headers not on the public allowlist are sensitive by default.
  return true;
}

export function isPublicHeaderName(name) {
  return PUBLIC_HEADER_ALLOWLIST.has(normalizeHeaderName(name));
}

export function isSecretQueryKey(key) {
  return SECRET_QUERY_KEYS.has(String(key || '').toLowerCase());
}

export function headersHaveCredentials(headers) {
  if (!headers || typeof headers !== 'object') return false;
  const keys =
    typeof headers.forEach === 'function' && typeof headers.get === 'function'
      ? (() => {
          const out = [];
          headers.forEach((_v, k) => out.push(k));
          return out;
        })()
      : Object.keys(headers);
  return keys.some((k) => isSensitiveHeaderName(k));
}

export function urlHasCredentials(url) {
  const s = String(url || '');
  try {
    const u = new URL(s);
    if (u.username || u.password) return true;
    for (const key of u.searchParams.keys()) {
      if (isSecretQueryKey(key)) return true;
    }
    return false;
  } catch {
    // Parse failed — still scan raw string for secret query patterns.
    return /(?:^|[?&#])(?:api_key|apikey|access_token|token|key|auth|password|secret|credential)=/i.test(
      s
    );
  }
}

export function isCredentialedRequest(url, headers) {
  return headersHaveCredentials(headers) || urlHasCredentials(url);
}

export function publicHeadersOnly(headers) {
  const out = {};
  if (!headers) return out;
  const entries =
    typeof headers.forEach === 'function' && typeof headers.get === 'function'
      ? (() => {
          const arr = [];
          headers.forEach((v, k) => arr.push([k, v]));
          return arr;
        })()
      : Object.entries(headers);
  for (const [k, v] of entries) {
    if (isPublicHeaderName(k)) out[k] = v;
  }
  return out;
}

export function stripSensitiveHeaders(headers) {
  return publicHeadersOnly(headers);
}

/**
 * Redact secret query values and userinfo from a URL-like string.
 * Works even when `new URL()` fails.
 */
export function redactUrl(url) {
  let s = String(url ?? '');
  // userinfo
  s = s.replace(/:\/\/([^/@\s]+):([^@/\s]+)@/g, '://[REDACTED]:[REDACTED]@');
  s = s.replace(/:\/\/([^/@\s]+)@/g, '://[REDACTED]@');
  // query secrets (raw) — also match bare key=value in free text
  for (const key of SECRET_QUERY_KEYS) {
    const re = new RegExp(`([?&#]?(?:${key})=)([^&#\\s]*)`, 'gi');
    s = s.replace(re, '$1[REDACTED]');
  }
  try {
    const u = new URL(String(url ?? ''));
    if (u.username) u.username = 'REDACTED';
    if (u.password) u.password = 'REDACTED';
    for (const key of [...u.searchParams.keys()]) {
      if (isSecretQueryKey(key)) u.searchParams.set(key, '[REDACTED]');
    }
    return u.toString();
  } catch {
    return s;
  }
}

export function redactSecretsInText(text) {
  let s = String(text ?? '');
  s = redactUrl(s);
  // header-like secrets in free text
  s = s.replace(
    /((?:authorization|proxy-authorization|cookie|x-api-key|api-key|x-auth-token|x-access-token|x-token)\s*[:=]\s*)([^\s,;]+)/gi,
    '$1[REDACTED]'
  );
  s = s.replace(/\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+/gi, '$1 [REDACTED]');
  return s;
}
