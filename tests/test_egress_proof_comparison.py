import sys
import os
import uuid
import json
import importlib.util
from pathlib import Path
from datetime import datetime, timezone
import pytest

BASE_DIR = Path(__file__).resolve().parent.parent

# 1. Load central-platform modules
sys.path.insert(0, str(BASE_DIR / "central-platform"))
from app.database import Base, engine, SessionLocal
from app.models import EgressAuditRecord
from app.schemas import TelemetryIngestIn, TelemetryEventIn
from app.main import ingest_telemetry, get_single_egress_proof

# 2. Load customer-agent modules via importlib to avoid 'app' namespace collision
def load_module_from_file(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod

agent_policy = load_module_from_file("agent_policy", BASE_DIR / "customer-agent" / "app" / "policy.py")
agent_egress = load_module_from_file("agent_egress", BASE_DIR / "customer-agent" / "app" / "egress_proof.py")

sanitize_event = agent_policy.sanitize_event
detect_secrets = agent_policy.detect_secrets
compute_payload_hash = agent_policy.compute_payload_hash
generate_redacted_preview = agent_policy.generate_redacted_preview
EgressProofManager = agent_egress.EgressProofManager

TEST_IDENTITY = {"tenant_id": "test-egress-tenant", "agent_id": "test-collector-egress"}

@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_egress_proof_before_and_after_comparison(db_session, tmp_path):
    """
    Requirement 3 Test: Verify Panel A (Raw local event with detected secrets masked)
    and Panel B (Exact serialized outbound JSON payload without secrets).
    """
    manager = EgressProofManager(log_path=tmp_path / "test_proof.jsonl")

    # Local raw event containing secrets
    raw_event = {
        "event_id": str(uuid.uuid4()),
        "tenant_id": TEST_IDENTITY["tenant_id"],
        "collector_id": TEST_IDENTITY["agent_id"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metric_name": "cpu_utilization",
        "metric_value": 0.42,
        "password": "hunter2_super_secret_password",
        "api_key": "sk-live-cicada-test-secret-token",
        "user_email": "admin@customer.internal",
        "raw_stacktrace": "Traceback (most recent call last): db_connect()",
    }

    # 1. Sanitize event
    sanitized, approved, redacted, rejected = sanitize_event(raw_event)
    assert sanitized is not None
    assert "password" not in sanitized
    assert "api_key" not in sanitized
    assert "user_email" not in sanitized
    assert "raw_stacktrace" not in sanitized
    assert "password (password)" in redacted or "password" in redacted

    # 2. Build outbound payload
    payload_id = str(uuid.uuid4())
    core_outbound = {
        "payload_id": payload_id,
        "collector_id": TEST_IDENTITY["agent_id"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "records": [sanitized],
        "approved_fields_count": len(approved),
        "rejected_fields_count": len(rejected) + len(redacted),
        "redacted_fields": list(set(redacted)),
        "policy_version": "v1.0-strict-allowlist",
        "policy_decision": "APPROVED_WITH_REDACTION",
    }

    payload_hash = compute_payload_hash(core_outbound)
    assert len(payload_hash) == 64  # Valid SHA-256 hex string

    safe_raw_preview = generate_redacted_preview(raw_event)
    assert "hunter2_super_secret_password" not in json.dumps(safe_raw_preview)
    assert "sk-live-cicada" not in json.dumps(safe_raw_preview)
    assert "BLOCKED_LOCALLY" in json.dumps(safe_raw_preview)

    # 3. Record proof
    proof = manager.record_proof(
        payload_id=payload_id,
        collector_id=TEST_IDENTITY["agent_id"],
        original_events=[raw_event],
        filtered_events=[sanitized],
        approved_fields=approved,
        redacted_fields=redacted,
        rejected_fields=rejected,
        outbound_payload=core_outbound,
        delivery_status="delivered",
    )

    assert proof["payload_hash"] == payload_hash
    assert proof["policy_decision"] == "APPROVED_WITH_REDACTION"

    # 4. Ingest into central platform and verify audit persistence
    ingest_payload = TelemetryIngestIn(
        payload_id=payload_id,
        collector_id=TEST_IDENTITY["agent_id"],
        timestamp=datetime.now(timezone.utc),
        records=[TelemetryEventIn(**sanitized)],
        approved_fields_count=len(approved),
        rejected_fields_count=len(rejected) + len(redacted),
        redacted_fields=list(set(redacted)),
        policy_version="v1.0-strict-allowlist",
        policy_decision="APPROVED_WITH_REDACTION",
        payload_hash=payload_hash,
        payload_size_bytes=proof["payload_size_bytes"],
        raw_sample_redacted=json.dumps(safe_raw_preview),
        exact_outbound_payload=json.dumps(core_outbound, indent=2),
    )

    ingest_res = ingest_telemetry(ingest_payload, identity=TEST_IDENTITY, db=db_session)
    assert ingest_res["status"] == "accepted"

    # Retrieve from audit endpoint
    audit_detail = get_single_egress_proof(payload_id=payload_id, identity=TEST_IDENTITY, db=db_session)
    assert audit_detail.payload_id == payload_id
    assert audit_detail.payload_hash == payload_hash
    assert audit_detail.policy_decision == "APPROVED_WITH_REDACTION"
    assert "BLOCKED_LOCALLY" in audit_detail.raw_sample_redacted
    assert "hunter2" not in audit_detail.exact_outbound_payload
