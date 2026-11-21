from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class MetricRecord(Base):
    __tablename__ = "metric_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "event_id", name="uq_tenant_event"),
        UniqueConstraint("tenant_id", "batch_id", "event_id", name="uq_tenant_batch_event"),
        Index("ix_tenant_observed", "tenant_id", "observed_at"),
        Index("ix_tenant_sequence", "tenant_id", "agent_id", "sequence_number"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    service: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(24), nullable=False)
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    # Requirement 1: Timestamp-based Real-time Measurement
    source_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collector_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ingestion_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    processing_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    sequence_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ingestion_delay_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    processing_delay_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_e2e_delay_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_delayed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_out_of_order: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CollectorRecord(Base):
    __tablename__ = "collector_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "collector_id", name="uq_tenant_collector"),
        Index("ix_collector_last_seen", "tenant_id", "last_heartbeat"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    collector_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), default="production", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="online", nullable=False)
    last_heartbeat: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    last_sequence_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_events_received: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_events_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delayed_events_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    out_of_order_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class EgressAuditRecord(Base):
    __tablename__ = "egress_audit_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "payload_id", name="uq_tenant_payload"),
        Index("ix_egress_sent_at", "tenant_id", "sent_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    collector_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    approved_fields_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_fields_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(32), default="delivered", nullable=False)
    api_response_status: Mapped[int] = mapped_column(Integer, default=202, nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), default="v1.0-allowlist", nullable=False)
    policy_decision: Mapped[str] = mapped_column(String(32), default="APPROVED", nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    payload_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fields_permitted: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    fields_redacted: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    sanitized_sample: Mapped[str] = mapped_column(Text, default="", nullable=False)
    raw_sample_redacted: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    exact_outbound_payload: Mapped[str] = mapped_column(Text, default="{}", nullable=False)


class StreamConnectionRecord(Base):
    __tablename__ = "stream_connection_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "stream_name", name="uq_tenant_stream"),
        Index("ix_stream_tenant_status", "tenant_id", "status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    stream_name: Mapped[str] = mapped_column(String(64), default="organiser-telemetry-stream", nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(255), default="https://stream.cicada2026.org/telemetry/live", nullable=False)
    transport_protocol: Mapped[str] = mapped_column(String(32), default="SSE/HTTP", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="DISCONNECTED", nullable=False)
    last_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_event_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    events_received_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_events_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delayed_events_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reconnect_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_heartbeat: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    error_message: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class AnomalyRecord(Base):
    __tablename__ = "anomaly_records"
    __table_args__ = (
        Index("ix_anomaly_tenant_time", "tenant_id", "detected_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    service: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="infrastructure", nullable=False)
    severity: Mapped[str] = mapped_column(String(24), default="warning", nullable=False)
    current_value: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_value: Mapped[float] = mapped_column(Float, nullable=False)
    deviation_pct: Mapped[float] = mapped_column(Float, nullable=False)
    z_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.9, nullable=False)
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    probable_cause: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class HealthTransitionRecord(Base):
    __tablename__ = "health_transition_records"
    __table_args__ = (
        Index("ix_health_trans_tenant_time", "tenant_id", "transitioned_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    from_state: Mapped[str] = mapped_column(String(24), nullable=False)
    to_state: Mapped[str] = mapped_column(String(24), nullable=False)
    overall_health: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_snapshot: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    transitioned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class IncidentRecord(Base):
    __tablename__ = "incident_records"
    __table_args__ = (
        UniqueConstraint("tenant_id", "incident_id", name="uq_tenant_incident"),
        Index("ix_incident_tenant_status", "tenant_id", "status"),
        Index("ix_incident_created", "tenant_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    incident_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    priority: Mapped[str] = mapped_column(String(24), default="Medium", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="Open", nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="infrastructure", nullable=False)
    affected_components: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    probable_root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.85, nullable=False)
    recommended_investigation: Mapped[str] = mapped_column(Text, nullable=False)
    contributing_signals: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    alert_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    raw_alerts_payload: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
