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
    records: list[TelemetryEventIn] = Field(min_length=1, max_length=500)
    approved_fields_count: int = Field(default=0, ge=0)
    rejected_fields_count: int = Field(default=0, ge=0)
    redacted_fields: list[str] = Field(default_factory=list)
    sanitized_sample: str = Field(default="")

class EgressAuditOut(BaseModel):
    payload_id: str
    collector_id: str
    sent_at: str
    approved_fields_count: int
    rejected_fields_count: int
    delivery_status: str
    api_response_status: int
    sanitized_sample: str


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
