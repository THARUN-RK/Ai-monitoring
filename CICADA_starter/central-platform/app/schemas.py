import math
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Resource(StrictModel):
    service: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    environment: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")

class Metric(StrictModel):
    name: Literal["cpu_utilization", "memory_utilization", "http_error_rate",
                  "http_latency_p95_ms", "network_bytes_per_second"]
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
    event_id: str = Field(min_length=36, max_length=36)
    observed_at: datetime
    signal_type: Literal["metric_summary"]
    resource: Resource
    metric: Metric
    window_seconds: int = Field(ge=1, le=3600)
    quality: Quality

class Batch(StrictModel):
    schema_version: Literal["1.0"]
    batch_id: str = Field(min_length=36, max_length=36)
    sent_at: datetime
    policy_version: str = Field(min_length=1, max_length=64)
    records: list[Record] = Field(min_length=1, max_length=500)
