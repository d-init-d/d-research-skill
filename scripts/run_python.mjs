import { spawnSync } from 'node:child_process';

const scriptArgs = process.argv.slice(2);
const candidates = process.platform === 'win32'
  ? [['py', ['-3']], ['python', []], ['python3', []]]
  : [['python3', []], ['python', []]];

let lastError = null;

for (const [command, prefixArgs] of candidates) {
  const result = spawnSync(command, [...prefixArgs, ...scriptArgs], {
    stdio: 'inherit',
    shell: false,
  });

  if (result.error) {
    lastError = result.error;
    continue;
  }

  process.exit(result.status ?? 0);
}

if (lastError) {
  console.error(`Unable to find a Python 3 interpreter: ${lastError.message}`);
} else {
  console.error('Unable to find a Python 3 interpreter.');
}

process.exit(1);
