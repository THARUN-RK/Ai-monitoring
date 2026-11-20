import sys
import os
import uuid
import json
import tempfile
import importlib.util
from pathlib import Path
from datetime import datetime, timezone

BASE_DIR = Path(__file__).resolve().parent.parent

# 1. Load central-platform modules
sys.path.insert(0, str(BASE_DIR / "central-platform"))
from app.database import Base, engine, SessionLocal
from app.models import MetricRecord, CollectorRecord, EgressAuditRecord
from app.schemas import CollectorRegisterIn, TelemetryIngestIn, TelemetryEventIn
from app.main import (
    register_collector,
    ingest_telemetry,
    get_collector_health,
    get_latest_telemetry,
    get_egress_audit,
)

# 2. Load customer-agent modules via importlib to avoid 'app' namespace collision
def load_module_from_file(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod

agent_policy = load_module_from_file("agent_policy", BASE_DIR / "customer-agent" / "app" / "policy.py")
agent_buffer = load_module_from_file("agent_buffer", BASE_DIR / "customer-agent" / "app" / "buffer.py")
agent_egress = load_module_from_file("agent_egress", BASE_DIR / "customer-agent" / "app" / "egress_proof.py")

sanitize_event = agent_policy.sanitize_event
detect_secrets = agent_policy.detect_secrets
LocalBuffer = agent_buffer.LocalBuffer
EgressProofManager = agent_egress.EgressProofManager

import psutil

TEST_IDENTITY = {"tenant_id": "demo-tenant", "agent_id": "test-collector-1"}


def setup_module():
    Base.metadata.create_all(bind=engine)


# 1. CPU Telemetry Collection
def test_1_cpu_collection():
    cpu = psutil.cpu_percent(interval=0.1)
    assert 0 <= cpu <= 100, "CPU percentage must be between 0 and 100"


# 2. Memory Telemetry Collection
def test_2_memory_collection():
    mem = psutil.virtual_memory().percent
    assert 0 <= mem <= 100, "Memory percentage must be between 0 and 100"


# 3. Disk Telemetry Collection
def test_3_disk_collection():
    disk = psutil.disk_usage("C:\\" if os.name == "nt" else "/").percent
    assert 0 <= disk <= 100, "Disk percentage must be between 0 and 100"


# 4. Secret Detection
def test_4_secret_detection():
    test_cases = [
        ("password=super_secret_db_pass", "password"),
        ("Authorization: Bearer my_secret_token_1234567890", "bearer_token"),
        ("api_key: sk-123456789012345678901234", "api_key"),
        ("token=cic_123456789012345678901234", "collector_key"),
    ]
    for text, expected_type in test_cases:
        detected = detect_secrets(text)
        assert len(detected) > 0, f"Expected to detect secret in '{text}'"


# 5. Secret Redaction
def test_5_secret_redaction():
    raw_event = {
        "event_id": str(uuid.uuid4()),
        "metric_name": "cpu_utilization",
        "metric_value": 0.45,
        "service": "checkout",
        "password": "plain_text_password_123",
        "api_key": "sk-123456789012345678901234",
    }
    sanitized, approved, redacted, rejected = sanitize_event(raw_event)
    assert sanitized is not None
    assert "password" not in sanitized, "Password must be redacted"
    assert "api_key" not in sanitized, "API key must be redacted"
    assert any("password" in r for r in redacted)


# 6. Unknown Field Rejection
def test_6_unknown_field_rejection():
    raw_event = {
        "event_id": str(uuid.uuid4()),
        "metric_name": "memory_utilization",
        "metric_value": 0.60,
        "arbitrary_unapproved_column": "should_be_dropped",
        "random_metadata": 12345,
    }
    sanitized, approved, redacted, rejected = sanitize_event(raw_event)
    assert sanitized is not None
    assert "arbitrary_unapproved_column" not in sanitized
    assert "random_metadata" not in sanitized
    assert "arbitrary_unapproved_column" in rejected
    assert "random_metadata" in rejected


# 7. Approved Metadata Transmission
def test_7_approved_metadata_transmission():
    raw_event = {
        "event_id": str(uuid.uuid4()),
        "tenant_id": "demo-tenant",
        "collector_id": "test-collector-1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metric_name": "cpu_utilization",
        "metric_value": 0.52,
        "service": "checkout",
        "environment": "production",
    }
    sanitized, approved, redacted, rejected = sanitize_event(raw_event)
    assert sanitized is not None
    assert sanitized["metric_name"] == "cpu_utilization"
    assert sanitized["metric_value"] == 0.52


# 8. Collector Registration & Health Check
def test_8_collector_registration_and_health():
    db = SessionLocal()
    try:
        reg_in = CollectorRegisterIn(
            collector_id="collector-pytest-8",
            name="Pytest Collector",
            environment="production",
        )
        reg_res = register_collector(reg_in, TEST_IDENTITY, db)
        assert reg_res["status"] == "online"
        assert reg_res["collector_id"] == "collector-pytest-8"

        health = get_collector_health(TEST_IDENTITY, db)
        collector_ids = [c.collector_id for c in health]
        assert "collector-pytest-8" in collector_ids
    finally:
        db.close()


# 9. Tenant Isolation
def test_9_tenant_isolation():
    db = SessionLocal()
    try:
        telemetry = get_latest_telemetry(100, TEST_IDENTITY, db)
        assert telemetry["tenant_id"] == "demo-tenant"
    finally:
        db.close()


# 10. Database Persistence
def test_10_database_persistence():
    db = SessionLocal()
    try:
        payload_id = str(uuid.uuid4())
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        payload = TelemetryIngestIn(
            payload_id=payload_id,
            collector_id="test-collector-1",
            timestamp=now,
            approved_fields_count=8,
            rejected_fields_count=0,
            records=[
                TelemetryEventIn(
                    event_id=event_id,
                    metric_name="cpu_utilization",
                    metric_value=0.42,
                    service="checkout",
                    environment="production",
                )
            ],
        )
        res = ingest_telemetry(payload, TEST_IDENTITY, db)
        assert res["status"] == "accepted"
        assert res["accepted_records"] == 1

        # Verify persisted record
        latest = get_latest_telemetry(100, TEST_IDENTITY, db)
        event_ids = [r["event_id"] for r in latest["records"]]
        assert event_id in event_ids
    finally:
        db.close()


# 11. Duplicate Event Rejection
def test_11_duplicate_event_rejection():
    db = SessionLocal()
    try:
        payload_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        payload = TelemetryIngestIn(
            payload_id=payload_id,
            collector_id="test-collector-1",
            timestamp=now,
            records=[
                TelemetryEventIn(
                    event_id=str(uuid.uuid4()),
                    metric_name="memory_utilization",
                    metric_value=0.55,
                    service="checkout",
                )
            ],
        )
        res1 = ingest_telemetry(payload, TEST_IDENTITY, db)
        assert res1["status"] == "accepted"

        # Duplicate attempt with same payload_id
        res2 = ingest_telemetry(payload, TEST_IDENTITY, db)
        assert res2["status"] == "duplicate"
        assert res2["accepted_records"] == 0
    finally:
        db.close()


# 12 & 13. SaaS Disconnection & Local Buffering
def test_12_and_13_local_buffering():
    with tempfile.TemporaryDirectory() as tmp_dir:
        buf = LocalBuffer(tmp_dir)
        sample_payload = {"payload_id": str(uuid.uuid4()), "test": "sanitized_data"}
        path = buf.put(sample_payload)
        assert path.exists()
        assert buf.count() == 1

        pending = buf.pending()
        assert len(pending) == 1
        data = buf.read(pending[0])
        assert data["payload_id"] == sample_payload["payload_id"]


# 14. Retry and Reconnection
def test_14_retry_and_reconnection():
    db = SessionLocal()
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            buf = LocalBuffer(tmp_dir)
            payload_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)

            buf.put({
                "payload_id": payload_id,
                "collector_id": "test-collector-retry",
                "timestamp": now.isoformat(),
                "records": [
                    {
                        "event_id": str(uuid.uuid4()),
                        "metric_name": "disk_utilization",
                        "metric_value": 0.75,
                        "service": "cicada-agent",
                    }
                ],
            })
            assert buf.count() == 1

            # Simulate reconnect by reading pending and ingesting
            for p in buf.pending():
                data = buf.read(p)
                payload_obj = TelemetryIngestIn(
                    payload_id=data["payload_id"],
                    collector_id=data["collector_id"],
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    records=[TelemetryEventIn(**r) for r in data["records"]],
                )
                res = ingest_telemetry(payload_obj, TEST_IDENTITY, db)
                assert res["status"] == "accepted"
                buf.delete(p)

            assert buf.count() == 0, "Buffer should be empty after retry"
    finally:
        db.close()


# 15. Egress Proof Accuracy
def test_15_egress_proof_accuracy():
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "proof.jsonl"
        ep = EgressProofManager(log_file)
        payload_id = str(uuid.uuid4())

        raw = [{"metric_name": "cpu_utilization", "metric_value": 0.5, "password": "xyz"}]
        sanitized = [{"metric_name": "cpu_utilization", "metric_value": 0.5}]

        proof = ep.record_proof(
            payload_id=payload_id,
            collector_id="col-1",
            original_events=raw,
            filtered_events=sanitized,
            approved_fields=["metric_name", "metric_value"],
            redacted_fields=["password"],
            rejected_fields=[],
            outbound_payload={"payload_id": payload_id, "records": sanitized},
            delivery_status="delivered",
        )

        assert proof["payload_id"] == payload_id
        assert "password" in proof["redacted_fields"]
        assert "password" not in proof["filtered_sample"]
        assert proof["delivery_status"] == "delivered"
