# Project Plan

This plan defines the full build and deployment path for the Windows-first, Docker Compose based snapshot + LLM vision system. It is written to be actionable step-by-step.

## 0) Goals and Constraints
- Windows host (Docker Desktop) with a USB webcam attached.
- Use Groq API (OpenAI-compatible) for per-snapshot descriptions.
- Use Google Gemini (generativelanguage endpoint) for image comparisons.
- Timezone: EST (America/New_York).
- Retention: 14 days for snapshots and JSON outputs.
- Open UI (no auth).
- Single docker compose file for production; allow a dev override file and a host capture script to bridge Windows USB camera access.
- One configuration file for all credentials and settings.
- No Home Assistant dependency.

## 1) Research/Inputs to Reference
- `ha-llmvision` for provider request format and endpoint URLs (Groq + Gemini).
- `HA-LLM-ChronoVision` for scheduling patterns, hourly compare logic, and retention cleanup approach.

## 2) Repository Layout
Create a clean repo with a small number of files and a clear separation of concerns.

```
/ (repo root)
  docker-compose.yml
  docker-compose.dev.yml        # Development overrides
  Dockerfile
  requirements.txt
  requirements-dev.txt          # Dev dependencies
  .env.example
  .gitignore
  README.md
  plan.md
  /app
    main.py               # FastAPI app + scheduler
    config.py             # config loading + validation
    storage.py            # JSON + file IO helpers
    tasks.py              # capture + LLM tasks
    prompts.py            # prompt templates + constraints
    retention.py          # cleanup utilities
    rate_limiter.py       # API rate limiting + backoff
    image_validator.py    # image validation helpers
    monitoring.py         # logging + metrics + health
  /web
    index.html
    app.js
    styles.css
  /scripts
    capture_webcam.ps1
    vision_tray.ps1
    backup.ps1            # backup/restore helpers
    validate_data.ps1     # data validation utility
  /tests
    test_config.py
    test_storage.py
    test_tasks.py
  /data                  (bind mounted, gitignored)
    snapshots/
    descriptions/
    compare_10m/
    compare_hourly/
    daily_reports/
    logs/
    backups/
    run/
```

## 3) Configuration (Single File)
Use `.env` for all configuration. Include `.env.example` for easy setup.

Required:
- `GROQ_API_KEY`
- `GOOGLE_API_KEY`

Recommended:
- `GROQ_MODEL` (default: `meta-llama/llama-4-scout-17b-16e-instruct`)
- `GOOGLE_MODEL` (default: `gemini-2.0-flash`)
- `TIMEZONE` (default: `America/New_York`)
- `CAPTURE_INTERVAL_MIN` (default: `10`)
- `DATA_DIR` (default: `/data`)
- `RETENTION_DAYS` (default: `14`)
- `RETENTION_MIN_SNAPSHOTS` (default: `10`)
- `CAMERA_SOURCE` (options: `windows-host`, `http`, `rtsp`)
- `CAMERA_HTTP_URL` (if `CAMERA_SOURCE=http`)
- `CAMERA_RTSP_URL` (if `CAMERA_SOURCE=rtsp`)
- `SNAPSHOT_WIDTH` (optional resize)
- `SNAPSHOT_QUALITY` (jpeg quality, default 85)
- `CAPTURE_DEVICE_NAME` (Windows DirectShow device name, e.g. `USB Camera`)
- `FFMPEG_PATH` (full path to `ffmpeg.exe` for host capture)
- `CAPTURE_OUTPUT_DIR` (host path for snapshots, default `./data/snapshots`)
- `MAX_FILE_SIZE_MB` (default: `10`)
- `IMAGE_MIN_WIDTH` (default: `320`)
- `IMAGE_MIN_HEIGHT` (default: `240`)
- `IMAGE_MAX_WIDTH` (default: `4096`)
- `IMAGE_MAX_HEIGHT` (default: `4096`)
- `MOTION_DETECTION_ENABLED` (default: `false`)
- `MOTION_DETECTION_THRESHOLD` (0-100, default: `5`)
- `UI_REFRESH_INTERVAL_SEC` (default: `30`)
- `LOG_LEVEL` (default: `INFO`)

API rate limiting:
- `GROQ_RATE_LIMIT_RPM` (default: `30`)
- `GEMINI_RATE_LIMIT_RPM` (default: `15`)
- `API_RETRY_MAX_ATTEMPTS` (default: `3`)
- `API_RETRY_BASE_DELAY` (seconds, default: `2`)
- `API_CIRCUIT_BREAKER_THRESHOLD` (consecutive failures, default: `5`)

Notes:
- `.env` must be gitignored.
- `data/` must be gitignored.
- Use `pytz` for robust timezone handling.
- Store timestamps in UTC; convert to configured timezone only for display/filenames.
- Handle DST transitions in scheduler logic.

Validation (config.py):
- API keys are present and non-empty.
- Camera source matches available options.
- Paths exist or can be created.
- Numeric values are in valid ranges.
- Model names are supported by respective APIs.

## 3b) Dependencies
`requirements.txt` baseline:
- fastapi
- uvicorn
- apscheduler
- loguru
- watchdog
- pytz
- python-dotenv
- httpx
- Pillow

`requirements-dev.txt`:
- pytest
- pytest-asyncio
- pytest-cov

## 3c) Configuration Profiles (Optional)
Development (`.env.dev`):
- `LOG_LEVEL=DEBUG`
- `UI_REFRESH_INTERVAL_SEC=5`
- `CAPTURE_INTERVAL_MIN=1`
- `RETENTION_DAYS=1`

Production (`.env`):
- `LOG_LEVEL=INFO`
- Use defaults from Section 3.

Low-bandwidth (`.env.low`):
- `SNAPSHOT_WIDTH=640`
- `SNAPSHOT_QUALITY=70`
- `GROQ_RATE_LIMIT_RPM=10`

## 4) Windows Webcam Capture Strategy
Docker Desktop Windows containers cannot reliably access USB webcams directly.
Plan:
- Provide a host-side capture script (PowerShell) that grabs a snapshot every 10 minutes and writes to a host folder mapped into the container.
- This is a Windows-only script; for production, it should start by default when `CAMERA_SOURCE=windows-host`.
- Container watches the snapshots directory and processes the newest file.
- Optional: allow RTSP or HTTP snapshot source if the user prefers to run a local relay (MediaMTX or IP camera).

Deliverables:
- `scripts/capture_webcam.ps1`:
  - Uses `ffmpeg.exe` to capture from a DirectShow device (e.g., `"USB Camera"`).
  - Writes `data/snapshots/YYYY/MM/DD/HHmmss.jpg`.
  - Write to a temp file and atomically rename to the final filename to avoid partial reads.
  - Runs in an infinite loop with a 10-minute interval.
  - Stores logs to `data/logs/` (optional).

## 4b) Windows Tray Controller
Provide a Windows tray app script to start/stop all services (Docker + host capture) and show status.

Deliverables:
- `scripts/vision_tray.ps1`:
  - Creates a tray icon using `System.Windows.Forms.NotifyIcon`.
  - Menu items: `Start All`, `Stop All`, `Open UI`, `Show Status`, `Exit`.
  - `Start All` runs `docker compose up -d` and launches `scripts/capture_webcam.ps1` in a background PowerShell process.
  - For production, launch the tray controller on login and auto-run `Start All` (capture starts by default).
  - `Stop All` stops the capture process and runs `docker compose down`.
  - Status polling: check `http://localhost:8080/api/health` and show a tooltip/state color (green/yellow/red).
  - Store the capture PID in `data/run/capture.pid` to manage clean stop.
  - Read `.env` to resolve `FFMPEG_PATH`, `CAPTURE_DEVICE_NAME`, and `CAPTURE_OUTPUT_DIR`.
  - Use a mutex/lock to prevent multiple tray instances.
  - Graceful shutdown on sleep/logout.
  - Store state to remember settings across restarts.
  - Add a log viewer menu item.
  - Show notifications on capture failures.
  - Auto-restart the capture process if it crashes.

## 5) Backend Service
Single Python service with FastAPI + APScheduler.

Core jobs:
1) Snapshot ingestion
   - If `CAMERA_SOURCE=windows-host`: use file system events (watchdog) to detect new files.
   - On Windows bind mounts, use PollingObserver or a periodic scan fallback to avoid missed events.
   - Add a processing lock file to prevent duplicate processing.
   - Store last processed timestamp to handle restarts gracefully.
   - If `CAMERA_SOURCE=http|rtsp`: capture internally on a 10-minute schedule.
   - Ignore temp extensions and verify file size stability before processing.
   - Validate image format/integrity before processing.
   - Handle corrupted/partial files from interrupted captures.
   - Enforce max file size (`MAX_FILE_SIZE_MB`) to prevent disk fill.
   - Validate min/max dimensions (`IMAGE_MIN_*`, `IMAGE_MAX_*`) and decode without errors.
   - Optional: minimum brightness/contrast check to detect black frames.
   - Optional: strip EXIF data for privacy.
   - Optional: motion detection to skip identical frames (`MOTION_DETECTION_*`).
2) Groq description
   - After each snapshot, call Groq OpenAI-compatible vision endpoint.
   - Save JSON to `data/descriptions/YYYY/MM/DD/HHmmss.json` and append to `data/descriptions.json`.
3) 10-minute compare (Gemini)
   - On each new snapshot, compare the last two images.
   - Prompt constraint: 1-3 sentences, <=200 chars.
   - Save JSON to `data/compare_10m/...` and `data/compare_10m.json`.
4) Hourly compare (Gemini)
   - Every hour, compare latest snapshot with closest snapshot ~1 hour earlier.
   - Save JSON to `data/compare_hourly/...` and `data/compare_hourly.json`.
5) Daily report (Gemini)
   - Every 24 hours, summarize the last 24 hourly comparisons.
   - Save JSON to `data/daily_reports/...` and `data/daily_reports.json`.
6) Retention cleanup
   - Daily cleanup for snapshots and JSON lists older than 14 days.
   - Dry-run mode to preview deletions.
   - Keep at least N snapshots regardless of age.
   - Archive option instead of delete.
   - Confirmation prompt for manual cleanup.
   - Log all deletions with timestamps.

Error handling:
- Log and continue if APIs fail.
- For Gemini output, enforce <=200 chars using:
  - Pre-prompt with the character limit in the system message.
  - Post-process with extractive summarization if still too long.
  - Fallback: truncate at the last complete sentence within limit.
  - Log when truncation occurs.
- Use atomic JSON writes (temp file + rename), file locking, and JSON schema validation.
- Add backup/restore for corrupted files.
- Store a `SCHEMA_VERSION` constant and write to `data/schema_version.txt` on first run; check and log mismatches on startup.

## 5b) API Management
- Implement exponential backoff for API failures.
- Add configurable rate limits per provider.
- Track API usage metrics (tokens, costs).
- Optional: add circuit breaker for repeated failures.
- Log API response times for monitoring.

## 5c) Prompt Templates (prompts.py)
Templates should include:
1. Groq description prompt
   - System: "You are a concise vision assistant..."
   - User: "Describe this snapshot in 2-3 sentences..."
2. Gemini 10-minute compare prompt
   - System: "Compare images. Max 200 chars. 1-3 sentences only."
   - User: "What changed between these two snapshots?"
3. Gemini hourly compare prompt
   - Similar structure, emphasize hour-scale changes.
4. Gemini daily report prompt
   - Summarize 24 hourly comparisons.
   - Focus on trends and notable events.

All prompts should:
- Include character/sentence limits in the system message.
- Be parameterized (timestamp, context injection).
- Track versions for A/B testing.

## 5d) Schema Migration Strategy
- Current schema version: `1.0.0`.
- On startup, compare stored version with app version.
- If mismatch:
  - Log warning with migration instructions.
  - Optionally run auto-migration scripts.
  - Provide rollback option.
- Migration scripts stored in `/migrations/` (future).

## 6) API Endpoints (FastAPI)
- `GET /api/health`
- `GET /api/config` (UI-safe config, e.g., refresh interval and timezone)
- `GET /api/snapshots/latest` (path + timestamp)
- `GET /api/descriptions` (list)
- `GET /api/compare/10m` (list)
- `GET /api/compare/hourly` (list)
- `GET /api/reports/daily` (list)
- `GET /api/metrics` (optional Prometheus format or JSON stats)
- Static file serving for `/web/*` and `/data/snapshots/*`

Health response details:
- Status: `healthy`, `degraded`, `unhealthy`
- Last snapshot time
- Last API success/failure times
- Disk space available
- Processing queue depth (pending snapshots count or task queue length)
- Return 200 for healthy/degraded, 503 for unhealthy

Metrics response format (JSON):
```
{
  "uptime_seconds": 3600,
  "snapshots_processed_total": 144,
  "api_calls": {
    "groq": {"success": 144, "failure": 2, "avg_latency_ms": 250},
    "gemini": {"success": 288, "failure": 1, "avg_latency_ms": 180}
  },
  "storage": {
    "disk_used_mb": 1024,
    "disk_free_mb": 50000
  },
  "last_snapshot": "2024-01-15T14:30:00Z"
}
```

## 7) Web UI
- Single page with a bold, non-boilerplate design.
- Custom fonts (Google Fonts) with defined CSS variables.
- Sections:
  - Latest snapshot + description.
  - Recent 10-minute diffs (timeline).
  - Hourly diffs (timeline).
  - Daily report (latest).
- Responsive layout for desktop and mobile.
- Minimal JS fetch from API endpoints.
- Auto-refresh with configurable interval (`UI_REFRESH_INTERVAL_SEC`).
- Use `/api/config` to read UI refresh interval and timezone for display.
- Loading states and error boundaries.
- Cache API responses with timestamps.
- Show last update time + manual refresh button.
- Handle network errors gracefully.

## 8) Docker Compose
- Single `docker-compose.yml`.
- One service: `vision-app`.
- Bind mount `./data` to `/data`.
- Expose port `8080` (FastAPI + static UI).
- `.env` is loaded in compose.
- Add healthcheck for `/api/health`.
- Prefer a Python-based healthcheck (uses httpx) or install curl in the image.

Healthcheck example:
```
services:
  vision-app:
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import httpx; r=httpx.get('http://localhost:8080/api/health', timeout=2); raise SystemExit(0 if r.status_code < 500 else 1)\""]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

## 9) Secrets and Git Hygiene
- `.env` excluded by `.gitignore`.
- `data/` excluded by `.gitignore`.
- Do not store API keys in repo.
- Add `README.md` notes about secrets and local files.

## 9b) Logging and Monitoring
- Structured logging with rotation (loguru).
- Separate log levels for components.
- Export a metrics endpoint (Prometheus optional).
- Store processing times and success/failure rates.
- Alert on consecutive failures (email/webhook optional).

## 9c) Security
- Add CORS configuration for API.
- Implement rate limiting on endpoints.
- Sanitize file paths to prevent directory traversal.
- Add Content-Security-Policy headers.
- Optional: simple API key for external access.
- Validate and sanitize all user inputs.

## 10) Backup Strategy
- Document backup/restore steps for `data/`.
- Add export/import for configuration.
- Store schema version for migration compatibility.
- Add data validation/repair utility script.
- `scripts/backup.ps1`:
  - Create timestamped archive of `data/`.
  - Optional: exclude `logs/`.
  - Support full and incremental backups.
  - Verify archive integrity after creation.
  - Clean up old backups based on retention policy.

## 11) Development Setup
- Add `docker-compose.dev.yml` override.
- Include hot-reload for development.
- Add debug logging mode.
- Document how to run tests locally.
- Provide a sample `.env` with dummy keys for testing.
- `docker-compose.dev.yml` overrides:
  - Mount `./app:/app:ro` for hot-reload.
  - `LOG_LEVEL=DEBUG`, `HOT_RELOAD=true`.
  - Expose `5678` for debugpy.
  - Set `uvicorn --reload` (or equivalent) for dev command override.

## 12) Step-by-step Build Checklist
1. Initialize repo files and directories per layout.
2. Add `.env.example` and `.gitignore`.
3. Implement `config.py` with strict validation, defaults, and timezone handling.
4. Implement `monitoring.py` (needed early for debugging).
5. Implement `storage.py` for atomic JSON writes, schema validation, and safe file IO.
6. Implement `image_validator.py`.
7. Implement `rate_limiter.py`.
8. Implement `tasks.py`:
   - Snapshot capture (internal and ingest modes).
   - Groq vision description.
   - Gemini compare prompts.
9. Implement `retention.py` with cleanup logic.
10. Implement scheduler in `main.py` using APScheduler.
11. Add FastAPI endpoints and static serving.
12. Build the UI in `/web` with custom CSS and auto-refresh.
13. Wire Dockerfile (Python slim) + compose (with healthcheck).
14. Add `scripts/capture_webcam.ps1` and test capture flow.
15. Add `scripts/vision_tray.ps1` with full lifecycle management.
16. Add `scripts/backup.ps1` and `scripts/validate_data.ps1`.
17. Write unit tests for critical functions:
   - Config validation
   - Storage atomic writes
   - Rate limiter logic
   - Image validation
18. Write integration tests:
   - Full snapshot processing pipeline
   - API endpoint responses
   - Retention cleanup
19. Write README with complete setup/run/troubleshooting steps for Windows.

## 13) README Sections (Template)
- Prerequisites
  - Docker Desktop for Windows (version X.X+)
  - PowerShell 5.1 or higher
  - FFmpeg (download link)
  - Groq API key (signup link)
  - Google API key (signup link)
- Quick Start (5-minute setup)
- Configuration Reference (all .env variables explained)
- Architecture Overview (diagram or description)
- Troubleshooting
  - Camera not detected: check DirectShow device name.
  - API quota exceeded: check rate limits.
  - Snapshots not processing: review logs at `data/logs/`.
  - Tray icon not responding: kill PowerShell processes.
  - Disk space issues: adjust `RETENTION_DAYS`.
- Development (how to contribute/modify)
- Backup and Recovery
- FAQ
  - How do I change the capture interval?
  - Can I use multiple cameras?
  - How do I export my data?
  - What happens if Docker restarts?

## 14) Run Instructions (Draft)
1. Copy `.env.example` to `.env` and fill keys.
2. Run `docker compose up -d`.
3. For production on Windows with `CAMERA_SOURCE=windows-host`, start `scripts/vision_tray.ps1` to auto-start capture by default.
4. If not using the tray controller, run `scripts/capture_webcam.ps1` directly.
5. Open `http://localhost:8080`.

## 15) Acceptance Criteria
- Snapshots created every 10 minutes and stored on disk.
- Groq descriptions saved in JSON and visible in UI.
- Gemini 10-minute comparisons saved and visible.
- Hourly comparisons saved and visible.
- Daily report saved and visible.
- All configs in `.env` only; repo is safe to publish.
- Single compose file used to run services.
