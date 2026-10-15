<#
.SYNOPSIS
  Routine offline quality gate. Exits nonzero if any check fails.
.EXAMPLE
  pwsh -File scripts/check.ps1                # Python 3.14 environment
  pwsh -File scripts/check.ps1 -Python 3.11   # Python 3.11 environment
.NOTES
  Requires the environment from scripts/setup-env.ps1. Changes no files and downloads nothing.
#>
param(
    [ValidatePattern('^3\.\d+$')]
    [string]$Python = '3.14'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$envDir = Join-Path $repo (".venvs/py" + ($Python -replace '\.', ''))
$interpreter = Join-Path $envDir 'Scripts/python.exe'
if (-not (Test-Path $interpreter)) {
    Write-Error "No environment at $envDir. Run: pwsh -File scripts/setup-env.ps1 -Python $Python"
    exit 2
}
Push-Location $repo
try {
    & $interpreter (Join-Path $repo 'scripts/quality.py')
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
