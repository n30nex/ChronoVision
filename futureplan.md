# Future Plan: Gemini-Powered Features

## Goals
- Add Gemini-backed reasoning on top of existing snapshots, tags, and comparisons.
- Keep storage append-only, JSON-first, and backward-compatible.
- Minimize token usage by gating Gemini calls with lightweight local checks.

## Phase 0: Shared Foundations
1. Schema + storage
   - Add new JSON stores:
     - `data/scene_metadata/{YYYY}/{MM}/{DD}/{HHMMSS}.json` + `data/scene_metadata.json`
     - `data/weekly_reports/{YYYY}-W{WW}.json` + `data/weekly_reports.json`
     - `data/anomalies/{YYYY}/{MM}/{DD}/{HHMMSS}.json` + `data/anomalies.json`
     - `data/ask_logs.json` (optional audit trail)
   - Keep existing `descriptions.json` and `compare_*` list files intact.
2. Config toggles (env + settings)
   - `SCENE_METADATA_ENABLED`, `ASK_ENABLED`, `ANOMALY_ENABLED`, `TAG_NORMALIZE_ENABLED`
   - Thresholds: `ANOMALY_MOTION_THRESHOLD`, `ANOMALY_BRIGHTNESS_DELTA`, `ASK_LOOKBACK_HOURS`, `ASK_MAX_ITEMS`
3. Prompts + parsing
   - Add Gemini prompt helpers in `app/prompts.py` for:
     - scene metadata JSON
     - categorized compare JSON
     - weekly rollup JSON
     - tag normalization JSON
     - ask-the-feed answer JSON (optional citations)
4. API surface
   - `POST /api/ask`
   - `GET /api/scene/metadata` (filters: day, limit)
   - `GET /api/reports/weekly`
   - `GET /api/anomalies`

## Feature 1: Ask the Feed (Gemini Text)
1. Endpoint
   - `POST /api/ask` with `{ query, lookback_hours?, max_items? }`.
   - Build context from `descriptions.json` (latest N) + tag summaries.
2. Gemini call
   - Use text-only payload (no images) to reduce tokens.
   - Return `{ answer, sources[]?, window }`.
3. Storage
   - Append to `data/ask_logs.json` with query + answer + counts.
4. UI
   - Add a small “Ask the Feed” card with textarea + response.
5. Tests
   - Validate request/response schema and empty-data behavior.

## Feature 2: Structured Scene Metadata (Gemini JSON)
1. Pipeline hook
   - After Groq description, call Gemini to return JSON:
     - `lighting`, `weather`, `activity`, `occupancy_count`, `confidence`.
2. Storage
   - Write per-snapshot JSON + append to `scene_metadata.json`.
3. UI
   - Display metadata chips under the latest snapshot and timelapse frames.
4. Tests
   - JSON parsing + fallback when Gemini returns invalid JSON.

## Feature 3: Categorized Change Explanations
1. Prompt update
   - Replace compare prompt to return JSON:
     - `summary`, `motion`, `lighting_change`, `objects_added`, `objects_removed`.
2. Storage
   - Keep `text` for backward compatibility; add `categories` block to compare records.
3. UI
   - Show summary + category chips in 10m/hourly lists and compare result.
4. Tests
   - Ensure old compare entries still render.

## Feature 4: Weekly Rollups
1. Scheduler
   - Add weekly job (e.g., Sunday 00:10 local) aggregating last 7 days.
2. Gemini call
   - Use hourly compare text + tag summaries.
   - Return JSON: `summary`, `trends`, `notable_changes`.
3. Storage + API
   - Write weekly report files + `weekly_reports.json`, expose `/api/reports/weekly`.
4. UI
   - Add a “Weekly Brief” card with trends list.

## Feature 5: Smart Tag Normalization
1. Taxonomy file
   - Add `data/tag_taxonomy.json` with canonical labels + synonyms.
2. Normalizer
   - Apply local mapping first; use Gemini for unknown tags.
   - Cache Gemini normalization results to avoid repeat calls.
3. Storage + UI
   - Store `tags_normalized` on descriptions and use them for filters/chips.
4. Tests
   - Ensure no duplicates and stable casing.

## Feature 6: Anomaly Detection (Local Gate + Gemini)
1. Local baseline
   - Compute brightness + motion deltas per time-of-day bucket.
   - Store rolling baseline in `data/baseline_stats.json`.
2. Trigger logic
   - If local metrics exceed thresholds, call Gemini with image for a concise anomaly summary.
3. Storage + API
   - Write anomaly JSON records + expose `/api/anomalies`.
4. UI
   - Add an “Anomalies” list with timestamp + summary.
5. Tests
   - Unit tests for threshold logic and baseline updates.

## Docs + Validation
- Update `README.md` with new endpoints, env vars, and data files.
- Add smoke tests for new endpoints (same style as existing health/config checks).
