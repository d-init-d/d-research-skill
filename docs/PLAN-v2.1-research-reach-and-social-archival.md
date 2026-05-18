# PLAN v2.1 — Research Reach + Social Archival Upgrade

> **Status:** Draft — not yet implemented
> **Owner:** Repo maintainer
> **Target version:** v2.1.0 (skill), 0.3.0 (npm package)
> **Estimate:** ~19–24 working hours, split across 3 PRs
> **Audience for this doc:** Agents executing this plan, contributors picking up an in-flight feature

This plan extends `d-research-skill` along five concrete capability gaps identified during the v2.0 audit:

1. PDF extraction tooling (currently documented but no script)
2. Wayback Machine integration (anti-bot fallback chain promises it, no script)
3. Wikidata / entity disambiguation (manual today, hurts `references/person-aggregation.md` and `references/fact-verification.md`)
4. Free search engine adapter with concrete patterns (current `adapters/web-search-only.md` is too abstract)
5. Public social-media archival workflow — **expanded** to cover mainstream consumer platforms (X, Facebook, Instagram, TikTok, YouTube) on top of the original developer-leaning set (Reddit, Hacker News, Mastodon, Bluesky, Lemmy)

The skill is for both developers AND general users (researchers, journalists, students, hobbyists). The social section is rewritten with that audience in mind: every claim sourced from social media must ship with a verifiability label, and the agent must explain that label in plain language, not jargon.

---

## Conventions for every new script and reference

These match the existing repo patterns (see `CONTRIBUTING.md`):

- `#!/usr/bin/env python3` or `#!/usr/bin/env node` shebang, executable bit set
- Subcommand-style CLI (`<verb> [args]`, plus `self-test`)
- **Stdlib-only** for Python where feasible. When a system binary is required (e.g. `pdftotext`, `pandoc`), shell out and degrade gracefully if missing — same pattern as `scripts/citation_render.py`
- Every script ships an offline `self-test` that exits 0 on pass
- Wire the new self-test into the chained `npm run self-test` script in `package.json`
- Add an `npm run <name>` shortcut in `package.json`
- Update `SKILL.md` "Optional bundled scripts" list AND the relevant decision-tree branch
- Update `AGENTS.md` if data-access layers or adapters change
- Update `.agents/skills/testing-scripts/SKILL.md` to list the new self-test
- Update README script and reference counts when totals change

---

## FEATURE 1 — PDF extraction

### 1.1 Technical decision

Pure stdlib cannot parse PDF reliably. Two complementary backends:

| Backend | Use for | Hard dep |
|---|---|---|
| `pdftotext` / `pdfinfo` (poppler-utils) | text + metadata | Required |
| `pdfplumber` (optional pip dep) | tables | Optional, soft fail |

Same shell-out pattern as `scripts/citation_render.py` (which depends on `pandoc`).

### 1.2 Files to create

```text
scripts/pdf_extract.py
references/pdf-extraction.md           (new — ~100 lines)
```

### 1.3 Subcommands for pdf_extract.py

- `text --in <pdf> [--out <txt>]` — full text via `pdftotext`
- `meta --in <pdf> [--out <json>]` — title, author, dates, page count via `pdfinfo`
- `tables --in <pdf> --out-dir <dir>` — one CSV per detected table; skip cleanly if `pdfplumber` is missing and emit a warning
- `to-ledger --in <pdf> --url <source-url> --out-row <csv>` — emit a single row in `templates/evidence-ledger.csv` format
- `self-test` — generate or include a tiny test PDF, run all four subcommands offline, validate output

### 1.4 Files to update

- `references/data-extraction-toolbox.md` — add a "PDF" section pointing at the new script
- `references/extraction-methods.md` — bullet for PDF extraction
- `SKILL.md` decision tree — branch "If the user asks to extract structured data" should now mention PDF explicitly
- `.github/workflows/lint-and-self-test.yml` — install poppler-utils alongside pandoc:
  ```yaml
  - name: Install pandoc and poppler-utils
    run: |
      sudo apt-get update
      sudo apt-get install -y pandoc poppler-utils
  ```

### 1.5 Test plan

- Self-test offline: ship a tiny test PDF (≤10 KB) under `examples/fixtures/` or generate at runtime, exercise all four subcommands
- Manual smoke: one arXiv preprint and one government PDF (e.g. an SEC filing)

### 1.6 Estimate

2–3 hours.

---

## FEATURE 2 — Wayback Machine integration

### 2.1 Technical decision

Stdlib `urllib.request` + `json`. No API key required for read endpoints; Save Page Now has a public (rate-limited) endpoint.

### 2.2 Files to create

```text
scripts/wayback.py
references/wayback-archive.md          (new — ~80 lines)
```

### 2.3 Subcommands for wayback.py

- `lookup --url <u> [--from YYYYMMDD] [--to YYYYMMDD] [--limit N]` — list snapshots via CDX API (`http://web.archive.org/cdx/search/cdx`)
- `nearest --url <u> --timestamp YYYYMMDD` — closest snapshot (`http://archive.org/wayback/available`)
- `save --url <u>` — submit to Save Page Now (`https://web.archive.org/save/<u>`); respect ~15 req/min etiquette, exponential backoff on 429
- `diff --url <u> --t1 YYYYMMDD --t2 YYYYMMDD` — fetch both snapshots, hash visible content, report whether content changed
- `self-test` — spin up a local stdlib `http.server`, return mock CDX/Memento JSON, validate parsing offline

### 2.4 Files to update

- `references/anti-bot-fallback.md` — replace prose "use a public web archive" with concrete `scripts/wayback.py nearest --url <u> --timestamp <t>` call
- `references/monitoring-change-detection.md` — add a "compare via Wayback snapshots" pattern using `wayback.py diff`
- `SKILL.md` "Optional bundled scripts" — add wayback.py
- `package.json` — add `wayback:lookup`, `wayback:save`, `wayback:diff` shortcuts

### 2.5 Test plan

- Self-test offline with mocked HTTP
- Manual smoke: query a stable URL like `https://www.python.org`, run `nearest --timestamp 20200101`

### 2.6 Estimate

2 hours.

---

## FEATURE 3 — Wikidata / entity disambiguation

### 3.1 Technical decision

Stdlib HTTP. Public SPARQL endpoint at `https://query.wikidata.org/sparql`. Wikimedia policy requires a User-Agent header containing a contact email — bake that into the script and document it.

### 3.2 Files to create

```text
scripts/wikidata.py
adapters/wikidata.md                   (new — ~70 lines)
```

### 3.3 Subcommands for wikidata.py

- `search --term "<query>" [--type person|org|product|place] [--limit N]` — `wbsearchentities` API; returns list of `{Q-id, label, description, aliases}`
- `entity --id Q12345 [--lang en] [--fields claims,labels,sitelinks]` — `wbgetentities`
- `disambiguate --term "<name>" --context "<context>"` — search + score by overlap between context and each candidate's description / claims; outputs ranked Q-ids
  - Heart use case: feed `references/person-aggregation.md` to anchor before crawl
- `sparql --query "<SPARQL>" [--out <csv>]` — arbitrary SELECT
- `self-test` — offline mock for `wbsearchentities` and `wbgetentities`

### 3.4 Files to update

- `references/person-aggregation.md` — add Step 0: "Anchor resolution via Wikidata search before crawl"
- `references/fact-verification.md` — add Wikidata as a canonical-entity short-circuit
- `SKILL.md` adapters list and `AGENTS.md` adapters list — both gain the new wikidata adapter doc
- `package.json` — add `wikidata:search`, `wikidata:entity`, `wikidata:sparql`

### 3.5 Test plan

- Self-test offline with mock JSON
- Manual smoke: search "OpenAlex" → confirm Q-id resolution

### 3.6 Estimate

3 hours.

---

## FEATURE 4 — Free search engine adapter

### 4.1 Technical decision

Combination of a small Node script + heavy upgrade to `adapters/web-search-only.md`. Make the adapter actionable, not abstract.

### 4.2 Files to create / update

```text
scripts/web_search.mjs                 (new — ~150 lines)
adapters/web-search-only.md            (rewrite — ~150 lines)
```

### 4.3 web_search.mjs flags

- `--engine duckduckgo|searxng|brave|google-cse`
- `--query "<q>"`
- `--limit <N>` (default 10)
- `--out <results.json>`
- Env vars when keys are needed: `BRAVE_API_KEY`, `GOOGLE_CSE_KEY` + `GOOGLE_CSE_ID`
- Output: normalised JSON `[{title, url, snippet, source_engine}]`
- `--self-test` — parse mocked HTML/JSON for each engine

### 4.4 Engines to document concretely

| Engine | Endpoint | Auth | Rate limit |
|---|---|---|---|
| DuckDuckGo HTML | `https://html.duckduckgo.com/html/?q=<q>` | None | Polite UA only |
| SearXNG | `https://<instance>/search?q=<q>&format=json` | None | Per-instance; ship a list of 5 stable public instances + how to validate one |
| Brave Search API | `https://api.search.brave.com/res/v1/web/search?q=<q>` | `X-Subscription-Token` header | Free tier ~2000 q/month |
| Google CSE | `https://www.googleapis.com/customsearch/v1?...` | `key` + `cx` query params | Free tier 100 q/day |

Document fallback chain: DuckDuckGo → SearXNG → (if user supplies key) Brave → Google CSE.

### 4.5 Files to update

- `references/source-discovery.md` — search-engine fallback chain section
- `SKILL.md` "Tool priority" — clarify which engine to try first when web-search-only branch is hit
- `package.json` — `search:web` shortcut

### 4.6 Test plan

- Offline self-test with mock responses for every engine
- Manual: one query against DuckDuckGo HTML, one against a public SearXNG instance

### 4.7 Estimate

2–3 hours.

---

## FEATURE 5 — Public social-media archival (the big one)

This feature now serves both developer and mainstream user audiences. The split:

- **Tier A — direct public APIs (high verifiability):** Reddit, Hacker News, Mastodon, Bluesky, Lemmy / Kbin
- **Tier B — archive-only (low verifiability, hand back caveats to the user):** X / Twitter, Facebook, Instagram, TikTok, YouTube comments, Threads, LinkedIn public posts

Tier B is the primary expansion in v2.1 versus the original v2.1 scoping. Mainstream users mostly encounter Tier B, not Tier A.

### 5.1 Why split into tiers

- Tier A platforms expose stable public read APIs. The agent fetches structured JSON, hashes canonical content, snapshots. Verifiability is "high" — same content can be re-fetched and compared exactly.
- Tier B platforms either block all bots, require login, change DOM constantly, or both. The only lawful-and-stable option is a Wayback / archive.today snapshot. Verifiability is "low" — the agent may have a screenshot or HTML capture but cannot guarantee the post wasn't edited or astroturfed before snapshot. The agent MUST tell the user this in plain language.

### 5.2 Verifiability label (every social claim ships with one)

Every evidence-ledger row whose source is a social platform carries a new column `verifiability` and a one-line `verifiability_note` written in plain language:

| Label | When to use | Example user-facing note |
|---|---|---|
| `direct_api` | Tier A platform, fetched live, content hashed | "Verified via Reddit's public JSON; same content can be re-checked any time." |
| `direct_api_deleted` | Tier A platform, fetched once, now 404 on re-check | "Found on Reddit on 2026-05-18; the post has since been deleted. Snapshot kept as audit trail." |
| `archive_snapshot` | Tier B, retrieved via Wayback / archive.today only | "Captured by Internet Archive on 2026-05-18. Original page is bot-protected; we could not verify the post directly. The archive may not reflect later edits." |
| `screenshot_only` | User supplied image; we transcribed text | "User-supplied screenshot. We cannot verify the post is real or unedited." |
| `unverified` | Mentioned in a third-party article, not snapshotted | "Reported by <publisher> on <date>; we could not reach the original post." |

**This column is mandatory for every social row** — `scripts/evidence_ledger.py validate` should warn when missing.

### 5.3 Files to create

```text
scripts/social_snapshot.py             (new — ~500 lines)
references/social-media-archival.md    (new — ~250 lines)
```

### 5.4 social_snapshot.py subcommands

```text
snapshot reddit     --url <u>             --out snap.json
snapshot hn         --id <id>             --out snap.json
snapshot mastodon   --url <u>             --out snap.json
snapshot bluesky    --url <u>             --out snap.json
snapshot lemmy      --url <u>             --out snap.json

snapshot x          --url <u>             --out snap.json   # archive-only
snapshot facebook   --url <u>             --out snap.json   # archive-only
snapshot instagram  --url <u>             --out snap.json   # archive-only
snapshot tiktok     --url <u>             --out snap.json   # archive-only
snapshot youtube    --url <u>             --out snap.json   # archive-only-with-metadata
snapshot threads    --url <u>             --out snap.json   # archive-only
snapshot linkedin   --url <u>             --out snap.json   # archive-only

snapshot generic    --url <u>             --out snap.json   # any other social URL
verify              --file snap.json                          # re-fetch & compare hash
to-ledger           --file snap.json --out-row row.csv
self-test
```

### 5.5 Snapshot output schema (`snap.json`)

```json
{
  "schema_version": "1.0",
  "platform": "reddit|hn|mastodon|bluesky|lemmy|x|facebook|instagram|tiktok|youtube|threads|linkedin|generic",
  "tier": "A|B",
  "verifiability": "direct_api|archive_snapshot|screenshot_only|unverified",
  "verifiability_note": "Plain-language sentence the agent shows the user.",
  "url_original": "https://...",
  "url_canonical": "https://...",
  "url_archive": "https://web.archive.org/web/.../...",
  "captured_at": "2026-05-18T10:30:00Z",
  "post": {
    "id": "...",
    "author_handle": "@username",
    "author_display_name": "Public Name",
    "author_verified_badge": true,
    "posted_at": "2026-05-15T08:00:00Z",
    "text": "Canonical text content (or null if archive-only and only screenshot available).",
    "lang": "en",
    "engagement_at_capture": {
      "score": 123,
      "reposts": 12,
      "comments": 45,
      "reactions": {"like": 10}
    },
    "media": [
      {"type": "image|video|gif", "url": "https://...", "archive_url": "..."}
    ],
    "thread_context": {
      "parent_id": "...",
      "channel": "r/python | mastodon-instance | youtube-video-id",
      "permalink": "..."
    }
  },
  "content_hash_sha256": "abc123...",
  "raw_response_path": "snap.raw.json",
  "verification": {
    "first_capture_at": "2026-05-18T10:30:00Z",
    "last_verified_at": null,
    "status": "intact|edited|deleted|unknown"
  },
  "limitations": [
    "Free-form list of caveats. E.g. 'Engagement counts on archive.org reflect 2026-05-18 — current numbers may differ.'"
  ]
}
```

### 5.6 Per-platform behaviour

#### Tier A — direct public APIs (verifiability: `direct_api`)

| Platform | Endpoint | Notes |
|---|---|---|
| Reddit | `https://www.reddit.com/<permalink>.json` | Polite UA required. ~60 req/min. Free, no key. |
| Hacker News | `https://hn.algolia.com/api/v1/items/<id>` | No rate limit advertised; be polite. Free, no key. |
| Mastodon | Per-instance `/api/v1/statuses/<id>` | Extract instance from URL. Each instance has its own rules. Polite UA. |
| Bluesky | `https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri=at://...` | Public read API, no auth. |
| Lemmy / Kbin | Per-instance `/api/v3/post?id=<id>` | Same instance pattern as Mastodon. |

#### Tier B — archive-only (verifiability: `archive_snapshot`)

For all Tier B platforms the script:

1. Calls `scripts/wayback.py save --url <u>` (Feature 2 dependency) to ensure a snapshot exists
2. Calls `scripts/wayback.py nearest --url <u> --timestamp <today>` to retrieve `archive_url`
3. Optionally also tries `https://archive.today` for redundancy (best-effort)
4. Sets `post.text = null` if no usable text could be extracted from the archive HTML
5. Sets `verifiability = "archive_snapshot"` and writes a clear `verifiability_note`
6. Records every limitation it knows about that platform in `limitations[]`

**Platform-specific Tier B notes** (these go into the limitations array verbatim where applicable):

- **X / Twitter** — Snapshot quality varies. Threads beyond the first reply are often lost. Engagement counts on the snapshot are stale. The skill MUST NOT attempt direct DOM scraping or use any third-party "Nitter"-style mirror that itself bypasses access controls; document that policy in the reference doc.
- **Facebook** — Public posts are sometimes cached by Wayback, but most aren't. Closed-profile posts will not be visible regardless. Group posts: only public groups, and even those are unreliable.
- **Instagram** — Wayback rarely captures Instagram. Most attempts will return `archive_snapshot` with `post.text = null`. The user must be told this is essentially a "title and screenshot only" record.
- **TikTok** — Heavy anti-bot. Snapshots often miss the video. Captions may or may not survive. Engagement counts are essentially unverifiable.
- **YouTube** — Comments are usually not in the Wayback snapshot. Video metadata (title, channel, upload date) is usually preserved. Public Invidious instances can supplement *metadata only*, not comments — and they're flaky; document but do not depend on them.
- **Threads (Meta)** — Treat like Instagram: archive-rare, low-coverage.
- **LinkedIn** — Public posts only when the original page is `linkedin.com/posts/...`. Anything behind a sign-up wall is out of scope.

### 5.7 references/social-media-archival.md outline

The reference doc must lead with the privacy boundary, not bury it:

1. **What this is for** (one paragraph)
2. **Privacy boundary — read this first** (hard refusals: minors, private individuals, harassment / stalking / doxxing framings; right-to-be-forgotten — keep hash + archive_url as audit trail but do not re-publish content the original poster has deleted unless there is an overriding public-interest reason and the agent surfaces that to the user)
3. **Tier A vs Tier B — what the user is getting** (the verifiability table, in plain Vietnamese-friendly English)
4. **Snapshot workflow** (step-by-step)
5. **Per-platform recipes** (one section each: Reddit, HN, Mastodon, Bluesky, Lemmy, X, Facebook, Instagram, TikTok, YouTube, Threads, LinkedIn, generic)
6. **Verification cycle** (re-fetch, compare hash, update `verification.status`)
7. **Evidence-ledger integration** (new columns: `archive_url`, `content_hash`, `snapshot_status`, `verifiability`, `verifiability_note`)
8. **Known limitations** by platform
9. **What the agent must say to the user** (templated phrases for each verifiability label, in plain language — example: "Tôi tìm thấy bài này trên Facebook, nhưng vì Facebook chặn truy cập tự động, tôi chỉ có ảnh chụp từ Internet Archive ngày 18/05/2026. Bài có thể đã bị chỉnh sửa hoặc xoá sau thời điểm đó.")

### 5.8 Templates and existing scripts to update

```text
templates/evidence-ledger.csv          (add 5 columns, backward compatible)
references/evidence-ledger.md          (document new columns)
scripts/evidence_ledger.py             (validate, sign, verify aware of new columns)
scripts/score_source.py                (rubric: +2 for archive_snapshot present, +1 for verified handle, -1 for unverified social claim)
references/source-quality-rubric.md    (document the new bands)
templates/api-request-log.csv          (add `platform` and `rate_limit_bucket` columns)
```

New evidence-ledger columns (all optional, all backward compatible):

- `archive_url` — Wayback or archive.today URL
- `content_hash` — SHA256 over canonical content
- `snapshot_status` — `intact|edited|deleted|unknown`
- `verifiability` — one of the labels in §5.2
- `verifiability_note` — plain-language sentence the agent will surface to the user

`scripts/evidence_ledger.py sign` and `verify` MUST include these columns in the canonical bytes hashed by HMAC, so signing protects the verifiability claim too.

### 5.9 Decision-tree branch in SKILL.md and AGENTS.md

Add a new branch:

> **If the user asks to capture or analyze a public social-media post**
>
> Use the social-media-archival reference doc (created in this PR). Snapshot first via the social_snapshot script, hash the canonical content, cross-archive with Wayback, and ledger with `archive_url` + `content_hash` + `verifiability`. For Tier B platforms (X, Facebook, Instagram, TikTok, YouTube, Threads, LinkedIn), the only lawful path is a Wayback snapshot — set `verifiability = archive_snapshot` and surface the verifiability note to the user in plain language. Refuse on minors, private individuals, harassment / stalking / doxxing framings — same hard stops as `references/person-aggregation.md`.

### 5.10 Privacy and ethics — explicit lists

**Allowed:**

- Public posts by public figures (politicians, executives, public researchers, verified journalists)
- Statements by organisations from official handles
- Press releases and official threads
- Aggregate public stats (subreddit member count, hashtag use)
- Snapshot-as-audit-trail when the post is later deleted, IF the purpose is documentation (research, journalism, fact-checking) AND the agent surfaces the deletion status to the user

**Not allowed:**

- Re-publishing posts of private individuals (even when public) — quote sparingly, prefer paraphrase, point to archive_url instead of inlining text
- Aggregating behavioural patterns of an individual account (when it posts, where, with whom)
- Cross-platform identity linking when the user has not publicly linked them
- Any scraping of accounts identified or self-identified as belonging to minors — refuse
- Attempting to bypass anti-bot systems, login walls, or rate limits on Tier B platforms
- Use of third-party "mirror" sites that themselves bypass access controls
- Any use case framed as harassment, stalking, doxxing, or coordinated reporting / reporting-for-suspension

**Grey zones requiring user confirmation:**

- Posts of public figures from when they were minors (default refuse, allow only with explicit user justification AND a public-interest signal)
- Posts deleted by a private user — keep hash + archive_url, do not re-publish content
- Anonymous or alias accounts — never re-identify

### 5.11 Test plan

**Self-test (offline, must run in CI):**

- Mock JSON for each Tier A platform (Reddit, HN, Mastodon, Bluesky, Lemmy)
- Mock Wayback responses for each Tier B platform
- Hash stability test (same input → same SHA256)
- Verification logic test (mock changed input → `status = edited`)
- Ledger row format test (output passes `evidence_ledger.py validate` with new columns)
- Refusal probe: minor account framing → must error out before any HTTP call

**Manual smoke (not in CI):**

- 1 Reddit post (Tier A)
- 1 HN comment (Tier A)
- 1 Mastodon status from a large instance (Tier A)
- 1 Bluesky post (Tier A)
- 1 X URL → expect Tier B archive-only path
- 1 Facebook public post URL → expect Tier B
- 1 Instagram URL → expect Tier B with `post.text = null`
- 1 YouTube video URL → expect metadata + comments-missing caveat
- 1 TikTok URL → expect Tier B and a "may not have captured the video" caveat

### 5.12 Estimate

8–10 hours (script + reference doc + ledger schema migration + score_source updates + decision-tree updates + tests).

---

## CROSS-CUTTING WORK

### CC.1 testing-scripts sub-skill

`.agents/skills/testing-scripts/SKILL.md` lists 13 self-tests today. After v2.1 this becomes 18:

- pdf_extract.py
- wayback.py
- wikidata.py
- web_search.mjs
- social_snapshot.py

### CC.2 CI workflow

`.github/workflows/lint-and-self-test.yml` already runs `npm run self-test` and will pick up the new tests automatically. One change required: install poppler-utils (Feature 1) alongside pandoc.

### CC.3 Documentation counts to refresh

In `README.md`:

- Scripts: 13 → 18
- References: 31 → 33 (adds pdf-extraction, wayback-archive, social-media-archival; rewrites web-search-only as adapter not reference)
- Adapters: 6 → 7 (adds wikidata)

### CC.4 Versioning and tagging

- `package.json` version: 0.2.0 → 0.3.0 (minor bump, additive only)
- Git tag at end of v2.1 work: `v2.1.0`

---

## DELIVERY ORDER (recommended)

| PR | Scope | Estimate | Depends on |
|---|---|---:|---|
| **PR #1** | Feature 1 (PDF) + Feature 2 (Wayback) | ~5 h | nothing |
| **PR #2** | Feature 3 (Wikidata) + Feature 4 (Search engines) | ~6 h | nothing |
| **PR #3** | Feature 5 (Social archival, Tier A + B) | ~9 h | **Feature 2 must already be merged** (Tier B archive flow calls wayback.py) |

Each PR is independently mergeable. Do not bundle everything into one PR — review burden becomes unmanageable, especially around the social privacy boundary.

---

## ACCEPTANCE CHECKLIST (per feature)

A feature is "done" when ALL of the following hold:

- [ ] Script(s) created and chmod +x
- [ ] `self-test` subcommand passes locally and in CI
- [ ] Wired into `npm run self-test` chain in `package.json`
- [ ] npm shortcut(s) added in `package.json`
- [ ] Reference / adapter doc(s) created
- [ ] Existing references and decision-tree branches in `SKILL.md` and `AGENTS.md` updated to mention the new tooling
- [ ] `.agents/skills/testing-scripts/SKILL.md` updated to include the new self-test
- [ ] README counts (scripts / references / adapters) updated
- [ ] `python3 scripts/check_internal_refs.py` exits 0
- [ ] CI green on the PR
- [ ] Manual smoke test executed and the result documented in the PR description
- [ ] For Feature 5: privacy boundary section reviewed by maintainer before merge

---

## OPEN QUESTIONS FOR THE MAINTAINER

1. Should `pdf_extract.py` ship a tiny test PDF in `examples/fixtures/`, or generate one at runtime? Repo currently has no `fixtures/` directory.
2. For Feature 4, should we ship a curated list of public SearXNG instances (which goes stale fast) or just point at `https://searx.space` and let the user pick?
3. For Feature 5, do we want `social_snapshot.py` to call `wayback.py` as a Python module, as a subprocess, or via a shared helper? Subprocess matches the existing `run_python.mjs` pattern but adds startup latency on bulk runs.
4. Should the verifiability label be enforced as a **warning** or **hard failure** in `evidence_ledger.py validate` when a social-platform row is missing it? Recommend hard failure for new rows after v2.1; soft warning for legacy rows for one minor version.
5. Should we add a screenshot-only intake path (`snapshot from-image --in screenshot.png --transcribe ...`) or leave that to the user? Mainstream users frequently arrive with a screenshot of a deleted post; transcribing it changes the verifiability story.

When these are resolved, the maintainer should append answers to this file under "DECISIONS" rather than rewrite the body, so the audit trail stays clear.
