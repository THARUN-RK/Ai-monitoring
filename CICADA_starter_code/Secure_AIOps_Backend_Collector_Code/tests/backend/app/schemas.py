from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class RegisterIn(StrictModel):
    organization_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

class LoginIn(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

class TokenOut(StrictModel):
    access_token: str
    token_type: str = "bearer"
    organization: str

class CollectorRegisterIn(StrictModel):
    name: str = Field(min_length=2, max_length=120)

class CollectorOut(StrictModel):
    id: int
    name: str
    is_active: bool
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class TelemetryMetricIn(StrictModel):
    server_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    environment: str = Field(default="production", max_length=64)
    metric_name: str = Field(pattern=r"^(cpu_percent|memory_percent|disk_percent|network_bytes_sent_rate|network_bytes_recv_rate|uptime_seconds|app_response_ms|app_available)$")
    value: float = Field(ge=0, le=1_000_000_000)
    unit: str = Field(default="", max_length=24)
    observed_at: datetime | None = None

class TelemetryBatchIn(StrictModel):
    records: list[TelemetryMetricIn] = Field(min_length=1, max_length=500)

class TelemetryOut(StrictModel):
    id: int
    server_id: int
    metric_name: str
    value: float
    unit: str
    observed_at: datetime
    model_config = ConfigDict(from_attributes=True)

class HealthOut(StrictModel):
    status: str
    service: str
