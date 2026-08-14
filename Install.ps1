param([switch]$Repair)
$ErrorActionPreference = 'Stop'
$source = Split-Path -Parent $MyInvocation.MyCommand.Path
$documents = [Environment]::GetFolderPath('MyDocuments')
$skins = Join-Path $documents 'Rainmeter\Skins'
$target = Join-Path $skins 'WindowsPorthexTheme'
$backupRoot = Join-Path $documents 'Rainmeter\Backups'
$rainmeter = Join-Path $env:ProgramFiles 'Rainmeter\Rainmeter.exe'
$wscript = Join-Path $env:WINDIR 'System32\wscript.exe'
$backup = $null
$hadTarget = Test-Path $target
$tasks = @('PorthexThemeAutoUpdate','PorthexTaskbarStatusHost','WindowsPorthexServerMonitor')
$existingTasks = @{}
foreach ($name in $tasks) {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    $existingTasks[$name] = if ($task) { Export-ScheduledTask -TaskName $name } else { $null }
}

if (-not (Test-Path $rainmeter)) { throw 'Rainmeter is not installed in Program Files.' }
try {
    if ((Resolve-Path $source).Path -ne $target -and $hadTarget) {
        New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
        $backup = Join-Path $backupRoot ("WindowsPorthexTheme-before-install-{0:yyyyMMdd-HHmmss}" -f (Get-Date))
        Copy-Item $target $backup -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    $preserved = @{}
    foreach ($relative in @('@Resources\UserSettings.inc','@Resources\Profile.inc')) {
        $path = Join-Path $target $relative
        if (Test-Path $path) { $preserved[$relative] = [IO.File]::ReadAllBytes($path) }
    }
    if ((Resolve-Path $source).Path -ne (Resolve-Path $target).Path) { Copy-Item (Join-Path $source '*') $target -Recurse -Force }
    foreach ($relative in $preserved.Keys) { [IO.File]::WriteAllBytes((Join-Path $target $relative), $preserved[$relative]) }

    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
    $logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
    $daily = New-ScheduledTaskTrigger -Daily -At '12:00'
    Register-ScheduledTask -TaskName 'PorthexThemeAutoUpdate' -Action (New-ScheduledTaskAction -Execute $wscript -Argument ('"' + (Join-Path $target '@Resources\RunUpdate.vbs') + '" auto')) -Trigger @($logon,$daily) -Principal $principal -Settings $settings -Force | Out-Null

    $python = $null
    foreach ($candidate in @('python','python3','py')) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($command) {
            if ($candidate -eq 'py') { $probe = & $command.Source -3 -c 'import sys;print(sys.executable)' 2>$null }
            else { $probe = & $command.Source -c 'import sys;print(sys.executable)' 2>$null }
            if ($LASTEXITCODE -eq 0 -and (Test-Path $probe)) { $python = $probe; break }
        }
    }
    if (-not $python) { throw 'Python 3 was not found on PATH. Install Python, then rerun Install.ps1.' }
    Register-ScheduledTask -TaskName 'PorthexTaskbarStatusHost' -Action (New-ScheduledTaskAction -Execute $python -Argument ('"' + (Join-Path $target '@Resources\TaskbarStatusHost.py') + '"')) -Trigger $logon -Principal $principal -Settings $settings -Force | Out-Null
    Register-ScheduledTask -TaskName 'WindowsPorthexServerMonitor' -Action (New-ScheduledTaskAction -Execute $python -Argument ('"' + (Join-Path $target '@Resources\ServerMonitor.py') + '"')) -Trigger $logon -Principal $principal -Settings $settings -Force | Out-Null
    & $python (Join-Path $target '@Resources\WorkspaceController.py') setup
    if ($LASTEXITCODE -ne 0) { throw 'Porthex profile setup failed.' }

    Start-Process $rainmeter -ArgumentList '!RefreshApp' -Wait
    Start-Process $rainmeter -ArgumentList '!ActivateConfig','WindowsPorthexTheme\TopBar','TopBar.ini' -Wait
    Start-Process $rainmeter -ArgumentList '!ActivateConfig','WindowsPorthexTheme\Field','Field.ini' -Wait
    Start-Process $rainmeter -ArgumentList '!ActivateConfig','WindowsPorthexTheme\Settings','Settings.ini' -Wait
    Write-Output "Porthex theme installed at $target"
} catch {
    foreach ($name in $tasks) {
        if ($existingTasks[$name]) {
            Register-ScheduledTask -TaskName $name -Xml $existingTasks[$name] -Force | Out-Null
        } else {
            Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
        }
    }
    if ($backup -and (Test-Path $backup)) {
        Remove-Item $target -Recurse -Force -ErrorAction SilentlyContinue
        Copy-Item $backup $target -Recurse -Force
    } elseif (-not $hadTarget) {
        Remove-Item $target -Recurse -Force -ErrorAction SilentlyContinue
    }
    throw
}
