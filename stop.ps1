$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$runDir = Join-Path $repoRoot "data\\run"
$trayPidPath = Join-Path $runDir "tray.pid"
$stopSignalPath = Join-Path $runDir "tray_stop.signal"
$capturePidPath = Join-Path $runDir "capture.pid"

function Stop-Capture {
  if (Test-Path $capturePidPath) {
    $capturePid = Get-Content $capturePidPath | Select-Object -First 1
    $proc = Get-Process -Id $capturePid -ErrorAction SilentlyContinue
    if ($proc) {
      Stop-Process -Id $capturePid -Force
    }
    Remove-Item $capturePidPath -Force -ErrorAction SilentlyContinue
  }
}

$trayStopped = $false
if (Test-Path $trayPidPath) {
  $trayPid = Get-Content $trayPidPath | Select-Object -First 1
  $proc = Get-Process -Id $trayPid -ErrorAction SilentlyContinue
  if ($proc) {
    "stop" | Set-Content -Path $stopSignalPath -Encoding UTF8
    $attempts = 0
    while ($attempts -lt 20) {
      Start-Sleep -Seconds 1
      $proc = Get-Process -Id $trayPid -ErrorAction SilentlyContinue
      if (-not $proc) {
        $trayStopped = $true
        break
      }
      $attempts += 1
    }
    if (-not $trayStopped -and $proc) {
      Stop-Process -Id $trayPid -Force
    }
  }
}

Stop-Capture
Start-Process -FilePath "docker" -ArgumentList "compose", "down" -WorkingDirectory $repoRoot -WindowStyle Hidden -Wait

if (Test-Path $trayPidPath) { Remove-Item $trayPidPath -Force -ErrorAction SilentlyContinue }
if (Test-Path $stopSignalPath) { Remove-Item $stopSignalPath -Force -ErrorAction SilentlyContinue }

Write-Host "Stopped tray, capture, and docker containers."
