#!/usr/bin/env node
/**
 * Runtime-profile self-test.
 *
 * This deliberately avoids release evidence, CI-only helpers, browser
 * installation, and developer evaluation fixtures.  It verifies the bounded
 * runtime surface that is shipped by the D Research runtime artifact.
 */

import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

const root = process.cwd();
const failures = [];

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: root,
    encoding: 'utf8',
    windowsHide: true,
  });
  if (result.error || result.status !== 0) {
    failures.push(`${command} ${args.join(' ')} exited ${result.status ?? 'error'}: ${result.error?.message || result.stderr || ''}`);
  }
}

function filesWithSuffix(dir, suffix) {
  return readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(suffix))
    .map((entry) => join(dir, entry.name));
}

const packageJson = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'));
if (!packageJson.scripts?.['self-test:runtime']) {
  failures.push('package.json is missing self-test:runtime');
}
const runtimeProjected = packageJson.dResearchArtifactProfile?.name === 'runtime';
if (existsSync(join(root, 'ARTIFACT-MANIFEST.json')) && !runtimeProjected) {
  failures.push('extracted runtime artifact is missing the trusted package projection marker');
}
if (runtimeProjected) {
  for (const forbidden of [
    '.agents',
    '.github',
    'release-evidence',
    join('examples', 'evals', 'quality', 'fixtures', 'hostile'),
  ]) {
    if (existsSync(join(root, forbidden))) failures.push(`runtime contains forbidden path: ${forbidden}`);
  }
}

const commandPathPattern = /(?:^|\s)((?:adapters|agents|docs|examples|references|release-evidence|scripts|templates)\/[A-Za-z0-9_./-]+)/g;
const npmRunPattern = /(?:^|\s)npm(?:\.cmd)?\s+run\s+([A-Za-z0-9:_-]+)/g;
for (const [name, command] of Object.entries(packageJson.scripts || {})) {
  if (runtimeProjected && (name.startsWith('eval:') || ['self-test', 'self-test:source', 'artifact:build', 'artifact:self-test', 'capability:check', 'package:check'].includes(name))) {
    failures.push(`runtime advertises source-only npm script: ${name}`);
  }
  for (const match of command.matchAll(commandPathPattern)) {
    const target = match[1].replace(/[.,;:)]+$/, '');
    if (!existsSync(join(root, target))) failures.push(`${name} points to missing path: ${target}`);
  }
  for (const match of command.matchAll(npmRunPattern)) {
    if (!packageJson.scripts?.[match[1]]) failures.push(`${name} depends on missing npm script: ${match[1]}`);
  }
}

for (const file of [...filesWithSuffix(join(root, 'scripts'), '.mjs'), ...filesWithSuffix(join(root, 'scripts', 'lib'), '.mjs')]) {
  run(process.execPath, ['--check', file]);
}

run(process.execPath, ['scripts/lib/config.mjs', '--self-test']);
run(process.execPath, ['scripts/lib/package_metadata.mjs', '--self-test']);
run(process.execPath, ['scripts/api_fetch.mjs', '--self-test']);
run(process.execPath, ['scripts/lib/http_cache.mjs', '--self-test']);
run(process.execPath, ['scripts/lib/ssrf_guards.mjs', '--self-test']);
run(process.execPath, ['scripts/lib/browser_ssrf.mjs', '--self-test']);
run(process.execPath, ['scripts/web_search.mjs', '--self-test']);

const pythonRunner = process.execPath;
for (const [script, ...args] of [
  ['scripts/package_metadata.py', 'self-test'],
  ['scripts/evidence_ledger.py', 'self-test'],
  ['scripts/wayback.py', 'self-test'],
  ['scripts/run_metadata.py', 'self-test'],
  ['scripts/check_internal_refs.py'],
  ['scripts/check_internal_refs.py', '--decision-tree'],
  ['scripts/check_doc_examples.py'],
  ['scripts/check_node_syntax.py'],
  ['scripts/resource_limits.py', 'self-test'],
]) {
  run(pythonRunner, ['scripts/run_python.mjs', script, ...args]);
}

if (failures.length) {
  console.error('runtime self-test FAILED:');
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log('runtime self-test ok');
