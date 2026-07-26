#!/usr/bin/env node
/** Resolve D Research package identity without embedding release numbers. */

import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const PACKAGE_URL = new URL('../../package.json', import.meta.url);
const VERSION_RE = /^\d+\.\d+\.\d+(?:-rc\.\d+)?$/;
const REPOSITORY_URL = 'https://github.com/d-init-d/d-research-skill';
let cachedVersion;

export function packageVersion({ strict = false } = {}) {
  if (cachedVersion) return cachedVersion;
  try {
    const pkg = JSON.parse(readFileSync(PACKAGE_URL, 'utf8'));
    if (pkg.name !== 'd-research-skill-tools' || !VERSION_RE.test(pkg.version)) {
      throw new Error('package.json has an invalid D Research identity');
    }
    cachedVersion = pkg.version;
    return cachedVersion;
  } catch (error) {
    if (strict) throw error;
    return 'unknown';
  }
}

export function packageUserAgent(component) {
  const suffix = component ? `; ${String(component).trim()}` : '';
  return `d-research-skill/${packageVersion()} (${REPOSITORY_URL}${suffix})`;
}

export function browserUserAgent() {
  return `Mozilla/5.0 (compatible; DResearchBot/${packageVersion()}; +${REPOSITORY_URL})`;
}

function selfTest() {
  const version = packageVersion({ strict: true });
  if (!packageUserAgent('self-test').includes(`/${version}`)) {
    throw new Error('package User-Agent does not contain the canonical version');
  }
  if (!browserUserAgent().includes(`DResearchBot/${version}`)) {
    throw new Error('browser User-Agent does not contain the canonical version');
  }
  process.stdout.write('package_metadata.mjs self-test ok\n');
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (process.argv[2] !== '--self-test') {
    process.stderr.write('usage: node scripts/lib/package_metadata.mjs --self-test\n');
    process.exit(2);
  }
  selfTest();
}
