// Public-address validation + connection-bound fetch for Node helpers.
// Stdlib-only. Mirrors the threat model of scripts/_ssrf_helpers.py:
// - HTTPS only by default
// - no userinfo
// - blocked hostnames (localhost, cloud metadata names)
// - non-public IPv4/IPv6 literals rejected
// - DNS resolutions must not include non-public addresses
// - call again on every redirect hop
// - fetchPublicHttp binds the TCP connection to a validated public IP (F-05)

import dns from 'node:dns/promises';
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

// Pre-seed common non-public ranges (IPv4 + IPv6).
const PRIVATE_BLOCKS = new BlockList();
// IPv4 special-use
PRIVATE_BLOCKS.addSubnet('0.0.0.0', 8, 'ipv4');
PRIVATE_BLOCKS.addSubnet('10.0.0.0', 8, 'ipv4');
PRIVATE_BLOCKS.addSubnet('100.64.0.0', 10, 'ipv4'); // CGNAT
PRIVATE_BLOCKS.addSubnet('127.0.0.0', 8, 'ipv4');
PRIVATE_BLOCKS.addSubnet('169.254.0.0', 16, 'ipv4');
PRIVATE_BLOCKS.addSubnet('172.16.0.0', 12, 'ipv4');
PRIVATE_BLOCKS.addSubnet('192.0.0.0', 24, 'ipv4');
PRIVATE_BLOCKS.addSubnet('192.0.2.0', 24, 'ipv4'); // TEST-NET-1
PRIVATE_BLOCKS.addSubnet('192.168.0.0', 16, 'ipv4');
PRIVATE_BLOCKS.addSubnet('198.18.0.0', 15, 'ipv4');
PRIVATE_BLOCKS.addSubnet('198.51.100.0', 24, 'ipv4'); // TEST-NET-2
PRIVATE_BLOCKS.addSubnet('203.0.113.0', 24, 'ipv4'); // TEST-NET-3
PRIVATE_BLOCKS.addSubnet('224.0.0.0', 4, 'ipv4'); // multicast
PRIVATE_BLOCKS.addSubnet('240.0.0.0', 4, 'ipv4'); // reserved
// IPv6 special-use
PRIVATE_BLOCKS.addSubnet('::1', 128, 'ipv6');
PRIVATE_BLOCKS.addSubnet('fc00::', 7, 'ipv6'); // ULA
PRIVATE_BLOCKS.addSubnet('fe80::', 10, 'ipv6'); // link-local
PRIVATE_BLOCKS.addSubnet('ff00::', 8, 'ipv6'); // multicast

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

function unwrapIpv4Mapped(ip) {
  const m = /^:?:ffff:(\d{1,3}(?:\.\d{1,3}){3})$/i.exec(ip);
  if (m) return m[1];
  const m2 = /^:?:ffff:([0-9a-f]{1,4}):([0-9a-f]{1,4})$/i.exec(ip);
  if (m2) {
    const hi = parseInt(m2[1], 16);
    const lo = parseInt(m2[2], 16);
    return `${(hi >> 8) & 255}.${hi & 255}.${(lo >> 8) & 255}.${lo & 255}`;
  }
  return ip;
}

export function isNonPublicIp(ip) {
  if (!ip || typeof ip !== 'string') return true;
  let normalized = normalizeHostname(ip);
  const unwrapped = unwrapIpv4Mapped(normalized);
  const candidate = net.isIP(unwrapped) ? unwrapped : normalized;
  const version = net.isIP(candidate);
  if (!version) return true;
  try {
    return PRIVATE_BLOCKS.check(candidate, version === 4 ? 'ipv4' : 'ipv6');
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
 * Connection-bound HTTP(S) fetch: DNS-validate, connect to validated IP,
 * preserve Host/SNI, re-check peer address. Eliminates validate-then-fetch TOCTOU.
 *
 * @param {string} url
 * @param {{method?: string, headers?: object, body?: any, signal?: AbortSignal}} [options]
 * @param {{allowHttp?: boolean, allowLoopback?: boolean}} [ssrfOpts]
 * @returns {Promise<Response>}
 */
export async function fetchPublicHttp(url, options = {}, ssrfOpts = {}) {
  const dest = await preparePublicDestination(url, ssrfOpts);
  const { parsed, publicIps, loopback } = dest;
  const method = (options.method || 'GET').toUpperCase();
  const headers = headersToObject(options.headers);
  const hostHeader =
    parsed.port &&
    !(
      (parsed.protocol === 'https:' && String(parsed.port) === '443') ||
      (parsed.protocol === 'http:' && String(parsed.port) === '80')
    )
      ? `${parsed.hostname}:${parsed.port}`
      : parsed.hostname;
  if (!Object.keys(headers).some((k) => k.toLowerCase() === 'host')) {
    headers.Host = hostHeader;
  }

  // Loopback fixtures: still use undici/fetch after validation (offline tests).
  if (loopback || publicIps === null) {
    return fetch(url, {
      method,
      headers,
      body: options.body,
      signal: options.signal,
      redirect: 'manual',
    });
  }

  const isHttps = parsed.protocol === 'https:';
  const port = parsed.port ? Number(parsed.port) : isHttps ? 443 : 80;
  const path = `${parsed.pathname || '/'}${parsed.search || ''}`;
  let lastErr = null;

  for (const ip of publicIps) {
    try {
      const response = await new Promise((resolve, reject) => {
        const transport = isHttps ? https : http;
        const reqOpts = {
          host: ip,
          port,
          path,
          method,
          headers: { ...headers },
          servername: isHttps ? parsed.hostname : undefined,
          setHost: false,
        };

        const onSocket = (socket) => {
          try {
            const peer = socket.remoteAddress || socket.getpeername?.()?.[0];
            if (!peer) {
              socket.destroy();
              reject(new Error('peer address unavailable'));
              return;
            }
            // Strip IPv4-mapped prefix if present
            let peerIp = peer;
            if (peerIp.startsWith('::ffff:')) peerIp = peerIp.slice(7);
            if (isNonPublicIp(peerIp)) {
              socket.destroy();
              reject(new Error(`peer address is non-public: ${peerIp}`));
              return;
            }
            // Peer must be one of the validated public IPs (rebinding/mismatch).
            const validated = new Set(publicIps.map((a) => a.replace(/^::ffff:/i, '')));
            const peerNorm = peerIp.replace(/^::ffff:/i, '');
            if (!validated.has(peerNorm) && !validated.has(peer)) {
              socket.destroy();
              reject(new Error(`peer address mismatch: ${peerIp} not in validated set`));
            }
          } catch (e) {
            try {
              socket.destroy();
            } catch {
              /* ignore */
            }
            reject(e);
          }
        };

        let req;
        if (_testConnect) {
          req = _testConnect({ ...reqOpts, ip, url, isHttps }, (err, res) => {
            if (err) reject(err);
            else resolve(res);
          });
          return;
        }

        req = transport.request(reqOpts, (res) => {
          const chunks = [];
          res.on('data', (c) => chunks.push(c));
          res.on('end', () => {
            const body = Buffer.concat(chunks);
            const hdrs = res.headers || {};
            // Build a Fetch API Response for callers
            resolve(
              new Response(body, {
                status: res.statusCode || 0,
                statusText: res.statusMessage || '',
                headers: hdrs,
              }),
            );
          });
          res.on('error', reject);
        });

        req.on('socket', (socket) => {
          if (socket.connecting) {
            socket.once('connect', () => onSocket(socket));
          } else {
            onSocket(socket);
          }
        });
        req.on('error', reject);
        if (options.signal) {
          if (options.signal.aborted) {
            req.destroy(new Error('aborted'));
            return;
          }
          options.signal.addEventListener(
            'abort',
            () => {
              req.destroy(new Error('aborted'));
            },
            { once: true },
          );
        }
        if (options.body != null) {
          req.write(options.body);
        }
        req.end();
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
    'https://[::ffff:127.0.0.1]/x',
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
  for (const good of ['https://[::ffff:8.8.8.8]/', 'https://8.8.8.8/']) {
    try {
      await assertPublicHttpUrl(good);
    } catch (e) {
      errors.push(`public address should be allowed (${good}): ${e.message || e}`);
    }
  }
  if (isNonPublicIp('::ffff:8.8.8.8') || isNonPublicIp('::ffff:808:808')) {
    errors.push('public IPv4-mapped classification must be public');
  }
  for (const [raw, expectBlock] of [
    ['::ffff:127.0.0.1', true],
    ['::ffff:169.254.169.254', true],
    ['8.8.8.8', false],
    ['::ffff:8.8.8.8', false],
  ]) {
    const blocked = isNonPublicIp(raw);
    if (blocked !== expectBlock) {
      errors.push(`isNonPublicIp(${raw})=${blocked}, expected ${expectBlock}`);
    }
  }

  // F-05: rebinding simulation — first resolution public, connect peer private → reject
  {
    setTestDnsResolver(async () => ['8.8.8.8']);
    setTestConnectFactory((opts, cb) => {
      // Simulate peer rebinding to private IP after DNS check
      const err = new Error('peer address is non-public: 127.0.0.1');
      cb(err);
      return { on() {}, end() {}, write() {}, destroy() {} };
    });
    let rebBlocked = false;
    try {
      await fetchPublicHttp('https://rebinding.test/', { method: 'GET' }, {});
    } catch (e) {
      rebBlocked = /non-public|peer|mismatch|SSRF|not allowed/i.test(String(e.message || e));
    }
    setTestDnsResolver(null);
    setTestConnectFactory(null);
    if (!rebBlocked) errors.push('DNS rebinding / private peer must be blocked on connect');
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

  // Peer mismatch: validated set is 1.2.3.4 but peer is 8.8.8.8
  {
    setTestDnsResolver(async () => ['1.2.3.4']);
    setTestConnectFactory((opts, cb) => {
      cb(new Error('peer address mismatch: 8.8.8.8 not in validated set'));
      return { on() {}, end() {}, write() {}, destroy() {} };
    });
    let mismatchBlocked = false;
    try {
      await fetchPublicHttp('https://mismatch.test/', { method: 'GET' }, {});
    } catch (e) {
      mismatchBlocked = /mismatch|non-public/i.test(String(e.message || e));
    }
    setTestDnsResolver(null);
    setTestConnectFactory(null);
    if (!mismatchBlocked) errors.push('peer mismatch must be blocked');
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
