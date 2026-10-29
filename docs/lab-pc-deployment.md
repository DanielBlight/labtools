# Labtools on the lab PC
## Installation, operator access and controlled updates

**Maintainer runbook | Windows | 28 October 2026**

This proposed deployment procedure is based on snapshot `labtools_source_20261028_170656.txt`, HEAD `a439207b4b6d6aec2fbf3575d2fa155893d318a3`. It is not an institutional IT policy or a claim that deployment has been performed. Have local IT approve accounts, paths, permissions and driver installation before applying it. [S1, S6, S7]

### Recommended approach

Keep development on your own PC. Build a reviewed release bundle, transfer it to the lab PC, and install a non-editable wheel into a new, protected environment. Operators launch that environment through shortcuts. They edit recipes and save data outside the installed application. The lab PC does not need GitHub access for this approach. [S1-S5]

**Do not deploy the experimental branch as an accepted production release yet.** The supplied snapshot contains lifecycle test source but no local pass log. The current verification reran the gate: 15 passed and four QtWidgets modules skipped because `libGL.so.1` is missing here. Skips are not acceptance. Finish the Windows gate and maintainer-controlled hardware acceptance before replacing a working installation. [S1]

### Proposed folder layout

- `C:\Program Files\Labtools\releases\RELEASE_ID\venv` : installed code and dependencies; administrator writes, operators read/execute.
- `C:\Program Files\Labtools\bin` : protected launcher scripts and shortcuts' targets.
- `C:\ProgramData\Labtools\instrument.json` : reviewed annealing profile; maintainer writes, operators read.
- `%LOCALAPPDATA%\Labtools\Workspace` : each operator's recipes, logs and local data; operator writes.
- `C:\Labtools-Staging\RELEASE_ID` : maintainer-controlled transfer bundle; not the active application.

Use a local, non-synchronised acquisition directory. Back up completed data through your approved storage process; do not use the protected installation as an output folder. If using shared `C:\LabData`, IT must grant the appropriate write access and review data privacy. [S1; proposed layout]

### What “cannot edit core code” means

Standard accounts plus filesystem permissions protect the official installed files from modification. They do not hide Python source, stop an administrator changing it, or stop someone copying it and modifying their own copy. Running arbitrary Python can bypass application-level limits. The profile approval flag, a wheel, a frozen executable and a read-only file attribute are not physical safety controls. Do not give operators administrator credentials merely to run the GUI. [S1, S6, S7]

---
# 1. Prepare the release on the development PC

Use a Windows build machine with the same Python major/minor version and CPU architecture as the lab PC. The project requires Python 3.12 or later; for this deployment, choose one tested 64-bit Python 3.12 installation on both machines and record its exact patch version. Do not copy a development `.venv` to another PC: environments contain absolute interpreter paths and should be recreated at their final location. [S1, S2, S4]

### Before packaging

1. Inspect the actual checkout and dirty state. Select a maintainer-approved commit; do not package unreviewed source or run an automatic Git update on the lab PC.
2. Run the alignment gate below. A skipped QtWidgets module leaves the gate open. Keep the complete output with the release.
3. Run the full offline suite and the project's lint/build checks. Never enable `--run-hardware` as part of packaging.
4. Inventory vendor software already working on the lab PC. Preserve the current environment, drivers, profiles, shortcuts and output paths before installing anything new.

```powershell
# From the reviewed source checkout, in its development environment:
$env:PYTHONPATH = (Resolve-Path .\src).Path
$env:QT_QPA_PLATFORM = 'offscreen'
$env:MPLBACKEND = 'Agg'
uv run --no-sync python -m pytest `
  tests/test_alignment_window_acceptance.py `
  tests/test_alignment_gui.py `
  tests/test_spectrum_gui_phase1.py `
  tests/test_gui_lifecycle.py `
  tests/test_qt_controllers.py `
  tests/test_alignment_lifecycle_acceptance.py -q -rs
uv run --no-sync python -m pytest -q -rs
uv run --no-sync python -m compileall -q src tests examples
git diff --check
git status --short
```

Run commands separately and stop on any failure. Save stdout/stderr and inspect skip reasons, not just the exit code. Run the repository's Ruff policy with its locked development tools; do not apply unsafe fixes or bundle a formatting sweep into a release. Remove `QT_QPA_PLATFORM=offscreen` before interactive GUI checks. [S1]

### Native prerequisites are separate

A Python wheel is not a driver installer. The selected workflows may require HORIBA SDK/ICL and licensing, LabJack drivers, serial adapters, Kinesis, camera DLLs or VISA components. Record versions, bitness, service configuration, DLL paths and account access. Use vendor-approved installers and local IT procedures. Do not update instrument firmware or infer successful hardware operation from `pip check` or `labtools doctor`. [S1]

---
# 2. Build a transferable, pinned bundle

The commands below are a proposed Windows packaging procedure, not commands executed on your lab PC. Replace the Python path with the verified build interpreter. Keep the release ID unique even while the package version remains `0.1.0`. A commit hash and artifact hashes distinguish builds with the same wheel filename. [S1-S5]

```powershell
# Run from the reviewed checkout. Use a new bundle directory.
$Commit = (git rev-parse HEAD).Trim()
$ReleaseId = (Get-Date -Format 'yyyyMMdd') + '-' + $Commit.Substring(0, 12)
$Bundle = Join-Path 'C:\Labtools-Releases' $ReleaseId
$BuildPython = 'C:\Program Files\Python312\python.exe' # verify first
if (Test-Path $Bundle) { throw 'Choose a fresh release directory.' }
New-Item -ItemType Directory -Path "$Bundle\wheelhouse" -Force

uv export --locked --no-dev --no-emit-project `
  --format requirements.txt `
  --output-file "$Bundle\requirements-runtime.txt"
if ($LASTEXITCODE -ne 0) { throw 'Dependency export failed.' }

& $BuildPython -m pip download --only-binary=:all: `
  --require-hashes -r "$Bundle\requirements-runtime.txt" `
  --dest "$Bundle\wheelhouse"
if ($LASTEXITCODE -ne 0) { throw 'Wheel download failed.' }

uv build --wheel --out-dir "$Bundle\wheelhouse"
if ($LASTEXITCODE -ne 0) { throw 'Project wheel build failed.' }
Copy-Item .\pyproject.toml, .\uv.lock -Destination $Bundle
$Commit | Set-Content "$Bundle\source-commit.txt" -Encoding ascii
& $BuildPython -c "import sys,platform;print(sys.version);print(platform.machine())" |
  Set-Content "$Bundle\python-build.txt" -Encoding utf8
```

`uv export --locked` refuses a stale lock rather than silently updating it. `--no-emit-project` excludes the editable project entry; dependencies remain pinned and hashed. `pip download` collects compatible wheels for the build interpreter. Build on matching Windows, not this Linux environment. [S3, S4]

If any pinned dependency lacks a compatible wheel, stop. Do not remove the pin, disable hashes, silently choose a different version or download random DLLs. Build/review the dependency on a suitable machine or deliberately revise and retest the release. The current project has a broad runtime dependency set; this guide does not trim it. [S1, S4; recommended release policy]

Copy test logs, this guide and a separately reviewed profile template into the bundle. Do not include passwords, private keys, operator data, development `.venv`, `.git` or an unreviewed “approved” profile. Create a SHA-256 manifest of bundle files using `Get-FileHash` [S9]; retain the trusted original separately and verify it after transfer. A hash detects changes only when its expected value is trusted; it is not a signature. [S1; recommended release policy]

---
# 3. Install on the lab PC, without GitHub

**Maintainer/IT task.** Have IT establish the protected root/ACL policy in section 4 before creating releases. First close every labtools window and ensure no acquisition or vendor connection is active. Leave the existing working installation untouched. Transfer the complete bundle using an approved USB drive or file share. Compare transferred hashes with the trusted manifest. [Proposed deployment procedure; S1-S5]

Install an IT-approved, machine-accessible Python at a stable path. Do not base a shared environment on a maintainer's private user-profile Python. Verify its version/bitness and that operators can execute it. The example path below is a placeholder to check, not an assertion about your PC. [S1, S2]

```powershell
# Elevated maintainer shell. Verify paths before running.
$ReleaseId = 'REPLACE_WITH_ACTUAL_RELEASE_ID'
$Bundle = Join-Path 'C:\Labtools-Staging' $ReleaseId
$BasePython = 'C:\Program Files\Python312\python.exe'
$Release = Join-Path 'C:\Program Files\Labtools\releases' $ReleaseId
if ($ReleaseId -like 'REPLACE*') { throw 'Set the real release ID.' }
if (Test-Path $Release) { throw 'Do not reuse an existing release.' }
& $BasePython -c "import sys,platform;print(sys.version);print(platform.machine())"
& $BasePython -m venv "$Release\venv"
if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed.' }
$Python = Join-Path $Release 'venv\Scripts\python.exe'

& $Python -m pip install --no-index `
  --find-links "$Bundle\wheelhouse" --require-hashes `
  -r "$Bundle\requirements-runtime.txt"
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }

$Wheels = @(Get-ChildItem "$Bundle\wheelhouse\lab_tools-*.whl")
if ($Wheels.Count -ne 1) { throw 'Expected exactly one project wheel.' }
& $Python -m pip install --no-index --no-deps $Wheels[0].FullName
if ($LASTEXITCODE -ne 0) { throw 'Project installation failed.' }
& $Python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed.' }
```

The two installation steps are intentional: hashed dependencies first, then the separately hash-verified project wheel. Do not use `pip install -e`, `uv sync`, `uv run` or a source checkout for normal protected operator use. Do not copy or rename the finished environment; create each release at its final absolute path. [S2-S5]

For an internet-connected lab PC, the same pinned requirements may be installed from an approved index instead of the local wheelhouse. The offline bundle is recommended here because the lab PC is not GitHub-synchronised and it provides a reproducible rollback artifact. No online dependency upgrade is part of operator startup. [S1, S3-S5; recommendation]

---
# 4. Protect the official installation

**IT/administrator task.** Use separate standard operator accounts and an administrator/maintainer account. If everyone uses the same Windows account with the same rights, filesystem permissions cannot distinguish maintainer edits from operator edits. Local administrators can change permissions; this is protection of the official installation, not source-code secrecy or an instrument safety interlock. [S1, S6, S7]

### Required effective permissions

- Installation root, releases, environment, dependencies and launcher directory: Administrators/SYSTEM full control; operator group read and execute only.
- Profile directory and `instrument.json`: Administrators/SYSTEM full control; operators read/traverse only. Protect the parent too so operators cannot replace the file.
- Operator workspace/data: the relevant operator has Modify. Do not make the entire ProgramData or Program Files tree writable.
- Base Python, native DLLs and launcher targets must also be protected. Review inherited and explicit grants and group membership, not only one file's read-only flag. [S6, S7]

### ACL template for a NEW, EMPTY installation root only

IT must replace the operator group and inspect the result. Do not run this blindly on an existing shared directory. Preserve a known administrative recovery path. Grant administrator/SYSTEM access before removing inherited entries. No blanket deny is used because a maintainer may also belong to the operator group. [S6, S7; proposed template]

```powershell
# Elevated IT shell; create/approve the group separately.
$Root = 'C:\Program Files\Labtools'
$OperatorGroup = 'REPLACE_WITH_APPROVED_OPERATOR_GROUP'
if ($OperatorGroup -like 'REPLACE*') { throw 'Set the approved group.' }
if (Test-Path $Root) { throw 'Existing root: ask IT to review ACLs.' }
New-Item -ItemType Directory -Path $Root
icacls $Root /grant:r '*S-1-5-18:(OI)(CI)F' `
  '*S-1-5-32-544:(OI)(CI)F' "${OperatorGroup}:(OI)(CI)RX"
if ($LASTEXITCODE -ne 0) { throw 'Grant failed; stop.' }
icacls $Root /inheritancelevel:r
if ($LASTEXITCODE -ne 0) { throw 'Inheritance change failed; stop.' }
icacls $Root /setowner '*S-1-5-32-544'
icacls $Root
```

Apply the reviewed policy before creating releases so children inherit it. If releases already exist, IT must review child ownership and ACLs as well; the root-only template is not proof that existing children are protected. Use the same design for the dedicated profile directory after backing up any existing profile. Do not run a recursive reset on unrelated lab data. [S6, S7]

### Verify using a real operator login

Create a harmless temporary file in the protected root as administrator. Under the operator account, reading it must work but modifying, deleting or creating a sibling must fail. Remove it as administrator. Confirm workspace writes work. Inspect effective access for code, Python, launchers and profile. Do not test permissions by corrupting a real source file or profile. [Recommended acceptance check; S6, S7]

---
# 5. Configure the instrument and operator workspace

### Maintainer-controlled configuration

Review `examples/profiles/instrument.example.json` against the actual installation. Its limits and coordinates are unverified starting values. Set the correct hardware fields and a unique profile ID; mark it approved only after the required review. Install the resulting file at `C:\ProgramData\Labtools\instrument.json`, with protected parent/file permissions. Do not overwrite an existing calibrated profile during a software update. [S1]

`LABTOOLS_INSTRUMENT_PROFILE` overrides that path for development/testing. Remove stale overrides from operator launch environments. The profile currently governs the annealing workflow; it is not a universal configuration system for every tool. Map/spectrum settings and QSettings must be reviewed separately. The approval flag and profile hash are not independent calibration or safety evidence. [S1]

The spectrum/alignment workflows require a maintainer-reviewed `LABTOOLS_SPECTRUM_CONFIGURATION_ID`. Set the actual ID in the protected launcher after reviewing the optical/detector configuration. Do not invent an ID to silence validation, and do not treat the ID as calibration evidence. [S1]

### Create each operator's writable workspace

Run under the operator's normal account, not as administrator. Set `$Python` to the accepted release's exact interpreter path. The local workspace below avoids depending on a maintainer's home directory or synchronised repository. [S1, S2; proposed location]

```powershell
$Python = 'C:\Program Files\Labtools\releases\ACTUAL_ID\venv\Scripts\python.exe'
$Workspace = Join-Path $env:LOCALAPPDATA 'Labtools\Workspace'
& $Python -I -B -m labtools init $Workspace
& $Python -I -B -m labtools doctor
& $Python -I -B -m labtools validate `
  (Join-Path $Workspace 'recipes\anneal.json')
```

`init` creates `recipes\anneal.json` and `data`; it refuses to overwrite an existing recipe. Do not delete a user's recipe just to rerun init. `doctor` checks the profile configuration only. `validate` checks recipe/profile compatibility without operating hardware. Neither proves connectivity, calibration, optical safety or SDK health. [S1]

Operators can use Load recipe, Save recipe and Save recipe as in the anneal GUI. They should not edit installed Python. Named recipe migration for intensity mapping and spectroscopy is not complete: use their existing GUI controls and approved output locations. Set map/spectrum output paths to writable directories; some defaults/QSettings may still point elsewhere. Do not solve output permission errors by granting write access to the installed environment. [S1]

Back up recipes, profiles and data separately. Keep an immutable copy of the profile associated with each accepted release, while retaining the active reviewed profile outside the code environment. [Recommended practice]

---
# 6. Give operators simple launchers

Use protected launch scripts plus desktop/Start-menu shortcuts. Operators should not need a terminal, environment activation, `uv`, Git or a code editor. Use the full interpreter path so another Python on PATH is not selected. Python's isolated mode reduces user-site/PYTHONPATH interference; it is not a security boundary against arbitrary Python or an administrator. [S1, S2, S8; proposed launcher]

Example `C:\Program Files\Labtools\bin\spectrum.ps1`:

```powershell
$ErrorActionPreference = 'Stop'
$Python = 'C:\Program Files\Labtools\releases\ACTUAL_ID\venv\Scripts\python.exe'
$Workspace = Join-Path $env:LOCALAPPDATA 'Labtools\Workspace'
New-Item -ItemType Directory -Path $Workspace -Force | Out-Null
Set-Location $Workspace
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
Remove-Item Env:MPLBACKEND -ErrorAction SilentlyContinue
Remove-Item Env:LABTOOLS_INSTRUMENT_PROFILE -ErrorAction SilentlyContinue
$env:LABTOOLS_SPECTRUM_CONFIGURATION_ID = 'REPLACE_WITH_REVIEWED_ID'
if ($env:LABTOOLS_SPECTRUM_CONFIGURATION_ID -like 'REPLACE*') {
  throw 'Maintainer must set the reviewed configuration ID.'
}
& $Python -I -B -m labtools gui spectrum
if ($LASTEXITCODE -ne 0) { throw 'Labtools failed; record the error.' }
```

The launcher clears test-only display/backend overrides so the GUI is not silently offscreen. It deliberately keeps a console for errors. Have IT sign/approve scripts under the existing execution policy; do not bypass policy or run the GUI elevated. A shortcut can target `powershell.exe -NoProfile -File` followed by the quoted protected script path. Keep the script and its selected release path maintainer-writable only. [Proposed launcher; S1, S2]

### Other existing launch commands

Use the same protected-interpreter pattern and the appropriate reviewed settings:

- Annealing: `-I -B -m labtools gui anneal`
- Intensity mapping: `-I -B -m labtools gui intensity-map`
- Mirror: `-I -B -m labtools gui mirror`
- Alignment: `-I -B -m labtools.gui.alignment_gui_horiba`
- Explicit synthetic map GUI: `-I -B -m labtools.simulation.intensity_map --gui`

Alignment has a module entry point, not a registered `labtools gui alignment` command. Standalone tools do not automatically share ownership; do not open competing tools against the same physical instrument. Simulation GUI mode is initially selected, not a security sandbox preventing a user changing modes. Label simulation shortcuts clearly and keep commissioning controlled. [S1]

---
# 7. Keep the lab PC current, with rollback

Use deliberate releases, not live synchronisation. Do not `git pull`, `uv sync`, upgrade dependencies or replace Python files while operators are acquiring. The lab PC can stay disconnected from GitHub: transfer a complete tested bundle for each update. [S1-S5; recommended workflow]

### Update checklist

1. On the development PC, review the next commit, run the acceptance gate/full offline checks and create a new uniquely identified bundle. Record source commit, lockfile hash, wheel hash, Python/tool versions and test output.
2. Schedule a maintainer-controlled stop. Close all labtools/vendor sessions; confirm no acquisition owns hardware. Back up the active profile, launch scripts, release record and operator configuration. Do not modify data.
3. On the lab PC, create a NEW release environment at its final path. Install pinned dependencies and the non-editable wheel using section 3. Do not overwrite the previous environment.
4. Run no-hardware smoke checks and operator-account permission checks. Perform only the approved, supervised device acceptance for the changed workflows. Keep firmware/driver changes as separate, recorded decisions.
5. After acceptance, update protected launcher paths to the new environment. Change all relevant shortcuts/scripts consistently while no tool is running. Record who approved the switch, the previous/new release IDs and profile ID/hash.
6. Start as a standard operator and verify imports, writable output paths and selected configuration. Retain the previous release and its bundle until the new release has been accepted and the retention policy permits removal.

### Roll back

Close every tool first. Restore the protected launcher paths to the previous accepted environment. Restore the associated profile only if compatibility review requires it; do not silently undo a later calibration or overwrite operator recipes/data. Recheck the normal operator account and record the reason for rollback. The old environment remains at its original path; do not move/rename it. [S1, S2; recommended rollback]

### Why not upgrade in place?

A fresh environment isolates dependency changes and keeps a known rollback target. Current wheels may all report `0.1.0`, so package version alone cannot identify the deployed source. Use the unique release ID, full source commit and hashes. Do not let pip's same-version behaviour decide which code is running. [S1, S2, S5]

### Release record to retain

Release ID; full commit; clean/dirty source status; Python version/bitness; uv/pip versions; dependency export and lockfile hash; wheel/manifest hashes; profile ID/hash; driver/SDK versions; tests and skip reasons; physical acceptance notes; active launcher targets; previous release; approver and rollback location. Keep credentials out of this record. [Recommended release record]

---
# 8. Verify the installed release and troubleshoot

Run these checks with the accepted release's exact `$Python`. Do not run them from a source checkout with PYTHONPATH pointing at `src`. Isolated mode ensures the import test uses the installed environment rather than user-site/PYTHONPATH entries. [S1, S2]

```powershell
& $Python -I -B -c "import sys,labtools;print(sys.executable);print(labtools.__file__)"
& $Python -I -B -c "from importlib.metadata import version;print(version('lab-tools'))"
& $Python -I -B -m labtools --help
& $Python -m pip check
& $Python -m pip list --editable
& $Python -I -B -m labtools doctor
```

The import path should be under the chosen release's `venv\Lib\site-packages`, not the development checkout. The editable list must not contain lab-tools. A successful `doctor` validates the reviewed profile, not the devices. Do not invoke hardware diagnostics merely to check installation. [S1, S2, S5]

### Common problems

- **Module not found / old GUI:** verify the shortcut's interpreter and `labtools.__file__`. Remove stale source-path overrides; do not install packages into an unrelated Python.
- **Permission denied saving data:** select the operator workspace/output root and review that directory's ACL. Do not make Program Files writable.
- **Profile missing or rejected:** verify the protected ProgramData profile, account read access and stale profile overrides. Do not set approved=true without review.
- **SDK/DLL/driver error:** compare bitness, vendor installation/licensing and per-account DLL access with the last accepted release. A Python wheel alone does not resolve native prerequisites.
- **Console scripts absent:** use the protected interpreter with `-m labtools`; verify the wheel installation. Do not fix production by switching to an editable source install.
- **GUI invisible:** check for inherited `QT_QPA_PLATFORM=offscreen` or test backend settings; use the reviewed launcher.
- **Busy instrument:** close the owning tool cleanly. Do not start a second process or force-reconnect to bypass ownership.
- **New map fails within the same second:** the known timestamp-directory collision is still unfixed while the Qt gate is open. Preserve the failed run/data and report it; do not delete another run's folder.

### Operator handover

Provide labelled shortcuts, the workspace/output locations, how to stop and close cleanly, who maintains releases, and how to record errors with release ID. Explain which settings/recipes may be changed and which profile/hardware fields require maintainer review. Software access does not authorise laboratory work or replace training, risk assessments and physical interlocks. [S1; recommended handover]

---
# 9. Sources, limits and release sign-off

### Source basis

[S1] User-supplied source snapshot `labtools_source_20261028_170656.txt`, HEAD `a439207b4b6d6aec2fbf3575d2fa155893d318a3`. Inspected files include pyproject.toml, uv.lock, docs/operator-workspace.md, docs/commands.md, docs/ai-handover.md, docs/refactor-roadmap.md, config/anneal_workspace.py, cli.py, launchers.py, spectrum/alignment GUIs and simulation/intensity_map.py.

[S2] Python documentation: virtual environments, creation, interpreter paths and non-portability.
[Python virtual-environment reference](https://docs.python.org/3/library/venv.html)

[S3] Astral uv CLI: export --locked, --no-dev, --no-emit-project and build.
[uv command reference](https://docs.astral.sh/uv/reference/cli/)

[S4] pip documentation: downloading compatible distributions for offline installation.
[pip download reference](https://pip.pypa.io/en/stable/cli/pip_download/)

[S5] pip documentation: local wheel installation, dependency handling and installation options.
[pip install reference](https://pip.pypa.io/en/stable/cli/pip_install/)

[S6] Microsoft Learn: icacls permissions, inheritance, ownership and verification.
[Windows icacls reference](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/icacls)

[S7] Microsoft Learn: Windows access-control concepts, accounts, groups and ACLs.
[Windows access-control overview](https://learn.microsoft.com/en-us/windows/security/identity-protection/access-control/access-control)

[S8] Python command-line documentation: -I isolated mode and interpreter options.
[Python command-line reference](https://docs.python.org/3/using/cmdline.html)

[S9] Microsoft Learn: Get-FileHash and SHA-256 integrity checks.
[PowerShell Get-FileHash reference](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/get-filehash)

### Validation boundary

The Windows commands and ACL template are a proposed runbook, not a tested lab-PC installer. No lab PC, account, driver, profile or instrument was changed. The project gate rerun here reported 15 passed / 4 skipped; full offline suite 318 passed / 4 skipped with inherited warnings. No local Windows pass output was attached. Collision-safe map allocation was not implemented because the required gate remains open. The supplied source snapshot and current live Git status must be checked before any release.

### Sign-off checklist

- [ ] Reviewed source commit and unique release ID recorded.
- [ ] QtWidgets gate executed without skips; full offline checks reviewed.
- [ ] Bundle/lock/wheel hashes and matching Windows Python recorded.
- [ ] Non-editable environment recreated at its final protected path.
- [ ] Operator read/execute and workspace-write permissions verified.
- [ ] Profile reviewed, protected and backed up; configuration IDs correct.
- [ ] Required native prerequisites and supervised device acceptance recorded.
- [ ] Shortcuts point to accepted release; previous release retained.
- [ ] Operator instructions, data backup and rollback owner agreed.

**Keep the existing working lab installation until this checklist is satisfied.**

## Subsequent device-wrapper audit: release caveat

This runbook's original source basis and counts above are historical. The subsequent
input is snapshot `labtools_source_20261028_215033.txt`, HEAD
`ceaabec9ea4882c1882f71facf604a04099a5992`. The Qt gate remains 15 passed / 4 skipped;
no local Windows pass log is embedded. No deployment or permissions were changed.

[Wrapper audit](device-wrapper-audit.md) documents ITC partial-startup leaks, HORIBA
cleanup visibility, IDQ response eval and other failure-path gaps. [Repairs](device-wrapper-repair-plan.md)
are planned, not implemented. Do not treat the guide, a protected wheel, a lint pass or
a fake test as hardware acceptance. Keep protected core/profile/launchers separate
from writable operator recipes/data. Collision-safe map allocation is still unfixed;
the warning above remains valid. Retain the accepted lab release and rollback path.

## ITC W1 release caveat

[ITC transport lifecycle W1](itc4000-lifecycle-checkpoint.md) is implemented with fake-PyVISA tests only.
Transport close still sends no laser-off, TEC-off or current-reset command. Failed
handles remain uncertain; commands are blocked after teardown begins. ExceptionGroup
reports ordinary cleanup failures; startup/body exceptions retain cleanup details.
This does not certify output state, drivers, SDK teardown or physical safety. Preserve
protected core/profile/launchers and writable operator recipes/data. Do not deploy as
physically accepted based on offline tests. The IDQ eval parser and other wrapper
findings remain open; acquisition Qt gate is still unmet. No lab-PC deployment occurred.

## HORIBA W2 release caveat

[W2 lifecycle](horiba-lifecycle-checkpoint.md) is offline fake-SDK validated only. Cleanup failures are now
visible, but native calls may block and retained failed handles remain uncertain.
Optical commands, shutter behaviour, SDK sleeps and exposure minima are unchanged.
No driver/physical acceptance or deployment occurred. Keep the prior accepted lab
release and protected-core/writable-workspace boundary. Qt acquisition gate and other
wrapper findings remain open.
