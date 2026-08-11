# RLMResearchPlanner research dataset

This directory contains the versioned, machine-readable research dataset used
by both the desktop and PWA applications. Both applications read the same
`generated/` release copy. Research IDs, facts, display connections, sources,
evidence metadata, and translations are validated as separate records.

`generated/trees/*.json` contains fixed IDs and research facts. Localized tree,
research, and metric names exist only in `generated/locales/*.json`; adding a
locale does not require editing a research tree. `DATA_LICENSE.md` defines the
data license boundary and `CONTRIBUTING.md` defines the review rules.

Run the standalone distribution check with:

```powershell
python -B scripts/check_distribution.py generated
```

## Phase 0 baseline

`baseline/` records the observable interpretation of the legacy
`data/research/catalog.json` used for compatibility checks. It is regenerated
only for an intentional catalog update; `research-ids.json` remains the frozen
identity set.

- `manifest.json` records the source catalog hash and baseline counts.
- `research-ids.json` freezes every currently generated research ID.
- `pc/categories/` records the desktop loader output by research tree.
- `pwa/categories/` records the PWA loader output by research tree.
- `pc/plans.json` and `pwa/plans.json` record one deterministic plan per tree.
- `platform-differences.json` records, rather than hides, current PC/PWA
  differences.

During Phase 0, `catalog.json` remains the only editable source of research
data.  Every file below `baseline/` is generated and must not be edited by
hand.  Neither application reads these files.

Generate the baseline in this order:

```powershell
& .venv\Scripts\python.exe -B tools\RLMResearchPlanner\dataset\scripts\export_pc_baseline.py
node tools\RLMResearchPlanner\dataset\scripts\export_pwa_baseline.mjs
& .venv\Scripts\python.exe -B tools\RLMResearchPlanner\dataset\scripts\compare_platform_baselines.py
```

The generators are deterministic: running them again without changing the
source catalog or loaders must leave the generated files unchanged.

## Phase 1 schema and validation

`schemas/` defines the proposed versioned format. `SPECIFICATION.md` records
the compatibility boundaries and the source-of-truth rules. The semantic
validator checks IDs, references, level coverage, negative values, dependency
cycles, aliases, required translations, verification evidence, and visual
connection endpoints.

The minimal example is deliberately small enough to review by hand:

```powershell
& .venv\Scripts\python.exe -B tools\RLMResearchPlanner\dataset\scripts\validate_dataset.py tools\RLMResearchPlanner\dataset\examples\minimal
```

## Versioned migration and compatibility copy

`generated/` is a deterministic conversion of the authoritative legacy
catalog. It contains one file per tree plus separate locale, source, evidence,
alias, and manifest documents. It is not hand-edited. The desktop development
application reads it through the compatibility repository; the PWA reads the
same documents through its JavaScript adapter.

`reports/legacy-vs-generated.json` records the semantic comparison. The report
must stay at `status: match` before an application adapter or cutover is
considered. The comparison covers every current research value, all 631 legacy
source edges, every grouped visual connection, and one dependency plan per
tree. Verification labels are mapped to the new vocabulary and therefore
compared by meaning rather than by their old strings.

The same report also lists non-fatal data-quality warnings. The current legacy
data produces 120 `empty_verified_costs` warnings for empty-but-available cost
records and 60 `level_value_decreased` warnings when a time, power, academy
level, or resource cost decreases at a higher research level. These values are
not rewritten: some may be legitimate game data and others may need new
evidence. Warnings therefore require review but do not masquerade as migration
differences.

Generate and verify the migration copy with:

```powershell
& .venv\Scripts\python.exe -B tools\RLMResearchPlanner\dataset\scripts\refresh_and_verify.py
```

The converter, validator, and comparator remain separately executable for
diagnosis, but the command above is the normal migration check.

The repository workflow
`.github/workflows/rlmresearchplanner-validation.yml` repeats this check for
changes to either application. It rejects stale generated files, then runs the
desktop and PWA tests, license checks, JavaScript syntax checks, and PWA release
layout checks. The workflow has read-only repository permissions and does not
publish an application or dataset.

The legacy `data/research/catalog.json` remains the migration input until the
dataset is moved to its dedicated repository. It is not read by either default
application path. The generated-dataset-to-observation mapping is
shared by the comparison code and desktop runtime repository. The legacy
desktop loader remains available through `--legacy-research-catalog` as a
temporary rollback path. The PWA does not generate IDs or connections at
runtime and its offline cache contains the versioned dataset documents.
