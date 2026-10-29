# Device-wrapper audit: evidence and rewrite decisions

> Historical findings below predate W2. HORIBA startup/independent cleanup is now
> repaired/offline-tested. Timeout/exposure policy and all other open findings remain.
> See [W2 checkpoint](horiba-lifecycle-checkpoint.md).

> Historical audit below describes the pre-W1 snapshot. ITC transport startup/close
> defects are now repaired and fake-tested; finite-input W1b and all other wrapper
> findings remain open. See [W1 checkpoint](itc4000-lifecycle-checkpoint.md).

## Scope, starting state and decision

Input: `labtools_source_20261028_215033.txt`, created 2026-10-28T21:50:33.8045255Z,
branch `feature/shared-instrument-session`, HEAD
`ceaabec9ea4882c1882f71facf604a04099a5992`, upstream +0/-0.
Recorded tracked worktree and index are clean. Three installers are untracked:
`apply_labtools_alignment_lifecycle.py`, `apply_labtools_comparative_audit.py` and
`apply_labtools_deployment_docs.py`. Preserve them and all live unrelated changes.
No .git directory is included in the snapshot; live Git cannot be inspected here.

The attachment could not be opened through the enterprise content endpoint (412),
but its complete local text was available and reconstructed directly. No separate
complete local Qt pass log is embedded. Documentation describing earlier skips is
historical evidence, not a local pass. Gate rerun: 15 passed, 4 skipped. All four
QtWidgets modules still skip because libGL.so.1 is missing. The requested acquisition
gate is NOT met. No collision-allocation or wrapper runtime changes were made.

The additional wrapper audit is independent static/fake-method analysis. It covers all
12 Python files in devices/: ten substantive modules and two package initializers.
It does not certify vendor implementations, external consumers, physical devices or
thread safety under real SDKs. The report is about code, not its authors.

**Recommendation:** targeted lifecycle/validation repairs for most wrappers, a staged
internal decomposition for IDQ/DLT, and no blanket replacement. Rewriting everything
would discard established command/optical semantics without sufficient device evidence.
The current wrappers pass Ruff; style cleanliness is not evidence of lifecycle safety.

## Severity and evidence labels

- P0: security-sensitive parsing requiring prompt isolated remediation.
- P1: demonstrated lifecycle/cleanup/partial-operation defect or important control gap.
- P2: validation, import, compatibility or coverage improvement.
- P3: documentation/maintenance cleanup.
- CONFIRMED: source inspection plus an extracted-method fake-handle probe.
- SOURCE: directly visible control flow; no physical outcome claimed.
- REVIEW: policy/vendor/physical evidence needed before changing behaviour.

Eight offline probes executed original methods extracted with AST and fake handles.
They do not import real SDKs, open devices, send commands to endpoints or replace full
module integration tests. No production method was modified to make a probe pass.

## Findings and per-wrapper decisions

### 1. ITC4000: retain API, repair lifecycle first (P1/P2)

Evidence: `devices/itc4000.py`, ITC4000.__init__, close, __exit__, set_current.

CONFIRMED: ResourceManager is created before open_resource without a startup cleanup
boundary. An open_resource failure does not close the manager. An initial *CLS failure
after resource creation closes neither handle. NaN threshold_current passes the
constructor's comparison-only validation and reaches fake resource creation.
CONFIRMED: if instrument.close and manager.close both fail, the manager error replaces
the instrument error; _closed remains false. __exit__ can replace a body failure.

Keep: one VISA session, command strings, current in amperes, checked *OPC?/error/readback
sequence, output-off-before-threshold reset, default TEC policy, limits and address.
Do NOT equate transport close with laser-off or add emission/TEC commands to close.

Decision: no full rewrite. First repair partial construction, independent close attempts
and primary-error retention. Add finite validation as a separate reviewed behaviour
change; NaN/Inf tests must run before opening resources. Do not infer that set_current
itself accepts NaN: its chained bound check rejects it; the demonstrated issue is
constructor validation. Review temperature/pulse setters individually, not by analogy.

### 2. HORIBA: retain optical/acquisition API, harden async lifecycle (P1)

Evidence: devices/horiba_spectrometer.py, connect, disconnect, configure,
set_exposure_time, reset, _wait_for_ccd, _wait_for_mono, __aenter__/__aexit__.

CONFIRMED: DeviceManager.start is outside connect's cleanup try. Failure there does
not call disconnect. A CCD close exception prevents mono.close, is logged/suppressed,
and disconnect returns normally if manager.stop succeeds. This can hide a cleanup
failure from the backend/worker's existing fault marker. Adapter tests with fake
spectrometers do not prove that the real wrapper reports those errors.
SOURCE: connect catches Exception, not asyncio.CancelledError. Cleanup may replace
an original connect error. disconnect does not clear device references; repeat close
behaviour is not defined. _wait_for_ccd/_wait_for_mono/reset busy loops have no overall
deadline. Direct set_exposure_time stores the requested seconds before SDK success
and does not enforce the preset floor; canonical alignment requests do enforce it.

Keep: preset detector identity, grating/mirror/ROI tokens, readback checks, slit units,
exposure conversion, dark capture order and existing sleeps unless SDK evidence supports
change. Preserve Syncerity 0.065 s and Symphony 0.1 s; no 0.02 s override.
Decision: staged lifecycle repair, not optical rewrite or persistent connection caching.
Attempt independent closes on the owning loop, retain primary/cancellation plus cleanup
failures, and define retry/idempotence deliberately. Any new timeout must be a reviewed
configurable policy, not an invented universal number. No forced thread cancellation.

### 3. IDQ controller: staged internal decomposition, keep public facade (P0/P1)

Evidence: devices/idq_time_controller/controller.py, get_histogram, connect,
disconnect, _run_record, _cmd/_query, stop_timestamp_stream, DLT startup helpers.

SOURCE P0: get_histogram evaluates the raw HIST:DATA? response with eval(raw).
A response is being interpreted as Python rather than parsed as a bounded data grammar.
This is security-sensitive if response text is malicious or compromised; no exploit
or compromised instrument was observed. Do not use untrusted histogram responses.
The inspected vendor histogram examples also use eval; they are not response fixtures
and do not establish a safe grammar. Replacing it is urgent but requires representative
accepted response fixtures and
explicit shape/type/size/range rules. Do not assume JSON or blindly substitute
literal_eval without checking firmware syntax and accepted integer values.

SOURCE P1: _run_record polls PLAYING without an overall deadline. disconnect begins
with stop_timestamp_stream before independent transport cleanup; an escaping stop
error can prevent later cleanup. Several socket/context/process close failures are
logged and swallowed. connect has no wrapper-level guard against repeated connection
or partial ZMQ construction failure. A REQ timeout can leave request/reply sequencing
uncertain; automatic retry/reconnect is not established by current code.
SOURCE: stream clients are joined with timeout, then references cleared without an
is_alive check. Process kill fallback does not establish a completed wait/reap.

Keep: public IDQTimeController import, SCPI spelling/order, numeric units, integration
count ordering, channel conventions, array dtypes and callback semantics. Shared count
ownership remains in InstrumentSession; do not introduce another resource manager.
Decision: not one big rewrite. First bounded parser hardening with fixtures, then
transport/cleanup, then explicit DLT process/stream ownership behind the existing facade.
Do not combine count-service repair with streaming migration or silently fall back to
synthetic counts. Shared canonical IPv4 policy is an application restriction, not proof
that every underlying transport rejects hostnames.

### 4. IDQ DLT: staged ownership/stop redesign (P1)

Evidence: devices/idq_time_controller/dlt.py, dlt_connect, StreamClient.run/join.

SOURCE: dlt_connect creates a context but returns only a socket; it launches a process
with stdout=PIPE and discards the process handle. This helper therefore has no explicit
owner for draining output, terminating/reaping a process it launched, or closing the
context on failure. A pipe could block a sufficiently verbose child; this was not
reproduced against the vendor process. The controller has a separate DLT launch path,
so both paths need a consumer inventory before consolidation.

SOURCE: StreamClient.run sets _running=True after socket setup; join sets it False.
An early join can be overwritten by the thread's later True assignment. join is both
stop request and wait, contrary to ordinary caller expectations. Setup precedes the
try/finally; teardown is sequential and can skip later closes after an earlier error.
Callback failures have no structured result channel to the owner. A callback can block.

Decision: a small owned DLT-session abstraction plus explicit stop Event is justified,
but migrate behind compatibility adapters and preserve StreamClient callback/import
contracts. Track whether the process was started here; never kill an externally owned
service. Keep process/thread/context cleanup on their correct owners. Do not promise
hard cancellation of callbacks or sockets. Test startup-stop races and post-timeout
is_alive state; never clear ownership of a live thread merely because join returned.

### 5. SC10: keep serial protocol, repair failure boundaries (P1/P2)

Evidence: devices/sc10.py, connect, close, _exchange, toggle_enable, set_enabled, get_state.

SOURCE: connect calls close in an exception handler without retaining the primary if
close fails. close drops _serial before connection.close completes; failure loses the
wrapper's handle. Timeout/baud inputs are coerced without explicit finite/range policy.
_exchange resets input, writes command+CR and reads a prompt; only echo cases have
focused extracted-method offline coverage. Existing SC10 mode tests are hardware-only.

Keep: mode/trigger enums, prompt/echo handling, enable toggle/readback semantics and
physical shutter status distinction. close releases transport; it does NOT mean
close_shutter or disable. Do not silently change shutter state on context exit.
Decision: targeted serial lifecycle and fake-transcript tests, not a protocol rewrite.
Validate against real captured responses before broadening parser tolerance. Do not
retry a toggle command after uncertain completion without reviewed state readback.

### 6. UC480: keep frame ownership and shutdown aggregation, repair partial start (P1/P2)

Evidence: devices/uc480_camera.py, connect, start_live, stop_live, close,
set_exposure, _prepare_frame.

CONFIRMED: start_live calls setup/start before setting _live=True. If start raises,
close sees live=False and calls camera.close but does not explicitly stop acquisition.
Whether camera.close alone fully unwinds a partial vendor start is unknown; this is
not a claim that a camera remained live. SOURCE: connect cleanup can replace the
original error. References are cleared before close finishes, so cleanup failure is
not retryable through the current wrapper. Finite exposure/gain and buffer coercion
policy needs review. Discovery says first available but connect uses cam_id=0; confirm
selection policy rather than silently selecting a different camera.

Keep: existing stop+close aggregation, owned C-contiguous frame copies, horizontal
mirror convention, seconds/readback semantics and lazy vendor import.
Decision: targeted partial-start/exception work, not rewrite. Define explicit acquisition
setup/live state and vendor-supported rollback; add failure injection at each stage.
Do not regress the existing independent stop/close attempts or frame-copy tests.

### 7. Kinesis rotation stage: retain native-unit API, tighten validation (P2)

Evidence: devices/kinesis_rotation_stage.py, __init__, connect, close, move_to, _module.

SOURCE: move_timeout_s <= 0 does not reject NaN; move_to converts position but does not
validate finite values or enforce instrument-specific limits. The anneal profile has
workflow limits, not universal native-unit wrapper calibration. close clears _stage
before stage.close succeeds. Connect wraps errors, and __exit__ may mask a body error
with close failure. _module suggests uv add as an error remedy, unsuitable for a
protected production install. Selection requires exactly one discovered device.

Keep: native controller units, exactly-one selection, no implicit homing, stop/move/wait
ordering, get_position behaviour and lazy import. Do not introduce degrees or guessed
travel limits. Decision: targeted validation/lifecycle/docs, not a full rewrite.

### 8. LabJack U6: retain narrow owner; extend failure tests (P2)

Evidence: devices/labjack_u6.py, __init__, close, __enter__/__exit__, pass-throughs.

Positive: calibration failure attempts cleanup and retains a cleanup note; close is
idempotent after success. SOURCE: __exit__ can mask a body exception if close fails;
pass-throughs have no explicit closed-state guard; u6 import is eager at wrapper import.
If u6.U6 itself fails before returning a handle, cleanup inside that vendor constructor
is not something this wrapper can prove or repair by guessing a handle.

Keep: one U6 connection, calibration and startup delay, shared borrowing by mirror/gate,
I2C/DIO semantics and no automatic output motion on close. Runtime factories already
provide a lazy import seam. Decision: no rewrite; narrow tests/guards as a separate task.

### 9. ScanningMirror / LJTick-DAC: retain calibration maths, preflight both axes (P1/P2)

Evidence: devices/scanning_mirror.py, _load_cal_constants, _to_double,
set_voltages, ScanningMirror.move/home.

CONFIRMED: set_voltages converts/writes axis A before converting B. A NaN B can raise
after A has already been sent. SOURCE: no preflight finite/range checks for both DAC
codes; byte bounds depend on calibration and requested voltage. EEPROM response length,
finite slope/offset and I2C acknowledgement validation are incomplete. The '255 anywhere'
heuristic is not proof of valid/invalid calibration; obtain vendor format evidence before
changing it. A second physical I2C write may fail even after valid preflight, so two-axis
movement cannot be claimed atomic.

Keep: EEPROM/DAC addresses, pin pairing, byte encoding, channel order, conversion formula
and home=(0,0). Home is movement, not a universal safe state. No guessed clipping or
automatic rollback movement. Decision: preflight/diagnostics with byte-exact fixtures,
not a maths/protocol rewrite. Report partial-axis failure explicitly.

### 10. SPADGate: keep tiny borrowed-device adapter (P2/P3)

Evidence: devices/spad_gate.py, __init__, open, close.

Positive: it borrows LabJack and never owns/disconnects it. close means drive the gate
low, unlike transport close in other wrappers. SOURCE: no local pin validation or
state/readback; its default pin 0 differs from some reviewed application wiring, so
explicit wiring matters. High/low meaning is a wiring contract, not measured state.
Decision: no rewrite. Add fake DIO/pin-policy tests and document borrowed ownership.
Do not unify all close methods under one generic device base class.

### Package initializers

`devices/__init__.py` is empty. `devices/idq_time_controller/__init__.py` re-exports the
controller and therefore imports its NumPy/ZMQ/DLT dependencies. Preserve the public
import path; any future lazy re-export requires import-compatibility tests. No reason
for a broad package rewrite was established.

## Existing test evidence and gaps

- test_reliability_regressions extracts camera close/frame methods and SC10 echo logic.
  It does not import/construct complete real wrappers against fake transports.
- test_comparative_audit tests IDQCountService partial startup using a fake controller,
  and cancellation/disconnect faulting using a fake spectrometer. It does not prove
  the real IDQ/HORIBA wrapper exposes failures that it currently swallows.
- test_spectrum_service tests adapter command ordering/cleanup with injected fakes.
- test_shared_idq_phase3b and session tests validate ownership using fake resources.
- test_project_structure includes real LabJack constructor logic with fake u6 and
  import/entry-point isolation. Existing hardware tests are excluded before imports.
- Kinesis and ITC whole-wrapper fake-transport lifecycle coverage was not found in the
  inspected tests. External/private tests are unknown. Native behaviour remains untested.

Do not convert these findings into 'hardware unsafe' verdicts or claims of device
failure. They are code-level risks with specified evidence and missing acceptance.

## Validation in this checkpoint

- Qt gate: 15 passed, 4 skipped; all four QtWidgets modules unavailable (libGL.so.1).
- Full offline suite: 318 passed, 4 skipped, 172 inherited Matplotlib/pyparsing warnings.
- Eight extracted-method fake-handle probes confirmed the observations listed below.
- Device Ruff check: passed. Device format check: all 12 files already formatted.
- Compileall, CLI help, TOML parsing, native-free smoke, wheel build and relative
  Markdown target validation are recorded in wrapper-audit-checkpoint.md.
- Python 3.12.15; temporary PyQt6 6.11.0 and Ruff 0.17.3. This is not the exact
  locked Windows environment. No lockfile/dependency changes were made.

No hardware tests, diagnostics, discovery, firmware actions, lab-PC deployment, account/
ACL changes or physical endpoints were used. No wrapper/acquisition/test Python was
changed. Current live Git status must be inspected by the maintainer before applying.

## Rewrite order and continuation

See [repair plan](device-wrapper-repair-plan.md) for bounded commits, compatibility
contracts, fake tests, physical gates and the first task prompt. Do not bundle all
wrappers into one rewrite or create a new general resource manager.

Acquisition lane: QtWidgets pass evidence first, then collision-safe map allocation.
Independent wrapper lane: first ITC transport startup/teardown repair, then HORIBA
cleanup, with IDQ parser hardening prioritized as a separate fixture-backed task.
The wrapper lane is permitted by the user's added audit request; it does not waive
or satisfy the acquisition gate. No wrapper repair is implemented in this checkpoint.

## Offline probe results

CONFIRMED: ITC open_resource failure does not close ResourceManager.
CONFIRMED: ITC initial CLS failure does not close instrument or ResourceManager.
CONFIRMED: ITC NaN threshold passes constructor validation and opens fake resource.
CONFIRMED: ITC manager-close failure replaces instrument-close error and leaves closed flag false.
CONFIRMED: HORIBA CCD close failure skips mono close and returns normally if manager.stop succeeds.
CONFIRMED: HORIBA manager.start failure is outside connect cleanup try block.
CONFIRMED: invalid DAC B value can raise after DAC A write has already occurred.
CONFIRMED: UC480 partial start failure leaves live false; close calls camera.close but not explicit stop.


## Consumer inventory (first-party imports)

Generated by AST import scanning across src, tests, scripts and examples. Includes
type-only and local imports; does not imply execution. Dynamic imports, user scripts
and vendor consumers may exist and require separate checks before API retirement.
Line numbers below refer to this input snapshot.

### labtools.devices.horiba_spectrometer

- `src/labtools/acquisition/range_spectrum.py:14: HoribaSpectrometer`
- `src/labtools/acquisition/run_hyperspectral_scan.py:93: HoribaSpectrometer`
- `src/labtools/gui/spectrum_gui_horiba.py:65: HoribaSpectrometer`
- `src/labtools/runtime/spectrum_backend.py:23: HoribaSpectrometer`
- `src/labtools/runtime/spectrum_backend.py:102: HoribaSpectrometer`
- `scripts/horiba/check_horiba_configuration.py:23: HoribaSpectrometer`
- `scripts/horiba/check_horiba_shutter.py:27: HoribaSpectrometer`
- `scripts/horiba/check_horiba_slit_width.py:19: HoribaSpectrometer`
- `scripts/horiba/set_horiba_configuration.py:27: HoribaSpectrometer`

### labtools.devices.idq_time_controller

- `src/labtools/runtime/idq_count_service.py:28: IDQTimeController`
- `src/labtools/runtime/map_devices.py:42: IDQTimeController`
- `src/labtools/runtime/shared_map.py:62: IDQTimeController`
- `src/labtools/devices/idq_time_controller/controller.py:59: dlt`
- `tests/test_idq_acquisition.py:4: IDQTimeController`
- `tests/test_timestamp_stream.py:13: IDQTimeController`

### labtools.devices.idq_time_controller.controller

- `src/labtools/devices/idq_time_controller/__init__.py:8: IDQTimeController`

### labtools.devices.itc4000

- `src/labtools/acquisition/run_hyperspectral_scan.py:94: ITC4000`
- `src/labtools/runtime/lazy_devices.py:10: ITC4000`

### labtools.devices.kinesis_rotation_stage

- `src/labtools/acquisition/laser_anneal.py:19: KinesisRotationStage`
- `src/labtools/gui/laser_anneal_gui.py:47: KinesisRotationStage`

### labtools.devices.labjack_u6

- `src/labtools/acquisition/laser_anneal.py:20: LabJackU6`
- `src/labtools/acquisition/run_hyperspectral_scan.py:95: LabJackU6`
- `src/labtools/devices/scanning_mirror.py:5: LabJackU6`
- `src/labtools/devices/spad_gate.py:3: LabJackU6`
- `src/labtools/runtime/labjack_service.py:92: LabJackU6`
- `src/labtools/runtime/map_devices.py:43: LabJackU6`
- `src/labtools/runtime/mirror_backend.py:17: LabJackU6`

### labtools.devices.sc10

- `src/labtools/acquisition/laser_anneal.py:21: SC10,SC10Mode`
- `src/labtools/gui/laser_anneal_gui.py:48: SC10`
- `tests/test_sc10_modes.py:18: SC10,SC10ExternalTriggerMode,SC10Mode,SC10TriggerMode`

### labtools.devices.scanning_mirror

- `src/labtools/acquisition/laser_anneal.py:22: ScanningMirror`
- `src/labtools/acquisition/run_hyperspectral_scan.py:96: ScanningMirror`
- `src/labtools/runtime/labjack_service.py:96: ScanningMirror`
- `src/labtools/runtime/map_devices.py:44: ScanningMirror`
- `src/labtools/runtime/mirror_backend.py:18: ScanningMirror`

### labtools.devices.spad_gate

- `src/labtools/runtime/labjack_service.py:100: SPADGate`
- `src/labtools/runtime/map_devices.py:45: SPADGate`

### labtools.devices.uc480_camera

- `src/labtools/gui/laser_anneal_gui.py:49: ThorlabsUC480Camera`
- `scripts/camera/check_uc480_camera.py:6: ThorlabsUC480Camera`

## Source method index

### src/labtools/devices/__init__.py


### src/labtools/devices/horiba_spectrometer.py

- HoribaSpectrometer: preset_options:86, __init__:99, connect:126, _verify_detector_identity:158, disconnect:196, configure:218, _validate_detector_token:334, configuration_summary:349, prepare_wavelength_axis:367, set_wavelength:394, set_slit_width:406, set_exposure_time:432, set_roi:443, reset:476, get_spectrum:488, get_dark_spectrum:576, _acquire_single:603, _wait_for_ccd:636, _wait_for_mono:641, __aenter__:650, __aexit__:654

### src/labtools/devices/idq_time_controller/__init__.py


### src/labtools/devices/idq_time_controller/controller.py

- IDQTimeController: __init__:105, connect:125, disconnect:139, __enter__:173, __exit__:177, configure_channel:184, configure_histogram:234, get_counts:297, get_simultaneous_counts:323, get_count_rate:357, get_histogram:379, start_timestamp_stream:421, acquire_timestamp_stream:481, wait_for_timestamp_stream_idle:531, stop_timestamp_stream:569, _start_stream_channels:604, _cmd:649, _query:658, _close_active_dlt_streams:668, _run_record:683, _is_dlt_healthy:694, _launch_dlt_service:706, _restart_dlt_service:745, ensure_dlt_running:765
- _parse_numeric_response:64

### src/labtools/devices/idq_time_controller/dlt.py

- StreamClient: __init__:122, run:134, join:171
- check_host:30
- dlt_connect:43
- dlt_exec:99

### src/labtools/devices/itc4000.py

- ITC4000: __init__:41, _ensure_open:80, _query:85, _check_error:90, _write_checked:97, identify:116, get_diode_output:120, get_tec_output:125, enable_diode:133, disable_diode:147, enable_tec:167, disable_tec:177, enable:190, disable:215, set_current:236, get_current:265, set_temperature:269, get_temperature_setpoint:278, get_temperature:282, set_pulse_frequency:289, get_pulse_frequency:303, set_pulse_width:309, get_pulse_width:321, set_pulse_duty_cycle:325, get_pulse_duty_cycle:340, set_pulse_hold:344, get_pulse_hold:369, close:376, __enter__:387, __exit__:391

### src/labtools/devices/kinesis_rotation_stage.py

- KinesisRotationStageError: (no declared methods)
- KinesisDevice: (no declared methods)
- KinesisRotationStage: __init__:22, _module:30, list_devices:47, is_connected:54, connect:57, close:74, _connected_stage:85, get_position:90, stop:93, move_to:96, __enter__:108, __exit__:112

### src/labtools/devices/labjack_u6.py

- LabJackU6: __init__:22, i2c:39, set_digital_out:42, close:50, __enter__:55, __exit__:58

### src/labtools/devices/sc10.py

- SC10Error: (no declared methods)
- SC10Mode: (no declared methods)
- SC10TriggerMode: (no declared methods)
- SC10ExternalTriggerMode: (no declared methods)
- SC10Device: (no declared methods)
- SC10State: (no declared methods)
- SC10: __init__:59, list_devices:75, is_connected:82, connect:85, close:111, _connection:136, _exchange:141, _query:158, _command:164, identify:169, is_enabled:172, toggle_enable:175, set_enabled:178, is_closed:185, set_mode:188, get_mode:191, set_trigger_mode:194, get_trigger_mode:197, set_external_trigger_mode:200, get_external_trigger_mode:203, set_open_time_ms:206, get_open_time_ms:211, set_close_time_ms:214, get_close_time_ms:219, set_repeat_count:222, get_repeat_count:227, get_state:230, __enter__:243, __exit__:247

### src/labtools/devices/scanning_mirror.py

- _LJTickDAC: __init__:14, _to_double:20, _load_cal_constants:24, set_voltages:43
- ScanningMirror: __init__:77, move:80, home:84

### src/labtools/devices/spad_gate.py

- SPADGate: __init__:25, open:29, close:33

### src/labtools/devices/uc480_camera.py

- UC480CameraError: (no declared methods)
- UC480CameraInfo: (no declared methods)
- ThorlabsUC480Camera: __init__:31, _module:45, list_cameras:55, is_connected:70, connect:73, close:84, _connected_camera:109, set_exposure:114, get_exposure:122, get_device_info:125, get_gains:128, get_max_gains:133, set_master_gain:138, start_live:145, stop_live:156, read_latest:162, snap:173, _prepare_frame:178, __enter__:187, __exit__:191

## W1 ITC4000 lifecycle checkpoint (current)

Input snapshot: `labtools_source_20261029_075745.txt`, HEAD
`ad2a95b9813bc8407d54120a3997571c24d52450`, branch
`feature/shared-instrument-session`, upstream +1/-0. Recorded tracked worktree/index
clean; four earlier installers are untracked and preserved. Live Git remains authoritative.

W1 is IMPLEMENTED and OFFLINE-VALIDATED, not physically accepted. Startup cleanup now
covers manager creation, resource open, termination setup and *CLS. Both close stages
are attempted independently. Ordinary close failures raise ExceptionGroup retaining
all errors. KeyboardInterrupt/CancelledError remain primary, with other failures
attached structurally in _itc4000_cleanup_failures and human-readable notes. Startup
and context-body exceptions remain primary if cleanup also fails.

Once teardown starts, all command/query paths refuse use. Successful handles are
cleared; failed handles remain uncertain and _closed stays false. Only an explicit
close retries failed stages; successful stages are not repeated. Manager close may
invalidate an instrument whose close failed: retained handles do not imply a usable
session or guaranteed recovery. A failed constructor returns no wrapper; its original
exception/traceback and cleanup details remain the evidence for maintainer teardown.
No reconnect, command retry, destructor, laser-off, TEC-off or current-reset was added.

Constructor/public imports, defaults, units, SCPI strings/order, *OPC?/error/readback,
TEC policy and timeouts are preserved. Existing command/setter method ASTs are unchanged.
Finite-input policy (including the audited NaN constructor gap) remains W1b, not fixed.
IDQ get_histogram eval(raw) remains P0 and unfixed; fixture-backed parser hardening is
separate. No other wrapper, map allocation, schema/resume/model, profile or launcher
changed. Syncerity 0.065 s and Symphony 0.1 s remain unchanged.

Validation: 44 whole-module fake-PyVISA cases pass; focused ITC/service/import selection
179 passed; full offline suite 362 passed / 4 skipped, 172 inherited warnings. Baseline
rerun 318 passed / 4 skipped. QtWidgets still cannot load libGL.so.1. Changed-file Ruff
format/check, compileall, CLI/native-free smoke, TOML and wheel build passed. See
[itc lifecycle checkpoint](itc4000-lifecycle-checkpoint.md) for exact evidence, inventory,
installer/rollback/commit commands and remaining Windows/physical acceptance.

## W2 HORIBA lifecycle checkpoint (current)

Input snapshot: `labtools_source_20261029_084624.txt`, created
2026-10-29T08:46:24.4544246Z, HEAD `8293c1677d43e94fc9b50ede778cc5853dca5db7`,
branch `feature/shared-instrument-session`, upstream +2/-0. Tracked index/worktree
recorded clean; five earlier installers are untracked and preserved. Live Git is authoritative.

W2 is IMPLEMENTED and OFFLINE-VALIDATED, not physically accepted. Manager construction/
start, monochromator/CCD open, configuration and detector identity now share one startup
cleanup boundary. Disconnect attempts CCD close, the established one-second mono wait+
close, and manager stop independently. Ordinary cleanup failures are visible as
ExceptionGroup; cancellation/interrupt remains primary, with other cleanup failures in
_horiba_cleanup_failures and notes. Backend contexts now also preserve operation/cancellation
when disconnect raises BaseException and mark cleanup failure for real-worker faulting.

Teardown permanently refuses reconnect. Public mono/CCD/manager references are cleared;
failed handles remain private uncertain handles for explicit disconnect-only retry.
Successful stages are not repeated. Retained handles do not imply usability, especially
if manager stop succeeded. Successful disconnect is idempotent. No persistent connection,
automatic reconnect, command retry or timeout policy was added.

Preserved: public API/imports, detector identity/presets, optical tokens/units/readbacks,
command order, CCD/mono wait loops, one-second mono-close delay, capture/dark/reduction,
exposure setter/cache policy and 0.065/0.1 s minima. No 0.02 s override. ITC W1b, IDQ
P0 eval parser and all other wrappers remain separate; no map/launcher/profile/schema change.

Validation: 39 whole-module fake-SDK/backend/worker tests pass; focused selection
135 passed; full offline suite 393 passed / 5 skipped, 172 warnings. This environment
had no PyQt6, so QtCore plus four QtWidgets modules skipped; acquisition remains gated.
Changed-file Ruff, compileall, CLI/native-free smoke, TOML and wheel build passed.
See [W2 checkpoint](horiba-lifecycle-checkpoint.md) for exact inventory, limitations,
installer/rollback/commit commands and physical acceptance.
