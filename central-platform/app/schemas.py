import math
from datetime import datetime
from typing import Literal, Optional, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Resource(StrictModel):
    service: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    environment: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")

class Metric(StrictModel):
    name: Literal[
        "cpu_utilization",
        "memory_utilization",
        "disk_utilization",
        "http_error_rate",
        "http_latency_p95_ms",
        "network_bytes_per_second",
    ]
    value: float
    unit: str = Field(max_length=24)

    @field_validator("value")
    @classmethod
    def finite_and_bounded(cls, value):
        if not math.isfinite(value) or abs(value) > 1_000_000_000:
            raise ValueError("metric value outside supported bounds")
        return value

class Quality(StrictModel):
    sample_count: int = Field(ge=1, le=1_000_000)

class Record(StrictModel):
    event_id: str = Field(min_length=1, max_length=64)
    observed_at: datetime
    signal_type: Literal["metric_summary"]
    resource: Resource
    metric: Metric
    window_seconds: int = Field(ge=1, le=3600)
    quality: Quality

class Batch(StrictModel):
    schema_version: Literal["1.0"]
    batch_id: str = Field(min_length=1, max_length=64)
    sent_at: datetime
    policy_version: str = Field(min_length=1, max_length=64)
    records: list[Record] = Field(min_length=1, max_length=500)

# -------------------------------------------------------------------------
# Step 5 - Dedicated Collector & Ingestion Schemas
# -------------------------------------------------------------------------

class CollectorRegisterIn(StrictModel):
    collector_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=64)
    environment: str = Field(default="production", max_length=64)
    tenant_id: Optional[str] = Field(default=None, max_length=64)

class CollectorHealthOut(BaseModel):
    collector_id: str
    name: str
    environment: str
    status: str
    last_heartbeat: str

class TelemetryEventIn(StrictModel):
    event_id: str = Field(min_length=1, max_length=64)
    tenant_id: Optional[str] = Field(default=None, max_length=64)
    collector_id: Optional[str] = Field(default=None, max_length=64)
    timestamp: Optional[datetime] = None
    observed_at: Optional[datetime] = None
    source_timestamp: Optional[datetime] = None
    collector_timestamp: Optional[datetime] = None
    sequence_number: Optional[int] = Field(default=0, ge=0)
    metric_name: str = Field(min_length=1, max_length=64)
    metric_value: float
    unit: str = Field(default="ratio", max_length=24)
    severity: str = Field(default="info", max_length=24)
    health_status: str = Field(default="healthy", max_length=24)
    event_category: str = Field(default="system", max_length=32)
    service: str = Field(default="cicada-agent", max_length=64)
    environment: str = Field(default="production", max_length=64)

    @field_validator("metric_value")
    @classmethod
    def finite_and_bounded(cls, value):
        if not math.isfinite(value) or abs(value) > 1_000_000_000:
            raise ValueError("metric value outside supported bounds")
        return value

class TelemetryIngestIn(StrictModel):
    payload_id: str = Field(min_length=1, max_length=64)
    collector_id: str = Field(min_length=1, max_length=64)
    timestamp: datetime
    collector_timestamp: Optional[datetime] = None
    records: list[TelemetryEventIn] = Field(min_length=1, max_length=500)
    approved_fields_count: int = Field(default=0, ge=0)
    rejected_fields_count: int = Field(default=0, ge=0)
    redacted_fields: list[str] = Field(default_factory=list)
    sanitized_sample: str = Field(default="")
    policy_version: Optional[str] = Field(default="v1.0-allowlist", max_length=64)
    policy_decision: Optional[str] = Field(default="APPROVED", max_length=32)
    payload_hash: Optional[str] = Field(default="", max_length=64)
    payload_size_bytes: Optional[int] = Field(default=0, ge=0)
    raw_sample_redacted: Optional[str] = Field(default="")
    exact_outbound_payload: Optional[str] = Field(default="")

class EgressAuditOut(BaseModel):
    payload_id: str
    collector_id: str
    sent_at: str
    approved_fields_count: int
    rejected_fields_count: int
    delivery_status: str
    api_response_status: int
    policy_version: str = "v1.0-allowlist"
    policy_decision: str = "APPROVED"
    payload_hash: str = ""
    payload_size_bytes: int = 0
    fields_permitted: list[str] = Field(default_factory=list)
    fields_redacted: list[str] = Field(default_factory=list)
    sanitized_sample: str = ""
    raw_sample_redacted: str = "{}"
    exact_outbound_payload: str = "{}"


# -------------------------------------------------------------------------
# Requirement 1: Real-time Telemetry Timestamp Status Schemas
# -------------------------------------------------------------------------

class RealtimeTelemetryStatusOut(BaseModel):
    last_event_id: str
    source_timestamp: Optional[str] = None
    collector_timestamp: Optional[str] = None
    ingestion_timestamp: str
    processing_timestamp: str
    ingestion_delay_ms: float
    processing_delay_ms: float
    total_e2e_delay_ms: float
    collector_heartbeat_age_seconds: float
    telemetry_freshness_status: str  # FRESH, AGING, STALE, EXPIRED
    delayed_events_count: int
    duplicate_events_count: int
    out_of_order_count: int
    total_events_ingested: int
    sequence_number: int
    is_delayed: bool
    is_out_of_order: bool


# -------------------------------------------------------------------------
# Requirement 2: Organiser Stream Connection Status Schemas
# -------------------------------------------------------------------------

class StreamStatusOut(BaseModel):
    stream_name: str
    endpoint_url: str
    transport_protocol: str
    status: str  # CONNECTED, CONNECTING, RECONNECTING, DISCONNECTED, ERROR
    last_event_id: Optional[str] = None
    last_event_timestamp: Optional[str] = None
    events_received_count: int = 0
    duplicate_events_count: int = 0
    delayed_events_count: int = 0
    reconnect_attempts: int = 0
    last_heartbeat: str
    error_message: str = ""


# -------------------------------------------------------------------------
# AIOps Explainable Anomaly Detection Schemas
# -------------------------------------------------------------------------

class AnomalyDetailOut(BaseModel):
    metric_name: str
    category: str
    severity: str
    current_value: float
    baseline_value: float
    deviation_pct: float
    z_score: float
    confidence: float
    summary: str
    probable_cause: str
    recommended_action: str

class AIOpsPreviewOut(BaseModel):
    tenant_id: str
    status: str
    anomaly: bool
    score: float
    severity: str
    model_version: str
    explanation: str
    probable_cause: str
    recommendation: str
    signals: list[dict[str, Any]] = Field(default_factory=list)
    anomalies: list[AnomalyDetailOut] = Field(default_factory=list)
    dynamic_baselines: dict[str, Any] = Field(default_factory=dict)
    security_risk_index: int = 0
    note: str = ""


# -------------------------------------------------------------------------
# SRE Four-State Health Classification Schemas
# -------------------------------------------------------------------------

class MetricHealthDetail(BaseModel):
    metric_name: str
    current_value: float
    unit: str
    state: str  # EXCELLENT, GOOD, FAIR, POOR
    threshold_applied: dict[str, float]
    reason: str

class CollectorHealthDetail(BaseModel):
    collector_id: str
    status: str
    last_heartbeat: Optional[str] = None
    freshness_seconds: Optional[float] = None
    state: str  # EXCELLENT, GOOD, FAIR, POOR
    reason: str

class FreshnessHealthDetail(BaseModel):
    last_telemetry_at: Optional[str] = None
    age_seconds: Optional[float] = None
    state: str  # EXCELLENT, GOOD, FAIR, POOR
    reason: str

class AnomalyHealthDetail(BaseModel):
    active_count: int
    critical_count: int
    warning_count: int
    max_severity: str
    state: str  # EXCELLENT, GOOD, FAIR, POOR
    reason: str

class HealthTransitionOut(BaseModel):
    id: int
    tenant_id: str
    from_state: str
    to_state: str
    overall_health: str
    reason: str
    metrics_snapshot: str
    transitioned_at: str

class SystemHealthOut(BaseModel):
    tenant_id: str
    overall_health: str  # EXCELLENT, GOOD, FAIR, POOR
    evaluated_at: str
    summary_reason: str
    reasons: list[str]
    metrics: list[MetricHealthDetail]
    collector: CollectorHealthDetail
    freshness: FreshnessHealthDetail
    anomalies: AnomalyHealthDetail
    latest_transition: Optional[HealthTransitionOut] = None
    transitions_count: int = 0


# -------------------------------------------------------------------------
# SRE Incident Correlation & Lifecycle Schemas
# -------------------------------------------------------------------------

class CorrelatedAlert(BaseModel):
    alert_id: str
    service: str
    metric_name: str
    category: str
    severity: str
    current_value: float
    baseline_value: float
    deviation_pct: float
    timestamp: str
    summary: str

class IncidentOut(BaseModel):
    id: int
    incident_id: str
    tenant_id: str
    title: str
    priority: str  # Critical, High, Medium, Low
    status: str    # Open, Investigating, Resolved, Closed
    category: str
    affected_components: list[str]
    probable_root_cause: str
    confidence_score: float
    recommended_investigation: str
    contributing_signals: list[str]
    alert_count: int
    timeline: list[CorrelatedAlert]
    created_at: str
    updated_at: str
    resolved_at: Optional[str] = None

class IncidentStatusUpdateIn(BaseModel):
    status: Literal["Open", "Investigating", "Resolved", "Closed"]
    note: Optional[str] = None
