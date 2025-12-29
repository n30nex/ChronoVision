Param(
  [switch]$Once
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
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

$deviceName = $envMap["CAPTURE_DEVICE_NAME"]
if (-not $deviceName) { $deviceName = "USB Camera" }

$intervalMin = [int]($envMap["CAPTURE_INTERVAL_MIN"])
if (-not $intervalMin) { $intervalMin = 10 }

$outputDir = $envMap["CAPTURE_OUTPUT_DIR"]
if (-not $outputDir) { $outputDir = ".\\data\\snapshots" }

if (-not [System.IO.Path]::IsPathRooted($outputDir)) {
  $outputDir = Join-Path $repoRoot $outputDir
}

$logDir = Join-Path $repoRoot "data\\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir "capture.log"

function Write-Log($message) {
  $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  "$timestamp $message" | Add-Content -Path $logPath
}

if (-not (Test-Path $ffmpegPath)) {
  Write-Log "FFmpeg not found at $ffmpegPath"
  throw "FFmpeg not found at $ffmpegPath"
}

Write-Log "Starting capture loop. Device=$deviceName Interval=${intervalMin}min"

function Capture-Once {
  $now = Get-Date
  $datePath = Join-Path $outputDir ($now.ToString("yyyy\\MM\\dd"))
  New-Item -ItemType Directory -Force -Path $datePath | Out-Null

  $fileName = $now.ToString("HHmmss") + ".jpg"
  $tempPath = Join-Path $datePath ($fileName + ".tmp")
  $finalPath = Join-Path $datePath $fileName

  $deviceArg = "video=`"$deviceName`""
  $args = @(
    "-f", "dshow",
    "-i", $deviceArg,
    "-frames:v", "1",
    "-q:v", "2",
    "-f", "image2",
    "-vcodec", "mjpeg",
    $tempPath
  )

  try {
    $ffmpegLog = Join-Path $logDir "ffmpeg_last.err"
    $proc = Start-Process -FilePath $ffmpegPath -ArgumentList $args -NoNewWindow -Wait -PassThru `
      -RedirectStandardError $ffmpegLog
    if ($proc.ExitCode -ne 0) {
      $details = Get-Content $ffmpegLog -Raw -ErrorAction SilentlyContinue
      Write-Log "FFmpeg exit code $($proc.ExitCode). $details"
    }
    if (Test-Path $tempPath) {
      Move-Item -Path $tempPath -Destination $finalPath -Force
      Write-Log "Captured $finalPath"
      return $true
    }
    Write-Log "Capture failed: temp file missing"
    return $false
  } catch {
    Write-Log "Capture error: $($_.Exception.Message)"
    if (Test-Path $tempPath) { Remove-Item $tempPath -Force }
    return $false
  }
}

if ($Once) {
  [void](Capture-Once)
  exit
}

while ($true) {
  [void](Capture-Once)
  Start-Sleep -Seconds ($intervalMin * 60)
}
