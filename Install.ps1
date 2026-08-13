param(
    [switch]$Repair
)
$ErrorActionPreference = 'Stop'
$source = Split-Path -Parent $MyInvocation.MyCommand.Path
$documents = [Environment]::GetFolderPath('MyDocuments')
$skins = Join-Path $documents 'Rainmeter\Skins'
$target = Join-Path $skins 'WindowsPorthexTheme'
$backupRoot = Join-Path $documents 'Rainmeter\Backups'
$rainmeter = Join-Path $env:ProgramFiles 'Rainmeter\Rainmeter.exe'
$wscript = Join-Path $env:WINDIR 'System32\wscript.exe'

if (-not (Test-Path $rainmeter)) { throw 'Rainmeter is not installed in Program Files.' }
if ((Resolve-Path $source).Path -ne $target -and (Test-Path $target)) {
    New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
    $backup = Join-Path $backupRoot ("WindowsPorthexTheme-before-install-{0:yyyyMMdd-HHmmss}" -f (Get-Date))
    Copy-Item $target $backup -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $target | Out-Null
if ((Resolve-Path $source).Path -ne (Resolve-Path $target).Path) {
    Copy-Item (Join-Path $source '*') $target -Recurse -Force
}

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$daily = New-ScheduledTaskTrigger -Daily -At '12:00'

Register-ScheduledTask -TaskName 'PorthexThemeAutoUpdate' `
    -Action (New-ScheduledTaskAction -Execute $wscript -Argument ('"' + (Join-Path $target '@Resources\RunUpdate.vbs') + '" auto')) `
    -Trigger @($logon, $daily) -Principal $principal -Settings $settings -Force | Out-Null

$pythonCandidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe')
)
$python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($python) {
    Register-ScheduledTask -TaskName 'PorthexTaskbarStatusHost' `
        -Action (New-ScheduledTaskAction -Execute $python -Argument ('"' + (Join-Path $target '@Resources\TaskbarStatusHost.py') + '"')) `
        -Trigger $logon -Principal $principal -Settings $settings -Force | Out-Null
    Register-ScheduledTask -TaskName 'WindowsPorthexServerMonitor' `
        -Action (New-ScheduledTaskAction -Execute $python -Argument ('"' + (Join-Path $target '@Resources\ServerMonitor.py') + '"')) `
        -Trigger $logon -Principal $principal -Settings $settings -Force | Out-Null
    & $python (Join-Path $target '@Resources\WorkspaceController.py') setup
}

Start-Process $rainmeter -ArgumentList '!RefreshApp' -Wait
Start-Process $rainmeter -ArgumentList '!ActivateConfig','WindowsPorthexTheme\TopBar','TopBar.ini' -Wait
Start-Process $rainmeter -ArgumentList '!ActivateConfig','WindowsPorthexTheme\Field','Field.ini' -Wait
Start-Process $rainmeter -ArgumentList '!ActivateConfig','WindowsPorthexTheme\Settings','Settings.ini' -Wait
Write-Output "Porthex theme installed at $target"
