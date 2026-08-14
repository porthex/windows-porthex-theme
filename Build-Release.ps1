param(
    [Parameter(Mandatory=$true)][string]$Version,
    [string]$Output
)
$ErrorActionPreference = 'Stop'
$repo = $PSScriptRoot
if (-not $Output) { $Output = Join-Path $repo 'dist' }
if ($Version -notmatch '^\d+\.\d+\.\d+$') { throw 'Version must use semantic versioning, for example 1.2.3.' }
$repo = (Resolve-Path $repo).Path
$stageRoot = Join-Path ([IO.Path]::GetTempPath()) ("porthex-theme-package-" + [guid]::NewGuid())
$stage = Join-Path $stageRoot 'WindowsPorthexTheme'
New-Item -ItemType Directory -Force -Path $stage,$Output | Out-Null
$excludedDirs = @('.git','dist','tests','.github')
$excludedFiles = @('TaskbarStatusHost.state.json','GoogleData.inc','ServerData.inc')
Get-ChildItem $repo -Force | Where-Object { $excludedDirs -notcontains $_.Name } | ForEach-Object {
    Copy-Item $_.FullName $stage -Recurse -Force
}
$excludedFiles | ForEach-Object { Get-ChildItem $stage -Recurse -File -Filter $_ -ErrorAction SilentlyContinue | Remove-Item -Force }
Get-ChildItem $stage -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
$files = Get-ChildItem $stage -Recurse -File | ForEach-Object { $_.FullName.Substring($stage.Length + 1).Replace('\','/') } | Sort-Object
$manifest = [ordered]@{
    package='WindowsPorthexTheme'
    version=$Version
    repository='https://github.com/porthex/windows-porthex-theme'
    files=$files
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $stage 'package-manifest.json') -Encoding utf8
$zip = Join-Path $Output 'WindowsPorthexTheme.zip'
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path $stage -DestinationPath $zip -CompressionLevel Optimal
$hash = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  WindowsPorthexTheme.zip" | Set-Content ($zip + '.sha256') -Encoding ascii
Remove-Item $stageRoot -Recurse -Force
Write-Output $zip
Write-Output $hash
