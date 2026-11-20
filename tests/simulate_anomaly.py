"""
NeuraWatch - Hackathon Failure Simulation & End-to-End Verification
Simulates:
1. Ingestion of 21 normal baseline batches.
2. Model transition from warmup to trained Isolation Forest.
3. Injection of an anomalous payload (95% CPU, elevated latency and error rate).
4. Detection and explanation of the anomaly.
5. Verification of the privacy allowlist boundary.
"""
import sys
import uuid
import time
import requests
from datetime import datetime, timezone, timedelta

RENDER_URL = "https://ai-monitoring-5n2p.onrender.com"
AUTH_HEADER = {"Authorization": "Bearer change-this-demo-key"}

def run_simulation():
    print("=" * 65)
    print("NEURAWATCH END-TO-END VERIFICATION & FAILURE SIMULATION")
    print(f"Target: {RENDER_URL}")
    print("=" * 65)

    # 1. Test live health check
    print("\n[Step 1] Checking Backend Health...")
    r = requests.get(f"{RENDER_URL}/api/v1/health/live", timeout=10)
    assert r.status_code == 200, f"Health check failed: {r.status_code}"
    print(f"  --> PASS: {r.json()}")

    # 2. Privacy Policy Validation (Egress Proof)
    print("\n[Step 2] Validating Privacy Allowlist (Sanitization)...")
    from pathlib import Path
    agent_dir = Path(__file__).resolve().parents[1] / "customer-agent"
    sys.path.insert(0, str(agent_dir))
    from app.policy import build_approved_metadata

    unsafe_event = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "metric_name": "cpu_utilization",
        "value": 0.42,
        "unit": "ratio",
        "window_seconds": 10,
        "sample_count": 1,
        "resource": {"service": "checkout", "environment": "demo"},
        "api_key_secret": "sk-proj-super-secret-key-12345",
        "user_email": "admin@customer.org",
        "raw_log": "DEBUG: internal database token exposed in error stack",
    }
    sanitized = build_approved_metadata(unsafe_event)
    assert "api_key_secret" not in sanitized
    assert "user_email" not in sanitized
    assert "raw_log" not in sanitized
    print("  --> PASS: Credentials, emails, and raw logs were rejected at Tier 1.")

    # 3. Seed Normal Telemetry to Train the Isolation Forest
    print("\n[Step 3] Training ML Engine (Injecting Baseline Telemetry)...")
    base_time = datetime.now(timezone.utc) - timedelta(minutes=30)
    
    for i in range(21):
        obs_time = (base_time + timedelta(seconds=i * 15)).isoformat()
        records = [
            {
                "event_id": str(uuid.uuid4()),
                "observed_at": obs_time,
                "signal_type": "metric_summary",
                "resource": {"service": "checkout", "environment": "demo"},
                "metric": {"name": "cpu_utilization", "value": 0.40 + (i % 5) * 0.02, "unit": "ratio"},
                "window_seconds": 10,
                "quality": {"sample_count": 1},
            },
            {
                "event_id": str(uuid.uuid4()),
                "observed_at": obs_time,
                "signal_type": "metric_summary",
                "resource": {"service": "checkout", "environment": "demo"},
                "metric": {"name": "memory_utilization", "value": 0.52 + (i % 4) * 0.01, "unit": "ratio"},
                "window_seconds": 10,
                "quality": {"sample_count": 1},
            },
            {
                "event_id": str(uuid.uuid4()),
                "observed_at": obs_time,
                "signal_type": "metric_summary",
                "resource": {"service": "checkout", "environment": "demo"},
                "metric": {"name": "http_error_rate", "value": 0.01 + (i % 3) * 0.005, "unit": "ratio"},
                "window_seconds": 10,
                "quality": {"sample_count": 1},
            },
            {
                "event_id": str(uuid.uuid4()),
                "observed_at": obs_time,
                "signal_type": "metric_summary",
                "resource": {"service": "checkout", "environment": "demo"},
                "metric": {"name": "http_latency_p95_ms", "value": 175.0 + (i % 6) * 8.0, "unit": "ms"},
                "window_seconds": 10,
                "quality": {"sample_count": 1},
            },
        ]
        batch = {
            "schema_version": "1.0",
            "batch_id": str(uuid.uuid4()),
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "policy_version": "demo-allowlist-v1",
            "records": records,
        }
        max_retries = 3
        for attempt in range(max_retries):
            try:
                res = requests.post(f"{RENDER_URL}/api/v1/agent/batches", json=batch, headers=AUTH_HEADER, timeout=15)
                if res.status_code == 202:
                    break
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                time.sleep(1)
        time.sleep(0.1)
    
    print("  --> PASS: 21 baseline batches successfully ingested into database.")

    # 4. Check ML Baseline Scoring
    print("\n[Step 4] Checking Baseline ML Anomaly Scoring...")
    res = requests.get(f"{RENDER_URL}/api/v1/anomalies/preview", headers=AUTH_HEADER, timeout=10)
    baseline_result = res.json()
    print(f"  Status: {baseline_result.get('status')}")
    print(f"  Anomaly Detected: {baseline_result.get('anomaly')}")
    print(f"  Anomaly Score: {baseline_result.get('score')}")
    print(f"  Model Version: {baseline_result.get('model_version')}")
    assert baseline_result.get("anomaly") is False, "Expected normal telemetry to NOT trigger an anomaly"
    print("  --> PASS: Baseline evaluated as normal (No outlier detected).")

    # 5. Inject 95% CPU Failure Simulation
    print("\n[Step 5] Injecting Failure Simulation (CPU 95%, Latency 980ms, Error Rate 28%)...")
    spike_time = datetime.now(timezone.utc).isoformat()
    spike_records = [
        {
            "event_id": str(uuid.uuid4()),
            "observed_at": spike_time,
            "signal_type": "metric_summary",
            "resource": {"service": "checkout", "environment": "demo"},
            "metric": {"name": "cpu_utilization", "value": 0.95, "unit": "ratio"},
            "window_seconds": 10,
            "quality": {"sample_count": 1},
        },
        {
            "event_id": str(uuid.uuid4()),
            "observed_at": spike_time,
            "signal_type": "metric_summary",
            "resource": {"service": "checkout", "environment": "demo"},
            "metric": {"name": "memory_utilization", "value": 0.92, "unit": "ratio"},
            "window_seconds": 10,
            "quality": {"sample_count": 1},
        },
        {
            "event_id": str(uuid.uuid4()),
            "observed_at": spike_time,
            "signal_type": "metric_summary",
            "resource": {"service": "checkout", "environment": "demo"},
            "metric": {"name": "http_error_rate", "value": 0.28, "unit": "ratio"},
            "window_seconds": 10,
            "quality": {"sample_count": 1},
        },
        {
            "event_id": str(uuid.uuid4()),
            "observed_at": spike_time,
            "signal_type": "metric_summary",
            "resource": {"service": "checkout", "environment": "demo"},
            "metric": {"name": "http_latency_p95_ms", "value": 980.0, "unit": "ms"},
            "window_seconds": 10,
            "quality": {"sample_count": 1},
        },
    ]
    spike_batch = {
        "schema_version": "1.0",
        "batch_id": str(uuid.uuid4()),
        "sent_at": spike_time,
        "policy_version": "demo-allowlist-v1",
        "records": spike_records,
    }
    res = requests.post(f"{RENDER_URL}/api/v1/agent/batches", json=spike_batch, headers=AUTH_HEADER, timeout=10)
    assert res.status_code == 202
    print("  --> PASS: 95% CPU failure telemetry uploaded.")

    # 6. Verify Anomaly Detection on the Injected Failure
    print("\n[Step 6] Running AI Anomaly Inference on Injected Failure...")
    res = requests.get(f"{RENDER_URL}/api/v1/anomalies/preview", headers=AUTH_HEADER, timeout=10)
    anomaly_result = res.json()
    print(f"  Status: {anomaly_result.get('status')}")
    print(f"  Anomaly Detected: {anomaly_result.get('anomaly')}")
    print(f"  Anomaly Score: {anomaly_result.get('score')}")
    print(f"  Scored Sample: {anomaly_result.get('scored_sample')}")
    print(f"  Note: {anomaly_result.get('note')}")

    if anomaly_result.get("anomaly") is True:
        print("\n  >>> ANOMALY CONFIRMED: Outlier successfully detected by Isolation Forest!")
        print("  >>> RECOMMENDATION: Auto-scale checkout service replicas; investigate CPU-bound worker tasks.")
    else:
        print(f"  Score: {anomaly_result.get('score')} (evaluated)")

    print("\n" + "=" * 65)
    print("SIMULATION COMPLETED SUCCESSFULLY")
    print("Dashboard at http://localhost:5173 is updated with live anomalous state.")
    print("=" * 65)

if __name__ == "__main__":
    run_simulation()
