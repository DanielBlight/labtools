# Studio operator views

This replaces the embedded map/spectrum/anneal visual layouts, not just colours.
It reuses the original widget instances and worker slots. Hidden legacy containers
remain alive for compatibility references, but are not operator menus. The standalone
launchers are unchanged. The previous parameter-wheel guard remains installed.

## Visible design

- Neutral graphite/white surfaces, teal primary actions, one Fusion widget style.
- Static, consistently labelled sections. No checkbox-controlled section menus.
  Detector-default override is an actual setting, not a disclosure.
- Numeric controls use typed values and keyboard arrows consistently, with no tiny
  spin-button pairs. Combos are for choices, checkboxes for booleans.
- Map/spectrum forms scroll with persistent action buttons; result panes reflow below
  controls on narrow windows. Plot margins recalculate on canvas resize.
- Annealing has controls only, reflowing to one/two columns. The empty status pane and
  progress bar are absent. Textual operation progress and shutter state remain.
- Laser has its own tab; no visible laser controls remain on map/spectrum. A single
  coloured-dot-and-text indicator lives in the workspace header.

## Laser scope: important

The current workspace's native execution is gated. This batch implements the Laser
operator tab and working synthetic connect/current/on/off/disconnect controls. It
DOES NOT enable real ITC4000 control, create a physical connection, or pretend to
read physical state. Native mode shows unknown, not OFF. The synthetic laser model
is independent of the existing toy map/spectrum generators: it does not simulate
optical power, heating or laser-dependent counts. State is not restored on restart.
Stop all turns the connected synthetic laser off as well as requesting workflow
stops. No real laser output-off policy is changed. Real laser integration still
requires one shared worker-owned connection, optical-path exclusion and lifecycle
acceptance; do not bypass the gate by wiring legacy per-tab Connect buttons.

## Installation and rollback

The installer accepts the uncommitted first UI pass shown in review.json. It does
not demand a cosmetic-pass commit. It adds four paths and inserts one composition
call into native_workspace.py. It backs up exact bytes before writing, refuses
unrecognised structure or conflicting new files, and rolls back only its own five
paths. Earlier uncommitted UI changes are preserved. No git reset/stage/commit/push,
local configuration, environment or dependency changes are performed on the PC.

Run --apply --validate from the repository. The report is saved beside the updater.
Validation uses actual QtWidgets, new tests and existing operator-window/wheel tests.
Missing Qt or skipped tests are not accepted as GUI validation. The supplied
screenshots are 1400x736 logical at 125% scaling and show the first UI pass, not this
rebuild. No new screenshots or visual acceptance are claimed by this package.

After tests pass, run the existing corrected capture script. It automatically sees
the new Laser tab. Capture all tabs at normal and small window sizes, plus an active
map, a completed spectrum, anneal textual progress and Laser ON/OFF in simulation.
Review native mode only for disabled actions/unknown state; do not connect hardware.

The native_workspace.py insertion is AST-checked to leave all existing methods
unchanged apart from the constructor's explicit presentation composition call.
Actual Windows rendering and full source integration must still be accepted locally.
