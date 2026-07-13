// Public-address validation + connection-bound fetch for Node helpers.
// Stdlib-only. Mirrors the threat model of scripts/_ssrf_helpers.py:
// - HTTPS only by default
// - no userinfo
// - blocked hostnames (localhost, cloud metadata names)
// - non-public IPv4/IPv6 literals rejected
// - DNS resolutions must not include non-public addresses
// - call again on every redirect hop
// - fetchPublicHttp binds the TCP connection to a validated public IP (F-05)
//
// IPv6 public-destination policy (deterministic; not version-drifting OS
// tables). Registry snapshot: IANA IPv6 Special-Purpose Address Registry,
// last updated 2025-10-09.
// 1) IPv4-mapped IPv6 (::ffff:0:0/96) → embedded IPv4 policy first.
// 2) Fail closed outside the current global-unicast envelope 2000::/3
//    (covers loopback, ULA, link-local, multicast, SRv6 5f00::/16, dummy
//    100:0:0:1::/64, deprecated site-local fec0::/10, IPv4-compatible
//    ::a.b.c.d, and unallocated space such as 4000::/3 and 8000::/1).
// 3) Translation prefixes remain blocked even when IANA marks a prefix
//    globally reachable (encoded private IPv4 is an SSRF risk):
//    64:ff9b::/96, 64:ff9b:1::/48, and 2002::/16 (6to4).
// 4) Within 2000::/3, block IANA non-global / special-use ranges:
//    2001::/23 (entire IETF Protocol Assignments parent — no more-specific
//    exceptions; CPython 3.10–3.12 disagree on 2001:1::/*, AMT, ORCHIDv2,
//    DETs, etc., so the fail-closed parent is the only cross-runtime stable
//    choice), 2001:db8::/32, 2002::/16, 3fff::/20.

import dns from 'node:dns/promises';
import { EventEmitter, getEventListeners } from 'node:events';
import http from 'node:http';
import https from 'node:https';
import net from 'node:net';
import { BlockList } from 'node:net';
import { pathToFileURL, URL } from 'node:url';

const BLOCKED_HOSTNAMES = new Set([
  'localhost',
  'localhost.localdomain',
  'metadata.google.internal',
  'metadata',
  'instance-data',
]);

// IPv4 special-use (explicit BlockList; independent of IPv6 tables).
const IPV4_PRIVATE_BLOCKS = new BlockList();
IPV4_PRIVATE_BLOCKS.addSubnet('0.0.0.0', 8, 'ipv4');
IPV4_PRIVATE_BLOCKS.addSubnet('10.0.0.0', 8, 'ipv4');
IPV4_PRIVATE_BLOCKS.addSubnet('100.64.0.0', 10, 'ipv4'); // CGNAT
IPV4_PRIVATE_BLOCKS.addSubnet('127.0.0.0', 8, 'ipv4');
IPV4_PRIVATE_BLOCKS.addSubnet('169.254.0.0', 16, 'ipv4');
IPV4_PRIVATE_BLOCKS.addSubnet('172.16.0.0', 12, 'ipv4');
IPV4_PRIVATE_BLOCKS.addSubnet('192.0.0.0', 24, 'ipv4');
IPV4_PRIVATE_BLOCKS.addSubnet('192.0.2.0', 24, 'ipv4'); // TEST-NET-1
IPV4_PRIVATE_BLOCKS.addSubnet('192.168.0.0', 16, 'ipv4');
IPV4_PRIVATE_BLOCKS.addSubnet('198.18.0.0', 15, 'ipv4');
IPV4_PRIVATE_BLOCKS.addSubnet('198.51.100.0', 24, 'ipv4'); // TEST-NET-2
IPV4_PRIVATE_BLOCKS.addSubnet('203.0.113.0', 24, 'ipv4'); // TEST-NET-3
IPV4_PRIVATE_BLOCKS.addSubnet('224.0.0.0', 4, 'ipv4'); // multicast
IPV4_PRIVATE_BLOCKS.addSubnet('240.0.0.0', 4, 'ipv4'); // reserved

// IPv6: only addresses inside 2000::/3 may be public destinations.
const IPV6_GLOBAL_UNICAST = new BlockList();
IPV6_GLOBAL_UNICAST.addSubnet('2000::', 3, 'ipv6');

// Blocked even when they fall outside/inside GUA; translation + special-use.
// 64:ff9b::/96 is IANA Globally Reachable=True but encodes arbitrary IPv4.
const IPV6_ALWAYS_BLOCK = new BlockList();
IPV6_ALWAYS_BLOCK.addSubnet('64:ff9b::', 96, 'ipv6'); // NAT64 well-known (RFC 6052)
IPV6_ALWAYS_BLOCK.addSubnet('64:ff9b:1::', 48, 'ipv6'); // local-use NAT64 (RFC 8215)

// Non-public / special-use ranges inside the 2000::/3 envelope.
const IPV6_GUA_BLOCK = new BlockList();
IPV6_GUA_BLOCK.addSubnet('2001::', 23, 'ipv6'); // IETF Protocol Assignments parent
IPV6_GUA_BLOCK.addSubnet('2001:db8::', 32, 'ipv6'); // documentation (RFC 3849)
IPV6_GUA_BLOCK.addSubnet('2002::', 16, 'ipv6'); // 6to4 (RFC 3056) — translation
IPV6_GUA_BLOCK.addSubnet('3fff::', 20, 'ipv6'); // documentation (RFC 9637)

/** Injectable DNS for rebinding tests. Signature: async (hostname) => string[] */
let _testResolve = null;
/** Injectable connect factory for peer-mismatch tests. */
let _testConnect = null;

export function setTestDnsResolver(fn) {
  _testResolve = typeof fn === 'function' ? fn : null;
}

export function setTestConnectFactory(fn) {
  _testConnect = typeof fn === 'function' ? fn : null;
}

export class HttpResourceLimitError extends Error {
  constructor(code, message, details = {}) {
    super(message);
    this.name = 'HttpResourceLimitError';
    this.code = code;
    this.details = details;
  }
}

/**
 * Expand an IPv6 literal into eight 16-bit hextet numbers, or null if invalid.
 * Accepts compressed forms and dotted-quad IPv4 tail (::ffff:192.0.2.1).
 */
function expandIpv6Hextets(ip) {
  let s = String(ip || '')
    .toLowerCase()
    .trim();
  if (s.startsWith('[') && s.endsWith(']')) s = s.slice(1, -1);
  if (s.includes('%')) s = s.split('%', 1)[0];
  if (!s || s.includes('.')) {
    // Dotted-quad tail: convert last group a.b.c.d into two hextets.
    const dq = /^(.*:)(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(s);
    if (!dq) return null;
    const octets = dq.slice(2, 6);
    // Match net.isIP()/WHATWG canonical decimal semantics. Leading-zero
    // octets are ambiguous and invalid here; the fallback parser must not
    // turn a rejected literal into a public mapped address.
    if (octets.some((part) => part.length > 1 && part.startsWith('0'))) return null;
    const [a, b, c, d] = octets.map(Number);
    if ([a, b, c, d].some((n) => !Number.isInteger(n) || n < 0 || n > 255)) return null;
    s = `${dq[1]}${((a << 8) | b).toString(16)}:${((c << 8) | d).toString(16)}`;
  }
  if (!s.includes(':')) return null;
  const sides = s.split('::');
  if (sides.length > 2) return null;
  const parseSide = (side) =>
    side === ''
      ? []
      : side.split(':').map((h) => {
          if (!/^[0-9a-f]{1,4}$/.test(h)) return NaN;
          return parseInt(h, 16);
        });
  let head;
  let tail;
  if (sides.length === 1) {
    head = parseSide(sides[0]);
    tail = [];
    if (head.length !== 8 || head.some((n) => Number.isNaN(n))) return null;
  } else {
    // "::" compression is present: it must replace at least one 16-bit group.
    // missing === 0 would accept forms like 1:2:3:4:5:6:7:8:: (zero groups).
    head = parseSide(sides[0]);
    tail = parseSide(sides[1]);
    if (head.some((n) => Number.isNaN(n)) || tail.some((n) => Number.isNaN(n))) return null;
    const missing = 8 - head.length - tail.length;
    if (missing < 1) return null;
    head = head.concat(Array(missing).fill(0), tail);
  }
  return head;
}

/** Return embedded IPv4 string for ::ffff:0:0/96, else null. */
function ipv4MappedEmbedded(ip) {
  const hextets = expandIpv6Hextets(ip);
  if (!hextets) return null;
  // ::ffff:0:0/96 → first 80 bits zero, next 16 bits 0xffff
  for (let i = 0; i < 5; i += 1) {
    if (hextets[i] !== 0) return null;
  }
  if (hextets[5] !== 0xffff) return null;
  const hi = hextets[6];
  const lo = hextets[7];
  return `${(hi >> 8) & 255}.${hi & 255}.${(lo >> 8) & 255}.${lo & 255}`;
}

function unwrapIpv4Mapped(ip) {
  return ipv4MappedEmbedded(ip) || ip;
}

/**
 * Canonical IP string for peer/validated membership.
 * IPv4-mapped IPv6 unwraps to the embedded IPv4; other IPv6 uses expanded
 * lowercase hextets so compressed/expanded forms compare equal. Returns null
 * on malformed input (callers must fail closed).
 */
export function canonicalizeIpForComparison(value) {
  if (typeof value !== 'string' || !value) return null;
  const raw = value;
  // Peer and resolver values are internal socket/DNS outputs, not URL
  // authorities. Never repair whitespace, brackets, or scope identifiers:
  // doing so could turn malformed input into a member of the validated set.
  // Public peers never require a zone identifier; scoped IPv6 is non-public.
  if (raw !== raw.trim() || raw.includes('%') || raw.includes('[') || raw.includes(']')) {
    return null;
  }
  if (net.isIP(raw) === 0) return null;

  if (net.isIPv4(raw)) return raw;

  const embedded = ipv4MappedEmbedded(raw);
  if (embedded) return embedded;

  const hextets = expandIpv6Hextets(raw);
  if (!hextets) return null;
  return hextets.map((h) => h.toString(16)).join(':');
}

/**
 * Whether the connected peer belongs to the DNS-validated public set after
 * canonicalization (including IPv4 ↔ IPv4-mapped equivalence).
 */
export function peerMatchesValidatedIps(peer, validatedIps) {
  const normalizedPeer = canonicalizeIpForComparison(peer);
  if (normalizedPeer == null) return false;
  if (!Array.isArray(validatedIps) || !validatedIps.length) return false;
  const normalizedValidated = new Set();
  for (const value of validatedIps) {
    const canon = canonicalizeIpForComparison(value);
    if (canon == null) return false; // fail closed on any malformed validated entry
    normalizedValidated.add(canon);
  }
  return normalizedValidated.has(normalizedPeer);
}

/**
 * Production peer check after TCP connect. Pure relative to network I/O:
 * throws on missing/malformed/non-public/unvalidated peers; no-op for loopback
 * fixtures. fetchPublicHttp socket hooks call exactly this function.
 *
 * @param {string|null|undefined} peerAddress
 * @param {string[]|null|undefined} publicIps
 * @param {{loopback?: boolean}} [opts]
 */
export function assertConnectedPeer(peerAddress, publicIps, opts = {}) {
  if (peerAddress == null || peerAddress === '') {
    throw new Error('peer address unavailable');
  }
  if (opts.loopback) return;

  const peerRaw = peerAddress;
  const peerCanon = canonicalizeIpForComparison(peerRaw);
  if (peerCanon == null) {
    throw new Error(`peer address is malformed: ${peerRaw}`);
  }
  // Classify with both raw and canonical forms so mapped private IPv4 is caught.
  if (isNonPublicIp(peerRaw) || isNonPublicIp(peerCanon)) {
    throw new Error(`peer address is non-public: ${peerRaw}`);
  }
  if (!Array.isArray(publicIps) || !publicIps.length) {
    throw new Error(`peer address mismatch: ${peerRaw} not in validated set`);
  }
  if (!peerMatchesValidatedIps(peerRaw, publicIps)) {
    throw new Error(`peer address mismatch: ${peerRaw} not in validated set`);
  }
}

/**
 * TLS SNI hostname for a WHATWG URL hostname.
 * IP literals (IPv4 or bracketed IPv6) must omit SNI on Node 18/20/22;
 * certificate verification stays bound to the connect host (unbracketed IP).
 * DNS names keep the original hostname as SNI.
 * @returns {string|undefined}
 */
function tlsServernameFor(hostname) {
  if (!hostname) return undefined;
  const bare = normalizeHostname(hostname);
  if (!bare) return undefined;
  if (net.isIP(bare)) return undefined;
  // Fallback: some dotted-quad mapped forms may not pass net.isIP.
  if (expandIpv6Hextets(bare)) return undefined;
  return bare;
}

function isNonPublicIpv4(ip) {
  try {
    return IPV4_PRIVATE_BLOCKS.check(ip, 'ipv4');
  } catch {
    return true;
  }
}

function isNonPublicIpv6(ip) {
  // 1) IPv4-mapped → embedded IPv4 policy first.
  const embedded = ipv4MappedEmbedded(ip);
  if (embedded) return isNonPublicIpv4(embedded);

  // 2) Explicit translation prefixes (SSRF risk) — always blocked.
  try {
    if (IPV6_ALWAYS_BLOCK.check(ip, 'ipv6')) return true;
  } catch {
    return true;
  }

  // 3) Fail closed outside currently allocated global-unicast envelope 2000::/3.
  try {
    if (!IPV6_GLOBAL_UNICAST.check(ip, 'ipv6')) return true;
  } catch {
    return true;
  }

  // 4) Block IANA non-global / special-use ranges inside 2000::/3.
  try {
    if (IPV6_GUA_BLOCK.check(ip, 'ipv6')) return true;
  } catch {
    return true;
  }

  return false;
}

export function isNonPublicIp(ip) {
  if (!ip || typeof ip !== 'string') return true;
  const normalized = normalizeHostname(ip);
  const version = net.isIP(normalized);
  if (!version) {
    // net.isIP rejects some dotted-quad IPv6 tails; try mapped unwrap.
    const embedded = ipv4MappedEmbedded(normalized);
    if (embedded && net.isIPv4(embedded)) return isNonPublicIpv4(embedded);
    return true;
  }
  try {
    if (version === 4) return isNonPublicIpv4(normalized);
    return isNonPublicIpv6(normalized);
  } catch {
    return true;
  }
}

function normalizeHostname(host) {
  let hostL = String(host || '')
    .toLowerCase()
    .replace(/\.$/, '')
    .trim();
  if (hostL.startsWith('[') && hostL.endsWith(']')) {
    hostL = hostL.slice(1, -1);
  }
  return hostL;
}

export async function resolvePublicIps(host) {
  const hostL = normalizeHostname(host);
  if (!hostL) throw new Error('URL host is required');
  if (BLOCKED_HOSTNAMES.has(hostL) || hostL.endsWith('.localhost')) {
    throw new Error(`blocked hostname: ${hostL}`);
  }
  if (net.isIP(hostL)) {
    if (isNonPublicIp(hostL)) throw new Error(`non-public IP not allowed: ${hostL}`);
    return [hostL];
  }
  const unwrapped = unwrapIpv4Mapped(hostL);
  if (unwrapped !== hostL && net.isIP(unwrapped)) {
    if (isNonPublicIp(unwrapped)) throw new Error(`non-public IP not allowed: ${hostL}`);
    return [unwrapped];
  }
  let addrsRaw;
  if (_testResolve) {
    addrsRaw = await _testResolve(hostL);
  } else {
    let records;
    try {
      records = await dns.lookup(hostL, { all: true, verbatim: true });
    } catch (e) {
      throw new Error(`DNS resolution failed for ${hostL}: ${e.message || e}`);
    }
    if (!records || !records.length) {
      throw new Error(`DNS returned no addresses for ${hostL}`);
    }
    addrsRaw = records.map((r) => r.address);
  }
  if (!addrsRaw || !addrsRaw.length) {
    throw new Error(`DNS returned no addresses for ${hostL}`);
  }
  const addrs = [];
  const seen = new Set();
  for (const addr of addrsRaw) {
    if (isNonPublicIp(addr)) {
      throw new Error(`host resolves to non-public address: ${addr}`);
    }
    if (!seen.has(addr)) {
      seen.add(addr);
      addrs.push(addr);
    }
  }
  if (!addrs.length) throw new Error(`DNS returned no usable addresses for ${hostL}`);
  return addrs;
}

function isLoopbackHost(host) {
  const h = String(host || '')
    .toLowerCase()
    .replace(/^\[|\]$/g, '');
  if (h === 'localhost' || h.endsWith('.localhost')) return true;
  if (h === '::1') return true;
  if (net.isIPv4(h) && h.startsWith('127.')) return true;
  if (h === '0.0.0.0') return true;
  return false;
}

/**
 * Validate URL is public HTTP(S) before network I/O.
 * @returns {Promise<{url: string, publicIps: string[]|null}>}
 */
export async function assertPublicHttpUrl(url, opts = {}) {
  if (!url || typeof url !== 'string') throw new Error('URL is required');
  let parsed;
  try {
    parsed = new URL(url.trim());
  } catch {
    throw new Error('URL is not valid');
  }
  const scheme = (parsed.protocol || '').replace(/:$/, '').toLowerCase();
  if (scheme !== 'https' && !(opts.allowHttp && scheme === 'http')) {
    throw new Error(`scheme not allowed: ${scheme}`);
  }
  if (parsed.username || parsed.password) {
    throw new Error('URL userinfo is not allowed');
  }
  const host = parsed.hostname;
  if (!host) throw new Error('URL host is required');
  if (opts.allowLoopback && isLoopbackHost(host)) {
    return url.trim();
  }
  await resolvePublicIps(host);
  return url.trim();
}

/**
 * Resolve + validate; return public IPs for connection binding.
 * Loopback fixtures return null IPs (use normal connect).
 */
export async function preparePublicDestination(url, opts = {}) {
  if (!url || typeof url !== 'string') throw new Error('URL is required');
  let parsed;
  try {
    parsed = new URL(url.trim());
  } catch {
    throw new Error('URL is not valid');
  }
  const scheme = (parsed.protocol || '').replace(/:$/, '').toLowerCase();
  if (scheme !== 'https' && !(opts.allowHttp && scheme === 'http')) {
    throw new Error(`scheme not allowed: ${scheme}`);
  }
  if (parsed.username || parsed.password) {
    throw new Error('URL userinfo is not allowed');
  }
  const host = parsed.hostname;
  if (!host) throw new Error('URL host is required');
  if (opts.allowLoopback && isLoopbackHost(host)) {
    return { parsed, publicIps: null, loopback: true };
  }
  const publicIps = await resolvePublicIps(host);
  return { parsed, publicIps, loopback: false };
}

function headersToObject(headers) {
  if (!headers) return {};
  if (typeof headers.forEach === 'function') {
    const out = {};
    headers.forEach((v, k) => {
      out[k] = v;
    });
    return out;
  }
  return { ...headers };
}

/**
 * RFC 7230 Host authority from a validated WHATWG URL.
 * Strips any caller Host rebinding: always derived from the current URL hop.
 * WHATWG hostname already brackets IPv6; non-default ports are appended.
 */
export function hostHeaderFromUrl(parsed) {
  const hostname = parsed.hostname;
  if (!hostname) throw new Error('URL host is required');
  const port = parsed.port; // empty string when default for the scheme
  if (
    port &&
    !(
      (parsed.protocol === 'https:' && String(port) === '443') ||
      (parsed.protocol === 'http:' && String(port) === '80')
    )
  ) {
    return `${hostname}:${port}`;
  }
  return hostname;
}

/** Remove every case-insensitive Host key, then set the URL-derived Host. */
function bindUrlDerivedHostHeader(headers, parsed) {
  for (const key of Object.keys(headers)) {
    if (key.toLowerCase() === 'host') delete headers[key];
  }
  headers.Host = hostHeaderFromUrl(parsed);
  return headers;
}

/**
 * Destroy and drain an IncomingMessage-like so body bytes do not leak.
 * Attaches a no-op error listener first so stream.destroy(err) cannot escape
 * as an unhandled 'error' event after the fetch promise has already settled.
 */
function destroyAndDrainMessage(res, err) {
  if (!res || typeof res !== 'object') return;
  let socket = null;
  try {
    socket = res.socket;
  } catch {
    /* ignore hostile/test doubles */
  }
  try {
    if (typeof res.on === 'function') {
      res.on('error', () => {
        /* swallow post-settlement stream errors */
      });
    }
  } catch {
    /* ignore */
  }
  try {
    if (typeof res.destroy === 'function') {
      // Prefer destroy(err) for diagnostics when listeners exist; the no-op
      // listener above prevents uncaughtException / unhandled 'error' events.
      if (err != null) res.destroy(err instanceof Error ? err : new Error(String(err)));
      else res.destroy();
    }
  } catch {
    /* ignore */
  }
  try {
    if (typeof res.resume === 'function') res.resume();
  } catch {
    /* ignore */
  }
  try {
    // IncomingMessage.destroy() can be a no-op for an already-complete
    // parser-defined null body. Explicitly retire the captured connection so
    // bytes hidden by HEAD/204/304 semantics cannot remain on a pooled socket.
    if (socket && !socket.destroyed && typeof socket.destroy === 'function') socket.destroy();
  } catch {
    /* ignore */
  }
}

/**
 * Connection-bound HTTP(S) fetch: DNS-validate, connect to validated IP,
 * bind Host from the validated URL (never caller Host), preserve SNI for DNS
 * names, re-check peer address. Eliminates validate-then-fetch TOCTOU and
 * Host-header rebinding to internal virtual hosts.
 *
 * @param {string} url
 * @param {{method?: string, headers?: object, body?: any, signal?: AbortSignal}} [options]
 * @param {{allowHttp?: boolean, allowLoopback?: boolean}} [ssrfOpts]
 * @returns {Promise<Response>}
 */
export async function fetchPublicHttp(url, options = {}, ssrfOpts = {}) {
  // Capture once: callers may retain and mutate their options object while DNS
  // is pending; listener cleanup must target the same signal it registered on.
  const signal = options.signal ?? null;
  if (signal?.aborted) throw new Error('aborted');
  const dest = await preparePublicDestination(url, ssrfOpts);
  const { parsed, publicIps, loopback } = dest;
  const method = (options.method || 'GET').toUpperCase();
  const headers = bindUrlDerivedHostHeader(headersToObject(options.headers), parsed);
  const maxResponseBytes = options.maxResponseBytes ?? null;
  if (
    maxResponseBytes !== null &&
    (!Number.isSafeInteger(maxResponseBytes) || maxResponseBytes < 1)
  ) {
    throw new HttpResourceLimitError(
      'invalid_http_max_bytes',
      `max response bytes must be a positive safe integer: ${maxResponseBytes}`,
      { limit: maxResponseBytes },
    );
  }

  const isHttps = parsed.protocol === 'https:';
  const port = parsed.port ? Number(parsed.port) : isHttps ? 443 : 80;
  const path = `${parsed.pathname || '/'}${parsed.search || ''}`;
  let lastErr = null;
  const connectHosts = loopback || publicIps === null ? [parsed.hostname] : publicIps;

  for (const ip of connectHosts) {
    try {
      const response = await new Promise((resolve, reject) => {
        let settled = false;
        let abortHandler = null;
        const cleanupAbortListener = () => {
          if (
            abortHandler !== null &&
            signal &&
            typeof signal.removeEventListener === 'function'
          ) {
            try {
              signal.removeEventListener('abort', abortHandler);
            } catch {
              /* ignore cleanup failures */
            }
          }
          abortHandler = null;
        };
        const settleResolve = (value) => {
          if (settled) return;
          settled = true;
          resolve(value);
        };
        const settleReject = (err) => {
          if (settled) return;
          settled = true;
          cleanupAbortListener();
          reject(err);
        };

        const transport = isHttps ? https : http;
        // Connect host is a validated IP (unbracketed). SNI is only for DNS names;
        // IP literals omit servername so Node does not receive bracketed IPv6 SNI.
        const reqOpts = {
          host: ip,
          port,
          path,
          method,
          headers: { ...headers },
          rejectUnauthorized: !(isHttps && ssrfOpts.ignoreTlsErrors === true),
          setHost: false,
        };
        if (isHttps) {
          const sni = tlsServernameFor(parsed.hostname);
          if (sni !== undefined) reqOpts.servername = sni;
        }

        const onSocket = (socket) => {
          try {
            const peer = socket.remoteAddress || socket.getpeername?.()?.[0];
            // Production peer gate — tests must exercise this same function.
            assertConnectedPeer(peer, publicIps, { loopback });
          } catch (e) {
            try {
              socket.destroy();
            } catch {
              /* ignore */
            }
            settleReject(e);
          }
        };

        const onResponse = (res) => {
          // Any synchronous throw here must reject the promise, never escape
          // as an uncaught exception from the ClientRequest callback.
          try {
            const hdrs = res.headers || {};
            const rawStatus = res.statusCode;
            // Fetch Response only accepts 200–599. Map missing/non-finite to 0
            // so construction fails deterministically and is caught below.
            const statusNum =
              typeof rawStatus === 'number' && Number.isFinite(rawStatus)
                ? rawStatus
                : Number(rawStatus);
            const statusForResponse = Number.isFinite(statusNum) ? statusNum : 0;
            const parserDefinedNullBody = method === 'HEAD' || [204, 304].includes(statusForResponse);
            const hasNullBodyStatus = parserDefinedNullBody || statusForResponse === 205;

            const declared = Number.parseInt(hdrs['content-length'] || '', 10);
            // For HEAD and 304, Content-Length describes the selected
            // representation, not bytes in this message. Enforce the cap on
            // actual bytes while draining instead of rejecting valid metadata.
            const declaredLengthIsRepresentationMetadata = method === 'HEAD' || statusForResponse === 304;
            if (
              !declaredLengthIsRepresentationMetadata &&
              maxResponseBytes !== null &&
              Number.isFinite(declared) &&
              declared > maxResponseBytes
            ) {
              const error = new HttpResourceLimitError(
                'http_max_bytes',
                `response body exceeds ${maxResponseBytes} bytes`,
                { limit: maxResponseBytes, actual: declared, url },
              );
              destroyAndDrainMessage(res, error);
              settleReject(error);
              return;
            }

            let observed = 0;
            const body =
              hasNullBodyStatus
                ? null
                : new ReadableStream({
                    start(controller) {
                      res.on('data', (chunk) => {
                        try {
                          observed += chunk.length;
                          if (maxResponseBytes !== null && observed > maxResponseBytes) {
                            const error = new HttpResourceLimitError(
                              'http_max_bytes',
                              `response body exceeds ${maxResponseBytes} bytes`,
                              { limit: maxResponseBytes, actual: observed, url },
                            );
                            try {
                              controller.error(error);
                            } catch {
                              /* ignore */
                            }
                            cleanupAbortListener();
                            destroyAndDrainMessage(res, error);
                            return;
                          }
                          controller.enqueue(new Uint8Array(chunk));
                        } catch (streamErr) {
                          try {
                            controller.error(streamErr);
                          } catch {
                            /* ignore */
                          }
                          cleanupAbortListener();
                          destroyAndDrainMessage(
                            res,
                            streamErr instanceof Error
                              ? streamErr
                              : new Error(String(streamErr)),
                          );
                        }
                      });
                      res.on('end', () => {
                        cleanupAbortListener();
                        try {
                          controller.close();
                        } catch {
                          /* ignore */
                        }
                      });
                      res.on('error', (error) => {
                        cleanupAbortListener();
                        try {
                          controller.error(error);
                        } catch {
                          /* ignore */
                        }
                      });
                      res.on('close', cleanupAbortListener);
                    },
                    cancel(reason) {
                      cleanupAbortListener();
                      destroyAndDrainMessage(
                        res,
                        reason instanceof Error
                          ? reason
                          : new Error(String(reason || 'cancelled')),
                      );
                    },
                  });
            // Build a Fetch API Response for callers without buffering the body.
            // Abnormal statuses (e.g. 600) throw RangeError here — catch and reject.
            const fetchResponse = new Response(body, {
              status: statusForResponse,
              statusText: res.statusMessage || '',
              headers: hdrs,
            });
            // Callers cannot consume a null-body Response. Explicitly drain the
            // IncomingMessage and retire its connection. Node's HTTP parser
            // does not surface bytes after HEAD/204/304 at all, so those paths
            // must close immediately; 205 remains observable and is drained
            // with byte-cap/abort enforcement before its connection is closed.
            if (hasNullBodyStatus) {
              if (typeof res.on !== 'function' || typeof res.resume !== 'function') {
                throw new Error('response stream cannot be drained');
              }
              if (parserDefinedNullBody) {
                cleanupAbortListener();
                destroyAndDrainMessage(res);
                settleResolve(fetchResponse);
                return;
              }
              let nullBodyEnded = false;
              res.on('data', (chunk) => {
                observed += chunk.length;
                if (maxResponseBytes !== null && observed > maxResponseBytes) {
                  const error = new HttpResourceLimitError(
                    'http_max_bytes',
                    `response body exceeds ${maxResponseBytes} bytes`,
                    { limit: maxResponseBytes, actual: observed, url },
                  );
                  cleanupAbortListener();
                  destroyAndDrainMessage(res, error);
                  settleReject(error);
                }
              });
              res.on('end', () => {
                nullBodyEnded = true;
                cleanupAbortListener();
                destroyAndDrainMessage(res);
                settleResolve(fetchResponse);
              });
              res.on('error', (error) => {
                cleanupAbortListener();
                settleReject(error instanceof Error ? error : new Error(String(error)));
              });
              res.on('close', () => {
                cleanupAbortListener();
                if (!nullBodyEnded) {
                  settleReject(new Error('response closed before end-of-stream'));
                }
              });
              res.resume();
              return;
            }
            settleResolve(fetchResponse);
          } catch (e) {
            destroyAndDrainMessage(res, e instanceof Error ? e : new Error(String(e)));
            settleReject(e instanceof Error ? e : new Error(String(e)));
          }
        };

        // Test seam returns a ClientRequest-like emitter; production always
        // registers the same socket peer hook (never short-circuit before it).
        if (signal?.aborted) {
          settleReject(new Error('aborted'));
          return;
        }
        let req;
        try {
          if (_testConnect) {
            req = _testConnect({ ...reqOpts, ip, url, isHttps }, onResponse);
          } else {
            req = transport.request(reqOpts, onResponse);
          }
        } catch (e) {
          settleReject(e instanceof Error ? e : new Error(String(e)));
          return;
        }

        req.on('socket', (socket) => {
          try {
            if (socket.connecting) {
              socket.once('connect', () => onSocket(socket));
            } else {
              onSocket(socket);
            }
          } catch (e) {
            settleReject(e instanceof Error ? e : new Error(String(e)));
          }
        });
        req.on('error', (err) => settleReject(err));
        if (signal) {
          abortHandler = () => {
            cleanupAbortListener();
            try {
              req.destroy(new Error('aborted'));
            } catch {
              /* ignore */
            }
            settleReject(new Error('aborted'));
          };
          signal.addEventListener('abort', abortHandler, { once: true });
          // Close the check/add race: a signal that aborted immediately before
          // listener registration will not replay its event.
          if (signal.aborted && abortHandler !== null) {
            abortHandler();
            return;
          }
        }
        try {
          if (options.body != null) {
            req.write(options.body);
          }
          req.end();
        } catch (e) {
          settleReject(e instanceof Error ? e : new Error(String(e)));
        }
      });
      return response;
    } catch (e) {
      lastErr = e;
      continue;
    }
  }
  throw lastErr || new Error(`could not connect to any validated address for ${parsed.hostname}`);
}

export async function selfTest() {
  const errors = [];
  const privateUrls = [
    'http://127.0.0.1/x',
    'https://127.0.0.1/x',
    'https://localhost/x',
    'https://169.254.169.254/latest/meta-data/',
    'https://192.168.1.10/x',
    'https://[::1]/x',
    'https://[::]/x',
    'https://[::ffff:127.0.0.1]/x',
    'https://[::ffff:169.254.169.254]/latest/',
    'https://[::192.168.1.1]/x',
    'https://[0:0:0:0:0:0:c0a8:101]/x',
    'https://[100:0:0:1::1]/x',
    'https://[2002::1]/x',
    'https://[5f00::1]/x',
    'https://[fec0::1]/x',
    'https://[4000::1]/x',
    'https://[8000::1]/x',
    'https://[2001:db8::1]/x',
    'https://[3fff::1]/x',
    'https://[64:ff9b::7f00:1]/x',
    'https://[64:ff9b::c0a8:1]/x',
    'https://[100::1]/x',
    'https://[2001::1]/x',
    'https://[2001:1::1]/x',
    'https://user:pass@example.com/x',
    'ftp://example.com/x',
  ];
  for (const bad of privateUrls) {
    try {
      await assertPublicHttpUrl(bad, { allowHttp: bad.startsWith('http://') });
      errors.push(`should reject ${bad}`);
    } catch {
      /* expected */
    }
  }
  for (const good of ['https://[::ffff:8.8.8.8]/', 'https://8.8.8.8/', 'https://[2001:4860:4860::8888]/']) {
    try {
      await assertPublicHttpUrl(good);
    } catch (e) {
      errors.push(`public address should be allowed (${good}): ${e.message || e}`);
    }
  }
  if (isNonPublicIp('::ffff:8.8.8.8') || isNonPublicIp('::ffff:808:808')) {
    errors.push('public IPv4-mapped classification must be public');
  }
  // Deterministic cross-runtime public-destination matrix (must match Python).
  for (const [raw, expectBlock] of [
    // Unspecified / loopback / expanded forms
    ['::', true],
    ['0:0:0:0:0:0:0:0', true],
    ['::1', true],
    // IPv4-mapped private / metadata (compressed + hextet + expanded)
    ['::ffff:127.0.0.1', true],
    ['::ffff:169.254.169.254', true],
    ['::ffff:10.1.2.3', true],
    ['::ffff:c0a8:101', true],
    ['0:0:0:0:0:ffff:192.168.1.1', true],
    ['0:0:0:0:0:ffff:c0a8:101', true],
    // Deprecated IPv4-compatible with embedded private (outside 2000::/3)
    ['::192.168.1.1', true],
    ['0:0:0:0:0:0:c0a8:101', true],
    // Outside global-unicast envelope 2000::/3
    ['100:0:0:1::1', true], // IANA dummy IPv6 prefix (RFC 9780)
    ['100::1', true], // discard-only
    ['5f00::1', true], // SRv6 SIDs (RFC 9602)
    ['fec0::1', true], // deprecated site-local
    ['4000::1', true],
    ['8000::1', true],
    ['fc00::1', true], // ULA
    ['fe80::1', true], // link-local
    ['ff02::1', true], // multicast
    // Translation prefixes (blocked even if IANA globally reachable)
    ['64:ff9b::7f00:1', true],
    ['64:ff9b::808:808', true],
    ['64:ff9b:1::1', true],
    ['2002::1', true], // 6to4
    ['2002:c0a8:101::1', true],
    // Inside 2000::/3 special-use
    ['2001::1', true], // Teredo / 2001::/23 parent
    ['2001:2::1', true], // benchmarking ⊂ 2001::/23
    ['2001:10::1', true], // deprecated ORCHID ⊂ 2001::/23
    // 2001::/23 IANA "globally reachable" more-specifics — intentionally blocked
    // for cross-runtime stability (CPython 3.10–3.12 disagree).
    ['2001:1::1', true],
    ['2001:1::2', true],
    ['2001:1::3', true],
    ['2001:1:1::1', true],
    ['2001:3::1', true],
    ['2001:4:112::1', true],
    ['2001:20::1', true],
    ['2001:30::1', true],
    ['2001:db8::1', true],
    ['3fff::1', true],
    // Safe public controls
    ['8.8.8.8', false],
    ['1.1.1.1', false],
    ['::ffff:8.8.8.8', false],
    ['::ffff:808:808', false],
    ['0:0:0:0:0:ffff:8.8.8.8', false],
    ['2001:4860:4860::8888', false], // Google Public DNS
    ['2606:4700:4700::1111', false], // Cloudflare DNS
    ['2000::1', false], // inside GUA, not special-use
    ['2620:4f:8000::1', false], // AS112 direct delegation (outside 2001::/23)
  ]) {
    const blocked = isNonPublicIp(raw);
    if (blocked !== expectBlock) {
      errors.push(`isNonPublicIp(${raw})=${blocked}, expected ${expectBlock}`);
    }
  }

  /**
   * Test connect factory: ClientRequest-like emitter that surfaces a peer
   * address via the real `socket` event so production assertConnectedPeer runs.
   * Never synthesizes peer-validation error text.
   *
   * @param {string|null|undefined} peerAddress
   * @param {Function} onResponse
   * @param {{respond?: boolean, delayedConnect?: boolean, statusCode?: number, statusMessage?: string, headers?: object, bodyChunks?: Buffer[], onResume?: Function}} [opts]
   */
  function makePeerTestRequest(peerAddress, onResponse, opts = {}) {
    const {
      respond = false,
      delayedConnect = false,
      statusCode = 204,
      statusMessage = 'No Content',
      headers = {},
      bodyChunks = null,
      onResume = null,
    } = opts;
    const req = new EventEmitter();
    let ended = false;
    req.write = () => true;
    req.destroy = (err) => {
      if (err) process.nextTick(() => req.emit('error', err));
    };
    req.end = () => {
      if (ended) return;
      ended = true;
      const socket = new EventEmitter();
      socket.remoteAddress = peerAddress;
      socket.connecting = Boolean(delayedConnect);
      socket.destroyed = false;
      socket.destroy = function destroySocket() {
        this.destroyed = true;
      };

      const deliverResponse = () => {
        if (socket.destroyed || !respond) return;
        const res = new EventEmitter();
        res.statusCode = statusCode;
        res.statusMessage = statusMessage;
        res.headers = headers;
        res.destroyed = false;
        let responseEnded = false;
        const emitResponseEnd = () => {
          if (responseEnded || res.destroyed) return;
          responseEnded = true;
          res.emit('end');
        };
        res.destroy = function destroyRes(err) {
          this.destroyed = true;
          if (err) process.nextTick(() => this.emit('error', err));
        };
        res.resume = () => {
          if (typeof onResume === 'function') onResume();
          if (!Array.isArray(bodyChunks)) process.nextTick(emitResponseEnd);
        };
        res.removeAllListeners = EventEmitter.prototype.removeAllListeners.bind(res);
        onResponse(res);
        if (Array.isArray(bodyChunks)) {
          for (const chunk of bodyChunks) {
            res.emit('data', chunk);
          }
          emitResponseEnd();
        }
      };

      // Production path: socket event, then connect (immediate or delayed).
      req.emit('socket', socket);
      if (delayedConnect) {
        process.nextTick(() => {
          socket.connecting = false;
          socket.emit('connect');
          deliverResponse();
        });
      } else {
        // connecting=false: production calls onSocket synchronously on socket event.
        // A real ClientRequest invokes its response callback asynchronously;
        // preserve that boundary so callback-throw regression tests cannot be
        // masked by the surrounding req.end() try/catch.
        process.nextTick(deliverResponse);
      }
    };
    return req;
  }

  // Pure peer validator: non-public and public-but-unvalidated peers rejected.
  {
    try {
      assertConnectedPeer('127.0.0.1', ['8.8.8.8'], { loopback: false });
      errors.push('assertConnectedPeer must reject non-public peer');
    } catch (e) {
      if (!/non-public/i.test(String(e.message || e))) {
        errors.push(`non-public peer error text unexpected: ${e.message || e}`);
      }
    }
    try {
      assertConnectedPeer('8.8.8.8', ['1.2.3.4'], { loopback: false });
      errors.push('assertConnectedPeer must reject public-but-unvalidated peer');
    } catch (e) {
      if (!/mismatch/i.test(String(e.message || e))) {
        errors.push(`unvalidated peer error text unexpected: ${e.message || e}`);
      }
    }
    try {
      assertConnectedPeer('8.8.8.8', ['8.8.8.8'], { loopback: false });
    } catch (e) {
      errors.push(`assertConnectedPeer must accept validated public peer: ${e.message || e}`);
    }
    // Compressed vs expanded IPv6, and IPv4 vs mapped-peer equivalence.
    try {
      assertConnectedPeer('2001:4860:4860:0:0:0:0:8888', ['2001:4860:4860::8888']);
      assertConnectedPeer('2001:4860:4860::8888', ['2001:4860:4860:0:0:0:0:8888']);
      assertConnectedPeer('::ffff:8.8.8.8', ['8.8.8.8']);
      assertConnectedPeer('8.8.8.8', ['::ffff:8.8.8.8']);
      assertConnectedPeer('::ffff:808:808', ['8.8.8.8']);
    } catch (e) {
      errors.push(`canonical peer membership must accept equivalents: ${e.message || e}`);
    }
    if (peerMatchesValidatedIps('not-an-ip', ['8.8.8.8'])) {
      errors.push('malformed peer must not match validated set');
    }
    if (peerMatchesValidatedIps('8.8.8.8', ['not-an-ip'])) {
      errors.push('malformed validated entry must fail closed');
    }
    const malformedPeers = [
      ' 8.8.8.8',
      '8.8.8.8 ',
      '[2001:4860:4860::8888]',
      '2001:4860:4860::8888%',
      '2001:4860:4860::8888%%',
      '2001:4860:4860::8888%2',
      '2001:4860:4860::8888%a%b',
      '[2001:4860:4860::8888]%7',
      'fe80::1%2',
      'fe80::1%eth0',
      '::ffff:008.008.008.008',
    ];
    for (const bad of malformedPeers) {
      if (canonicalizeIpForComparison(bad) != null) {
        errors.push(`malformed/scoped peer must not canonicalize: ${bad}`);
      }
      if (peerMatchesValidatedIps(bad, ['2001:4860:4860::8888', '8.8.8.8'])) {
        errors.push(`malformed/scoped peer must not match validated set: ${bad}`);
      }
      try {
        assertConnectedPeer(bad, ['2001:4860:4860::8888', '8.8.8.8']);
        errors.push(`malformed/scoped peer must fail closed: ${bad}`);
      } catch {
        /* expected */
      }
    }
  }

  // expandIpv6Hextets: reject :: that replaces zero groups (via fail-closed classify).
  {
    const zeroCompression = [
      '1:2:3:4:5:6:7:8::',
      '1:2:3:4:5:6:7::8',
      '1::2:3:4:5:6:7:8',
      '::ffff:8.8.8.8::',
      '0:0:0:0:0:ffff:8.8.8.8::',
      '::ffff:008.008.008.008',
      '0:0:0:0:0:ffff:008.008.008.008',
    ];
    for (const bad of zeroCompression) {
      if (canonicalizeIpForComparison(bad) != null) {
        errors.push(`malformed IPv6/map form must fail closed: ${bad}`);
      }
      if (!isNonPublicIp(bad)) {
        errors.push(`malformed IPv6 must not classify public: ${bad}`);
      }
    }
  }

  // Pure hostHeaderFromUrl: DNS / IPv4 / bracketed IPv6 / non-default ports.
  {
    const hostCases = [
      ['https://example.com/x', 'example.com'],
      ['https://example.com:443/x', 'example.com'],
      ['https://example.com:8443/x', 'example.com:8443'],
      ['http://example.com:80/x', 'example.com'],
      ['http://example.com:8080/x', 'example.com:8080'],
      ['https://8.8.8.8/', '8.8.8.8'],
      ['https://8.8.8.8:8443/', '8.8.8.8:8443'],
      ['https://[2001:4860:4860::8888]/', '[2001:4860:4860::8888]'],
      ['https://[2001:4860:4860::8888]:8443/', '[2001:4860:4860::8888]:8443'],
    ];
    for (const [rawUrl, expectHost] of hostCases) {
      try {
        const got = hostHeaderFromUrl(new URL(rawUrl));
        if (got !== expectHost) {
          errors.push(`hostHeaderFromUrl(${rawUrl})=${got}, expected ${expectHost}`);
        }
      } catch (e) {
        errors.push(`hostHeaderFromUrl(${rawUrl}) threw: ${e.message || e}`);
      }
    }
  }

  // HTTPS request options: DNS keeps SNI; IP literals omit SNI; Host is always URL-derived.
  {
    const captured = [];
    const cases = [
      {
        label: 'dns',
        url: 'https://sni-dns.test/path',
        dns: ['1.2.3.4'],
        peer: '1.2.3.4',
        expectServername: 'sni-dns.test',
        expectHost: 'sni-dns.test',
        expectConnectHost: '1.2.3.4',
      },
      {
        label: 'ipv4-literal',
        url: 'https://8.8.8.8/',
        dns: null,
        peer: '8.8.8.8',
        expectServername: undefined,
        expectHost: '8.8.8.8',
        expectConnectHost: '8.8.8.8',
      },
      {
        label: 'ipv6-literal',
        url: 'https://[2001:4860:4860::8888]/',
        dns: null,
        peer: '2001:4860:4860::8888',
        expectServername: undefined,
        expectHost: '[2001:4860:4860::8888]',
        expectConnectHost: '2001:4860:4860::8888',
      },
      {
        label: 'ipv6-literal-port',
        url: 'https://[2001:4860:4860::8888]:8443/',
        dns: null,
        peer: '2001:4860:4860::8888',
        expectServername: undefined,
        expectHost: '[2001:4860:4860::8888]:8443',
        expectConnectHost: '2001:4860:4860::8888',
      },
    ];
    for (const c of cases) {
      captured.length = 0;
      if (c.dns) setTestDnsResolver(async () => c.dns);
      else setTestDnsResolver(null);
      setTestConnectFactory((opts, onResponse) => {
        captured.push({
          host: opts.host,
          servername: opts.servername,
          Host: opts.headers.Host || opts.headers.host,
          hasServernameKey: Object.prototype.hasOwnProperty.call(opts, 'servername'),
          hostKeyCount: Object.keys(opts.headers).filter((k) => k.toLowerCase() === 'host')
            .length,
        });
        return makePeerTestRequest(c.peer, onResponse, { respond: true });
      });
      try {
        await fetchPublicHttp(c.url, { method: 'GET' }, {});
      } catch (e) {
        errors.push(`HTTPS options capture (${c.label}) failed: ${e.message || e}`);
        setTestDnsResolver(null);
        setTestConnectFactory(null);
        continue;
      }
      setTestDnsResolver(null);
      setTestConnectFactory(null);
      if (captured.length !== 1) {
        errors.push(`HTTPS options capture (${c.label}): expected 1 request, got ${captured.length}`);
        continue;
      }
      const got = captured[0];
      if (got.host !== c.expectConnectHost) {
        errors.push(
          `HTTPS options (${c.label}): connect host ${got.host} != ${c.expectConnectHost}`,
        );
      }
      if (got.Host !== c.expectHost) {
        errors.push(`HTTPS options (${c.label}): Host ${got.Host} != ${c.expectHost}`);
      }
      if (got.hostKeyCount !== 1) {
        errors.push(`HTTPS options (${c.label}): expected exactly one Host key, got ${got.hostKeyCount}`);
      }
      if (c.expectServername === undefined) {
        if (got.hasServernameKey || got.servername !== undefined) {
          errors.push(
            `HTTPS options (${c.label}): SNI must be omitted for IP literal, got ${got.servername}`,
          );
        }
      } else if (got.servername !== c.expectServername) {
        errors.push(
          `HTTPS options (${c.label}): SNI ${got.servername} != ${c.expectServername}`,
        );
      }
    }
  }

  // Host-header rebinding: hostile Host / HOST must be stripped; URL authority wins.
  {
    const rebindingCases = [
      {
        label: 'host-lowercase-loopback',
        url: 'https://rebinding-host.test/path',
        dns: ['1.2.3.4'],
        peer: '1.2.3.4',
        callerHeaders: { host: '127.0.0.1', 'User-Agent': 'ssrf-test' },
        expectHost: 'rebinding-host.test',
      },
      {
        label: 'HOST-uppercase-metadata',
        url: 'https://rebinding-host.test/path',
        dns: ['1.2.3.4'],
        peer: '1.2.3.4',
        callerHeaders: { HOST: '169.254.169.254', Accept: '*/*' },
        expectHost: 'rebinding-host.test',
      },
      {
        label: 'mixed-case-Host-ipv6',
        url: 'https://[2001:4860:4860::8888]:8443/x',
        dns: null,
        peer: '2001:4860:4860::8888',
        callerHeaders: { HoSt: '127.0.0.1', host: 'metadata', HOST: '::1' },
        expectHost: '[2001:4860:4860::8888]:8443',
      },
      {
        label: 'dns-with-port-authority',
        url: 'https://port-host.test:8443/x',
        dns: ['9.9.9.9'],
        peer: '9.9.9.9',
        callerHeaders: { Host: 'internal.local:443' },
        expectHost: 'port-host.test:8443',
      },
    ];
    for (const c of rebindingCases) {
      let capturedHeaders = null;
      if (c.dns) setTestDnsResolver(async () => c.dns);
      else setTestDnsResolver(null);
      setTestConnectFactory((opts, onResponse) => {
        capturedHeaders = { ...opts.headers };
        return makePeerTestRequest(c.peer, onResponse, { respond: true });
      });
      try {
        await fetchPublicHttp(c.url, { method: 'GET', headers: c.callerHeaders }, {});
      } catch (e) {
        errors.push(`Host rebinding (${c.label}) failed: ${e.message || e}`);
        setTestDnsResolver(null);
        setTestConnectFactory(null);
        continue;
      }
      setTestDnsResolver(null);
      setTestConnectFactory(null);
      if (!capturedHeaders) {
        errors.push(`Host rebinding (${c.label}): no request captured`);
        continue;
      }
      const hostKeys = Object.keys(capturedHeaders).filter((k) => k.toLowerCase() === 'host');
      if (hostKeys.length !== 1) {
        errors.push(
          `Host rebinding (${c.label}): expected one Host key, got ${hostKeys.join(',') || 'none'}`,
        );
      }
      const gotHost = capturedHeaders.Host ?? capturedHeaders.host ?? capturedHeaders.HOST;
      if (gotHost !== c.expectHost) {
        errors.push(
          `Host rebinding (${c.label}): Host ${gotHost} != ${c.expectHost} (caller rebinding must not stick)`,
        );
      }
      // No residual hostile values under any Host casing.
      for (const k of hostKeys) {
        if (String(capturedHeaders[k]).includes('127.0.0.1') ||
            String(capturedHeaders[k]).includes('169.254') ||
            String(capturedHeaders[k]) === 'metadata' ||
            String(capturedHeaders[k]) === '::1' ||
            String(capturedHeaders[k]).includes('internal.local')) {
          errors.push(`Host rebinding (${c.label}): hostile value retained under ${k}`);
        }
      }
    }
  }

  // Delayed connect path: socket.connecting=true then 'connect' event runs assertConnectedPeer.
  {
    setTestDnsResolver(async () => ['1.2.3.4']);
    setTestConnectFactory((opts, onResponse) =>
      makePeerTestRequest('1.2.3.4', onResponse, { respond: true, delayedConnect: true }),
    );
    try {
      const res = await fetchPublicHttp('https://delayed-connect.test/', { method: 'GET' }, {});
      if (res.status !== 204) {
        errors.push(`delayed-connect happy path expected 204, got ${res.status}`);
      }
    } catch (e) {
      errors.push(`delayed-connect production path failed: ${e.message || e}`);
    }
    setTestDnsResolver(null);
    setTestConnectFactory(null);

    setTestDnsResolver(async () => ['1.2.3.4']);
    setTestConnectFactory((opts, onResponse) =>
      makePeerTestRequest('127.0.0.1', onResponse, { respond: true, delayedConnect: true }),
    );
    let delayedReb = false;
    try {
      await fetchPublicHttp('https://delayed-rebinding.test/', { method: 'GET' }, {});
    } catch (e) {
      delayedReb = /non-public/i.test(String(e.message || e));
    }
    setTestDnsResolver(null);
    setTestConnectFactory(null);
    if (!delayedReb) {
      errors.push('delayed-connect path must still reject non-public peer via assertConnectedPeer');
    }
  }

  // Abnormal upstream status (600) must reject the promise, never uncaught crash.
  {
    setTestDnsResolver(async () => ['1.2.3.4']);
    setTestConnectFactory((opts, onResponse) =>
      makePeerTestRequest('1.2.3.4', onResponse, {
        respond: true,
        statusCode: 600,
        statusMessage: 'Nonstandard',
        headers: { 'content-type': 'text/plain' },
      }),
    );
    let status600Rejected = false;
    let status600Uncaught = false;
    const onUncaught = () => {
      status600Uncaught = true;
    };
    process.on('uncaughtException', onUncaught);
    try {
      await fetchPublicHttp('https://status600.test/', { method: 'GET' }, {});
    } catch {
      status600Rejected = true;
    } finally {
      // The fake stream emits destroy(error) on nextTick. Keep the observer
      // installed through that turn so this regression test cannot pass while
      // an asynchronous uncaughtException is still queued.
      await new Promise((resolve) => setImmediate(resolve));
      process.removeListener('uncaughtException', onUncaught);
      setTestDnsResolver(null);
      setTestConnectFactory(null);
    }
    if (!status600Rejected) {
      errors.push('status 600 must reject fetchPublicHttp promise');
    }
    if (status600Uncaught) {
      errors.push('status 600 must not escape as uncaughtException');
    }

    // Normal status still works through the same Response construction path.
    setTestDnsResolver(async () => ['1.2.3.4']);
    setTestConnectFactory((opts, onResponse) =>
      makePeerTestRequest('1.2.3.4', onResponse, {
        respond: true,
        statusCode: 200,
        statusMessage: 'OK',
        headers: { 'content-type': 'text/plain' },
      }),
    );
    try {
      const okRes = await fetchPublicHttp('https://status200.test/', { method: 'GET' }, {});
      if (okRes.status !== 200) {
        errors.push(`normal status 200 expected, got ${okRes.status}`);
      }
    } catch (e) {
      errors.push(`normal status 200 must succeed: ${e.message || e}`);
    }
    setTestDnsResolver(null);
    setTestConnectFactory(null);

    // Null-body statuses must drain the underlying message; callers receive no
    // body stream with which to do so themselves.
    let noBodyResumeCount = 0;
    setTestDnsResolver(async () => ['1.2.3.4']);
    setTestConnectFactory((opts, onResponse) =>
      makePeerTestRequest('1.2.3.4', onResponse, {
        respond: true,
        statusCode: 204,
        statusMessage: 'No Content',
        onResume: () => {
          noBodyResumeCount += 1;
        },
      }),
    );
    try {
      const noBodyRes = await fetchPublicHttp('https://status204.test/', { method: 'GET' }, {});
      if (noBodyRes.status !== 204 || noBodyRes.body !== null) {
        errors.push('status 204 must produce a null-body Response');
      }
    } catch (e) {
      errors.push(`status 204 drain path must succeed: ${e.message || e}`);
    }
    setTestDnsResolver(null);
    setTestConnectFactory(null);
    if (noBodyResumeCount !== 1) {
      errors.push(`status 204 must drain exactly once, got ${noBodyResumeCount}`);
    }

    // A protocol-violating body on a null-body status is still network input
    // and must not bypass the configured byte cap while being discarded.
    setTestDnsResolver(async () => ['1.2.3.4']);
    setTestConnectFactory((opts, onResponse) =>
      makePeerTestRequest('1.2.3.4', onResponse, {
        respond: true,
        statusCode: 205,
        statusMessage: 'Reset Content',
        bodyChunks: [Buffer.from('oversize')],
      }),
    );
    let nullBodyCapRejected = false;
    try {
      await fetchPublicHttp(
        'https://status205-cap.test/',
        { method: 'GET', maxResponseBytes: 4 },
        {},
      );
    } catch (e) {
      nullBodyCapRejected = e instanceof HttpResourceLimitError;
    }
    setTestDnsResolver(null);
    setTestConnectFactory(null);
    if (!nullBodyCapRejected) {
      errors.push('null-body status must enforce the streaming byte cap');
    }

    // HEAD and 304 Content-Length is representation metadata, not body bytes.
    for (const metadataCase of [
      { label: 'HEAD 200', method: 'HEAD', statusCode: 200, statusMessage: 'OK' },
      { label: 'GET 304', method: 'GET', statusCode: 304, statusMessage: 'Not Modified' },
    ]) {
      setTestDnsResolver(async () => ['1.2.3.4']);
      setTestConnectFactory((opts, onResponse) =>
        makePeerTestRequest('1.2.3.4', onResponse, {
          respond: true,
          statusCode: metadataCase.statusCode,
          statusMessage: metadataCase.statusMessage,
          headers: { 'content-length': '1000' },
        }),
      );
      try {
        const metadataRes = await fetchPublicHttp(
          `https://content-length-metadata.test/${metadataCase.label.replace(/\s+/g, '-')}`,
          { method: metadataCase.method, maxResponseBytes: 4 },
          {},
        );
        if (metadataRes.status !== metadataCase.statusCode || metadataRes.body !== null) {
          errors.push(`${metadataCase.label} must resolve with a null body`);
        }
      } catch (e) {
        errors.push(`${metadataCase.label} representation Content-Length rejected: ${e.message || e}`);
      }
      setTestDnsResolver(null);
      setTestConnectFactory(null);
    }

    // Raw TCP regression: Node intentionally emits no data for HEAD/204/304,
    // even if a hostile peer keeps writing chunk frames after the headers.
    // The client must retire that connection rather than pool hidden bytes.
    for (const rawCase of [
      { label: 'HEAD-200', method: 'HEAD', statusCode: 200, statusText: 'OK' },
      { label: 'GET-204', method: 'GET', statusCode: 204, statusText: 'No Content' },
      { label: 'GET-304', method: 'GET', statusCode: 304, statusText: 'Not Modified' },
    ]) {
      let serverSocket = null;
      let writer = null;
      let markClosed;
      const socketClosed = new Promise((resolve) => {
        markClosed = resolve;
      });
      const server = net.createServer((socket) => {
        serverSocket = socket;
        socket.on('error', () => {
          /* expected when the guarded client retires the connection */
        });
        socket.on('close', () => {
          if (writer !== null) clearInterval(writer);
          markClosed(true);
        });
        socket.once('data', () => {
          socket.write(
            `HTTP/1.1 ${rawCase.statusCode} ${rawCase.statusText}\r\n` +
              'Transfer-Encoding: chunked\r\n' +
              'Connection: keep-alive\r\n\r\n',
          );
          const payload = 'x'.repeat(1024);
          const frame = `${payload.length.toString(16)}\r\n${payload}\r\n`;
          writer = setInterval(() => {
            if (!socket.destroyed) socket.write(frame);
          }, 5);
        });
      });
      try {
        await new Promise((resolve, reject) => {
          const onListenError = (error) => reject(error);
          server.once('error', onListenError);
          server.listen(0, '127.0.0.1', () => {
            server.removeListener('error', onListenError);
            resolve();
          });
        });
        const address = server.address();
        if (!address || typeof address === 'string') throw new Error('raw test server has no port');
        const guarded = await fetchPublicHttp(
          `http://127.0.0.1:${address.port}/${rawCase.label}`,
          { method: rawCase.method, maxResponseBytes: 4 },
          { allowHttp: true, allowLoopback: true },
        );
        if (guarded.status !== rawCase.statusCode || guarded.body !== null) {
          errors.push(`${rawCase.label} raw response must resolve with a null body`);
        }
        const closed = await Promise.race([
          socketClosed,
          new Promise((resolve) => setTimeout(() => resolve(false), 1000)),
        ]);
        if (!closed) {
          errors.push(`${rawCase.label} parser-null connection was not retired`);
        }
      } catch (e) {
        errors.push(`${rawCase.label} raw null-body regression failed: ${e.message || e}`);
      } finally {
        if (writer !== null) clearInterval(writer);
        if (serverSocket && !serverSocket.destroyed) serverSocket.destroy();
        if (server.listening) {
          await new Promise((resolve) => server.close(() => resolve()));
        }
      }
    }

    // Completed and rejected requests must not retain AbortSignal listeners.
    const sharedController = new AbortController();
    setTestDnsResolver(async () => ['1.2.3.4']);
    setTestConnectFactory((opts, onResponse) =>
      makePeerTestRequest('1.2.3.4', onResponse, {
        respond: true,
        statusCode: 204,
      }),
    );
    for (let i = 0; i < 12; i += 1) {
      try {
        await fetchPublicHttp(
          `https://signal-cleanup.test/${i}`,
          { method: 'GET', signal: sharedController.signal },
          {},
        );
      } catch (e) {
        errors.push(`AbortSignal cleanup request ${i} failed: ${e.message || e}`);
        break;
      }
    }
    setTestDnsResolver(null);
    setTestConnectFactory(null);
    const retainedAbortListeners = getEventListeners(sharedController.signal, 'abort').length;
    if (retainedAbortListeners !== 0) {
      errors.push(`completed requests retained ${retainedAbortListeners} abort listeners`);
    }

    const rejectedController = new AbortController();
    setTestDnsResolver(async () => ['1.2.3.4']);
    setTestConnectFactory((opts, onResponse) =>
      makePeerTestRequest('127.0.0.1', onResponse, { respond: true }),
    );
    try {
      await fetchPublicHttp(
        'https://signal-reject-cleanup.test/',
        { method: 'GET', signal: rejectedController.signal },
        {},
      );
      errors.push('peer rejection cleanup test must reject');
    } catch {
      /* expected */
    }
    setTestDnsResolver(null);
    setTestConnectFactory(null);
    if (getEventListeners(rejectedController.signal, 'abort').length !== 0) {
      errors.push('rejected request retained an abort listener');
    }

    const preAbortedController = new AbortController();
    preAbortedController.abort();
    let preAbortedDnsCalls = 0;
    let preAbortedRequestCalls = 0;
    setTestDnsResolver(async () => {
      preAbortedDnsCalls += 1;
      return ['1.2.3.4'];
    });
    setTestConnectFactory(() => {
      preAbortedRequestCalls += 1;
      throw new Error('pre-aborted request factory must not run');
    });
    try {
      await fetchPublicHttp(
        'https://signal-pre-aborted.test/',
        { method: 'POST', body: 'must-not-write', signal: preAbortedController.signal },
        {},
      );
      errors.push('pre-aborted signal must reject');
    } catch (e) {
      if (!/aborted/i.test(String(e.message || e))) {
        errors.push(`pre-aborted signal error unexpected: ${e.message || e}`);
      }
    }
    setTestDnsResolver(null);
    setTestConnectFactory(null);
    if (preAbortedDnsCalls !== 0 || preAbortedRequestCalls !== 0) {
      errors.push(
        `pre-aborted signal performed work: dns=${preAbortedDnsCalls}, request=${preAbortedRequestCalls}`,
      );
    }
  }

  // F-05: rebinding — DNS public, connected peer private → production assertConnectedPeer
  {
    setTestDnsResolver(async () => ['8.8.8.8']);
    setTestConnectFactory((opts, onResponse) =>
      makePeerTestRequest('127.0.0.1', onResponse, { respond: true }),
    );
    let rebBlocked = false;
    let rebMsg = '';
    try {
      await fetchPublicHttp('https://rebinding.test/', { method: 'GET' }, {});
    } catch (e) {
      rebMsg = String(e.message || e);
      rebBlocked = /non-public/i.test(rebMsg);
    }
    setTestDnsResolver(null);
    setTestConnectFactory(null);
    if (!rebBlocked) {
      errors.push(
        `DNS rebinding / private peer must be blocked on connect (got: ${rebMsg || 'no error'})`,
      );
    }
  }

  // Mixed public+private DNS answer must fail closed at resolve
  {
    setTestDnsResolver(async () => ['8.8.8.8', '127.0.0.1']);
    let mixedBlocked = false;
    try {
      await resolvePublicIps('mixed.test');
    } catch (e) {
      mixedBlocked = /non-public/i.test(String(e.message || e));
    }
    setTestDnsResolver(null);
    if (!mixedBlocked) errors.push('mixed public/private DNS answers must reject');
  }

  // Peer mismatch via production socket hook: validated 1.2.3.4, peer 8.8.8.8
  {
    setTestDnsResolver(async () => ['1.2.3.4']);
    setTestConnectFactory((opts, onResponse) =>
      makePeerTestRequest('8.8.8.8', onResponse, { respond: true }),
    );
    let mismatchBlocked = false;
    let mismatchMsg = '';
    try {
      await fetchPublicHttp('https://mismatch.test/', { method: 'GET' }, {});
    } catch (e) {
      mismatchMsg = String(e.message || e);
      mismatchBlocked = /mismatch/i.test(mismatchMsg);
    }
    setTestDnsResolver(null);
    setTestConnectFactory(null);
    if (!mismatchBlocked) {
      errors.push(`peer mismatch must be blocked via production hook (got: ${mismatchMsg || 'no error'})`);
    }
  }

  // Equivalent compressed/expanded IPv6 peer accepted through production socket hook
  {
    setTestDnsResolver(async () => ['2001:4860:4860::8888']);
    setTestConnectFactory((opts, onResponse) =>
      makePeerTestRequest('2001:4860:4860:0:0:0:0:8888', onResponse, { respond: true }),
    );
    try {
      await fetchPublicHttp('https://ipv6-canon.test/', { method: 'GET' }, {});
    } catch (e) {
      errors.push(
        `production hook must accept compressed/expanded IPv6 peer: ${e.message || e}`,
      );
    }
    setTestDnsResolver(null);
    setTestConnectFactory(null);
  }

  // IPv4 validated vs IPv4-mapped peer through production socket hook
  {
    setTestDnsResolver(async () => ['8.8.8.8']);
    setTestConnectFactory((opts, onResponse) =>
      makePeerTestRequest('::ffff:8.8.8.8', onResponse, { respond: true }),
    );
    try {
      await fetchPublicHttp('https://mapped-peer.test/', { method: 'GET' }, {});
    } catch (e) {
      errors.push(`production hook must accept IPv4-mapped peer: ${e.message || e}`);
    }
    setTestDnsResolver(null);
    setTestConnectFactory(null);
  }

  // Streaming cap: no Content-Length, body crosses the byte limit while reading.
  {
    const server = http.createServer((_req, res) => {
      res.writeHead(200, { 'content-type': 'text/plain' });
      res.write('123');
      setTimeout(() => {
        res.end('45');
      }, 10);
    });
    await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
    const port = server.address().port;
    let streamCapBlocked = false;
    try {
      const response = await fetchPublicHttp(
        `http://127.0.0.1:${port}/large`,
        { method: 'GET', maxResponseBytes: 4 },
        { allowHttp: true, allowLoopback: true },
      );
      await response.text();
    } catch (e) {
      streamCapBlocked = e?.code === 'http_max_bytes';
    } finally {
      await new Promise((resolve) => server.close(resolve));
    }
    if (!streamCapBlocked) errors.push('streaming response cap must abort while reading');
  }

  if (errors.length) {
    console.error('ssrf_guards.mjs self-test FAILED:');
    for (const e of errors) console.error(`  - ${e}`);
    process.exitCode = 1;
    return 1;
  }
  console.log('ssrf_guards.mjs self-test ok');
  return 0;
}

// Only auto-run when this file is the entrypoint (not when imported).
const _isMain =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (_isMain && process.argv.includes('--self-test')) {
  selfTest();
}
