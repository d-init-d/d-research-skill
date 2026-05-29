# Multilingual Research

Multilingual research enables thorough investigation across languages, capturing perspectives, data, and publications that English-only searches miss. This skill is essential for global market analysis, comparative policy research, and accessing non-English academic literature.

## When to Use Multilingual Research

Use this approach when:

- **Sources in multiple languages**: Primary documents, government reports, or local news exist only in their native language
- **Multi-country market/policy research**: Analyzing how different regions approach similar challenges requires original-language sources
- **Non-English academic papers**: Major research findings are often published in the language of the country conducting the study
- **Local context understanding**: Regional expertise frequently appears in local publications not translated to English
- **Verification and triangulation**: Cross-language sources provide stronger evidence when findings align across linguistic boundaries

## Workflow

Follow this sequence for systematic multilingual research:

1. **Identify relevant languages**: Determine which languages contain authoritative sources for your topic. Consider official languages of relevant countries, languages of key institutions, and languages with significant academic output in your field.

2. **Generate queries per language**: Create search queries in each target language. Use terminology appropriate to that linguistic and cultural context. Consider consulting bilingual dictionaries or local experts for domain-specific terms.

3. **Search on local search engines**: Use region-appropriate search engines and academic databases. English search engines often miss local content or rank it lower in results.

4. **Extract in original language**: Gather sources, data, and quotes in their original language when possible. Preserve nuance and avoid premature translation that may lose meaning.

5. **Translate key findings**: Translate selected material using reliable translation tools or services. Prioritize sources most relevant to your research objectives.

6. **Cross-validate across languages**: Compare findings from different language sources. Agreement across languages strengthens conclusions. Discrepancies reveal cultural or contextual factors worth investigating.

7. **Report language coverage**: Document which languages were searched, key sources found in each language, and the overall language diversity of your research foundation.

## Search Engines by Language

Different search engines dominate in different regions and often provide better local results:

| Language | Primary Search Engines |
|----------|----------------------|
| English | Google, Bing |
| Chinese | Baidu, Sogou |
| Russian | Yandex |
| Korean | Naver |
| Japanese | Yahoo Japan |
| Vietnamese | CocCoc, Google.com.vn |
| Portuguese | Google.br, Bing Brasil |
| Spanish | Google.es, Bing Latino |

For **multilingual academic searches**, use Google Scholar with language filters in settings, or combine with specialized regional engines.

For Vietnamese or Vietnam-local source discovery, also read
`references/vietnamese-source-discovery.md`. It provides query matrices,
diacritic/no-diacritic alias handling, local source basins, and date/identity
discipline for Vietnamese news, public institutions, and public community
sources.

When recall stays thin because the evidence basin uses lay terms, community
jargon, or vernacular slang rather than canonical vocabulary, also read
`references/register-and-jargon-expansion.md`. It adds a bidirectional register
ladder (formal ↔ vernacular) as a layer on top of this native-language
workflow — extract original-language terms first, then expand register; never
let an English slang pivot overwrite the native register.

## Translation Strategy

Effective translation preserves meaning while enabling analysis:

- **Extract first, translate second**: Always read source material in original language when possible before relying on translation
- **Preserve original alongside translation**: Keep original text available for verification and to catch translation errors
- **Note translation confidence**: Flag passages where translation is uncertain or machine-generated
- **Keep proper nouns untranslated**: Names, locations, organizations, and product names should remain in original form
- **Verify technical terms**: Confirm translation accuracy of specialized terminology with domain-specific resources or native speakers

### Tool support

Use `scripts/translate.py` for programmatic translation:

```bash
# Detect language (offline, no network)
python scripts/translate.py detect --in source.txt

# Translate with explicit remote opt-in
python scripts/translate.py text --in source.txt --to en --allow-remote --out translated.txt
```

Remote translation requires `--allow-remote` or `D_RESEARCH_ALLOW_REMOTE_TRANSLATION=1` for privacy. See `adapters/translation.md` for backend configuration.

## Academic Multilingual Resources

Many academic databases support language filtering and specialized local repositories exist:

- **Multidisciplinary with language filters**: Web of Science, Scopus, Google Scholar
- **OpenAlex**: Supports language filtering via the `lang` parameter in API queries
- **French research**: HAL (hal.science) - comprehensive French open archive
- **Chinese research**: CNKI (cnki.net) - primary Chinese academic database
- **Japanese research**: CiNii (cir.nii.ac.jp) - Japanese academic literature
- **Portuguese/Spanish research**: SciELO (scielo.org) - Latin American and Iberian publications
- **Korean research**: DBPIA (dbpia.co.kr) - Korean academic publications

When accessing local repositories, use the native language interface for better search precision and access to filters not available in translated versions.

## Documenting Language Coverage

Always report your linguistic scope in research outputs. Note which languages were searched, what proportion of sources came from each language, and any languages identified but not accessed due to limitations. This transparency allows readers to assess the comprehensiveness of your research and identify potential gaps in coverage.
