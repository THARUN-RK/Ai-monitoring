from __future__ import annotations
from typing import Any

ALLOWED_METRICS = {
    "cpu_utilization",
    "memory_utilization",
    "http_error_rate",
    "http_latency_p95_ms",
    "network_bytes_per_second",
}
ALLOWED_RESOURCE_KEYS = {"service", "environment"}

def build_approved_metadata(raw_event: dict[str, Any]) -> dict[str, Any] | None:
    """Build a fresh outbound object. Never serialize or forward raw_event."""
    metric_name = raw_event.get("metric_name")
    if metric_name not in ALLOWED_METRICS:
        return None

    raw_resource = raw_event.get("resource")
    if not isinstance(raw_resource, dict):
        return None

    resource = {}
    for key in ALLOWED_RESOURCE_KEYS:
        value = raw_resource.get(key)
        if isinstance(value, str) and 0 < len(value) <= 64:
            # Conservative label validation: bounded, non-PII-like identifiers only.
            if all(ch.isalnum() or ch in "_.-" for ch in value):
                resource[key] = value

    if set(resource) != ALLOWED_RESOURCE_KEYS:
        return None

    try:
        value = float(raw_event["value"])
        window = int(raw_event.get("window_seconds", 60))
        sample_count = int(raw_event.get("sample_count", 1))
    except (KeyError, TypeError, ValueError):
        return None

    if not (-1_000_000_000 <= value <= 1_000_000_000):
        return None
    if not (1 <= window <= 3600 and 1 <= sample_count <= 1_000_000):
        return None

    # Explicit allowlist projection. Raw messages, payloads, arbitrary
    # attributes, credentials, IPs and user identifiers are never copied.
    return {
        "observed_at": raw_event["observed_at"],
        "signal_type": "metric_summary",
        "resource": resource,
        "metric": {
            "name": metric_name,
            "value": value,
            "unit": str(raw_event.get("unit", "value"))[:24],
        },
        "window_seconds": window,
        "quality": {"sample_count": sample_count},
    }
