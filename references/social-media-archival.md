# Social Media Archival

Use this file when the user asks to capture, verify, or analyze a public
social-media post. The script `scripts/social_snapshot.py` wraps the
entire workflow into a single CLI with subcommands: `snapshot`, `verify`,
`to-ledger`, and `self-test`.

---

## Privacy boundary (read first)

The privacy boundary is a **hard stop**, not abstract guidance. It runs
BEFORE any HTTP call and exits with code 2 on violation.

### Allowed

- Archiving public posts by public figures, organizations, or verified
  accounts for research, journalism, or accountability purposes.
- Capturing public discussion threads (Reddit, HN, Mastodon, Lemmy) for
  evidence or citation.
- Archiving your own posts on any platform.
- Capturing posts that are part of a public event, press release, or
  official announcement.

### Not allowed

- Archiving posts by or about minors (under 18), regardless of account
  visibility settings.
- Aggregating behavioral patterns of individual private accounts.
- Cross-platform identity linking or pseudonym-to-real-name
  re-identification.
- Framing requests as harassment, stalking, doxxing, or intimidation.
- Using Nitter-style mirrors, login-bypass URLs, or any tool that
  circumvents access controls.
- Scraping DMs, private groups, or followers-only content.

### Grey zone (ask the user)

- Public posts by private individuals that went viral — archive only if
  the user confirms a legitimate research or journalistic purpose.
- Deleted posts that still exist in web archives — the archive is public,
  but context matters; confirm intent before proceeding.
- Engagement metrics on sensitive topics — capture if relevant to the
  research question, but flag the sensitivity.

---

## Tier A vs Tier B

The script uses a two-tier architecture based on API availability:

| Tier | Platforms | Method | Verifiability |
|------|-----------|--------|---------------|
| A | Reddit, Hacker News, Mastodon, Bluesky, Lemmy | Direct public API fetch | `direct_api` (high) |
| B | X, Facebook, Instagram, TikTok, YouTube, Threads, LinkedIn | Archive-only via `scripts/wayback.py` | `archive_snapshot` (low) |

**Tier A** platforms expose stable public JSON APIs. The script fetches
the post directly, extracts structured fields, computes a SHA-256
content hash, and writes a Snapshot JSON file. Re-verification is
possible by re-fetching and comparing hashes.

**Tier B** platforms block direct bot access. The only lawful archival
path is a Wayback Machine snapshot via `scripts/wayback.py`. Text
extraction is not guaranteed (`post.text` may be null), and
re-verification against the original is not possible.

### Verifiability table

| Label | Meaning | When assigned |
|-------|---------|---------------|
| `direct_api` | Content fetched from official API; hash verifiable | Tier A, successful fetch |
| `direct_api_deleted` | Was verifiable, but post has since been deleted | Tier A, 404 on re-verify |
| `archive_snapshot` | Archived via Wayback; no direct text extraction | Tier B, or Tier A fallback |
| `screenshot_only` | Only a screenshot exists; no structured text | Manual capture only |
| `unverified` | No API, no archive, no screenshot | Claim without evidence |

---

## Per-platform recipes

### Reddit (Tier A)

```bash
python scripts/social_snapshot.py snapshot reddit \
  --url "https://www.reddit.com/r/science/comments/abc123/title/" \
  --out snap.json
```

API endpoint: `https://www.reddit.com/<permalink>.json`
Rate limit: ~60 req/min (polite User-Agent header).

### Hacker News (Tier A)

```bash
python scripts/social_snapshot.py snapshot hn \
  --id 12345678 \
  --out snap.json
```

API endpoint: `https://hn.algolia.com/api/v1/items/<id>`
No authentication required.

### Mastodon (Tier A)

```bash
python scripts/social_snapshot.py snapshot mastodon \
  --url "https://mastodon.social/@user/123456789" \
  --out snap.json
```

API endpoint: `https://<instance>/api/v1/statuses/<id>`
Works with any Mastodon-compatible instance (Pleroma, Akkoma, etc.).

### Bluesky (Tier A)

```bash
python scripts/social_snapshot.py snapshot bluesky \
  --url "https://bsky.app/profile/user.bsky.social/post/abc123" \
  --out snap.json
```

API endpoint: `https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread`
Converts the URL to an AT URI before fetching.

### Lemmy (Tier A)

```bash
python scripts/social_snapshot.py snapshot lemmy \
  --url "https://lemmy.world/post/12345" \
  --out snap.json
```

API endpoint: `https://<instance>/api/v3/post?id=<id>`
Works with any Lemmy instance.

### X / Twitter (Tier B)

```bash
python scripts/social_snapshot.py snapshot x \
  --url "https://x.com/user/status/123456789" \
  --out snap.json
```

Archive-only. `post.text` will be null. Limitations include no
engagement metrics and no thread context from the archive.

### Facebook (Tier B)

```bash
python scripts/social_snapshot.py snapshot facebook \
  --url "https://www.facebook.com/page/posts/123456" \
  --out snap.json
```

Archive-only. Public page posts only. Personal profiles are refused by
the privacy boundary.

### Instagram (Tier B)

```bash
python scripts/social_snapshot.py snapshot instagram \
  --url "https://www.instagram.com/p/ABC123/" \
  --out snap.json
```

Archive-only. `post.text` will be null. Media URLs are not extracted.

### TikTok (Tier B)

```bash
python scripts/social_snapshot.py snapshot tiktok \
  --url "https://www.tiktok.com/@user/video/123456789" \
  --out snap.json
```

Archive-only. Video content is not captured; only the page metadata
from the archive snapshot is preserved.

### YouTube (Tier B)

```bash
python scripts/social_snapshot.py snapshot youtube \
  --url "https://www.youtube.com/watch?v=abc123" \
  --out snap.json
```

Archive-only. Video content and comments are not captured. Title and
description may be available from the archive HTML.

### Threads (Tier B)

```bash
python scripts/social_snapshot.py snapshot threads \
  --url "https://www.threads.net/@user/post/ABC123" \
  --out snap.json
```

Archive-only. `post.text` will be null.

### LinkedIn (Tier B)

```bash
python scripts/social_snapshot.py snapshot linkedin \
  --url "https://www.linkedin.com/posts/user_activity-123456789" \
  --out snap.json
```

Archive-only. Public posts only. The privacy boundary refuses personal
profile archival requests.

### Generic fallback

```bash
python scripts/social_snapshot.py snapshot generic \
  --url "https://some-forum.example.com/thread/42" \
  --out snap.json
```

Attempts a Wayback snapshot. Sets `platform: "generic"` and
`verifiability: "archive_snapshot"`. Use when the platform is not in
the supported list.

---

## Verification cycle

After capturing a snapshot, you can re-verify Tier A posts to detect
edits or deletions:

```bash
python scripts/social_snapshot.py verify --file snap.json
```

The verification logic:

1. Load the Snapshot JSON and check the tier.
2. **Tier A:** Re-fetch from the original API endpoint, compute a new
   SHA-256 hash, and compare with the stored hash.
   - Match → `verification.status = "intact"`
   - Mismatch → `verification.status = "edited"` (warning printed)
   - HTTP 404 → `verification.status = "deleted"`, `verifiability`
     updated to `"direct_api_deleted"`
3. **Tier B:** Set `verification.status = "unknown"` — archive-only
   posts cannot be re-verified against the original.
4. Update `verification.last_verified_at` in the JSON file.

---

## Evidence-ledger integration

Convert a snapshot to an evidence-ledger row:

```bash
python scripts/social_snapshot.py to-ledger \
  --file snap.json \
  --out-row row.csv
```

The 5 new columns added to the evidence ledger for social archival:

| Column | Source field | Description |
|--------|-------------|-------------|
| `archive_url` | `url_archive` | Wayback Machine archive URL (if any) |
| `content_hash` | `content_hash_sha256` | SHA-256 hex digest of canonical text |
| `snapshot_status` | `verification.status` | `intact`, `edited`, `deleted`, or `unknown` |
| `verifiability` | `verifiability` | Label from the verifiability table above |
| `verifiability_note` | `verifiability_note` | Plain-language explanation |

These columns are optional in the ledger schema — existing ledgers
without them continue to validate. When present, they are included in
the HMAC signature computed by `scripts/evidence_ledger.py sign`.

---

## Verifiability phrases

The script generates a plain-language `verifiability_note` for each
capture. Templated phrases by label:

| Label | Template phrase |
|-------|----------------|
| `direct_api` | "Content fetched directly from the {platform} public API on {date}. The SHA-256 hash can be re-verified by re-fetching." |
| `direct_api_deleted` | "Content was originally fetched from the {platform} API but the post has since been deleted (HTTP 404 on re-verification)." |
| `archive_snapshot` | "Content archived via Wayback Machine on {date}. Direct text extraction is not available; verifiability is limited to the archive copy." |
| `screenshot_only` | "Only a screenshot of this post exists. No structured text or hash verification is possible." |
| `unverified` | "This claim references a social post but no API fetch, archive snapshot, or screenshot was obtained. Treat as unverified." |

---

## npm shortcuts

```bash
npm run social:snapshot -- reddit --url <url> --out snap.json
npm run social:verify -- --file snap.json
```

The self-test is wired into the `npm run self-test` chain and runs
fully offline (no network requests).

---

## See also

- `scripts/social_snapshot.py` — the script itself
- `scripts/wayback.py` — Wayback Machine archive access (Tier B dependency)
- `scripts/evidence_ledger.py` — evidence ledger init/validate/sign/verify
- `scripts/score_source.py` — source-quality rubric (includes social scoring bands)
- `references/evidence-ledger.md` — evidence ledger format and columns
- `references/source-quality-rubric.md` — scoring rubric with social modifiers
- `references/wayback-archive.md` — Wayback Machine reference
- `references/person-aggregation.md` — privacy boundary for person lookups
- `references/safety-and-access-policy.md` — full safety and access policy
