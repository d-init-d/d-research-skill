#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const PUBLISH_ROOTS = [
  "adapters/",
  "agents/",
  "docs/",
  "examples/",
  "references/",
  "scripts/",
  "templates/",
];
const PUBLISH_TOP_LEVEL = new Set([
  "AGENTS.md",
  "CHANGELOG.md",
  "CONTRIBUTING.md",
  "LICENSE",
  "README.md",
  "README.vi.md",
  "SKILL.md",
  "package.json",
  "pyproject.toml",
  "research.config.example.json",
]);
const FORBIDDEN_PREFIXES = [
  ".agents/",
  ".git/",
  ".github/",
  ".playwright-mcp/",
  "mcps/",
  "node_modules/",
  "release-evidence/",
  "research-output/",
];
const FORBIDDEN_BASENAMES = new Set([
  ".env",
  ".npmrc",
  "id_dsa",
  "id_ed25519",
  "id_rsa",
]);
const FORBIDDEN_SUFFIXES = [".key", ".log", ".pem", ".pfx", ".tgz"];

function fail(message, details = []) {
  process.stderr.write(`package_manifest_check FAILED: ${message}\n`);
  for (const detail of details) {
    process.stderr.write(`  - ${detail}\n`);
  }
  process.exit(1);
}

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: ROOT,
    encoding: "utf8",
    env: { ...process.env, npm_config_update_notifier: "false" },
    windowsHide: true,
  });
  if (result.error) {
    fail(`cannot execute ${command}`, [result.error.message]);
  }
  if (result.status !== 0) {
    fail(`${command} exited with status ${result.status}`, [
      result.stderr.trim() || result.stdout.trim() || "no diagnostic output",
    ]);
  }
  return result.stdout;
}

function runNpm(args) {
  const npmExecPath = process.env.npm_execpath;
  if (npmExecPath) {
    return run(process.execPath, [npmExecPath, ...args]);
  }
  if (process.platform === "win32") {
    return run(process.env.ComSpec || "cmd.exe", [
      "/d",
      "/s",
      "/c",
      "npm.cmd",
      ...args,
    ]);
  }
  return run("npm", args);
}

function normalize(value) {
  return String(value).replaceAll("\\", "/").replace(/^\.\//, "");
}

function isForbidden(file) {
  const normalized = normalize(file);
  const basename = normalized.split("/").at(-1).toLowerCase();
  return (
    FORBIDDEN_PREFIXES.some(
      (prefix) => normalized === prefix.slice(0, -1) || normalized.startsWith(prefix),
    ) ||
    FORBIDDEN_BASENAMES.has(basename) ||
    basename.startsWith(".env.") ||
    FORBIDDEN_SUFFIXES.some((suffix) => basename.endsWith(suffix))
  );
}

const tracked = new Set(
  run("git", ["ls-files", "-z"])
    .split("\0")
    .filter(Boolean)
    .map(normalize),
);

let payload;
try {
  payload = JSON.parse(
    runNpm(["pack", "--dry-run", "--json", "--ignore-scripts"]),
  );
} catch (error) {
  fail("npm pack did not return valid JSON", [error.message]);
}

const manifest = Array.isArray(payload) ? payload[0] : undefined;
if (!manifest || !Array.isArray(manifest.files)) {
  fail("npm pack response is missing files[]");
}

const fileList = manifest.files.map((entry) => normalize(entry?.path));
const packed = new Set(fileList);
if (packed.size !== fileList.length) {
  fail("npm pack returned duplicate file paths");
}

const untracked = fileList.filter((file) => !tracked.has(file));
if (untracked.length > 0) {
  fail("package contains files that are not tracked by Git", untracked.sort());
}

const forbidden = fileList.filter(isForbidden);
if (forbidden.length > 0) {
  fail("package contains forbidden local, credential, or evidence artifacts", forbidden.sort());
}

const required = [...tracked].filter(
  (file) =>
    PUBLISH_TOP_LEVEL.has(file) || PUBLISH_ROOTS.some((prefix) => file.startsWith(prefix)),
);
const missing = required.filter((file) => !packed.has(file));
if (missing.length > 0) {
  fail("package omits tracked runtime or documentation files", missing.sort());
}

if (!packed.has("SKILL.md") || !packed.has("agents/openai.yaml")) {
  fail("package is missing the skill entry point or agent metadata");
}

process.stdout.write(
  `package_manifest_check ok (tracked=${tracked.size}, packed=${packed.size})\n`,
);
