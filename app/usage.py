from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from . import storage


def record_usage(
    settings,
    provider: str,
    model: str,
    usage: dict[str, int],
    endpoint: str,
) -> None:
    if not usage:
        return
    input_tokens = int(usage.get("input_tokens", 0))
    output_tokens = int(usage.get("output_tokens", 0))
    total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens))
    cost_usd = _calculate_cost(settings, provider, input_tokens, output_tokens)
    record = {
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "provider": provider,
        "model": model,
        "endpoint": endpoint,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cost_usd": round(cost_usd, 6),
    }
    storage.append_record(settings.data_dir, "usage", record)


def summarize_usage(settings, days: int = 7) -> dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    records = storage.fetch_records_since(settings.data_dir, "usage", cutoff)

    totals = _empty_totals()
    by_provider: dict[str, dict[str, float]] = defaultdict(_empty_totals)
    by_day: dict[str, dict[str, float]] = defaultdict(_empty_totals)

    for record in records:
        timestamp = _parse_iso(record.get("timestamp"))
        if timestamp is None:
            continue
        provider = record.get("provider", "unknown")
        date_key = timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d")

        _accumulate(totals, record)
        _accumulate(by_provider[provider], record)
        _accumulate(by_day[date_key], record)

    day_list = [
        {"date": day, **_normalize(totals)}
        for day, totals in sorted(by_day.items())
    ]

    return {
        "window_days": days,
        "totals": _normalize(totals),
        "by_provider": {provider: _normalize(data) for provider, data in by_provider.items()},
        "by_day": day_list,
    }


def _calculate_cost(settings, provider: str, input_tokens: int, output_tokens: int) -> float:
    if provider == "groq":
        input_rate = settings.groq_cost_input_million
        output_rate = settings.groq_cost_output_million
    elif provider == "gemini":
        input_rate = settings.gemini_cost_input_million
        output_rate = settings.gemini_cost_output_million
    else:
        input_rate = 0.0
        output_rate = 0.0

    return (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate


def _empty_totals() -> dict[str, float]:
    return {
        "input_tokens": 0.0,
        "output_tokens": 0.0,
        "total_tokens": 0.0,
        "cost_usd": 0.0,
    }


def _accumulate(target: dict[str, float], record: dict[str, Any]) -> None:
    target["input_tokens"] += float(record.get("input_tokens", 0))
    target["output_tokens"] += float(record.get("output_tokens", 0))
    target["total_tokens"] += float(record.get("total_tokens", 0))
    target["cost_usd"] += float(record.get("cost_usd", 0))


def _normalize(data: dict[str, float]) -> dict[str, float]:
    return {
        "input_tokens": int(data["input_tokens"]),
        "output_tokens": int(data["output_tokens"]),
        "total_tokens": int(data["total_tokens"]),
        "cost_usd": round(data["cost_usd"], 6),
    }


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
