# Reproducibility Checklist

<!-- d-research-checklist:v1 -->

## Contents

- [Provenance](#provenance)
- [Search / discovery](#search--discovery)
- [Data collection](#data-collection)
- [Data processing](#data-processing)
- [Quality assessment](#quality-assessment)
- [Synthesis](#synthesis)
- [Reporting](#reporting)
- [Versioning](#versioning)
- [Tamper-evidence](#tamper-evidence)
- [Repeatability test](#repeatability-test)
- [See also](#see-also)

Use this list before declaring any research output "done". Every item
should be answerable from the artefacts you produced; if any item is
not, the output is not yet reproducible.

## Provenance

- [ ] <!-- DRC-001 --> Every claim in the report has a `claim_id` linking it to a row
      in `evidence-ledger.csv`.
- [ ] <!-- DRC-002 --> Every ledger row has a `source_url` and a `date_accessed` (UTC
      ISO-8601).
- [ ] <!-- DRC-003 --> Every ledger row has a `source_type` from the controlled
      vocabulary (`scripts/evidence_ledger.py validate` passes).
- [ ] <!-- DRC-004 --> Every quote in the report is anchored (page number, heading, or
      DOM selector) in `quote_or_anchor`.
- [ ] <!-- DRC-005 --> The evidence ledger has a tamper-evidence sidecar
      (`scripts/evidence_ledger.py sign`) and the sidecar verifies
      (`scripts/evidence_ledger.py verify`).

## Search / discovery

- [ ] <!-- DRC-006 --> `templates/search-log.csv` records every search query, tool,
      date, results-reviewed count, kept count, and notes.
- [ ] <!-- DRC-007 --> Each query string in the search log is the **exact** string that
      was run (no paraphrasing).
- [ ] <!-- DRC-008 --> If any database was filtered by language, date, or document
      type, the filter is recorded.
- [ ] <!-- DRC-009 --> If the screening was single-screener rather than dual-screener,
      this is disclosed in the report.

## Data collection

- [ ] <!-- DRC-010 --> If APIs were used: every request is logged in
      `templates/api-request-log.csv` with timestamp, URL, status code,
      response time, and rate-limit headers.
- [ ] <!-- DRC-011 --> If a browser adapter was used: the adapter, browser version, and
      user-agent string are recorded.
- [ ] <!-- DRC-012 --> If pagination was used: the cursor / page parameter scheme and
      the stopping condition are documented.
- [ ] <!-- DRC-013 --> If checkpointing was used (large crawls): the checkpoint file
      path and resumption procedure are documented.

## Data processing

- [ ] <!-- DRC-014 --> If a dataset was built, `templates/data-dictionary.csv` describes
      every field, with its source, type, transformation, and example.
- [ ] <!-- DRC-015 --> If cleaning was applied, the cleaning steps are reproducible from
      `scripts/data_clean.py` invocations recorded in the report
      appendix.
- [ ] <!-- DRC-016 --> If deduplication was applied, the merge key and the number of
      duplicates removed are recorded.
- [ ] <!-- DRC-017 --> If transformations changed values (e.g. normalising license
      strings), the mapping table is recorded.

## Quality assessment

- [ ] <!-- DRC-018 --> Every included source has a `confidence` band (`high` / `medium`
      / `low`) in the ledger.
- [ ] <!-- DRC-019 --> If `scripts/score_source.py` was used, the raw rubric output is
      saved next to the ledger.
- [ ] <!-- DRC-020 --> Manual overrides of the rubric output are justified in the
      ledger `notes` field.

## Synthesis

- [ ] <!-- DRC-021 --> Every numbered finding in the report cites at least one
      `claim_id`.
- [ ] <!-- DRC-022 --> Contradictions across sources are surfaced explicitly (do not
      hide divergence).
- [ ] <!-- DRC-023 --> Sub-questions in the report match the sub-questions in the
      original protocol / decomposition.

## Reporting

- [ ] <!-- DRC-024 --> References are formatted in the journal / institution's required
      style (`scripts/citation_render.py render --style <alias>`).
- [ ] <!-- DRC-025 --> The report names every database / tool / version actually used.
- [ ] <!-- DRC-026 --> Blocked or paywalled sources are listed in a "Sources blocked"
      section (see `references/blocker-report.md`), not silently
      dropped.
- [ ] <!-- DRC-027 --> The report states the access policy explicitly (read-only, no
      bypass).

## Versioning

- [ ] <!-- DRC-028 --> The skill version is recorded (e.g. `d-research-skill` git SHA).
- [ ] <!-- DRC-029 --> Each external tool used has a recorded version
      (`pandoc --version`, `playwright --version`, `python3 --version`,
      `node --version`).
- [ ] <!-- DRC-030 --> The CSL style file used (if not the bundled default) has a name
      and source URL recorded.

## Tamper-evidence

- [ ] <!-- DRC-031 --> The evidence ledger is signed with HMAC (`scripts/evidence_ledger.py
      sign`).
- [ ] <!-- DRC-032 --> The signing key is **not** in the repository — it is provided via
      the environment variable named in `--key-env`.
- [ ] <!-- DRC-033 --> The sidecar `.hmac` file is committed alongside the ledger.

## Repeatability test

If a third party were given the work directory, the protocol, and the
HMAC key, could they:

- [ ] <!-- DRC-034 --> Re-run the searches and obtain the same hits (modulo new records)?
- [ ] <!-- DRC-035 --> Verify the ledger sidecar matches (`evidence_ledger.py verify`)?
- [ ] <!-- DRC-036 --> Reproduce the dataset by re-running the cleaning scripts?
- [ ] <!-- DRC-037 --> Re-render references in the original style?

If any answer is "no", document what would block them and fix it before
calling the output reproducible.

## See also

- `references/systematic-review-protocol.md`
- `references/evidence-ledger.md`
- `references/source-quality-rubric.md`
- `references/safety-and-access-policy.md`
- `references/blocker-report.md`
