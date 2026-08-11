# RLM research dataset specification draft

Status: Schema v2 implemented. Both application development versions read this
format through platform adapters; publication remains a separate release step.

## Compatibility boundaries

The dataset has its own `schema_version` and `dataset_version`.  These versions
must never be coupled to the application backup or research-directive schema
versions.  Existing research directives and player backups continue to use
their current document formats.

Research IDs already produced by the application are immutable.  They are
declared explicitly in the new dataset and are never generated from a display
name at runtime.  A released ID is never reused.  When an unavoidable ID
replacement occurs, the old ID remains in `id-aliases.json` and resolves to one
active ID.

## One editable source

Only one representation may be edited by people at a time.

- During Phases 0–3, the legacy `catalog.json` is authoritative and the new
  dataset is generated from it.
- After an explicit cutover, the tree files become authoritative and the
  legacy catalog may only be generated as a compatibility artifact.

The source-of-truth transition must be atomic.  There is no phase in which both
representations are edited manually.

## File granularity

The editable dataset uses one file per research tree.  Locale strings, sources,
evidence, aliases, and the manifest are separate.  Applications receive one
generated and fully interpreted `dist` document so that Python and JavaScript
do not independently infer IDs or visual connections.

## Semantics

`prerequisites` are the dependencies used by planning calculations.
`source_edges` preserve the legacy category edge pairs consumed by the desktop
UI for edge activity and fallback rendering. `display_connections` are the
fully grouped visual buses drawn by the tree UI. These three collections are
independent facts. Applications must not infer or replace one from another.

Tree coordinates are physical game-layout coordinates and do not change with
the UI writing direction.  Locale files control text direction.  Whether a
specific game locale mirrors the physical tree remains an observation question
and is not encoded by changing the canonical coordinates.

## Unknown, uncollected, and zero

- `0` means that zero was confirmed.
- `null` means the field was investigated but the value is unknown.
- An omitted field means it has not been collected for that record.
- `coverage` declares whether a tree is complete, partial, or structure-only.

These states are not interchangeable.  Generators and applications must not
replace `null` or an omitted value with zero.

Tree `coverage` describes level-record coverage, not whether every scalar in
those records is known. `complete` means that every level record from 1 through
`max_level` exists; individual fields may still be `null`. `structure_only`
means that no level records may be present.

During legacy migration, cost availability follows this compatibility rule:

- legacy `costs_verified: false` with an empty cost map becomes `costs: null`;
- legacy `costs_verified: true` becomes a non-null cost object, including `{}`;
- the compatibility adapter reconstructs the legacy availability flag as
  `costs is not null`.

The legacy flag describes whether the planner may treat the cost record as
available; it is not promoted to the new dataset's evidence-backed `verified`
status. A non-empty but not directly verified cost record remains representable
with non-null `costs` plus `verification_overrides.costs: provisional`. The 120
legacy levels that currently map to an empty non-null cost object are preserved
for behavior compatibility and emitted as `empty_verified_costs` review
warnings rather than being silently changed to zero or unknown.

## Verification and lifecycle

Verification status is one of:

- `verified`: directly checked against game evidence.
- `cross_checked`: at least two independent references agree.
- `provisional`: collected but not directly verified or independently
  cross-checked.
- `disputed`: references conflict; the distributed value is the selected
  working value and the reason is documented.

Deprecation is a lifecycle state, not a verification state.  A deprecated
record uses `lifecycle.state: deprecated` and may identify `superseded_by`.

A tree or level may declare default verification.  `verification_overrides`
may refine `time`, `costs`, `requirements`, `effects`, or `layout` only when
those facts have different provenance.  This avoids both false provenance and
metadata repeated for every scalar value.

While the legacy catalog remains the editable source, a level may carry a
transitional `source_urls` object whose `time`, `costs`, and `requirements`
members are a URL or URL list. Every referenced URL must also be declared in
the catalog-level `sources` list. The converter resolves those URLs to stable
source IDs and writes fact-specific `verification_overrides`. A source URL by
itself remains `provisional`; it is not promoted to `verified` without direct
evidence or to `cross_checked` without an exact independent match.

The Phase 2 converter uses this explicit legacy mapping:

| Legacy value | New status | Migration rule |
| --- | --- | --- |
| `sourced` | `provisional` | A cited source exists, but direct evidence or a second independent source is not established per value. |
| `sourced_partial` | `provisional` | Preserve collected values and mark omitted or unknown fields without inventing zeroes. |
| `sourced_conflict_corrected` | `disputed` | Preserve the selected legacy correction and require an explanatory note. |
| `sourced_conflict_omitted` | `disputed` | Preserve the omission/unknown and require an explanatory note. |
| category-level legacy labels | `provisional` | Preserve their scope as notes; do not promote them to verified automatically. |

This mapping deliberately does not equate “has a URL” with verification.
`verified` requires direct evidence metadata, and `cross_checked` requires at
least two distinct references.

During Phase 2, effect `metric_id` values are placeholders based on the frozen
research IDs. Japanese metric labels reuse the research display name, and raw
effect values use `unit: text`, `parsed: false`, and a required
`display_fallback`. These are migration-preservation fields, not a finalized
metric vocabulary or confirmed effect translation.

## Evidence and licensing

Data records refer to normalized source and evidence IDs.  Public evidence
metadata does not contain private filesystem paths or game screenshots.
Redistribution permission is explicit.  Fandom-derived data retains the
applicable CC BY-SA 3.0 attribution and share-alike boundary.

The legacy catalog stored only a dataset-wide `checked_on` date. Phase 2 uses
that value as an approximate `retrieved_on` for each migrated source and records
the approximation in the source notes; it must not be read as an independently
recorded per-source retrieval date.

## Release policy

Applications bundle a tested dataset release.  They do not read a development
branch at runtime.  `schema_version` describes structural compatibility;
`dataset_version` describes the content release.  A bad content release is
rolled back by rebundling the previous verified dataset artifact.

## Phase 4 adapter rule

The generated-dataset-to-observation mapping is implemented once in
`repositories/research_dataset_adapter.py`; the Phase 3 comparator already
uses it. The first runtime dataset repository must call this same mapping.
Reimplementing the mapping independently is not permitted because a round-trip
comparison cannot protect behavior that uses a different interpretation at
runtime.

The compatibility observation model currently represents at most one effect
per research node. The adapter fails explicitly when a dataset node contains
multiple effects, rather than silently dropping additional effects. Supporting
multiple effects in the application requires a separate domain/UI extension
before such a dataset can be selected at runtime.

During Phases 4 and 5, generated trees also retain a narrow
`legacy_compatibility` block and level `legacy_verification_status`. These
fields preserve metadata that the current UI exposes but that is intentionally
not part of the new verification vocabulary. Runtime adapters prefer these
fields so changing the storage format does not change visible status text or
planning warnings. They are transitional compatibility data, not the future
canonical verification model, and may be removed only together with the old
UI/status contract in a later schema version.

## Translation boundary

Tree documents must not contain localized display-name fields. Tree titles,
research names, and metric labels are keyed by fixed IDs in locale documents.
Required locales contain every active tree, research, and metric ID. Optional
locales may be partial and fall back to their declared `fallback_locale`, then
to `en-US`. `direction` controls UI text direction only; it does not mirror
physical research-tree coordinates.

Effect `display_fallback` remains permitted while an effect is `parsed: false`.
It preserves an observed value, not a translated research or metric name.
