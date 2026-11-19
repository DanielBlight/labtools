# Operator workspace presentation refresh

## Scope

Shared workspace theme, compact shell, consistent tab headers/forms/status styling,
responsive control/result splitters and scoped parameter-wheel protection.
No acquisition, averaging, cancellation, reservation, profile or native execution
policy changes. The map display backpressure correction is retained unchanged.

The clean capture records source commit 1abe400e077bae993f8a769382c5f14741e9bf3f,
1200 x 854 logical pixels, 125% scaling, Qt/PyQt 6.11.0. The screenshots are idle
states, not acceptance evidence for running operations or other window sizes.

## Presentation contract

- One shared light instrument theme: typography, spacing, borders, focus and disabled
  states. Local legacy panel styles are cleared only when embedded in the workspace.
- Compact Labtools header with a persistent Simulation or Native execution disabled
  badge, Camera and Stop all. No full-width camera/close buttons or repeated banner
  paragraphs. Window-manager close remains the existing cooperative close path.
- Workspace summary replaces default raw JSON. Diagnostics is a disclosure; Validate
  settings opens it. Save/refresh errors remain visible in the summary, and stop
  errors open diagnostics. Actual device-state/error reporting is not removed.
- Map, spectrum and annealing use the same two-pane responsive splitter. Narrow
  windows stack controls above results; wide windows place controls beside results.
  Controls scroll vertically. Existing large minimum widths/heights are relaxed.
  Initial window size is based on available logical screen geometry.
- Forms wrap long rows. Plot/status labels can wrap instead of forcing window width.
  Estimates and dark-record status are retained; static instructional prose is hidden.
- Mouse-wheel and touchpad-scroll events cannot change spin boxes, combo boxes or
  sliders, even when focused, including controls added later and the owned camera.
  Events over a parameter scroll its nearest scroll area when present. Normal scroll
  bars, keyboard editing, arrow buttons and plot navigation remain available.
- No new safety confirmations. A permanently disabled native-draft confirmation is
  hidden without changing its value or bypassing native execution gating. Simulation
  remains clearly identified; physical state and fault indications remain visible.

## Validation and acceptance

Run ruff check --fix on the changed Python paths and the targeted tests included by
this updater. test_operator_ui.py exercises real Qt wheel events (focused/unfocused,
angle/pixel deltas), keyboard editing, late camera controls, form scrolling, splitter
orientation changes and the full workspace at 800x600, 1024x700 and 1400x900 logical
sizes. Existing native/simulation window tests cover operation and deferred-close
behaviour. A skip is not GUI acceptance.

The sandbox lacks libGL.so.1. It cannot render this change or execute QtWidgets
acceptance. Do not describe the refresh as visually validated or release-ready until
actual Windows tests and screenshots are reviewed. The theme is intentionally light;
no dark-theme or arbitrary tiny-screen acceptance is claimed. The separate camera
inherits styling and wheel protection but its internal layout is not redesigned here.

On Windows, run the targeted validator, then the existing corrected capture script.
After initial tab captures, resize the workspace to a small and a large window and
press F8 on each tab. Include expanded sections, a running/stopped map, a plotted
spectrum, anneal progress and the camera. Check scroll over focused integration,
exposure, gain and combo controls: values must not change. Confirm normal form
scrolling and keyboard edits. Close normally to create the review ZIP.

Keep this batch uncommitted until local tests and visual review are satisfactory.
Use explicit staging of the eight paths listed by the updater, not git add -A.
