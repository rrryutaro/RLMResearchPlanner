# Exported and imported files

English | [日本語](../ja-JP/data-files.md) | [Detailed translation guide](translation-files.md)

RLMResearchPlanner exports several JSON document types. Files with the same extension do not necessarily have the same purpose or import behavior.

## File types

| Type | Main contents | Import behavior |
|---|---|---|
| Backup | Player settings, resources, research and building levels, talent plan, registered tasks, and paid offers | Replaces the current player data with the backup. Export the current state before restoring another backup. |
| Research directive | Named research tasks | Keeps current settings and levels and adds or updates only the tasks. Completed research remains complete and only missing requirements are recalculated. |
| Talent directive | Talent acquisition order and target levels identified by stable IDs | Replaces only the talent plan without changing research levels or player settings. Required talents are inserted before dependent talents. |
| Paid-offer comparison | Paid offers and/or comparison-point settings | Imports into the paid-offer comparison without replacing player settings or research levels. Duplicate offers are ignored. |
| Translation file | UI text, research, talent and category names, buildings, effects, and resources | Adds or updates a display language. It does not modify player data. |

## Where to find the commands

### Windows desktop version

- Backup: Player Settings tab
- Research directive: Research Plan tab
- Talent directive: Talents tab
- Paid-offer comparison: Share view in the Paid tab
- Translation: Translation File menu at the top of Help

### Mobile version

- Backup, research directive, and translation: Player tab
- Talent directive: Talents tab
- Paid-offer comparison: Share view in the Paid tab

## Share with another device or user

Use email, messaging, cloud storage, or another file-sharing method. RLMResearchPlanner does not upload exported files automatically.

A backup does not contain a game login or password, but it can contain progression, stored resources, and paid-offer candidates. Do not send it to someone who should not see that information.

## If a file cannot be imported

- Confirm that the document type matches the import command you selected.
- If the JSON was edited manually, save it as UTF-8.
- Import old files with a current application version and export them again when possible.
- Export a backup first if you may need to restore the current state.
