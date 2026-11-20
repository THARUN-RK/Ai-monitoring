from datetime import datetime, timezone
from fastapi import HTTPException
from .schemas import TelemetryBatchIn

# Strict schema + metric allowlist: only these normalized numeric fields may leave the customer site.
ALLOWED_METRICS = {
    "cpu_percent", "memory_percent", "disk_percent",
    "network_bytes_sent_rate", "network_bytes_recv_rate",
    "uptime_seconds", "app_response_ms", "app_available",
}

def approve_batch(batch: TelemetryBatchIn) -> list[dict]:
    approved = []
    for item in batch.records:
        if item.metric_name not in ALLOWED_METRICS:
            raise HTTPException(422, "Telemetry policy rejected an unsupported metric")
        approved.append({
            "server_id": item.server_id,
            "display_name": item.display_name,
            "environment": item.environment,
            "metric_name": item.metric_name,
            "value": item.value,
            "unit": item.unit,
            "observed_at": item.observed_at or datetime.now(timezone.utc),
        })
    return approved
