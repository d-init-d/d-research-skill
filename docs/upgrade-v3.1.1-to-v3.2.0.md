# Upgrade guide: v3.1.1 to v3.2.0

This guide upgrades a v3.1.1 research workspace to the v3.2 schema without
silently discarding tasks, blockers, outputs, execution assignments, or custom
gates. v3.2 remains compatible with v1 plans until v4, but migration is required
before relying on the new synthesis/release gates.

## Before upgrading

- Use Python 3.10 or newer and Node.js 18 or newer.
- Install the exact Node dependency set with `npm ci`.
- Keep the source workspace under version control or make an independent copy.
- Do not delete the old plan or its ledger. In-place migration creates a
  byte-for-byte `research-plan.json.bak` before replacing the plan.
- Set `D_RESEARCH_LEDGER_KEY` only when signing/verifying the real ledger; never
  place the key in the workspace or command history.

## Bash

Set the installed skill path, then enter the v3.1.1 workspace:

```bash
export D_RESEARCH_HOME=/absolute/path/to/d-research
cd /absolute/path/to/research-workspace
python3 "$D_RESEARCH_HOME/scripts/research_plan.py" migrate \
  --file research-plan.json --in-place
```

The command must:

- create `research-plan.json.bak` with the exact original bytes;
- set `schema_version` to `2.0`;
- infer `tasks[].phase` (`research` or `synthesis`);
- replace standard gates with the canonical v3.2 definitions while preserving
  custom gates;
- revoke the old approval; and
- remove the stale rendered `PLAN.md`.

Create any v3.2 workspace paths missing from an older hand-built workspace:

```bash
mkdir -p research-output/notes research-output/sections
test -f evidence-ledger.csv || \
  cp "$D_RESEARCH_HOME/templates/evidence-ledger.csv" evidence-ledger.csv
```

Render, validate, and approve the migrated plan again:

```bash
python3 "$D_RESEARCH_HOME/scripts/research_plan.py" check \
  --file research-plan.json
python3 "$D_RESEARCH_HOME/scripts/research_plan.py" render \
  --file research-plan.json
python3 "$D_RESEARCH_HOME/scripts/research_plan.py" gate \
  --file research-plan.json --gate plan_ready
python3 "$D_RESEARCH_HOME/scripts/research_plan.py" approve \
  --file research-plan.json --by "Reviewer name"
python3 "$D_RESEARCH_HOME/scripts/research_plan.py" gate \
  --file research-plan.json --gate execute_ready
```

## PowerShell

```powershell
$DResearchHome = "C:\absolute\path\to\d-research"
Set-Location "C:\absolute\path\to\research-workspace"
python "$DResearchHome\scripts\research_plan.py" migrate `
  --file research-plan.json --in-place

New-Item -ItemType Directory -Force research-output\notes | Out-Null
New-Item -ItemType Directory -Force research-output\sections | Out-Null
if (-not (Test-Path -LiteralPath evidence-ledger.csv)) {
  Copy-Item -LiteralPath "$DResearchHome\templates\evidence-ledger.csv" `
    -Destination evidence-ledger.csv
}

python "$DResearchHome\scripts\research_plan.py" check `
  --file research-plan.json
python "$DResearchHome\scripts\research_plan.py" render `
  --file research-plan.json
python "$DResearchHome\scripts\research_plan.py" gate `
  --file research-plan.json --gate plan_ready
python "$DResearchHome\scripts\research_plan.py" approve `
  --file research-plan.json --by "Reviewer name"
python "$DResearchHome\scripts\research_plan.py" gate `
  --file research-plan.json --gate execute_ready
```

## Verify the migration

Compare the backup and migrated plan. The source task set must be unchanged
except for additive `phase` fields; standard gates and approval are expected to
change.

```bash
python3 "$D_RESEARCH_HOME/scripts/research_plan.py" status \
  --file research-plan.json
python3 "$D_RESEARCH_HOME/scripts/evidence_ledger.py" validate \
  --file evidence-ledger.csv
```

If the ledger was already signed, verify it with the original key. Migration
does not modify the ledger, so a signature failure is a hard stop:

```bash
python3 "$D_RESEARCH_HOME/scripts/evidence_ledger.py" verify \
  --file evidence-ledger.csv --key-env D_RESEARCH_LEDGER_KEY
```

Before synthesis, populate and complete the reproducibility checklist, finish
all research-phase task outputs, and run `synthesize_ready`. Before release,
finish synthesis tasks, render/lint the declared report, ensure 100% claim
coverage, and run `release_ready`.

## Committed upgrade fixture

`examples/fixtures/v3.1.1-workspace/` is the canonical pre-upgrade fixture. The
`research_plan.py self-test` copies it to a temporary directory, performs an
in-place migration, verifies the exact backup, checks lossless task/blocker/
output/execution preservation, confirms synthesis-phase inference and custom
gate preservation, removes the stale plan, scaffolds required paths, renders,
re-approves, and passes `execute_ready`.

Run the same regression locally:

```bash
python3 scripts/research_plan.py self-test
```

## Rollback

If any verification fails, stop. Preserve the failed migrated file for
diagnosis, then restore the exact backup only after confirming both paths:

```bash
cp research-plan.json.bak research-plan.json
```

```powershell
Copy-Item -LiteralPath research-plan.json.bak -Destination research-plan.json
```

Do not promote v3.2.0 stable solely because this migration passes. The default
release path requires live Tier-1/Tier-2 dogfood, independent review, and
GitHub-verified tags. For v3.2.0 only, the policy frozen in v3.2.0-rc.3 records a
repository-owner waiver for those three external assurances plus the candidate
tag signature. It substitutes no synthetic scores or reviews: a strict
maintainer record must bind the exact RC commit, annotated tag object, and
SHA-256 of every required local verification result. Annotated tags, candidate
ancestry, successful full CI for the exact tagged SHA, executable metadata
freeze, source-archive replay, checksum verification, and provenance attestation
remain non-waivable. Copying otherwise valid artifacts from another revision
fails closed. Code changes after the candidate tag require a new RC.
