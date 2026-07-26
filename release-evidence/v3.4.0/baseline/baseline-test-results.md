# D Research v3.4.0 — baseline freeze (Phase D0)

Frozen from the pre-upgrade tree before any behavior change.

- Baseline branch point: `main` @ `f097505c1f3a76428d381581c2ac9310553b6823`
- Baseline tag: `v3.3.0`
- `package.json` / `pyproject.toml` version: `3.3.0`
- Feature branch: `upgrade/d-research-v3.4.0`
- Toolchain used for capture: Node `v24.14.0`, Python `3.11.15`, Windows 11

## D0.2 baseline suite results

| Command | Result | Notes |
|---|---|---|
| `npm run self-test:node` | PASS | api_fetch / http_cache / ssrf_guards / browser_ssrf / web_search self-tests + package_manifest_check (207 files) |
| `npm run self-test:python` | PASS | all Python self-tests, `check_contract ok (version=3.3.0, skill_lines=312)`, resource_limits |
| `npm run refs:check` | PASS | all backticked internal refs resolve |
| `npm run refs:check:decision-tree` | PASS | every `references/*.md` reachable from decision tree |
| `npm run package:check` | PASS | `mode=git, packed=207` |
| `npm run acceptance` | 32 PASS / 2 FAIL | see pre-existing environment failures below |
| `npm pack --dry-run` | 207 files, 3.4 MB unpacked | shasum `964c80308af97bb665775244d62f3ed09988722c` |

## Pre-existing environment failures (NOT introduced by this upgrade)

Two acceptance cases fail in this environment **only because a real Chromium
browser is not installed** (`node_modules` absent; the plan forbids
auto-installing browsers). Both route through `browser_smoke_result()`:

- `04_robots_disallow_no_extract` — needs `npm run browser:smoke` (chromium).
- `27_real_chromium_smoke` — needs a real chromium launch.

On CI with Playwright chromium installed these pass. They are recorded here so
they are never mistaken for a regression caused by the v3.4.0 changes. The
monotonic gate treats "was already failing at baseline for an environmental
reason" as out of scope; no code path for these was modified.

## Capability baseline

`capability-baseline.json` (captured by `capability_baseline.py capture`) freezes
the public surface: 111 npm scripts, 28 route ids, 52 references, the
scripts/templates inventories, ledger header sizes `[14, 19, 22, 23, 37]`,
record types `[blocker, claim, lead, process]`, HMAC signature
`d-research-skill/hmac-sha256/v1`, and default `api_fetch.maxPages = 10`.

Every later phase must satisfy:

```
python release-evidence/v3.4.0/baseline/capability_baseline.py \
  check --baseline release-evidence/v3.4.0/baseline/capability-baseline.json
```

which fails if any command/route/reference/script/template disappears, a ledger
header size or record type is dropped, the signature/canonicalization identifier
changes, or a recorded default changes without a caller opt-in.
