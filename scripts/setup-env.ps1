<#
.SYNOPSIS
  Create or update an isolated verification environment from uv.lock (needs network the first time).
.EXAMPLE
  pwsh -File scripts/setup-env.ps1                # .venvs/py314
  pwsh -File scripts/setup-env.ps1 -Python 3.11   # .venvs/py311
.NOTES
  --locked fails instead of rewriting uv.lock if pyproject.toml and uv.lock disagree.
  Your own .venv is not touched.
#>
param(
    [ValidatePattern('^3\.\d+$')]
    [string]$Python = '3.14'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$previous = $env:UV_PROJECT_ENVIRONMENT
$env:UV_PROJECT_ENVIRONMENT = Join-Path $repo (".venvs/py" + ($Python -replace '\.', ''))
try {
    uv sync --locked --python $Python --project $repo
    exit $LASTEXITCODE
}
finally {
    $env:UV_PROJECT_ENVIRONMENT = $previous
}
