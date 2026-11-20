from __future__ import annotations

import os
import uuid
import time
import psutil
import requests

from datetime import datetime, timezone
from app.policy import build_approved_metadata


API_URL = os.getenv(
    "CICADA_API_URL",
    "https://ai-monitoring-5n2p.onrender.com"
)

API_KEY = os.getenv(
    "CICADA_AGENT_API_KEY",
    "change-this-demo-key"
)

COLLECTION_INTERVAL = 10


def collect_real_metrics():

    cpu = psutil.cpu_percent(interval=1) / 100
    memory = psutil.virtual_memory().percent / 100
    try:
        disk = psutil.disk_usage("C:\\" if os.name == "nt" else "/").percent / 100
    except Exception:
        disk = 0.50

    before = psutil.net_io_counters()
    time.sleep(1)
    after = psutil.net_io_counters()

    network_speed = (
        (after.bytes_sent - before.bytes_sent)
        + (after.bytes_recv - before.bytes_recv)
    )

    return [
        ("cpu_utilization", cpu, "ratio"),
        ("memory_utilization", memory, "ratio"),
        ("disk_utilization", disk, "ratio"),
        ("network_bytes_per_second", float(network_speed), "bytes/s"),
    ]


def collect_checkout_metrics():

    # Synthetic application telemetry for demonstration.
    return [
        ("http_error_rate", 0.18, "ratio"),
        ("http_latency_p95_ms", 850.0, "ms"),
    ]


def build_records(metrics, service, observed_at):

    records = []

    for name, value, unit in metrics:

        event = {
            "observed_at": observed_at,
            "metric_name": name,
            "value": value,
            "unit": unit,
            "window_seconds": COLLECTION_INTERVAL,
            "sample_count": 1,
            "resource": {
                "service": service,
                "environment": "demo",
            },
        }

        approved = build_approved_metadata(event)

        if approved:
            records.append({
                "event_id": str(uuid.uuid4()),
                **approved,
            })

    return records


def send_telemetry(records):

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
        headers={
            "Authorization": f"Bearer {API_KEY}"
        },
        timeout=15,
    )

    response.raise_for_status()

    return response.json()


def monitoring_loop():

    print("=" * 55)
    print("CICADA CONTINUOUS MONITORING STARTED")
    print("Target API:", API_URL)
    print("Collection interval:", COLLECTION_INTERVAL, "seconds")
    print("Press CTRL + C to stop")
    print("=" * 55)

    cycle = 0

    while True:

        start_time = time.monotonic()
        cycle += 1

        print(f"\nMONITORING CYCLE: {cycle}")

        try:

            laptop_metrics = collect_real_metrics()
            checkout_metrics = collect_checkout_metrics()

            # Shared timestamp for each collection cycle.
            observed_at = datetime.now(timezone.utc).isoformat()

            # Real laptop metrics remain separate.
            laptop_records = build_records(
                laptop_metrics,
                "cicada-agent",
                observed_at,
            )

            # All four ML features belong to the same demo service.
            checkout_records = build_records(
                [
                    ("cpu_utilization", 0.45, "ratio"),
                    ("memory_utilization", 0.55, "ratio"),
                    *checkout_metrics,
                ],
                "checkout",
                observed_at,
            )

            records = laptop_records + checkout_records

            print("\nREAL LAPTOP METRICS")

            for name, value, unit in laptop_metrics:
                print(f"{name}: {value:.4f} {unit}")

            print("\nSYNTHETIC CHECKOUT METRICS")

            for name, value, unit in checkout_metrics:
                print(f"{name}: {value:.4f} {unit}")

            result = send_telemetry(records)

            print("\nTELEMETRY UPLOAD")
            print("Status:", result["status"])
            print("Accepted records:", result["accepted_records"])

        except requests.RequestException as error:

            print("\nAPI CONNECTION ERROR:", error)

        except Exception as error:

            print("\nMONITORING ERROR:", error)

        elapsed = time.monotonic() - start_time
        remaining = max(0, COLLECTION_INTERVAL - elapsed)

        print(f"\nNext collection in {remaining:.1f} seconds")

        time.sleep(remaining)


if __name__ == "__main__":

    try:
        monitoring_loop()

    except KeyboardInterrupt:
        print("\nCICADA MONITORING STOPPED")
