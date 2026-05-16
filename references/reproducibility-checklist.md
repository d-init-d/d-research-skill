# Reproducibility Checklist

Use this list before declaring any research output "done". Every item
should be answerable from the artefacts you produced; if any item is
not, the output is not yet reproducible.

## Provenance

- [ ] Every claim in the report has a `claim_id` linking it to a row
      in `evidence-ledger.csv`.
- [ ] Every ledger row has a `source_url` and a `date_accessed` (UTC
      ISO-8601).
- [ ] Every ledger row has a `source_type` from the controlled
      vocabulary (`scripts/evidence_ledger.py validate` passes).
- [ ] Every quote in the report is anchored (page number, heading, or
      DOM selector) in `quote_or_anchor`.
- [ ] The evidence ledger has a tamper-evidence sidecar
      (`scripts/evidence_ledger.py sign`) and the sidecar verifies
      (`scripts/evidence_ledger.py verify`).

## Search / discovery

- [ ] `templates/search-log.csv` records every search query, tool,
      date, results-reviewed count, kept count, and notes.
- [ ] Each query string in the search log is the **exact** string that
      was run (no paraphrasing).
- [ ] If any database was filtered by language, date, or document
      type, the filter is recorded.
- [ ] If the screening was single-screener rather than dual-screener,
      this is disclosed in the report.

## Data collection

- [ ] If APIs were used: every request is logged in
      `templates/api-request-log.csv` with timestamp, URL, status code,
      response time, and rate-limit headers.
- [ ] If a browser adapter was used: the adapter, browser version, and
      user-agent string are recorded.
- [ ] If pagination was used: the cursor / page parameter scheme and
      the stopping condition are documented.
- [ ] If checkpointing was used (large crawls): the checkpoint file
      path and resumption procedure are documented.

## Data processing

- [ ] If a dataset was built, `templates/data-dictionary.csv` describes
      every field, with its source, type, transformation, and example.
- [ ] If cleaning was applied, the cleaning steps are reproducible from
      `scripts/data_clean.py` invocations recorded in the report
      appendix.
- [ ] If deduplication was applied, the merge key and the number of
      duplicates removed are recorded.
- [ ] If transformations changed values (e.g. normalising license
      strings), the mapping table is recorded.

## Quality assessment

- [ ] Every included source has a `confidence` band (`high` / `medium`
      / `low`) in the ledger.
- [ ] If `scripts/score_source.py` was used, the raw rubric output is
      saved next to the ledger.
- [ ] Manual overrides of the rubric output are justified in the
      ledger `notes` field.

## Synthesis

- [ ] Every numbered finding in the report cites at least one
      `claim_id`.
- [ ] Contradictions across sources are surfaced explicitly (do not
      hide divergence).
- [ ] Sub-questions in the report match the sub-questions in the
      original protocol / decomposition.

## Reporting

- [ ] References are formatted in the journal / institution's required
      style (`scripts/citation_render.py render --style <alias>`).
- [ ] The report names every database / tool / version actually used.
- [ ] Blocked or paywalled sources are listed in a "Sources blocked"
      section (see `references/blocker-report.md`), not silently
      dropped.
- [ ] The report states the access policy explicitly (read-only, no
      bypass).

## Versioning

- [ ] The skill version is recorded (e.g. `d-research-skill` git SHA).
- [ ] Each external tool used has a recorded version
      (`pandoc --version`, `playwright --version`, `python3 --version`,
      `node --version`).
- [ ] The CSL style file used (if not the bundled default) has a name
      and source URL recorded.

## Tamper-evidence

- [ ] The evidence ledger is signed with HMAC (`scripts/evidence_ledger.py
      sign`).
- [ ] The signing key is **not** in the repository — it is provided via
      the environment variable named in `--key-env`.
- [ ] The sidecar `.hmac` file is committed alongside the ledger.

## Repeatability test

If a third party were given the work directory, the protocol, and the
HMAC key, could they:

- [ ] Re-run the searches and obtain the same hits (modulo new records)?
- [ ] Verify the ledger sidecar matches (`evidence_ledger.py verify`)?
- [ ] Reproduce the dataset by re-running the cleaning scripts?
- [ ] Re-render references in the original style?

If any answer is "no", document what would block them and fix it before
calling the output reproducible.

## See also

- `references/systematic-review-protocol.md`
- `references/evidence-ledger.md`
- `references/source-quality-rubric.md`
- `references/safety-and-access-policy.md`
- `references/blocker-report.md`
