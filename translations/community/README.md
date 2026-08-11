# Community translations

English | [日本語](README.ja.md)

Japanese and English are the officially maintained application and documentation languages. Translation files contributed by users are stored separately as community translations until their terminology, layout, placeholders, and RTL behavior have been reviewed.

## Submit a translation

1. Export the current English-source template from RLMResearchPlanner.
2. Follow the [translation file guide](../../docs/en-US/translation-files.md).
3. Name the file with its normalized BCP 47 locale, for example `fr-FR.json` or `ar.json`.
4. Fill in `author` and `license`. A file without clear reuse terms cannot be redistributed from this repository.
5. Verify the file in both the Windows and mobile versions.

Do not include game screenshots, extracted game assets, login information, or player backup data.

## Support levels

- **Community translation:** the JSON is available but may not have complete terminology or translated documentation.
- **Verified translation:** the JSON imports into both versions, placeholders are valid, key screens have been reviewed, and RTL behavior is checked when applicable.
- **Officially maintained language:** application text and essential GitHub guides are maintained with releases.

Documentation that is not available in a community language falls back to English. Application entries with an empty `text` value also fall back to English.
