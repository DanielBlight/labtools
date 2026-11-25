# Fixed-window intensity-map counts (2026-11-25)

Baseline: bf2faa36380bc6b8c46400df265f2b2e84a63970.

The native multi-channel count API now uses cyclic input counters, with integration time set in milliseconds and mode/duration read back. Native workspace maps prepare counters after channel configuration and before opening the detector gate. The persistent shared-session adapter lazily prepares at the first pixel; later reads reuse the verified settings. Channel reconfiguration, reconnect and REC acquisitions invalidate the cache.

Per-pixel reads no longer reset counters or run REC. Raw counts and count-rate normalization by the verified requested duration remain unchanged. Single-channel get_counts/get_count_rate and histogram/streaming acquisition methods retain their previous acquisition implementation. No threshold, edge, coupling, laser-current limit, wiring, plot filtering or output format is changed.

Freshness policy: cyclic counters are free-running, not synchronized to mirror moves. After the caller moves and settles, the reader waits 2 * integration_time + 1 ms. Under last-completed-window counter semantics, this allows one full completed window entirely after settling at any cycle phase. Host delays do not extend the fixed hardware integration window. This is intentionally more conservative than the old animation interval, and costs about twice the integration time per pixel plus settling, queries and plotting. Stop is checked between pixels, so this wait adds to cancellation latency. Multi-channel windows are not guaranteed phase-aligned despite the historical get_simultaneous_counts method name.

Readback mismatch stops acquisition rather than silently normalizing by an incorrect duration. No automatic fallback to the old accumulation path exists. Verify actual controller readback and completed-window semantics during connected acceptance. Do not claim this removes detector-origin bursts or proves the screenshot's cause.

Validation: 103 offline tests passed, including 28 new command/timing-model/service/map-order tests, plus existing map simulation, shared-IDQ, shared-backend and workspace-transport tests. Run with --noconftest because the repository's autouse Qt fixture cannot run without PyQt6 in this environment. No real endpoint was contacted. Windows GUI/connected acceptance and Ruff remain pending.

Next bounded continuation prompt:
Review the Windows validation output and one small connected intensity map at the committed revision. Confirm cyclic mode and integration readback, preserved raw counts, expected roughly 2T per-pixel timing, Stop/cleanup, and optional output. Compare a stationary dark/steady-signal measurement and a small scan with the old code using the same input threshold, edge, integration time and optical conditions. Inspect raw outliers before concluding the timing repair removed the spikes. Do not add filtering or change detector/laser limits. Record only observed results.
