# Snapshot Vision System (Windows + Docker) v1.0

## Prerequisites
- Docker Desktop for Windows (version X.X+)
- PowerShell 5.1 or higher
- FFmpeg (run `scripts\install_ffmpeg.ps1` or install manually and set `FFMPEG_PATH`)
- Groq API key (signup link)
- Google API key (signup link)

## Quick Start
1. Copy `.env.example` to `.env` and fill in your API keys.
2. Optional: run `scripts\install_ffmpeg.ps1 -UpdateEnv` to download FFmpeg and set `FFMPEG_PATH`.
3. For Windows production with `CAMERA_SOURCE=windows-host`, run `start.ps1` (starts tray, capture, and Docker).
4. For container-only runs, use `docker compose up -d --build`.
5. Open `http://localhost:8080`.
6. Stop everything with `stop.ps1` when needed.
7. If `API_KEY` is set, the UI will prompt for it on first load (stored in browser localStorage).
8. Use Range Summary presets (1h/4h/12h/24h) to quickly summarize recent activity.

## Configuration Reference
All settings live in `.env`. See `.env.example` for defaults.

Key additions:
- `TAGGING_ENABLED`: enable tag extraction for people/vehicles/objects.
- `MOTION_DETECTION_ENABLED`: skip AI calls when consecutive snapshots are similar.
- `MOTION_DETECTION_THRESHOLD`: percent difference to treat a frame as changed.
- `ASK_ENABLED`: enable the Ask the Feed endpoint.
- `ASK_LOOKBACK_HOURS`: lookback window for Ask the Feed.
- `ASK_MAX_ITEMS`: max snapshots used to answer a question.
- `PREVIEW_COOLDOWN_SEC`: minimum seconds between live preview captures.
- `GROQ_COST_PER_MILLION_INPUT/OUTPUT`, `GEMINI_COST_PER_MILLION_INPUT/OUTPUT`: cost tracking rates.
- `API_KEY`: optional shared secret required for `/api/*` and `/data/*` access (send as `X-API-Key` header or `api_key` query param).

## Architecture Overview
- Windows host capture script writes snapshots to `data/snapshots/`.
- Container processes snapshots and serves the API + UI.
- Snapshot metadata is stored in `data/records.db` (SQLite) and migrated automatically from legacy JSON lists on first read/write.

## API Endpoints
- `GET /api/health`: health status and last API calls.
- `GET /api/config`: UI refresh settings.
- `GET /api/metrics`: metrics payload.
- `GET /api/snapshots/latest`: latest snapshot path + timestamp.
- `GET /api/preview`: capture or return a single preview frame.
- `GET /api/descriptions`: snapshot descriptions with tags.
- `GET /api/compare/10m`: 10-minute comparisons.
- `GET /api/compare/hourly`: hourly comparisons.
- `POST /api/compare/custom`: compare two snapshots (body: `snapshot_a`, `snapshot_b`).
- `POST /api/ask`: ask a question about recent snapshots (body: `query`, optional `lookback_hours`, `max_items`).
- `POST /api/summary/range`: summarize a time range (body: `start`, `end`, optional `max_items`).
- `GET /api/story/daily`: timeline bullets from hourly comparisons (query: `hours`, `max_items`).
- `GET /api/highlights/daily`: top 3 snapshots by activity (query: `hours`, `max_items`).
- `GET /api/reports/daily`: daily summaries with highlights and tags.
- `GET /api/usage/summary`: token/cost totals for last N days.

## Troubleshooting
- Camera not detected: check DirectShow device name.
- API quota exceeded: check rate limits.
- Snapshots not processing: review logs at `data/logs/`.
- Tray icon not responding: kill PowerShell processes.
- Disk space issues: adjust `RETENTION_DAYS`.

## Development
- Use `docker compose -f docker-compose.yml -f docker-compose.dev.yml up`.
- For local tests, run `python -m pip install -e .` once to make `app` importable, then `pytest`.

## Backup and Recovery
- Use `scripts/backup.ps1` and keep archives in `data/backups/`.

## FAQ
- How do I change the capture interval? Update `CAPTURE_INTERVAL_MIN` in `.env`.
- Can I use multiple cameras? Not in the initial release.
- How do I export my data? Use the backup script.
- What happens if Docker restarts? The scheduler resumes and processes new snapshots.
