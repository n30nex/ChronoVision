import sys
import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, Optional

from loguru import logger


@dataclass
class ApiCallStats:
    success: int = 0
    failure: int = 0
    latency_total_ms: float = 0.0

    @property
    def avg_latency_ms(self) -> float:
        total = self.success + self.failure
        if total == 0:
            return 0.0
        return self.latency_total_ms / total


@dataclass
class Metrics:
    start_time: float = field(default_factory=time.time)
    snapshots_processed_total: int = 0
    last_snapshot_time: Optional[str] = None
    last_groq_success: Optional[str] = None
    last_groq_failure: Optional[str] = None
    last_gemini_success: Optional[str] = None
    last_gemini_failure: Optional[str] = None
    api_calls: Dict[str, ApiCallStats] = field(
        default_factory=lambda: {"groq": ApiCallStats(), "gemini": ApiCallStats()}
    )

    def record_snapshot(self, timestamp_iso: str) -> None:
        self.snapshots_processed_total += 1
        self.last_snapshot_time = timestamp_iso

    def record_api_call(self, provider: str, success: bool, latency_ms: float) -> None:
        stats = self.api_calls.setdefault(provider, ApiCallStats())
        if success:
            stats.success += 1
        else:
            stats.failure += 1
        stats.latency_total_ms += latency_ms

    def to_metrics_json(self, disk_used_mb: float, disk_free_mb: float) -> dict:
        return {
            "uptime_seconds": int(time.time() - self.start_time),
            "snapshots_processed_total": self.snapshots_processed_total,
            "api_calls": {
                provider: {
                    "success": stats.success,
                    "failure": stats.failure,
                    "avg_latency_ms": round(stats.avg_latency_ms, 2),
                }
                for provider, stats in self.api_calls.items()
            },
            "storage": {
                "disk_used_mb": round(disk_used_mb, 2),
                "disk_free_mb": round(disk_free_mb, 2),
            },
            "last_snapshot": self.last_snapshot_time,
        }


metrics = Metrics()


def configure_logging(log_path, log_level: str) -> None:
    logger.remove()
    logger.add(sys.stdout, level=log_level, enqueue=True)
    logger.add(
        log_path,
        level=log_level,
        rotation="5 MB",
        retention="7 days",
        enqueue=True,
    )


def health_status(
    last_snapshot_time: Optional[str],
    disk_free_mb: float,
    queue_depth: int,
    capture_interval_min: int,
) -> str:
    if disk_free_mb < 100:
        return "unhealthy"
    if last_snapshot_time is None:
        return "degraded"
    age_seconds = time.time() - _iso_to_epoch(last_snapshot_time)
    if age_seconds > capture_interval_min * 120:
        return "degraded"
    if queue_depth > 20:
        return "degraded"
    return "healthy"


def _iso_to_epoch(timestamp: str) -> float:
    try:
        parsed = timestamp.replace("Z", "+00:00")
        return datetime.fromisoformat(parsed).timestamp()
    except ValueError:
        return 0.0
