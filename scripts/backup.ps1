Param(
  [switch]$Incremental,
  [switch]$ExcludeLogs,
  [int]$RetentionDays = 30
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$dataDir = Join-Path $repoRoot "data"
$backupDir = Join-Path $dataDir "backups"
$stateFile = Join-Path $backupDir "last_backup.txt"

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$archivePath = Join-Path $backupDir "backup_$timestamp.zip"

$lastBackup = $null
if ($Incremental -and (Test-Path $stateFile)) {
  $raw = Get-Content $stateFile | Select-Object -First 1
  if ($raw) { $lastBackup = [DateTime]::Parse($raw) }
}

$files = Get-ChildItem -Path $dataDir -Recurse -File
if ($ExcludeLogs) {
  $files = $files | Where-Object { $_.FullName -notmatch "\\logs\\" }
}
if ($Incremental -and $lastBackup) {
  $files = $files | Where-Object { $_.LastWriteTime -gt $lastBackup }
}

if (-not $files) {
  Write-Host "No files to backup."
  exit 0
}

Compress-Archive -Path $files.FullName -DestinationPath $archivePath -Force

if ((Get-Item $archivePath).Length -le 0) {
  throw "Backup archive is empty: $archivePath"
}

(Get-Date).ToString("o") | Set-Content -Path $stateFile -Encoding UTF8

$cutoff = (Get-Date).AddDays(-$RetentionDays)
Get-ChildItem -Path $backupDir -Filter "backup_*.zip" | Where-Object {
  $_.LastWriteTime -lt $cutoff
} | Remove-Item -Force -ErrorAction SilentlyContinue

Write-Host "Backup created: $archivePath"
