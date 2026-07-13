import { spawnSync } from 'node:child_process';

const scriptArgs = process.argv.slice(2);
const configured = [process.env.D_RESEARCH_PYTHON, process.env.PYTHON]
  .filter((value) => typeof value === 'string' && value.trim() !== '')
  .map((value) => [value.trim(), []]);
const defaults = process.platform === 'win32'
  ? [['py', ['-3']], ['python', []], ['python3', []]]
  : [['python3', []], ['python', []]];
const candidates = [];

for (const candidate of [...configured, ...defaults]) {
  const key = JSON.stringify(candidate);
  if (!candidates.some((existing) => JSON.stringify(existing) === key)) {
    candidates.push(candidate);
  }
}

const failures = [];

for (const [command, prefixArgs] of candidates) {
  const probe = spawnSync(
    command,
    [
      ...prefixArgs,
      '-c',
      'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)',
    ],
    {
      stdio: 'ignore',
      shell: false,
      windowsHide: true,
    },
  );

  if (probe.error || probe.status !== 0) {
    const detail = probe.error?.message ?? `probe exited ${probe.status ?? 'without status'}`;
    failures.push(`${command}: ${detail}`);
    continue;
  }

  const result = spawnSync(command, [...prefixArgs, ...scriptArgs], {
    stdio: 'inherit',
    shell: false,
    windowsHide: true,
  });

  if (result.error) {
    failures.push(`${command}: ${result.error.message}`);
    continue;
  }

  process.exit(result.status ?? 0);
}

console.error('Unable to find a working Python >=3.10 interpreter.');
if (failures.length > 0) {
  console.error(failures.map((failure) => `  - ${failure}`).join('\n'));
}
console.error('Set D_RESEARCH_PYTHON to an explicit interpreter path.');

process.exit(1);
