$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$runDir = Join-Path $repoRoot "data\\run"
$logDir = Join-Path $repoRoot "data\\logs"
$trayPidPath = Join-Path $runDir "tray.pid"
$trayScript = Join-Path $repoRoot "scripts\\vision_tray.ps1"
$envPath = Join-Path $repoRoot ".env"

function Read-EnvFile($path) {
  $map = @{}
  if (-not (Test-Path $path)) {
    return $map
  }
  Get-Content $path | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    $parts = $line -split "=", 2
    if ($parts.Length -eq 2) {
      $key = $parts[0].Trim()
      $value = $parts[1].Trim()
      $map[$key] = $value
    }
  }
  return $map
}

$envMap = Read-EnvFile $envPath
$ffmpegPath = $envMap["FFMPEG_PATH"]
if (-not $ffmpegPath) { $ffmpegPath = "ffmpeg.exe" }
if (-not [System.IO.Path]::IsPathRooted($ffmpegPath)) {
  $ffmpegPath = Join-Path $repoRoot $ffmpegPath
}
$ffmpegOk = $false
if (Test-Path $ffmpegPath) {
  $ffmpegOk = $true
} else {
  $cmd = Get-Command "ffmpeg.exe" -ErrorAction SilentlyContinue
  if ($cmd) {
    $ffmpegOk = $true
  }
}
if (-not $ffmpegOk) {
  Write-Host "FFmpeg not found. Set FFMPEG_PATH in .env or run scripts\\install_ffmpeg.ps1 -UpdateEnv"
  exit 1
}

if (Test-Path $trayPidPath) {
  $trayPid = Get-Content $trayPidPath | Select-Object -First 1
  $proc = Get-Process -Id $trayPid -ErrorAction SilentlyContinue
  if ($proc) {
    Write-Host "Tray already running (PID $trayPid)."
    exit 0
  }
}

New-Item -ItemType Directory -Force -Path $runDir | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$outLog = Join-Path $logDir "tray_start.out"
$errLog = Join-Path $logDir "tray_start.err"

$proc = Start-Process -FilePath "powershell" -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-STA", "-File", $trayScript `
  -WindowStyle Hidden -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog

Start-Sleep -Seconds 2
if ($proc.HasExited) {
  Write-Host "Tray failed to start. Check $errLog"
  exit 1
}

Write-Host "Tray started."
