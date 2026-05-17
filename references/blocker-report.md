# Blocker Report

Use this file when a relevant source is discovered but cannot be extracted.

If the source appears to be a public tier-1 source blocked by anti-bot, JavaScript challenge, captcha, 403, 429, geo block, or repeated browser/fetch failure, run `references/anti-bot-fallback.md` once before writing this report. Do not run the fallback chain for real permission boundaries such as login-only, paywall-only, or private content.

## Principle

Failure to extract is still useful research output if it tells the user exactly where the data is and how to retrieve it manually.

## Blocker types

- login required
- paywall
- captcha or bot challenge
- 401 unauthorized
- 403 forbidden
- 429 rate limited
- geo or VPN block
- JavaScript challenge
- robots or access restriction
- broken page
- file unavailable
- unsupported file format
- content visible only after user action
- permission needed
- unknown

## Required report

```markdown
## Blocked source

URL:
Source title:
Why this source likely matters:
Access status:
Blocker type:
Confidence that the source contains useful data:

## Attempts made

Search query used:
Browser opened:
Fetch attempted:
Interactions attempted:
Files/endpoints discovered:
Fallback chain attempted:
Screenshot captured:
Timestamp:

## Observed evidence

What was visible:
What indicated blocking:
Error/status/message:

## Manual retrieval instructions

1. Open the URL manually.
2. Log in or obtain permission if required.
3. Navigate to:
4. Apply these filters:
5. Export/copy/download these fields or files:
6. Return the data to the agent in this format:

## Data to collect

Required fields:
Optional fields:
Date range:
Filters:
Export format:
Screenshots needed:
Relevant page sections:

## Alternative sources

| Alternative | URL | What it may provide | Confidence |
|---|---|---|---|
```

## Manual retrieval format

When possible, ask the user to return data as:
- CSV for tables
- JSON for nested records
- PDF or screenshot for visual evidence
- copied text with URL and access date for small snippets
