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
- `main.py` is retained temporarily as a legacy spectrum-launch compatibility shim.
  Remove it only after confirming that no external shortcut or operator procedure uses it.
- Existing files under `data/` are retained until each is classified as either a test
  fixture or generated operator output.
- Vendored IDQ and Cryostation material is retained pending licence and provenance review.

## Release rule

A release candidate must be built from a clean working tree. Generated output,
local export bundles, updater backups and test caches must remain outside the release
commit.
