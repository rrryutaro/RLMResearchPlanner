# Create and import a translation file

English | [日本語](../ja-JP/translation-files.md) | [File type guide](data-files.md)

A translation file adds or updates an RLMResearchPlanner display language. The same JSON works in the desktop and mobile versions. Importing it does not modify player settings, research levels, resources, or tasks.

OCR remains limited to Japanese and English. A custom translation affects the user interface and names from the research data only.

## 1. Export a template

- Windows desktop: open Translation File at the top of Help and select Export translation template.
- Mobile: open Translation File in the Player tab and press Export translation template.

The template is UTF-8 JSON with English source text.

## 2. Edit the metadata

```json
{
  "locale": "fr-FR",
  "name": "Français",
  "direction": "ltr",
  "fallback_locale": "en-US",
  "author": "Your name",
  "license": "CC0-1.0"
}
```

- `locale`: a BCP 47 language tag such as `fr-FR`, `ko-KR`, or `ar`.
- `name`: the name shown in the application language selector.
- `direction`: use `ltr` for left-to-right languages and `rtl` for right-to-left languages such as Arabic.
- `fallback_locale`: the language used for blank translations. Use `en-US` for the current version.
- `author` and `license`: identify the translator and reuse terms when distributing the file.

Do not change `document_type`, `schema_version`, or `catalog_dataset_id`.

## 3. Translate only `text`

```json
"tree.search_placeholder": {
  "source": "Search by research name",
  "text": "Rechercher une recherche"
}
```

- `source` is the English source and normally remains unchanged.
- Enter the translation in `text`.
- Do not rename keys or rearrange the JSON structure.
- Leave `text` blank when an entry is not translated. The application displays English instead.
- HTML containing `<` or `>` is not allowed.
- Escape line breaks and quotation marks according to JSON syntax.

The disclaimer body uses only the official Japanese and English text, so it is not included in translation templates. An `app.disclaimer` entry added to a translation file is ignored, and custom languages display the official English text.

## 4. Preserve placeholders

Placeholders such as `{name}`, `{level}`, and `{count}` in `messages` receive values at runtime. Every placeholder in the source must also appear in the translation.

```json
"plan.count": {
  "source": "{count} research tasks",
  "text": "Tâches de recherche : {count}"
}
```

Renaming or removing a placeholder causes an import error.

## 5. Sections

| Section | Contents |
|---|---|
| `messages` | Buttons, labels, guidance, and error messages |
| `categories` | Research category names |
| `research` | Research names |
| `buildings` | Building names |
| `effects` | Research effect names |
| `resources` | Resource and special-material names |

## 6. Import the file

- Desktop: select Import translation file from Translation File.
- Mobile: press Import translation file.

After a successful import, the application switches to the imported language and saves the selection for later launches. Import another file with the same `locale` to update it.

Removing a custom translation returns the display to English and does not delete player data.

## RTL languages

Set `direction` to `rtl` to change the reading direction of the interface. The physical layout of the research tree is not mirrored so it can still be compared with the game. Verify long labels, dialogs, and number inputs on an actual device.

## Checks before distribution

- The file imports into both desktop and mobile versions.
- Main tabs, research, buildings, and resources are translated.
- Long labels are not clipped.
- All placeholders are preserved.
- Inputs and dialogs remain readable in RTL mode.

See [`language-pack.schema.json`](../../schemas/language-pack.schema.json) for the machine-readable format definition.
