[CmdletBinding()]
param(
    [string]$OutputPath = (Join-Path $env:USERPROFILE (
        "Downloads\labtools_quick_snapshot_{0}.txt" -f (Get-Date -Format "yyyyMMddTHHmmss")
    ))
)

$ErrorActionPreference = "Stop"
$repo = (git rev-parse --show-toplevel).Trim()
if (-not $repo) { throw "Run inside the LabTools Git repository." }
Set-Location -LiteralPath $repo

function Add-Section([string]$Title, [object[]]$Content) {
    Add-Content -LiteralPath $OutputPath -Encoding UTF8 -Value ""
    Add-Content -LiteralPath $OutputPath -Encoding UTF8 -Value "===== $Title ====="
    if ($null -ne $Content) {
        Add-Content -LiteralPath $OutputPath -Encoding UTF8 -Value $Content
    }
}

function Add-EncodedFile([string]$RelativePath) {
    if (-not (Test-Path -LiteralPath $RelativePath -PathType Leaf)) { return }
    $bytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $RelativePath).Path)
    $hash = (Get-FileHash -LiteralPath $RelativePath -Algorithm SHA256).Hash
    $base64 = [System.Convert]::ToBase64String($bytes)
    Add-Content -LiteralPath $OutputPath -Encoding ASCII -Value ""
    Add-Content -LiteralPath $OutputPath -Encoding ASCII -Value "=== FILE: $($RelativePath -replace '\\','/') ==="
    Add-Content -LiteralPath $OutputPath -Encoding ASCII -Value "=== SIZE: $($bytes.Length) ==="
    Add-Content -LiteralPath $OutputPath -Encoding ASCII -Value "=== SHA256: $hash ==="
    Add-Content -LiteralPath $OutputPath -Encoding ASCII -Value "=== ENCODING: BASE64 ==="
    Add-Content -LiteralPath $OutputPath -Encoding ASCII -Value $base64
    Add-Content -LiteralPath $OutputPath -Encoding ASCII -Value "=== END FILE ==="
}

@(
    "LABTOOLS QUICK DEVELOPMENT SNAPSHOT V2"
    "Generated: $(Get-Date -Format o)"
    "Repository: $repo"
    "Branch: $(git branch --show-current)"
    "HEAD: $(git rev-parse HEAD)"
    "Purpose: continue recent development from Git state, diffs, tests, and exact changed files"
) | Set-Content -LiteralPath $OutputPath -Encoding UTF8

Add-Section "GIT STATUS" @(git status --short --untracked-files=all)
Add-Section "RECENT COMMITS" @(git log -n 20 --date=iso --pretty=format:"%h%x09%ad%x09%an%x09%s")
Add-Section "UNSTAGED DIFF STAT" @(git diff --stat)
Add-Section "UNSTAGED DIFF" @(git diff --no-ext-diff --no-color)
Add-Section "STAGED DIFF STAT" @(git diff --cached --stat)
Add-Section "STAGED DIFF" @(git diff --cached --no-ext-diff --no-color)
Add-Section "PROJECT CONFIG" @(
    "Python: $(& .\.venv\Scripts\python.exe --version 2>&1)"
    "Git: $(git --version)"
)

$changed = @(
    git diff --name-only
    git diff --cached --name-only
    git ls-files --others --exclude-standard
) | Where-Object { $_ } | Sort-Object -Unique

$context = @(
    "pyproject.toml"
    "uv.lock"
    "README.md"
    "docs/README.md"
    "docs/current-state.md"
    "docs/release-plan.md"
    "docs/repository-hygiene.md"
) | Where-Object { Test-Path -LiteralPath $_ }

$include = @($changed + $context) | Sort-Object -Unique
Add-Section "EXACT FILE BUNDLE" @(
    "Files included: $($include.Count)"
    "Changed/untracked files plus release and project context follow as Base64 records."
)
foreach ($file in $include) { Add-EncodedFile $file }

$finalHash = (Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256).Hash
Write-Host "Created: $OutputPath"
Write-Host "Files included: $($include.Count)"
Write-Host "SHA256: $finalHash"
