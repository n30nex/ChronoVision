Param(
  [string]$InstallRoot,
  [string]$FfmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
  [switch]$UpdateEnv
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

if (-not $InstallRoot) {
  $InstallRoot = Join-Path $repoRoot "tools\\ffmpeg"
}

try {
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
} catch {
}

$downloadPath = Join-Path $env:TEMP "ffmpeg_release_essentials.zip"
$extractRoot = Join-Path $env:TEMP ("ffmpeg_extract_" + [System.Guid]::NewGuid().ToString("N"))

Write-Host "Downloading FFmpeg from $FfmpegUrl"
Invoke-WebRequest -Uri $FfmpegUrl -OutFile $downloadPath

New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null
Expand-Archive -Path $downloadPath -DestinationPath $extractRoot -Force

$extractedDir = Get-ChildItem -Path $extractRoot -Directory | Select-Object -First 1
if (-not $extractedDir) {
  throw "FFmpeg archive did not contain an expected folder."
}

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
$currentDir = Join-Path $InstallRoot "current"
if (Test-Path $currentDir) {
  Remove-Item $currentDir -Recurse -Force
}
Move-Item -Path $extractedDir.FullName -Destination $currentDir

$ffmpegPath = Join-Path $currentDir "bin\\ffmpeg.exe"
if (-not (Test-Path $ffmpegPath)) {
  throw "FFmpeg not found at $ffmpegPath"
}

if ($UpdateEnv) {
  $envPath = Join-Path $repoRoot ".env"
  $line = "FFMPEG_PATH=$ffmpegPath"
  if (Test-Path $envPath) {
    $found = $false
    $updated = Get-Content $envPath | ForEach-Object {
      if ($_ -match "^\s*FFMPEG_PATH=") {
        $found = $true
        $line
      } else {
        $_
      }
    }
    if (-not $found) {
      $updated += $line
    }
    $updated | Set-Content -Path $envPath -Encoding UTF8
  } else {
    $line | Set-Content -Path $envPath -Encoding UTF8
  }
  Write-Host "Updated $envPath with FFMPEG_PATH."
} else {
  Write-Host "FFmpeg installed at $ffmpegPath"
  Write-Host "Set FFMPEG_PATH in .env if needed."
}

Remove-Item $downloadPath -Force -ErrorAction SilentlyContinue
Remove-Item $extractRoot -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "FFmpeg install complete."
