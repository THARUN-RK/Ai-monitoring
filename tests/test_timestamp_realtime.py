import sys
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "central-platform"))

from app.database import Base, engine, SessionLocal
from app.models import MetricRecord, CollectorRecord
from app.schemas import TelemetryIngestIn, TelemetryEventIn
from app.main import (
    register_collector,
    ingest_telemetry,
    get_realtime_status,
)

TEST_IDENTITY = {"tenant_id": "test-timestamp-tenant", "agent_id": "test-collector-ts"}

@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_timestamp_measured_delay(db_session):
    """
    Requirement 1 Test: Submit telemetry with known timestamps and verify calculated delays.
    """
    # Clean any prior collector state for deterministic test
    col = db_session.query(CollectorRecord).filter(
        CollectorRecord.tenant_id == TEST_IDENTITY["tenant_id"],
        CollectorRecord.collector_id == TEST_IDENTITY["agent_id"],
    ).first()
    if col:
        col.last_sequence_number = 0
        db_session.commit()

    now = datetime.now(timezone.utc)
    # Known source timestamp 2.5 seconds in the past
    source_ts = now - timedelta(seconds=2.5)
    # Known collector timestamp 1.0 second in the past
    collector_ts = now - timedelta(seconds=1.0)

    event_id = str(uuid.uuid4())
    payload_id = str(uuid.uuid4())

    event = TelemetryEventIn(
        event_id=event_id,
        tenant_id=TEST_IDENTITY["tenant_id"],
        collector_id=TEST_IDENTITY["agent_id"],
        source_timestamp=source_ts,
        collector_timestamp=collector_ts,
        sequence_number=1,
        metric_name="cpu_utilization",
        metric_value=0.45,
        unit="ratio",
        service="payment-service",
        environment="production",
    )

    payload = TelemetryIngestIn(
        payload_id=payload_id,
        collector_id=TEST_IDENTITY["agent_id"],
        timestamp=collector_ts,
        collector_timestamp=collector_ts,
        records=[event],
        approved_fields_count=8,
        rejected_fields_count=0,
    )

    res = ingest_telemetry(payload, identity=TEST_IDENTITY, db=db_session)
    assert res["status"] == "accepted"
    assert res["accepted_records"] == 1
    # Ingestion delay should be around 1000ms (within tolerance)
    assert res["ingestion_delay_ms"] >= 500.0

    # Query MetricRecord directly
    rec = db_session.query(MetricRecord).filter(MetricRecord.event_id == event_id).first()
    assert rec is not None
    assert rec.ingestion_delay_ms > 0
    assert rec.total_e2e_delay_ms > rec.ingestion_delay_ms
    assert rec.is_out_of_order is False
    assert rec.sequence_number == 1


def test_out_of_order_sequence_detection(db_session):
    """
    Requirement 1 Test: Detect out-of-order sequence events.
    """
    collector = db_session.query(CollectorRecord).filter(
        CollectorRecord.tenant_id == TEST_IDENTITY["tenant_id"],
        CollectorRecord.collector_id == TEST_IDENTITY["agent_id"],
    ).first()
    if not collector:
        collector = CollectorRecord(
            tenant_id=TEST_IDENTITY["tenant_id"],
            collector_id=TEST_IDENTITY["agent_id"],
            name="Test Collector",
            environment="production",
            last_sequence_number=10,
        )
        db_session.add(collector)
        db_session.commit()
    else:
        collector.last_sequence_number = 10
        db_session.commit()

    now = datetime.now(timezone.utc)
    # Event with sequence number 5 arriving after sequence 10
    out_of_order_event = TelemetryEventIn(
        event_id=str(uuid.uuid4()),
        tenant_id=TEST_IDENTITY["tenant_id"],
        collector_id=TEST_IDENTITY["agent_id"],
        source_timestamp=now,
        collector_timestamp=now,
        sequence_number=5,
        metric_name="memory_utilization",
        metric_value=0.62,
    )

    payload = TelemetryIngestIn(
        payload_id=str(uuid.uuid4()),
        collector_id=TEST_IDENTITY["agent_id"],
        timestamp=now,
        records=[out_of_order_event],
    )

    res = ingest_telemetry(payload, identity=TEST_IDENTITY, db=db_session)
    assert res["status"] == "accepted"

    db_rec = db_session.query(MetricRecord).filter(MetricRecord.event_id == out_of_order_event.event_id).first()
    assert db_rec.is_out_of_order is True
    assert collector.out_of_order_count >= 1


def test_delayed_event_flagging(db_session):
    """
    Requirement 1 Test: Telemetry arriving with high delay (> 15s) is flagged as delayed.
    """
    now = datetime.now(timezone.utc)
    ancient_source_ts = now - timedelta(seconds=25.0)

    event_id = str(uuid.uuid4())
    event = TelemetryEventIn(
        event_id=event_id,
        tenant_id=TEST_IDENTITY["tenant_id"],
        collector_id=TEST_IDENTITY["agent_id"],
        source_timestamp=ancient_source_ts,
        collector_timestamp=ancient_source_ts,
        sequence_number=15,
        metric_name="http_latency_p95_ms",
        metric_value=120.0,
    )

    payload = TelemetryIngestIn(
        payload_id=str(uuid.uuid4()),
        collector_id=TEST_IDENTITY["agent_id"],
        timestamp=ancient_source_ts,
        records=[event],
    )

    ingest_telemetry(payload, identity=TEST_IDENTITY, db=db_session)
    rec = db_session.query(MetricRecord).filter(MetricRecord.event_id == event_id).first()
    assert rec.is_delayed is True
    assert rec.total_e2e_delay_ms >= 20000.0


def test_realtime_status_endpoint(db_session):
    """
    Requirement 1 Test: Verify /api/v1/telemetry/realtime returns genuine calculated metrics.
    """
    status = get_realtime_status(identity=TEST_IDENTITY, db=db_session)
    assert status.last_event_id != "NONE"
    assert status.ingestion_timestamp is not None
    assert status.total_e2e_delay_ms >= 0.0
    assert status.telemetry_freshness_status in ("FRESH", "AGING", "STALE", "EXPIRED")
    assert status.total_events_ingested > 0
