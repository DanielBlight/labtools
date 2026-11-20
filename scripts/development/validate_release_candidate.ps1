[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$KeepDist
)

$ErrorActionPreference = "Stop"
$repo = (git rev-parse --show-toplevel).Trim()
if (-not $repo) { throw "Run inside the LabTools Git repository." }
Set-Location -LiteralPath $repo

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing .venv. Recreate it with: uv sync --frozen --group dev"
}
if (git status --porcelain) {
    throw "Release validation requires a clean working tree."
}

Write-Host "[1/6] Verifying locked environment"
uv sync --frozen --group dev

Write-Host "[2/6] Running Ruff"
& $python -m ruff check src tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "[3/6] Compiling package"
& $python -m compileall -q src
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $SkipTests) {
    Write-Host "[4/6] Running non-hardware tests"
    $oldQt = $env:QT_QPA_PLATFORM
    $oldMpl = $env:MPLBACKEND
    try {
        $env:QT_QPA_PLATFORM = "offscreen"
        $env:MPLBACKEND = "Agg"
        & $python -m pytest -q -ra -m "not hardware"
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    finally {
        if ($null -eq $oldQt) { Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue } else { $env:QT_QPA_PLATFORM = $oldQt }
        if ($null -eq $oldMpl) { Remove-Item Env:\MPLBACKEND -ErrorAction SilentlyContinue } else { $env:MPLBACKEND = $oldMpl }
    }
}
else {
    Write-Host "[4/6] Tests skipped by explicit request"
}

Write-Host "[5/6] Building distributions"
if (-not $KeepDist) { Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue }
uv build

Write-Host "[6/6] Smoke-testing wheel metadata in an isolated environment"
& ".\scripts\development\smoke_test_wheel.ps1"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Release-candidate validation passed." -ForegroundColor Green
