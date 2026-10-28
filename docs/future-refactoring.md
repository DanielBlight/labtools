# Future refactoring

> Historical batch/backlog note. Current implementation status and task order are
> authoritative in [architecture](architecture.md), [roadmap](refactor-roadmap.md)
> and [handover](ai-handover.md). Technical details below are retained for context.

This is a backlog, not a list of implemented features. See architecture.md for
current boundaries and refactor-notes.md for the completed cleanup.

1. Shared application/session ownership and whole-measurement reservations.
   Start with mirror control and intensity mapping; coordinate LabJack users.
2. Persistent instrument workers with explicit thread/event-loop ownership.
   Preserve HORIBA's connect/use/disconnect loop affinity.
3. Compose the large GUI windows from panels and controllers incrementally.
   Add Qt interaction tests before moving signal wiring and close-event logic.
4. Extend explicit simulation to additional workflows with tested contracts.
   Camera, annealing, shutter, stage, spectrometer and laser are not simulated.
5. Extend spectrum regression coverage to installed vendor stitching and Qt
   interactions, then separate output/checkpoint services where useful.
   Offline combination/dark-order coverage is now in test_spectrum_processing.py.
6. Review remaining hardcoded defaults and dependency groups separately.
   Do not change laboratory limits or split dependencies without local testing.

Previously stale statements that the README was empty, xarray was undeclared,
or only IDQ tests existed have been removed. No persistent connection manager
or universal instrument simulation is introduced by this cleanup.

