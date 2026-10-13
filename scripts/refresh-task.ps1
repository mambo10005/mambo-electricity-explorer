<#
.SYNOPSIS
    Optional Windows scheduled task for `mambo refresh` (Stage 15, ADR 0013).

.DESCRIPTION
    Manages ONLY this application's task: \mambo-electricity-explorer\refresh.
    The default action is Preview: it prints the task XML and registers nothing.

    Actions:
      Preview   print the task definition (default; changes nothing)
      Register  register the task for the current user (explicit; refuses if it exists
                unless -Replace)
      Inspect   show whether the task exists, its state, and last/next run times
      Disable   disable the task (keeps its definition)
      Remove    unregister the task

    The task runs as the current user, only while that user is logged on (no stored
    password), with least privilege, a bounded run time, no overlapping instances, and
    only when a network is available. It does not wake the computer and does not change
    power settings. If a start is missed (computer off or asleep, user logged off),
    -StartWhenAvailable (on by default) runs it once as soon as possible afterwards;
    pass -NoCatchUpStart to skip missed starts instead.

    No credentials are placed in the task. The EIA key is read by `mambo` at run time
    from EIA_API_KEY or the gitignored .env in the working directory.

    Manual equivalent of the scheduled command (from the repository root):
      .venvs\py314\Scripts\mambo.exe refresh

.EXAMPLE
    pwsh -File scripts/refresh-task.ps1                     # preview only
    pwsh -File scripts/refresh-task.ps1 -Action Inspect
#>
[CmdletBinding()]
param(
    [ValidateSet("Preview", "Register", "Inspect", "Disable", "Remove")]
    [string]$Action = "Preview",
    [ValidateSet("3.11", "3.14")]
    [string]$Python = "3.14",
    [ValidatePattern("^([01]\d|2[0-3]):[0-5]\d$")]
    [string]$At = "07:15",
    [ValidateRange(5, 120)]
    [int]$TimeLimitMinutes = 30,
    [switch]$NoCatchUpStart,
    [switch]$Replace,
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
# The only task this script ever touches.
$TaskPath = "\mambo-electricity-explorer\"
$TaskName = "refresh"

function Get-TaskXml {
    $venv = ".venvs\py" + $Python.Replace(".", "")
    $exe = Join-Path $RepoRoot "$venv\Scripts\mambo.exe"
    if (-not [System.IO.Path]::IsPathRooted($exe)) { throw "interpreter path must be absolute" }
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $esc = { param($s) [System.Security.SecurityElement]::Escape($s) }
    $catchUp = if ($NoCatchUpStart) { "false" } else { "true" }
    $start = "2026-01-01T" + $At + ":00"
    return @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>mambo-electricity-explorer: bounded local refresh of EIA-930 and ERCOT NP6-345-CD (mambo refresh). Collects only while this computer is on, the user is logged on, and a network is available.</Description>
    <URI>$($TaskPath)$($TaskName)</URI>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>$start</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$(& $esc $user)</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <StartWhenAvailable>$catchUp</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT$($TimeLimitMinutes)M</ExecutionTimeLimit>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>$(& $esc $exe)</Command>
      <Arguments>refresh</Arguments>
      <WorkingDirectory>$(& $esc $RepoRoot)</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"@
}

function Get-OwnTask {
    Get-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -ErrorAction SilentlyContinue
}

switch ($Action) {
    "Preview" {
        $xml = Get-TaskXml
        Write-Output $xml
        Write-Output ""
        try {
            # Parse with Task Scheduler's own definition object; this registers nothing.
            $service = New-Object -ComObject Schedule.Service
            $service.Connect()
            $definition = $service.NewTask(0)
            $definition.XmlText = $xml
            Write-Output "Task Scheduler parsed this definition (not registered)."
        } catch {
            Write-Output "Task Scheduler could not parse this definition: $($_.Exception.Message)"
            exit 1
        }
        Write-Output "Preview only: nothing was registered. To register for the current user:"
        Write-Output "  pwsh -File scripts/refresh-task.ps1 -Action Register"
    }
    "Register" {
        $exe = Join-Path $RepoRoot (".venvs\py" + $Python.Replace(".", "") + "\Scripts\mambo.exe")
        if (-not (Test-Path $exe)) { throw "locked environment not found: run scripts/setup-env.ps1 first" }
        if ((Get-OwnTask) -and -not $Replace) { throw "task $TaskPath$TaskName already exists (use -Replace)" }
        Register-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Xml (Get-TaskXml) -Force:$Replace | Out-Null
        Write-Output "Registered $TaskPath$TaskName for the current user (least privilege)."
    }
    "Inspect" {
        $task = Get-OwnTask
        if (-not $task) { Write-Output "Task $TaskPath$TaskName is not registered."; break }
        $info = Get-ScheduledTaskInfo -TaskPath $TaskPath -TaskName $TaskName
        [pscustomobject]@{
            Task           = "$TaskPath$TaskName"
            State          = $task.State
            LastRunTime    = $info.LastRunTime
            LastTaskResult = $info.LastTaskResult
            NextRunTime    = $info.NextRunTime
        } | Format-List
    }
    "Disable" {
        if (-not (Get-OwnTask)) { Write-Output "Task $TaskPath$TaskName is not registered."; break }
        Disable-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName | Out-Null
        Write-Output "Disabled $TaskPath$TaskName."
    }
    "Remove" {
        if (-not (Get-OwnTask)) { Write-Output "Task $TaskPath$TaskName is not registered."; break }
        Unregister-ScheduledTask -TaskPath $TaskPath -TaskName $TaskName -Confirm:$false
        Write-Output "Removed $TaskPath$TaskName."
    }
}
