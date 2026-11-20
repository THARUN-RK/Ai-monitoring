from __future__ import annotations

import os
import sys
import uuid
import time
import json
import psutil
import requests
from pathlib import Path
from datetime import datetime, timezone

# Ensure customer-agent root directory is on sys.path
_current_dir = Path(__file__).resolve().parent
_agent_root = _current_dir.parent
if str(_agent_root) not in sys.path:
    sys.path.insert(0, str(_agent_root))

from app.policy import sanitize_event, build_approved_metadata
from app.buffer import LocalBuffer
from app.egress_proof import EgressProofManager


API_URL = os.getenv("CICADA_API_URL", "https://ai-monitoring-5n2p.onrender.com").rstrip("/")
API_KEY = os.getenv("CICADA_AGENT_API_KEY", "change-this-demo-key")
COLLECTOR_ID = os.getenv("COLLECTOR_ID", "collector-tier1-demo")
TENANT_ID = os.getenv("TENANT_ID", "demo-tenant")
COLLECTION_INTERVAL = int(os.getenv("COLLECTION_INTERVAL", "10"))
INJECT_TEST_SECRET = os.getenv("INJECT_TEST_SECRET", "true").lower() in ("true", "1", "yes")

# Initialize storage and egress proof components
buffer = LocalBuffer("data/buffer")
egress_manager = EgressProofManager("data/egress_proof.jsonl")


def register_collector() -> bool:
    """Step 5 - Registers collector with the central platform."""
    url = f"{API_URL}/api/v1/collector/register"
    body = {
        "collector_id": COLLECTOR_ID,
        "name": f"Local-Collector-{COLLECTOR_ID[-6:]}",
        "environment": "production",
        "tenant_id": TENANT_ID,
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        res = requests.post(url, json=body, headers=headers, timeout=10)
        if res.status_code in (200, 201):
            print(f"[REGISTRATION] Collector {COLLECTOR_ID} registered successfully.")
            return True
        else:
            print(f"[REGISTRATION] Fallback: central platform returned {res.status_code}")
    except Exception as err:
        print(f"[REGISTRATION] Registration notice: {err} (will retry during ingestion)")
    return False


def collect_real_metrics() -> list[tuple[str, float, str]]:
    """Step 2 - Collects real system hardware and network metrics using psutil."""
    cpu = psutil.cpu_percent(interval=0.5) / 100.0
    memory = psutil.virtual_memory().percent / 100.0
    try:
        disk = psutil.disk_usage("C:\\" if os.name == "nt" else "/").percent / 100.0
    except Exception:
        disk = 0.42

    before = psutil.net_io_counters()
    time.sleep(0.5)
    after = psutil.net_io_counters()

    network_speed = float(
        (after.bytes_sent - before.bytes_sent) + (after.bytes_recv - before.bytes_recv)
    )

    return [
        ("cpu_utilization", cpu, "ratio"),
        ("memory_utilization", memory, "ratio"),
        ("disk_utilization", disk, "ratio"),
        ("network_bytes_per_second", network_speed, "bytes/s"),
        ("collector_heartbeat", 1.0, "status"),
        ("service_availability", 1.0, "status"),
    ]


def collect_checkout_metrics() -> list[tuple[str, float, str]]:
    """Synthetic customer application metrics for AIOps demonstration."""
    return [
        ("http_error_rate", 0.18, "ratio"),
        ("http_latency_p95_ms", 850.0, "ms"),
    ]


def flush_local_buffer() -> int:
    """Step 8 - Retries sending any locally buffered payloads when connection is restored."""
    pending = buffer.pending()
    if not pending:
        return 0

    print(f"[RETRY BUFFER] Found {len(pending)} pending offline payloads. Flushing...")
    flushed = 0
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    for path in pending:
        try:
            payload = buffer.read(path)
            res = requests.post(
                f"{API_URL}/api/v1/telemetry/ingest",
                json=payload,
                headers=headers,
                timeout=10,
            )
            if res.status_code in (200, 202):
                buffer.delete(path)
                egress_manager.update_delivery(payload.get("payload_id", ""), "delivered", res.json())
                flushed += 1
            else:
                break
        except Exception:
            break

    print(f"[RETRY BUFFER] Successfully flushed {flushed} payloads.")
    return flushed


def run_collection_cycle(cycle_num: int) -> dict[str, Any]:
    """
    Executes one complete telemetry cycle:
    Collection -> Filtering & Redaction -> Egress Proof -> API Ingestion / Buffer.
    """
    print(f"\n{'='*20} TELEMETRY CYCLE {cycle_num} {'='*20}")
    observed_at = datetime.now(timezone.utc).isoformat()

    # Step 2: Collect metrics
    laptop_metrics = collect_real_metrics()
    checkout_metrics = collect_checkout_metrics()

    raw_events: list[dict[str, Any]] = []

    # Build raw events for real hardware metrics
    for name, value, unit in laptop_metrics:
        raw_events.append({
            "event_id": str(uuid.uuid4()),
            "tenant_id": TENANT_ID,
            "collector_id": COLLECTOR_ID,
            "timestamp": observed_at,
            "metric_name": name,
            "metric_value": value,
            "unit": unit,
            "severity": "info",
            "health_status": "healthy",
            "event_category": "system",
            "service": "cicada-agent",
            "environment": "demo",
        })

    # Build raw events for checkout application
    for name, value, unit in [
        ("cpu_utilization", 0.45, "ratio"),
        ("memory_utilization", 0.55, "ratio"),
        *checkout_metrics,
    ]:
        raw_events.append({
            "event_id": str(uuid.uuid4()),
            "tenant_id": TENANT_ID,
            "collector_id": COLLECTOR_ID,
            "timestamp": observed_at,
            "metric_name": name,
            "metric_value": value,
            "unit": unit,
            "severity": "warning" if "error" in name or value > 500 else "info",
            "health_status": "degraded" if "error" in name or value > 500 else "healthy",
            "event_category": "application",
            "service": "checkout",
            "environment": "demo",
        })

    # Step 3 & Acceptance test: Inject simulated sensitive fields to prove redaction
    if INJECT_TEST_SECRET and cycle_num == 1:
        raw_events[0]["password"] = "super_secret_db_password_123"
        raw_events[0]["api_key"] = "sk-live-cicada-demo-secret-key-999"
        raw_events[0]["user_email"] = "admin@internal.customer.corp"
        raw_events[0]["unapproved_custom_field"] = "arbitrary_debug_data"
        print("[TEST MODE] Injected simulated test secrets into local raw event to prove redaction!")

    # Step 3: Privacy Filtering & Redaction
    sanitized_events: list[dict[str, Any]] = []
    all_approved_fields: list[str] = []
    all_redacted_fields: list[str] = []
    all_rejected_fields: list[str] = []

    for raw in raw_events:
        sanitized, approved, redacted, rejected = sanitize_event(raw)
        if sanitized:
            sanitized_events.append(sanitized)
        all_approved_fields.extend(approved)
        all_redacted_fields.extend(redacted)
        all_rejected_fields.extend(rejected)

    payload_id = str(uuid.uuid4())

    # Build outbound payload (approved metadata only!)
    outbound_payload = {
        "payload_id": payload_id,
        "collector_id": COLLECTOR_ID,
        "timestamp": observed_at,
        "records": sanitized_events,
        "approved_fields_count": len(all_approved_fields),
        "rejected_fields_count": len(all_rejected_fields) + len(all_redacted_fields),
        "redacted_fields": list(set(all_redacted_fields)),
        "sanitized_sample": json.dumps(sanitized_events[0]) if sanitized_events else "{}",
    }

    # Step 4: Record Egress Proof immediately before transmission
    egress_manager.record_proof(
        payload_id=payload_id,
        collector_id=COLLECTOR_ID,
        original_events=raw_events,
        filtered_events=sanitized_events,
        approved_fields=all_approved_fields,
        redacted_fields=all_redacted_fields,
        rejected_fields=all_rejected_fields,
        outbound_payload=outbound_payload,
        delivery_status="transmitting",
    )

    print(f"[EGRESS PROOF] Payload ID: {payload_id}")
    print(f"[EGRESS PROOF] Approved Fields Count: {len(all_approved_fields)}")
    print(f"[EGRESS PROOF] Redacted/Blocked Secrets: {list(set(all_redacted_fields))}")
    print(f"[EGRESS PROOF] Rejected Unknown Fields: {list(set(all_rejected_fields))}")

    # Step 5 & 8: Send to API with local buffer fallback
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    delivery_status = "failed"
    api_response = None

    try:
        # 1. First attempt modern Step 5 endpoint: /api/v1/telemetry/ingest
        response = requests.post(
            f"{API_URL}/api/v1/telemetry/ingest",
            json=outbound_payload,
            headers=headers,
            timeout=10,
        )

        if response.status_code in (200, 202):
            delivery_status = "delivered"
            api_response = response.json()
            print(f"[API RESPONSE] Ingested successfully via /api/v1/telemetry/ingest: {api_response}")
        else:
            # 2. Backward-compatible fallback: /api/v1/agent/batches
            print(f"[INGEST NOTICE] Ingest returned {response.status_code}, trying legacy batch endpoint...")
            legacy_batch = {
                "schema_version": "1.0",
                "batch_id": payload_id,
                "sent_at": observed_at,
                "policy_version": "demo-allowlist-v1",
                "records": [
                    {
                        "event_id": str(uuid.uuid4()),
                        **build_approved_metadata(r),
                    }
                    for r in raw_events
                    if build_approved_metadata(r) is not None
                ],
            }
            legacy_res = requests.post(
                f"{API_URL}/api/v1/agent/batches",
                json=legacy_batch,
                headers=headers,
                timeout=10,
            )
            if legacy_res.status_code in (200, 202):
                delivery_status = "delivered"
                api_response = legacy_res.json()
                print(f"[API RESPONSE] Ingested successfully via /api/v1/agent/batches: {api_response}")
            else:
                raise requests.RequestException(f"Both endpoints failed: {legacy_res.status_code}")

    except Exception as err:
        print(f"[NETWORK/API ERROR] {err}")
        print("[FAILURE HANDLING] Buffering payload to local disk queue...")
        buffer.put(outbound_payload)
        delivery_status = "buffered"
        api_response = {"error": str(err)}

    egress_manager.update_delivery(payload_id, delivery_status, api_response)
    print(f"[DELIVERY STATUS] {delivery_status.upper()}")
    print("[PRIVACY GUARANTEE] Raw logs and sensitive fields NEVER left local customer environment.")

    return {
        "payload_id": payload_id,
        "delivery_status": delivery_status,
        "events_sent": len(sanitized_events),
    }


def monitoring_loop():
    print("=" * 60)
    print("CICADA SECURE TIER-1 COLLECTOR & EGRESS PROOF ENGINE")
    print(f"Target Central SaaS API: {API_URL}")
    print(f"Collector ID: {COLLECTOR_ID}")
    print(f"Tenant ID: {TENANT_ID}")
    print(f"Collection Interval: {COLLECTION_INTERVAL}s")
    print("=" * 60)

    # Initial collector registration
    register_collector()

    cycle = 0
    while True:
        cycle += 1
        start_time = time.monotonic()

        # Flush any previously buffered payloads if network restored
        flush_local_buffer()

        # Run cycle
        run_collection_cycle(cycle)

        elapsed = time.monotonic() - start_time
        sleep_time = max(0.5, COLLECTION_INTERVAL - elapsed)
        time.sleep(sleep_time)


if __name__ == "__main__":
    try:
        monitoring_loop()
    except KeyboardInterrupt:
        print("\nCollector gracefully stopped.")
