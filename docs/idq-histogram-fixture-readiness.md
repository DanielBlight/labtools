# IDQ histogram response-fixture readiness

## Scheduling decision: ID900 histogram work deferred (2026-11-05)

The maintainer reports that the device is an **IDQ ID900 Time Controller**, but
response records and further device details are not currently available. This is
user-supplied model identity, not verified firmware or response-format evidence.
Defer the IDQ histogram fixture/parser work until those inputs are available.
**DEFERRED / BLOCKED ON EVIDENCE; P0 eval(raw) remains open and unfixed.** This is
not risk acceptance, parser approval, or hardware/native-SDK acceptance.

Do not keep selecting fixture collection as the next engineering checkpoint while
these inputs are unavailable. See [return instructions](idq-histogram-fixture-readiness.md#return-to-this-work)
for the evidence checklist and reopening procedure. Older fixture-collection next-task
pointers below are historical and are superseded by this scheduling decision.

Next independent checkpoint: ITC4000 W1b finite-input contract review only. Inspect
the current constructor/setter validation and existing tests, document compatibility
and one bounded design decision, but do not implement policy or access hardware.
This is separate from IDQ parsing, not a claim that the IDQ issue is resolved.

## Return to this work

### Known information and preserved blocker

The maintainer supplied model IDQ ID900 on 2026-11-05. Firmware version, actual
histogram replies and approved response specifications are still unavailable.
Do not infer ID900 wire grammar, count limits, bin width or firmware behavior from
model identity, scalar examples, vendor command scripts or another model's examples.
The existing get_histogram path still uses eval(raw); it is not made safe by this
documentation. This deferral authorizes no new histogram execution, collection,
network access, output enabling or parser replacement. Do not feed untrusted response
text to the current parser. Existing behavior is unchanged, not certified safe.

### Reopening trigger and maintainer procedure

1. Reopen when approved existing response records or an explicit ID900 response
   specification becomes available, or when the maintainer explicitly prioritizes
   this issue with the missing evidence. A new source snapshot alone is not a trigger.
2. Inspect a fresh snapshot and this deferral first. Establish branch, HEAD, dirty
   state and actual installed code. Preserve measurement data, validation artifacts,
   every installer backup and unrelated files. Do not run old rollback commands.
3. Locate existing approved records/specifications before considering acquisition.
   For each candidate record the original source/path, approval, model ID900,
   firmware/software version if known, timestamp, exact query, histogram index,
   configured bin count, queried bin width and acquisition/configuration context.
   Mark missing metadata unknown, never infer it from example defaults.
4. Preserve complete raw bytes or a lossless encoding. Record byte length and
   SHA-256, expected bins and the independent basis for those expectations. Keep
   originals unchanged and record redactions/transformations separately. A script's
   hash is not a response hash; synthetic examples must be labeled synthetic.
5. Review as inert data. Never use eval, exec, the existing get_histogram method,
   vendor acquisition scripts or native SDKs to inspect records. No automatic
   device connection or fault induction is part of fixture review.
6. Cover normal nonempty data, zero-count bins versus empty/no-data, error replies,
   delimiters/whitespace/numeric forms, shape versus configured bin count, count
   range/overflow and response-size context. Separate code expectations from
   demonstrated firmware behavior. Mark unsupported cases unknown.
7. If no records exist, prepare a separately reviewed, maintainer-authorized capture
   procedure before any hardware work. Identify device/firmware, benign approved
   configuration, exact queries, timeout/abort handling and lossless recording.
   This document is a planning checklist, not an executable acquisition procedure.
   Do not enable outputs, alter limits, induce errors or guess SCPI commands.
8. Record one readiness decision. If evidence is insufficient, keep the issue open
   and specify missing inputs. If sufficient, propose a separately bounded parser
   design with explicit accepted grammar and rejection policy; do not implement it
   incidentally during fixture review.
9. A later implementation must preserve reviewed command order, units, bin-axis
   construction and public output compatibility. Test offline with approved fixtures
   and clearly labeled adversarial synthetic cases; reject executable expressions
   without evaluating them. Resolve empty/error replies, shape, integer conversion,
   overflow and size policy explicitly. Keep IDQ/DLT ownership/teardown redesign out.
10. Close only the scope actually evidenced: parser tests are not native-SDK,
    hardware, operator-visible or original-audit acceptance. Update roadmap/handover
    with exact results and remaining gates, not a generic complete label.

### Deferred-task handoff prompt

When approved ID900 histogram response records/specifications become available,
inspect the fresh snapshot and docs/idq-histogram-fixture-readiness.md. Review only
supplied/approved material as inert data. Build a provenance/coverage matrix with
raw-byte hashes and expected-bin evidence; distinguish captures, specifications,
command examples and synthetic tests. Do not collect hardware responses, evaluate
text or implement a parser. Decide whether a separately bounded parser design is
ready, or retain the blocker with exact missing inputs. Preserve all compatibility,
source, schema, limit, dependency and ownership boundaries. If no new evidence is
available, do not repeat this audit or manufacture a documentation checkpoint.

### Scope and authority for this scheduling update

Based on labtools_source_20261105_120201.txt, HEAD
d4158406423bc78942225ec759b84dae13f59a24, branch feature/shared-instrument-session,
tracked worktree/index clean, upstream +3/-0. This documentation-only update records
the maintainer's explicit deferral and supplied model. No firmware, response fixture,
local owner acceptance output or v4 raw-artifact verification output was supplied.
No application tests, hardware, SDKs or parser calls are required for this update.
Production source, tests, commands, dependencies, schemas, limits, owner labels,
plotting and real/simulation behavior remain unchanged. Historical Windows acceptance
is not reopened or broadened. Original comparison and physical/operator gates remain.

## Decision: BLOCKED on authentic representative response evidence

This documentation-only checkpoint does not replace a parser, change SCPI commands,
execute histogram responses, import device modules, connect hardware, or alter
IDQ/DLT ownership. The existing eval(raw) path remains P0 and unfixed. No exploit
or compromised instrument is asserted. Vendor examples using eval do not establish
a safe grammar. No production/test/dependency/schema/limit/backend changes.

## Authority and previous checkpoint

Snapshot: labtools_source_20261105_113246.txt, created UTC
2026-11-05T11:32:46.8973314Z. Branch feature/shared-instrument-session, HEAD
c52badae636ba8214bfeea7733600ab3cff35181, upstream +2/-0. Tracked worktree/index
recorded clean. Latest commit: Characterize hyperspectral owner labels and record
provider-owned contract. Untracked owner/v2/v3/v4 backups, installers, validation
artifacts and measurement data are preserved. Work uses an isolated reconstruction,
not the live Windows worktree. No Git mutation or hardware access.

The seven owner-checkpoint documentation files match their installed backup payload.
The owner test differs only by wrapping one import into a parenthesized multiline
import; parsed ASTs are identical. Preserve this formatting, do not restore the old
payload. Exact old-installer verification/rollback would reject that later test edit;
this is not a demonstrated behavior regression and is not permission to bypass guards.
No actual local owner-checkpoint verify/Ruff/pytest transcript is exported. The
commit and formatting change do not prove local acceptance. Prior sandbox evidence
remains 60 passed (26 new), zero failures/errors/skips, with Ruff unavailable.

The recorded original Windows acceptance remains Ruff passed, core 68, widgets 12,
full offline 608, zero recorded failures/errors/skips/timeouts. Counts overlap.
Actual v4 evidence-command output and raw original logs/XML remain absent; local
raw-artifact verification, original historical comparison, visible operator acceptance,
native-SDK acceptance and hardware acceptance are not claimed.

## Exact production path and caller references

All paths below are repository-relative; line references identify the fresh baseline.

- src/labtools/devices/idq_time_controller/controller.py:64-73:
  _parse_numeric_response extracts a numeric prefix and casts it. Its docstring
  examples 1000TB and 0.1V concern scalar responses, not histogram DATA grammar.
- controller.py:379-415: get_histogram(hist, duration_s) computes integer duration
  picoseconds, queries HIST{hist}:BWID? through that scalar helper with cast=int,
  issues HIST{hist}:FLUS, runs _run_record(duration_ps), then queries HIST{hist}:DATA?.
  At line 412, np.array(eval(raw), dtype=np.int64) evaluates the response and casts
  the result. No new execution or characterization of this unsafe expression was
  performed. The method has no explicit one-dimensionality, count-range, size or
  configured-bin-count equality check at this parsing boundary.
- controller.py:414-415: x_ps = (np.arange(len(y)) + 0.5) * bin_width_ps; returns
  (x_ps, y). This is current bin-centre construction, not firmware syntax evidence.
  Successful conversion requests int64 for y; this does not establish wire integer
  width, permitted count range or a future rejection policy.
- controller.py:658-666: _query sends the command over the existing ZMQ socket,
  receives one message and decodes UTF-8; zmq.Again becomes TimeoutError. No DATA
  suffix stripping or response-error classification occurs here.
- controller.py:23-35: usage example calls get_histogram after configuration.
- tests/test_idq_acquisition.py:22-40: test_get_histogram_smoke configures and
  acquires hardware data; asserts equal shapes, nonempty output, nonnegative y,
  increasing x_ps. Module is hardware-marked at line 6. It is not a response fixture
  and was not run. No other production get_histogram caller was found in exported
  source/scripts/examples; that statement is limited to exported content.

## Fixture and example inventory with provenance

Scope: all 270 exported file-content sections, including 54 test modules and 41
vendor/IDQ sections, plus snapshot manifest/path references. Omitted/binary files,
external records and an entire vendor distribution cannot be certified by this
export. No external web/vendor retrieval was needed or performed.

1. Authentic captured HIST{hist}:DATA? responses: none identified in exported
   contents or relevant manifest names. No raw-byte response, device/firmware identity,
   capture timestamp, command context or provenance-linked expected bins supplied.
2. Hand-written histogram parser fixtures: none identified. The hardware smoke test
   is an assertion set, not recorded input. No fabricated response is introduced.
3. Vendor Python examples, provenance limited to the repository vendor/IDQ tree:
   - Examples/Python/utils/acquisitions/histograms.py:12-37 declares
     Dict[int, List[int]], runs acquisition and applies eval(zmq_exec(...DATA?)).
     Lines 40-63 save bins by iterating zipped histogram sequences.
   - Examples/Python/utils/common.py:42-46 sends a command and UTF-8 decodes recv().
     Its dlt_exec JSON handling at 72-80 is a different protocol boundary, not
     evidence that histogram DATA is JSON.
   - Examples/Python/utils/plot.py:20-21 uses histogram[-1] and list concatenation;
     plot_histograms:30 onward assumes indexable, nonempty sequences. These are
     consumer assumptions, not validated device-response syntax.
   - Examples/Python/Histogram_acquisition/histogram_acquisition.py:120;
     Histogram_acquisition_filtred/histogram_acquisition_filtred.py:197;
     Precise_counters_acquisition_over_time/long_precise_input_counters_acquisition.py:145;
     utils/acquisitions/counts_over_time.py:84 call the vendor histogram helper.
   - Examples/Python/Timestamp_acquisition_multi_tc/multi_tc_acquisition/acquisition.py:
     148-168 separately evaluates DATA? and MIN?/BWID? responses. Its sibling utils.py
     decodes UTF-8. No response capture is included.
   These are bundled examples, not independently authenticated vendor publications,
   firmware specifications or response fixtures. They were read, never executed.
4. Vendor SCPI command examples:
   - Examples/SCPI/tc_as_high_resolution_histogram.txt:44-67 configures and queries
     HISTogram1:DATA?; no returned payload is shown.
   - Examples/SCPI/deadtime.txt:32-43 configures/queries HIST1:DATA?; its descriptive
     pulse/count comment is not a literal response or count-range specification.
   - Examples/SCPI/default_config.txt:252-289 configures/flushes histograms; no
     DATA response. Example bin counts are settings, not new parser size limits.

## Supported parser-input boundary versus unknown grammar

Established by code, not authentic wire fixtures:
- input source is the decoded UTF-8 response to the existing DATA? query;
- current consumer requests an int64 NumPy array and derives bin centres from len(y)
  and queried bin width; the intended public output is counts per bin;
- vendor annotations/consumers expect integer sequences, but do not validate grammar;
- preserve command order, units, output compatibility and axis construction in any
  later implementation unless a separately reviewed decision changes them.

Not established: delimiters/brackets, separators, whitespace/newlines, sign syntax,
integer bases, exponent/decimal notation, wrappers/units, trailing terminators,
empty response versus zero-count bins, error-reply forms, malformed-response behavior,
scalar/nested shape validity, configured-bin-count relationship, supported count
range/overflow semantics, maximum message size and firmware/version variation.
Do not assume JSON, literal_eval compatibility, unsigned/signed wire width, a new
size bound, or acceptance of booleans/floats merely because Python/NumPy can coerce
some inputs. Do not claim the smoke-test expectations are established firmware rules.
A safe parser's eventual rejection policy needs an explicit bounded design decision;
malicious expressions must not be executed to discover compatibility.

## Precise missing evidence and maintainer-controlled plan

Exactly one next bounded task: assemble and review a provenance-recorded fixture
bundle from already approved histogram-response records or explicit vendor response
specifications. No automatic acquisition or hardware connection is authorized.

Required baseline evidence:
- at least one complete, unedited normal DATA? response with matching query,
  expected bin values/count and acquisition/configuration context;
- a zero-count histogram response, distinct from an empty/absent response;
- device model, firmware/software version, histogram index, configured bin count,
  queried bin width, encoding/framing, timestamp/source and maintainer approval;
- raw bytes (or lossless encoding), byte length and SHA-256; retain originals and
  document any redaction/transformation separately;
- representative deployed-version/format variation, or an explicitly narrowed
  supported-version scope backed by the maintainer;
- documented count-domain/overflow expectations and supported response-size context.

Seek existing approved examples/specifications for empty/no-data, error replies,
truncated/malformed data and numeric extremes. Do not induce faults or claim such
records exist. If unavailable, record each unknown and obtain a separately reviewed
rejection policy before parser implementation. Later synthetic adversarial tests
must be labeled synthetic, not firmware captures; none are generated here.

The maintainer should locate existing approved records first, record provenance and
hashes, and review them as inert data. Do not pass them to eval, exec, vendor example
scripts or the current get_histogram method. If no suitable records exist, request
separately authorized evidence collection with a reviewed procedure; this checkpoint
provides no device-execution commands. Stop before implementation while blocked.

## Validation and exclusions

Static inspection only for the application: no pytest, device import, parser call,
Ruff application gate, native SDK, network or hardware execution. No production or
test file changes. Documentation link/payload checks, patch dry-run and guarded
installer filesystem tests are delivery validation, not application acceptance.
No old Windows gates were rerun. No fixtures or parser grammar were invented.
Keep parser hardening separate from IDQ/DLT transport, streaming, ownership and
teardown; preserve all owner-label, schema, dependency, limit and backend decisions.
