$ErrorActionPreference = 'Stop'
$py = (Resolve-Path '.\.venv\Scripts\python.exe').Path
$out = Join-Path $env:USERPROFILE (
    'Downloads\labtools_snapshot_' +
    (Get-Date -Format 'yyyyMMddTHHmmssfff') +
    '.txt'
)

@'
from pathlib import Path
import datetime
import hashlib
import json
import subprocess
import sys

root = Path.cwd().resolve()
output = Path(sys.argv[1])
MAX_BYTES = 2_000_000

def git(*args):
    result = subprocess.run(
        ["git", *args], cwd=root,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False,
    )
    return {
        "command": ["git", *args],
        "exit_code": result.returncode,
        "stdout": result.stdout.decode("utf-8", errors="replace"),
        "stderr": result.stderr.decode("utf-8", errors="replace"),
    }

def git_required(*args):
    result = git(*args)
    if result["exit_code"]:
        raise RuntimeError(result["stderr"])
    return result["stdout"]

actual_root = Path(git_required("rev-parse", "--show-toplevel").strip()).resolve()
if actual_root != root:
    raise RuntimeError("Run from the repository root.")

selected = {}
missing = []
excluded = []
manifest = []
sections = []

def add(label, path):
    if path.is_file():
        selected.setdefault(label, path)
    else:
        missing.append(label)

# Current tracked files, including local modifications.
tracked = git_required("ls-files", "-z").split("\0")
skip_parts = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".labtools-validation", "measurement-data", "build", "dist",
}
for name in tracked:
    if not name:
        continue
    relative = Path(name)
    if any(part in skip_parts for part in relative.parts):
        excluded.append(name)
        continue
    add("repository/" + relative.as_posix(), root / relative)

# Include the helpers even when untracked or locally ignored.
helpers = [
    "apply_labtools_expanded_r1_scope_v1.py",
    "run_labtools_expanded_r1_evidence_v1.py",
    "new_labtools_snapshot copy.ps1",
]
for name in helpers:
    add("repository/" + name, root / name)

# Include root-level PowerShell scripts for snapshot-script comparison.
for path in sorted(root.glob("*.ps1")):
    add("repository/" + path.name, path)

# Local exclusions are not tracked, but matter for interpreting status.
exclude_name = git_required("rev-parse", "--git-path", "info/exclude").strip()
exclude_path = Path(exclude_name)
if not exclude_path.is_absolute():
    exclude_path = root / exclude_path
add("git-local/info-exclude", exclude_path)

# Inventory validation runs without embedding copied source/build trees.
validation = root / ".labtools-validation"
runs = []
if validation.is_dir():
    for directory in sorted(validation.iterdir()):
        if directory.is_dir() and not directory.is_symlink():
            runs.append({
                "directory": directory.name,
                "has_results": (directory / "results.json").is_file(),
            })

    # Include the newest actual tooling verification result and direct
    # logs/XML/JSON. Never recurse into build or staging environments.
    verified_runs = [
        directory for directory in validation.glob("tooling-r1-verify-*")
        if directory.is_dir()
        and not directory.is_symlink()
        and (directory / "results.json").is_file()
    ]
    if verified_runs:
        latest = max(
            verified_runs,
            key=lambda p: (p / "results.json").stat().st_mtime_ns,
        )
        for path in sorted(latest.iterdir()):
            if path.is_file() and path.suffix.lower() in {
                ".json", ".log", ".xml", ".txt", ".py"
            }:
                add("verification/" + latest.name + "/" + path.name, path)
    else:
        missing.append("latest tooling-r1-verify results.json")

    # Original parent manifest only; original artifacts stay on disk.
    parent = (
        validation /
        "expanded-r1-20261105T143002139702Z-743afbb9" /
        "results.json"
    )
    add("parent-evidence/results.json", parent)

# Include archive manifests, not the archived backup contents.
archive_root = root.parent / "labtools-archive"
if archive_root.is_dir():
    for directory in sorted(archive_root.iterdir()):
        if directory.is_dir() and not directory.is_symlink():
            for name in ("manifest.csv", "journal.json"):
                path = directory / name
                if path.is_file():
                    add("archive-manifests/" + directory.name + "/" + name, path)

metadata = {
    "created_utc": datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat(),
    "repository_root": str(root),
    "python_executable": sys.executable,
    "python_version": sys.version,
    "git": [
        git("rev-parse", "HEAD"),
        git("branch", "--show-current"),
        git("status", "--short", "--untracked-files=all"),
        git("log", "-15", "--oneline"),
        git("show", "-1", "--format=fuller", "--stat"),
        git("diff", "--stat"),
        git("diff", "--cached", "--stat"),
        git("diff", "--no-ext-diff", "--no-textconv", "HEAD", "--",
            "docs", "tests", "pyproject.toml", "uv.lock"),
    ],
    "validation_runs": runs,
    "missing_requested_inputs": missing,
    "excluded_tracked_paths": excluded,
}

for label, path in sorted(selected.items()):
    entry = {"path": label}
    try:
        if path.is_symlink():
            entry["status"] = "symbolic link omitted"
        else:
            raw = path.read_bytes()
            entry["bytes"] = len(raw)
            entry["sha256"] = hashlib.sha256(raw).hexdigest()
            if len(raw) > MAX_BYTES:
                entry["status"] = "oversized; content omitted"
            elif b"\x00" in raw:
                entry["status"] = "binary; content omitted"
            else:
                text = raw.decode("utf-8-sig")
                entry["status"] = "included"
                sections.append(
                    "\n===== BEGIN " + label + " =====\n"
                    "SHA256: " + entry["sha256"] + "\n\n" +
                    text +
                    "\n===== END " + label + " =====\n"
                )
    except (OSError, UnicodeError) as exc:
        entry["status"] = "read/decode error"
        entry["error"] = str(exc)
    manifest.append(entry)

# Detect Git-state changes during collection rather than silently
# presenting the snapshot as atomic.
metadata["git_status_after"] = git(
    "status", "--short", "--untracked-files=all"
)
metadata["head_after"] = git("rev-parse", "HEAD")
metadata["git_state_stable"] = (
    metadata["git"][0]["stdout"] == metadata["head_after"]["stdout"]
    and metadata["git"][2]["stdout"]
    == metadata["git_status_after"]["stdout"]
)

with output.open("x", encoding="utf-8", newline="\n") as handle:
    handle.write("LABTOOLS REPOSITORY SNAPSHOT\n")
    handle.write(
        "Read-only collection. No tests or installers executed.\n"
        "Not an atomic filesystem snapshot; SHA256 values identify "
        "the individual captured file bytes.\n"
    )
    handle.write("\n===== METADATA =====\n")
    handle.write(json.dumps(metadata, indent=2))
    handle.write("\n\n===== FILE MANIFEST =====\n")
    handle.write(json.dumps(manifest, indent=2))
    for section in sections:
        handle.write(section)

print("Created:", output)
print("Size:", f"{output.stat().st_size / 1_000_000:.2f} MB")
print("Included files:", sum(x["status"] == "included" for x in manifest))
print("Omitted/error entries:", sum(x["status"] != "included" for x in manifest))
print("Missing requested inputs:", len(missing))
print("Git state stable during capture:", metadata["git_state_stable"])
print("Repository unchanged by this script.")
'@ | & $py - "$out"

if ($LASTEXITCODE -ne 0) {
    throw 'Snapshot creation failed. Preserve the error output.'
}

Get-Item -LiteralPath $out | Select-Object FullName, Length