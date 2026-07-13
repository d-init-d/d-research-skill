#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
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

function packageFileManifest(files) {
  const canonical = [...files].map(normalize).sort();
  const digest = createHash("sha256")
    .update(JSON.stringify(canonical), "utf8")
    .digest("hex");
  return {
    schema_version: 1,
    algorithm: "sha256",
    file_count: canonical.length,
    paths_sha256: `sha256:${digest}`,
  };
}

function readExpectedManifest() {
  let packageJson;
  try {
    packageJson = JSON.parse(readFileSync(path.join(ROOT, "package.json"), "utf8"));
  } catch (error) {
    fail("cannot parse package.json", [error.message]);
  }
  const manifest = packageJson.dResearchPackageManifest;
  if (
    !manifest ||
    manifest.schema_version !== 1 ||
    manifest.algorithm !== "sha256" ||
    !Number.isSafeInteger(manifest.file_count) ||
    manifest.file_count < 1 ||
    !/^sha256:[0-9a-f]{64}$/.test(manifest.paths_sha256 ?? "")
  ) {
    fail("package.json has an invalid dResearchPackageManifest");
  }
  return manifest;
}

function trackedFiles() {
  if (!existsSync(path.join(ROOT, ".git"))) {
    return null;
  }
  const topLevel = path.resolve(run("git", ["rev-parse", "--show-toplevel"]).trim());
  if (topLevel !== ROOT) {
    fail("repository root does not match the package root", [
      `package root: ${ROOT}`,
      `repository root: ${topLevel}`,
    ]);
  }
  return new Set(
    run("git", ["ls-files", "-z"])
      .split("\0")
      .filter(Boolean)
      .map(normalize),
  );
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

const tracked = trackedFiles();

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

if (tracked) {
  const untracked = fileList.filter((file) => !tracked.has(file));
  if (untracked.length > 0) {
    fail("package contains files that are not tracked by Git", untracked.sort());
  }
}

const forbidden = fileList.filter(isForbidden);
if (forbidden.length > 0) {
  fail("package contains forbidden local, credential, or evidence artifacts", forbidden.sort());
}

if (tracked) {
  const required = [...tracked].filter(
    (file) =>
      PUBLISH_TOP_LEVEL.has(file) || PUBLISH_ROOTS.some((prefix) => file.startsWith(prefix)),
  );
  const missing = required.filter((file) => !packed.has(file));
  if (missing.length > 0) {
    fail("package omits tracked runtime or documentation files", missing.sort());
  }
}

if (!packed.has("SKILL.md") || !packed.has("agents/openai.yaml")) {
  fail("package is missing the skill entry point or agent metadata");
}

const expectedManifest = readExpectedManifest();
const actualManifest = packageFileManifest(fileList);
if (
  actualManifest.schema_version !== expectedManifest.schema_version ||
  actualManifest.algorithm !== expectedManifest.algorithm ||
  actualManifest.file_count !== expectedManifest.file_count ||
  actualManifest.paths_sha256 !== expectedManifest.paths_sha256
) {
  fail("package file list does not match the committed manifest", [
    `expected: ${JSON.stringify(expectedManifest)}`,
    `actual: ${JSON.stringify(actualManifest)}`,
  ]);
}

process.stdout.write(
  `package_manifest_check ok (mode=${tracked ? "git" : "archive"}, packed=${packed.size})\n`,
);
