# Safety and Access Policy

Use this file for all data collection, crawling, and browser automation tasks.

## Default mode

Research is read-only by default.

Do not submit forms, create accounts, make purchases, change settings, send messages, or perform side-effect actions unless the user explicitly requests and authorizes that action.

## Access boundaries

Do not bypass:
- authentication
- paywalls
- captcha or bot challenges
- access control headers
- rate limits
- IP bans
- robots restrictions when crawling
- terms explicitly forbidding automated access

## Credentials

Use credentials only when:
- the user explicitly provides them or authorizes the agent to use an existing session
- the user has permission to access the data
- the task is read-only unless otherwise stated

Never reveal secrets, tokens, cookies, or private data.

## Politeness

Use bounded crawl limits, delays, deduplication, and early stopping. Stop on repeated 403, 429, captcha, or similar blockers.

## Personal data

Avoid collecting personal data unless the user has a legitimate, authorized purpose. Collect only the minimum necessary fields.

## Blocked sources

When access is blocked, produce a blocker report instead of trying to evade the block.

## Uncertain legality or permission

When permission is unclear:
- use public summaries and official pages
- avoid automated extraction
- ask the user to manually retrieve authorized data
- document the limitation

## Machine translation privacy

Remote machine translation services (LibreTranslate, DeepL, Google Translate) send text to third-party servers. This is a privacy-sensitive operation:

- **Requires explicit opt-in**: `--allow-remote` flag or `D_RESEARCH_ALLOW_REMOTE_TRANSLATION=1`
- **Do not pipe sensitive evidence-ledger rows** to public MT without user consent
- **Prefer local translation** (Argos Translate) for confidential or personal data
- **Document when remote MT is used** in the evidence ledger `notes` field

See `adapters/translation.md` for backend configuration and `scripts/translate.py` for usage.
