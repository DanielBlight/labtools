# Unified GUI lab-PC acceptance report, 2026-11-23

## Evidence and scope

The supplied clean development snapshot is branch feature/unified-gui-alignment,
HEAD 2dd0661cfd52938bf7f2c76d5f14c93a3110b38d (Workspace hub/all-hardware mode).
The 411 exported files were decoded and individually checked against declared sizes
and SHA-256 hashes before implementing the next feature batch.

The supplied Windows validation log reports the source import from C:/Dev/labtools/src,
Ruff check --fix passed, and **630 passed in 74.58 seconds**, all commands exit 0.
This is the targeted selection in that log, not a full-project-suite claim.
The current-state file and manifest both show the same clean development HEAD.

The user reports: "It all worked well on the lab pc apart from a couple of the boxes
on the left of the camera window being clipped and the y axis on the intensity
mapping being clipped if I made the window too narrow."

Record this as **user-reported unified GUI connected acceptance of the checks
performed so far, with two known presentation defects**. No functional hardware
failure was reported. This supersedes the earlier blanket statement that no unified
all-hardware lab result had been supplied. It does not invent a device-by-device
trace, a separate lab-PC HEAD capture, a physical safety certification or a pass
for unperformed checks. The user did not provide separate powered laser, dark,
Stop-all or active-close observations in this report; do not manufacture those.

## Known issues from that accepted baseline

1. Camera control boxes clipped at the tested layout.
2. Intensity-map Y axis clipped when the window was made narrow.

Both have source/layout corrections in the next feature batch. Linux offscreen
layout tests are not a Windows visual reacceptance. Confirm the corrections on the
lab PC rather than marking them physically verified from this report.

## New functionality is a separate acceptance scope

Single-point/ramped-dose programs, unified hyperspectral mapping and anneal/measure
sequences are introduced AFTER the accepted baseline. They are not covered by the
630-test Windows log or the user's preceding lab-PC pass. Their Windows and connected
acceptance remains pending. See experiment-workflows.md and the implementation note.
