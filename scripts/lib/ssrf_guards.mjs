// Public-address validation for Node helpers that accept user-controlled URLs.
// Stdlib-only. Mirrors the threat model of scripts/_ssrf_helpers.py:
// - HTTPS only by default
// - no userinfo
// - blocked hostnames (localhost, cloud metadata names)
// - non-public IPv4/IPv6 literals rejected
// - DNS resolutions must not include non-public addresses
// - call again on every redirect hop

import dns from 'node:dns/promises';
import net from 'node:net';
import { BlockList } from 'node:net';

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

function unwrapIpv4Mapped(ip) {
  // ::ffff:x.x.x.x → evaluate embedded IPv4
  const m = /^:?:ffff:(\d{1,3}(?:\.\d{1,3}){3})$/i.exec(ip);
  if (m) return m[1];
  // :ffff:aabb:ccdd form
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
  // Prefer classifying the embedded IPv4 for mapped addresses so private
  // ::ffff:127.0.0.1 cannot depend on platform IPv6 property quirks.
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
  // WHATWG / some Node versions may leave brackets or IPv4-mapped forms.
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
  // Literal IP (including IPv4-mapped IPv6 in either dotted or hex form).
  if (net.isIP(hostL)) {
    if (isNonPublicIp(hostL)) throw new Error(`non-public IP not allowed: ${hostL}`);
    return [hostL];
  }
  // Fallback: unwrap mapped form then re-check (platform-normalized hostnames).
  const unwrapped = unwrapIpv4Mapped(hostL);
  if (unwrapped !== hostL && net.isIP(unwrapped)) {
    if (isNonPublicIp(unwrapped)) throw new Error(`non-public IP not allowed: ${hostL}`);
    return [unwrapped];
  }
  let records;
  try {
    records = await dns.lookup(hostL, { all: true, verbatim: true });
  } catch (e) {
    throw new Error(`DNS resolution failed for ${hostL}: ${e.message || e}`);
  }
  if (!records || !records.length) {
    throw new Error(`DNS returned no addresses for ${hostL}`);
  }
  const addrs = [];
  const seen = new Set();
  for (const rec of records) {
    const addr = rec.address;
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
 * @param {string} url
 * @param {{allowHttp?: boolean, allowLoopback?: boolean}} [opts]
 * @returns {Promise<string>} normalized URL
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
  // Offline self-tests may opt into loopback fixtures only.
  if (opts.allowLoopback && isLoopbackHost(host)) {
    return url.trim();
  }
  await resolvePublicIps(host);
  return url.trim();
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
  // Public IPv4-mapped literals must classify as public without DNS.
  for (const good of ['https://[::ffff:8.8.8.8]/', 'https://8.8.8.8/']) {
    try {
      await assertPublicHttpUrl(good);
    } catch (e) {
      errors.push(`public address should be allowed (${good}): ${e.message || e}`);
    }
  }
  // Direct classification (does not depend on URL hostname normalization).
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
  if (errors.length) {
    console.error('ssrf_guards.mjs self-test FAILED:');
    for (const e of errors) console.error(`  - ${e}`);
    process.exitCode = 1;
    return 1;
  }
  console.log('ssrf_guards.mjs self-test ok');
  return 0;
}

if (process.argv.includes('--self-test')) {
  selfTest();
}
