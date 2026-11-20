# Repository hygiene

## Active policy

- Project export tooling lives in `scripts/development/`.
- Local source bundles such as `labtools_source_*.txt` are not tracked.
- Guarded updater backups such as `*.before_*` are not tracked.
- Python, pytest, Ruff, build and virtual-environment artefacts are not tracked.
- Operator-generated measurement output should not be added to Git unless it is a
  documented test fixture under `tests/fixtures/`.

## Deliberately retained pending separate decisions

- `.labtools-migrations/` is retained as migration/audit evidence. A later archival
  decision may move it to `docs/history/` or a separate evidence repository.
- The legacy root `main.py` spectrum launcher has been removed; use `uv run labtools gui spectrum`.
- Audited operator-generated intensity-map output was removed from `data/`; future measurement output is ignored.
- Vendored IDQ and Cryostation material is retained pending licence and provenance review.

## Release rule

A release candidate must be built from a clean working tree. Generated output,
local export bundles, updater backups and test caches must remain outside the release
commit.
