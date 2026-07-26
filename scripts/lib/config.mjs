// Shared standard-library config loader for D Research Node helpers.
//
// Stdlib only (fs/path). No third-party dependency, no network, no auto-create.
//
// Discovery is intentionally narrow and predictable: with no explicit --config
// path, only `research.config.json` in the chosen working directory is read.
// We deliberately do NOT walk up the filesystem so a helper never silently
// reads a config outside the directory the caller pointed it at. Anything else
// must be passed explicitly via --config <path>.
//
// Precedence is decided by the *caller*: a CLI flag always wins over config,
// and this loader only supplies values the caller did not set explicitly.

import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

export const CONFIG_BASENAME = 'research.config.json';

// Leaf keys whose values must never be printed by --print-effective-config.
const SECRET_KEY_RE =
  /(^|_|\.)(key|token|secret|password|passwd|authorization|auth|cookie|credential|api[_-]?key|access[_-]?token|bearer)($|_|\.)/i;

const REDACTED = '***redacted***';

// Resolve the config path without reading it. Returns an absolute path or null.
export function discoverConfigPath(startDir = process.cwd()) {
  const candidate = path.join(path.resolve(startDir), CONFIG_BASENAME);
  return existsSync(candidate) ? candidate : null;
}

// Load config. Always returns an object; never throws.
//   { config, source, error }
// - explicitPath set + missing         -> error, empty config
// - no explicitPath + none discovered  -> empty config, source null, no error
// - malformed JSON / non-object        -> error, empty config
export function loadConfig({ explicitPath = null, startDir = process.cwd() } = {}) {
  let resolved = null;
  if (explicitPath) {
    resolved = path.resolve(explicitPath);
    if (!existsSync(resolved)) {
      return { config: {}, source: null, error: `config file not found: ${explicitPath}` };
    }
  } else {
    resolved = discoverConfigPath(startDir);
    if (!resolved) {
      return { config: {}, source: null, error: null };
    }
  }

  let text;
  try {
    text = readFileSync(resolved, 'utf8');
  } catch (e) {
    return { config: {}, source: resolved, error: `cannot read config ${resolved}: ${e.message}` };
  }

  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (e) {
    return { config: {}, source: resolved, error: `invalid JSON in config ${resolved}: ${e.message}` };
  }

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { config: {}, source: resolved, error: `config must be a JSON object: ${resolved}` };
  }

  return { config: parsed, source: resolved, error: null };
}

// Typed dotted-path lookup, e.g. getConfigValue(cfg, "api.maxPagesPerEndpoint").
export function getConfigValue(config, dottedKey) {
  if (!dottedKey) return undefined;
  let cur = config;
  for (const part of String(dottedKey).split('.')) {
    if (cur == null || typeof cur !== 'object' || Array.isArray(cur)) return undefined;
    cur = cur[part];
  }
  return cur;
}

// Read a positive integer config value with structured validation.
//   { value, error }  (value is null when absent or invalid)
export function getPositiveIntConfig(config, dottedKey) {
  const raw = getConfigValue(config, dottedKey);
  if (raw === undefined) return { value: null, error: null };
  if (typeof raw !== 'number' || !Number.isSafeInteger(raw) || raw < 1) {
    return { value: null, error: `${dottedKey} must be a positive integer, got ${JSON.stringify(raw)}` };
  }
  return { value: raw, error: null };
}

// Deep copy with secret-looking leaf values replaced, for safe printing.
export function redactConfig(value) {
  if (Array.isArray(value)) return value.map((v) => redactConfig(v));
  if (value && typeof value === 'object') {
    const out = {};
    for (const [k, v] of Object.entries(value)) {
      out[k] = SECRET_KEY_RE.test(k) ? REDACTED : redactConfig(v);
    }
    return out;
  }
  return value;
}

async function selfTest() {
  const os = await import('node:os');
  const { mkdtempSync, writeFileSync, rmSync } = await import('node:fs');
  const errors = [];
  const dir = mkdtempSync(path.join(os.tmpdir(), 'drs-config-'));
  try {
    // No config present -> empty, no error.
    let r = loadConfig({ startDir: dir });
    if (r.source !== null || r.error !== null || Object.keys(r.config).length) {
      errors.push('absent config should return empty with no error');
    }

    // Discovered config.
    writeFileSync(
      path.join(dir, CONFIG_BASENAME),
      JSON.stringify({ api: { maxPagesPerEndpoint: 50 }, headers: { Authorization: 'Bearer x' } }),
      'utf8',
    );
    r = loadConfig({ startDir: dir });
    if (r.error) errors.push(`discovered config should load: ${r.error}`);
    if (getConfigValue(r.config, 'api.maxPagesPerEndpoint') !== 50) {
      errors.push('discovered config value mismatch');
    }

    // Positive int validation.
    if (getPositiveIntConfig(r.config, 'api.maxPagesPerEndpoint').value !== 50) {
      errors.push('positive int reader mismatch');
    }
    const badCfg = { api: { maxPagesPerEndpoint: 0 } };
    if (!getPositiveIntConfig(badCfg, 'api.maxPagesPerEndpoint').error) {
      errors.push('non-positive int must error');
    }

    // Redaction never leaks secret-like values.
    const redacted = redactConfig(r.config);
    if (JSON.stringify(redacted).includes('Bearer x')) {
      errors.push('redactConfig must hide Authorization values');
    }

    // Explicit missing path errors.
    const missing = loadConfig({ explicitPath: path.join(dir, 'nope.json') });
    if (!missing.error) errors.push('explicit missing config must error');

    // Malformed JSON errors, empty config.
    const badPath = path.join(dir, 'bad.json');
    writeFileSync(badPath, '{ not json', 'utf8');
    const bad = loadConfig({ explicitPath: badPath });
    if (!bad.error || Object.keys(bad.config).length) {
      errors.push('malformed JSON must error with empty config');
    }
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }

  if (errors.length) {
    console.error('config.mjs self-test FAILED:');
    for (const e of errors) console.error(`  - ${e}`);
    process.exitCode = 1;
    return 1;
  }
  console.log('config.mjs self-test ok');
  return 0;
}

const _isMain =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (_isMain && process.argv.includes('--self-test')) {
  await selfTest();
}
