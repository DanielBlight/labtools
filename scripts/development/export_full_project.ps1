[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path $env:USERPROFILE "Downloads"),
    [int64]$TargetPartBytes = 6000000
)

$ErrorActionPreference = "Stop"
$repo = (git rev-parse --show-toplevel).Trim()
if (-not $repo) { throw "Run inside the LabTools Git repository." }
Set-Location -LiteralPath $repo
if ($TargetPartBytes -lt 1000000) { throw "TargetPartBytes must be at least 1000000." }

$stamp = Get-Date -Format "yyyyMMddTHHmmss"
$prefix = "labtools_full_project_$stamp"
$manifest = Join-Path $OutputDirectory "$prefix-manifest.txt"

function Is-Excluded([string]$Path) {
    $normal = $Path -replace '\\','/'
    return (
        $normal -match '(^|/)\.git(/|$)' -or
        $normal -match '(^|/)\.venv(/|$)' -or
        $normal -match '(^|/)__pycache__(/|$)' -or
        $normal -match '(^|/)\.pytest_cache(/|$)' -or
        $normal -match '(^|/)\.ruff_cache(/|$)' -or
        $normal -match '\.pyc$' -or
        $normal -match '\.before_[^/]*$' -or
        $normal -match 'labtools_(quick_snapshot|full_project).*\.txt$'
    )
}

function New-Part([int]$Number) {
    $path = Join-Path $OutputDirectory ("{0}-part-{1:D3}.txt" -f $prefix, $Number)
    @(
        "LABTOOLS FULL PROJECT BUNDLE V2"
        "Part: $Number"
        "Generated: $(Get-Date -Format o)"
        "Repository: $repo"
        "Branch: $(git branch --show-current)"
        "HEAD: $(git rev-parse HEAD)"
        "Encoding: each file is Base64 with path, byte size, and SHA256"
        ""
    ) | Set-Content -LiteralPath $path -Encoding ASCII
    return $path
}

$files = @(git ls-files --cached --others --exclude-standard) |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -and -not (Is-Excluded $_) } |
    Sort-Object -Unique
if (-not $files) { throw "No project files found." }

$partNumber = 1
$partPath = New-Part $partNumber
$partSize = (Get-Item -LiteralPath $partPath).Length
$partCounts = @{}
$fileCount = 0

foreach ($relative in $files) {
    if (-not (Test-Path -LiteralPath $relative -PathType Leaf)) { continue }
    $bytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $relative).Path)
    $hash = (Get-FileHash -LiteralPath $relative -Algorithm SHA256).Hash
    $base64 = [System.Convert]::ToBase64String($bytes)
    $record = @(
        "=== FILE: $($relative -replace '\\','/') ==="
        "=== SIZE: $($bytes.Length) ==="
        "=== SHA256: $hash ==="
        "=== ENCODING: BASE64 ==="
        $base64
        "=== END FILE ==="
        ""
    ) -join "`r`n"
    $recordBytes = [System.Text.Encoding]::ASCII.GetByteCount($record)
    if (($partSize + $recordBytes -gt $TargetPartBytes) -and $partCounts.ContainsKey($partNumber)) {
        $partNumber++
        $partPath = New-Part $partNumber
        $partSize = (Get-Item -LiteralPath $partPath).Length
    }
    Add-Content -LiteralPath $partPath -Encoding ASCII -Value $record
    $partSize += $recordBytes
    if (-not $partCounts.ContainsKey($partNumber)) { $partCounts[$partNumber] = 0 }
    $partCounts[$partNumber]++
    $fileCount++
}

@(
    "LABTOOLS FULL PROJECT MANIFEST V2"
    "Generated: $(Get-Date -Format o)"
    "Repository: $repo"
    "Branch: $(git branch --show-current)"
    "HEAD: $(git rev-parse HEAD)"
    "Files exported: $fileCount"
    "Bundle parts: $partNumber"
    ""
    "===== PARTS ====="
) | Set-Content -LiteralPath $manifest -Encoding UTF8

for ($number = 1; $number -le $partNumber; $number++) {
    $name = "{0}-part-{1:D3}.txt" -f $prefix, $number
    $path = Join-Path $OutputDirectory $name
    $size = (Get-Item -LiteralPath $path).Length
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    Add-Content -LiteralPath $manifest -Encoding UTF8 -Value (
        "$name | files=$($partCounts[$number]) | bytes=$size | sha256=$hash"
    )
}

Add-Content -LiteralPath $manifest -Encoding UTF8 -Value @(
    ""
    "===== GIT STATUS ====="
    (git status --short --untracked-files=all)
    ""
    "===== RECENT COMMITS ====="
    (git log -n 30 --date=iso --pretty=format:"%h%x09%ad%x09%an%x09%s")
    ""
    "===== UNSTAGED DIFF STAT ====="
    (git diff --stat)
    ""
    "===== STAGED DIFF STAT ====="
    (git diff --cached --stat)
)

Write-Host "Created manifest: $manifest"
Write-Host "Files exported: $fileCount"
Write-Host "Parts: $partNumber"
Get-ChildItem -LiteralPath $OutputDirectory -Filter "$prefix-*.txt" |
    Sort-Object Name |
    Select-Object Name, Length, FullName |
    Format-Table -AutoSize
