# Anti-Bot Fallback

Use this file when a relevant public source appears to be blocked by an anti-bot layer, JavaScript challenge, captcha, 403, 429, geo block, or repeated browser/fetch failure. The goal is to preserve lawful research coverage without trying to defeat access controls.

This is a fallback chain, not an evasion playbook. Do not use stealth plugins, CAPTCHA solving, residential proxy rotation, leaked cookies, login bypasses, or rate-limit evasion. If the chain cannot reach an equivalent public source, produce a blocker report.

## When this applies

Use this reference only when all are true:

1. The blocked source is relevant to the current research question or evidence gap.
2. The source appears public in intent, but the current tool path cannot access it cleanly.
3. You need the same factual content, record, file, or citation - not private data and not a workaround around authentication.
4. The fallback remains read-only and respects robots, rate limits, and site terms.

Do not use this chain when the blocker is a real permission boundary: login-only content, paywall-only content, private account content, authenticated dashboards, purchased databases, or data the user is not authorized to access. Go straight to `references/blocker-report.md`.

## One chain, in order

Run the chain in this order. Stop as soon as one fallback yields usable evidence from a lawful public source.

1. **Canonical API or raw/static form from the same source.** Try the official API, JSON endpoint, raw file URL, registry API, release asset, sitemap-listed file, or canonical static page for the same record. Examples: GitHub HTML page -> GitHub REST API; PyPI project page -> PyPI JSON; docs page -> raw Markdown in the upstream repo.
2. **Public web archive.** Try `web.archive.org` for the same URL or a nearby canonical URL. Use the archived page only if the timestamp is acceptable for the research question and the archive does not expose private or restricted content.

   ```bash
   python scripts/wayback.py nearest --url <blocked-url> --timestamp <YYYYMMDD>
   ```
3. **Search-engine cache or snippet, if available.** Use cached copies or snippets only as discovery signals unless you can open a stable public cached page and quote it with a URL and timestamp. Do not treat a snippet alone as high-confidence evidence for a final claim.
4. **Fetch-only or no-JavaScript retrieval.** If Playwright hit a challenge, try a normal HTTP fetch, documented feed, sitemap, RSS, or static file path. If fetch is the path that was blocked first, try browser rendering once instead. Do not change identity, spoof fingerprints, or retry aggressively.
5. **Blocker report.** If the first four steps fail, stop. Produce `references/blocker-report.md` with the original URL, blocker type, fallback attempts, visible evidence, and manual retrieval instructions.

Do not loop the chain. One pass is enough. Repeated 403, 429, captcha, or challenge pages mean blocked.

## What to record

Record both positive evidence and failed fallback attempts.

### Positive row

When a fallback works, file the normal evidence row in `templates/evidence-ledger.csv`:

- `claim` is the factual claim supported by the fallback source.
- `source_url` is the fallback URL actually opened.
- `access_method` is `public_api`, `fetch`, `playwright`, `public_file`, or `manual_needed` as appropriate.
- `notes` names the blocked tier-1 source and says which fallback step succeeded.

### Negative row without schema changes

The ledger schema does not have a dedicated `attempt_result` column. Until it does, record failed fallback attempts as low-confidence process rows:

- `claim`: `Fallback attempt did not retrieve usable evidence from <source>.`
- `sub_question`: the gap or source the attempt targeted.
- `source_title`: the blocked or attempted source.
- `source_url`: the attempted URL.
- `source_type`: `unknown` unless the source class is clear.
- `access_method`: the attempted method (`playwright`, `fetch`, `public_api`, `public_file`, `manual_needed`).
- `evidence`: status code, challenge text, timeout, redirect, or archive miss.
- `quote_or_anchor`: selector, screenshot path, response excerpt, or archive timestamp.
- `contradiction`: `none`.
- `confidence`: `low`.
- `notes`: `fallback_result=blocked`, `fallback_result=not-found`, or `fallback_result=refused`; do not use this row as positive evidence in the final answer.

Negative rows are proof of search coverage, not proof that the underlying fact is false.

## Safety stops

Stop immediately and use `references/blocker-report.md` if any fallback would require:

- login, purchase, or account access not provided by the user
- captcha solving or anti-bot evasion
- stealth, proxy rotation, cookie reuse, or identity manipulation
- scraping private or personal data
- ignoring robots or explicit crawl restrictions
- repeated requests after 429 or rate-limit messaging

## Output pattern

When this chain runs, include a short fallback summary in the final answer:

```markdown
## Fallback summary

Original source: <URL>
Blocker: <403 / captcha / JS challenge / 429 / etc.>
Fallback attempted: API -> archive -> cache/snippet -> fetch-only
Evidence recovered from: <URL or none>
Rows recorded: <positive row IDs and negative row IDs>
Manual retrieval needed: <yes/no>
```

## Worked mini-example

Original source: a GitHub repository HTML page returns a challenge page in the browser.

1. Try the GitHub REST API for the same repo.
2. If the API returns the needed `owner`, `description`, `default_branch`, or release metadata, record that API URL as the positive source.
3. Record the challenged HTML page as a negative process row with `fallback_result=blocked`.
4. Do not retry with stealth or proxy settings.

## See also

- `SKILL.md` - workflow entry point and safety boundary.
- `references/fact-verification.md` - deterministic API-first path for atomic facts.
- `references/browser-first-crawl.md` - normal browser-first probing before fallback.
- `references/api-access-workflow.md` - API pagination, rate-limit, and retry guidance.
- `references/evidence-ledger.md` - ledger schema and CSV quoting rules.
- `references/blocker-report.md` - final output when the fallback chain cannot recover evidence.
- `references/safety-and-access-policy.md` - hard access boundaries.
- `templates/evidence-ledger.csv` - row template for positive and negative rows.
