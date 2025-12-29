# Architecture

## Purpose and Scope
Snapshot Vision is a Windows-first camera snapshot pipeline that captures still images, enriches them with vision model output, and serves a local dashboard. This document describes the runtime flow, storage model, APIs, and operational details so future contributors can extend or maintain the system with minimal context switching.

Primary goals:
- Reliable periodic capture of snapshots (Windows host or container).
- LLM-based description and change detection (Groq + Gemini).
- Local-first storage with retention and cost tracking.
- Simple LAN access with optional shared-key auth.

Non-goals (current):
- Multi-camera management.
- Continuous video streaming.
- Public internet exposure or multi-tenant auth.

## System Diagram

Windows host capture (PowerShell + FFmpeg)
          |
          v
   data/snapshots/YYYY/MM/DD/HHMMSS.jpg
          |
          v
   Watchdog + Queue (FastAPI background worker)
          |
          v
  TaskRunner (validation, LLM calls, comparisons)
          |
          v
SQLite records.db + per-snapshot JSON artifacts
          |
          v
FastAPI endpoints + static web UI

## Runtime Modes
The system runs in one of three capture modes controlled by `CAMERA_SOURCE`:
- `windows-host`: snapshots are produced by `scripts/capture_webcam.ps1` on the host and written into `data/snapshots`. The container detects new files via a filesystem watcher and a periodic scan.
- `http`: the service captures snapshots from a static URL via HTTP at `CAPTURE_INTERVAL_MIN`.
- `rtsp`: the service captures from RTSP via FFmpeg at `CAPTURE_INTERVAL_MIN`.

## Startup Lifecycle
1) Load environment variables and validate configuration (`app/config.py`).
2) Ensure data directories exist (snapshots, logs, run state, etc).
3) Configure logging (`app/monitoring.py`).
4) Write `data/schema_version.txt` if missing.
5) Resolve `WEB_DIR` for static assets (defaults to `/web`, with a local fallback for tests).
6) Start background worker thread and file watcher.
7) Scan for new snapshots (Windows host mode).
8) Register APScheduler jobs and start the scheduler.

## Concurrency Model and Locks
- `snapshot_queue`: in-memory queue of snapshot paths to process.
- `enqueued_paths`: de-duplication set to prevent redundant enqueue.
- `processing.lock`: file lock to ensure only one snapshot is processed at a time.
- `list_snapshot_files` caches the snapshot list for 2 seconds to reduce disk scans.
- SQLite operates in WAL mode; record writes are per-call connections.

## Storage Model

### Directory Layout
Under `data/`:
- `snapshots/` (images): `YYYY/MM/DD/HHMMSS.jpg`
- `descriptions/` (per-snapshot JSON)
- `compare_10m/` (per-snapshot JSON)
- `compare_hourly/` (per-snapshot JSON)
- `daily_reports/` (per-day JSON)
- `logs/` (application, capture, tray logs)
- `run/` (locks, PID files, last processed)
- `backups/` (zip archives from `scripts/backup.ps1`)
- `records.db` (SQLite list storage)
- Legacy JSON lists: `descriptions.json`, `compare_10m.json`, etc (migrated to SQLite on first access)

### Snapshot Naming and Time Parsing
Snapshots are stored as:
```
YYYY/MM/DD/HHMMSS.jpg
```
The system parses timestamps from this path and converts them to UTC based on the configured `TIMEZONE`. Parsing is centralized in `app/tasks.py` and `app/retention.py`.

### SQLite Records
Database: `data/records.db`

Table schema:
- `records`
  - `id` INTEGER PRIMARY KEY AUTOINCREMENT
  - `list_name` TEXT
  - `timestamp` TEXT (ISO-8601, optional)
  - `timestamp_epoch` REAL (UTC epoch, optional)
  - `data` TEXT (JSON payload)

Indexes:
- `idx_records_list_id` on `(list_name, id)`
- `idx_records_list_ts` on `(list_name, timestamp_epoch)`

List names:
- `descriptions`, `compare_10m`, `compare_hourly`, `compare_custom`, `daily_reports`, `usage`

Migration behavior:
- On first access to a list, if the DB is empty for that list and a legacy JSON list file exists, the JSON list is imported.
- Migration is non-destructive; legacy JSON files are not deleted.
- If any record exists for a list, migration is skipped.

### Per-Snapshot JSON Artifacts
These are stored for audit/debugging and are pruned during retention:
- `data/descriptions/...` (description record)
- `data/compare_10m/...` (10-minute comparison record)
- `data/compare_hourly/...` (hourly comparison record)

### Schema Version
`data/schema_version.txt` is written once on startup to mark the data schema version.

## Backend Architecture (FastAPI)
Entry point: `app/main.py`

### Core Modules
- `app/main.py`: API routes, worker thread, scheduling, file watcher, auth middleware.
- `app/tasks.py`: snapshot processing, LLM calls, comparisons, reports.
- `app/storage.py`: atomic file IO, snapshot listing, SQLite record store.
- `app/retention.py`: disk retention and record pruning.
- `app/monitoring.py`: metrics and health checks.
- `app/rate_limiter.py`: rate limiting + circuit breaker.
- `app/usage.py`: usage aggregation and cost tracking.
- `app/image_validator.py`: size/dimension checks, dark frame detection, diff.
- `app/prompts.py`: LLM prompt strings and versioning.

### HTTP API Endpoints
All `/api/*` and `/data/*` routes require `API_KEY` if configured.

- `GET /api/health`
  - Response: `{status, last_snapshot_time, last_api_success, last_api_failure, disk_free_mb, queue_depth}`
  - Status code: 200 for healthy/degraded, 503 for unhealthy

- `GET /api/config`
  - Response: UI refresh interval, timezone, ask settings, preview cooldown

- `GET /api/metrics`
  - Response: uptime, snapshots processed, API call stats, storage usage

- `GET /api/usage/summary?days=7`
  - Response: usage totals by day and provider

- `GET /api/snapshots/latest`
  - Response: `{snapshot, timestamp}` with snapshot path relative to `/data`

- `GET /api/preview`
  - Response: image stream or 404 if unavailable

- `GET /api/descriptions?limit=N&offset=K`
  - Response: description list, newest items first when limit is set

- `GET /api/compare/10m`
- `GET /api/compare/hourly`
  - Response: comparison lists

- `POST /api/compare/custom`
  - Body: `{snapshot_a, snapshot_b}`
  - Response: comparison record

- `POST /api/ask`
  - Body: `{query, lookback_hours?, max_items?}`
  - Response: `{answer, window, timestamp}`

- `POST /api/summary/range`
  - Body: `{start, end, max_items?}`
  - Response: `{answer, window, timestamp}`

- `GET /api/story/daily`
  - Response: `{bullets, window, timestamp}`

- `GET /api/highlights/daily`
  - Response: `{items, window, timestamp}`

- `GET /api/reports/daily`
  - Response: daily report list

- `GET /data/snapshots/...`
  - Serves snapshot files (if API key is satisfied)

### Auth Model
If `API_KEY` is set:
- Requests must include `X-API-Key` header or `api_key` query parameter.
- The UI stores the key in `localStorage` and attaches it automatically.

### Request/Response Shapes (Common Records)
Description record:
```
{
  "timestamp": "2025-12-29T00:26:56Z",
  "snapshot": "snapshots/2025/12/29/002656.jpg",
  "text": "...",
  "tags": {"people": [], "vehicles": [], "objects": []},
  "provider": "groq",
  "model": "...",
  "prompt_version": "1.0.0",
  "latency_ms": 123.45
}
```

Compare record:
```
{
  "timestamp": "2025-12-29T00:26:56Z",
  "snapshot_a": "snapshots/...",
  "snapshot_b": "snapshots/...",
  "text": "...",
  "provider": "gemini",
  "model": "...",
  "prompt_version": "1.0.0",
  "latency_ms": 123.45
}
```

Daily report:
```
{
  "timestamp": "2025-12-29T00:05:00Z",
  "date": "2025-12-29",
  "summary": "...",
  "highlights": ["...", "...", "..."],
  "tags": {"people": [["alice", 3]], "vehicles": [], "objects": []},
  "provider": "gemini",
  "model": "...",
  "prompt_version": "1.0.0"
}
```

Usage record:
```
{
  "timestamp": "2025-12-29T00:26:56Z",
  "provider": "groq",
  "model": "...",
  "endpoint": "description",
  "input_tokens": 123,
  "output_tokens": 45,
  "total_tokens": 168,
  "cost_usd": 0.000123
}
```

### Snapshot Processing Pipeline (Detail)
1) Wait for new snapshot path in queue.
2) Ensure file is stable (size check across attempts).
3) Validate image (format, size, dimensions).
4) Optional dark frame check (mean luminance).
5) Optional motion detection (pixel difference threshold).
6) Groq description call, then tag extraction call.
7) Write description record to SQLite and per-snapshot JSON.
8) Run compare (10-minute) and append result to SQLite and per-snapshot JSON.
9) Write last processed state to `data/run/last_processed.json`.

### Comparisons and Reports
- 10-minute compare runs on schedule; summarizes the last 10 snapshots (~10 minutes).
- Hourly compare runs on schedule; summarizes the last 60 snapshots (~60 minutes).
- Daily report aggregates hourly comparisons and tags for the previous local day, runs at 00:05.
- Custom compare compares any two snapshot files selected by the UI.

### Ask the Feed
- Builds context from recent description records.
- Truncates each entry for length control.
- Gemini is prompted to answer only using the provided context.
- Range summaries combine descriptions and comparisons within a selected time window.
- Range summaries ask Gemini for a detailed what/who/where/when narrative and consistent person labels.

### Rate Limiting and Retry Strategy
- Each provider has its own `RateLimiter`.
- Requests are spaced by RPM and backed off with exponential delay.
- Circuit breaker opens after `API_CIRCUIT_BREAKER_THRESHOLD` failures.

### Health and Metrics
- Health status uses:
  - Disk free < 100 MB => unhealthy
  - No snapshot yet => degraded
  - Last snapshot too old => degraded
  - Queue depth > 20 => degraded
- Metrics include:
  - Uptime
  - Total snapshots processed
  - API success/failure counts and average latency
  - Disk used/free MB

## Frontend Architecture
Location: `web/index.html`, `web/styles.css`, `web/app.js`

UI behavior:
- Loads config (`/api/config`) to drive refresh interval and ask settings.
- Polls data on a timer (`UI_REFRESH_INTERVAL_SEC`).
- Uses `/api/descriptions` to power latest summary, history, trends, and timelapse.
- Uses `/api/compare/*` and `/api/reports/daily` for timelines and summaries.
- Uses `/api/story/daily` and `/api/highlights/daily` for narrative insights.
- Uses `/api/usage/summary` for cost reporting.
- Uses `localStorage` for API key persistence and attaches it to requests.
- Range summary includes preset windows (1h/4h/12h/24h) that set start/end.

Key UI features:
- Latest snapshot + tags
- Live preview capture
- Tag trends (hourly/daily)
- Range summary by time window
- Daily story arc (hourly comparison timeline)
- Day highlight reel (top snapshots)
- Timelapse scrubbing
- 10-minute and hourly change lists
- Daily summary + highlights
- Custom compare UI
- Cost and usage summary
- Searchable snapshot history

## Deployment

### Docker
- Container listens on port 8080.
- Mounts:
  - `./data:/data`
  - `./web:/web` (static UI)
- Healthcheck uses `/api/health` and includes the API key if set.

### Docker Development Override
`docker-compose.dev.yml`:
- Enables `--reload` with uvicorn.
- Mounts `./app:/app/app:ro` and `./web:/web:ro`.

### Windows Scripts
- `start.ps1`: validates FFmpeg and launches the tray app.
- `stop.ps1`: stops tray, capture, and Docker containers.
- `scripts/vision_tray.ps1`: tray UI for start/stop, open UI, view logs; monitors health.
- `scripts/capture_webcam.ps1`: uses FFmpeg + DirectShow to write snapshots.
- `scripts/install_ffmpeg.ps1`: downloads and configures FFmpeg.
- `scripts/backup.ps1`: zips `data/` with optional incremental mode.
- `scripts/validate_data.ps1`: validates JSON file integrity.

## Configuration Reference
All values are read from `.env` (see `.env.example`). Defaults shown where applicable.

### Required Keys
- `GROQ_API_KEY`: required for image descriptions and tagging.
- `GOOGLE_API_KEY`: required for comparisons, ask, and daily reports.

### Optional Auth
- `API_KEY`: shared secret required for `/api/*` and `/data/*` access.

### Model Settings
- `GROQ_MODEL` (default: `meta-llama/llama-4-scout-17b-16e-instruct`)
- `GOOGLE_MODEL` (default: `gemini-2.0-flash`)

### Time and Scheduling
- `TIMEZONE` (default: `America/New_York`)
- `CAPTURE_INTERVAL_MIN` (default: `10`)

### Storage and Retention
- `DATA_DIR` (default: `/data`)
- `RETENTION_DAYS` (default: `14`)
- `RETENTION_MIN_SNAPSHOTS` (default: `10`)

### Camera Settings
- `CAMERA_SOURCE` (`windows-host`, `http`, `rtsp`)
- `CAMERA_HTTP_URL`
- `CAMERA_RTSP_URL`
- `CAPTURE_DEVICE_NAME` (default: `USB Camera`)
- `FFMPEG_PATH` (optional absolute path)
- `CAPTURE_OUTPUT_DIR` (used by PowerShell capture script)

### Snapshot Settings
- `SNAPSHOT_WIDTH` (currently unused in backend)
- `SNAPSHOT_QUALITY` (default: `85`)
- `MAX_FILE_SIZE_MB` (default: `10`)
- `IMAGE_MIN_WIDTH` (default: `320`)
- `IMAGE_MIN_HEIGHT` (default: `240`)
- `IMAGE_MAX_WIDTH` (default: `4096`)
- `IMAGE_MAX_HEIGHT` (default: `4096`)
- `MOTION_DETECTION_ENABLED` (default: `false`)
- `MOTION_DETECTION_THRESHOLD` (default: `5` percent)
- `DARK_FRAME_CHECK` (default: `false`)
- `TAGGING_ENABLED` (default: `true`)

### Rate Limiting and Retry
- `GROQ_RATE_LIMIT_RPM` (default: `30`)
- `GEMINI_RATE_LIMIT_RPM` (default: `15`)
- `API_RETRY_MAX_ATTEMPTS` (default: `3`)
- `API_RETRY_BASE_DELAY` (default: `2` seconds)
- `API_CIRCUIT_BREAKER_THRESHOLD` (default: `5` failures)

### UI and Ask
- `UI_REFRESH_INTERVAL_SEC` (default: `30`)
- `PREVIEW_COOLDOWN_SEC` (default: `5`)
- `ASK_ENABLED` (default: `true`)
- `ASK_LOOKBACK_HOURS` (default: `24`)
- `ASK_MAX_ITEMS` (default: `40`)

### Logging and Cost Tracking
- `LOG_LEVEL` (default: `INFO`)
- `GROQ_COST_PER_MILLION_INPUT`, `GROQ_COST_PER_MILLION_OUTPUT`
- `GEMINI_COST_PER_MILLION_INPUT`, `GEMINI_COST_PER_MILLION_OUTPUT`

### Additional Runtime Overrides
- `WEB_DIR` (optional): override static web directory (useful for tests)

## Operational Behavior

### Logging
- Loguru writes to `data/logs/app.log` with rotation and retention.

### Health Checks
- `/api/health` is used by Docker healthcheck and the tray app.
- Health status depends on disk free, last snapshot time, and queue depth.

### Retention
- Retention runs daily at 01:00.
- Removes old snapshots and their JSON artifacts.
- Prunes old SQLite records based on timestamp.

### Backups
- `scripts/backup.ps1` can run full or incremental backups of `data/`.
- `RetentionDays` controls backup cleanup.

## Testing and Development
Local testing:
1) `python -m pip install -e .`
2) `pytest`

Test coverage includes:
- Config loading and validation
- Rate limiter behavior
- Storage (atomic writes + SQLite records)
- Retention cleanup
- Auth enforcement

## Extension Points
- Add new LLM providers by extending `TaskRunner` and `prompts.py`.
- Add new data lists by registering a list name in `app/storage.py` and wiring endpoints.
- Introduce multi-camera support by adding camera identifiers to snapshot paths and records.
- Replace SQLite with a more scalable DB if retention size grows significantly.

## Known Limitations
- Single camera only.
- No streaming or video clips.
- No multi-user auth; only shared API key.
- Backend uses a single worker thread for snapshot processing.
- Legacy JSON lists are retained for migration but not updated.
