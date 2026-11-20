from __future__ import annotations
import os
import uuid
from datetime import datetime, timezone
import requests
from app.policy import build_approved_metadata

API_URL = os.getenv("CICADA_API_URL", "http://localhost:8000")
API_KEY = os.getenv("CICADA_AGENT_API_KEY", "change-this-demo-key")

def synthetic_events():
    now = datetime.now(timezone.utc).isoformat()
    return [
        {
            "observed_at": now, "metric_name": "cpu_utilization",
            "value": 0.92, "unit": "ratio", "window_seconds": 60,
            "sample_count": 60,
            "resource": {"service": "checkout", "environment": "demo"},
            "raw_message": "local-only diagnostic: password=not-for-export",
            "attributes": {"customer_email": "person@example.com"},
        },
        {
            "observed_at": now, "metric_name": "http_error_rate",
            "value": 0.18, "unit": "ratio", "window_seconds": 60,
            "sample_count": 240,
            "resource": {"service": "checkout", "environment": "demo"},
        },
    ]

def main():
    records = []
    for event in synthetic_events():
        approved = build_approved_metadata(event)
        if approved:
            records.append({"event_id": str(uuid.uuid4()), **approved})

    if not records:
        print("No records passed local policy.")
        return

    if not API_URL.startswith("https://") and "localhost" not in API_URL and "127.0.0.1" not in API_URL:
        raise RuntimeError("Refusing cleartext transmission to a non-local host")

    batch = {
        "schema_version": "1.0",
        "batch_id": str(uuid.uuid4()),
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "policy_version": "demo-allowlist-v1",
        "records": records,
    }
    response = requests.post(
        f"{API_URL.rstrip('/')}/api/v1/agent/batches",
        json=batch,
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=10,
    )
    response.raise_for_status()
    print("Central acknowledgement:", response.json())

if __name__ == "__main__":
    main()
