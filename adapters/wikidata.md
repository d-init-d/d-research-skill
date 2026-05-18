# Wikidata Adapter

Use this adapter when the research task involves **entity disambiguation**, **structured knowledge retrieval**, or **relationship queries** against the Wikidata knowledge base. Wikidata provides canonical Q-IDs for people, organisations, products, places, and concepts — useful as anchors before a broader crawl.

## When to use

- Anchoring a person or entity to a canonical identifier (Q-ID) before running `references/person-aggregation.md`.
- Verifying structured facts (birth date, affiliation, authorship) via `references/fact-verification.md`.
- Discovering relationships between entities via SPARQL (e.g. "all novels by author Q42").
- Disambiguating homonyms using contextual scoring.

## Script

`scripts/wikidata.py` — stdlib-only Python, no pip dependencies.

## Subcommand reference

### search

Find entities matching a term.

```bash
python3 scripts/wikidata.py search --term "Douglas Adams" --limit 5
python3 scripts/wikidata.py search --term "Apple" --type org --limit 3
```

Options: `--term` (required), `--type person|org|product|place` (optional filter), `--limit N` (default 5).

Output: JSON array of `{qid, label, description, aliases}`.

### entity

Retrieve detailed information about a known entity.

```bash
python3 scripts/wikidata.py entity --id Q42
python3 scripts/wikidata.py entity --id Q42 --lang de --fields labels,claims
```

Options: `--id` (required Q-ID), `--lang` (default `en`), `--fields` (comma-separated subset of `claims,labels,descriptions,aliases,sitelinks`).

Output: JSON object with requested fields.

### disambiguate

Score candidates by contextual overlap to resolve homonyms.

```bash
python3 scripts/wikidata.py disambiguate --term "Marie Curie" --context "physicist Nobel Prize radium"
```

Options: `--term` (required), `--context` (required context string for scoring).

Output: JSON array sorted by descending score: `{qid, label, description, score}`.

### sparql

Execute arbitrary SPARQL SELECT queries against the Wikidata Query Service.

```bash
python3 scripts/wikidata.py sparql --query "SELECT ?item ?itemLabel WHERE { ?item wdt:P31 wd:Q5 . ?item wdt:P106 wd:Q36180 . SERVICE wikibase:label { bd:serviceParam wikibase:language 'en'. } } LIMIT 10"
python3 scripts/wikidata.py sparql --query "..." --out results.csv
```

Options: `--query` (required SPARQL string), `--out` (optional file path; writes CSV instead of JSON to stdout).

## Rate-limit etiquette

- Wikidata API and SPARQL endpoint are public and free but rate-limited.
- Do not send more than ~10 requests per second to the API or ~1 SPARQL query per second.
- If you receive HTTP 429, back off and retry after the indicated delay.
- Batch entity lookups when possible (the API supports multiple IDs per call).

## User-Agent policy

Wikimedia requires a descriptive User-Agent header containing a contact email on every request. The script enforces this automatically. If you fork or modify the script, update the `USER_AGENT` constant with your own project URL and contact address.

See: https://meta.wikimedia.org/wiki/User-Agent_policy

## See also

- `references/person-aggregation.md` — uses `disambiguate` for Step 0 anchor resolution.
- `references/fact-verification.md` — uses `entity` as a canonical-entity short-circuit.
- `references/api-access-workflow.md` — general API access patterns.
- `references/source-discovery.md` — Wikidata as a structured-data discovery layer.
- `SKILL.md` — main entry point and decision tree.
