$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$dataDir = Join-Path $repoRoot "data"

if (-not (Test-Path $dataDir)) {
  Write-Host "Data directory not found."
  exit 1
}

$errors = 0
Get-ChildItem -Path $dataDir -Recurse -Filter "*.json" | ForEach-Object {
  try {
    Get-Content $_.FullName | ConvertFrom-Json | Out-Null
  } catch {
    Write-Host "Invalid JSON: $($_.FullName)"
    $errors += 1
  }
}

if ($errors -gt 0) {
  Write-Host "Validation failed: $errors errors"
  exit 1
}

Write-Host "Validation passed"
exit 0
