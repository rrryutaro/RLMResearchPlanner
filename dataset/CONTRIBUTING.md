# Contributing research data

Research data changes must be reviewable, attributable, and reproducible.

## Required for every change

1. Use existing fixed IDs. Never derive an ID from a translated name and never
   reuse a retired ID.
2. Change research facts in the relevant tree document and display text in a
   locale document. Do not put translated research names in tree files.
3. Record the source in `sources.json`, or reference an existing source ID.
4. Choose the honest verification status: `verified`, `cross_checked`,
   `provisional`, or `disputed`. Do not promote a value merely because a URL
   exists.
5. Do not submit screenshots or files containing player, guild, account, or
   filesystem information. Public metadata may refer to a private evidence ID.
6. By contributing adapted research data, you agree that it may be distributed
   under CC BY-SA 3.0 as described in `DATA_LICENSE.md`.

## Required checks

Run the standalone distribution check before submitting a change:

```powershell
python -B scripts/check_distribution.py generated
```

It checks the JSON Schema, fixed references, cycles, level coverage, values,
translation coverage, source/evidence rules, and the separation of facts from
localized display names. Warnings must be explained in the change description;
they must not be silently rewritten.

The maintainer reviews all facts and evidence before a dataset release is
tagged. Merging a contribution does not automatically publish it to either
application.
