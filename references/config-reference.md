# Configuration reference

## research.config.json fields

If a project has `research.config.json`, obey it. Otherwise use `research.config.example.json` defaults.

Important config fields:
- browser.default
- browser.timeoutMs
- crawl.maxDepth
- crawl.maxPagesPerDomain
- crawl.maxTotalPages
- crawl.delayMs
- crawl.respectRobots
- research.intake.enabled
- research.intake.emitClassificationCard
- research.intake.multiLabel
- research.intake.askOnSafetyOrOutputAmbiguity
- research.intake.defaultToConservativeBranch
- research.requireEvidenceLedger
- research.requireContradictionPass
- research.executionGates.enabled
- research.executionGates.lowRecallGuard
- research.executionGates.noSingleBasinStop
- research.executionGates.finalVerificationGate
- research.executionGates.subagentsOptional
- research.executionGates.minIndependentBasinsForCompleteness
- researchPlan.context.mainContextLength
- researchPlan.context.taskBudgetRatio
- researchPlan.context.writeFindingsImmediately
- researchPlan.subagents.slots[].id
- researchPlan.subagents.slots[].agent
- researchPlan.subagents.slots[].contextLength
- researchPlan.subagents.slots[].maxParallel
- researchPlan.workspace.baseDir
- researchPlan.workspace.nameTemplate
- researchPlan.workspace.fallbackToCwdOnError
- researchPlan.finalResponse.reportWorkspacePath
- access.allowLoginWithUserPermission
- access.allowPaywalledSources
- access.allowCaptchaSolving
- access.allowStealthEvasion
- api.defaultDelayMs
- api.maxRetries
- api.respectRateLimitHeaders
- database.queryTimeoutMs
- database.maxResultRows
- database.readOnly
- citation.defaultFormat
- citation.enrichFromCrossRef
- monitoring.enabled
- monitoring.defaultIntervalMinutes
- processing.autoClean
- processing.detectOutliers
- largeScale.checkpointEveryN
- largeScale.adaptiveRateLimit

Default access policy is conservative and read-only.

`access.allowCaptchaSolving` and `access.allowStealthEvasion` are compatibility
keys that accept only `false`. A value of `true` is a hard validation failure;
captcha solving and stealth/evasion are never allowed.

## Resource-limit overrides

Conservative defaults live in `scripts/resource_limits.py`. Set the matching
`D_RESEARCH_*` environment variable for automation, or prefer the explicit CLI
flag for an individual invocation. Every value must be positive and finite.

| Scope | Environment | CLI flag |
|---|---|---|
| HTTP/browser bytes | `D_RESEARCH_HTTP_MAX_BYTES` | `api_fetch.mjs` and `web_search.mjs` cap HTTP bodies; `playwright_probe/extract/crawl.mjs` use `--max-response-bytes` as the per-response and extracted-output ceiling, with additional aggregate/request-count guards; Python extraction helpers use `--max-http-bytes` where exposed |
| HTTP deadline | `D_RESEARCH_HTTP_TIMEOUT_SEC` | Python helpers `--http-timeout-sec` where exposed; `web_search.mjs --timeout-ms` |
| Local input file | `D_RESEARCH_DOWNLOAD_MAX_BYTES` | `--max-file-bytes` |
| Excel cells / column | `D_RESEARCH_EXCEL_MAX_CELLS`, `D_RESEARCH_EXCEL_MAX_COL` | `--max-excel-cells`, `--max-excel-column-index` |
| XLSX expansion | `D_RESEARCH_XLSX_MAX_UNCOMPRESSED`, `D_RESEARCH_XLSX_MAX_COMPRESSION_RATIO` | `--max-xlsx-uncompressed-bytes`, `--max-xlsx-compression-ratio` |
| PDF pages / bytes | `D_RESEARCH_PDF_MAX_PAGES`, `D_RESEARCH_PDF_MAX_BYTES` | `--max-pdf-pages`, `--max-pdf-bytes` |
| OCR pages / pixels / image bytes | `D_RESEARCH_OCR_MAX_PAGES`, `D_RESEARCH_OCR_MAX_PIXELS`, `D_RESEARCH_OCR_MAX_IMAGE_BYTES` | `--max-ocr-pages`, `--max-ocr-pixels`, `--max-ocr-image-bytes` |
| Subprocess time / output | `D_RESEARCH_SUBPROCESS_TIMEOUT_SEC`, `D_RESEARCH_SUBPROCESS_MAX_OUTPUT_BYTES` | `--subprocess-timeout-sec`, `--max-subprocess-output-bytes` |
| HTML tables | `D_RESEARCH_TABLE_MAX_ROWS`, `D_RESEARCH_TABLE_MAX_CELLS` | `--max-table-rows`, `--max-table-cells` |
| Wayback / social response | `D_RESEARCH_WAYBACK_MAX_BYTES`, `D_RESEARCH_SOCIAL_MAX_BYTES` | `--max-wayback-bytes`, `--max-social-bytes` |

Limit violations emit a structured blocker, return exit code `3`, and write an
`incomplete` metadata sidecar when the command has an output path. They never
silently truncate and label the result complete.

For long-horizon research, `researchPlan.finalResponse.reportWorkspacePath` defaults to `true`; always tell the user the workspace path where the plan, ledger, notes, sections, report, and checklist were written.


See also: research.config.example.json.
