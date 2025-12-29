import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pytz
from dotenv import load_dotenv

ALLOWED_CAMERA_SOURCES = {"windows-host", "http", "rtsp"}
SCHEMA_VERSION = "1.0.0"


def _parse_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_int(value: Optional[str], default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass
class Settings:
    groq_api_key: str
    google_api_key: str
    groq_model: str
    google_model: str
    timezone: str
    tz: pytz.BaseTzInfo
    capture_interval_min: int
    data_dir: Path
    retention_days: int
    retention_min_snapshots: int
    camera_source: str
    camera_http_url: str
    camera_rtsp_url: str
    snapshot_width: Optional[int]
    snapshot_quality: int
    capture_device_name: str
    ffmpeg_path: str
    capture_output_dir: str
    max_file_size_mb: int
    image_min_width: int
    image_min_height: int
    image_max_width: int
    image_max_height: int
    motion_detection_enabled: bool
    motion_detection_threshold: int
    dark_frame_check: bool
    tagging_enabled: bool
    ask_enabled: bool
    ask_lookback_hours: int
    ask_max_items: int
    preview_cooldown_sec: int
    ui_refresh_interval_sec: int
    log_level: str
    groq_rate_limit_rpm: int
    gemini_rate_limit_rpm: int
    api_retry_max_attempts: int
    api_retry_base_delay: int
    api_circuit_breaker_threshold: int
    groq_cost_input_million: float
    groq_cost_output_million: float
    gemini_cost_input_million: float
    gemini_cost_output_million: float

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def descriptions_dir(self) -> Path:
        return self.data_dir / "descriptions"

    @property
    def compare_10m_dir(self) -> Path:
        return self.data_dir / "compare_10m"

    @property
    def compare_hourly_dir(self) -> Path:
        return self.data_dir / "compare_hourly"

    @property
    def daily_reports_dir(self) -> Path:
        return self.data_dir / "daily_reports"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def run_dir(self) -> Path:
        return self.data_dir / "run"


def load_settings() -> Settings:
    load_dotenv(override=False)

    groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
    google_api_key = os.getenv("GOOGLE_API_KEY", "").strip()

    timezone = os.getenv("TIMEZONE", "America/New_York")
    tz = pytz.timezone(timezone)

    settings = Settings(
        groq_api_key=groq_api_key,
        google_api_key=google_api_key,
        groq_model=os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
        google_model=os.getenv("GOOGLE_MODEL", "gemini-2.0-flash"),
        timezone=timezone,
        tz=tz,
        capture_interval_min=_parse_int(os.getenv("CAPTURE_INTERVAL_MIN"), 10),
        data_dir=Path(os.getenv("DATA_DIR", "/data")),
        retention_days=_parse_int(os.getenv("RETENTION_DAYS"), 14),
        retention_min_snapshots=_parse_int(os.getenv("RETENTION_MIN_SNAPSHOTS"), 10),
        camera_source=os.getenv("CAMERA_SOURCE", "windows-host"),
        camera_http_url=os.getenv("CAMERA_HTTP_URL", "").strip(),
        camera_rtsp_url=os.getenv("CAMERA_RTSP_URL", "").strip(),
        snapshot_width=_parse_int(os.getenv("SNAPSHOT_WIDTH"), 0) or None,
        snapshot_quality=_parse_int(os.getenv("SNAPSHOT_QUALITY"), 85),
        capture_device_name=os.getenv("CAPTURE_DEVICE_NAME", "USB Camera"),
        ffmpeg_path=os.getenv("FFMPEG_PATH", ""),
        capture_output_dir=os.getenv("CAPTURE_OUTPUT_DIR", "./data/snapshots"),
        max_file_size_mb=_parse_int(os.getenv("MAX_FILE_SIZE_MB"), 10),
        image_min_width=_parse_int(os.getenv("IMAGE_MIN_WIDTH"), 320),
        image_min_height=_parse_int(os.getenv("IMAGE_MIN_HEIGHT"), 240),
        image_max_width=_parse_int(os.getenv("IMAGE_MAX_WIDTH"), 4096),
        image_max_height=_parse_int(os.getenv("IMAGE_MAX_HEIGHT"), 4096),
        motion_detection_enabled=_parse_bool(os.getenv("MOTION_DETECTION_ENABLED"), False),
        motion_detection_threshold=_parse_int(os.getenv("MOTION_DETECTION_THRESHOLD"), 5),
        dark_frame_check=_parse_bool(os.getenv("DARK_FRAME_CHECK"), False),
        tagging_enabled=_parse_bool(os.getenv("TAGGING_ENABLED"), True),
        ask_enabled=_parse_bool(os.getenv("ASK_ENABLED"), True),
        ask_lookback_hours=_parse_int(os.getenv("ASK_LOOKBACK_HOURS"), 24),
        ask_max_items=_parse_int(os.getenv("ASK_MAX_ITEMS"), 40),
        preview_cooldown_sec=_parse_int(os.getenv("PREVIEW_COOLDOWN_SEC"), 5),
        ui_refresh_interval_sec=_parse_int(os.getenv("UI_REFRESH_INTERVAL_SEC"), 30),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        groq_rate_limit_rpm=_parse_int(os.getenv("GROQ_RATE_LIMIT_RPM"), 30),
        gemini_rate_limit_rpm=_parse_int(os.getenv("GEMINI_RATE_LIMIT_RPM"), 15),
        api_retry_max_attempts=_parse_int(os.getenv("API_RETRY_MAX_ATTEMPTS"), 3),
        api_retry_base_delay=_parse_int(os.getenv("API_RETRY_BASE_DELAY"), 2),
        api_circuit_breaker_threshold=_parse_int(os.getenv("API_CIRCUIT_BREAKER_THRESHOLD"), 5),
        groq_cost_input_million=float(os.getenv("GROQ_COST_PER_MILLION_INPUT", "0") or 0),
        groq_cost_output_million=float(os.getenv("GROQ_COST_PER_MILLION_OUTPUT", "0") or 0),
        gemini_cost_input_million=float(os.getenv("GEMINI_COST_PER_MILLION_INPUT", "0") or 0),
        gemini_cost_output_million=float(os.getenv("GEMINI_COST_PER_MILLION_OUTPUT", "0") or 0),
    )

    _validate_settings(settings)
    _ensure_dirs(settings)
    return settings


def _validate_settings(settings: Settings) -> None:
    errors = []
    if not settings.groq_api_key:
        errors.append("GROQ_API_KEY is required")
    if not settings.google_api_key:
        errors.append("GOOGLE_API_KEY is required")
    if settings.camera_source not in ALLOWED_CAMERA_SOURCES:
        errors.append("CAMERA_SOURCE must be windows-host, http, or rtsp")
    if settings.camera_source == "http" and not settings.camera_http_url:
        errors.append("CAMERA_HTTP_URL is required for CAMERA_SOURCE=http")
    if settings.camera_source == "rtsp" and not settings.camera_rtsp_url:
        errors.append("CAMERA_RTSP_URL is required for CAMERA_SOURCE=rtsp")
    if settings.capture_interval_min <= 0:
        errors.append("CAPTURE_INTERVAL_MIN must be > 0")
    if settings.retention_days <= 0:
        errors.append("RETENTION_DAYS must be > 0")
    if settings.retention_min_snapshots < 0:
        errors.append("RETENTION_MIN_SNAPSHOTS must be >= 0")
    if settings.snapshot_quality < 1 or settings.snapshot_quality > 100:
        errors.append("SNAPSHOT_QUALITY must be 1-100")
    if settings.motion_detection_threshold < 0 or settings.motion_detection_threshold > 100:
        errors.append("MOTION_DETECTION_THRESHOLD must be 0-100")
    if settings.ask_lookback_hours <= 0:
        errors.append("ASK_LOOKBACK_HOURS must be > 0")
    if settings.ask_max_items <= 0:
        errors.append("ASK_MAX_ITEMS must be > 0")
    if settings.preview_cooldown_sec < 0:
        errors.append("PREVIEW_COOLDOWN_SEC must be >= 0")
    if settings.groq_cost_input_million < 0 or settings.groq_cost_output_million < 0:
        errors.append("GROQ cost values must be >= 0")
    if settings.gemini_cost_input_million < 0 or settings.gemini_cost_output_million < 0:
        errors.append("GEMINI cost values must be >= 0")
    if errors:
        raise ValueError("; ".join(errors))


def _ensure_dirs(settings: Settings) -> None:
    for directory in [
        settings.data_dir,
        settings.snapshots_dir,
        settings.descriptions_dir,
        settings.compare_10m_dir,
        settings.compare_hourly_dir,
        settings.daily_reports_dir,
        settings.logs_dir,
        settings.backups_dir,
        settings.run_dir,
    ]:
        directory.mkdir(parents=True, exist_ok=True)
