# RLMResearchPlanner

[日本語](README.md) | English

RLMResearchPlanner is an unofficial research and construction planner for *Lords Mobile*. It is available as a Windows desktop application and a browser-based mobile version. Both versions use the same research and building data and exchange compatible JSON files.

The current `v0.1.1` release is an alpha version. Its main features are usable, but its features, interface, and bundled data remain under active verification and improvement.

This project is not affiliated with IGG or the game operator. Game names, trademarks, and other rights belong to their respective owners.

## Use the application

- Download the Windows version from [GitHub Releases](https://github.com/rrryutaro/RLMResearchPlanner/releases).
- Open the [mobile version](https://rrryutaro.github.io/RLMResearchPlanner/) in a phone, tablet, or desktop browser. It is a PWA and can optionally be added to the home screen.
- OCR-assisted input is available only in the Windows version. Planning, settings, and data-sharing features are otherwise shared by the desktop and mobile versions.

## Required initial settings

Enter your VIP level, research speed, and construction speed in Player Settings for accurate time calculations. Use the in-game values for the equipment and temporary speed boosts that will actually be active.

On first launch, the application chooses a display language from the operating system or browser preferences. It falls back to English if no supported language matches. A language selected by the user is saved and is not overwritten by later automatic detection.

## Data exchange and translations

- [Data export and import file types](docs/en-US/data-files.md)
- [Create and import a translation file](docs/en-US/translation-files.md)
- [Contribute a community translation](translations/community/README.md)

Backups, research directives, paid-offer comparisons, and translations have different import behavior. Read the corresponding guide before sharing a file with another user.

## Data and privacy

- The desktop version stores settings and player data beside the application.
- The mobile version stores data in the current browser.
- Data is not synchronized to a cloud service automatically. Export a backup before changing devices.
- OCR captures the screen only after a user action. The application does not attach to the game process, read game memory, or automate game input.

## Current limitations

- OCR is an input aid and does not yet recognize every environment, screen, or research item reliably. OCR verification currently covers Japanese and English. Show the same research category in the game and the tool, and always verify recognized values.
- Operation has been verified with game version `v2.200.309`; later game updates may change values or layouts.
- Research time or resource values that cannot be confirmed from a published source remain explicitly unrecorded rather than being estimated.
- The Guild Duel tree structure is included, but its level-by-level time, resource, and dedicated-material data is not yet recorded.
- The unsigned Windows executable may trigger a Microsoft SmartScreen warning.

## Important notice and disclaimer

This is a free, unofficial tool. Its data and calculations are provided for reference and are not guaranteed to be accurate. Verify the current in-game screen before spending money, gems, or scarce items, and use the tool at your own discretion. Except where liability cannot be excluded by law, the developer is not liable for loss arising from its use.

## Reporting problems

Use [GitHub Issues](https://github.com/rrryutaro/RLMResearchPlanner/issues) for ordinary bugs and data corrections. Do not disclose a potentially exploitable security issue in a public issue; follow the [security policy](SECURITY.md) to report it privately.

## Acknowledgements

Parts of the research and building dataset are structured from information maintained by contributors to the [Lords Mobile Wiki on Fandom](https://lordsmobile.fandom.com/wiki/Research). We thank those contributors for recording and maintaining this information over the years.

Those portions are provided under CC BY-SA 3.0. Their sources, modifications, and license boundary are documented in [Data licensing and attribution](DATA_LICENSE.md). Values that cannot be confirmed from a published source are not filled with estimates.

## License

- Application code: [MIT License](LICENSE)
- Research and building data: [Data licensing and attribution](DATA_LICENSE.md)
- Distributed third-party components: [Third-party notices](licenses/THIRD_PARTY_NOTICES.md)
