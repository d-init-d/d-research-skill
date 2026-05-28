# Vietnamese Source Discovery

Use this companion with `references/multilingual-research.md` when Vietnamese
sources, Vietnam-based organizations, local news, education sources, public
events, government portals, or Vietnamese-language social/community sources are
material to the task.

This file improves recall for Vietnamese and Vietnam-local research without
making Vietnamese discovery the default for unrelated domains.

## Safety and Scope

- Stay read-only and follow `references/safety-and-access-policy.md`.
- For named people, apply `references/person-aggregation.md` before searching.
- Do not collect private personal information, private accounts, family details,
  personal contact details, exact whereabouts, private photos, or sensitive
  status.
- Public social/community sources are leads unless identity and context are
  independently supported.
- Login-only groups, private profiles, deleted posts, captchas, paywalls, and
  anti-bot barriers are blockers, not targets to force.

## Query Construction

For each important entity, build a small alias set:

- Vietnamese with diacritics and without diacritics.
- Full name, short name, abbreviation, acronym, and common misspelling.
- Old and new organization names, campus/city names, department names, and
  English/Vietnamese translations.
- Event title, article title, distinctive quote, award name, program name,
  class/cohort/year, role, and associated people when relevant.
- Hyphenated and non-hyphenated variants when names or schools are often written
  both ways.

Run a balanced matrix instead of relying on one organic search path:

1. exact full-name or exact title;
2. no-diacritic variant;
3. partial-name or abbreviation variant;
4. role plus organization;
5. event/article title plus organization;
6. unique quote;
7. associated person plus organization;
8. class/cohort/year plus organization;
9. site-specific official search;
10. site-specific news search;
11. archive, mirror, reprint, or aggregator search;
12. public social, forum, or video search when privacy-safe;
13. contradiction or same-name disambiguation search.

For audit-grade work, record which buckets were tried, which produced sources,
which were irrelevant, and which were blocked.

## Source Basins

Prefer basins in roughly this order, adjusting for the task:

- Official organization, school, company, government, or project pages.
- Public data portals and official document repositories.
- National or local news outlets.
- Education, association, event, award, conference, or contest pages.
- Archive snapshots, mirrors, reprints, and aggregators when originals are
  unavailable.
- Public social pages/posts/videos/forums that are directly relevant and
  privacy-safe.
- Same-name contradiction sources.

Do not treat mirrors, reprints, or copied articles as independent confirmation
unless they add new original evidence.

## Useful Query Patterns

Examples below are patterns, not a required checklist for every task:

```text
"<ten day du>" "<to chuc>"
"<ten khong dau>" "<to chuc khong dau>"
"<ten rut gon>" "<vai tro>" "<to chuc>"
"<tieu de bai viet>"
"<cum tu dac trung>"
"<su kien>" "<nam>"
"<lop/khoa/nam>" "<to chuc>"
"<nguoi lien quan>" "<to chuc>"
site:<official-domain> "<anchor>"
site:vietnamnet.vn "<anchor>"
site:vnexpress.net "<anchor>"
site:tuoitre.vn "<anchor>"
site:thanhnien.vn "<anchor>"
site:dantri.com.vn "<anchor>"
site:nld.com.vn "<anchor>"
site:tienphong.vn "<anchor>"
site:giaoducthoidai.vn "<anchor>"
site:moet.gov.vn "<anchor>"
site:*.gov.vn "<anchor>"
"<anchor>" "bao dien tu"
"<anchor>" "dien dan"
"<anchor>" "forum"
"<anchor>" "Facebook" "<to chuc>"
"<anchor>" "YouTube" "<to chuc>"
```

For social/community discovery, use public pages and public posts first:

```text
site:facebook.com "<ten/to chuc>" "<anchor>"
site:youtube.com "<su kien/to chuc>" "<anchor>"
site:tiktok.com "<ten/to chuc>" "<anchor>"
site:instagram.com "<ten/to chuc>" "<anchor>"
site:linkedin.com "<ten/to chuc>" "<anchor>"
(site:x.com OR site:twitter.com) "<ten/to chuc>" "<anchor>"
site:threads.net "<ten/to chuc>" "<anchor>"
site:zalo.me "<to chuc>" "<anchor>"
```

Mark every social/community lead with access state and identity status:

- confirmed same identity;
- likely same identity;
- possible same identity;
- uncertain or same-name risk;
- likely different person/entity.

## Date and Identity Discipline

Vietnamese local sources often contain compressed context. Be strict:

- Do not infer birth year from article year, grade, class, event year, or labels
  such as "9X" unless the source states the birth year.
- Do not convert article publication year into school year or cohort unless the
  source states that relationship.
- Report "article published in 2008" instead of "school year 2008-2009" unless
  verified.
- Distinguish schools or organizations with the same name across cities,
  campuses, branches, and historical names.
- Distinguish students, alumni, teachers, parents, journalists, organizers,
  award winners, and social profiles with similar names.
- Downgrade confidence when matching depends on snippets, mirrors, partial names,
  personal social profiles, or non-primary sources.

## Compact Coverage Table

For non-trivial Vietnamese/local discovery, include a compact table when useful:

| Bucket | Queries tried | Best source found | Status | Gap |
|---|---|---|---|---|
| Official |  |  | found / none / blocked |  |
| News |  |  | found / none / blocked |  |
| Archive/mirror |  |  | found / none / blocked |  |
| Public social/community |  |  | found / none / blocked / out of scope |  |
| Same-name contradiction |  |  | checked / unresolved |  |

If the answer remains single-basin after this pass, either continue with
`references/execution-gates.md` and `references/frontier-search.md`, or state
that coverage is partial.
