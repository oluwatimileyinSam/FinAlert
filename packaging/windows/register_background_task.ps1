param(
    [Parameter(Mandatory = $true)]
    [string]$InstallDirectory,

    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$TaskName = "FinAlert Background Monitor"

if ($Uninstall) {
    $task = Get-ScheduledTask `
        -TaskName $TaskName `
        -ErrorAction SilentlyContinue

    if ($task) {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask `
            -TaskName $TaskName `
            -Confirm:$false
    }

    exit 0
}

$InstallDirectory = [System.IO.Path]::GetFullPath($InstallDirectory)
$Executable = Join-Path $InstallDirectory "FinAlert.exe"

if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
    throw "FinAlert.exe was not found at: $Executable"
}

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

$action = New-ScheduledTaskAction `
    -Execute $Executable `
    -Argument "--background" `
    -WorkingDirectory $InstallDirectory

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser

$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Runs FinAlert mailbox monitoring in the background." `
    -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Output "FinAlert background monitoring task installed and started."
