[CmdletBinding()]
param(
    [string]$WheelPath
)

$ErrorActionPreference = "Stop"
$repo = (git rev-parse --show-toplevel).Trim()
if (-not $repo) { throw "Run inside the LabTools Git repository." }
Set-Location -LiteralPath $repo

if (-not $WheelPath) {
    $wheel = Get-ChildItem -LiteralPath "dist" -Filter "lab_tools-*.whl" |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if (-not $wheel) { throw "No LabTools wheel found under dist/. Run 'uv build' first." }
    $WheelPath = $wheel.FullName
}
$WheelPath = (Resolve-Path -LiteralPath $WheelPath).Path
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("labtools-wheel-smoke-" + [guid]::NewGuid().ToString("N"))
$venv = Join-Path $tempRoot ".venv"

try {
    & ".\.venv\Scripts\python.exe" -m venv $venv
    $python = Join-Path $venv "Scripts\python.exe"
    & $python -m pip install --disable-pip-version-check --no-deps $WheelPath
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $python -c "from importlib.metadata import version; import labtools; assert version('lab-tools') == '0.2.0rc1'; print('Wheel smoke passed:', version('lab-tools'), labtools.__file__)"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Remove-Item -Recurse -Force $tempRoot -ErrorAction SilentlyContinue
}
