[CmdletBinding()]
param(
    [string]$OutputPath = (Join-Path (Get-Location) ("labtools_source_{0}.txt" -f (Get-Date -Format "yyyyMMdd_HHmmss")))
)
$ErrorActionPreference = "Stop"
$root = (git rev-parse --show-toplevel).Trim()
if (-not $root) { throw "Not inside a Git repository." }
Set-Location $root
$exclude = @(
    '.git/', '.venv/', 'build/', 'dist/', '__pycache__/', '.pytest_cache/',
    '.ruff_cache/', '.mypy_cache/', '.tox/', '.nox/', '.labtools-backups/',
    'labtools_source_', 'apply_labtools_', '*.egg-info/'
)
$textExtensions = @(
    '.py','.pyi','.toml','.md','.txt','.json','.yaml','.yml','.ini','.cfg','.conf',
    '.csv','.tsv','.ps1','.bat','.cmd','.sh','.gitignore','.gitattributes','.rst'
)
function Is-Excluded([string]$name) {
    $n = $name.Replace('\','/')
    foreach ($item in $exclude) {
        if ($item.StartsWith('*')) { if ($n -like "*$item") { return $true } }
        elseif ($n.StartsWith($item) -or $n.Contains("/$item")) { return $true }
    }
    return $false
}
function Is-Text([string]$name) {
    $leaf = [IO.Path]::GetFileName($name)
    if ($leaf -in @('LICENSE','LICENSE.txt','Makefile','Dockerfile','uv.lock')) { return $true }
    return $textExtensions -contains [IO.Path]::GetExtension($name).ToLowerInvariant()
}
$utf8 = [Text.UTF8Encoding]::new($false)
$content = [Text.StringBuilder]::new()
function Add-Line([string]$value = '') { [void]$content.Append($value).Append("`n") }
function Add-Section([string]$title, [scriptblock]$command) {
    Add-Line "===== $title ====="
    try { $result = & $command 2>&1 | Out-String; Add-Line $result.TrimEnd() }
    catch { Add-Line ("ERROR: " + $_.Exception.Message) }
    Add-Line
}
Add-Line 'LABTOOLS SOURCE SNAPSHOT'
Add-Line ("Created UTC: " + [DateTime]::UtcNow.ToString('o'))
Add-Line ("Repository root: " + $root)
Add-Line
Add-Section 'GIT BRANCH AND HEAD' { git status --porcelain=v2 --branch }
Add-Section 'GIT STATUS SHORT' { git status --short --untracked-files=all }
Add-Section 'RECENT COMMITS' { git log -n 15 --date=iso-strict --pretty=format:'%H%x09%ad%x09%an%x09%s' }
Add-Section 'REMOTES' { git remote -v }
Add-Section 'DIFF FROM MAIN NAME STATUS' { git diff --name-status main...HEAD }
Add-Section 'DIFF FROM MAIN STAT' { git diff --stat main...HEAD }
Add-Section 'WORKTREE DIFF STAT' { git diff --stat }
Add-Section 'STAGED DIFF STAT' { git diff --cached --stat }
Add-Section 'WORKTREE DIFF CHECK' { git diff --check }
Add-Section 'STAGED DIFF CHECK' { git diff --cached --check }
Add-Section 'PYPROJECT' { if (Test-Path pyproject.toml) { Get-Content pyproject.toml -Raw } }
Add-Section 'UV VERSION' { uv --version }
Add-Section 'PYTHON VERSION' { uv run --no-sync python --version }
Add-Section 'RUFF VERSION' { uv run --no-sync ruff --version }
Add-Section 'PYTEST VERSION' { uv run --no-sync python -m pytest --version }
$files = @(git ls-files --cached --others --exclude-standard) |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -and -not (Is-Excluded $_) } |
    Sort-Object -Unique
Add-Line '===== FILE MANIFEST ====='
foreach ($name in $files) {
    if (-not (Test-Path -LiteralPath $name -PathType Leaf)) { continue }
    $item = Get-Item -LiteralPath $name
    $hash = (Get-FileHash -LiteralPath $name -Algorithm SHA256).Hash.ToLowerInvariant()
    Add-Line ("{0}`t{1}`t{2}" -f $name, $item.Length, $hash)
}
Add-Line
Add-Line '===== TEXT FILE CONTENTS ====='
foreach ($name in $files) {
    if (-not (Test-Path -LiteralPath $name -PathType Leaf) -or -not (Is-Text $name)) { continue }
    $bytes = [IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $name))
    $text = $utf8.GetString($bytes).Replace("`r`n","`n").Replace("`r","`n")
    $trailing = 0
    while ($text.EndsWith("`n")) { $trailing++; $text = $text.Substring(0,$text.Length-1) }
    Add-Line ("BEGIN FILE: " + $name.Replace('\','/'))
    Add-Line ('=' * 80)
    if ($text.Length -gt 0) { [void]$content.Append($text).Append("`n") }
    Add-Line ("END FILE: " + $name.Replace('\','/'))
    Add-Line ("SOURCE TRAILING NEWLINES JSON: " + ($trailing | ConvertTo-Json -Compress))
    Add-Line
}
[IO.File]::WriteAllText([IO.Path]::GetFullPath($OutputPath), $content.ToString(), $utf8)
Write-Host "Snapshot written to: $([IO.Path]::GetFullPath($OutputPath))"
Write-Host "Included $($files.Count) tracked/untracked non-ignored files in the manifest."
