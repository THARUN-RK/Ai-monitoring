from __future__ import annotations
import re
from typing import Any

# -------------------------------------------------------------------------
# Step 3 - Strict Field Allowlist & Secret Redaction Engine
# -------------------------------------------------------------------------

# Strict approved top-level telemetry fields
APPROVED_FIELDS = {
    "event_id",
    "tenant_id",
    "collector_id",
    "timestamp",
    "observed_at",
    "metric_name",
    "metric_value",
    "severity",
    "health_status",
    "event_category",
    "service",
    "environment",
    "unit",
}

# Strict approved metrics
ALLOWED_METRICS = {
    "cpu_utilization",
    "memory_utilization",
    "disk_utilization",
    "network_bytes_per_second",
    "network_bytes_sent_rate",
    "network_bytes_recv_rate",
    "http_error_rate",
    "http_latency_p95_ms",
    "uptime_seconds",
    "collector_heartbeat",
    "service_availability",
}

# Sensitive regex patterns for secret detection
SECRET_PATTERNS = [
    (re.compile(r"(?i)(password|passwd|pwd)[\s=:\"']+(\S+)"), "password"),
    (re.compile(r"(?i)(bearer\s+[a-zA-Z0-9_\-\.]{15,})"), "bearer_token"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,}"), "api_key"),
    (re.compile(r"cic_[a-zA-Z0-9_\-]{20,}"), "collector_key"),
    (re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"), "email_identifier"),
]


def detect_secrets(text: str) -> list[str]:
    """Detects any credentials, API keys, or secrets inside a text string."""
    detected = []
    for pattern, secret_type in SECRET_PATTERNS:
        if pattern.search(text):
            detected.append(secret_type)
    return detected


def sanitize_event(
    raw_event: dict[str, Any]
) -> tuple[dict[str, Any] | None, list[str], list[str], list[str]]:
    """
    Enforces strict field allowlisting, secret detection, and field redaction.
    Returns:
        (sanitized_event, approved_fields, redacted_fields, rejected_fields)
    """
    approved_fields = []
    redacted_fields = []
    rejected_fields = []

    # 1. Inspect all fields present in raw event
    for key, value in raw_event.items():
        key_str = str(key)
        val_str = str(value)

        # Check for secrets inside key name or value
        secret_types = detect_secrets(f"{key_str}={val_str}")
        if secret_types:
            redacted_fields.append(f"{key_str} ({','.join(secret_types)})")
            continue

        if key_str in ("password", "token", "secret", "api_key", "raw_logs", "user_email"):
            redacted_fields.append(key_str)
            continue

        # Check against approved allowlist
        if key_str in APPROVED_FIELDS:
            approved_fields.append(key_str)
        else:
            rejected_fields.append(key_str)

    # 2. Metric validation
    metric_name = raw_event.get("metric_name")
    if not metric_name or metric_name not in ALLOWED_METRICS:
        return None, approved_fields, redacted_fields, rejected_fields

    try:
        metric_value = float(raw_event.get("metric_value", raw_event.get("value", 0.0)))
    except (ValueError, TypeError):
        return None, approved_fields, redacted_fields, rejected_fields

    if not (-1_000_000_000 <= metric_value <= 1_000_000_000):
        return None, approved_fields, redacted_fields, rejected_fields

    # 3. Construct clean outbound sanitized event
    sanitized: dict[str, Any] = {
        "event_id": str(raw_event.get("event_id", "")),
        "metric_name": metric_name,
        "metric_value": metric_value,
        "unit": str(raw_event.get("unit", "ratio"))[:24],
        "service": str(raw_event.get("service", "cicada-agent"))[:64],
        "environment": str(raw_event.get("environment", "production"))[:64],
        "severity": str(raw_event.get("severity", "info"))[:24],
        "health_status": str(raw_event.get("health_status", "healthy"))[:24],
        "event_category": str(raw_event.get("event_category", "system"))[:32],
    }

    if "timestamp" in raw_event:
        sanitized["timestamp"] = str(raw_event["timestamp"])
    elif "observed_at" in raw_event:
        sanitized["timestamp"] = str(raw_event["observed_at"])

    if "tenant_id" in raw_event:
        sanitized["tenant_id"] = str(raw_event["tenant_id"])[:64]
    if "collector_id" in raw_event:
        sanitized["collector_id"] = str(raw_event["collector_id"])[:64]

    return sanitized, approved_fields, redacted_fields, rejected_fields


def build_approved_metadata(raw_event: dict[str, Any]) -> dict[str, Any] | None:
    """
    Backward-compatible adapter for legacy batch endpoint.
    Builds nested resource/metric object compliant with schemas.Record.
    """
    sanitized, _, _, _ = sanitize_event(raw_event)
    if not sanitized:
        return None

    return {
        "observed_at": raw_event.get("observed_at", raw_event.get("timestamp")),
        "signal_type": "metric_summary",
        "resource": {
            "service": sanitized["service"],
            "environment": sanitized["environment"],
        },
        "metric": {
            "name": sanitized["metric_name"],
            "value": sanitized["metric_value"],
            "unit": sanitized["unit"],
        },
        "window_seconds": int(raw_event.get("window_seconds", 10)),
        "quality": {"sample_count": int(raw_event.get("sample_count", 1))},
    }
