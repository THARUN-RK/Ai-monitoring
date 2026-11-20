from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON, func
from .database import Base

class EgressAudit(Base):
    __tablename__ = "egress_audit"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    payload_size = Column(Integer, nullable=False)
    dest_endpoint = Column(String, nullable=False)
    allowed_fields = Column(JSON, nullable=False)
    redaction_count = Column(Integer, nullable=False)
    http_status = Column(Integer, nullable=False)
    success = Column(Boolean, nullable=False)
    sanitized_payload = Column(JSON, nullable=True)  # optional trimmed version
