# Research dataset migration status

Last verified: 2026-08-11

## Current boundary

Phases 0 through 6 are implemented inside the private monorepository. The
current desktop and PWA development sources both read `dataset/generated/`
through platform adapters. The PWA copy is synchronized under
`data/research-dataset/`, uses fixed IDs and recorded `display_connections`,
and contains no runtime slug or connection inference. Player backup,
research-directive, user language-pack, UI, and OCR formats remain unchanged.

The legacy catalog remains the controlled migration input until the dedicated
dataset repository is explicitly authorized. Files in
`dataset/baseline/`, `dataset/generated/`, and `dataset/reports/` are generated
artifacts and must not be edited by hand.

The pure compatibility mapping lives in
`repositories/research_dataset_adapter.py`. Both the comparison report and the
Phase 4 runtime repository call that shared implementation; there is no second
interpretation of the generated data.

## Verified result

- 16 research trees
- 399 frozen research IDs
- 3,143 level records
- Japanese and English names for every tree and research ID
- source and private-evidence metadata separated from facts
- prerequisites, 631 legacy source edges, and display connections kept as
  separate facts
- 16 representative dependency plans compared
- zero legacy/new value differences
- zero semantic validation errors
- 180 non-fatal source-data review warnings:
  - 120 empty-but-available legacy cost records (`empty_verified_costs`)
  - 60 higher-level value decreases (`level_value_decreased`)

The machine-readable result is
`reports/legacy-vs-generated.json`. Its `status` must remain `match`.
Its `warnings` array is a separate data-quality queue; it does not mean that
the converter changed those values.

## Deliberate interim choices

- Existing research IDs are copied explicitly and never regenerated from
  translated display names in the new format.
- Display connections preserve the current desktop loader result. They remain
  `provisional`; this does not claim that every line is already verified
  against a game capture.
- Source edges preserve all legacy edge pairs currently consumed by the
  desktop UI. They also remain `provisional` and are compared independently
  from planner prerequisites and grouped display connections.
- Effects preserve the exact legacy display value with `parsed: false` and
  `display_fallback`. Metric parsing is deferred so conversion cannot silently
  change visible effects.
- Guild Duel remains `structure_only` because the legacy catalog does not have
  per-level time and cost data.
- The single private economy capture is represented only by public-safe
  metadata. No private path or screenshot is copied into the dataset.

## Repeatable check

From the repository root:

```powershell
& .venv\Scripts\python.exe -B tools\RLMResearchPlanner\dataset\scripts\refresh_and_verify.py
```

This regenerates the compatibility dataset, validates it, and updates the
Phase 4 comparison report. A nonzero exit means the generated dataset must not
be used.

## Completed gate before Phase 4

The reviewed migration plan required the Phase 3 comparison to remain clean
across at least two real legacy-catalog updates. This proved that the converter
is maintainable rather than matching only one frozen catalog revision.

Current gate count: **3 recorded post-baseline catalog updates; 2 required**.
The distinct catalog hashes and comparison summaries are recorded in
`reports/catalog-update-gate.json`. Re-running the converter against the same
catalog hash is not counted. Both recorded updates were intentional data or
provenance corrections and retained `status: match` with zero differences.

With that gate met, Phase 4 added a desktop dataset repository and one
reversible input-selection point around the shared compatibility mapping. The
old loader remains available and must stay through the following PWA migration.
A public data repository is not created until the PWA adapter and release
pinning have also completed inside this monorepository.

## Phase 4 result

- Desktop default: bundled `dataset/generated/`
- Explicit rollback: `--legacy-research-catalog`
- Legacy and generated repositories produce equal
  `ResearchTreeObservation` tuples, including ordering and visible legacy
  status metadata.
- The executable build includes only `dataset/generated/`, not baselines,
  private reports, schemas, or migration notes.
- No automatic fallback hides a malformed generated dataset. Missing input
  retains the legacy repository's empty-result behavior; malformed input raises
  a clear `ValueError`.

## Phase 4 pre-release verification

The following non-GUI verification was repeated on 2026-08-11 after the
current UI, language-pack, layout, and disclaimer changes:

- dataset refresh and semantic comparison: 16 trees, 399 research IDs,
  3,143 levels, 0 differences, 180 review warnings
- deterministic regeneration: all 24 generated/report files retained the same
  SHA-256 values
- desktop non-visual suite: 182 passed; tree-view UI suite: 15 passed;
  data/adapter/planning/language subset: 49 passed
- PWA test suite: 72 passed
- desktop release-license check: passed
- PWA release-layout check: passed (0.1.0, 41 offline files, 399 nodes)
- desktop default generated input and explicit legacy input return identical
  `ResearchTreeObservation` tuples
- repository validation workflow added with read-only permissions; it repeats
  dataset regeneration, stale-output detection, desktop/PWA tests, source
  checks, and release-layout checks after the changes are pushed

This completes the checks that can be performed without opening an application
window or publishing a release. It does not by itself satisfy the maintainer
GUI smoke check or the real release-and-use gate below.

## Gate before Phase 5

The maintainer explicitly authorized completing the remaining data-foundation
work before the v0.1.0 publication. Phase 5 therefore switched the PWA to the
same generated dataset and added shared PC/PWA golden checks. Phase 6 verified
that research facts contain no localized name fields and that a third RTL
locale can be added without changing tree facts. The retained legacy inputs
are rollback and migration material only; the PWA no longer reads them.

## Remaining external boundary

The dataset package now contains portable schemas, a standalone validator,
license, contribution rules, and application-independent generated data. A
dedicated public repository has not been created because it is outside the
currently authorized workspace. Creating that repository and completing one
tagged dataset-to-application import cycle are Phase 7 publication operations,
not missing application implementation.
