import sys
import uuid
import time
import importlib.util
from pathlib import Path
from datetime import datetime, timezone
import pytest

BASE_DIR = Path(__file__).resolve().parent.parent

# 1. Load central-platform modules
sys.path.insert(0, str(BASE_DIR / "central-platform"))
from app.main import get_stream_status, update_stream_status
from app.schemas import StreamStatusOut
from app.database import Base, engine, SessionLocal

# 2. Load customer-agent modules via importlib to avoid 'app' namespace collision
def load_module_from_file(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod

agent_stream = load_module_from_file("agent_stream", BASE_DIR / "customer-agent" / "app" / "stream_consumer.py")
OrganiserStreamConsumer = agent_stream.OrganiserStreamConsumer

TEST_IDENTITY = {"tenant_id": "test-stream-tenant", "agent_id": "test-agent"}

@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_stream_consumer_event_ingestion_and_timestamp_preservation():
    """
    Requirement 2 Test: Ingest event from stream consumer, verify original timestamp preserved.
    """
    received_events = []
    consumer = OrganiserStreamConsumer(
        stream_url="http://mock.stream/live",
        on_event_received=lambda ev: received_events.append(ev),
    )

    original_ts = "2026-11-21T08:00:00Z"
    event_id = str(uuid.uuid4())
    raw_stream_event = {
        "event_id": event_id,
        "source_timestamp": original_ts,
        "metric_name": "cpu_utilization",
        "metric_value": 0.58,
        "unit": "ratio",
        "service": "order-stream",
        "environment": "production",
        "sequence_number": 101,
    }

    ok, reason, sanitized = consumer.process_incoming_event(raw_stream_event)
    assert ok is True
    assert reason == "accepted"
    assert sanitized is not None
    # Original source timestamp must be preserved
    assert sanitized["source_timestamp"] == original_ts
    assert sanitized["sequence_number"] == 101
    assert consumer.events_received_count == 1
    assert consumer.last_event_id == event_id
    assert len(received_events) == 1


def test_stream_consumer_duplicate_prevention():
    """
    Requirement 2 Test: Reject duplicate event IDs from stream.
    """
    consumer = OrganiserStreamConsumer(stream_url="http://mock.stream/live")
    event_id = str(uuid.uuid4())
    raw_event = {
        "event_id": event_id,
        "metric_name": "memory_utilization",
        "metric_value": 0.75,
    }

    # First event
    ok1, reason1, _ = consumer.process_incoming_event(raw_event)
    assert ok1 is True

    # Same event ID again
    ok2, reason2, _ = consumer.process_incoming_event(raw_event)
    assert ok2 is False
    assert reason2 == "duplicate_event_detected"
    assert consumer.duplicate_events_count == 1


def test_stream_consumer_exponential_backoff():
    """
    Requirement 2 Test: Exponential backoff calculation upon connection failure.
    """
    consumer = OrganiserStreamConsumer(stream_url="http://mock.stream/live")
    assert consumer.current_backoff == 1.0

    # Simulate 3 backoff increments
    consumer.current_backoff = min(consumer.max_backoff, consumer.current_backoff * consumer.backoff_factor)
    assert consumer.current_backoff == 2.0

    consumer.current_backoff = min(consumer.max_backoff, consumer.current_backoff * consumer.backoff_factor)
    assert consumer.current_backoff == 4.0

    consumer.current_backoff = min(consumer.max_backoff, consumer.current_backoff * consumer.backoff_factor)
    assert consumer.current_backoff == 8.0


def test_stream_status_api(db_session):
    """
    Requirement 2 Test: Stream status endpoint reporting and retrieval.
    """
    now = datetime.now(timezone.utc).isoformat()
    status_update = StreamStatusOut(
        stream_name="organiser-telemetry-stream",
        endpoint_url="https://stream.cicada2026.org/live",
        transport_protocol="HTTP_SSE",
        status="CONNECTED",
        last_event_id="STREAM-EVT-9001",
        last_event_timestamp=now,
        events_received_count=42,
        duplicate_events_count=2,
        delayed_events_count=1,
        reconnect_attempts=0,
        last_heartbeat=now,
        error_message="",
    )

    update_stream_status(status_update, identity=TEST_IDENTITY, db=db_session)

    current_status = get_stream_status(identity=TEST_IDENTITY, db=db_session)
    assert current_status.status == "CONNECTED"
    assert current_status.events_received_count == 42
    assert current_status.last_event_id == "STREAM-EVT-9001"
