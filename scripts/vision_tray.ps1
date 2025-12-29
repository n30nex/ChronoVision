$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$runDir = Join-Path $repoRoot "data\\run"
$logDir = Join-Path $repoRoot "data\\logs"
$envPath = Join-Path $repoRoot ".env"
$statePath = Join-Path $runDir "tray_state.json"
$pidPath = Join-Path $runDir "capture.pid"
$trayPidPath = Join-Path $runDir "tray.pid"
$stopSignalPath = Join-Path $runDir "tray_stop.signal"
$healthUrl = "http://localhost:8080/api/health"

New-Item -ItemType Directory -Force -Path $runDir | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

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
$apiKey = $envMap["API_KEY"]

$mutexCreated = $false
$mutex = New-Object System.Threading.Mutex($true, "Global\SnapshotVisionTray", [ref]$mutexCreated)
if (-not $mutexCreated) {
  [System.Windows.Forms.MessageBox]::Show("Snapshot tray is already running.", "Snapshot Vision")
  exit
}

$PID | Set-Content -Path $trayPidPath -Encoding UTF8

function Save-State($state) {
  $state | ConvertTo-Json | Set-Content -Path $statePath -Encoding UTF8
}

function Write-Log($message) {
  $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  "$timestamp $message" | Add-Content -Path (Join-Path $logDir "tray.log")
}

function Start-Capture {
  if (Test-Path $pidPath) {
    $capturePid = Get-Content $pidPath | Select-Object -First 1
    $proc = Get-Process -Id $capturePid -ErrorAction SilentlyContinue
    if ($proc) {
      return
    }
  }
  $captureScript = Join-Path $repoRoot "scripts\\capture_webcam.ps1"
  $process = Start-Process -FilePath "powershell" -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $captureScript -WindowStyle Hidden -PassThru
  $process.Id | Set-Content -Path $pidPath -Encoding UTF8
  Write-Log "Started capture process PID=$($process.Id)"
}

function Stop-Capture {
  if (Test-Path $pidPath) {
    $capturePid = Get-Content $pidPath | Select-Object -First 1
    $proc = Get-Process -Id $capturePid -ErrorAction SilentlyContinue
    if ($proc) {
      Stop-Process -Id $capturePid -Force
      Write-Log "Stopped capture process PID=$capturePid"
    }
    Remove-Item $pidPath -Force -ErrorAction SilentlyContinue
  }
}

function Start-All {
  Write-Log "Starting services"
  Start-Process -FilePath "docker" -ArgumentList "compose", "up", "-d" -WorkingDirectory $repoRoot -WindowStyle Hidden -Wait
  Start-Capture
  Save-State @{ last_action = "started"; timestamp = (Get-Date).ToString("o") }
}

function Stop-All {
  Write-Log "Stopping services"
  Stop-Capture
  Start-Process -FilePath "docker" -ArgumentList "compose", "down" -WorkingDirectory $repoRoot -WindowStyle Hidden -Wait
  Save-State @{ last_action = "stopped"; timestamp = (Get-Date).ToString("o") }
}

function Open-UI {
  Start-Process "http://localhost:8080"
}

function Show-Logs {
  $logFile = Join-Path $logDir "app.log"
  if (Test-Path $logFile) {
    Start-Process notepad.exe $logFile
  }
}

function Update-Status {
  try {
    $headers = @{}
    if ($apiKey) {
      $headers["X-API-Key"] = $apiKey
    }
    if ($headers.Count -gt 0) {
      $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2 -Headers $headers
    } else {
      $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 2
    }
    $data = $response.Content | ConvertFrom-Json
    $status = $data.status
    $notifyIcon.Text = "Snapshot Vision: $status"
    $healthItem.Text = "Status: $status"
    $notifyIcon.BalloonTipTitle = "Snapshot Vision"
    $notifyIcon.BalloonTipText = "Status: $status"

    if ($status -eq "healthy") {
      $notifyIcon.Icon = [System.Drawing.SystemIcons]::Information
    } elseif ($status -eq "degraded") {
      $notifyIcon.Icon = [System.Drawing.SystemIcons]::Warning
    } else {
      $notifyIcon.Icon = [System.Drawing.SystemIcons]::Error
    }
  } catch {
    $notifyIcon.Text = "Snapshot Vision: unreachable"
    $healthItem.Text = "Status: unreachable"
  }

  if (Test-Path $pidPath) {
    $capturePid = Get-Content $pidPath | Select-Object -First 1
    $proc = Get-Process -Id $capturePid -ErrorAction SilentlyContinue
    if (-not $proc) {
      Write-Log "Capture process not running, restarting"
      Start-Capture
      $notifyIcon.ShowBalloonTip(2000)
    }
  }
}

$contextMenu = New-Object System.Windows.Forms.ContextMenuStrip
$startItem = New-Object System.Windows.Forms.ToolStripMenuItem "Start All"
$stopItem = New-Object System.Windows.Forms.ToolStripMenuItem "Stop All"
$openItem = New-Object System.Windows.Forms.ToolStripMenuItem "Open UI"
$healthItem = New-Object System.Windows.Forms.ToolStripMenuItem "Status: unknown"
$logItem = New-Object System.Windows.Forms.ToolStripMenuItem "View Logs"
$exitItem = New-Object System.Windows.Forms.ToolStripMenuItem "Exit"

$startItem.add_Click({ Start-All })
$stopItem.add_Click({ Stop-All })
$openItem.add_Click({ Open-UI })
$logItem.add_Click({ Show-Logs })
$exitItem.add_Click({ Stop-All; $notifyIcon.Visible = $false; [System.Windows.Forms.Application]::Exit() })

$contextMenu.Items.AddRange(@($startItem, $stopItem, $openItem, $healthItem, $logItem, $exitItem))

$notifyIcon = New-Object System.Windows.Forms.NotifyIcon
$notifyIcon.Icon = [System.Drawing.SystemIcons]::Information
$notifyIcon.Text = "Snapshot Vision"
$notifyIcon.ContextMenuStrip = $contextMenu
$notifyIcon.Visible = $true

$appContext = New-Object System.Windows.Forms.ApplicationContext
$appContext.Tag = $notifyIcon

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 30000
$timer.Add_Tick({ Update-Status })
$timer.Start()

[System.Windows.Forms.Application]::add_ApplicationExit({
  Stop-All
  if (Test-Path $trayPidPath) { Remove-Item $trayPidPath -Force -ErrorAction SilentlyContinue }
  if (Test-Path $stopSignalPath) { Remove-Item $stopSignalPath -Force -ErrorAction SilentlyContinue }
})

$powerSub = Register-ObjectEvent -InputObject ([Microsoft.Win32.SystemEvents]) -EventName PowerModeChanged -Action {
  if ($EventArgs.Mode -eq [Microsoft.Win32.PowerModes]::Suspend) {
    Stop-All
  } elseif ($EventArgs.Mode -eq [Microsoft.Win32.PowerModes]::Resume) {
    Start-All
  }
}

$stopTimer = New-Object System.Windows.Forms.Timer
$stopTimer.Interval = 2000
$stopTimer.Add_Tick({
  if (Test-Path $stopSignalPath) {
    Write-Log "Stop signal received"
    Stop-All
    if (Test-Path $stopSignalPath) { Remove-Item $stopSignalPath -Force -ErrorAction SilentlyContinue }
    $notifyIcon.Visible = $false
    [System.Windows.Forms.Application]::Exit()
  }
})
$stopTimer.Start()

Start-All
Update-Status
$notifyIcon.BalloonTipTitle = "Snapshot Vision"
$notifyIcon.BalloonTipText = "Tray started. Services are running."
$notifyIcon.ShowBalloonTip(2000)

[System.Windows.Forms.Application]::Run($appContext)
