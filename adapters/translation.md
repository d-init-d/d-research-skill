# Translation Adapter

Translate text between languages using `scripts/translate.py`. Supports multiple backends with privacy-aware defaults.

## When to Use

- Multilingual research requiring source-language extraction then translation
- Translating evidence-ledger claims for cross-language synthesis
- Detecting the language of extracted text before routing to translators
- Any workflow described in `references/multilingual-research.md`

## Backends

| Backend | Auth | Privacy | Quality |
|---|---|---|---|
| LibreTranslate (default) | None (public instances) | Data sent to public server | Good |
| DeepL | `DEEPL_API_KEY` env var | Data sent to DeepL servers | High |
| Google Translate | `GOOGLE_TRANSLATE_API_KEY` | Data sent to Google | High |
| Argos Translate | `pip install argostranslate` | Fully local | Moderate |

## Privacy Warning

Translation backends (except Argos) send text to external servers. Do NOT pipe sensitive evidence-ledger rows to public MT services without explicit user consent. See `references/safety-and-access-policy.md`.

Remote translation requires explicit opt-in:
- Flag: `--allow-remote` on the `text` subcommand
- Environment: `D_RESEARCH_ALLOW_REMOTE_TRANSLATION=1`
- Without either, remote engines exit non-zero with a privacy message

For sensitive content, use Argos Translate (local) or ask the user to translate manually.

## Provider Configuration

| Backend | Required Env Var | Opt-in | Notes |
|---|---|---|---|
| LibreTranslate | None (optional: `LIBRETRANSLATE_URL`, `LIBRETRANSLATE_API_KEY`) | `--allow-remote` | Public instances, no key needed |
| DeepL | `DEEPL_API_KEY` | `--allow-remote` | 500k chars/month free tier |
| Google | `GOOGLE_TRANSLATE_API_KEY` | `--allow-remote` | Pay-per-use |
| Argos | None (pip install argostranslate) | Not needed (local) | Fully offline |

## Usage

```bash
# Translate text (default: LibreTranslate, requires --allow-remote)
python scripts/translate.py text --in input.txt --to en --allow-remote --out translated.txt

# Detect language (stdlib trigram heuristic, no network)
python scripts/translate.py detect --in unknown.txt

# List known LibreTranslate instances
python scripts/translate.py instances
```

## Language Detection

The `detect` subcommand uses a stdlib trigram cosine-similarity heuristic. It supports: en, vi, fr, de, es, ja, zh, ru. Returns top-3 candidates with confidence scores. No network required.

Optional upgrade: if `langdetect` is pip-installed, it can be preferred for higher accuracy (not implemented yet — future enhancement).

## Multilingual Research Workflow

The canonical workflow from `references/multilingual-research.md`:

1. **Extract first** — get source text in original language
2. **Detect language** — `python scripts/translate.py detect --in text.txt`
3. **Translate second** — `python scripts/translate.py text --in text.txt --to en`
4. **Preserve original** — keep both original and translation in the evidence ledger

Never translate before extraction. Original-language evidence is the primary source; translations are secondary.

## See Also

- `references/multilingual-research.md` — full multilingual workflow
- `references/safety-and-access-policy.md` — privacy constraints for MT
- `scripts/translate.py` — the translation script
